package gchatmeow

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"math"
	"math/rand"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
	"unicode/utf16"

	"go.mau.fi/util/pblite"

	"go.mau.fi/mautrix-googlechat/pkg/gchatmeow/proto"
)

const (
	channelURLBase    = "https://chat.google.com/u/0/webchannel/"
	pushTimeout       = 60 * time.Second
	maxReadBytes      = 1024 * 1024
	protocolVersion   = 8
	initialRequestRID = 10000
)

var (
	ErrNetworkError     = errors.New("network error")
	ErrUnexpectedStatus = errors.New("unexpected status")
	ErrSIDInvalid       = errors.New("SID invalid")
	ErrSIDExpiring      = errors.New("SID expiring")
	ErrChannelLifetime  = errors.New("channel lifetime expired")
)

type Channel struct {
	session          *Session
	maxRetries       int
	retryBackoffBase int
	isConnected      bool
	onConnectCalled  bool
	chunkParser      *ChunkParser
	sidParam         string
	csessionidParam  string
	aid              int
	ofs              int
	rid              int

	OnConnect      *Event
	OnReconnect    *Event
	OnDisconnect   *Event
	OnReceiveArray *Event
}

type UTF16String []uint16

func NewUTF16String(s string) UTF16String {
	return utf16.Encode([]rune(s))
}

func (u UTF16String) String() string {
	return string(utf16.Decode(u))
}

type ChunkParser struct {
	buf []byte
}

func NewChunkParser() *ChunkParser {
	return &ChunkParser{
		buf: make([]byte, 0),
	}
}

func (p *ChunkParser) GetChunks(newDataBytes []byte) []string {
	var chunks []string
	p.buf = append(p.buf, newDataBytes...)

	for {
		bufStr := string(p.buf)
		lengthStr, after, _ := strings.Cut(bufStr, "\n")
		length, err := strconv.Atoi(lengthStr)
		if err != nil {
			break
		}
		utf16Str := NewUTF16String(after)
		if len(utf16Str) < length {
			break
		}

		chunks = append(chunks, utf16Str[0:length].String())
		p.buf = []byte(utf16Str[length:].String())
	}

	return chunks
}

func NewChannel(session *Session, maxRetries, retryBackoffBase int) (*Channel, error) {

	return &Channel{
		session:          session,
		maxRetries:       maxRetries,
		retryBackoffBase: retryBackoffBase,
		rid:              initialRequestRID + rand.Intn(89999),
		OnConnect:        &Event{},
		OnReconnect:      &Event{},
		OnDisconnect:     &Event{},
		OnReceiveArray:   &Event{},
	}, nil
}

func (c *Channel) IsConnected() bool {
	return c.isConnected
}

func (c *Channel) Listen(ctx context.Context, maxAge time.Duration) error {
	retries := 0
	skipBackoff := false

	csessionidParam, err := c.register(ctx)
	if err != nil {
		return fmt.Errorf("failed to register: %w", err)
	}
	c.csessionidParam = csessionidParam

	// start := time.Now()

	for retries <= c.maxRetries {
		// if time.Since(start) > maxAge {
		// 	return ErrChannelLifetime
		// }

		if retries > 0 && !skipBackoff {
			backoffTime := time.Duration(pow(c.retryBackoffBase, retries)) * time.Second
			log.Printf("Backing off for %v seconds", backoffTime)
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(backoffTime):
			}
		}
		skipBackoff = false

		c.chunkParser = &ChunkParser{}

		err := c.longPollRequest(ctx)
		if err != nil {
			if errors.Is(err, ErrSIDExpiring) {
				log.Printf("Long-polling interrupted: %v", err)

				csessionidParam, err = c.register(ctx)
				if err != nil {
					return fmt.Errorf("failed to re-register: %w", err)
				}
				c.csessionidParam = csessionidParam

				retries++
				skipBackoff = true
				continue
			}

			log.Printf("Long-polling request failed: %v", err)
			retries++

			if c.isConnected {
				c.isConnected = false
				c.OnDisconnect.Fire(nil)
			}

			continue
		}

		retries = 0
	}

	return fmt.Errorf("ran out of retries for long-polling request")
}

func (c *Channel) register(ctx context.Context) (string, error) {
	c.sidParam = ""
	c.aid = 0
	c.ofs = 0

	resp, err := c.session.FetchRaw(ctx, http.MethodGet, channelURLBase+"register?ignore_compass_cookie=1", nil, http.Header{
		"Content-Type": {"application/x-protobuf"},
	}, true, nil)
	if err != nil {
		return "", fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("%w: %d %s - %s", ErrUnexpectedStatus, resp.StatusCode, resp.Status, string(body))
	}

	for _, cookie := range resp.Cookies() {
		if cookie.Name == "COMPASS" {
			if strings.HasPrefix(cookie.Value, "dynamite-ui=") {
				return cookie.Value[len("dynamite-ui="):], nil
			}
			log.Printf("COMPASS cookie doesn't start with dynamite-ui= (value: %s)", cookie.Value)
		}
	}

	return "", nil
}

func (c *Channel) sendStreamEvent(ctx context.Context, request *proto.StreamEventsRequest) error {
	params := url.Values{
		"VER": []string{"8"},                      // channel protocol version
		"RID": []string{fmt.Sprintf("%d", c.rid)}, // request identifier
		"t":   []string{"1"},                      // trial
		"SID": []string{c.sidParam},               // session ID
		"AID": []string{strconv.Itoa(c.aid)},      // last acknowledged id
	}
	c.rid++

	// Prepare headers
	headers := http.Header{
		"Content-Type": []string{"application/x-www-form-urlencoded"},
	}

	protoBytes, err := pblite.Marshal(request)
	if err != nil {
		return fmt.Errorf("failed to marshal events request: %w", err)
	}

	jsonBody, err := json.Marshal(protoBytes)
	if err != nil {
		return fmt.Errorf("failed to marshal JSON body: %w", err)
	}

	// Prepare form data
	formData := url.Values{
		"count":     []string{"1"},
		"ofs":       []string{fmt.Sprintf("%d", c.ofs)},
		"req0_data": []string{string(jsonBody)},
	}
	c.ofs++

	res, err := c.session.FetchRaw(ctx, http.MethodPost, channelURLBase+"events", params, headers, true, []byte(formData.Encode()))
	if err != nil {
		return err
	}
	_ = res
	return nil
}

func (c *Channel) sendInitialPing(ctx context.Context) error {
	event := proto.PingEvent{
		State:                      proto.PingEvent_ACTIVE,
		ApplicationFocusState:      proto.PingEvent_FOCUS_STATE_FOREGROUND,
		ClientInteractiveState:     proto.PingEvent_INTERACTIVE,
		ClientNotificationsEnabled: true,
	}
	return c.sendStreamEvent(ctx, &proto.StreamEventsRequest{PingEvent: &event})
}

func (c *Channel) longPollRequest(ctx context.Context) error {
	params := url.Values{
		"VER": {strconv.Itoa(protocolVersion)},
		"RID": {strconv.Itoa(c.rid)},
		"t":   {"1"},
		"zx":  {uniqueID()},
	}

	if c.sidParam == "" {
		params.Set("CVER", "22")
		params.Set("$req", "count=1&ofs=0&req0_data=%5B%5D")
		params.Set("SID", "null")
		c.rid++
	} else {
		params.Set("CI", "0")
		params.Set("TYPE", "xmlhttp")
		params.Set("RID", "rpc")
		params.Set("AID", strconv.Itoa(c.aid))
		params.Set("SID", c.sidParam)
	}

	resp, err := c.session.FetchRaw(ctx, http.MethodGet, channelURLBase+"events", params, http.Header{
		"referer": {"https://chat.google.com/"},
	}, true, nil)
	if err != nil {
		if err == context.DeadlineExceeded {
			return fmt.Errorf("%w: request timed out", ErrNetworkError)
		}
		return fmt.Errorf("%w: %v", ErrNetworkError, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		if resp.StatusCode == http.StatusBadRequest {
			if resp.Status == "Unknown SID" || strings.Contains(string(body), "Unknown SID") {
				return ErrSIDInvalid
			}
		}
		return fmt.Errorf("%w: %d %s - %s", ErrUnexpectedStatus, resp.StatusCode, resp.Status, string(body))
	}

	if initialResp := resp.Header.Get("X-HTTP-Initial-Response"); initialResp != "" {
		sid, err := parseSIDResponse(initialResp)
		if err != nil {
			return fmt.Errorf("failed to parse SID response: %w", err)
		}

		if c.sidParam != sid {
			c.sidParam = sid
			c.aid = 0
			c.ofs = 0

			params := url.Values{
				"VER":  []string{"8"},
				"RID":  []string{"rpc"},
				"SID":  []string{c.sidParam},
				"AID":  []string{strconv.Itoa(c.aid)},
				"CI":   []string{"0"},
				"TYPE": []string{"xmlhttp"},
				"zx":   []string{uniqueID()},
				"t":    []string{"1"},
			}

			if _, err := c.session.FetchRaw(ctx, http.MethodGet, channelURLBase+"events", params, nil, true, nil); err != nil {
				return fmt.Errorf("failed to acknowledge sid")
			}

			if err := c.sendInitialPing(ctx); err != nil {
				return fmt.Errorf("failed to send initial ping: %w", err)
			}
		}
	}

	reader := resp.Body
	buffer := make([]byte, maxReadBytes)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
			n, err := reader.Read(buffer)
			if err != nil {
				if err == io.EOF {
					return nil
				}
				if strings.Contains(err.Error(), "use of closed network connection") {
					return ErrSIDExpiring
				}
				return fmt.Errorf("%w: %v", ErrNetworkError, err)
			}

			if err := c.onPushData(buffer[:n]); err != nil {
				return fmt.Errorf("failed to process push data: %w", err)
			}
		}
	}
}

func (c *Channel) onPushData(dataBytes []byte) error {
	// Log received chunk
	log.Printf("[gchatmeow:channel] received chunk (%d): %s", len(dataBytes), string(dataBytes))

	// Process chunks
	chunks := c.chunkParser.GetChunks(dataBytes)

	for _, chunk := range chunks {
		// Handle connection state
		if !c.isConnected {
			if c.onConnectCalled {
				c.isConnected = true
				c.OnReconnect.Fire(nil)
			} else {
				log.Printf("[gchatmeow:channel] marking as connected")
				c.onConnectCalled = true
				c.isConnected = true
				c.OnConnect.Fire(nil)
			}
		}

		// Parse the container array
		var containerArray [][]interface{}
		if err := json.Unmarshal([]byte(chunk), &containerArray); err != nil {
			log.Printf("[gchatmeow:channel] failed to unmarshal chunk: %#v", chunk)
			return fmt.Errorf("failed to unmarshal chunk: %w", err)
		}

		// Process each inner array
		for _, innerArray := range containerArray {
			// Ensure the inner array has exactly 2 elements
			if len(innerArray) != 2 {
				return fmt.Errorf("invalid inner array length: expected 2, got %d", len(innerArray))
			}

			// Extract array ID and data array
			arrayID, ok := innerArray[0].(float64)
			if !ok {
				return fmt.Errorf("array ID is not a number")
			}

			dataArray := innerArray[1]

			log.Printf("[gchatmeow:channel] inner data array with id %#v: %#v", arrayID, dataArray)

			// Fire receive array event
			c.OnReceiveArray.Fire(dataArray)

			// Update last array ID
			c.aid = int(math.Round(arrayID))
		}
	}

	return nil
}

func uniqueID() string {
	// Implementation of _unique_id from Python code
	return base64.RawURLEncoding.EncodeToString([]byte(fmt.Sprintf("%d", rand.Int63())))
}

func parseSIDResponse(response string) (string, error) {
	var data []interface{}
	if err := json.Unmarshal([]byte(response), &data); err != nil {
		return "", err
	}

	if len(data) < 1 {
		return "", errors.New("invalid SID response format")
	}

	arr, ok := data[0].([]interface{})
	if !ok || len(arr) < 2 {
		return "", errors.New("invalid SID response array format")
	}

	sid, ok := arr[1].([]interface{})[1].(string)
	if !ok {
		return "", errors.New("invalid SID format in response")
	}

	return sid, nil
}

func pow(base, exp int) int {
	result := 1
	for i := 0; i < exp; i++ {
		result *= base
	}
	return result
}
