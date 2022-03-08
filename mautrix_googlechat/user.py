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

from typing import TYPE_CHECKING, Any, AsyncIterable, Awaitable, Callable, Iterable, cast
import asyncio
import time

from maugclib import (
    ChannelLifetimeExpired,
    Client,
    GoogleAuthError,
    RefreshTokenCache,
    TokenManager,
    googlechat_pb2 as googlechat,
)
from mautrix.bridge import BaseUser, async_getter_lock
from mautrix.types import MessageType, RoomID, UserID
from mautrix.util.bridge_state import BridgeState, BridgeStateEvent
from mautrix.util.opt_prometheus import Gauge, Histogram, async_time
import maugclib.parsers

from . import portal as po, puppet as pu
from .config import Config
from .db import User as DBUser

if TYPE_CHECKING:
    from .__main__ import GoogleChatBridge

METRIC_SYNC = Histogram("bridge_sync", "calls to sync")
METRIC_LOGGED_IN = Gauge("bridge_logged_in", "Number of users logged into the bridge")
METRIC_CONNECTED = Gauge("bridge_connected", "Number of users connected to Google Chat")


class User(DBUser, BaseUser):
    by_mxid: dict[UserID, User] = {}
    by_gcid: dict[str, User] = {}
    config: Config

    client: Client | None
    is_admin: bool
    _db_instance: DBUser | None

    _notice_room_lock: asyncio.Lock
    _intentional_disconnect: bool
    name: str | None
    email: str | None
    name_future: asyncio.Future
    connected: bool
    _skip_backoff: bool
    _skip_on_connect: bool
    _prev_sync: float
    periodic_sync_task: asyncio.Task | None

    groups: dict[str, googlechat.GetGroupResponse]
    groups_lock: asyncio.Lock
    users: dict[str, googlechat.User]
    users_lock: asyncio.Lock

    def __init__(
        self,
        mxid: UserID,
        gcid: str | None = None,
        revision: int | None = None,
        refresh_token: str | None = None,
        notice_room: RoomID | None = None,
    ) -> None:
        super().__init__(
            mxid=mxid,
            gcid=gcid,
            refresh_token=refresh_token,
            revision=revision,
            notice_room=notice_room,
        )
        BaseUser.__init__(self)
        self._notice_room_lock = asyncio.Lock()
        self.is_whitelisted, self.is_admin, self.level = self.config.get_permissions(mxid)
        self.client = None
        self.name = None
        self.email = None
        self.name_future = self.loop.create_future()
        self.connected = False
        self._skip_backoff = False
        self._skip_on_connect = False
        self._prev_sync = 0
        self.groups = {}
        self.groups_lock = asyncio.Lock()
        self.users = {}
        self.users_lock = asyncio.Lock()
        self._intentional_disconnect = False
        self.periodic_sync_task = None

    # region Sessions

    def _add_to_cache(self) -> None:
        self.by_mxid[self.mxid] = self
        if self.gcid:
            self.by_gcid[self.gcid] = self

    @classmethod
    async def all_logged_in(cls) -> AsyncIterable[User]:
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
    async def get_by_mxid(cls, mxid: UserID, *, create: bool = True) -> User | None:
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
    async def get_by_gcid(cls, gcid: str) -> User | None:
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

    async def get_puppet(self) -> pu.Puppet | None:
        if not self.gcid:
            return None
        return await pu.Puppet.get_by_gcid(self.gcid)

    async def get_portal_with(self, puppet: pu.Puppet, create: bool = True) -> po.Portal | None:
        # DMs need to be explicitly created on Google Chat, so we can't just get a chat by ID here.
        return None

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
                creation_content = {}
                if not self.config["bridge.federate_rooms"]:
                    creation_content["m.federate"] = False
                self.notice_room = await self.az.intent.create_room(
                    is_direct=True,
                    invitees=[self.mxid],
                    topic="Google Chat bridge notices",
                    creation_content=creation_content,
                )
                await self.save()
        return self.notice_room

    async def send_bridge_notice(
        self, text: str, important: bool = False, state_event: BridgeStateEvent | None = None
    ) -> None:
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
    def init_cls(cls, bridge: "GoogleChatBridge") -> AsyncIterable[Awaitable[None]]:
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
            self.login_complete(token_mgr)

    def login_complete(self, token_manager: TokenManager) -> None:
        self.client = Client(token_manager, max_retries=3, retry_backoff_base=2)
        asyncio.create_task(self.start())
        if not self.periodic_sync_task:
            self.periodic_sync_task = asyncio.create_task(self._periodic_sync())
        self.client.on_stream_event.add_observer(self._in_background(self.on_stream_event))
        self.client.on_connect.add_observer(self.on_connect)
        self.client.on_reconnect.add_observer(self.on_reconnect)
        self.client.on_disconnect.add_observer(self.on_disconnect)

    def _in_background(
        self, method: Callable[[Any], Awaitable[None]]
    ) -> Callable[[Any], Awaitable[None]]:
        async def try_proxy(*args, **kwargs) -> None:
            try:
                await method(*args, **kwargs)
            except Exception:
                self.log.exception("Exception in event handler")

        async def proxy(*args, **kwargs) -> None:
            asyncio.create_task(try_proxy(*args, **kwargs))

        return proxy

    async def start(self) -> None:
        last_disconnection = 0
        backoff = 4
        backoff_reset_in_seconds = 60
        state_event = BridgeStateEvent.TRANSIENT_DISCONNECT
        self._intentional_disconnect = False
        while True:
            try:
                await self.client.connect(max_age=1.5 * 60 * 60)
                self._track_metric(METRIC_CONNECTED, False)
                if self._intentional_disconnect:
                    self.log.info("Client connection finished")
                    return
                elif self._skip_backoff:
                    self._skip_backoff = False
                    self.log.debug("Client connection was terminated for reconnection")
                    continue
                else:
                    self.log.warning("Client connection finished unexpectedly")
                    error_msg = "Client connection finished unexpectedly"
            except ChannelLifetimeExpired:
                self.log.debug("Client connection was terminated after being alive too long")
                self._skip_on_connect = True
                continue
            except Exception as e:
                self._track_metric(METRIC_CONNECTED, False)
                self.log.exception("Exception in connection")
                error_msg = f"Exception in Google Chat connection: {e}"

            if last_disconnection + backoff_reset_in_seconds < time.time():
                backoff = 4
                state_event = BridgeStateEvent.TRANSIENT_DISCONNECT
            else:
                backoff = int(backoff * 1.5)
                if backoff > 60:
                    state_event = BridgeStateEvent.UNKNOWN_ERROR
            await self.send_bridge_notice(
                error_msg,
                state_event=state_event,
                important=state_event == BridgeStateEvent.UNKNOWN_ERROR,
            )
            last_disconnection = time.time()
            self.log.debug(f"Reconnecting in {backoff} seconds")
            await asyncio.sleep(backoff)

    async def stop(self) -> None:
        if self.client:
            self._intentional_disconnect = True
            self.client.disconnect()
        if self.periodic_sync_task:
            self.periodic_sync_task.cancel()
            self.periodic_sync_task = None
        await self.save()

    async def logout(self) -> None:
        self._track_metric(METRIC_LOGGED_IN, False)
        self.by_gcid.pop(self.gcid, None)
        self.gcid = None
        self.refresh_token = None
        await self.stop()
        self.client = None
        self.connected = False

        self.users = {}
        self.groups = {}

        self.name = None
        self.email = None
        if not self.name_future.done():
            self.name_future.set_exception(Exception("logged out"))
        self.name_future = self.loop.create_future()

    async def on_connect(self) -> None:
        self.connected = True
        if not self._skip_on_connect:
            asyncio.create_task(self.on_connect_later())
            await self.send_bridge_notice("Connected to Google Chat")
        else:
            self._skip_on_connect = False
            await self.push_bridge_state(BridgeStateEvent.CONNECTED)

    async def get_self(self) -> googlechat.User:
        if not self.gcid:
            info = await self.client.proto_get_self_user_status(
                googlechat.GetSelfUserStatusRequest(request_header=self.client.gc_request_header)
            )
            self.gcid = info.user_status.user_id.id
            self.by_gcid[self.gcid] = self

        resp = await self.client.proto_get_members(
            googlechat.GetMembersRequest(
                request_header=self.client.gc_request_header,
                member_ids=[
                    googlechat.MemberId(user_id=googlechat.UserId(id=self.gcid)),
                ],
            )
        )
        user: googlechat.User = resp.members[0].user
        self.users[user.user_id.id] = user
        return user

    async def get_users(self, ids: Iterable[str]) -> list[googlechat.User]:
        async with self.users_lock:
            req_ids = [
                googlechat.MemberId(user_id=googlechat.UserId(id=user_id))
                for user_id in ids
                if user_id not in self.users
            ]
            if req_ids:
                self.log.debug(f"Fetching info of users {[user.user_id.id for user in req_ids]}")
                resp = await self.client.proto_get_members(
                    googlechat.GetMembersRequest(
                        request_header=self.client.gc_request_header,
                        member_ids=req_ids,
                    )
                )
                member: googlechat.Member
                for member in resp.members:
                    self.users[member.user.user_id.id] = member.user
        return [self.users[user_id] for user_id in ids]

    async def get_group(
        self, id: googlechat.GroupId | str, revision: int
    ) -> googlechat.GetGroupResponse:
        if isinstance(id, str):
            group_id = maugclib.parsers.group_id_from_id(id)
            conv_id = id
        else:
            group_id = id
            conv_id = maugclib.parsers.id_from_group_id(id)
        try:
            group = self.groups[conv_id]
        except KeyError:
            pass
        else:
            if group.group_revision.timestamp >= revision:
                return group

        async with self.groups_lock:
            # Try again in case the fetch succeeded while waiting for the lock
            try:
                group = self.groups[conv_id]
            except KeyError:
                pass
            else:
                if group.group_revision.timestamp >= revision:
                    return group
            self.log.debug(f"Fetching info of chat {conv_id}")
            resp = await self.client.proto_get_group(
                googlechat.GetGroupRequest(
                    request_header=self.client.gc_request_header,
                    group_id=group_id,
                    fetch_options=[
                        googlechat.GetGroupRequest.MEMBERS,
                        googlechat.GetGroupRequest.INCLUDE_DYNAMIC_GROUP_NAME,
                    ],
                )
            )
            self.groups[conv_id] = resp
        return resp

    async def on_connect_later(self) -> None:
        try:
            self_info = await self.get_self()
        except Exception:
            self.log.exception("Failed to get own info")
            return
        await self.push_bridge_state(BridgeStateEvent.BACKFILLING)

        self.name = self_info.name or self_info.first_name
        self.email = self_info.email
        self.log.debug(f"Found own name: {self.name}")
        if not self.name_future.done():
            self.name_future.set_result(self.name)

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

        await self.push_bridge_state(BridgeStateEvent.CONNECTED)

    async def on_reconnect(self) -> None:
        self.connected = True
        await self.send_bridge_notice("Reconnected to Google Chat")
        await self.push_bridge_state(BridgeStateEvent.CONNECTED)

    async def on_disconnect(self) -> None:
        self.connected = False
        await self.send_bridge_notice("Disconnected from Google Chat")
        await self.push_bridge_state(
            BridgeStateEvent.TRANSIENT_DISCONNECT, error="googlechat-disconnected"
        )

    def reconnect(self) -> None:
        self._skip_backoff = True
        self.client.disconnect()

    async def _periodic_sync(self) -> None:
        while True:
            try:
                await asyncio.sleep(60 * 60)
                if self._prev_sync + 3 * 60 > time.monotonic():
                    self.log.debug("Skipping periodic sync, less than 3 minutes since last sync")
                    continue
                # Low limit here since the manual reconnect will trigger a full sync
                backfilled_count = await self.sync(limit=3)
                if backfilled_count:
                    self.log.debug(f"Periodic sync backfilled {backfilled_count} chats")
                    self.reconnect()
                else:
                    self.log.debug("Periodic sync didn't backfill anything")
            except asyncio.CancelledError:
                self.log.debug("Periodic sync cancelled")
                break
            except Exception:
                self.log.exception("Exception in periodic sync")

    @async_time(METRIC_SYNC)
    async def sync(self, limit: int | None = None) -> int:
        self._prev_sync = time.monotonic()
        self.log.debug("Fetching first page of the world")
        req = googlechat.PaginatedWorldRequest(
            request_header=self.client.gc_request_header,
            fetch_from_user_spaces=True,
            fetch_options=[
                googlechat.PaginatedWorldRequest.EXCLUDE_GROUP_LITE,
            ],
        )
        if limit:
            req.world_section_requests.append(googlechat.WorldSectionRequest(page_size=limit))
        resp = await self.client.proto_paginated_world(req)
        items: list[googlechat.WorldItemLite] = list(resp.world_items)
        items.sort(key=lambda item: item.sort_timestamp, reverse=True)
        max_sync = self.config["bridge.initial_chat_sync"]
        portals_to_sync: list[tuple[po.Portal, googlechat.WorldItemLite]] = []
        prefetch_users: set[str] = set()
        for index, item in enumerate(items):
            conv_id = maugclib.parsers.id_from_group_id(item.group_id)
            if (
                item.read_state.blocked
                or item.read_state.hide_timestamp > 0
                or item.read_state.membership_state != googlechat.MEMBER_JOINED
            ):
                self.log.trace(f"Skipping unwanted chat %s", conv_id)
                continue
            portal = await po.Portal.get_by_gcid(conv_id, self.gcid)
            if portal.mxid or index < max_sync:
                if item.HasField("dm_members"):
                    prefetch_users |= {member.id for member in item.dm_members.members}
                portals_to_sync.append((portal, item))

        # To avoid the portal sync sending individual get user requests for each DM portal,
        # make all of them beforehand. Group chat portals will still request all group
        # participants separately, but that's probably fine since they can be larger anyway.
        await self.get_users(prefetch_users)

        backfilled_count = 0
        for portal, info in portals_to_sync:
            self.log.debug("Syncing %s", portal.gcid)
            if portal.mxid:
                if limit is None:
                    await portal.update_matrix_room(self, info)
                if portal.revision and info.group_revision.timestamp > portal.revision:
                    msg_count = await portal.backfill(self, info.group_revision.timestamp)
                    if msg_count > 0:
                        backfilled_count += 1
            else:
                await portal.create_matrix_room(self, info)
                backfilled_count += 1

        await self.update_direct_chats()
        return backfilled_count

    async def get_direct_chats(self) -> dict[UserID, list[RoomID]]:
        return {
            pu.Puppet.get_mxid_from_id(portal.other_user_id): [portal.mxid]
            async for portal in po.Portal.get_all_by_receiver(self.gcid)
            if portal.mxid
        }

    async def on_stream_event(self, evt: googlechat.Event) -> None:
        group_id = evt.group_id
        if evt.type == googlechat.Event.TYPING_STATE_CHANGED:
            group_id = evt.body.typing_state_changed.context.group_id
        portal = await po.Portal.get_by_group_id(group_id, self.gcid)
        if portal:
            portal.queue_event(self, evt)
        if evt.HasField("user_revision"):
            await self.set_revision(evt.user_revision.timestamp)

    async def mark_read(self, conversation_id: str, timestamp: int) -> None:
        await self.client.proto_mark_group_read_state(
            googlechat.MarkGroupReadstateRequest(
                request_header=self.client.gc_request_header,
                id=maugclib.parsers.group_id_from_id(conversation_id),
                last_read_time=int((timestamp or (time.time() * 1000)) * 1000),
            )
        )


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
