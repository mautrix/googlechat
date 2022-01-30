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

from maugclib import googlechat_pb2 as googlechat
from mautrix.types import RoomID, UserID
from mautrix.util.formatter import MatrixParser as BaseMatrixParser, RecursionContext
from mautrix.util.formatter.html_reader import HTMLNode

from ... import puppet as pu
from .gc_message import GCEntityType, GCMessage


async def parse_html(input_html: str) -> tuple[str, list[googlechat.Annotation] | None]:
    msg = await MatrixParser().parse(input_html)
    return msg.text, msg.googlechat_entities


class MatrixParser(BaseMatrixParser[GCMessage]):
    e = GCEntityType
    fs = GCMessage

    async def color_to_fstring(self, msg: GCMessage, color: str) -> GCMessage:
        try:
            rgb_int = int(color.lstrip("#"), 16)
        except ValueError:
            return msg
        # I have no idea what's happening here but it works
        rgb_int = (rgb_int | 0x7F000000) - 2**31
        return msg.format(GCEntityType.COLOR, font_color=rgb_int)

    async def user_pill_to_fstring(self, msg: GCMessage, user_id: UserID) -> GCMessage:
        # TODO remove potential Google Chat suffix from displayname
        # TODO convert Matrix mentions of Google Chat users to GC mentions
        gcid = pu.Puppet.get_id_from_mxid(user_id)
        return msg.format(GCEntityType.USER_MENTION, user_id=gcid)

    async def room_pill_to_fstring(self, msg: GCMessage, room_id: RoomID) -> GCMessage | None:
        # TODO are room mentions supported at all?
        return None

    async def spoiler_to_fstring(self, msg: GCMessage, reason: str) -> GCMessage:
        return msg

    async def list_to_fstring(self, node: HTMLNode, ctx: RecursionContext) -> GCMessage:
        if node.tag == "ol":
            return await super().list_to_fstring(node, ctx)
        tagged_children = await self.node_to_tagged_fstrings(node, ctx)
        children = []
        for child, tag in tagged_children:
            if tag != "li":
                continue
            children.append(child.format(GCEntityType.LIST_ITEM))
        return self.fs.join(children, "\n").format(GCEntityType.LIST)

    async def header_to_fstring(cls, node: HTMLNode, ctx: RecursionContext) -> GCMessage:
        children = await cls.node_to_fstrings(node, ctx)
        length = int(node.tag[1])
        prefix = "#" * length + " "
        return GCMessage.join(children, "").prepend(prefix).format(GCEntityType.BOLD)

    async def blockquote_to_fstring(self, node: HTMLNode, ctx: RecursionContext) -> GCMessage:
        msg = await self.tag_aware_parse_node(node, ctx)
        children = msg.trim().split("\n")
        children = [child.prepend("> ") for child in children]
        return GCMessage.join(children, "\n")
