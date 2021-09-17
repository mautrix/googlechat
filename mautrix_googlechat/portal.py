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
from typing import (Dict, Deque, Optional, Tuple, Union, Set, List, Any, AsyncIterable,
                    Awaitable, cast, TYPE_CHECKING)
from collections import deque
import asyncio
import random
import time
import cgi
import io

from hangups import hangouts_pb2 as hangouts, googlechat_pb2 as googlechat, ChatMessageEvent
from hangups.user import User as HangoutsUser
from hangups.conversation import Conversation as HangoutsChat
from mautrix.types import (RoomID, MessageEventContent, EventID, MessageType, EventType, ImageInfo,
                           TextMessageEventContent, MediaMessageEventContent, Membership, UserID,
                           PowerLevelStateEventContent, ContentURI, EncryptionAlgorithm)
from mautrix.appservice import IntentAPI
from mautrix.bridge import BasePortal, NotificationDisabler, async_getter_lock
from mautrix.util.simple_lock import SimpleLock
from mautrix.errors import MatrixError

from .config import Config
from .db import Portal as DBPortal, Message as DBMessage
from . import puppet as p, user as u

if TYPE_CHECKING:
    from .__main__ import GoogleChatBridge
    from .matrix import MatrixHandler

try:
    from mautrix.crypto.attachments import decrypt_attachment, encrypt_attachment
except ImportError:
    decrypt_attachment = encrypt_attachment = None


class FakeLock:
    async def __aenter__(self) -> None:
        pass

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


StateBridge = EventType.find("m.bridge", EventType.Class.STATE)
StateHalfShotBridge = EventType.find("uk.half-shot.bridge", EventType.Class.STATE)


class Portal(DBPortal, BasePortal):
    invite_own_puppet_to_pm: bool = False
    by_mxid: Dict[RoomID, 'Portal'] = {}
    by_gcid: Dict[Tuple[str, str], 'Portal'] = {}
    matrix: 'MatrixHandler'
    config: Config

    _main_intent: Optional[IntentAPI]
    _create_room_lock: asyncio.Lock
    _last_bridged_mxid: Optional[EventID]
    _dedup: Deque[str]
    _local_dedup: Set[str]
    _send_locks: Dict[str, asyncio.Lock]
    _noop_lock: FakeLock = FakeLock()
    _typing: Set[UserID]
    backfill_lock: SimpleLock

    def __init__(self, gcid: str, gc_receiver: str, other_user_id: Optional[str] = None,
                 mxid: Optional[RoomID] = None, name: Optional[str] = None,
                 avatar_mxc: Optional[ContentURI] = None, name_set: bool = False,
                 avatar_set: bool = False, encrypted: bool = False) -> None:
        super().__init__(gcid=gcid, gc_receiver=gc_receiver, other_user_id=other_user_id,
                         mxid=mxid, name=name, avatar_mxc=avatar_mxc, name_set=name_set,
                         avatar_set=avatar_set, encrypted=encrypted)
        self.log = self.log.getChild(self.gcid_log)

        self._main_intent = None
        self._create_room_lock = asyncio.Lock()
        self._last_bridged_mxid = None
        self._dedup = deque(maxlen=100)
        self._local_dedup = set()
        self._send_locks = {}
        self._typing = set()

        self.backfill_lock = SimpleLock("Waiting for backfilling to finish before handling %s",
                                        log=self.log)

        self.by_gcid[self.gcid_full] = self
        if self.mxid:
            self.by_mxid[self.mxid] = self

    @classmethod
    def init_cls(cls, bridge: 'GoogleChatBridge') -> None:
        BasePortal.bridge = bridge
        cls.az = bridge.az
        cls.config = bridge.config
        cls.loop = bridge.loop
        cls.matrix = bridge.matrix
        cls.invite_own_puppet_to_pm = cls.config["bridge.invite_own_puppet_to_pm"]
        NotificationDisabler.puppet_cls = p.Puppet
        NotificationDisabler.config_enabled = cls.config["bridge.backfill.disable_notifications"]

    @property
    def gcid_full(self) -> Tuple[str, str]:
        return self.gcid, self.gc_receiver

    @property
    def gcid_log(self) -> str:
        if self.is_direct:
            return f"{self.gcid}-{self.gc_receiver}"
        return self.gcid

    # region DB conversion

    async def delete(self) -> None:
        if self.mxid:
            await DBMessage.delete_all_by_room(self.mxid)
        self.by_gcid.pop(self.gcid_full, None)
        self.by_mxid.pop(self.mxid, None)
        await super().delete()

    # endregion
    # region Properties

    @property
    def is_direct(self) -> bool:
        return self.gcid.startswith("dm:")

    @property
    def main_intent(self) -> IntentAPI:
        if not self._main_intent:
            raise ValueError("Portal must be postinit()ed before main_intent can be used")
        return self._main_intent

    # endregion
    # region Chat info updating

    async def update_info(self, source: Optional['u.User'] = None,
                          info: Optional[HangoutsChat] = None) -> HangoutsChat:
        if not info:
            info = source.chats.get(self.gcid)
            # info = await source.client.get_conversation(hangouts.GetConversationRequest(
            #     request_header=source.client.get_request_header(),
            #     conversation_spec=hangouts.ConversationSpec(
            #         conversation_id=hangouts.ConversationId(id=self.gid),
            #     ),
            #     include_event=False,
            # ))
        changed = await self._update_participants(source, info)
        changed = await self._update_name(info) or changed
        if changed:
            await self.save()
            await self.update_bridge_info()
        return info

    async def _update_name(self, info: HangoutsChat) -> bool:
        if self.is_direct:
            other_user = info.get_user(self.other_user_id)
            name = p.Puppet.get_name_from_info(other_user)
        else:
            name = info.name
        if self.name != name:
            self.name = name
            if self.mxid and (self.encrypted or not self.is_direct):
                await self.main_intent.set_room_name(self.mxid, self.name)
            return True
        return False

    def _get_invite_content(self, double_puppet: Optional['p.Puppet']) -> Dict[str, Any]:
        invite_content = {}
        if double_puppet:
            invite_content["fi.mau.will_auto_accept"] = True
        if self.is_direct:
            invite_content["is_direct"] = True
        return invite_content

    async def _update_participants(self, source: 'u.User', info: HangoutsChat) -> None:
        users = info.users
        if self.is_direct:
            users = [user for user in users if user.id_ != source.gcid]
            if not self.other_user_id:
                self.other_user_id = users[0].id_
                self._main_intent = (await p.Puppet.get_by_gcid(self.other_user_id)
                                     ).default_mxid_intent
                await self.save()
        if not self.mxid:
            return
        puppets: Dict[HangoutsUser, p.Puppet] = {user: await p.Puppet.get_by_gcid(user.id_)
                                                 for user in users}
        await asyncio.gather(*[puppet.update_info(source=source, info=user)
                               for user, puppet in puppets.items()])
        await asyncio.gather(*[puppet.intent_for(self).ensure_joined(self.mxid)
                               for puppet in puppets.values()])

    # endregion

    async def _load_messages(self, source: 'u.User', limit: int = 100,
                             token: Optional[hangouts.EventContinuationToken] = None
                             ) -> Tuple[List[ChatMessageEvent], hangouts.EventContinuationToken]:
        # resp = await source.client.get_conversation(hangouts.GetConversationRequest(
        #     request_header=source.client.get_request_header(),
        #     conversation_spec=hangouts.ConversationSpec(
        #         conversation_id=hangouts.ConversationId(id=self.gid),
        #     ),
        #     include_conversation_metadata=False,
        #     include_event=True,
        #     max_events_per_conversation=limit,
        #     event_continuation_token=token
        # ))
        # return ([HangoutsChat._wrap_event(evt) for evt in resp.conversation_state.event],
        #         resp.conversation_state.event_continuation_token)
        return [], None

    async def _load_many_messages(self, source: 'u.User', is_initial: bool
                                  ) -> List[ChatMessageEvent]:
        limit = (self.config["bridge.backfill.initial_limit"] if is_initial
                 else self.config["bridge.backfill.missed_limit"])
        if limit <= 0:
            return []
        messages = []
        self.log.debug("Fetching up to %d messages through %s", limit, source.gcid)
        token = None
        while limit > 0:
            chunk_limit = min(limit, 100)
            chunk, token = await self._load_messages(source, chunk_limit, token)
            for message in reversed(chunk):
                if await DBMessage.get_by_gcid(message.msg_id, self.gc_receiver):
                    self.log.debug("Stopping backfilling at %s (ts: %s) "
                                   "as message was already bridged",
                                   message.msg_id, message.timestamp)
                    break
                messages.append(message)
            if len(chunk) < chunk_limit:
                break
            limit -= len(chunk)
        return messages

    async def backfill(self, source: 'u.User', is_initial: bool = False) -> None:
        if not TYPE_CHECKING:
            self.log.debug("Backfill is not yet implemented")
            return
        try:
            with self.backfill_lock:
                await self._backfill(source, is_initial)
        except Exception:
            self.log.exception("Failed to backfill portal")

    async def _backfill(self, source: 'u.User', is_initial: bool = False) -> None:
        self.log.debug("Backfilling history through %s", source.mxid)
        messages = await self._load_many_messages(source, is_initial)
        if not messages:
            self.log.debug("Didn't get any messages from server")
            return
        self.log.debug("Got %d messages from server", len(messages))
        backfill_leave = set()
        if self.config["bridge.backfill.invite_own_puppet"]:
            self.log.debug("Adding %s's default puppet to room for backfilling", source.mxid)
            sender = await p.Puppet.get_by_gcid(source.gcid)
            await self.main_intent.invite_user(self.mxid, sender.default_mxid)
            await sender.default_mxid_intent.join_room_by_id(self.mxid)
            backfill_leave.add(sender.default_mxid_intent)
        async with NotificationDisabler(self.mxid, source):
            for message in reversed(messages):
                if isinstance(message, ChatMessageEvent):
                    puppet = await p.Puppet.get_by_gcid(message.user_id)
                    await self.handle_googlechat_message(source, puppet, message)
                else:
                    self.log.trace("Unhandled event type %s while backfilling", type(message))
        for intent in backfill_leave:
            self.log.trace("Leaving room with %s post-backfill", intent.mxid)
            await intent.leave_room(self.mxid)
        self.log.info("Backfilled %d messages through %s", len(messages), source.mxid)

    # region Matrix room creation

    async def _update_matrix_room(self, source: 'u.User',
                                  info: Optional[HangoutsChat] = None) -> None:
        await self.main_intent.invite_user(self.mxid, source.mxid, check_cache=True)
        puppet = await p.Puppet.get_by_custom_mxid(source.mxid)
        if puppet:
            await puppet.intent.ensure_joined(self.mxid)
        await self.update_info(source, info)

    async def update_matrix_room(self, source: 'u.User', info: Optional[HangoutsChat] = None
                                 ) -> None:
        try:
            await self._update_matrix_room(source, info)
        except Exception:
            self.log.exception("Failed to update portal")

    async def create_matrix_room(self, source: 'u.User', info: Optional[HangoutsChat] = None
                                 ) -> RoomID:
        if self.mxid:
            try:
                await self._update_matrix_room(source, info)
            except Exception:
                self.log.exception("Failed to update portal")
            return self.mxid
        async with self._create_room_lock:
            try:
                return await self._create_matrix_room(source, info)
            except Exception:
                self.log.exception("Failed to create portal")

    @property
    def bridge_info_state_key(self) -> str:
        return f"net.maunium.googlechat://googlechat/{self.gcid}"

    @property
    def bridge_info(self) -> Dict[str, Any]:
        return {
            "bridgebot": self.az.bot_mxid,
            "creator": self.main_intent.mxid,
            "protocol": {
                "id": "googlechat",
                "displayname": "Google Chat",
                "avatar_url": self.config["appservice.bot_avatar"],
            },
            "channel": {
                "id": self.gcid,
                "displayname": self.name,
            }
        }

    async def update_bridge_info(self) -> None:
        if not self.mxid:
            self.log.debug("Not updating bridge info: no Matrix room created")
            return
        try:
            self.log.debug("Updating bridge info...")
            await self.main_intent.send_state_event(self.mxid, StateBridge,
                                                    self.bridge_info, self.bridge_info_state_key)
            # TODO remove this once https://github.com/matrix-org/matrix-doc/pull/2346 is in spec
            await self.main_intent.send_state_event(self.mxid, StateHalfShotBridge,
                                                    self.bridge_info, self.bridge_info_state_key)
        except Exception:
            self.log.warning("Failed to update bridge info", exc_info=True)

    async def _create_matrix_room(self, source: 'u.User', info: Optional[HangoutsChat] = None
                                  ) -> RoomID:
        if self.mxid:
            await self._update_matrix_room(source, info)
            return self.mxid

        info = await self.update_info(source=source, info=info)
        self.log.debug("Creating Matrix room")
        name: Optional[str] = None
        power_levels = PowerLevelStateEventContent()
        invites = []
        if self.is_direct:
            users = [user for user in info.users if user.id_ != source.gcid]
            if not self.other_user_id:
                self.other_user_id = users[0].id_
                self._main_intent = (await p.Puppet.get_by_gcid(self.other_user_id)
                                     ).default_mxid_intent
                await self.save()
            puppet = await p.Puppet.get_by_gcid(self.other_user_id)
            await puppet.update_info(source=source, info=info.get_user(self.other_user_id))
            power_levels.users[source.mxid] = 50
        power_levels.users[self.main_intent.mxid] = 100
        initial_state = [{
            "type": str(EventType.ROOM_POWER_LEVELS),
            "content": power_levels.serialize(),
        }, {
            "type": str(StateBridge),
            "state_key": self.bridge_info_state_key,
            "content": self.bridge_info,
        }, {
            # TODO remove this once https://github.com/matrix-org/matrix-doc/pull/2346 is in spec
            "type": str(StateHalfShotBridge),
            "state_key": self.bridge_info_state_key,
            "content": self.bridge_info,
        }]
        if self.config["bridge.encryption.default"] and self.matrix.e2ee:
            self.encrypted = True
            initial_state.append({
                "type": str(EventType.ROOM_ENCRYPTION),
                "content": {"algorithm": str(EncryptionAlgorithm.MEGOLM_V1)},
            })
            if self.is_direct:
                invites.append(self.az.bot_mxid)
        if self.encrypted or not self.is_direct:
            name = self.name
        # We lock backfill lock here so any messages that come between the room being created
        # and the initial backfill finishing wouldn't be bridged before the backfill messages.
        with self.backfill_lock:
            self.mxid = await self.main_intent.create_room(name=name, is_direct=self.is_direct,
                                                           invitees=invites,
                                                           initial_state=initial_state)
            if not self.mxid:
                raise Exception("Failed to create room: no mxid returned")
            if self.encrypted and self.matrix.e2ee and self.is_direct:
                try:
                    await self.az.intent.ensure_joined(self.mxid)
                except Exception:
                    self.log.warning(f"Failed to add bridge bot to new private chat {self.mxid}")
            await self.save()
            self.log.debug(f"Matrix room created: {self.mxid}")
            self.by_mxid[self.mxid] = self
            await self._update_participants(source, info)

            puppet = await p.Puppet.get_by_custom_mxid(source.mxid)
            await self.main_intent.invite_user(self.mxid, source.mxid,
                                               extra_content=self._get_invite_content(puppet))
            if puppet:
                try:
                    if self.is_direct:
                        await source.update_direct_chats({self.main_intent.mxid: [self.mxid]})
                    await puppet.intent.join_room_by_id(self.mxid)
                except MatrixError:
                    self.log.debug("Failed to join custom puppet into newly created portal",
                                   exc_info=True)

            await self.backfill(source, is_initial=True)

        return self.mxid

    # endregion
    # region Matrix event handling

    def require_send_lock(self, user_id: str) -> asyncio.Lock:
        try:
            lock = self._send_locks[user_id]
        except KeyError:
            lock = asyncio.Lock()
            self._send_locks[user_id] = lock
        return lock

    def optional_send_lock(self, user_id: str) -> Union[asyncio.Lock, FakeLock]:
        try:
            return self._send_locks[user_id]
        except KeyError:
            pass
        return self._noop_lock

    async def _send_delivery_receipt(self, event_id: EventID) -> None:
        if event_id and self.config["bridge.delivery_receipts"]:
            try:
                await self.az.intent.mark_read(self.mxid, event_id)
            except Exception:
                self.log.exception("Failed to send delivery receipt for %s", event_id)

    async def handle_matrix_message(self, sender: 'u.User', message: MessageEventContent,
                                    event_id: EventID) -> None:
        puppet = await p.Puppet.get_by_custom_mxid(sender.mxid)
        if puppet and message.get(self.az.real_user_content_key, False):
            self.log.debug(f"Ignoring puppet-sent message by confirmed puppet user {sender.mxid}")
            return
        reply_to = await DBMessage.get_by_mxid(message.get_reply_to(), self.mxid)
        thread_id = (reply_to.gc_parent_id or reply_to.gcid) if reply_to else None
        local_id = f"mautrix-googlechat%{random.randint(0, 0xffffffffffffffff)}"
        self._local_dedup.add(local_id)

        # TODO this probably isn't nice for bridging images, it really only needs to lock the
        #      actual message send call and dedup queue append.
        async with self.require_send_lock(sender.gcid):
            if message.msgtype == MessageType.TEXT or message.msgtype == MessageType.NOTICE:
                gcid = await self._handle_matrix_text(sender, message, thread_id, local_id)
            elif message.msgtype == MessageType.EMOTE:
                gcid = await self._handle_matrix_emote(sender, message, thread_id, local_id)
            elif message.msgtype == MessageType.IMAGE:
                gcid = await self._handle_matrix_image(sender, message, thread_id, local_id)
            # elif message.msgtype == MessageType.LOCATION:
            #     gid = await self._handle_matrix_location(sender, message, thread_id, local_id)
            else:
                self.log.warning(f"Unsupported msgtype in {message}")
                return
            if not gcid:
                return
            self._dedup.appendleft(gcid)
            self._local_dedup.remove(local_id)
            # TODO pass through actual timestamp instead of using time.time()
            ts = int(time.time() * 1000)
            await DBMessage(mxid=event_id, mx_room=self.mxid, gcid=gcid, gc_chat=self.gcid,
                            gc_receiver=self.gc_receiver, gc_parent_id=thread_id, index=0,
                            timestamp=ts).insert()
            self._last_bridged_mxid = event_id
            self.log.debug(f"Handled Matrix message {event_id} -> {local_id} -> {gcid}")
        await self._send_delivery_receipt(event_id)

    async def _handle_matrix_text(self, sender: 'u.User', message: TextMessageEventContent,
                                  thread_id: str, local_id: str) -> str:
        return await sender.send_text(self.gcid, message.body, thread_id=thread_id,
                                      local_id=local_id)

    async def _handle_matrix_emote(self, sender: 'u.User', message: TextMessageEventContent,
                                   thread_id: str, local_id: str) -> str:
        return await sender.send_emote(self.gcid, message.body, thread_id=thread_id,
                                       local_id=local_id)

    async def _handle_matrix_image(self, sender: 'u.User', message: MediaMessageEventContent,
                                   thread_id: str, local_id: str) -> Optional[str]:
        if message.file and decrypt_attachment:
            data = await self.main_intent.download_media(message.file.url)
            data = decrypt_attachment(data, message.file.key.key,
                                      message.file.hashes.get("sha256"), message.file.iv)
        elif message.url:
            data = await self.main_intent.download_media(message.url)
        else:
            return None
        image = await sender.client.upload_image(io.BytesIO(data), filename=message.body)
        return await sender.send_image(self.gcid, image, thread_id=thread_id, local_id=local_id)

    #
    # async def _handle_matrix_location(self, sender: 'u.User',
    #                                   message: LocationMessageEventContent) -> str:
    #     pass

    async def handle_matrix_leave(self, user: 'u.User') -> None:
        if self.is_direct:
            self.log.info(f"{user.mxid} left private chat portal with {self.gcid},"
                          " cleaning up and deleting...")
            await self.cleanup_and_delete()
        else:
            self.log.debug(f"{user.mxid} left portal to {self.gcid}")

    async def handle_matrix_typing(self, users: Set[UserID]) -> None:
        user_map = {mxid: await u.User.get_by_mxid(mxid, create=False) for mxid in users}
        stopped_typing = [user_map[mxid].set_typing(self.gcid, False)
                          for mxid in self._typing - users
                          if mxid in user_map]
        started_typing = [user_map[mxid].set_typing(self.gcid, True)
                          for mxid in users - self._typing
                          if mxid in user_map]
        self._typing = users
        await asyncio.gather(*stopped_typing, *started_typing)

    # endregion
    # region Hangouts event handling

    async def _bridge_own_message_pm(self, source: 'u.User', sender: 'p.Puppet', msg_id: str,
                                     invite: bool = True) -> bool:
        if self.is_direct and sender.gcid == source.gcid and not sender.is_real_user:
            if self.invite_own_puppet_to_pm and invite:
                await self.main_intent.invite_user(self.mxid, sender.mxid)
            elif (await self.az.state_store.get_membership(self.mxid, sender.mxid)
                  != Membership.JOIN):
                self.log.warning(f"Ignoring own {msg_id} in private chat "
                                 "because own puppet is not in room.")
                return False
        return True

    async def handle_googlechat_message(self, source: 'u.User', sender: 'p.Puppet',
                                        event: ChatMessageEvent) -> None:
        async with self.optional_send_lock(sender.gcid):
            if event.local_id in self._local_dedup:
                self.log.debug(f"Dropping message {event.msg_id} (found in local dedup set)")
                return
            elif event.msg_id in self._dedup:
                self.log.debug(f"Dropping message {event.msg_id} (found in dedup queue)")
                return
            self._dedup.appendleft(event.msg_id)
        if not self.mxid:
            mxid = await self.create_matrix_room(source)
            if not mxid:
                # Failed to create
                return
        if not await self._bridge_own_message_pm(source, sender, f"message {event.msg_id}"):
            return
        intent = sender.intent_for(self)
        self.log.debug("Handling Google Chat message %s", event.msg_id)

        event_ids = []
        if event.text:
            content = TextMessageEventContent(msgtype=MessageType.TEXT, body=event.text)
            if event.parent_msg_id:
                reply_to = await DBMessage.get_last_in_thread(event.parent_msg_id,
                                                              self.gc_receiver)
                if reply_to:
                    content.set_reply(reply_to.mxid)
            event_ids.append(await self._send_message(intent, content, timestamp=event.timestamp))
        if event.attachments:
            self.log.debug("Processing attachments.")
            self.log.trace("Attachments: %s", event.attachments)
            try:
                async for event_id in self.process_googlechat_attachments(source, event, intent):
                    event_ids.append(event_id)
            except Exception:
                self.log.exception("Failed to process attachments")
        if not event_ids:
            # TODO send notification
            self.log.debug("Unhandled Google Chat message %s", event.msg_id)
            return
        ts = int(event.timestamp.timestamp() * 1000)
        for index, event_id in enumerate(event_ids):
            await DBMessage(mxid=event_id, mx_room=self.mxid, gcid=event.msg_id, gc_chat=self.gcid,
                            gc_receiver=self.gc_receiver, gc_parent_id=event.parent_msg_id,
                            index=index, timestamp=ts).insert()
        self.log.debug("Handled Google Chat message %s -> %s", event.msg_id, event_ids)
        await self._send_delivery_receipt(event_ids[-1])

    async def process_googlechat_attachments(self, source: 'u.User', event: ChatMessageEvent,
                                             intent: IntentAPI) -> AsyncIterable[EventID]:
        for url in event.attachments:
            sess = source.client._session
            async with sess.fetch_raw_ctx("GET", url) as resp:
                value, params = cgi.parse_header(resp.headers["Content-Disposition"])
                mime = resp.headers["Content-Type"]
                filename = params.get("filename", url.split("/")[-1])
                if int(resp.headers["Content-Length"]) > self.matrix.media_config.upload_size:
                    # TODO send error message
                    self.log.warning("Can't upload too large attachment")
                    continue
                data = await resp.read()

            upload_mime = mime
            decryption_info = None
            if self.encrypted and encrypt_attachment:
                data, decryption_info = encrypt_attachment(data)
                upload_mime = "application/octet-stream"
            mxc_url = await intent.upload_media(data, mime_type=upload_mime, filename=filename)
            if decryption_info:
                decryption_info.url = mxc_url
                mxc_url = None
            content = MediaMessageEventContent(url=mxc_url, file=decryption_info, body=filename,
                                               info=ImageInfo(size=len(data), mimetype=mime))
            content.msgtype = getattr(MessageType, mime.split("/")[0].upper(), MessageType.FILE)
            yield await self._send_message(intent, content, timestamp=event.timestamp)

    async def handle_hangouts_typing(self, source: 'u.User', sender: 'p.Puppet', status: int
                                     ) -> None:
        if not self.mxid:
            return
        if self.is_direct and sender.gcid == source.gcid:
            membership = await self.az.state_store.get_membership(self.mxid, sender.mxid)
            if membership != Membership.JOIN:
                return
        await sender.intent_for(self).set_typing(self.mxid,
                                                 status == googlechat.TypingState.TYPING,
                                                 timeout=6000)

    # endregion
    # region Getters

    async def postinit(self) -> None:
        self.by_gcid[self.gcid_full] = self
        if self.mxid:
            self.by_mxid[self.mxid] = self
        if self.other_user_id or not self.is_direct:
            self._main_intent = (
                (await p.Puppet.get_by_gcid(self.other_user_id)).default_mxid_intent
                if self.is_direct else self.az.intent
            )

    @classmethod
    @async_getter_lock
    async def get_by_mxid(cls, mxid: RoomID) -> Optional['Portal']:
        try:
            return cls.by_mxid[mxid]
        except KeyError:
            pass

        portal = cast(cls, await super().get_by_mxid(mxid))
        if portal:
            await portal.postinit()
            return portal

        return None

    @classmethod
    @async_getter_lock
    async def get_by_gcid(cls, gcid: str, receiver: Optional[str] = None) -> Optional['Portal']:
        receiver = "" if gcid.startswith("space:") else receiver
        try:
            return cls.by_gcid[(gcid, receiver)]
        except KeyError:
            pass

        portal = cast(cls, await super().get_by_gcid(gcid, receiver))
        if portal:
            await portal.postinit()
            return portal

        portal = cls(gcid=gcid, gc_receiver=receiver)
        await portal.insert()
        await portal.postinit()
        return portal

    @classmethod
    async def get_all_by_receiver(cls, receiver: str) -> AsyncIterable['Portal']:
        portal: Portal
        for portal in await super().get_all_by_receiver(receiver):
            try:
                yield cls.by_gcid[(portal.gcid, portal.gc_receiver)]
            except KeyError:
                await portal.postinit()
                yield portal

    @classmethod
    async def all(cls) -> AsyncIterable['Portal']:
        portal: Portal
        for portal in await super().all():
            try:
                yield cls.by_gcid[(portal.gcid, portal.gc_receiver)]
            except KeyError:
                await portal.postinit()
                yield portal

    @classmethod
    def get_by_conversation(cls, conversation: HangoutsChat, receiver: str
                            ) -> Awaitable[Optional['Portal']]:
        return cls.get_by_gcid(conversation.id_, receiver)

    # endregion
