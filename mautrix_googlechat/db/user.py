# mautrix-googlechat - A Matrix-Google Chat puppeting bridge
# Copyright (C) 2023 Tulir Asokan
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
import json

from asyncpg import Record
from attr import dataclass

from maugclib import Cookies
from mautrix.types import RoomID, UserID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class User:
    db: ClassVar[Database] = fake_db

    mxid: UserID
    gcid: str | None
    cookies: Cookies | None
    user_agent: str | None
    notice_room: RoomID | None
    revision: int | None
    space_mxid: RoomID | None

    @classmethod
    def _from_row(cls, row: Record | None) -> User | None:
        if row is None:
            return None
        data = {**row}
        cookies_raw = data.pop("cookies")
        cookies = Cookies(**json.loads(cookies_raw)) if cookies_raw else None
        return cls(**data, cookies=cookies)

    @classmethod
    async def all_logged_in(cls) -> list[User]:
        q = (
            'SELECT mxid, gcid, cookies, user_agent, notice_room, revision, space_mxid FROM "user" '
            "WHERE cookies IS NOT NULL"
        )
        rows = await cls.db.fetch(q)
        return [cls._from_row(row) for row in rows]

    @classmethod
    async def get_by_gcid(cls, gcid: str) -> User | None:
        q = """
        SELECT mxid, gcid, cookies, user_agent, notice_room, revision, space_mxid FROM "user" WHERE gcid=$1
        """
        row = await cls.db.fetchrow(q, gcid)
        return cls._from_row(row)

    @classmethod
    async def get_by_mxid(cls, mxid: UserID) -> User | None:
        q = """
        SELECT mxid, gcid, cookies, user_agent, notice_room, revision, space_mxid FROM "user" WHERE mxid=$1
        """
        row = await cls.db.fetchrow(q, mxid)
        return cls._from_row(row)

    @property
    def _values(self):
        return (
            self.mxid,
            self.gcid,
            json.dumps(self.cookies._asdict()) if self.cookies else None,
            self.user_agent,
            self.notice_room,
            self.revision,
            self.space_mxid,
        )

    async def insert(self) -> None:
        q = (
            'INSERT INTO "user" (mxid, gcid, cookies, user_agent, notice_room, revision, space_mxid) '
            "VALUES ($1, $2, $3, $4, $5, $6, $7)"
        )
        await self.db.execute(q, *self._values)

    async def delete(self) -> None:
        await self.db.execute('DELETE FROM "user" WHERE mxid=$1', self.mxid)

    async def save(self) -> None:
        q = (
            'UPDATE "user" SET gcid=$2, cookies=$3, user_agent=$4, notice_room=$5, revision=$6, space_mxid=$7 '
            "WHERE mxid=$1"
        )
        await self.db.execute(q, *self._values)

    async def set_revision(self, revision: int) -> None:
        if self.revision and self.revision >= revision > 0:
            return
        self.revision = revision
        q = 'UPDATE "user" SET revision=$1 WHERE mxid=$2 AND (revision IS NULL OR revision<$1)'
        await self.db.execute(q, self.revision, self.mxid)
