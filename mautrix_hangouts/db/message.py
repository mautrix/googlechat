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
from datetime import datetime, timezone

from sqlalchemy import Column, String, SmallInteger, UniqueConstraint, and_, types

from mautrix.types import RoomID, EventID

from mautrix.util.db import Base


class UTCDateTime(types.TypeDecorator):
    impl = types.DateTime

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            elif value.tzinfo != timezone.utc:
                value = value.astimezone(timezone.utc)

        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        else:
            return value


class Message(Base):
    __tablename__ = "message"

    mxid: EventID = Column(String(255))
    mx_room: RoomID = Column(String(255))
    gid: str = Column(String(255), primary_key=True)
    receiver: str = Column(String(255), primary_key=True)
    index: int = Column(SmallInteger, primary_key=True)
    date: Optional[datetime] = Column(UTCDateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("mxid", "mx_room", name="_mx_id_room"),)

    @classmethod
    def get_by_gid(cls, gid: str) -> Optional['Message']:
        return cls._select_one_or_none(cls.c.gid == gid)

    @classmethod
    def get_most_recent(cls, mx_room: RoomID, max_date: Optional[datetime] = None
                        ) -> Optional['Message']:
        cond = cls.c.mx_room == mx_room
        if max_date is not None:
            cond &= cls.c.date <= max_date
        return cls._one_or_none(cls.db.execute(cls.t.select().where(cond)
                                               .order_by(cls.c.date.desc()).limit(1)))

    @classmethod
    def get_by_mxid(cls, mxid: EventID, mx_room: RoomID) -> Optional['Message']:
        return cls._select_one_or_none(and_(cls.c.mxid == mxid, cls.c.mx_room == mx_room))

    @classmethod
    def delete_all_by_mxid(cls, mx_room: RoomID) -> None:
        cls.db.execute(cls.t.delete().where(cls.c.mx_room == mx_room))
