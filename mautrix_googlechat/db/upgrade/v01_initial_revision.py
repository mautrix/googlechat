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


@upgrade_table.register(description="Initial revision")
async def upgrade_v1(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE "user" (
            mxid          TEXT PRIMARY KEY,
            gcid          TEXT UNIQUE,
            refresh_token TEXT,
            notice_room   TEXT
        )"""
    )
    await conn.execute(
        """CREATE TABLE portal (
            gcid          TEXT,
            gc_receiver   TEXT,
            other_user_id TEXT,
            mxid          TEXT UNIQUE,
            name          TEXT,
            avatar_mxc    TEXT,
            name_set      BOOLEAN NOT NULL DEFAULT false,
            avatar_set    BOOLEAN NOT NULL DEFAULT false,
            encrypted     BOOLEAN NOT NULL DEFAULT false,
            PRIMARY KEY (gcid, gc_receiver)
        )"""
    )
    await conn.execute(
        """CREATE TABLE puppet (
            gcid      TEXT PRIMARY KEY,
            name      TEXT,
            photo_id  TEXT,
            photo_mxc TEXT,

            name_set      BOOLEAN NOT NULL DEFAULT false,
            avatar_set    BOOLEAN NOT NULL DEFAULT false,
            is_registered BOOLEAN NOT NULL DEFAULT false,

            custom_mxid  TEXT,
            access_token TEXT,
            next_batch   TEXT,
            base_url     TEXT
        )"""
    )
    await conn.execute(
        """CREATE TABLE "message" (
            mxid         TEXT NOT NULL,
            mx_room      TEXT NOT NULL,
            gcid         TEXT,
            gc_chat      TEXT NOT NULL,
            gc_receiver  TEXT,
            gc_parent_id TEXT,
            index        SMALLINT NOT NULL,
            timestamp    BIGINT   NOT NULL,
            PRIMARY KEY (gcid, gc_chat, gc_receiver, index),
            FOREIGN KEY (gc_chat, gc_receiver) REFERENCES portal(gcid, gc_receiver)
                ON UPDATE CASCADE ON DELETE CASCADE,
            UNIQUE (mxid, mx_room)
        )"""
    )
