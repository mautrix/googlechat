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
from typing import List, Tuple, Optional

from mautrix.types import UserID, RoomID
from mautrix.util.formatter import MatrixParser as BaseMatrixParser, RecursionContext
from mautrix.util.formatter.html_reader_htmlparser import read_html, HTMLNode

from maugclib import googlechat_pb2 as googlechat

from ... import puppet as pu
from .gc_message import GCMessage, GCEntityType


ParsedMessage = Tuple[str, Optional[List[googlechat.Annotation]]]


def parse_html(input_html: str) -> ParsedMessage:
    msg = MatrixParser.parse(input_html)
    return msg.text, msg.googlechat_entities


class MatrixParser(BaseMatrixParser[GCMessage]):
    e = GCEntityType
    fs = GCMessage
    read_html = read_html

    @classmethod
    def color_to_fstring(cls, node: HTMLNode, ctx: RecursionContext, color: str
                         ) -> Optional[GCMessage]:
        msg = cls.tag_aware_parse_node(node, ctx)
        try:
            rgb_int = int(color.lstrip("#"), 16)
        except ValueError:
            return msg
        # I have no idea what's happening here but it works
        rgb_int = (rgb_int | 0x7f000000) - 2**31
        return msg.format(GCEntityType.FONT_COLOR, font_color=rgb_int)

    @classmethod
    def user_pill_to_fstring(cls, msg: GCMessage, user_id: UserID) -> GCMessage:
        # TODO remove potential Google Chat suffix from displayname
        # TODO convert Matrix mentions of Google Chat users to GC mentions (requires async)
        gcid = pu.Puppet.get_id_from_mxid(user_id)
        return msg.format(GCEntityType.USER_MENTION, user_id=gcid)

    @classmethod
    def room_pill_to_fstring(cls, msg: GCMessage, room_id: RoomID) -> Optional[GCMessage]:
        # TODO are room mentions supported at all?
        return None

    @classmethod
    def list_to_fstring(cls, node: HTMLNode, ctx: RecursionContext) -> GCMessage:
        if node.tag == "ol":
            return super().list_to_fstring(node, ctx)
        tagged_children = cls.node_to_tagged_fstrings(node, ctx)
        children = []
        for child, tag in tagged_children:
            if tag != "li":
                continue
            children.append(child.format(GCEntityType.LIST_ITEM))
        return cls.fs.join(children, "\n").format(GCEntityType.LIST)

    @classmethod
    def header_to_fstring(cls, node: HTMLNode, ctx: RecursionContext) -> GCMessage:
        children = cls.node_to_fstrings(node, ctx)
        length = int(node.tag[1])
        prefix = "#" * length + " "
        return GCMessage.join(children, "").prepend(prefix).format(GCEntityType.BOLD)

    @classmethod
    def blockquote_to_fstring(cls, node: HTMLNode, ctx: RecursionContext) -> GCMessage:
        msg = cls.tag_aware_parse_node(node, ctx)
        children = msg.trim().split("\n")
        children = [child.prepend("> ") for child in children]
        return GCMessage.join(children, "\n")
