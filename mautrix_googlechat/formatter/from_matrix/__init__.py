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

import html
import logging

from maugclib import googlechat_pb2 as googlechat
from mautrix.types import Format, TextMessageEventContent, UserID

from ... import puppet as pu
from ..util import FormatError, add_surrogate, del_surrogate
from .gc_message import GCEntity, GCEntityType
from .parser import MX_ROOM_MENTION, parse_html

log = logging.getLogger("mau.fmt.matrix")


async def _annotations_from_m_mentions(
    body: str,
    mentions: dict,
) -> list[googlechat.Annotation] | None:
    """Build USER_MENTION annotations from MSC3952 m.mentions when formatted_body is absent."""
    user_ids = mentions.get("user_ids")
    if not user_ids:
        return None
    annotations = []
    for mxid in user_ids:
        gcid = pu.Puppet.get_id_from_mxid(UserID(mxid))
        if not gcid:
            continue
        puppet = await pu.Puppet.get_by_gcid(gcid, create=False)
        display_name = puppet.name if puppet else None
        # Find the mention text in the body. Clients typically render as @DisplayName.
        offset = -1
        if display_name:
            mention_text = f"@{display_name}"
            offset = body.find(mention_text)
            if offset == -1:
                # Try without @ prefix in case the body has a different format
                offset = body.find(display_name)
        if offset == -1:
            # Display name not found in body — skip this mention rather than
            # inject an annotation with wrong offsets.
            log.debug(
                "Skipping m.mentions entry %s: display name %r not found in body",
                mxid,
                display_name,
            )
            continue
        length = (
            len(mention_text)
            if display_name and body[offset:].startswith(f"@{display_name}")
            else len(display_name or "")
        )
        entity = GCEntity(
            type=GCEntityType.USER_MENTION,
            offset=offset,
            length=length,
            extra_info={"user_id": gcid, "displayname": display_name},
        )
        annotations.append(entity.internal)
    return annotations or None


async def matrix_to_googlechat(
    content: TextMessageEventContent,
) -> tuple[str, list[googlechat.Annotation] | None]:
    if content.format != Format.HTML or not content.formatted_body:
        if MX_ROOM_MENTION in content.body:
            content.formatted_body = html.escape(content.body)
        else:
            # No HTML — fall back to m.mentions (MSC3952) for mention annotations.
            mentions = content.get("m.mentions", {})
            if mentions:
                annotations = await _annotations_from_m_mentions(content.body, mentions)
                return content.body, annotations
            return content.body, None
    try:
        text, entities = await parse_html(add_surrogate(content.formatted_body))
        return del_surrogate(text), entities
    except Exception as e:
        raise FormatError(f"Failed to convert Matrix format") from e


__all__ = ["matrix_to_googlechat"]
