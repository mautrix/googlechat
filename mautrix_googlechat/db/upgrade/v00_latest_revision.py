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
from mautrix.util.async_db import Connection

from . import upgrade_table


@upgrade_table.register(description="Latest revision", upgrades_to=10)
async def upgrade_latest(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE "user" (
            mxid        TEXT PRIMARY KEY,
            gcid        TEXT UNIQUE,
            cookies     TEXT,
            user_agent  TEXT,
            notice_room TEXT,
            revision    BIGINT
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
            description   TEXT,
            name_set      BOOLEAN NOT NULL DEFAULT false,
            avatar_set    BOOLEAN NOT NULL DEFAULT false,
            description_set BOOLEAN NOT NULL DEFAULT false,
            encrypted     BOOLEAN NOT NULL DEFAULT false,
            revision      BIGINT,
            threads_only  BOOLEAN,
            threads_enabled BOOLEAN,
            PRIMARY KEY (gcid, gc_receiver)
        )"""
    )
    await conn.execute(
        """CREATE TABLE puppet (
            gcid       TEXT PRIMARY KEY,
            name       TEXT,
            photo_id   TEXT,
            photo_mxc  TEXT,
            photo_hash TEXT,

            name_set      BOOLEAN NOT NULL DEFAULT false,
            avatar_set    BOOLEAN NOT NULL DEFAULT false,
            is_registered BOOLEAN NOT NULL DEFAULT false,

            contact_info_set BOOLEAN NOT NULL DEFAULT false,

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
            gc_sender    TEXT,
            "index"      SMALLINT NOT NULL,
            timestamp    BIGINT   NOT NULL,
            msgtype      TEXT,
            PRIMARY KEY (gcid, gc_chat, gc_receiver, "index"),
            FOREIGN KEY (gc_chat, gc_receiver) REFERENCES portal(gcid, gc_receiver)
                ON UPDATE CASCADE ON DELETE CASCADE,
            UNIQUE (mxid, mx_room)
        )"""
    )
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
                REFERENCES message(gcid, gc_chat, gc_receiver, "index")
                ON UPDATE CASCADE ON DELETE CASCADE,
            UNIQUE (mxid, mx_room)
        )"""
    )
