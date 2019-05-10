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
from typing import Optional, Dict, Iterator, Iterable, Awaitable, Tuple, TYPE_CHECKING
import logging
import asyncio

from yarl import URL
import aiohttp
import magic

from hangups import hangouts_pb2 as hangouts
from hangups.user import User as HangoutsUser
from mautrix.types import RoomID, UserID, ContentURI
from mautrix.appservice import AppService, IntentAPI

from .config import Config
from .db import Puppet as DBPuppet
from mautrix.bridge.custom_puppet import CustomPuppetMixin
from . import user as u, portal as p, matrix as m

if TYPE_CHECKING:
    from .context import Context

config: Config


class Puppet(CustomPuppetMixin):
    log: logging.Logger = logging.getLogger("mau.puppet")
    az: AppService
    loop: asyncio.AbstractEventLoop
    mx: m.MatrixHandler
    hs_domain: str
    _mxid_prefix: str
    _mxid_suffix: str

    by_gid: Dict[str, 'Puppet'] = {}
    by_custom_mxid: Dict[UserID, 'Puppet'] = {}

    gid: str
    name: str
    photo_url: str

    is_registered: bool

    custom_mxid: UserID
    access_token: str

    _db_instance: Optional[DBPuppet]

    intent: IntentAPI

    def __init__(self, gid: str, name: str = "", photo_url: str = "", is_registered: bool = False,
                 custom_mxid: UserID = "", access_token: str = "",
                 db_instance: Optional[DBPuppet] = None) -> None:
        self.gid = gid
        self.name = name
        self.photo_url = photo_url

        self.is_registered = is_registered

        self.custom_mxid = custom_mxid
        self.access_token = access_token

        self._db_instance = db_instance

        self.default_mxid = self.get_mxid_from_id(gid)
        self.default_mxid_intent = self.az.intent.user(self.default_mxid)
        self.intent = self._fresh_intent()

        self.log = self.log.getChild(self.gid)

        self.by_gid[gid] = self
        if self.custom_mxid:
            self.by_custom_mxid[self.custom_mxid] = self

    # region DB conversion

    @property
    def db_instance(self) -> DBPuppet:
        if not self._db_instance:
            self._db_instance = DBPuppet(gid=self.gid, name=self.name, photo_url=self.photo_url,
                                         matrix_registered=self.is_registered,
                                         custom_mxid=self.custom_mxid,
                                         access_token=self.access_token)
        return self._db_instance

    @classmethod
    def from_db(cls, db_puppet: DBPuppet) -> 'Puppet':
        return Puppet(gid=db_puppet.gid, name=db_puppet.name, photo_url=db_puppet.photo_url,
                      is_registered=db_puppet.matrix_registered, custom_mxid=db_puppet.custom_mxid,
                      access_token=db_puppet.access_token, db_instance=db_puppet)

    def save(self) -> None:
        self.db_instance.edit(name=self.name, photo_url=self.photo_url,
                              matrix_registered=self.is_registered, custom_mxid=self.custom_mxid,
                              access_token=self.access_token)

    # endregion

    def default_puppet_should_leave_room(self, room_id: RoomID) -> bool:
        portal = p.Portal.get_by_mxid(room_id)
        return portal and portal.other_user_id != self.gid

    def intent_for(self, portal: 'p.Portal') -> IntentAPI:
        if portal.gid == self.gid:
            return self.default_mxid_intent
        return self.intent

    # region User info updating

    async def update_info(self, source: 'u.User', info: HangoutsUser) -> None:
        if not info:
            info = source.users.get_user(self.gid)
            # info = await source.client.get_entity_by_id(hangouts.GetEntityByIdRequest(
            #     request_header=source.client.get_request_header(),
            #     batch_lookup_spec=hangouts.EntityLookupSpec(
            #         gaia_id=self.gid,
            #     ),
            # ))
        changed = any(await asyncio.gather(self._update_name(info.full_name),
                                           self._update_photo(info.photo_url),
                                           loop=self.loop))
        if changed:
            self.save()

    async def _update_name(self, name: str) -> bool:
        if name != self.name:
            self.name = name
            await self.default_mxid_intent.set_displayname(self.name)
            return True
        return False

    async def _update_photo(self, photo_url: str) -> bool:
        if photo_url != self.photo_url:
            self.photo_url = photo_url
            if photo_url:
                avatar_uri, _, _ = await self._reupload_hg_photo(photo_url,
                                                                 self.default_mxid_intent)
            else:
                avatar_uri = ""
            await self.default_mxid_intent.set_avatar_url(avatar_uri)
            return True
        return False

    @staticmethod
    async def _reupload_hg_photo(url: str, intent: IntentAPI, filename: Optional[str] = None
                                 ) -> Tuple[ContentURI, str, int]:
        async with aiohttp.ClientSession() as session:
            resp = await session.get(URL(url).with_scheme("https"))
            data = await resp.read()
        mime = magic.from_buffer(data, mime=True)
        return await intent.upload_media(data, mime_type=mime, filename=filename), mime, len(data)

    # endregion
    # region Getters

    @classmethod
    def get_by_gid(cls, gid: str, create: bool = True) -> Optional['Puppet']:
        try:
            return cls.by_gid[gid]
        except KeyError:
            pass

        db_puppet = DBPuppet.get_by_gid(gid)
        if db_puppet:
            return cls.from_db(db_puppet)

        if create:
            puppet = cls(gid)
            puppet.db_instance.insert()
            return puppet

        return None

    @classmethod
    def get_by_mxid(cls, mxid: UserID, create: bool = True) -> Optional['Puppet']:
        gid = cls.get_id_from_mxid(mxid)
        if gid:
            return cls.get_by_gid(gid, create)

        return None

    @classmethod
    def get_by_custom_mxid(cls, mxid: UserID) -> Optional['Puppet']:
        try:
            return cls.by_custom_mxid[mxid]
        except KeyError:
            pass

        db_puppet = DBPuppet.get_by_custom_mxid(mxid)
        if db_puppet:
            return cls.from_db(db_puppet)

        return None

    @classmethod
    def get_id_from_mxid(cls, mxid: UserID) -> Optional[str]:
        prefix = cls._mxid_prefix
        suffix = cls._mxid_suffix
        if mxid[:len(prefix)] == prefix and mxid[-len(suffix):] == suffix:
            return mxid[len(prefix):-len(suffix)]
        return None

    @classmethod
    def get_mxid_from_id(cls, gid: str) -> UserID:
        return UserID(cls._mxid_prefix + gid + cls._mxid_suffix)

    @classmethod
    def get_all_with_custom_mxid(cls) -> Iterator['Puppet']:
        for db_puppet in DBPuppet.get_all_with_custom_mxid():
            try:
                yield cls.by_gid[db_puppet.gid]
            except KeyError:
                pass

            yield cls.from_db(db_puppet)

    # endregion


def init(context: 'Context') -> Iterable[Awaitable[None]]:
    global config
    Puppet.az, config, Puppet.loop = context.core
    Puppet.mx = context.mx
    username_template = config["bridge.username_template"].lower()
    CustomPuppetMixin.sync_with_custom_puppets = config["bridge.sync_with_custom_puppets"]
    index = username_template.index("{userid}")
    length = len("{userid}")
    Puppet.hs_domain = config["homeserver"]["domain"]
    Puppet._mxid_prefix = f"@{username_template[:index]}"
    Puppet._mxid_suffix = f"{username_template[index + length:]}:{Puppet.hs_domain}"

    return (puppet.start() for puppet in Puppet.get_all_with_custom_mxid())
