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
from asyncpg import Connection

from . import upgrade_table


@upgrade_table.register(description="Add reaction table and update message table")
async def upgrade_v2(conn: Connection, dialect: str) -> None:
    if dialect != "sqlite":
        # This change was backported to the v1 db schema before SQLite support was added
        await conn.execute(
            "ALTER TABLE message"
            "  DROP CONSTRAINT message_pkey,"
            "  ADD PRIMARY KEY (gcid, gc_chat, gc_receiver, index)"
        )
    await conn.execute("ALTER TABLE message ADD COLUMN msgtype TEXT")
    await conn.execute("ALTER TABLE message ADD COLUMN gc_sender TEXT")
    await conn.execute(
        """CREATE TABLE reaction (
            mxid         TEXT NOT NULL,
            mx_room      TEXT NOT NULL,
            emoji        TEXT,
            gc_sender    TEXT,
            gc_msgid     TEXT,
            gc_chat      TEXT,
            gc_receiver  TEXT,
            timestamp    BIGINT NOT NULL,
            _index       SMALLINT DEFAULT 0,
            PRIMARY KEY (emoji, gc_sender, gc_msgid, gc_chat, gc_receiver),
            FOREIGN KEY (gc_chat, gc_receiver)
                REFERENCES portal(gcid, gc_receiver)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (gc_msgid, gc_chat, gc_receiver, _index)
                REFERENCES message(gcid, gc_chat, gc_receiver, index)
                ON UPDATE CASCADE ON DELETE CASCADE,
            UNIQUE (mxid, mx_room)
        )"""
    )
