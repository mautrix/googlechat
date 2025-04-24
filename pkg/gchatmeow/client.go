package gchatmeow

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"slices"
	"strings"
	"sync"
	"time"

	"go.mau.fi/util/pblite"
	pb "google.golang.org/protobuf/proto"

	"go.mau.fi/mautrix-googlechat/pkg/gchatmeow/proto"
)

const (
	uploadURL = "https://chat.google.com/uploads"
	apiKey    = "AIzaSyD7InnYR3VKdb4j2rMUEbTCIr2VyEazl6k"
	gcBaseURL = "https://chat.google.com/u/0"
)

var (
	wizPattern = regexp.MustCompile(`>window.WIZ_global_data = ({.+?});</script>`)
	logger     = log.New(os.Stdout, "client: ", log.LstdFlags)
)

type Client struct {
	session          *Session
	channel          *Channel
	maxRetries       int
	retryBackoffBase int

	// Events
	OnConnect     *Event
	OnReconnect   *Event
	OnDisconnect  *Event
	OnStreamEvent *Event

	// State
	gcRequestHeader  *proto.RequestHeader
	apiReqID         int64
	xsrfToken        string
	lastTokenRefresh float64

	// Mutex for thread safety
	mu sync.RWMutex
}

func NewClient(cookies *Cookies, userAgent string, maxRetries, retryBackoffBase int) *Client {
	if maxRetries == 0 {
		maxRetries = 5
	}
	if retryBackoffBase == 0 {
		retryBackoffBase = 2
	}

	session, err := NewSession(cookies, userAgent, os.Getenv("HTTP_PROXY"))

	if err != nil {
		return nil
	}
	c := &Client{
		maxRetries:       maxRetries,
		retryBackoffBase: retryBackoffBase,
		lastTokenRefresh: -86400,

		// Initialize channels for events
		OnConnect:     &Event{},
		OnReconnect:   &Event{},
		OnDisconnect:  &Event{},
		OnStreamEvent: &Event{},

		session: session,

		gcRequestHeader: &proto.RequestHeader{
			ClientType:    proto.RequestHeader_WEB,
			ClientVersion: int64(2440378181258),
			ClientFeatureCapabilities: &proto.ClientFeatureCapabilities{
				SpamRoomInvitesLevel: proto.ClientFeatureCapabilities_FULLY_SUPPORTED,
			},
		},
	}

	return c
}

func (c *Client) Connect(ctx context.Context, maxAge time.Duration) error {
	c.apiReqID = 0

	if time.Now().Unix()-int64(c.lastTokenRefresh) > 86400 {
		logger.Println("Refreshing xsrf token before connecting")
		if err := c.RefreshTokens(ctx); err != nil {
			return fmt.Errorf("failed to refresh tokens: %w", err)
		}
	}

	channel, err := NewChannel(c.session, c.maxRetries, c.retryBackoffBase)
	if err != nil {
		return err
	}
	c.channel = channel

	// Set up event forwarding
	c.channel.OnConnect.AddObserver(func(interface{}) {
		c.OnConnect.Fire(nil)
	})
	c.channel.OnReceiveArray.AddObserver(c.onReceiveArray)

	go c.channel.Listen(ctx, maxAge)
	return nil
}

func (c *Client) RefreshTokens(ctx context.Context) error {
	params := url.Values{
		"origin": {"https://mail.google.com"},
		"shell":  {"9"},
		"hl":     {"en"},
		"wfi":    {"gtn-roster-iframe-id"},
		"hs":     {`["h_hs",null,null,[1,0],null,null,"gmail.pinto-server_20230730.06_p0",1,null,[15,38,36,35,26,30,41,18,24,11,21,14,6],null,null,"3Mu86PSulM4.en..es5",0,null,null,[0]]`},
	}

	headers := http.Header{
		"authority": {"chat.google.com"},
		"referer":   {"https://mail.google.com/"},
	}

	resp, err := c.session.Fetch(ctx, http.MethodGet, fmt.Sprintf("%s/mole/world", gcBaseURL), params, headers, true, nil)
	if err != nil {
		return err
	}

	matches := wizPattern.FindSubmatch(resp.Body)
	if len(matches) != 2 {
		return fmt.Errorf("didn't find WIZ_global_data in /mole/world response")
	}

	var wizData struct {
		QwAQke string `json:"qwAQke"`
		SMqcke string `json:"SMqcke"`
	}
	if err := json.Unmarshal(matches[1], &wizData); err != nil {
		return fmt.Errorf("non-JSON WIZ_global_data in /mole/world response: %w", err)
	}

	if wizData.QwAQke == "AccountsSignInUi" {
		// return ErrNotLoggedIn
		return fmt.Errorf("ErrNotLoggedIn")
	}

	c.mu.Lock()
	c.xsrfToken = wizData.SMqcke
	c.lastTokenRefresh = float64(time.Now().Unix())
	c.mu.Unlock()

	return nil
}

func (c *Client) onReceiveArray(arg interface{}) {
	array, ok := arg.([]interface{})
	if !ok {
		log.Printf("[gchatmeow:client] error: expected arg to be any, got %T: %#v", array[0], array[0])
		return
	}

	if len(array) == 0 {
		log.Printf("[gchatmeow:client] error: got empty array")
		return
	}

	// Check for noop (keep-alive)
	if str, ok := array[0].(string); ok && str == "noop" {
		return // Ignore keep-alive
	}

	// Get the data from array
	data, ok := array[0].([]interface{})
	if !ok {
		log.Printf("[gchatmeow:client] error: expected array[0] to be any, got %T: %#v", array[0], array[0])
	}

	bytes, err := json.Marshal(data)
	if err != nil {
		log.Printf("[gchatmeow:client] error: failed to marshal data to json: %#v", err)
		return
	}

	// Create and decode protobuf response
	resp := &proto.StreamEventsResponse{}
	if err := pblite.Unmarshal(bytes, resp); err != nil {
		fmt.Println(fmt.Errorf("failed to decode proto: %w", err))
		return
	}

	log.Printf("[gchatmeow:client] stream event response: %#v", resp)

	// Process each event body
	for _, evt := range c.SplitEventBodies(resp.GetEvent()) {
		log.Printf("[gchatmeow:client] dispatching stream event: %#v", evt.String())
		c.OnStreamEvent.Fire(evt)
	}

}

func (c *Client) SplitEventBodies(evt *proto.Event) []*proto.Event {
	if evt == nil {
		return nil
	}

	var events []*proto.Event

	// Handle embedded bodies
	embeddedBodies := evt.GetBodies()
	if len(embeddedBodies) > 0 {
		// Clear the bodies field in the original event
		evt.Bodies = nil
	}

	// If there's a body in the main event, include it
	if evt.Body != nil {
		events = append(events, pb.Clone(evt).(*proto.Event))
	}

	// Process each embedded body
	for _, body := range embeddedBodies {
		evtCopy := pb.Clone(evt).(*proto.Event)
		evtCopy.Body = pb.Clone(body).(*proto.Event_EventBody)
		evtCopy.Type = body.GetEventType()
		events = append(events, evtCopy)
	}

	return events
}

func (c *Client) GetSelf(ctx context.Context) (*proto.User, error) {
	status, err := c.getSelfUserStatus(ctx)
	if err != nil {
		return nil, err
	}
	gcid := status.UserStatus.UserId.Id
	log.Printf("[gchatmeow:client] attempting to get self (gcid: %#v)", gcid)
	members, err := c.GetMembers(ctx, []string{gcid})
	if err != nil {
		return nil, err
	}
	return members.Members[0].GetUser(), nil
}

func (c *Client) Sync(ctx context.Context) (*proto.PaginatedWorldResponse, error) {
	return c.paginatedWorld(ctx)
}

func (c *Client) DownloadAttachment(ctx context.Context, attUrl *url.URL) (*http.Response, error) {
	urlStr := attUrl.String()
	if strings.HasSuffix(attUrl.Host, ".google.com") {
		resp, err := c.session.FetchRaw(ctx, http.MethodGet, urlStr, nil, nil, false, nil)
		if err != nil {
			return nil, err
		}
		if slices.Contains([]int{301, 302, 307, 308}, resp.StatusCode) {
			redirected, err := url.Parse(resp.Header.Get("Location"))
			if err != nil {
				return nil, err
			}
			return c.DownloadAttachment(ctx, redirected)
		}
	}

	// External attachment
	return http.Get(urlStr)
}
