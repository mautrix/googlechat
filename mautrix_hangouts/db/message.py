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
from typing import Optional

from sqlalchemy import Column, String, SmallInteger, UniqueConstraint, and_

from mautrix.types import RoomID, EventID

from mautrix.util.db import Base


class Message(Base):
    __tablename__ = "message"

    mxid: EventID = Column(String(255))
    mx_room: RoomID = Column(String(255))
    gid: str = Column(String(255), primary_key=True)
    receiver: str = Column(String(255), primary_key=True)
    index: int = Column(SmallInteger, primary_key=True)

    __table_args__ = (UniqueConstraint("mxid", "mx_room", name="_mx_id_room"),)

    @classmethod
    def get_by_gid(cls, gid: str) -> Optional['Message']:
        return cls._select_one_or_none(cls.c.gid == gid)

    @classmethod
    def get_by_mxid(cls, mxid: EventID, mx_room: RoomID) -> Optional['Message']:
        return cls._select_one_or_none(and_(cls.c.mxid == mxid, cls.c.mx_room == mx_room))

    @classmethod
    def delete_all_by_mxid(cls, mx_room: RoomID) -> None:
        cls.db.execute(cls.t.delete().where(cls.c.mx_room == mx_room))
