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

from mautrix.types import EventID, RoomID
from mautrix.util.async_db import Database

fake_db = Database.create("") if TYPE_CHECKING else None


@dataclass
class Reaction:
    db: ClassVar[Database] = fake_db

    mxid: EventID
    mx_room: RoomID
    emoji: str
    gc_sender: str
    gc_msgid: str
    gc_chat: str
    gc_receiver: str
    timestamp: int

    @classmethod
    def _from_row(cls, row: Record | None) -> Reaction | None:
        if row is None:
            return None
        return cls(**row)

    columns = "mxid, mx_room, emoji, gc_sender, gc_msgid, gc_chat, gc_receiver, timestamp"

    @classmethod
    async def get_all_by_gcid(cls, gcid: str, gc_receiver: str) -> list[Reaction]:
        q = f"SELECT {cls.columns} FROM message WHERE gcid=$1 AND gc_receiver=$2"
        rows = await cls.db.fetch(q, gcid, gc_receiver)
        return [cls._from_row(row) for row in rows]

    @classmethod
    async def get_by_gcid(
        cls, emoji: str, gc_sender: str, gc_msgid: str, gc_chat: str, gc_receiver: str
    ) -> Reaction | None:
        q = (
            f"SELECT {cls.columns} FROM reaction "
            f"WHERE emoji=$1 AND gc_sender=$2 AND gc_msgid=$3 AND gc_chat=$4 AND gc_receiver=$5"
        )
        row = await cls.db.fetchrow(q, emoji, gc_sender, gc_msgid, gc_chat, gc_receiver)
        return cls._from_row(row)

    @classmethod
    async def delete_all_by_room(cls, room_id: RoomID) -> None:
        await cls.db.execute("DELETE FROM message WHERE mx_room=$1", room_id)

    @classmethod
    async def get_by_mxid(cls, mxid: EventID, mx_room: RoomID) -> Reaction | None:
        q = f"SELECT {cls.columns} FROM reaction WHERE mxid=$1 AND mx_room=$2"
        row = await cls.db.fetchrow(q, mxid, mx_room)
        return cls._from_row(row)

    async def insert(self) -> None:
        q = (
            "INSERT INTO reaction (mxid, mx_room, emoji, gc_sender, gc_msgid, gc_chat,"
            "                      gc_receiver, timestamp) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)"
        )
        await self.db.execute(
            q,
            self.mxid,
            self.mx_room,
            self.emoji,
            self.gc_sender,
            self.gc_msgid,
            self.gc_chat,
            self.gc_receiver,
            self.timestamp,
        )

    async def delete(self) -> None:
        q = (
            "DELETE FROM reaction WHERE emoji=$1 AND gc_sender=$2 AND gc_msgid=$3"
            "                       AND gc_chat=$4 AND gc_receiver=$5"
        )
        await self.db.execute(
            q, self.emoji, self.gc_sender, self.gc_msgid, self.gc_chat, self.gc_receiver
        )
