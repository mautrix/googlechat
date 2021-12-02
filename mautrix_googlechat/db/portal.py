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
from typing import Optional, List, TYPE_CHECKING, ClassVar

from asyncpg import Record
from attr import dataclass

from mautrix.types import RoomID, ContentURI
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Portal:
    db: ClassVar[Database] = fake_db

    gcid: str
    gc_receiver: str
    other_user_id: Optional[str]
    mxid: Optional[RoomID]
    name: Optional[str]
    avatar_mxc: Optional[ContentURI]
    name_set: bool
    avatar_set: bool
    encrypted: bool
    revision: Optional[int]
    is_threaded: Optional[bool]

    @classmethod
    def _from_row(cls, row: Optional[Record]) -> Optional['Portal']:
        if row is None:
            return None
        return cls(**row)

    @classmethod
    async def get_by_gcid(cls, gcid: str, gc_receiver: str) -> Optional['Portal']:
        q = ("SELECT gcid, gc_receiver, other_user_id, mxid, name, avatar_mxc, "
             "       name_set, avatar_set, encrypted, revision, is_threaded "
             "FROM portal WHERE gcid=$1 AND gc_receiver=$2")
        row = await cls.db.fetchrow(q, gcid, gc_receiver)
        return cls._from_row(row)

    @classmethod
    async def get_by_mxid(cls, mxid: RoomID) -> Optional['Portal']:
        q = ("SELECT gcid, gc_receiver, other_user_id, mxid, name, avatar_mxc, "
             "       name_set, avatar_set, encrypted, revision, is_threaded "
             "FROM portal WHERE mxid=$1")
        row = await cls.db.fetchrow(q, mxid)
        return cls._from_row(row)

    @classmethod
    async def get_all_by_receiver(cls, gc_receiver: str) -> List['Portal']:
        q = ("SELECT gcid, gc_receiver, other_user_id, mxid, name, avatar_mxc, "
             "       name_set, avatar_set, encrypted, revision, is_threaded "
             "FROM portal WHERE gc_receiver=$1 AND gcid LIKE 'dm:%'")
        rows = await cls.db.fetch(q, gc_receiver)
        return [cls._from_row(row) for row in rows]

    @classmethod
    async def all(cls) -> List['Portal']:
        q = ("SELECT gcid, gc_receiver, other_user_id, mxid, name, avatar_mxc, "
             "       name_set, avatar_set, encrypted, revision, is_threaded "
             "FROM portal")
        rows = await cls.db.fetch(q)
        return [cls._from_row(row) for row in rows]

    async def insert(self) -> None:
        q = ("INSERT INTO portal (gcid, gc_receiver, other_user_id, mxid, name, avatar_mxc, "
             "                    name_set, avatar_set, encrypted, revision, is_threaded) "
             "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)")
        await self.db.execute(q, self.gcid, self.gc_receiver, self.other_user_id, self.mxid,
                              self.name, self.avatar_mxc, self.name_set, self.avatar_set,
                              self.encrypted, self.revision, self.is_threaded)

    async def delete(self) -> None:
        q = "DELETE FROM portal WHERE gcid=$1 AND gc_receiver=$2"
        await self.db.execute(q, self.gcid, self.gc_receiver)

    async def save(self) -> None:
        await self.db.execute("UPDATE portal SET mxid=$3, name=$4, avatar_mxc=$5,"
                              "                  name_set=$6, avatar_set=$7, encrypted=$8,"
                              "                  other_user_id=$9, revision=$10, is_threaded=$11 "
                              "WHERE gcid=$1 AND gc_receiver=$2",
                              self.gcid, self.gc_receiver, self.mxid, self.name, self.avatar_mxc,
                              self.name_set, self.avatar_set, self.encrypted, self.other_user_id,
                              self.revision, self.is_threaded)

    async def set_revision(self, revision: int) -> None:
        if self.revision and self.revision >= revision > 0:
            return
        self.revision = revision
        q = ("UPDATE portal SET revision=$1 WHERE gcid=$2 AND gc_receiver=$3 "
             "                                AND (revision IS NULL OR revision<$1)")
        await self.db.execute(q, self.revision, self.gcid, self.gc_receiver)
