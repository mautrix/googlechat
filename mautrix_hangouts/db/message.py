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
from typing import Optional, Iterable, List

from sqlalchemy import Column, String, SmallInteger, UniqueConstraint, and_
from sqlalchemy.engine.result import RowProxy
from sqlalchemy.sql.expression import ClauseElement

from mautrix.types import RoomID, EventID

from mautrix.bridge.db.base import Base


class Message(Base):
    __tablename__ = "message"

    mxid: EventID = Column(String(255))
    mx_room: RoomID = Column(String(255))
    gid: str = Column(String(255), primary_key=True)

    __table_args__ = (UniqueConstraint("mxid", "mx_room", name="_mx_id_room"),)

    @classmethod
    def scan(cls, row: RowProxy) -> 'Message':
        mxid, mx_room, gid, receiver = row
        return cls(mxid=mxid, mx_room=mx_room, gid=gid)

    @classmethod
    def get_by_gid(cls, gid: str) -> Optional['Message']:
        return cls._select_one_or_none(cls.c.gid == gid)

    @classmethod
    def get_by_mxid(cls, mxid: EventID, mx_room: RoomID) -> Optional['Message']:
        return cls._select_one_or_none(and_(cls.c.mxid == mxid, cls.c.mx_room == mx_room))

    @property
    def _edit_identity(self) -> ClauseElement:
        return self.c.gid == self.gid

    def insert(self) -> None:
        with self.db.begin() as conn:
            conn.execute(self.t.insert().values(mxid=self.mxid, mx_room=self.mx_room, gid=self.gid))
