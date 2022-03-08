# mautrix-googlechat - A Matrix-Google Chat puppeting bridge
# Copyright (C) 2022 Tulir Asokan
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
from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncIterable, NamedTuple, Union, cast
from collections import deque
import asyncio
import mimetypes
import random
import time

from yarl import URL
import aiohttp

from maugclib import FileTooLargeError, googlechat_pb2 as googlechat
from mautrix.appservice import IntentAPI
from mautrix.bridge import BasePortal, NotificationDisabler, async_getter_lock
from mautrix.errors import IntentError, MatrixError, MForbidden
from mautrix.types import (
    ContentURI,
    EncryptionAlgorithm,
    EventID,
    EventType,
    ImageInfo,
    MediaMessageEventContent,
    Membership,
    MessageEventContent,
    MessageType,
    PowerLevelStateEventContent,
    RoomID,
    TextMessageEventContent,
    UserID,
)
from mautrix.util import magic, variation_selector
from mautrix.util.message_send_checkpoint import MessageSendCheckpointStatus
from mautrix.util.opt_prometheus import Histogram
from mautrix.util.simple_lock import SimpleLock
import maugclib.parsers

from . import formatter as fmt, matrix as m, puppet as p, user as u
from .config import Config
from .db import Message as DBMessage, Portal as DBPortal, Reaction as DBReaction

if TYPE_CHECKING:
    from .__main__ import GoogleChatBridge

try:
    from mautrix.crypto.attachments import async_inplace_encrypt_attachment, decrypt_attachment
except ImportError:
    decrypt_attachment = async_inplace_encrypt_attachment = None


class FakeLock:
    async def __aenter__(self) -> None:
        pass

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


StateBridge = EventType.find("m.bridge", EventType.Class.STATE)
StateHalfShotBridge = EventType.find("uk.half-shot.bridge", EventType.Class.STATE)

SendResponse = NamedTuple("SendResponse", gcid=str, timestamp=int)
ChatInfo = Union[googlechat.WorldItemLite, googlechat.GetGroupResponse]

METRIC_HANDLE_EVENT = Histogram("bridge_handle_event", "calls to handle_event", ["event_type"])


class AttachmentURL(NamedTuple):
    url: URL
    name: str | None
    mime: str | None


class Portal(DBPortal, BasePortal):
    invite_own_puppet_to_pm: bool = False
    by_mxid: dict[RoomID, Portal] = {}
    by_gcid: dict[tuple[str, str], Portal] = {}
    matrix: m.MatrixHandler
    config: Config

    _main_intent: IntentAPI | None
    _create_room_lock: asyncio.Lock
    _last_bridged_mxid: EventID | None
    _dedup: deque[str]
    _local_dedup: set[str]
    _send_locks: dict[str, asyncio.Lock]
    _edit_dedup: dict[str, int]
    _noop_lock: FakeLock = FakeLock()
    _typing: set[UserID]
    _incoming_events: asyncio.Queue[tuple[u.User, googlechat.Event]]
    _event_dispatcher_task: asyncio.Task | None
    backfill_lock: SimpleLock

    def __init__(
        self,
        gcid: str,
        gc_receiver: str,
        other_user_id: str | None = None,
        mxid: RoomID | None = None,
        name: str | None = None,
        avatar_mxc: ContentURI | None = None,
        name_set: bool = False,
        avatar_set: bool = False,
        encrypted: bool = False,
        revision: int | None = None,
        is_threaded: bool | None = None,
    ) -> None:
        super().__init__(
            gcid=gcid,
            gc_receiver=gc_receiver,
            other_user_id=other_user_id,
            mxid=mxid,
            name=name,
            avatar_mxc=avatar_mxc,
            name_set=name_set,
            avatar_set=avatar_set,
            encrypted=encrypted,
            revision=revision,
            is_threaded=is_threaded,
        )
        self.log = self.log.getChild(self.gcid_log)

        self._main_intent = None
        self._create_room_lock = asyncio.Lock()
        self._incoming_events = asyncio.Queue()
        self._event_dispatcher_task = None
        self._last_bridged_mxid = None
        self._dedup = deque(maxlen=100)
        self._edit_dedup = {}
        self._local_dedup = set()
        self._send_locks = {}
        self._typing = set()
        self.backfill_lock = SimpleLock(
            "Waiting for backfilling to finish before handling %s", log=self.log
        )

    @classmethod
    def init_cls(cls, bridge: "GoogleChatBridge") -> None:
        BasePortal.bridge = bridge
        cls.az = bridge.az
        cls.config = bridge.config
        cls.loop = bridge.loop
        cls.matrix = bridge.matrix
        cls.invite_own_puppet_to_pm = cls.config["bridge.invite_own_puppet_to_pm"]
        NotificationDisabler.puppet_cls = p.Puppet
        NotificationDisabler.config_enabled = cls.config["bridge.backfill.disable_notifications"]

    # region Properties

    @property
    def gcid_full(self) -> tuple[str, str]:
        return self.gcid, self.gc_receiver

    @property
    def gcid_plain(self) -> str:
        gc_type, gcid = self.gcid.split(":")
        return gcid

    @property
    def gcid_log(self) -> str:
        if self.is_direct:
            return f"{self.gcid}-{self.gc_receiver}"
        return self.gcid

    @property
    def gc_group_id(self) -> googlechat.GroupId:
        return maugclib.parsers.group_id_from_id(self.gcid)

    @property
    def is_direct(self) -> bool:
        return self.is_dm and bool(self.other_user_id)

    @property
    def is_dm(self) -> bool:
        return self.gcid.startswith("dm:")

    @property
    def main_intent(self) -> IntentAPI:
        if not self._main_intent:
            raise ValueError("Portal must be postinit()ed before main_intent can be used")
        return self._main_intent

    # endregion
    # region DB conversion

    async def delete(self) -> None:
        if self.mxid:
            await DBMessage.delete_all_by_room(self.mxid)
            await DBReaction.delete_all_by_room(self.mxid)
        self.by_mxid.pop(self.mxid, None)
        self.mxid = None
        self.name_set = False
        self.avatar_set = False
        await super().save()

    # endregion
    # region Chat info updating

    async def get_dm_puppet(self) -> p.Puppet | None:
        if not self.is_direct:
            return None
        return await p.Puppet.get_by_gcid(self.other_user_id)

    async def update_info(
        self, source: u.User | None = None, info: ChatInfo | None = None
    ) -> ChatInfo:
        if not info or (not self.is_dm and isinstance(info, googlechat.WorldItemLite)):
            info = await source.get_group(
                self.gcid, (info.group_revision.timestamp if info else self.revision)
            )

        changed = False
        is_threaded = (
            info if isinstance(info, googlechat.WorldItemLite) else info.group
        ).HasField("threaded_group")
        if is_threaded != self.is_threaded:
            self.is_threaded = is_threaded
            changed = True
        changed = await self._update_participants(source, info) or changed
        changed = await self._update_name(info) or changed
        if changed:
            await self.save()
            await self.update_bridge_info()
        return info

    async def _update_name(self, info: ChatInfo) -> bool:
        if self.is_direct:
            puppet = await self.get_dm_puppet()
            name = puppet.name
        elif isinstance(info, googlechat.WorldItemLite) and info.HasField("room_name"):
            name = info.room_name
        elif isinstance(info, googlechat.GetGroupResponse) and info.group.HasField("name"):
            name = info.group.name
        else:
            return False
        if self.name != name:
            self.name = name
            if self.mxid and (self.encrypted or not self.is_direct):
                await self.main_intent.set_room_name(self.mxid, self.name)
            return True
        return False

    def _get_invite_content(self, double_puppet: p.Puppet | None) -> dict[str, Any]:
        invite_content = {}
        if double_puppet:
            invite_content["fi.mau.will_auto_accept"] = True
        if self.is_direct:
            invite_content["is_direct"] = True
        return invite_content

    async def _update_participants(self, source: u.User, info: ChatInfo) -> None:
        bots = user_ids = []
        if self.is_dm and isinstance(info, googlechat.WorldItemLite):
            if len(info.read_state.joined_users) > 0:
                user_ids = [
                    user.id
                    for user in info.read_state.joined_users
                    if user.type == googlechat.HUMAN
                ]
                bots = [
                    user.id for user in info.read_state.joined_users if user.type == googlechat.BOT
                ]
            else:
                user_ids = [member.id for member in info.dm_members.members]
        elif isinstance(info, googlechat.GetGroupResponse):
            user_ids = [member.id.member_id.user_id.id for member in info.memberships]
        if not user_ids:
            raise ValueError("No participants found :(")
        if self.is_dm and len(user_ids) == 2:
            user_ids.remove(source.gcid)
        if self.is_dm and len(user_ids) == 1 and not self.other_user_id:
            self.other_user_id = user_ids[0]
            self._main_intent = (await self.get_dm_puppet()).default_mxid_intent
            await self.save()
        if not self.mxid and not self.is_direct:
            return
        users = await source.get_users(user_ids + bots)
        await asyncio.gather(*[self._update_participant(source, user) for user in users])

    async def _update_participant(self, source: u.User, user: googlechat.User) -> None:
        puppet = await p.Puppet.get_by_gcid(user.user_id.id)
        await puppet.update_info(source=source, info=user)
        if self.mxid:
            await puppet.intent_for(self).ensure_joined(self.mxid, bot=self.main_intent)

    # endregion
    # region Backfill

    async def backfill(
        self, source: u.User, latest_revision: int, is_initial: bool = False
    ) -> int:
        try:
            with self.backfill_lock:
                async with NotificationDisabler(self.mxid, source):
                    if is_initial:
                        total_handled = await self._initial_backfill(source)
                    else:
                        total_handled = await self._catchup_backfill(source, latest_revision)
                await self.set_revision(latest_revision)
            return total_handled
        except Exception:
            self.log.exception(f"Failed to backfill portal ({latest_revision=}, {is_initial=})")
            return 0

    async def _initial_backfill(self, source: u.User) -> int:
        self.log.debug(f"Fetching topics through {source.mxid} for initial backfill")
        req = googlechat.ListTopicsRequest(
            request_header=source.client.gc_request_header,
            page_size_for_topics=(
                self.config["bridge.backfill.initial_thread_limit"]
                if self.is_threaded
                else self.config["bridge.backfill.initial_nonthread_limit"]
            ),
            group_id=self.gc_group_id,
        )
        resp = await source.client.proto_list_topics(req)
        self.log.debug(
            f"Got {len(resp.topics)} topics from server "
            f"(up to revision {resp.group_revision.timestamp})"
        )
        if self.is_threaded:
            # Store the group revision already now, we can't continue from the middle anyway.
            await self.set_revision(resp.group_revision.timestamp)
        topic: googlechat.Topic
        message_count = 0
        # The reversed list is probably already sorted properly, but re-sort it just in case
        sorted_topics = sorted(reversed(resp.topics), key=lambda topic: topic.sort_time)
        for topic in sorted_topics:
            await self.handle_googlechat_message(source, topic.replies[0])
            message_count += 1
            if self.is_threaded:
                msg_req = googlechat.ListMessagesRequest(
                    request_header=source.client.gc_request_header,
                    parent_id=googlechat.MessageParentId(topic_id=topic.id),
                    page_size=self.config["bridge.backfill.initial_thread_reply_limit"],
                )
                msg_resp = await source.client.proto_list_messages(msg_req)
                self.log.debug(f"Fetched {len(msg_resp.messages)} replies to {topic.id.topic_id}")
                for msg in msg_resp.messages:
                    await self.handle_googlechat_message(source, msg)
                    message_count += 1
            else:
                await self.set_revision(topic.replies[0].create_time)
        self.log.info(f"Initial backfill complete, handled {message_count} messages in total")
        if not self.is_threaded:
            await self.set_revision(resp.group_revision.timestamp)
        return message_count

    async def _catchup_backfill(self, source: u.User, latest_revision: int) -> int:
        if not self.revision:
            self.log.debug("Can't do catch-up backfill on portal with no known last revision")
            return 0

        has_more_pages = True
        total_handled = 0
        while has_more_pages:
            self.log.debug(
                f"Making catchup request through {source.mxid} "
                f"from {self.revision} to {latest_revision}"
            )
            resp = await source.client.proto_catch_up_group(
                googlechat.CatchUpGroupRequest(
                    request_header=source.client.gc_request_header,
                    group_id=self.gc_group_id,
                    range=googlechat.CatchUpRange(
                        from_revision_timestamp=self.revision,
                        to_revision_timestamp=latest_revision,
                    ),
                    page_size=self.config["bridge.backfill.missed_event_page_size"],
                    cutoff_size=self.config["bridge.backfill.missed_event_limit"],
                )
            )
            status_name = googlechat.CatchUpResponse.ResponseStatus.Name(resp.status)
            if resp.status not in (
                googlechat.CatchUpResponse.PAGINATED,
                googlechat.CatchUpResponse.COMPLETED,
            ):
                self.log.warning(f"Failed to backfill: got {status_name} in response to catchup")
                return total_handled
            has_more_pages = resp.status == googlechat.CatchUpResponse.PAGINATED
            self.log.debug(
                f"Got {len(resp.events)} events from catchup request "
                f"(response status: {status_name})"
            )
            handled_count = await self._handle_backfill_events(source, resp.events)
            total_handled += handled_count
            self.log.debug(f"Handled {handled_count} events in catchup chunk")
        self.log.info(f"Catchup backfill complete, handled {total_handled} events in total")
        return total_handled

    async def _handle_backfill_events(self, source: u.User, events: list[googlechat.Event]) -> int:
        handled_count = 0
        for multi_evt in events:
            for evt in source.client.split_event_bodies(multi_evt):
                handled = await self.handle_event(source, evt)
                if not handled:
                    type_name = googlechat.Event.EventType.Name(evt.type)
                    self.log.debug(f"Unhandled event type {type_name} in backfill")
                else:
                    handled_count += 1
            if multi_evt.HasField("group_revision"):
                await self.set_revision(multi_evt.group_revision.timestamp)
        return handled_count

    async def _try_event_dispatcher_loop(self) -> None:
        loop_id = f"{hex(id(self))}#{time.monotonic()}"
        self.log.debug(f"Dispatcher loop {loop_id} starting")
        try:
            await self._event_dispatcher_loop()
        except Exception:
            self.log.exception("Error in event dispatcher loop")
        finally:
            self.log.debug(f"Dispatcher loop {loop_id} stopped")

    async def _event_dispatcher_loop(self) -> None:
        await self.backfill_lock.wait()
        while True:
            user, evt = await self._incoming_events.get()
            type_name = googlechat.Event.EventType.Name(evt.type)
            start = time.time()
            try:
                handled = await self.handle_event(user, evt)
                if not handled:
                    self.log.debug(f"Unhandled event type {type_name}")
            except Exception:
                self.log.exception("Error in Google Chat event handler")
            finally:
                METRIC_HANDLE_EVENT.labels(event_type=type_name).observe(time.time() - start)
            if evt.HasField("group_revision"):
                await self.set_revision(evt.group_revision.timestamp)

    def queue_event(self, user: u.User, evt: googlechat.Event) -> None:
        self._incoming_events.put_nowait((user, evt))
        if not self._event_dispatcher_task or self._event_dispatcher_task.done():
            self._event_dispatcher_task = asyncio.create_task(self._try_event_dispatcher_loop())

    async def handle_event(self, source: u.User, evt: googlechat.Event) -> bool:
        if evt.body.HasField("message_posted"):
            if evt.type == googlechat.Event.MESSAGE_UPDATED:
                await self.handle_googlechat_edit(source, evt.body.message_posted.message)
            else:
                await self.handle_googlechat_message(source, evt.body.message_posted.message)
        elif evt.body.HasField("message_reaction"):
            await self.handle_googlechat_reaction(evt.body.message_reaction)
        elif evt.body.HasField("message_deleted"):
            await self.handle_googlechat_redaction(evt.body.message_deleted)
        elif evt.body.HasField("read_receipt_changed"):
            await self.handle_googlechat_read_receipts(evt.body.read_receipt_changed)
        elif evt.body.HasField("typing_state_changed"):
            await self.handle_googlechat_typing(
                source,
                evt.body.typing_state_changed.user_id.id,
                evt.body.typing_state_changed.state,
            )
        elif evt.body.HasField("group_viewed"):
            await self.mark_read(source.gcid, evt.body.group_viewed.view_time)
        else:
            return False
        return True

    # endregion
    # region Matrix room creation

    async def _update_matrix_room(self, source: u.User, info: ChatInfo | None = None) -> None:
        puppet = await p.Puppet.get_by_custom_mxid(source.mxid)
        await self.main_intent.invite_user(
            self.mxid, source.mxid, extra_content=self._get_invite_content(puppet)
        )
        if puppet:
            did_join = await puppet.intent.ensure_joined(self.mxid)
            if did_join and self.is_direct:
                await source.update_direct_chats({self.main_intent.mxid: [self.mxid]})
        await self.update_info(source, info)

    async def update_matrix_room(self, source: u.User, info: ChatInfo | None = None) -> None:
        try:
            await self._update_matrix_room(source, info)
        except Exception:
            self.log.exception("Failed to update portal")

    async def create_matrix_room(self, source: u.User, info: ChatInfo | None = None) -> RoomID:
        if self.mxid:
            await self.update_matrix_room(source, info)
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
    def bridge_info(self) -> dict[str, Any]:
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
                "fi.mau.googlechat.is_threaded": self.is_threaded,
            },
        }

    async def update_bridge_info(self, timestamp: int | None = None) -> None:
        if not self.mxid:
            self.log.debug("Not updating bridge info: no Matrix room created")
            return
        try:
            self.log.debug("Updating bridge info...")
            await self.main_intent.send_state_event(
                self.mxid,
                StateBridge,
                self.bridge_info,
                self.bridge_info_state_key,
                timestamp=timestamp,
            )
            # TODO remove this once https://github.com/matrix-org/matrix-doc/pull/2346 is in spec
            await self.main_intent.send_state_event(
                self.mxid,
                StateHalfShotBridge,
                self.bridge_info,
                self.bridge_info_state_key,
                timestamp=timestamp,
            )
        except Exception:
            self.log.warning("Failed to update bridge info", exc_info=True)

    async def _create_matrix_room(self, source: u.User, info: ChatInfo | None = None) -> RoomID:
        if self.mxid:
            await self._update_matrix_room(source, info)
            return self.mxid

        info = await self.update_info(source=source, info=info)
        self.log.debug("Creating Matrix room")
        power_levels = PowerLevelStateEventContent()
        invites = []
        if self.is_direct:
            power_levels.users[source.mxid] = 50
        power_levels.users[self.main_intent.mxid] = 100
        initial_state = [
            {
                "type": str(EventType.ROOM_POWER_LEVELS),
                "content": power_levels.serialize(),
            },
            {
                "type": str(StateBridge),
                "state_key": self.bridge_info_state_key,
                "content": self.bridge_info,
            },
            {
                # TODO remove this once https://github.com/matrix-org/matrix-doc/pull/2346 is in spec
                "type": str(StateHalfShotBridge),
                "state_key": self.bridge_info_state_key,
                "content": self.bridge_info,
            },
        ]
        if self.config["bridge.encryption.default"] and self.matrix.e2ee:
            self.encrypted = True
            initial_state.append(
                {
                    "type": str(EventType.ROOM_ENCRYPTION),
                    "content": {"algorithm": str(EncryptionAlgorithm.MEGOLM_V1)},
                }
            )
            if self.is_direct:
                invites.append(self.az.bot_mxid)

        creation_content = {}
        if not self.config["bridge.federate_rooms"]:
            creation_content["m.federate"] = False

        # We lock backfill lock here so any messages that come between the room being created
        # and the initial backfill finishing wouldn't be bridged before the backfill messages.
        with self.backfill_lock:
            self.mxid = await self.main_intent.create_room(
                name=self.name if self.encrypted or not self.is_direct else None,
                is_direct=self.is_direct,
                initial_state=initial_state,
                invitees=invites,
                creation_content=creation_content,
            )
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
            await self.main_intent.invite_user(
                self.mxid, source.mxid, extra_content=self._get_invite_content(puppet)
            )
            if puppet:
                try:
                    if self.is_direct:
                        await source.update_direct_chats({self.main_intent.mxid: [self.mxid]})
                    await puppet.intent.join_room_by_id(self.mxid)
                except MatrixError:
                    self.log.debug(
                        "Failed to join custom puppet into newly created portal", exc_info=True
                    )

            await self.backfill(
                source, latest_revision=info.group_revision.timestamp, is_initial=True
            )

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

    def optional_send_lock(self, user_id: str) -> asyncio.Lock | FakeLock:
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

    async def handle_matrix_reaction(
        self, sender: u.User, reaction_id: EventID, target_id: EventID, reaction: str
    ) -> None:
        reaction = variation_selector.remove(reaction)

        target = await DBMessage.get_by_mxid(target_id, self.mxid)
        if not target:
            self._rec_dropped(
                sender, reaction_id, EventType.REACTION, reason="reaction target not found"
            )
            return
        existing = await DBReaction.get_by_gcid(
            reaction, sender.gcid, target.gcid, target.gc_chat, target.gc_receiver
        )
        if existing:
            self._rec_dropped(sender, reaction_id, EventType.REACTION, reason="duplicate reaction")
            return
        # TODO real timestamp?
        fake_ts = int(time.time() * 1000)
        # TODO proper locks?
        await DBReaction(
            mxid=reaction_id,
            mx_room=self.mxid,
            emoji=reaction,
            gc_sender=sender.gcid,
            gc_msgid=target.gcid,
            gc_chat=target.gc_chat,
            gc_receiver=target.gc_receiver,
            timestamp=fake_ts,
        ).insert()
        try:
            await sender.client.react(target.gc_chat, target.gc_parent_id, target.gcid, reaction)
        except Exception as e:
            self._rec_error(sender, e, reaction_id, EventType.REACTION)
        else:
            await self._rec_success(sender, reaction_id, EventType.REACTION)

    async def handle_matrix_redaction(
        self, sender: u.User, target_id: EventID, redaction_id: EventID
    ) -> None:
        target = await DBMessage.get_by_mxid(target_id, self.mxid)
        if target:
            await target.delete()
            try:
                await sender.client.delete_message(
                    target.gc_chat, target.gc_parent_id, target.gcid
                )
            except Exception as e:
                self._rec_error(sender, e, redaction_id, EventType.ROOM_REDACTION)
            else:
                await self._rec_success(sender, redaction_id, EventType.ROOM_REDACTION)
            return

        reaction = await DBReaction.get_by_mxid(target_id, self.mxid)
        if reaction:
            reaction_target = await DBMessage.get_by_gcid(
                reaction.gc_msgid, reaction.gc_chat, reaction.gc_receiver
            )
            await reaction.delete()
            try:
                await sender.client.react(
                    reaction.gc_chat,
                    reaction_target.gc_parent_id,
                    reaction_target.gcid,
                    reaction.emoji,
                    remove=True,
                )
            except Exception as e:
                self._rec_error(sender, e, redaction_id, EventType.ROOM_REDACTION)
            else:
                await self._rec_success(sender, redaction_id, EventType.ROOM_REDACTION)
            return

        self._rec_dropped(
            sender, redaction_id, EventType.ROOM_REDACTION, reason="redaction target not found"
        )

    async def handle_matrix_edit(
        self, sender: u.User, message: MessageEventContent, event_id: EventID
    ) -> None:
        target = await DBMessage.get_by_mxid(message.get_edit(), self.mxid)
        if not target:
            self._rec_dropped(
                sender,
                event_id,
                EventType.ROOM_MESSAGE,
                reason="unknown edit target",
                msgtype=message.msgtype,
            )
            return
        # We don't support non-text edits yet
        if message.msgtype != MessageType.TEXT:
            self._rec_dropped(
                sender,
                event_id,
                EventType.ROOM_MESSAGE,
                reason="non-text edit",
                msgtype=message.msgtype,
            )
            return

        text, annotations = await fmt.matrix_to_googlechat(message)
        try:
            async with self.require_send_lock(sender.gcid):
                resp = await sender.client.edit_message(
                    target.gc_chat,
                    target.gc_parent_id,
                    target.gcid,
                    text=text,
                    annotations=annotations,
                )
                self._edit_dedup[target.gcid] = resp.message.last_edit_time
        except Exception as e:
            self._rec_error(sender, e, event_id, EventType.ROOM_MESSAGE, message.msgtype)
        else:
            await self._rec_success(sender, event_id, EventType.ROOM_MESSAGE, message.msgtype)

    async def handle_matrix_message(
        self, sender: u.User, message: MessageEventContent, event_id: EventID
    ) -> None:
        if message.get_edit():
            await self.handle_matrix_edit(sender, message, event_id)
            return
        reply_to = await DBMessage.get_by_mxid(message.get_reply_to(), self.mxid)
        thread_id = (
            (reply_to.gc_parent_id or reply_to.gcid) if reply_to and self.is_threaded else None
        )
        local_id = f"mautrix-googlechat%{random.randint(0, 0xffffffffffffffff)}"
        self._local_dedup.add(local_id)

        # TODO this probably isn't nice for bridging images, it really only needs to lock the
        #      actual message send call and dedup queue append.
        async with self.require_send_lock(sender.gcid):
            try:
                if message.msgtype == MessageType.TEXT or message.msgtype == MessageType.NOTICE:
                    resp = await self._handle_matrix_text(sender, message, thread_id, local_id)
                elif message.msgtype.is_media:
                    resp = await self._handle_matrix_media(sender, message, thread_id, local_id)
                else:
                    raise ValueError(f"Unsupported msgtype {message.msgtype}")
            except Exception as e:
                self._rec_error(sender, e, event_id, EventType.ROOM_MESSAGE, message.msgtype)
            else:
                self.log.debug(f"Handled Matrix message {event_id} -> {local_id} -> {resp.gcid}")
                await self._rec_success(sender, event_id, EventType.ROOM_MESSAGE, message.msgtype)
                self._dedup.appendleft(resp.gcid)
                self._local_dedup.remove(local_id)
                await DBMessage(
                    mxid=event_id,
                    mx_room=self.mxid,
                    gcid=resp.gcid,
                    gc_chat=self.gcid,
                    gc_receiver=self.gc_receiver,
                    gc_parent_id=thread_id,
                    index=0,
                    timestamp=resp.timestamp // 1000,
                    msgtype=message.msgtype.value,
                    gc_sender=sender.gcid,
                ).insert()
                self._last_bridged_mxid = event_id

    def _rec_dropped(
        self,
        user: u.User,
        event_id: EventID,
        evt_type: EventType,
        reason: str,
        msgtype: MessageType | None = None,
    ) -> None:
        user.send_remote_checkpoint(
            status=MessageSendCheckpointStatus.PERM_FAILURE,
            event_id=event_id,
            room_id=self.mxid,
            event_type=evt_type,
            message_type=msgtype,
            error=Exception(reason),
        )

    def _rec_error(
        self,
        user: u.User,
        err: Exception,
        event_id: EventID,
        evt_type: EventType,
        msgtype: MessageType | None = None,
        edit: bool = False,
    ) -> None:
        if evt_type == EventType.ROOM_MESSAGE:
            if edit:
                self.log.exception(f"Failed handling Matrix edit {event_id}", exc_info=err)
            else:
                self.log.exception(f"Failed handling Matrix message {event_id}", exc_info=err)
        elif evt_type == EventType.ROOM_REDACTION:
            self.log.exception(f"Failed handling Matrix redaction {event_id}", exc_info=err)
        elif evt_type == EventType.REACTION:
            self.log.exception(f"Failed handling Matrix reaction {event_id}", exc_info=err)
        else:
            self.log.exception(f"Failed handling unknown Matrix event {event_id}", exc_info=err)
        user.send_remote_checkpoint(
            status=MessageSendCheckpointStatus.PERM_FAILURE,
            event_id=event_id,
            room_id=self.mxid,
            event_type=evt_type,
            message_type=msgtype,
            error=err,
        )

    async def _rec_success(
        self,
        user: u.User,
        event_id: EventID,
        evt_type: EventType,
        msgtype: MessageType | None = None,
    ) -> None:
        await self._send_delivery_receipt(event_id)
        _ = user.send_remote_checkpoint(
            status=MessageSendCheckpointStatus.SUCCESS,
            event_id=event_id,
            room_id=self.mxid,
            event_type=evt_type,
            message_type=msgtype,
        )

    @staticmethod
    def _get_send_response(
        resp: googlechat.CreateTopicResponse | googlechat.CreateMessageResponse,
    ) -> SendResponse:
        if isinstance(resp, googlechat.CreateTopicResponse):
            return SendResponse(gcid=resp.topic.id.topic_id, timestamp=resp.topic.create_time_usec)
        return SendResponse(gcid=resp.message.id.message_id, timestamp=resp.message.create_time)

    async def _handle_matrix_text(
        self, sender: u.User, message: TextMessageEventContent, thread_id: str, local_id: str
    ) -> SendResponse:
        text, annotations = await fmt.matrix_to_googlechat(message)
        await sender.client.mark_typing(self.gcid, typing=False)
        resp = await sender.client.send_message(
            self.gcid, text=text, annotations=annotations, thread_id=thread_id, local_id=local_id
        )
        return self._get_send_response(resp)

    async def _handle_matrix_media(
        self, sender: u.User, message: MediaMessageEventContent, thread_id: str, local_id: str
    ) -> SendResponse:
        if message.file and decrypt_attachment:
            data = await self.main_intent.download_media(message.file.url)
            data = decrypt_attachment(
                data, message.file.key.key, message.file.hashes.get("sha256"), message.file.iv
            )
        elif message.url:
            data = await self.main_intent.download_media(message.url)
        else:
            raise Exception("Failed to download media from matrix")
        mime = message.info.mimetype or magic.mimetype(data)
        upload = await sender.client.upload_file(
            data=data, group_id=self.gcid_plain, filename=message.body, mime_type=mime
        )
        annotations = [
            googlechat.Annotation(
                type=googlechat.UPLOAD_METADATA,
                upload_metadata=upload,
                chip_render_type=googlechat.Annotation.RENDER,
            )
        ]
        resp = await sender.client.send_message(
            self.gcid, annotations=annotations, thread_id=thread_id, local_id=local_id
        )
        return self._get_send_response(resp)

    async def handle_matrix_leave(self, user: u.User) -> None:
        if self.is_direct:
            self.log.info(
                f"{user.mxid} left private chat portal with {self.gcid},"
                " cleaning up and deleting..."
            )
            await self.cleanup_and_delete()
        else:
            self.log.debug(f"{user.mxid} left portal to {self.gcid}")

    async def handle_matrix_typing(self, users: set[UserID]) -> None:
        user_map = {mxid: await u.User.get_by_mxid(mxid, create=False) for mxid in users}
        stopped_typing = [
            user_map[mxid].client.mark_typing(self.gcid, typing=False)
            for mxid in self._typing - users
            if user_map.get(mxid)
        ]
        started_typing = [
            user_map[mxid].client.mark_typing(self.gcid, typing=True)
            for mxid in users - self._typing
            if user_map.get(mxid)
        ]
        self._typing = users
        await asyncio.gather(*stopped_typing, *started_typing)

    # endregion
    # region Hangouts event handling

    async def _bridge_own_message_pm(
        self, source: u.User, sender: p.Puppet, msg_id: str, invite: bool = True
    ) -> bool:
        if self.is_direct and sender.gcid == source.gcid and not sender.is_real_user:
            if self.invite_own_puppet_to_pm and invite:
                await self.main_intent.invite_user(self.mxid, sender.mxid)
            elif (
                await self.az.state_store.get_membership(self.mxid, sender.mxid) != Membership.JOIN
            ):
                self.log.warning(
                    f"Ignoring own {msg_id} in private chat because own puppet is not in room."
                )
                return False
        return True

    async def handle_googlechat_reaction(self, evt: googlechat.MessageReactionEvent) -> None:
        if not self.mxid:
            return
        sender = await p.Puppet.get_by_gcid(evt.user_id.id)
        target = await DBMessage.get_by_gcid(
            evt.message_id.message_id, self.gcid, self.gc_receiver
        )
        if not target:
            self.log.debug(f"Dropping reaction to unknown message {evt.message_id}")
            return
        existing = await DBReaction.get_by_gcid(
            evt.emoji.unicode, sender.gcid, target.gcid, target.gc_chat, target.gc_receiver
        )
        if evt.type == googlechat.MessageReactionEvent.ADD:
            if existing:
                # Duplicate reaction
                return
            timestamp = evt.timestamp // 1000
            matrix_reaction = variation_selector.add(evt.emoji.unicode)
            event_id = await sender.intent_for(self).react(
                target.mx_room, target.mxid, matrix_reaction, timestamp=timestamp
            )
            await DBReaction(
                mxid=event_id,
                mx_room=target.mx_room,
                emoji=evt.emoji.unicode,
                gc_sender=sender.gcid,
                gc_msgid=target.gcid,
                gc_chat=target.gc_chat,
                gc_receiver=target.gc_receiver,
                timestamp=timestamp,
            ).insert()
        elif evt.type == googlechat.MessageReactionEvent.REMOVE:
            if not existing:
                # Non-existent reaction
                return
            try:
                await sender.intent_for(self).redact(existing.mx_room, existing.mxid)
            except MForbidden:
                await self.main_intent.redact(existing.mx_room, existing.mxid)
            finally:
                await existing.delete()
        else:
            self.log.debug(f"Unknown reaction event type {evt.type}")

    async def handle_googlechat_redaction(self, evt: googlechat.MessageDeletedEvent) -> None:
        if not self.mxid:
            return
        target = await DBMessage.get_all_by_gcid(
            evt.message_id.message_id, self.gcid, self.gc_receiver
        )
        if not target:
            self.log.debug(f"Dropping deletion of unknown message {evt.message_id}")
            return
        for msg in target:
            await msg.delete()
            try:
                await self.main_intent.redact(
                    msg.mx_room, msg.mxid, timestamp=evt.timestamp // 1000
                )
            except Exception as e:
                self.log.warning(f"Failed to redact {msg.mxid}: {e}")

    async def handle_googlechat_edit(self, source: u.User, evt: googlechat.Message) -> None:
        if not self.mxid:
            return
        sender = await p.Puppet.get_by_gcid(evt.creator.user_id.id)
        msg_id = evt.id.message_id
        if not await self._bridge_own_message_pm(source, sender, f"edit {msg_id}"):
            return
        async with self.optional_send_lock(sender.gcid):
            edit_ts = evt.last_edit_time or evt.last_update_time
            try:
                if self._edit_dedup[msg_id] >= edit_ts:
                    self.log.debug(f"Ignoring likely duplicate edit of {msg_id} at {edit_ts}")
                    return
            except KeyError:
                pass
            self._edit_dedup[msg_id] = edit_ts
        target = await DBMessage.get_by_gcid(msg_id, self.gcid, self.gc_receiver, index=0)
        if not target:
            self.log.debug(f"Ignoring edit of unknown message {msg_id}")
            return
        elif target.msgtype != "m.text" or not evt.text_body:
            # Figuring out how to map multipart message edits to Matrix is hard, so don't even try
            self.log.debug(f"Ignoring edit of non-text message {msg_id}")
            return

        self._preprocess_annotations(evt)
        content = await fmt.googlechat_to_matrix(source, evt, self.encrypted)
        content.set_edit(target.mxid)
        event_id = await self._send_message(
            sender.intent_for(self), content, timestamp=edit_ts // 1000
        )
        self.log.debug("Handled Google Chat edit of %s at %s -> %s", msg_id, edit_ts, event_id)
        await self._send_delivery_receipt(event_id)

    async def handle_googlechat_update(
        self, sender: p.Puppet, timestamp: int, update: googlechat.RoomUpdatedMetadata
    ) -> bool:
        if update.HasField("rename_metadata") and update.rename_metadata.new_name:
            if self.name != update.rename_metadata.new_name:
                self.name = update.rename_metadata.new_name
                try:
                    await sender.intent_for(self).set_room_name(
                        self.mxid, self.name, timestamp=timestamp
                    )
                except (MForbidden, IntentError):
                    await self.main_intent.set_room_name(self.mxid, self.name, timestamp=timestamp)
                await self.update_bridge_info(timestamp=timestamp)
            return True
        else:
            return False

    async def handle_googlechat_message(self, source: u.User, evt: googlechat.Message) -> None:
        sender = await p.Puppet.get_by_gcid(evt.creator.user_id.id)
        msg_id = evt.id.message_id
        async with self.optional_send_lock(sender.gcid):
            if evt.local_id in self._local_dedup:
                self.log.debug(f"Dropping message {msg_id} (found in local dedup set)")
                return
            elif msg_id in self._dedup:
                self.log.debug(f"Dropping message {msg_id} (found in dedup queue)")
                return
            self._dedup.appendleft(msg_id)
            if await DBMessage.get_by_gcid(msg_id, self.gcid, self.gc_receiver):
                self.log.debug(f"Dropping message {msg_id} (found in database)")
                return
        if not self.mxid:
            mxid = await self.create_matrix_room(source)
            if not mxid:
                # Failed to create
                return
        if not await self._bridge_own_message_pm(source, sender, f"message {msg_id}"):
            return

        # Google Chat timestamps are in microseconds, Matrix wants milliseconds
        timestamp = evt.create_time // 1000

        if len(evt.annotations) == 1 and evt.annotations[0].type == googlechat.ROOM_UPDATED:
            self.log.debug("Handling Google Chat room update message %s", msg_id)
            if await self.handle_googlechat_update(
                sender, update=evt.annotations[0].room_updated, timestamp=timestamp
            ):
                return
        intent = sender.intent_for(self)
        self.log.debug("Handling Google Chat message %s", msg_id)

        reply_to = None
        parent_id = evt.id.parent_id.topic_id.topic_id
        if parent_id:
            reply_to = await DBMessage.get_last_in_thread(parent_id, self.gcid, self.gc_receiver)

        # This also adds text to evt.text_body if necessary
        attachment_urls = self._preprocess_annotations(evt)

        event_ids: list[tuple[EventID, MessageType]] = []
        if evt.text_body:
            content = await fmt.googlechat_to_matrix(source, evt, self.encrypted)
            if reply_to:
                content.set_reply(reply_to.mxid)
            event_id = await self._send_message(intent, content, timestamp=timestamp)
            event_ids.append((event_id, MessageType.TEXT))

        try:
            for att in attachment_urls:
                resp = await self._process_googlechat_attachment(
                    att, source=source, intent=intent, reply_to=reply_to, ts=timestamp
                )
                if resp:
                    event_ids.append(resp)
        except Exception:
            self.log.exception("Failed to process attachments")

        if not event_ids:
            # TODO send notification
            self.log.debug("Unhandled Google Chat message %s", msg_id)
            return
        for index, (event_id, msgtype) in enumerate(event_ids):
            await DBMessage(
                mxid=event_id,
                mx_room=self.mxid,
                gcid=msg_id,
                gc_chat=self.gcid,
                gc_receiver=self.gc_receiver,
                gc_parent_id=parent_id,
                index=index,
                timestamp=timestamp,
                msgtype=msgtype.value,
                gc_sender=sender.gcid,
            ).insert()
        self.log.debug("Handled Google Chat message %s -> %s", msg_id, event_ids)
        await self._send_delivery_receipt(event_ids[-1][0])

    @staticmethod
    async def _download_external_attachment(url: URL, max_size: int) -> tuple[bytearray, str, str]:
        async with aiohttp.ClientSession() as sess, sess.get(url) as resp:
            resp.raise_for_status()
            filename = url.path.split("/")[-1]
            data = await maugclib.Client.read_with_max_size(resp, max_size)
            mime = resp.headers.get("Content-Type") or magic.mimetype(data)
            return data, mime, filename

    @staticmethod
    def _preprocess_annotations(evt: googlechat.Message) -> list[AttachmentURL]:
        if not evt.annotations:
            return []
        attachment_urls = []
        for annotation in evt.annotations:
            if annotation.HasField("upload_metadata"):
                url_type = (
                    "FIFE_URL"
                    if annotation.upload_metadata.content_type.startswith("image/")
                    else "DOWNLOAD_URL"
                )
                url = URL("https://chat.google.com/api/get_attachment_url").with_query(
                    {
                        "url_type": url_type,
                        "attachment_token": annotation.upload_metadata.attachment_token,
                    }
                )
                au = AttachmentURL(
                    url=url,
                    name=annotation.upload_metadata.content_name,
                    mime=annotation.upload_metadata.content_type,
                )
            elif annotation.HasField("url_metadata"):
                if annotation.url_metadata.should_not_render:
                    continue
                if annotation.url_metadata.image_url:
                    url = URL(annotation.url_metadata.image_url)
                elif annotation.url_metadata.url:
                    url = URL(annotation.url_metadata.url.url)
                else:
                    continue
                au = AttachmentURL(url=url, name=None, mime=annotation.url_metadata.mime_type)
            elif annotation.HasField("video_call_metadata"):
                if annotation.video_call_metadata.meeting_space.meeting_url not in evt.text_body:
                    url = annotation.video_call_metadata.meeting_space.meeting_url
                    if not evt.text_body:
                        evt.text_body = str(url)
                    else:
                        evt.text_body += f"\n\n{url}"
                continue
            elif annotation.HasField("drive_metadata"):
                if annotation.drive_metadata.id not in evt.text_body:
                    url = fmt.DRIVE_OPEN_URL.with_query({"id": annotation.drive_metadata.id})
                    if not evt.text_body:
                        evt.text_body = str(url)
                    else:
                        evt.text_body += f"\n\n{url}"
                continue
            elif annotation.HasField("youtube_metadata"):
                if annotation.youtube_metadata.id not in evt.text_body:
                    url = fmt.YOUTUBE_URL.with_query({"v": annotation.youtube_metadata.id})
                    if not evt.text_body:
                        evt.text_body = str(url)
                    else:
                        evt.text_body += f"\n\n{url}"
                continue
            else:
                continue
            attachment_urls.append(au)
        return attachment_urls

    async def _process_googlechat_attachment(
        self,
        att: AttachmentURL,
        source: u.User,
        intent: IntentAPI,
        reply_to: DBMessage | None,
        ts: int,
    ) -> tuple[EventID, MessageType] | None:
        max_size = self.matrix.media_config.upload_size
        try:
            if att.url.host.endswith(".google.com"):
                data, mime, filename = await source.client.download_attachment(att.url, max_size)
            else:
                data, mime, filename = await self._download_external_attachment(att.url, max_size)
        except FileTooLargeError:
            # TODO send error message
            self.log.warning("Can't upload too large attachment")
            return None
        except aiohttp.ClientResponseError as e:
            self.log.warning(f"Failed to download attachment: {e}")
            return None
        if mime.startswith("text/html"):
            self.log.debug(f"Ignoring HTML URL attachment {att.url}")
            return None

        msgtype = getattr(MessageType, mime.split("/")[0].upper(), MessageType.FILE)
        if msgtype == MessageType.TEXT:
            msgtype = MessageType.FILE
        if not filename or filename == "get_attachment_url":
            if att.name:
                filename = att.name
            else:
                filename = msgtype.value + (mimetypes.guess_extension(mime) or "")
        upload_mime = mime
        decryption_info = None
        if self.encrypted and async_inplace_encrypt_attachment:
            decryption_info = await async_inplace_encrypt_attachment(data)
            upload_mime = "application/octet-stream"
        mxc_url = await intent.upload_media(data, mime_type=upload_mime, filename=filename)
        if decryption_info:
            decryption_info.url = mxc_url
            mxc_url = None
        content = MediaMessageEventContent(
            url=mxc_url,
            file=decryption_info,
            body=filename,
            info=ImageInfo(size=len(data), mimetype=mime),
        )
        content.msgtype = msgtype
        if reply_to:
            content.set_reply(reply_to.mxid)
        event_id = await self._send_message(intent, content, timestamp=ts)
        return event_id, content.msgtype

    async def handle_googlechat_read_receipts(
        self, evt: googlechat.ReadReceiptChangedEvent
    ) -> None:
        rr: googlechat.ReadReceipt
        for rr in evt.read_receipt_set.read_receipts:
            await self.mark_read(rr.user.user_id.id, rr.read_time_micros)

    async def mark_read(self, user_id: str, ts: int) -> None:
        message = await DBMessage.get_closest_before(self.gcid, self.gc_receiver, ts // 1000)
        puppet = await p.Puppet.get_by_gcid(user_id)
        if puppet and message:
            await puppet.intent_for(self).mark_read(message.mx_room, message.mxid)

    async def handle_googlechat_typing(self, source: u.User, sender: str, status: int) -> None:
        if not self.mxid:
            return
        puppet = await p.Puppet.get_by_gcid(sender)
        if self.is_direct and puppet.gcid == source.gcid:
            membership = await self.az.state_store.get_membership(self.mxid, puppet.mxid)
            if membership != Membership.JOIN:
                return
        await puppet.intent_for(self).set_typing(
            self.mxid, status == googlechat.TYPING, timeout=6000
        )

    # endregion
    # region Getters

    async def postinit(self) -> None:
        self.by_gcid[self.gcid_full] = self
        if self.mxid:
            self.by_mxid[self.mxid] = self
        if self.other_user_id or not self.is_direct:
            self._main_intent = (
                (await self.get_dm_puppet()).default_mxid_intent
                if self.is_direct
                else self.az.intent
            )

    @classmethod
    @async_getter_lock
    async def get_by_mxid(cls, mxid: RoomID) -> Portal | None:
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
    async def get_by_group_id(
        cls, group_id: googlechat.GroupId, receiver: str | None = None
    ) -> Portal | None:
        conv_id = maugclib.parsers.id_from_group_id(group_id)
        if not conv_id:
            return None
        return await cls.get_by_gcid(conv_id, receiver)

    @classmethod
    @async_getter_lock
    async def get_by_gcid(cls, gcid: str, receiver: str | None = None) -> Portal:
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
    async def get_all_by_receiver(cls, receiver: str) -> AsyncIterable[Portal]:
        portal: Portal
        for portal in await super().get_all_by_receiver(receiver):
            try:
                yield cls.by_gcid[(portal.gcid, portal.gc_receiver)]
            except KeyError:
                await portal.postinit()
                yield portal

    @classmethod
    async def all(cls) -> AsyncIterable[Portal]:
        portal: Portal
        for portal in await super().all():
            try:
                yield cls.by_gcid[(portal.gcid, portal.gc_receiver)]
            except KeyError:
                await portal.postinit()
                yield portal

    # endregion
