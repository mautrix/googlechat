package gchatmeow

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"strconv"

	pb "google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"

	"go.mau.fi/mautrix-googlechat/pkg/gchatmeow/proto"
)

func (c *Client) gcRequest(ctx context.Context, endpoint string, requestPB protoreflect.ProtoMessage, responsePB protoreflect.ProtoMessage) error {
	headers := http.Header{}
	if c.xsrfToken != "" {
		headers.Set("x-framework-xsrf-token", c.xsrfToken)
	}

	log.Printf("[gchatmeow:api] proto request to %#v: %#v\n", endpoint, requestPB)
	c.apiReqID++

	requestData, err := pb.Marshal(requestPB)
	if err != nil {
		return fmt.Errorf("failed to serialize protocol buffer: %v", err)
	}

	params := url.Values{}
	params.Set("c", strconv.FormatInt(c.apiReqID, 10))
	params.Set("rt", "b")
	res, err := c.baseRequest(
		ctx,
		fmt.Sprintf("%s/api/%s", gcBaseURL, endpoint),
		"application/x-protobuf",
		"proto",
		requestData,
		headers,
		params,
		http.MethodPost,
	)
	if err != nil {
		return err
	}

	if err := pb.Unmarshal(res.Body, responsePB); err != nil {
		return fmt.Errorf("failed to decode Protocol Buffer response: %v", err)
	}

	log.Printf("[gchatmeow:api] response from %#v: %#v", endpoint, responsePB)
	return nil
}

func (c *Client) baseRequest(
	ctx context.Context,
	urlStr string,
	contentType string,
	responseType string,
	data []byte,
	headers http.Header,
	params url.Values,
	method string,
) (*FetchResponse, error) {
	if headers == nil {
		headers = http.Header{}
	}

	if contentType != "" {
		headers.Set("content-type", contentType)
	}

	if responseType == "proto" {
		headers.Set("X-Goog-Encode-Response-If-Executable", "base64")
	}

	if params == nil {
		params = url.Values{}
	}
	params.Set("alt", responseType)
	params.Set("key", apiKey)

	res, err := c.session.Fetch(ctx, method, urlStr, params, headers, true, data)

	if err != nil {
		return nil, err
	}

	return res, nil
}

func (c *Client) getSelfUserStatus(ctx context.Context) (*proto.GetSelfUserStatusResponse, error) {
	request := &proto.GetSelfUserStatusRequest{
		RequestHeader: c.gcRequestHeader,
	}
	response := &proto.GetSelfUserStatusResponse{}
	err := c.gcRequest(ctx, "get_self_user_status", request, response)
	return response, err
}

func (c *Client) GetMembers(ctx context.Context, ids []string) (*proto.GetMembersResponse, error) {
	memberIds := make([]*proto.MemberId, len(ids))
	for i, id := range ids {
		memberIds[i] = &proto.MemberId{
			Id: &proto.MemberId_UserId{
				UserId: &proto.UserId{Id: id},
			},
		}
	}

	request := &proto.GetMembersRequest{
		RequestHeader: c.gcRequestHeader,
		MemberIds:     memberIds,
	}
	response := &proto.GetMembersResponse{}
	log.Printf("[gchatmeow:api] GetMembers %#v", request)
	err := c.gcRequest(ctx, "get_members", request, response)
	return response, err
}

func (c *Client) paginatedWorld(ctx context.Context) (*proto.PaginatedWorldResponse, error) {
	request := &proto.PaginatedWorldRequest{
		RequestHeader:       c.gcRequestHeader,
		FetchFromUserSpaces: true,
		FetchOptions: []proto.PaginatedWorldRequest_FetchOptions{
			proto.PaginatedWorldRequest_EXCLUDE_GROUP_LITE,
		},
	}
	response := &proto.PaginatedWorldResponse{}
	err := c.gcRequest(ctx, "paginated_world", request, response)
	return response, err
}

func (c *Client) CreateTopic(ctx context.Context, request *proto.CreateTopicRequest) (*proto.CreateTopicResponse, error) {
	request.RequestHeader = c.gcRequestHeader
	response := &proto.CreateTopicResponse{}
	return response, c.gcRequest(ctx, "create_topic", request, response)
}

func (c *Client) CreateMessage(ctx context.Context, request *proto.CreateMessageRequest) (*proto.CreateMessageResponse, error) {
	request.RequestHeader = c.gcRequestHeader
	response := &proto.CreateMessageResponse{}
	return response, c.gcRequest(ctx, "create_message", request, response)
}

func (c *Client) EditMessage(ctx context.Context, request *proto.EditMessageRequest) (*proto.EditMessageResponse, error) {
	request.RequestHeader = c.gcRequestHeader
	response := &proto.EditMessageResponse{}
	return response, c.gcRequest(ctx, "edit_message", request, response)
}

func (c *Client) DeleteMessage(ctx context.Context, request *proto.DeleteMessageRequest) (*proto.DeleteMessageResponse, error) {
	request.RequestHeader = c.gcRequestHeader
	response := &proto.DeleteMessageResponse{}
	return response, c.gcRequest(ctx, "delete_message", request, response)
}

func (c *Client) GetGroup(ctx context.Context, request *proto.GetGroupRequest) (*proto.GetGroupResponse, error) {
	request.RequestHeader = c.gcRequestHeader
	response := &proto.GetGroupResponse{}
	return response, c.gcRequest(ctx, "get_group", request, response)
}

func (c *Client) CatchUpGroup(ctx context.Context, request *proto.CatchUpGroupRequest) (*proto.CatchUpResponse, error) {
	request.RequestHeader = c.gcRequestHeader
	response := &proto.CatchUpResponse{}
	return response, c.gcRequest(ctx, "catch_up_group", request, response)
}

func (c *Client) UpdateReaction(ctx context.Context, request *proto.UpdateReactionRequest) (*proto.UpdateReactionResponse, error) {
	request.RequestHeader = c.gcRequestHeader
	response := &proto.UpdateReactionResponse{}
	return response, c.gcRequest(ctx, "update_reaction", request, response)
}

func (c *Client) SetTypingState(ctx context.Context, request *proto.SetTypingStateRequest) (*proto.SetTypingStateResponse, error) {
	request.RequestHeader = c.gcRequestHeader
	response := &proto.SetTypingStateResponse{}
	return response, c.gcRequest(ctx, "set_typing_state", request, response)
}

func (c *Client) MarkGroupReadstate(ctx context.Context, request *proto.MarkGroupReadstateRequest) (*proto.MarkGroupReadstateResponse, error) {
	request.RequestHeader = c.gcRequestHeader
	response := &proto.MarkGroupReadstateResponse{}
	return response, c.gcRequest(ctx, "mark_group_readstate", request, response)
}

func (c *Client) UploadFile(ctx context.Context, data []byte, groupId string, fileName string, mimeType string) (*proto.UploadMetadata, error) {
	headers := http.Header{
		"x-goog-upload-protocol":       {"resumable"},
		"x-goog-upload-command":        {"start"},
		"x-goog-upload-content-length": {strconv.Itoa(len(data))},
		"x-goog-upload-content-type":   {mimeType},
		"x-goog-upload-file-name":      {fileName},
	}
	res, err := c.baseRequest(
		ctx, uploadURL, "", "", nil,
		headers, url.Values{"group_id": []string{groupId}},
		http.MethodPost,
	)
	if err != nil {
		return nil, err
	}
	newUploadURL := res.Headers.Get("x-goog-upload-url")
	if newUploadURL == "" {
		return nil, errors.New("image upload failed: can not acquire an upload url")
	}

	headers = http.Header{
		"x-goog-upload-command":  {"upload, finalize"},
		"x-goog-upload-protocol": {"resumable"},
		"x-goog-upload-offset":   {"0"},
	}
	res, err = c.baseRequest(
		ctx, newUploadURL, "", "",
		data, headers, nil,
		http.MethodPut,
	)
	if err != nil {
		return nil, err
	}
	body, err := base64.StdEncoding.DecodeString(string(res.Body))
	if err != nil {
		return nil, err
	}
	uploadMetadata := &proto.UploadMetadata{}
	err = pb.Unmarshal(body, uploadMetadata)
	if err != nil {
		return nil, err
	}
	return uploadMetadata, nil
}
