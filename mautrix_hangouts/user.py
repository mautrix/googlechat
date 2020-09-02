# mautrix-hangouts - A Matrix-Hangouts puppeting bridge
# Copyright (C) 2019 Tulir Asokan
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
from typing import (Any, Dict, Iterator, Optional, List, Awaitable, Union, Callable,
                    TYPE_CHECKING)
from concurrent import futures
import datetime
import asyncio
import time

import hangups
from hangups import (hangouts_pb2 as hangouts,
                     Client, UserList, RefreshTokenCache, ConversationEvent, ChatMessageEvent,
                     MembershipChangeEvent)
from hangups.conversation import ConversationList, Conversation
from hangups.parsers import TypingStatusMessage, WatermarkNotification

from mautrix.types import UserID, RoomID
from mautrix.client import Client as MxClient
from mautrix.bridge import BaseUser
from mautrix.bridge._community import CommunityHelper, CommunityID

from .config import Config
from .db import User as DBUser, UserPortal, Contact, Message as DBMessage, Portal as DBPortal
from .util.hangups_try_auth import try_auth, TryAuthResp
from . import puppet as pu, portal as po

if TYPE_CHECKING:
    from .context import Context

config: Config


class User(BaseUser):
    by_mxid: Dict[UserID, 'User'] = {}

    client: Optional[Client]
    is_admin: bool
    _db_instance: Optional[DBUser]

    gid: Optional[str]
    refresh_token: Optional[str]
    notice_room: Optional[RoomID]
    _notice_room_lock: asyncio.Lock
    _intentional_disconnect: bool
    name: Optional[str]
    name_future: asyncio.Future
    connected: bool

    chats: Optional[ConversationList]
    chats_future: asyncio.Future
    users: Optional[UserList]

    _community_helper: CommunityHelper
    _community_id: Optional[CommunityID]

    def __init__(self, mxid: UserID, gid: Optional[str] = None,
                 refresh_token: Optional[str] = None, notice_room: Optional[RoomID] = None,
                 db_instance: Optional[DBUser] = None) -> None:
        self.mxid = mxid
        self.gid = gid
        self.refresh_token = refresh_token
        self.notice_room = notice_room
        self._notice_room_lock = asyncio.Lock()
        self.by_mxid[mxid] = self
        self.command_status = None
        self.is_whitelisted, self.is_admin, self.level = config.get_permissions(mxid)
        self._db_instance = db_instance
        self._community_id = None
        self.client = None
        self.name = None
        self.name_future = asyncio.Future()
        self.connected = False
        self.chats = None
        self.chats_future = asyncio.Future()
        self.users = None
        self._intentional_disconnect = False
        self.dm_update_lock = asyncio.Lock()

        self.log = self.log.getChild(self.mxid)

    # region Sessions

    def save(self) -> None:
        self.db_instance.edit(refresh_token=self.refresh_token, gid=self.gid,
                              notice_room=self.notice_room)

    @property
    def db_instance(self) -> DBUser:
        if not self._db_instance:
            self._db_instance = DBUser(mxid=self.mxid, gid=self.gid, notice_room=self.notice_room,
                                       refresh_token=self.refresh_token)
        return self._db_instance

    @classmethod
    def from_db(cls, db_user: DBUser) -> 'User':
        return User(mxid=db_user.mxid, refresh_token=db_user.refresh_token,
                    notice_room=db_user.notice_room, db_instance=db_user)

    @classmethod
    def get_all(cls) -> Iterator['User']:
        for db_user in DBUser.all():
            yield cls.from_db(db_user)

    @classmethod
    def get_by_mxid(cls, mxid: UserID, create: bool = True) -> Optional['User']:
        if pu.Puppet.get_id_from_mxid(mxid) is not None or mxid == cls.az.bot_mxid:
            return None
        try:
            return cls.by_mxid[mxid]
        except KeyError:
            pass

        db_user = DBUser.get_by_mxid(mxid)
        if db_user:
            return cls.from_db(db_user)

        if create:
            user = cls(mxid)
            user.db_instance.insert()
            return user

        return None

    # endregion

    async def get_notice_room(self) -> RoomID:
        if not self.notice_room:
            async with self._notice_room_lock:
                # If someone already created the room while this call was waiting,
                # don't make a new room
                if self.notice_room:
                    return self.notice_room
                self.notice_room = await self.az.intent.create_room(
                    is_direct=True, invitees=[self.mxid],
                    topic="Hangouts bridge notices")
                self.save()
        return self.notice_room

    async def send_bridge_notice(self, text: str) -> None:
        try:
            await self.az.intent.send_notice(await self.get_notice_room(), text)
        except Exception:
            self.log.warning("Failed to send bridge notice '%s'", text, exc_info=True)

    async def is_logged_in(self) -> bool:
        return self.client and self.connected

    @classmethod
    async def init_all(cls) -> None:
        users = [user for user in cls.get_all() if user.refresh_token]

        with futures.ThreadPoolExecutor() as pool:
            auth_resps: List[TryAuthResp] = await asyncio.gather(
                *[cls.loop.run_in_executor(pool, try_auth, user.refresh_token)
                  for user in users],
                loop=cls.loop)
        finish = []
        for user, auth_resp in zip(users, auth_resps):
            if auth_resp.success:
                finish.append(user.login_complete(auth_resp.cookies))
            else:
                await user.send_bridge_notice("Failed to resume session with stored "
                                              f"refresh token: {auth_resp.error}")
                user.log.exception("Failed to resume session with stored refresh token",
                                   exc_info=auth_resp.error)
        await asyncio.gather(*finish, loop=cls.loop)

    async def login_complete(self, cookies: dict) -> None:
        self.client = Client(cookies, max_retries=30, retry_backoff_base=1.5)
        await self._create_community()
        asyncio.ensure_future(self.start(), loop=self.loop)
        self.client.on_connect.add_observer(self.on_connect)
        self.client.on_reconnect.add_observer(self.on_reconnect)
        self.client.on_disconnect.add_observer(self.on_disconnect)

    async def start(self) -> None:
        try:
            self._intentional_disconnect = False
            await self.client.connect()
            if self._intentional_disconnect:
                self.log.info("Client connection finished")
            else:
                self.log.warning("Client connection finished unexpectedly")
                await self.send_bridge_notice("Client connection finished unexpectedly")
        except Exception as e:
            self.log.exception("Exception in connection")
            await self.send_bridge_notice(f"Exception in Hangouts connection: {e}")

    async def stop(self) -> None:
        if self.client:
            self._intentional_disconnect = True
            await self.client.disconnect()

    async def logout(self) -> None:
        await self.stop()
        self.client = None
        self.gid = None
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
        asyncio.ensure_future(self.on_connect_later(), loop=self.loop)
        await self.send_bridge_notice("Connected to Hangouts")

    async def on_connect_later(self) -> None:
        try:
            info = await self.client.get_self_info(hangouts.GetSelfInfoRequest(
                request_header=self.client.get_request_header()
            ))
        except Exception:
            self.log.exception("Failed to get_self_info")
            return
        self.gid = info.self_entity.id.gaia_id
        self.name = info.self_entity.properties.display_name
        self.name_future.set_result(self.name)
        self.save()

        try:
            puppet = pu.Puppet.get_by_gid(self.gid)
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

    async def on_disconnect(self) -> None:
        self.connected = False
        await self.send_bridge_notice("Disconnected from Hangouts")

    async def sync(self) -> None:
        users, chats = await hangups.build_user_conversation_list(self.client)
        await asyncio.gather(self.sync_users(users), self.sync_chats(chats), loop=self.loop)

    async def sync_users(self, users: UserList) -> None:
        self.users = users
        puppets: Dict[str, pu.Puppet] = {}
        update_avatars = config["bridge.update_avatar_initial_sync"]
        updates = []
        for info in users.get_all():
            if not info.id_.gaia_id:
                self.log.debug(f"Found user without gaia_id: {info}")
                continue
            puppet = pu.Puppet.get_by_gid(info.id_.gaia_id, create=True)
            puppets[puppet.gid] = puppet
            updates.append(puppet.update_info(self, info, update_avatar=update_avatars))
        self.log.debug(f"Syncing info of {len(updates)} puppets "
                       f"(avatars included: {update_avatars})...")
        await asyncio.gather(*updates, loop=self.loop)
        await self._sync_community_users(puppets)

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
            for portal in DBPortal.get_all_by_receiver(self.gid)
            if portal.mxid
        }

    async def sync_chats(self, chats: ConversationList) -> None:
        self.chats = chats
        self.chats_future.set_result(None)
        portals = {conv.id_: po.Portal.get_by_conversation(conv, self.gid)
                   for conv in chats.get_all()}
        await self._sync_community_rooms(portals)
        self.chats.on_watermark_notification.add_observer(self._ensure_future_proxy(self.on_receipt))
        self.chats.on_event.add_observer(self._ensure_future_proxy(self.on_event))
        self.chats.on_typing.add_observer(self._ensure_future_proxy(self.on_typing))
        self.log.debug("Fetching recent conversations to create portals for")
        res = await self.client.sync_recent_conversations(hangouts.SyncRecentConversationsRequest(
            request_header=self.client.get_request_header(),
            max_conversations=config["bridge.initial_chat_sync"],
            max_events_per_conversation=1,
            sync_filter=[hangouts.SYNC_FILTER_INBOX],
        ))
        self.log.debug("Server returned %d conversations", len(res.conversation_state))
        convs = sorted(res.conversation_state, reverse=True,
                       key=lambda state: state.conversation.self_conversation_state.sort_timestamp)
        for state in convs:
            self.log.debug("Syncing %s", state.conversation_id.id)
            chat = chats.get(state.conversation_id.id)
            portal = po.Portal.get_by_conversation(chat, self.gid)
            if portal.mxid:
                await portal.update_matrix_room(self, chat)
                if len(state.event) > 0 and not DBMessage.get_by_gid(state.event[0].event_id):
                    self.log.debug("Last message %s in chat %s not found in db, backfilling...",
                                   state.event[0].event_id, state.conversation_id.id)
                    await portal.backfill(self, is_initial=False)
            else:
                await portal.create_matrix_room(self, chat)
        await self.update_direct_chats()

    # region Hangouts event handling

    async def on_receipt(self, event: WatermarkNotification) -> None:
        if not self.chats:
            self.log.debug("Received receipt event before chat list, ignoring")
            return
        conv: Conversation = self.chats.get(event.conv_id)
        portal = po.Portal.get_by_conversation(conv, self.gid)
        if not portal:
            return
        message = DBMessage.get_most_recent(portal.mxid, event.read_timestamp)
        if not message:
            return
        puppet = pu.Puppet.get_by_gid(event.user_id.gaia_id)
        await puppet.intent_for(portal).mark_read(message.mx_room, message.mxid)

    async def on_event(self, event: ConversationEvent) -> None:
        if not self.chats:
            self.log.debug("Received message event before chat list, waiting for chat list")
            await self.chats_future
        conv: Conversation = self.chats.get(event.conversation_id)
        portal = po.Portal.get_by_conversation(conv, self.gid)
        if not portal:
            return

        sender = pu.Puppet.get_by_gid(event.user_id.gaia_id)

        if isinstance(event, ChatMessageEvent):
            await portal.backfill_lock.wait(event.id_)
            await portal.handle_hangouts_message(self, sender, event)
        elif isinstance(event, MembershipChangeEvent):
            self.log.info(f"{event.id_} by {event.user_id} in {event.conversation_id} "
                          f"({conv._conversation.type}): {event.participant_ids} {event.type_}'d")
        else:
            self.log.info(f"Unrecognized event {event}")

    async def on_typing(self, event: TypingStatusMessage):
        portal = po.Portal.get_by_gid(event.conv_id, self.gid)
        if not portal:
            return
        sender = pu.Puppet.get_by_gid(event.user_id.gaia_id, create=False)
        if not sender:
            return
        await portal.handle_hangouts_typing(self, sender, event.status)

    # endregion
    # region Hangouts API calls

    async def set_typing(self, conversation_id: str, typing: bool) -> None:
        self.log.debug(f"set_typing({conversation_id}, {typing})")
        await self.client.set_typing(hangouts.SetTypingRequest(
            request_header=self.client.get_request_header(),
            conversation_id=hangouts.ConversationId(id=conversation_id),
            type=hangouts.TYPING_TYPE_STARTED if typing else hangouts.TYPING_TYPE_STOPPED,
        ))

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

    async def send_emote(self, conversation_id: str, text: str) -> str:
        resp = await self.client.send_chat_message(hangouts.SendChatMessageRequest(
            request_header=self.client.get_request_header(),
            annotation=[hangouts.EventAnnotation(type=4)],
            event_request_header=await self._get_event_request_header(conversation_id),
            message_content=hangouts.MessageContent(
                segment=[hangups.ChatMessageSegment(text).serialize()],
            ),
        ))
        return resp.created_event.event_id

    async def send_text(self, conversation_id: str, text: str) -> str:
        resp = await self.client.send_chat_message(hangouts.SendChatMessageRequest(
            request_header=self.client.get_request_header(),
            event_request_header=await self._get_event_request_header(conversation_id),
            message_content=hangouts.MessageContent(
                segment=[hangups.ChatMessageSegment(text).serialize()],
            ),
        ))
        return resp.created_event.event_id

    async def send_image(self, conversation_id: str, id: str) -> str:
        resp = await self.client.send_chat_message(hangouts.SendChatMessageRequest(
            request_header=self.client.get_request_header(),
            event_request_header=await self._get_event_request_header(conversation_id),
            existing_media=hangouts.ExistingMedia(
                photo=hangouts.Photo(photo_id=id),
            ),
        ))
        return resp.created_event.event_id

    async def mark_read(self, conversation_id: str,
                        timestamp: Optional[Union[datetime.datetime, int]] = None) -> None:
        if isinstance(timestamp, datetime.datetime):
            timestamp = hangups.parsers.to_timestamp(timestamp)
        elif not timestamp:
            timestamp = int(time.time() * 1_000_000)
        await self.client.update_watermark(hangouts.UpdateWatermarkRequest(
            request_header=self.client.get_request_header(),
            conversation_id=hangouts.ConversationId(id=conversation_id),
            last_read_timestamp=timestamp,
        ))

    # endregion
    # region Community stuff

    async def _create_community(self) -> None:
        template = config["bridge.community_template"]
        if not template:
            return
        localpart, server = MxClient.parse_user_id(self.mxid)
        community_localpart = template.format(localpart=localpart.lower(), server=server.lower())
        self.log.debug(f"Creating personal filtering community {community_localpart}...")
        self._community_id, created = await self._community_helper.create(community_localpart)
        if created:
            await self._community_helper.update(self._community_id, name="Hangouts",
                                                avatar_url=config["appservice.bot_avatar"],
                                                short_desc="Your Hangouts bridged chats")
            await self._community_helper.invite(self._community_id, self.mxid)

    async def _sync_community_users(self, puppets: Dict[str, 'pu.Puppet']) -> None:
        if not self._community_id:
            return
        self.log.debug("Syncing personal filtering community users")
        old_db_contacts = {contact.contact: contact.in_community
                           for contact in self.db_instance.contacts}
        db_contacts = []
        for puppet in puppets.values():
            in_community = old_db_contacts.get(puppet.gid, None) or False
            if not in_community:
                await self._community_helper.join(self._community_id, puppet.default_mxid_intent)
                in_community = True
            db_contacts.append(Contact(user=self.gid, contact=puppet.gid,
                                       in_community=in_community))
        self.db_instance.contacts = db_contacts

    async def _sync_community_rooms(self, portals: Dict[str, 'po.Portal']) -> None:
        if not self._community_id:
            return
        self.log.debug("Syncing personal filtering community rooms")
        old_db_portals = {portal.portal: portal.in_community
                          for portal in self.db_instance.portals}
        db_portals = []
        for portal in portals.values():
            in_community = old_db_portals.get(portal.gid, None) or False
            if not in_community:
                await self._community_helper.add_room(self._community_id, portal.mxid)
                in_community = True
            db_portals.append(UserPortal(user=self.gid, portal=portal.gid,
                                         portal_receiver=portal.receiver,
                                         in_community=in_community))
        self.db_instance.portals = db_portals

    # endregion


class UserRefreshTokenCache(RefreshTokenCache):
    user: User

    def __init__(self, user: User) -> None:
        self.user = user

    def get(self) -> str:
        return self.user.refresh_token

    def set(self, refresh_token: str) -> None:
        self.user.log.trace("New refresh token: %s", refresh_token)
        self.user.refresh_token = refresh_token
        self.user.save()


def init(context: 'Context') -> Awaitable[None]:
    global config
    User.az, config, User.loop = context.core
    User.bridge = context.bridge
    User._community_helper = CommunityHelper(User.az)
    return User.init_all()
