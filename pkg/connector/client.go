package connector

import (
	"context"
	"fmt"
	"strings"
	"time"

	"maunium.net/go/mautrix/bridgev2"
	"maunium.net/go/mautrix/bridgev2/database"
	"maunium.net/go/mautrix/bridgev2/networkid"
	"maunium.net/go/mautrix/bridgev2/simplevent"
	"maunium.net/go/mautrix/bridgev2/status"
	"maunium.net/go/mautrix/event"

	"go.mau.fi/util/ptr"

	"go.mau.fi/mautrix-googlechat/pkg/gchatmeow"
	"go.mau.fi/mautrix-googlechat/pkg/gchatmeow/proto"
	"go.mau.fi/mautrix-googlechat/pkg/msgconv"
)

type GChatClient struct {
	userLogin *bridgev2.UserLogin
	client    *gchatmeow.Client
	users     map[string]*proto.User
	msgConv   *msgconv.MessageConverter
}

var (
	_ bridgev2.NetworkAPI = (*GChatClient)(nil)
)

func NewClient(userLogin *bridgev2.UserLogin, client *gchatmeow.Client) *GChatClient {
	return &GChatClient{
		userLogin: userLogin,
		client:    client,
		users:     map[string]*proto.User{},
		msgConv:   msgconv.NewMessageConverter(userLogin.Bridge, client),
	}
}

func (c *GChatClient) Connect(ctx context.Context) {
	c.client.OnConnect.AddObserver(func(interface{}) { c.onConnect(ctx) })
	c.client.OnStreamEvent.AddObserver(func(evt interface{}) { c.onStreamEvent(ctx, evt) })

	err := c.client.Connect(ctx, time.Duration(90)*time.Minute)
	if err != nil {
		c.userLogin.BridgeState.Send(status.BridgeState{
			StateEvent: status.StateBadCredentials,
			Error:      "googlechat-invalid-credentials",
			Message:    err.Error(),
		})
	}
}

func (c *GChatClient) Disconnect() {
}

var dmCaps = &event.RoomFeatures{
	Edit:  event.CapLevelFullySupported,
	Reply: event.CapLevelFullySupported,
}

var spaceCaps *event.RoomFeatures

func init() {
	spaceCaps = ptr.Clone(dmCaps)
	spaceCaps.Thread = event.CapLevelFullySupported
}

func (c *GChatClient) GetCapabilities(ctx context.Context, portal *bridgev2.Portal) *event.RoomFeatures {
	if strings.Contains(string(portal.ID), "space") {
		return spaceCaps
	}
	return dmCaps
}

func (c *GChatClient) GetChatInfo(ctx context.Context, portal *bridgev2.Portal) (*bridgev2.ChatInfo, error) {
	groupId := portalToGroupId(portal)
	return c.groupToChatInfo(ctx, groupId)
}

func (c *GChatClient) GetUserInfo(ctx context.Context, ghost *bridgev2.Ghost) (*bridgev2.UserInfo, error) {
	user, err := c.getUser(ctx, string(ghost.ID))
	return c.makeUserInfo(user), err
}

func (c *GChatClient) IsLoggedIn() bool {
	return true
}

func (c *GChatClient) IsThisUser(ctx context.Context, userID networkid.UserID) bool {
	return networkid.UserID(c.userLogin.ID) == userID
}

func (c *GChatClient) LogoutRemote(ctx context.Context) {
}

func (c *GChatClient) getUser(ctx context.Context, userId string) (*proto.User, error) {
	if c.users[userId] == nil {
		err := c.getUsers(ctx, []string{userId})
		if err != nil {
			return nil, err
		}
	}
	return c.users[userId], nil
}

func (c *GChatClient) getUsers(ctx context.Context, userIds []string) error {
	idsToFetch := make([]string, 0)
	for _, id := range userIds {
		if c.users[id] == nil {
			idsToFetch = append(idsToFetch, id)
		}
	}
	res, err := c.client.GetMembers(ctx, idsToFetch)
	if err != nil {
		return err
	}
	for _, member := range res.Members {
		user := member.GetUser()
		c.users[user.UserId.Id] = user
	}
	return nil
}

func (c *GChatClient) onConnect(ctx context.Context) {
	res, err := c.client.Sync(ctx)
	if err != nil {
		fmt.Println(err)
		return
	}
	userIdMap := make(map[string]struct{})
	for _, item := range res.WorldItems {
		if item.DmMembers != nil {
			for _, member := range item.DmMembers.Members {
				userIdMap[member.Id] = struct{}{}
			}
		}
	}
	userIds := make([]string, len(userIdMap))
	i := 0
	for userId := range userIdMap {
		userIds[i] = userId
		i++
	}

	err = c.getUsers(ctx, userIds)
	if err != nil {
		fmt.Println(err)
		return
	}

	for _, item := range res.WorldItems {
		var chatInfo *bridgev2.ChatInfo
		if item.DmMembers != nil {
			var dmUser *proto.User
			for _, member := range item.DmMembers.Members {
				if member.Id != string(c.userLogin.ID) {
					dmUser = c.users[member.Id]
					break
				}
			}
			chatInfo = &bridgev2.ChatInfo{
				Name:    &dmUser.Name,
				Members: c.gcMembersToMatrix(true, item.DmMembers.Members),
				Type:    ptr.Ptr(database.RoomTypeDM),
				Avatar:  c.makeAvatar(dmUser.AvatarUrl),
			}
		} else {
			chatInfo, err = c.groupToChatInfo(ctx, item.GroupId)
			if err != nil {
				fmt.Println(err)
				continue
			}
		}

		c.userLogin.Bridge.QueueRemoteEvent(c.userLogin, &simplevent.ChatResync{
			EventMeta: simplevent.EventMeta{
				Type: bridgev2.RemoteEventChatResync,
				PortalKey: networkid.PortalKey{
					ID:       networkid.PortalID(item.GroupId.String()),
					Receiver: c.userLogin.ID,
				},
				CreatePortal: true,
			},
			ChatInfo: chatInfo,
		})

		c.backfillPortal(ctx, item)
	}
}
