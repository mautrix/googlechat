package connector

import (
	"context"
	"log"
	"time"

	"github.com/rs/zerolog"
	"maunium.net/go/mautrix/bridgev2"
	"maunium.net/go/mautrix/bridgev2/database"
	"maunium.net/go/mautrix/bridgev2/networkid"
	"maunium.net/go/mautrix/bridgev2/simplevent"
	"maunium.net/go/mautrix/event"

	"go.mau.fi/mautrix-googlechat/pkg/gchatmeow/proto"
)

func (c *GChatClient) makeEventMeta(evt *proto.Event, typ bridgev2.RemoteEventType, senderId string, ts int64) simplevent.EventMeta {
	return simplevent.EventMeta{
		Type:      typ,
		PortalKey: c.makePortalKey(evt),
		Sender: bridgev2.EventSender{
			IsFromMe:    senderId == string(c.userLogin.ID),
			SenderLogin: networkid.UserLoginID(senderId),
			Sender:      networkid.UserID(senderId),
		},
		CreatePortal: typ == bridgev2.RemoteEventMessage,
		Timestamp:    time.UnixMicro(ts),
	}
}

func (c *GChatClient) onStreamEvent(ctx context.Context, raw any) {
	evt, ok := raw.(*proto.Event)
	if !ok {
		log.Printf("[connector:handlegchat] can't handle stream event that isn't an event: %#v", raw)
		return
	}

	switch evt.Type {
	case proto.Event_MESSAGE_POSTED:
		msg := evt.Body.GetMessagePosted().Message
		if msg.MessageType != proto.Message_SYSTEM_MESSAGE {
			c.userLogin.Bridge.QueueRemoteEvent(c.userLogin, &simplevent.Message[*proto.Message]{
				EventMeta:          c.makeEventMeta(evt, bridgev2.RemoteEventMessage, msg.Creator.UserId.Id, msg.CreateTime),
				ID:                 networkid.MessageID(msg.Id.MessageId),
				Data:               msg,
				ConvertMessageFunc: c.msgConv.ToMatrix,
			})
		}
	case proto.Event_MESSAGE_UPDATED:
		msg := evt.Body.GetMessagePosted().Message
		eventMeta := c.makeEventMeta(evt, bridgev2.RemoteEventEdit, msg.Creator.UserId.Id, msg.LastEditTime)
		c.userLogin.Bridge.QueueRemoteEvent(c.userLogin, &simplevent.Message[*proto.Message]{
			EventMeta:       eventMeta,
			ID:              networkid.MessageID(msg.Id.MessageId),
			TargetMessage:   networkid.MessageID(msg.Id.MessageId),
			Data:            msg,
			ConvertEditFunc: c.ConvertEdit,
		})
	case proto.Event_MESSAGE_DELETED:
		msg := evt.Body.GetMessageDeleted()
		eventMeta := c.makeEventMeta(evt, bridgev2.RemoteEventMessageRemove, "", msg.Timestamp)
		c.userLogin.Bridge.QueueRemoteEvent(c.userLogin, &simplevent.Message[*proto.Message]{
			EventMeta:     eventMeta,
			TargetMessage: networkid.MessageID(msg.MessageId.MessageId),
		})
	case proto.Event_TYPING_STATE_CHANGED:
		state := evt.Body.GetTypingStateChanged()
		c.userLogin.Bridge.QueueRemoteEvent(c.userLogin, &simplevent.Typing{
			EventMeta: c.makeEventMeta(evt, bridgev2.RemoteEventTyping, state.UserId.Id, state.StartTimestampUsec),
		})
	case proto.Event_READ_RECEIPT_CHANGED:
		changed := evt.Body.GetReadReceiptChanged()
		if changed != nil {
			receipts := changed.ReadReceiptSet.ReadReceipts
			for _, receipt := range receipts {
				c.userLogin.Bridge.QueueRemoteEvent(c.userLogin, &simplevent.Receipt{
					EventMeta: c.makeEventMeta(evt, bridgev2.RemoteEventReadReceipt, receipt.User.UserId.Id, receipt.ReadTimeMicros),
					ReadUpTo:  time.UnixMicro(receipt.ReadTimeMicros),
				})
			}
		}
	case proto.Event_GROUP_UPDATED:
		c.handleGroupUpdated(ctx, evt)
	case proto.Event_MEMBERSHIP_CHANGED:
		c.handleMembershipChanged(ctx, evt)
	}

	c.setPortalRevision(ctx, evt)

	c.handleReaction(ctx, evt)
}

func (c *GChatClient) handleReaction(ctx context.Context, evt *proto.Event) {
	reaction := evt.Body.GetMessageReaction()
	if reaction == nil {
		return
	}

	var eventType bridgev2.RemoteEventType
	if reaction.GetType() == proto.MessageReactionEvent_ADD {
		eventType = bridgev2.RemoteEventReaction
	} else {
		eventType = bridgev2.RemoteEventReactionRemove

	}

	sender := reaction.UserId.GetId()
	messageId := reaction.MessageId.GetMessageId()
	eventMeta := c.makeEventMeta(evt, eventType, sender, reaction.Timestamp)
	eventMeta.LogContext = func(c zerolog.Context) zerolog.Context {
		return c.
			Str("message_id", messageId).
			Str("sender", sender).
			Str("emoji", reaction.Emoji.GetUnicode()).
			Str("type", reaction.GetType().String())
	}
	c.userLogin.Bridge.QueueRemoteEvent(c.userLogin, &simplevent.Reaction{
		EventMeta:     eventMeta,
		EmojiID:       networkid.EmojiID(reaction.Emoji.GetUnicode()),
		Emoji:         reaction.Emoji.GetUnicode(),
		TargetMessage: networkid.MessageID(messageId),
	})
}

func (c *GChatClient) handleGroupUpdated(ctx context.Context, evt *proto.Event) {
	new := evt.Body.GetGroupUpdated().New
	if new == nil || (new.Name == "" && new.AvatarUrl == "") {
		return
	}
	c.userLogin.Bridge.QueueRemoteEvent(c.userLogin, &simplevent.ChatInfoChange{
		EventMeta: c.makeEventMeta(evt, bridgev2.RemoteEventChatInfoChange, "", evt.GetGroupRevision().Timestamp),
		ChatInfoChange: &bridgev2.ChatInfoChange{
			ChatInfo: &bridgev2.ChatInfo{
				Name:   &new.Name,
				Avatar: c.makeAvatar(new.AvatarUrl),
			},
		},
	})
}

func (c *GChatClient) handleMembershipChanged(ctx context.Context, evt *proto.Event) {
	userId := evt.Body.GetMembershipChanged().NewMembership.Id.MemberId.GetUserId().Id
	member := bridgev2.ChatMember{
		EventSender: bridgev2.EventSender{
			IsFromMe: userId == string(c.userLogin.ID),
			Sender:   networkid.UserID(userId),
		},
	}
	switch evt.Body.GetMembershipChanged().NewMembership.MembershipState {
	case proto.MembershipState_MEMBER_JOINED:
		member.Membership = event.MembershipJoin
	case proto.MembershipState_MEMBER_NOT_A_MEMBER:
		member.Membership = event.MembershipLeave
		// case proto.MembershipState_MEMBER_INVITED:
		// 	member.Membership = event.MembershipInvite
	}
	memberMap := map[networkid.UserID]bridgev2.ChatMember{}
	memberMap[networkid.UserID(userId)] = member
	ts := time.Now().UnixMicro()
	if evt.GetGroupRevision() != nil {
		ts = evt.GetGroupRevision().Timestamp
	}
	c.userLogin.Bridge.QueueRemoteEvent(c.userLogin, &simplevent.ChatInfoChange{
		EventMeta: c.makeEventMeta(evt, bridgev2.RemoteEventChatInfoChange, "", ts),
		ChatInfoChange: &bridgev2.ChatInfoChange{
			MemberChanges: &bridgev2.ChatMemberList{
				MemberMap: memberMap,
			},
		},
	})
}

func (c *GChatClient) ConvertEdit(ctx context.Context, portal *bridgev2.Portal, intent bridgev2.MatrixAPI, existing []*database.Message, msg *proto.Message) (*bridgev2.ConvertedEdit, error) {
	cm, err := c.msgConv.ToMatrix(ctx, portal, intent, msg)
	if err != nil {
		return nil, err
	}

	editPart := cm.Parts[len(cm.Parts)-1].ToEditPart(existing[len(existing)-1])
	editPart.Part.EditCount++

	return &bridgev2.ConvertedEdit{
		ModifiedParts: []*bridgev2.ConvertedEditPart{editPart},
	}, nil
}
