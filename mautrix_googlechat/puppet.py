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
from typing import Optional, Dict, AsyncIterable, Awaitable, cast, TYPE_CHECKING
import asyncio

from yarl import URL
import aiohttp
import magic

from maugclib import googlechat_pb2 as googlechat
from mautrix.types import RoomID, UserID, ContentURI, SyncToken
from mautrix.appservice import IntentAPI
from mautrix.bridge import BasePuppet, async_getter_lock
from mautrix.util.simple_template import SimpleTemplate

from .config import Config
from .db import Puppet as DBPuppet
from . import user as u, portal as p

if TYPE_CHECKING:
    from .__main__ import GoogleChatBridge


class Puppet(DBPuppet, BasePuppet):
    config: Config
    hs_domain: str
    mxid_template: SimpleTemplate[str]

    by_gcid: Dict[str, 'Puppet'] = {}
    by_custom_mxid: Dict[UserID, 'Puppet'] = {}

    def __init__(self, gcid: str, name: Optional[str] = None, photo_id: Optional[str] = None,
                 photo_mxc: Optional[ContentURI] = None, name_set: bool = False,
                 avatar_set: bool = False, is_registered: bool = False,
                 custom_mxid: Optional[UserID] = None, access_token: Optional[str] = None,
                 next_batch: Optional[SyncToken] = None, base_url: Optional[URL] = None) -> None:
        super().__init__(gcid=gcid, name=name, photo_id=photo_id, photo_mxc=photo_mxc,
                         name_set=name_set, avatar_set=avatar_set, is_registered=is_registered,
                         custom_mxid=custom_mxid, access_token=access_token, next_batch=next_batch,
                         base_url=base_url)

        self.default_mxid = self.get_mxid_from_id(gcid)
        self.default_mxid_intent = self.az.intent.user(self.default_mxid)
        self.intent = self._fresh_intent()

        self.log = self.log.getChild(self.gcid)

    def _add_to_cache(self) -> None:
        self.by_gcid[self.gcid] = self
        if self.custom_mxid:
            self.by_custom_mxid[self.custom_mxid] = self

    @classmethod
    def init_cls(cls, bridge: 'GoogleChatBridge') -> AsyncIterable[Awaitable[None]]:
        cls.config = bridge.config
        cls.loop = bridge.loop
        cls.mx = bridge.matrix
        cls.az = bridge.az
        cls.hs_domain = cls.config["homeserver"]["domain"]
        cls.mxid_template = SimpleTemplate(cls.config["bridge.username_template"], "userid",
                                           prefix="@", suffix=f":{cls.hs_domain}", type=str)
        cls.sync_with_custom_puppets = cls.config["bridge.sync_with_custom_puppets"]
        cls.homeserver_url_map = {server: URL(url) for server, url
                                  in cls.config["bridge.double_puppet_server_map"].items()}
        cls.allow_discover_url = cls.config["bridge.double_puppet_allow_discovery"]
        cls.login_shared_secret_map = {server: secret.encode("utf-8") for server, secret
                                       in cls.config["bridge.login_shared_secret_map"].items()}
        cls.login_device_name = "Google Chat Bridge"

        return (puppet.start() async for puppet in Puppet.get_all_with_custom_mxid())

    async def default_puppet_should_leave_room(self, room_id: RoomID) -> bool:
        portal = await p.Portal.get_by_mxid(room_id)
        return portal and portal.other_user_id != self.gcid

    async def _leave_rooms_with_default_user(self) -> None:
        await super()._leave_rooms_with_default_user()
        # Make the user join all private chat portals.
        await asyncio.gather(*[self.intent.ensure_joined(portal.mxid)
                               async for portal in p.Portal.get_all_by_receiver(self.gcid)
                               if portal.mxid])

    def intent_for(self, portal: 'p.Portal') -> IntentAPI:
        if (portal.other_user_id == self.gcid
            or (portal.backfill_lock.locked
                and self.config["bridge.backfill.invite_own_puppet"])):
            return self.default_mxid_intent
        return self.intent

    # region User info updating

    async def update_info(self, source: 'u.User', info: Optional[googlechat.User] = None,
                          update_avatar: bool = True) -> None:
        if info is None:
            info = (await source.get_users([self.gcid]))[0]
        changed = await self._update_name(info)
        if update_avatar:
            changed = await self._update_photo(info.avatar_url) or changed
        if changed:
            await self.save()

    @classmethod
    def get_name_from_info(cls, info: googlechat.User) -> Optional[str]:
        full = info.name
        first = info.first_name
        last = info.last_name
        if not full:
            if info.first_name or info.last_name:
                # No full name, but have first and/or last name, use those as fallback
                full = " ".join(item for item in (info.first_name, info.last_name) if item)
            elif info.email:
                # No names at all, use email as fallback
                full = info.email
            else:
                # There's nothing to show at all, return
                return None
        elif not first:
            first = full
            # Try to find the actual first name if possible
            if last and first.endswith(last):
                first = first[:-len(last)].rstrip()
        return cls.config["bridge.displayname_template"].format(first_name=first, full_name=full,
                                                                last_name=last, email=info.email)

    async def _update_name(self, info: googlechat.User) -> bool:
        name = self.get_name_from_info(info)
        if not name:
            self.log.warning(f"Got user info with no name: {info}")
            return False
        if name != self.name or not self.name_set:
            self.name = name
            try:
                await self.default_mxid_intent.set_displayname(self.name)
                self.name_set = True
            except Exception:
                self.log.exception("Failed to set displayname")
                self.name_set = False
            return True
        return False

    async def _update_photo(self, photo_url: str) -> bool:
        if photo_url != self.photo_id or not self.avatar_set:
            if photo_url != self.photo_id:
                if photo_url:
                    self.photo_mxc = await self._reupload_gc_photo(
                        photo_url, self.default_mxid_intent)
                else:
                    self.photo_mxc = ContentURI("")
                self.photo_id = photo_url
            try:
                await self.default_mxid_intent.set_avatar_url(self.photo_mxc)
                self.avatar_set = True
            except Exception:
                self.log.exception("Failed to set avatar")
                self.avatar_set = False
            return True
        return False

    @staticmethod
    async def _reupload_gc_photo(url: str, intent: IntentAPI, filename: Optional[str] = None
                                 ) -> ContentURI:
        async with aiohttp.ClientSession() as session:
            resp = await session.get(URL(url).with_scheme("https"))
            data = await resp.read()
        mime = magic.from_buffer(data, mime=True)
        return await intent.upload_media(data, mime_type=mime, filename=filename)

    # endregion
    # region Getters

    @classmethod
    @async_getter_lock
    async def get_by_gcid(cls, gcid: str, create: bool = True) -> Optional['Puppet']:
        if not gcid:
            return None
        try:
            return cls.by_gcid[gcid]
        except KeyError:
            pass

        puppet = cast(Puppet, await super().get_by_gcid(gcid))
        if puppet:
            puppet._add_to_cache()
            return puppet

        if create:
            puppet = cls(gcid)
            await puppet.insert()
            puppet._add_to_cache()
            return puppet

        return None

    @classmethod
    @async_getter_lock
    async def get_by_mxid(cls, mxid: UserID, create: bool = True) -> Optional['Puppet']:
        gcid = cls.get_id_from_mxid(mxid)
        if gcid:
            return await cls.get_by_gcid(gcid, create)

        return None

    @classmethod
    @async_getter_lock
    async def get_by_custom_mxid(cls, mxid: UserID) -> Optional['Puppet']:
        try:
            return cls.by_custom_mxid[mxid]
        except KeyError:
            pass

        puppet = cast(Puppet, await super().get_by_custom_mxid(mxid))
        if puppet:
            puppet._add_to_cache()
            return puppet

        return None

    @classmethod
    def get_id_from_mxid(cls, mxid: UserID) -> Optional[str]:
        if mxid == cls.az.bot_mxid:
            return None
        return cls.mxid_template.parse(mxid)

    @classmethod
    def get_mxid_from_id(cls, gcid: str) -> UserID:
        return UserID(cls.mxid_template.format_full(gcid))

    @classmethod
    async def get_all_with_custom_mxid(cls) -> AsyncIterable['Puppet']:
        puppets = await super().get_all_with_custom_mxid()
        puppet: cls
        for puppet in puppets:
            try:
                yield cls.by_gcid[puppet.gcid]
            except KeyError:
                puppet._add_to_cache()
                yield puppet

    # endregion
