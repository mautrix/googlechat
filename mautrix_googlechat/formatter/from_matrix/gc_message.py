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
from typing import Any, Dict, List, Optional, Union
from enum import Enum, auto

from maugclib import googlechat_pb2 as googlechat
from mautrix.util.formatter import EntityString, SemiAbstractEntity


class GCFormatType(Enum):
    BOLD = googlechat.FormatMetadata.BOLD
    ITALIC = googlechat.FormatMetadata.ITALIC
    STRIKE = googlechat.FormatMetadata.STRIKE
    SOURCE_CODE = googlechat.FormatMetadata.SOURCE_CODE
    MONOSPACE = googlechat.FormatMetadata.MONOSPACE
    HIDDEN = googlechat.FormatMetadata.HIDDEN
    MONOSPACE_BLOCK = googlechat.FormatMetadata.MONOSPACE_BLOCK
    UNDERLINE = googlechat.FormatMetadata.UNDERLINE
    FONT_COLOR = googlechat.FormatMetadata.FONT_COLOR
    BULLETED_LIST = googlechat.FormatMetadata.BULLETED_LIST
    BULLETED_LIST_ITEM = googlechat.FormatMetadata.BULLETED_LIST_ITEM
    CLIENT_HIDDEN = googlechat.FormatMetadata.CLIENT_HIDDEN


class GCUserMentionType(Enum):
    INVITE = googlechat.UserMentionMetadata.INVITE
    UNINVITE = googlechat.UserMentionMetadata.UNINVITE
    MENTION = googlechat.UserMentionMetadata.MENTION
    MENTION_ALL = googlechat.UserMentionMetadata.MENTION_ALL
    FAILED_TO_ADD = googlechat.UserMentionMetadata.FAILED_TO_ADD


class GCEntityType(Enum):
    """EntityType is a Matrix formatting entity type."""

    BOLD = GCFormatType.BOLD
    ITALIC = GCFormatType.ITALIC
    STRIKETHROUGH = GCFormatType.STRIKE
    UNDERLINE = GCFormatType.UNDERLINE
    URL = auto()
    EMAIL = auto()
    USER_MENTION = GCUserMentionType.MENTION
    PREFORMATTED = GCFormatType.MONOSPACE_BLOCK
    INLINE_CODE = GCFormatType.MONOSPACE
    COLOR = GCFormatType.FONT_COLOR

    # Google Chat specific types, not present in mautrix-python's EntityType
    LIST = GCFormatType.BULLETED_LIST
    LIST_ITEM = GCFormatType.BULLETED_LIST_ITEM
    HIDDEN = GCFormatType.HIDDEN


class GCEntity(SemiAbstractEntity):
    internal: googlechat.Annotation
    type: GCEntityType

    def __init__(
        self,
        type: Union[GCEntityType, GCFormatType, GCUserMentionType],
        offset: int,
        length: int,
        extra_info: Dict[str, Any],
    ) -> None:
        if isinstance(type, GCEntityType):
            gc_type = type.value
            self.type = type
        else:
            gc_type = type
            self.type = GCEntityType(type)
        if isinstance(gc_type, GCFormatType):
            self.internal = googlechat.Annotation(
                type=googlechat.FORMAT_DATA,
                chip_render_type=googlechat.Annotation.DO_NOT_RENDER,
                start_index=offset,
                length=length,
                format_metadata=googlechat.FormatMetadata(
                    format_type=gc_type.value,
                    font_color=extra_info.get("font_color"),
                ),
            )
        elif isinstance(gc_type, GCUserMentionType):
            self.internal = googlechat.Annotation(
                type=googlechat.USER_MENTION,
                chip_render_type=googlechat.Annotation.DO_NOT_RENDER,
                start_index=offset,
                length=length,
                user_mention_metadata=googlechat.UserMentionMetadata(
                    type=gc_type.value,
                    id=googlechat.UserId(id=extra_info["user_id"]),
                    display_name=extra_info.get("displayname"),
                ),
            )
        elif self.type == GCEntityType.URL:
            self.internal = googlechat.Annotation(
                type=googlechat.URL,
                chip_render_type=googlechat.Annotation.DO_NOT_RENDER,
                start_index=offset,
                length=length,
                url_metadata=googlechat.UrlMetadata(
                    url=googlechat.Url(url=extra_info["url"]),
                ),
            )
        else:
            raise ValueError(f"Can't create Entity with unknown entity type {type}")

    def copy(self) -> Optional["GCEntity"]:
        extra_info = {}
        if self.type == GCEntityType.COLOR:
            extra_info["font_color"] = self.internal.format_metadata.font_color
        elif self.type == GCEntityType.USER_MENTION:
            extra_info["user_id"] = self.internal.user_mention_metadata.id.id
            extra_info["displayname"] = self.internal.user_mention_metadata.display_name
        elif self.type == GCEntityType.URL:
            extra_info["url"] = self.internal.url_metadata.url.url
        return GCEntity(self.type, offset=self.offset, length=self.length, extra_info=extra_info)

    def __repr__(self) -> str:
        return str(self.internal)

    @property
    def offset(self) -> int:
        return self.internal.start_index

    @offset.setter
    def offset(self, value: int) -> None:
        self.internal.start_index = value

    @property
    def length(self) -> int:
        return self.internal.length

    @length.setter
    def length(self, value: int) -> None:
        self.internal.length = value


class GCMessage(EntityString[GCEntity, GCEntityType]):
    entity_class = GCEntity

    @property
    def googlechat_entities(self) -> List[googlechat.Annotation]:
        return [
            entity.internal
            for entity in self.entities
            if entity.internal.type != googlechat.ANNOTATION_TYPE_UNKNOWN
        ]
