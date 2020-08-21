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
from typing import Dict, Deque, Optional, Tuple, Union, Set, List, Iterator, Any, TYPE_CHECKING
from datetime import datetime
from collections import deque
import asyncio
import io
import cgi

from hangups import hangouts_pb2 as hangouts, ChatMessageEvent
from hangups.user import User as HangoutsUser, UserID as HangoutsUserID
from hangups.conversation import Conversation as HangoutsChat
from mautrix.types import (RoomID, MessageEventContent, EventID, MessageType, EventType, ImageInfo,
                           TextMessageEventContent, MediaMessageEventContent, Membership,
                           PowerLevelStateEventContent, EncryptedFile)
from mautrix.appservice import IntentAPI
from mautrix.bridge import BasePortal, NotificationDisabler
from mautrix.util.simple_lock import SimpleLock

from .config import Config
from .db import Portal as DBPortal, Message as DBMessage
from . import puppet as p, user as u

if TYPE_CHECKING:
    from .context import Context
    from .matrix import MatrixHandler

try:
    from mautrix.crypto.attachments import decrypt_attachment, encrypt_attachment
except ImportError:
    decrypt_attachment = encrypt_attachment = None

config: Config


class FakeLock:
    async def __aenter__(self) -> None:
        pass

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


StateBridge = EventType.find("m.bridge", EventType.Class.STATE)
StateHalfShotBridge = EventType.find("uk.half-shot.bridge", EventType.Class.STATE)


class Portal(BasePortal):
    invite_own_puppet_to_pm: bool = False
    by_mxid: Dict[RoomID, 'Portal'] = {}
    by_gid: Dict[Tuple[str, str], 'Portal'] = {}
    matrix: 'MatrixHandler'

    gid: str
    receiver: Optional[str]
    conv_type: int
    other_user_id: Optional[str]
    mxid: Optional[RoomID]
    encrypted: bool

    name: str

    _db_instance: DBPortal

    _main_intent: Optional[IntentAPI]
    _create_room_lock: asyncio.Lock
    _last_bridged_mxid: Optional[EventID]
    _dedup: Deque[Tuple[str, str]]
    _send_locks: Dict[str, asyncio.Lock]
    _noop_lock: FakeLock = FakeLock()
    _typing: Set['u.User']
    backfill_lock: SimpleLock

    def __init__(self, gid: str, receiver: str, conv_type: int, other_user_id: Optional[str] = None,
                 mxid: Optional[RoomID] = None, encrypted: bool = False, name: str = "",
                 db_instance: Optional[DBPortal] = None) -> None:
        self.gid = gid
        self.receiver = receiver
        if not receiver:
            raise ValueError("Receiver not given")
        self.conv_type = conv_type
        self.other_user_id = other_user_id
        self.mxid = mxid
        self.encrypted = encrypted

        self.name = name

        self._db_instance = db_instance

        self._main_intent = None
        self._create_room_lock = asyncio.Lock()
        self._last_bridged_mxid = None
        self._dedup = deque(maxlen=100)
        self._send_locks = {}
        self._typing = set()

        self.log = self.log.getChild(self.gid_log)
        self.backfill_lock = SimpleLock("Waiting for backfilling to finish before handling %s",
                                        log=self.log)

        self.by_gid[self.full_gid] = self
        if self.mxid:
            self.by_mxid[self.mxid] = self

    @property
    def full_gid(self) -> Tuple[str, str]:
        return self.gid, self.receiver

    @property
    def other_user_scoped_id(self) -> HangoutsUserID:
        # TODO is chat_id ever different from gaia_id?
        return HangoutsUserID(chat_id=self.other_user_id, gaia_id=self.other_user_id)

    @property
    def gid_log(self) -> str:
        if self.conv_type == hangouts.CONVERSATION_TYPE_ONE_TO_ONE:
            return f"{self.gid}-{self.receiver}"
        return self.gid

    # region DB conversion

    @property
    def db_instance(self) -> DBPortal:
        if not self._db_instance:
            self._db_instance = DBPortal(gid=self.gid, receiver=self.receiver,
                                         conv_type=self.conv_type, other_user_id=self.other_user_id,
                                         mxid=self.mxid, encrypted=self.encrypted, name=self.name)
        return self._db_instance

    @classmethod
    def from_db(cls, db_portal: DBPortal) -> 'Portal':
        return Portal(gid=db_portal.gid, receiver=db_portal.receiver, conv_type=db_portal.conv_type,
                      other_user_id=db_portal.other_user_id, mxid=db_portal.mxid,
                      encrypted=db_portal.encrypted, name=db_portal.name, db_instance=db_portal)

    async def save(self) -> None:
        self.db_instance.edit(other_user_id=self.other_user_id, mxid=self.mxid, name=self.name,
                              encrypted=self.encrypted)

    def delete(self) -> None:
        if self.mxid:
            DBMessage.delete_all_by_mxid(self.mxid)
        self.by_gid.pop(self.full_gid, None)
        self.by_mxid.pop(self.mxid, None)
        if self._db_instance:
            self._db_instance.delete()

    # endregion
    # region Properties

    @property
    def is_direct(self) -> bool:
        return self.conv_type == hangouts.CONVERSATION_TYPE_ONE_TO_ONE

    @property
    def main_intent(self) -> IntentAPI:
        if not self._main_intent:
            if self.is_direct:
                if not self.other_user_id:
                    raise ValueError("Portal.other_user_id not set for private chat")
                self._main_intent = p.Puppet.get_by_gid(self.other_user_id).default_mxid_intent
            else:
                self._main_intent = self.az.intent
        return self._main_intent

    # endregion
    # region Chat info updating

    async def update_info(self, source: Optional['u.User'] = None,
                          info: Optional[HangoutsChat] = None) -> HangoutsChat:
        if not info:
            info = source.chats.get(self.gid)
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
            other_user = info.get_user(self.other_user_scoped_id)
            name = p.Puppet._get_name_from_info(other_user)
        else:
            name = info.name
        if self.name != name:
            self.name = name
            if self.mxid and (self.encrypted or not self.is_direct):
                await self.main_intent.set_room_name(self.mxid, self.name)
            return True
        return False

    async def _update_participants(self, source: 'u.User', info: HangoutsChat) -> None:
        users = info.users
        if self.is_direct:
            users = [user for user in users if user.id_.gaia_id != source.gid]
            self.other_user_id = users[0].id_.gaia_id
        if not self.mxid:
            return
        puppets: Dict[HangoutsUser, p.Puppet] = {user: p.Puppet.get_by_gid(user.id_.gaia_id)
                                                 for user in users}
        await asyncio.gather(*[puppet.update_info(source=source, info=user)
                               for user, puppet in puppets.items()])
        await asyncio.gather(*[puppet.intent_for(self).ensure_joined(self.mxid)
                               for puppet in puppets.values()])

    # endregion

    async def _load_messages(self, source: 'u.User', limit: int = 100,
                             token: Optional[hangouts.EventContinuationToken] = None
                             ) -> Tuple[List[ChatMessageEvent], hangouts.EventContinuationToken]:
        resp = await source.client.get_conversation(hangouts.GetConversationRequest(
            request_header=source.client.get_request_header(),
            conversation_spec=hangouts.ConversationSpec(
                conversation_id=hangouts.ConversationId(id=self.gid),
            ),
            include_conversation_metadata=False,
            include_event=True,
            max_events_per_conversation=limit,
            event_continuation_token=token
        ))
        return ([HangoutsChat._wrap_event(evt) for evt in resp.conversation_state.event],
                resp.conversation_state.event_continuation_token)

    async def _load_many_messages(self, source: 'u.User', is_initial: bool
                                  ) -> List[ChatMessageEvent]:
        limit = (config["bridge.backfill.initial_limit"] if is_initial
                 else config["bridge.backfill.missed_limit"])
        if limit <= 0:
            return []
        messages = []
        self.log.debug("Fetching up to %d messages through %s", limit, source.gid)
        token = None
        while limit > 0:
            chunk_limit = min(limit, 100)
            chunk, token = await self._load_messages(source, chunk_limit, token)
            for message in reversed(chunk):
                if DBMessage.get_by_gid(message.id_):
                    self.log.debug("Stopping backfilling at %s (ts: %s) "
                                   "as message was already bridged",
                                   message.id_, message.timestamp)
                    break
                messages.append(message)
            if len(chunk) < chunk_limit:
                break
            limit -= len(chunk)
        return messages

    async def backfill(self, source: 'u.User', is_initial: bool = False) -> None:
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
        if config["bridge.backfill.invite_own_puppet"]:
            self.log.debug("Adding %s's default puppet to room for backfilling", source.mxid)
            sender = p.Puppet.get_by_gid(source.gid)
            await self.main_intent.invite_user(self.mxid, sender.default_mxid)
            await sender.default_mxid_intent.join_room_by_id(self.mxid)
            backfill_leave.add(sender.default_mxid_intent)
        async with NotificationDisabler(self.mxid, source):
            for message in reversed(messages):
                if isinstance(message, ChatMessageEvent):
                    puppet = p.Puppet.get_by_gid(message.user_id.gaia_id)
                    await self.handle_hangouts_message(source, puppet, message)
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
        return f"net.maunium.hangouts://hangouts/{self.gid}"

    @property
    def bridge_info(self) -> Dict[str, Any]:
        return {
            "bridgebot": self.az.bot_mxid,
            "creator": self.main_intent.mxid,
            "protocol": {
                "id": "hangouts",
                "displayname": "Hangouts",
                "avatar_url": config["appservice.bot_avatar"],
            },
            "channel": {
                "id": self.gid,
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
        invites = [source.mxid]
        if self.is_direct:
            users = [user for user in info.users if user.id_.gaia_id != source.gid]
            self.other_user_id = users[0].id_.gaia_id
            puppet = p.Puppet.get_by_gid(self.other_user_id)
            await puppet.update_info(source=source, info=info.get_user(self.other_user_scoped_id))
            power_levels.users[source.mxid] = 50
        power_levels.users[self.main_intent.mxid] = 100
        initial_state = [{
            "type": EventType.ROOM_POWER_LEVELS.serialize(),
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
        if config["appservice.community_id"]:
            initial_state.append({
                "type": "m.room.related_groups",
                "content": {"groups": [config["appservice.community_id"]]},
            })
        if config["bridge.encryption.default"] and self.matrix.e2ee:
            self.encrypted = True
            initial_state.append({
                "type": "m.room.encryption",
                "content": {"algorithm": "m.megolm.v1.aes-sha2"},
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
            if puppet:
                did_join = await puppet.intent.ensure_joined(self.mxid)
                if did_join and self.conv_type == hangouts.CONVERSATION_TYPE_ONE_TO_ONE:
                    await source.update_direct_chats({self.main_intent.mxid: [self.mxid]})
            await source._community_helper.add_room(source._community_id, self.mxid)

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
        if event_id and config["bridge.delivery_receipts"]:
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
        # TODO this probably isn't nice for bridging images, it really only needs to lock the
        #      actual message send call and dedup queue append.
        async with self.require_send_lock(sender.gid):
            if message.msgtype == MessageType.TEXT or message.msgtype == MessageType.NOTICE:
                gid = await self._handle_matrix_text(sender, message)
            elif message.msgtype == MessageType.EMOTE:
                gid = await self._handle_matrix_emote(sender, message)
            elif message.msgtype == MessageType.IMAGE:
                gid = await self._handle_matrix_image(sender, message)
            # elif message.msgtype == MessageType.LOCATION:
            #     gid = await self._handle_matrix_location(sender, message)
            else:
                self.log.warning(f"Unsupported msgtype in {message}")
                return
            if not gid:
                return
            self._dedup.appendleft(gid)
            # TODO pass through actual timestamp instead of using datetime.now()
            DBMessage(mxid=event_id, mx_room=self.mxid, gid=gid, receiver=self.receiver,
                      index=0, date=datetime.utcnow()).insert()
            self._last_bridged_mxid = event_id
        await self._send_delivery_receipt(event_id)

    async def _handle_matrix_text(self, sender: 'u.User', message: TextMessageEventContent) -> str:
        return await sender.send_text(self.gid, message.body)

    async def _handle_matrix_emote(self, sender: 'u.User', message: TextMessageEventContent
                                   ) -> str:
        return await sender.send_emote(self.gid, message.body)

    async def _handle_matrix_image(self, sender: 'u.User',
                                   message: MediaMessageEventContent) -> Optional[str]:
        if message.file and decrypt_attachment:
            data = await self.main_intent.download_media(message.file.url)
            data = decrypt_attachment(data, message.file.key.key,
                                      message.file.hashes.get("sha256"), message.file.iv)
        elif message.url:
            data = await self.main_intent.download_media(message.url)
        else:
            return None
        image = await sender.client.upload_image(io.BytesIO(data), filename=message.body)
        return await sender.send_image(self.gid, image)

    #
    # async def _handle_matrix_location(self, sender: 'u.User',
    #                                   message: LocationMessageEventContent) -> str:
    #     pass

    async def handle_matrix_leave(self, user: 'u.User') -> None:
        if self.is_direct:
            self.log.info(f"{user.mxid} left private chat portal with {self.gid},"
                          " cleaning up and deleting...")
            await self.cleanup_and_delete()
        else:
            self.log.debug(f"{user.mxid} left portal to {self.gid}")

    async def handle_matrix_typing(self, users: Set['u.User']) -> None:
        stopped_typing = [user.set_typing(self.gid, False)
                          for user in self._typing - users]
        started_typing = [user.set_typing(self.gid, True)
                          for user in users - self._typing]
        self._typing = users
        await asyncio.gather(*stopped_typing, *started_typing, loop=self.loop)

    # endregion
    # region Hangouts event handling

    async def _send_message(self, intent: IntentAPI, content: MessageEventContent,
                            event_type: EventType = EventType.ROOM_MESSAGE, **kwargs) -> EventID:
        if self.encrypted and self.matrix.e2ee:
            if intent.api.is_real_user:
                content[intent.api.real_user_content_key] = True
            event_type, content = await self.matrix.e2ee.encrypt(self.mxid, event_type, content)
        return await intent.send_message_event(self.mxid, event_type, content, **kwargs)

    async def _bridge_own_message_pm(self, source: 'u.User', sender: 'p.Puppet', msg_id: str,
                                     invite: bool = True) -> bool:
        if self.is_direct and sender.gid == source.gid and not sender.is_real_user:
            if self.invite_own_puppet_to_pm and invite:
                await self.main_intent.invite_user(self.mxid, sender.mxid)
            elif self.az.state_store.get_membership(self.mxid, sender.mxid) != Membership.JOIN:
                self.log.warning(f"Ignoring own {msg_id} in private chat "
                                 "because own puppet is not in room.")
                return False
        return True

    async def handle_hangouts_message(self, source: 'u.User', sender: 'p.Puppet',
                                      event: ChatMessageEvent) -> None:
        async with self.optional_send_lock(sender.gid):
            if event.id_ in self._dedup:
                return
            self._dedup.appendleft(event.id_)
        if not self.mxid:
            mxid = await self.create_matrix_room(source)
            if not mxid:
                # Failed to create
                return
        if not await self._bridge_own_message_pm(source, sender, f"message {event.id_}"):
            return
        intent = sender.intent_for(self)
        self.log.debug("Handling hangouts message %s", event.id_)

        event_id = None
        if event.attachments:
            self.log.debug("Processing attachments.")
            self.log.trace("Attachments: %s", event.attachments)
            event_id = await self.process_hangouts_attachments(event, intent)
        # Just to fallback to text if something else hasn't worked.
        if not event_id:
            content = TextMessageEventContent(msgtype=MessageType.TEXT, body=event.text)
            event_id = await self._send_message(intent, content, timestamp=event.timestamp)
        DBMessage(mxid=event_id, mx_room=self.mxid, gid=event.id_, receiver=self.receiver,
                  index=0, date=event.timestamp).insert()
        self.log.debug("Handled Hangouts message %s -> %s", event.id_, event_id)
        await self._send_delivery_receipt(event_id)

    async def _get_remote_bytes(self, url):
        async with self.az.http_session.request("GET", url) as resp:
            return await resp.read()

    async def process_hangouts_attachments(self, event: ChatMessageEvent, intent: IntentAPI
                                           ) -> Optional[EventID]:
        attachments_pb = event._event.chat_message.message_content.attachment

        if len(event.attachments) > 1:
            self.log.warning("Can't handle more that one attachment")
            return None

        attachment = event.attachments[0]
        attachment_pb = attachments_pb[0]

        embed_item = attachment_pb.embed_item

        # Get the filename from the headers
        async with self.az.http_session.request("GET", attachment) as resp:
            value, params = cgi.parse_header(resp.headers["Content-Disposition"])
            mime = resp.headers["Content-Type"]
            filename = params.get('filename', attachment.split("/")[-1])

        # TODO: This also catches movies, but I can't work out how they present
        #       differently to images
        if embed_item.type[0] == hangouts.ITEM_TYPE_PLUS_PHOTO:
            data = await self._get_remote_bytes(attachment)
            upload_mime = mime
            decryption_info = None
            if self.encrypted and encrypt_attachment:
                data, decryption_info = encrypt_attachment(data)
                upload_mime = "application/octet-stream"
            mxc_url = await intent.upload_media(data, mime_type=upload_mime, filename=filename)
            if decryption_info:
                decryption_info.url = mxc_url
            content = MediaMessageEventContent(url=mxc_url, file=decryption_info, body=filename,
                                               info=ImageInfo(size=len(data), mimetype=mime),
                                               msgtype=MessageType.IMAGE)
            return await self._send_message(intent, content, timestamp=event.timestamp)
        return None

    async def handle_hangouts_typing(self, source: 'u.User', sender: 'p.Puppet', status: int
                                     ) -> None:
        if not self.mxid:
            return
        if ((self.is_direct and sender.gid == source.gid
             and self.az.state_store.get_membership(self.mxid, sender.mxid) != Membership.JOIN)):
            return
        await sender.intent_for(self).set_typing(self.mxid, status == hangouts.TYPING_TYPE_STARTED,
                                                 timeout=6000)

    # endregion
    # region Getters

    @classmethod
    def get_by_mxid(cls, mxid: RoomID) -> Optional['Portal']:
        try:
            return cls.by_mxid[mxid]
        except KeyError:
            pass

        db_portal = DBPortal.get_by_mxid(mxid)
        if db_portal:
            return cls.from_db(db_portal)

        return None

    @classmethod
    def get_by_gid(cls, gid: str, receiver: Optional[str] = None, conv_type: Optional[int] = None,
                   ) -> Optional['Portal']:
        if not receiver or (conv_type and conv_type != hangouts.CONVERSATION_TYPE_ONE_TO_ONE):
            receiver = gid
        try:
            return cls.by_gid[(gid, receiver)]
        except KeyError:
            pass

        db_portal = DBPortal.get_by_gid(gid, receiver)
        if db_portal:
            if not db_portal.receiver:
                cls.log.warning(f"Found DBPortal {gid} without receiver, setting to {receiver}")
                db_portal.edit(receiver=receiver)
            return cls.from_db(db_portal)

        if conv_type is not None:
            portal = cls(gid=gid, receiver=receiver, conv_type=conv_type)
            portal.db_instance.insert()
            return portal

        return None

    @classmethod
    def get_all_by_receiver(cls, receiver: str) -> Iterator['Portal']:
        for db_portal in DBPortal.get_all_by_receiver(receiver):
            try:
                yield cls.by_gid[(db_portal.gid, db_portal.receiver)]
            except KeyError:
                yield cls.from_db(db_portal)

    @classmethod
    def all(cls) -> Iterator['Portal']:
        for db_portal in DBPortal.all():
            try:
                yield cls.by_gid[(db_portal.gid, db_portal.receiver)]
            except KeyError:
                yield cls.from_db(db_portal)

    @classmethod
    def get_by_conversation(cls, conversation: HangoutsChat, receiver: str) -> Optional['Portal']:
        return cls.get_by_gid(conversation.id_, receiver, conversation._conversation.type)

    # endregion


def init(context: 'Context') -> None:
    global config
    Portal.az, config, Portal.loop = context.core
    Portal.matrix = context.mx
    Portal.invite_own_puppet_to_pm = config["bridge.invite_own_puppet_to_pm"]
    NotificationDisabler.puppet_cls = p.Puppet
    NotificationDisabler.config_enabled = config["bridge.backfill.disable_notifications"]
