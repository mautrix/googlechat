# mautrix-googlechat - A Matrix-Google Chat puppeting bridge
# Copyright (C) 2021 Tulir Asokan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from typing import (Any, Dict, Optional, List, Awaitable, Union, Callable, AsyncIterable, cast,
                    TYPE_CHECKING)
import datetime
import asyncio

import hangups
from hangups import (hangouts_pb2 as hangouts, googlechat_pb2 as googlechat,
                     Client, UserList, RefreshTokenCache, ConversationEvent, ChatMessageEvent,
                     MembershipChangeEvent)
from hangups.auth import TokenManager, GoogleAuthError
from hangups.conversation import ConversationList, Conversation
from hangups.parsers import TypingStatusMessage, WatermarkNotification

from mautrix.types import UserID, RoomID, MessageType
from mautrix.bridge import BaseUser, BridgeState, async_getter_lock
from mautrix.util.bridge_state import BridgeStateEvent
from mautrix.util.opt_prometheus import Gauge, Summary, async_time

from .config import Config
from .db import User as DBUser, Message as DBMessage
from . import puppet as pu, portal as po

if TYPE_CHECKING:
    from .__main__ import GoogleChatBridge

METRIC_SYNC_CHATS = Summary('bridge_sync_chats', 'calls to sync_chats')
METRIC_SYNC_USERS = Summary('bridge_sync_users', 'calls to sync_users')
METRIC_TYPING = Summary('bridge_on_typing', 'calls to on_typing')
METRIC_EVENT = Summary('bridge_on_event', 'calls to on_event')
METRIC_RECEIPT = Summary('bridge_on_receipt', 'calls to on_receipt')
METRIC_LOGGED_IN = Gauge('bridge_logged_in', 'Number of users logged into the bridge')
METRIC_CONNECTED = Gauge('bridge_connected', 'Number of users connected to Hangouts')


class User(DBUser, BaseUser):
    by_mxid: Dict[UserID, 'User'] = {}
    by_gcid: Dict[str, 'User'] = {}
    config: Config

    client: Optional[Client]
    is_admin: bool
    _db_instance: Optional[DBUser]

    _notice_room_lock: asyncio.Lock
    _intentional_disconnect: bool
    name: Optional[str]
    name_future: asyncio.Future
    connected: bool

    chats: Optional[ConversationList]
    chats_future: asyncio.Future
    users: Optional[UserList]

    def __init__(self, mxid: UserID, gcid: Optional[str] = None,
                 refresh_token: Optional[str] = None, notice_room: Optional[RoomID] = None
                 ) -> None:
        super().__init__(mxid=mxid, gcid=gcid, refresh_token=refresh_token,
                         notice_room=notice_room)
        BaseUser.__init__(self)
        self._notice_room_lock = asyncio.Lock()
        self.is_whitelisted, self.is_admin, self.level = self.config.get_permissions(mxid)
        self.client = None
        self.name = None
        self.name_future = asyncio.Future()
        self.connected = False
        self.chats = None
        self.chats_future = asyncio.Future()
        self.users = None
        self._intentional_disconnect = False

    # region Sessions

    def _add_to_cache(self) -> None:
        self.by_mxid[self.mxid] = self
        if self.gcid:
            self.by_gcid[self.gcid] = self

    @classmethod
    async def all_logged_in(cls) -> AsyncIterable['User']:
        users = await super().all_logged_in()
        user: cls
        for user in users:
            try:
                yield cls.by_mxid[user.mxid]
            except KeyError:
                user._add_to_cache()
                yield user

    @classmethod
    @async_getter_lock
    async def get_by_mxid(cls, mxid: UserID, *, create: bool = True) -> Optional['User']:
        if pu.Puppet.get_id_from_mxid(mxid) or mxid == cls.az.bot_mxid:
            return None
        try:
            return cls.by_mxid[mxid]
        except KeyError:
            pass

        user = cast(cls, await super().get_by_mxid(mxid))
        if user is not None:
            user._add_to_cache()
            return user

        if create:
            cls.log.debug(f"Creating user instance for {mxid}")
            user = cls(mxid)
            await user.insert()
            user._add_to_cache()
            return user

        return None

    @classmethod
    @async_getter_lock
    async def get_by_gcid(cls, gcid: str) -> Optional['User']:
        try:
            return cls.by_gcid[gcid]
        except KeyError:
            pass

        user = cast(cls, await super().get_by_gcid(gcid))
        if user is not None:
            user._add_to_cache()
            return user

        return None

    # endregion

    async def fill_bridge_state(self, state: BridgeState) -> None:
        await super().fill_bridge_state(state)
        state.remote_id = str(self.gcid)
        state.remote_name = ""
        if self.gcid:
            puppet = await pu.Puppet.get_by_gcid(self.gcid)
            state.remote_name = puppet.name

    async def get_notice_room(self) -> RoomID:
        if not self.notice_room:
            async with self._notice_room_lock:
                # If someone already created the room while this call was waiting,
                # don't make a new room
                if self.notice_room:
                    return self.notice_room
                self.notice_room = await self.az.intent.create_room(
                    is_direct=True, invitees=[self.mxid],
                    topic="Google Chat bridge notices")
                await self.save()
        return self.notice_room

    async def send_bridge_notice(self, text: str, important: bool = False,
                                 state_event: Optional[BridgeStateEvent] = None) -> None:
        if state_event:
            await self.push_bridge_state(state_event, message=text)
        if self.config["bridge.disable_bridge_notices"]:
            return
        elif not important and not self.config["bridge.unimportant_bridge_notices"]:
            return
        msgtype = MessageType.TEXT if important else MessageType.NOTICE
        try:
            await self.az.intent.send_text(await self.get_notice_room(), text, msgtype=msgtype)
        except Exception:
            self.log.warning("Failed to send bridge notice '%s'", text, exc_info=True)

    async def is_logged_in(self) -> bool:
        return self.client and self.connected

    @classmethod
    def init_cls(cls, bridge: 'GoogleChatBridge') -> AsyncIterable[Awaitable[None]]:
        cls.bridge = bridge
        cls.az = bridge.az
        cls.config = bridge.config
        cls.loop = bridge.loop
        return (user._try_init() async for user in cls.all_logged_in())

    async def _try_init(self) -> None:
        try:
            token_mgr = await TokenManager.from_refresh_token(UserRefreshTokenCache(self))
        except GoogleAuthError as e:
            await self.send_bridge_notice(
                f"Failed to resume session with stored refresh token: {e}",
                state_event=BridgeStateEvent.BAD_CREDENTIALS,
                important=True,
            )
            self.log.exception("Failed to resume session with stored refresh token")
        else:
            await self.login_complete(token_mgr)

    async def login_complete(self, token_manager: TokenManager) -> None:
        self.client = Client(
            token_manager, max_retries=self.config['bridge.reconnect.max_retries'],
                             retry_backoff_base=self.config['bridge.reconnect.retry_backoff_base'])
        asyncio.create_task(self.start())
        self.client.on_connect.add_observer(self.on_connect)
        self.client.on_reconnect.add_observer(self.on_reconnect)
        self.client.on_disconnect.add_observer(self.on_disconnect)

    async def start(self) -> None:
        try:
            self._intentional_disconnect = False
            await self.client.connect()
            self._track_metric(METRIC_CONNECTED, False)
            if self._intentional_disconnect:
                self.log.info("Client connection finished")
            else:
                self.log.warning("Client connection finished unexpectedly")
                await self.send_bridge_notice("Client connection finished unexpectedly",
                                              state_event=BridgeStateEvent.UNKNOWN_ERROR,
                                              important=True)
        except Exception as e:
            self._track_metric(METRIC_CONNECTED, False)
            self.log.exception("Exception in connection")
            await self.send_bridge_notice(f"Exception in Google Chat connection: {e}",
                                          state_event=BridgeStateEvent.UNKNOWN_ERROR,
                                          important=True)

    async def stop(self) -> None:
        if self.client:
            self._intentional_disconnect = True
            await self.client.disconnect()

    async def logout(self) -> None:
        self._track_metric(METRIC_LOGGED_IN, False)
        await self.stop()
        self.client = None
        self.by_gcid.pop(self.gcid, None)
        self.gcid = None
        self.refresh_token = None
        self.connected = False

        self.chats = None
        if not self.chats_future.done():
            self.chats_future.set_exception(Exception("logged out"))
        self.chats_future = asyncio.Future()
        self.users = None

        self.name = None
        if not self.name_future.done():
            self.name_future.set_exception(Exception("logged out"))
        self.name_future = asyncio.Future()

    async def on_connect(self) -> None:
        self.connected = True
        asyncio.create_task(self.on_connect_later())
        await self.send_bridge_notice("Connected to Hangouts")

    async def on_connect_later(self) -> None:
        try:
            info = await self.client.get_self_user_status(googlechat.GetSelfUserStatusRequest(
                request_header=self.client.get_gc_request_header()
            ))
        except Exception:
            self.log.exception("Failed to get_self_info")
            return
        self.gcid = info.user_status.user_id.id
        self.by_gcid[self.gcid] = self
        self._track_metric(METRIC_CONNECTED, True)
        self._track_metric(METRIC_LOGGED_IN, True)
        await self.save()

        try:
            puppet = await pu.Puppet.get_by_gcid(self.gcid)
            if puppet.custom_mxid != self.mxid and puppet.can_auto_login(self.mxid):
                self.log.info(f"Automatically enabling custom puppet")
                await puppet.switch_mxid(access_token="auto", mxid=self.mxid)
        except Exception:
            self.log.exception("Failed to automatically enable custom puppet")

        try:
            await self.sync()
        except Exception:
            self.log.exception("Failed to sync conversations and users")

    async def on_reconnect(self) -> None:
        self.connected = True
        await self.send_bridge_notice("Reconnected to Hangouts")
        await self.push_bridge_state(BridgeStateEvent.CONNECTED)

    async def on_disconnect(self) -> None:
        self.connected = False
        await self.send_bridge_notice("Disconnected from Google Chat")
        await self.push_bridge_state(BridgeStateEvent.TRANSIENT_DISCONNECT,
                                     error="googlechat-disconnected")

    async def sync(self) -> None:
        await self.push_bridge_state(BridgeStateEvent.BACKFILLING)
        users, chats = await hangups.build_user_conversation_list(self.client)
        await asyncio.gather(self.sync_users(users), self.sync_chats(chats))
        await self.push_bridge_state(BridgeStateEvent.CONNECTED)

    @async_time(METRIC_SYNC_USERS)
    async def sync_users(self, users: UserList) -> None:
        self.users = users
        puppets: Dict[str, pu.Puppet] = {}
        update_avatars = self.config["bridge.update_avatar_initial_sync"]
        updates = []
        self.name = users.get_self().full_name
        self.name_future.set_result(self.name)
        for info in users.get_all():
            if not info.id_:
                self.log.debug(f"Found user without gaia_id: {info}")
                continue
            puppet = await pu.Puppet.get_by_gcid(info.id_, create=True)
            puppets[puppet.gcid] = puppet
            updates.append(puppet.update_info(self, info, update_avatar=update_avatars))
        self.log.debug(f"Syncing info of {len(updates)} puppets "
                       f"(avatars included: {update_avatars})...")
        await asyncio.gather(*updates)

    def _ensure_future_proxy(self, method: Callable[[Any], Awaitable[None]]
                             ) -> Callable[[Any], Awaitable[None]]:
        async def try_proxy(*args, **kwargs) -> None:
            try:
                await method(*args, **kwargs)
            except Exception:
                self.log.exception("Exception in event handler")

        async def proxy(*args, **kwargs) -> None:
            asyncio.ensure_future(try_proxy(*args, **kwargs))

        return proxy

    async def get_direct_chats(self) -> Dict[UserID, List[RoomID]]:
        return {
            pu.Puppet.get_mxid_from_id(portal.other_user_id): [portal.mxid]
            async for portal in po.Portal.get_all_by_receiver(self.gcid)
            if portal.mxid
        }

    @async_time(METRIC_SYNC_CHATS)
    async def sync_chats(self, chats: ConversationList) -> None:
        self.chats = chats
        self.chats_future.set_result(None)
        portals = {conv.id_: await po.Portal.get_by_conversation(conv, self.gcid)
                   for conv in chats.get_all()}
        self.chats.on_watermark_notification.add_observer(
            self._ensure_future_proxy(self.on_receipt))
        self.chats.on_event.add_observer(self._ensure_future_proxy(self.on_event))
        self.chats.on_typing.add_observer(self._ensure_future_proxy(self.on_typing))
        # self.log.debug("Fetching recent conversations to create portals for")
        # res = await self.client.sync_recent_conversations(hangouts.SyncRecentConversationsRequest(
        #     request_header=self.client.get_request_header(),
        #     max_conversations=config["bridge.initial_chat_sync"],
        #     max_events_per_conversation=1,
        #     sync_filter=[hangouts.SYNC_FILTER_INBOX],
        # ))
        convs = self.chats.get_all()
        self.log.debug("Found %d conversations in chat list", len(convs))
        convs = sorted(convs, reverse=True,
                       key=lambda conv: conv.last_modified)
        for chat in convs:
            self.log.debug("Syncing %s", chat.id_)
            portal = await po.Portal.get_by_conversation(chat, self.gcid)
            if portal.mxid:
                await portal.update_matrix_room(self, chat)
                # TODO backfill
                # if len(state.event) > 0 and not DBMessage.get_by_gid(state.event[0].event_id):
                #     self.log.debug("Last message %s in chat %s not found in db, backfilling...",
                #                    state.event[0].event_id, state.conversation_id.id)
                #     await portal.backfill(self, is_initial=False)
            else:
                await portal.create_matrix_room(self, chat)
        await self.update_direct_chats()

    # region Google Chat event handling

    @async_time(METRIC_RECEIPT)
    async def on_receipt(self, event: WatermarkNotification) -> None:
        if not self.chats:
            self.log.debug("Received receipt event before chat list, ignoring")
            return
        conv: Conversation = self.chats.get(event.conv_id)
        portal = await po.Portal.get_by_conversation(conv, self.gcid)
        if not portal:
            return
        message = await DBMessage.get_closest_before(portal.gcid, portal.gc_receiver,
                                                     event.read_timestamp)
        if not message:
            return
        puppet = await pu.Puppet.get_by_gcid(event.user_id)
        await puppet.intent_for(portal).mark_read(message.mx_room, message.mxid)

    @async_time(METRIC_EVENT)
    async def on_event(self, event: ConversationEvent) -> None:
        if not self.chats:
            self.log.debug("Received message event before chat list, waiting for chat list")
            await self.chats_future
        conv: Conversation = self.chats.get(event.conversation_id)
        portal = await po.Portal.get_by_conversation(conv, self.gcid)
        if not portal:
            return

        sender = await pu.Puppet.get_by_gcid(event.user_id)

        if isinstance(event, ChatMessageEvent):
            await portal.backfill_lock.wait(event.id_)
            await portal.handle_googlechat_message(self, sender, event)
        elif isinstance(event, MembershipChangeEvent):
            self.log.info(f"{event.id_} by {event.user_id} in {event.conversation_id} "
                          f"({conv._conversation.type}): {event.participant_ids} {event.type_}'d")
        else:
            self.log.info(f"Unrecognized event {event}")

    @async_time(METRIC_TYPING)
    async def on_typing(self, event: TypingStatusMessage):
        portal = await po.Portal.get_by_gcid(event.conv_id, self.gcid)
        if not portal:
            return
        sender = await pu.Puppet.get_by_gcid(event.user_id, create=False)
        if not sender:
            return
        await portal.handle_hangouts_typing(self, sender, event.status)

    # endregion
    # region Google Chat API calls

    async def set_typing(self, conversation_id: str, typing: bool) -> None:
        self.log.debug(f"set_typing({conversation_id}, {typing})")
        # await self.client.set_typing(hangouts.SetTypingRequest(
        #     request_header=self.client.get_request_header(),
        #     conversation_id=hangouts.ConversationId(id=conversation_id),
        #     type=hangouts.TYPING_TYPE_STARTED if typing else hangouts.TYPING_TYPE_STOPPED,
        # ))

    async def _get_event_request_header(self, conversation_id: str) -> hangouts.EventRequestHeader:
        if not self.chats:
            self.log.debug("Tried to send message before receiving chat list, waiting")
            await self.chats_future
        delivery_medium = self.chats.get(conversation_id)._get_default_delivery_medium()
        return hangouts.EventRequestHeader(
            conversation_id=hangouts.ConversationId(
                id=conversation_id,
            ),
            delivery_medium=delivery_medium,
            client_generated_id=self.client.get_client_generated_id(),
        )

    async def send_emote(self, conversation_id: str, text: str, thread_id: Optional[str] = None,
                        local_id: Optional[str] = None) -> str:
        pass
        # resp = await self.client.send_chat_message(hangouts.SendChatMessageRequest(
        #     request_header=self.client.get_request_header(),
        #     annotation=[hangouts.EventAnnotation(type=4)],
        #     event_request_header=await self._get_event_request_header(conversation_id),
        #     message_content=hangouts.MessageContent(
        #         segment=[hangups.ChatMessageSegment(text).serialize()],
        #     ),
        # ))
        # return resp.created_event.event_id

    async def send_text(self, conversation_id: str, text: str, thread_id: Optional[str] = None,
                        local_id: Optional[str] = None) -> str:
        resp = await self.chats.get(conversation_id).send_message(text, thread_id=thread_id,
                                                                  local_id=local_id)
        return resp.topic.id.topic_id

    async def send_image(self, conversation_id: str, id: str, thread_id: Optional[str] = None,
                        local_id: Optional[str] = None) -> str:
        resp = await self.chats.get(conversation_id).send_message(image_id=id, thread_id=thread_id,
                                                                  local_id=local_id)
        return resp.topic.id.topic_id

    async def mark_read(self, conversation_id: str,
                        timestamp: Optional[Union[datetime.datetime, int]] = None) -> None:
        pass
        # if isinstance(timestamp, datetime.datetime):
        #     timestamp = hangups.parsers.to_timestamp(timestamp)
        # elif not timestamp:
        #     timestamp = int(time.time() * 1_000_000)
        # await self.client.update_watermark(hangouts.UpdateWatermarkRequest(
        #     request_header=self.client.get_request_header(),
        #     conversation_id=hangouts.ConversationId(id=conversation_id),
        #     last_read_timestamp=timestamp,
        # ))

    # endregion


class UserRefreshTokenCache(RefreshTokenCache):
    user: User

    def __init__(self, user: User) -> None:
        self.user = user

    async def get(self) -> str:
        return self.user.refresh_token

    async def set(self, refresh_token: str) -> None:
        self.user.log.trace("New refresh token: %s", refresh_token)
        self.user.refresh_token = refresh_token
        await self.user.save()
