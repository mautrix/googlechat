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
class Message:
    db: ClassVar[Database] = fake_db

    mxid: EventID
    mx_room: RoomID
    gcid: str
    gc_chat: str
    gc_receiver: str
    gc_parent_id: str | None
    index: int
    timestamp: int
    msgtype: str | None
    gc_sender: str | None

    @classmethod
    def _from_row(cls, row: Record | None) -> Message | None:
        if row is None:
            return None
        return cls(**row)

    columns = (
        "mxid, mx_room, gcid, gc_chat, gc_receiver, gc_parent_id, "
        "index, timestamp, msgtype, gc_sender"
    )

    @classmethod
    async def get_all_by_gcid(cls, gcid: str, gc_chat: str, gc_receiver: str) -> list[Message]:
        q = f"SELECT {cls.columns} FROM message WHERE gcid=$1 AND gc_chat=$2 AND gc_receiver=$3"
        rows = await cls.db.fetch(q, gcid, gc_chat, gc_receiver)
        return [cls._from_row(row) for row in rows]

    @classmethod
    async def get_by_gcid(
        cls, gcid: str, gc_chat: str, gc_receiver: str, index: int = 0
    ) -> Message | None:
        q = (
            f"SELECT {cls.columns} FROM message"
            " WHERE gcid=$1 AND gc_chat=$2 AND gc_receiver=$3 AND index=$4"
        )
        row = await cls.db.fetchrow(q, gcid, gc_chat, gc_receiver, index)
        return cls._from_row(row)

    @classmethod
    async def get_last_in_thread(
        cls, gc_parent_id: str, gc_chat: str, gc_receiver: str
    ) -> Message | None:
        q = (
            f"SELECT {cls.columns} FROM message"
            " WHERE (gc_parent_id=$1 OR gcid=$1) AND gc_chat=$2 AND gc_receiver=$3"
            " ORDER BY timestamp DESC, index DESC LIMIT 1"
        )
        row = await cls.db.fetchrow(q, gc_parent_id, gc_chat, gc_receiver)
        return cls._from_row(row)

    @classmethod
    async def delete_all_by_room(cls, room_id: RoomID) -> None:
        await cls.db.execute("DELETE FROM message WHERE mx_room=$1", room_id)

    @classmethod
    async def get_by_mxid(cls, mxid: EventID, mx_room: RoomID) -> Message | None:
        q = f"SELECT {cls.columns} FROM message WHERE mxid=$1 AND mx_room=$2"
        row = await cls.db.fetchrow(q, mxid, mx_room)
        return cls._from_row(row)

    @classmethod
    async def get_most_recent(cls, gc_chat: str, gc_receiver: str) -> Message | None:
        q = (
            f"SELECT {cls.columns} FROM message"
            " WHERE gc_chat=$1 AND gc_receiver=$2 ORDER BY timestamp DESC LIMIT 1"
        )
        row = await cls.db.fetchrow(q, gc_chat, gc_receiver)
        return cls._from_row(row)

    @classmethod
    async def get_closest_before(
        cls, gc_chat: str, gc_receiver: str, timestamp: int
    ) -> Message | None:
        q = (
            f"SELECT {cls.columns} FROM message"
            " WHERE gc_chat=$1 AND gc_receiver=$2 AND timestamp<=$3"
            " ORDER BY timestamp DESC LIMIT 1"
        )
        row = await cls.db.fetchrow(q, gc_chat, gc_receiver, timestamp)
        return cls._from_row(row)

    async def insert(self) -> None:
        q = (
            "INSERT INTO message (mxid, mx_room, gcid, gc_chat, gc_receiver, gc_parent_id, "
            "                     index, timestamp, msgtype, gc_sender) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)"
        )
        await self.db.execute(
            q,
            self.mxid,
            self.mx_room,
            self.gcid,
            self.gc_chat,
            self.gc_receiver,
            self.gc_parent_id,
            self.index,
            self.timestamp,
            self.msgtype,
            self.gc_sender,
        )

    async def delete(self) -> None:
        q = "DELETE FROM message WHERE gcid=$1 AND gc_receiver=$2 AND index=$3"
        await self.db.execute(q, self.gcid, self.gc_receiver, self.index)
