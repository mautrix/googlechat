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

from mautrix.types import RoomID, UserID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class User:
    db: ClassVar[Database] = fake_db

    mxid: UserID
    gcid: str | None
    refresh_token: str | None
    notice_room: RoomID | None
    revision: int | None

    @classmethod
    def _from_row(cls, row: Record | None) -> User | None:
        if row is None:
            return None
        return cls(**row)

    @classmethod
    async def all_logged_in(cls) -> list[User]:
        q = (
            'SELECT mxid, gcid, refresh_token, notice_room, revision FROM "user" '
            "WHERE gcid IS NOT NULL AND refresh_token IS NOT NULL"
        )
        rows = await cls.db.fetch(q)
        return [cls._from_row(row) for row in rows]

    @classmethod
    async def get_by_gcid(cls, gcid: str) -> User | None:
        q = 'SELECT mxid, gcid, refresh_token, notice_room, revision FROM "user" WHERE gcid=$1'
        row = await cls.db.fetchrow(q, gcid)
        return cls._from_row(row)

    @classmethod
    async def get_by_mxid(cls, mxid: UserID) -> User | None:
        q = 'SELECT mxid, gcid, refresh_token, notice_room, revision FROM "user" WHERE mxid=$1'
        row = await cls.db.fetchrow(q, mxid)
        return cls._from_row(row)

    @property
    def _values(self):
        return (
            self.mxid,
            self.gcid,
            self.refresh_token,
            self.notice_room,
            self.revision,
        )

    async def insert(self) -> None:
        q = (
            'INSERT INTO "user" (mxid, gcid, refresh_token, notice_room, revision) '
            "VALUES ($1, $2, $3, $4, $5)"
        )
        await self.db.execute(q, *self._values)

    async def delete(self) -> None:
        await self.db.execute('DELETE FROM "user" WHERE mxid=$1', self.mxid)

    async def save(self) -> None:
        q = (
            'UPDATE "user" SET gcid=$2, refresh_token=$3, notice_room=$4, revision=$5 '
            "WHERE mxid=$1"
        )
        await self.db.execute(q, *self._values)

    async def set_revision(self, revision: int) -> None:
        if self.revision and self.revision >= revision > 0:
            return
        self.revision = revision
        q = 'UPDATE "user" SET revision=$1 WHERE mxid=$2 AND (revision IS NULL OR revision<$1)'
        await self.db.execute(q, self.revision, self.mxid)
