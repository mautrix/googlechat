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

from typing import TYPE_CHECKING, ClassVar

from asyncpg import Record
from attr import dataclass
from yarl import URL

from mautrix.types import ContentURI, SyncToken, UserID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Puppet:
    db: ClassVar[Database] = fake_db

    gcid: str
    name: str | None
    photo_id: str | None
    photo_mxc: ContentURI | None
    photo_hash: str | None
    name_set: bool
    avatar_set: bool
    contact_info_set: bool
    is_registered: bool

    custom_mxid: UserID | None
    access_token: str | None
    next_batch: SyncToken | None
    base_url: URL | None

    @classmethod
    def _from_row(cls, row: Record | None) -> Puppet | None:
        if row is None:
            return None
        data = {**row}
        base_url = data.pop("base_url", None)
        return cls(**data, base_url=URL(base_url) if base_url else None)

    columns = (
        "gcid, name, photo_id, photo_mxc, name_set, avatar_set, contact_info_set, is_registered, "
        "custom_mxid, access_token, next_batch, base_url, photo_hash"
    )

    @classmethod
    async def get_by_gcid(cls, gcid: str) -> Puppet | None:
        q = f"SELECT {cls.columns} FROM puppet WHERE gcid=$1"
        row = await cls.db.fetchrow(q, gcid)
        return cls._from_row(row)

    @classmethod
    async def get_by_name(cls, name: str) -> Puppet | None:
        q = f"SELECT {cls.columns} FROM puppet WHERE name=$1"
        row = await cls.db.fetchrow(q, name)
        return cls._from_row(row)

    @classmethod
    async def get_by_custom_mxid(cls, mxid: UserID) -> Puppet | None:
        q = f"SELECT {cls.columns} FROM puppet WHERE custom_mxid=$1"
        row = await cls.db.fetchrow(q, mxid)
        return cls._from_row(row)

    @classmethod
    async def get_all_with_custom_mxid(cls) -> list[Puppet]:
        q = f"SELECT {cls.columns} FROM puppet WHERE custom_mxid<>''"
        rows = await cls.db.fetch(q)
        return [cls._from_row(row) for row in rows]
    
    @classmethod
    async def all(cls) -> list[Puppet]:
        q = f"SELECT {cls.columns} FROM puppet''"
        rows = await cls.db.fetch(q)
        return [cls._from_row(row) for row in rows]

    @property
    def _values(self):
        return (
            self.gcid,
            self.name,
            self.photo_id,
            self.photo_mxc,
            self.name_set,
            self.avatar_set,
            self.contact_info_set,
            self.is_registered,
            self.custom_mxid,
            self.access_token,
            self.next_batch,
            str(self.base_url) if self.base_url else None,
            self.photo_hash,
        )

    async def insert(self) -> None:
        q = f"""
            INSERT INTO puppet ({self.columns})
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        """
        await self.db.execute(q, *self._values)

    async def delete(self) -> None:
        q = "DELETE FROM puppet WHERE gcid=$1"
        await self.db.execute(q, self.gcid)

    async def save(self) -> None:
        q = """
            UPDATE puppet
            SET name=$2, photo_id=$3, photo_mxc=$4, name_set=$5, avatar_set=$6,
                contact_info_set=$7, is_registered=$8, custom_mxid=$9, access_token=$10,
                next_batch=$11, base_url=$12, photo_hash=$13
            WHERE gcid=$1
        """
        await self.db.execute(q, *self._values)
