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

from html import escape

from maugclib import googlechat_pb2 as googlechat
from mautrix.types import Format, MessageType, TextMessageEventContent

from .. import puppet as pu, user as u
from .gc_url_preview import gc_previews_to_beeper
from .util import FormatError, add_surrogate, del_surrogate


async def googlechat_to_matrix(
    source: u.User, evt: googlechat.Message, encrypt: bool = False
) -> TextMessageEventContent:
    content = TextMessageEventContent(
        msgtype=MessageType.TEXT,
        body=add_surrogate(evt.text_body),
    )
    content["com.beeper.linkpreviews"] = await gc_previews_to_beeper(
        source, content.body, evt.annotations or [], encrypt=encrypt
    )
    if annotations:
        content.format = Format.HTML
        content.formatted_body = await _gc_annotations_to_matrix_catch(
            content.body, evt.annotations
        )

    content.body = del_surrogate(content.body)

    if content.formatted_body:
        content.formatted_body = del_surrogate(content.formatted_body.replace("\n", "<br/>"))

    return content


async def _gc_annotations_to_matrix_catch(
    text: str, annotations: list[googlechat.Annotation]
) -> str:
    try:
        return await _gc_annotations_to_matrix(text, annotations)
    except Exception as e:
        raise FormatError("Failed to convert Google Chat format") from e


def _annotation_key(item: googlechat.Annotation) -> tuple[int, int, int]:
    # Lowest offset sorts first
    offset_key = item.start_index
    type_key = 2
    # Bulleted lists sort before bulleted list items and those sort before other things
    if item.format_metadata.format_type == googlechat.FormatMetadata.BULLETED_LIST_ITEM:
        type_key = 1
    if item.format_metadata.format_type == googlechat.FormatMetadata.BULLETED_LIST:
        type_key = 0
    # Finally sort highest length first
    length_key = -item.length
    return offset_key, type_key, length_key


# Make sure annotations nested inside other annotations end before the next annotation starts
def _normalize_annotations(
    annotations: list[googlechat.Annotation],
) -> list[googlechat.Annotation]:
    i = 0
    insert_annotations = []
    # We want to sort so lowest index comes first and highest length with same index comes first
    annotations = sorted(annotations, key=lambda item: (item.start_index, -item.length))
    while i < len(annotations):
        cur = annotations[i]
        end = cur.start_index + cur.length
        for i2, annotation in enumerate(annotations[i + 1 :]):
            if annotation.start_index >= end:
                # Annotation is after current one, no need to modify it,
                # just insert the split-up annotations here and move on to the next one.
                i += 1 + i2
                annotations[i:i] = insert_annotations
                insert_annotations = []
                break
            elif annotation.start_index + annotation.length > end:
                # The annotation continues past this one, so split it into two
                annotation_copy = googlechat.Annotation()
                annotation_copy.CopyFrom(annotation)
                annotation.length = end - annotation.start_index
                annotation_copy.start_index += annotation.length
                annotation_copy.length -= annotation.length
                insert_annotations.append(annotation_copy)
        else:
            i += 1
    annotations[i:i] = insert_annotations
    return annotations


async def _gc_annotations_to_matrix(
    text: str, annotations: list[googlechat.Annotation], offset: int = 0, length: int = None
) -> str:
    if not annotations:
        return escape(text)
    if length is None:
        length = len(text)
    html = []
    last_offset = 0
    annotations = _normalize_annotations(annotations)
    for i, annotation in enumerate(annotations):
        if annotation.start_index >= offset + length:
            break
        elif annotation.chip_render_type != googlechat.Annotation.DO_NOT_RENDER:
            # Annotations with the "RENDER" type are rendered separately, so they're not formatting
            continue
        # Overlapping annotations should be removed by _normalize_annotations
        assert annotation.start_index + annotation.length <= offset + length
        relative_offset = annotation.start_index - offset
        if relative_offset > last_offset:
            html.append(escape(text[last_offset:relative_offset]))
        elif relative_offset < last_offset:
            continue

        skip_entity = False
        entity_text = await _gc_annotations_to_matrix(
            text=text[relative_offset : relative_offset + annotation.length],
            annotations=annotations[i + 1 :],
            offset=annotation.start_index,
            length=annotation.length,
        )

        if annotation.HasField("format_metadata"):
            type = annotation.format_metadata.format_type
            if type == googlechat.FormatMetadata.HIDDEN:
                # Don't append the text
                pass
            elif type == googlechat.FormatMetadata.BOLD:
                html.append(f"<strong>{entity_text}</strong>")
            elif type == googlechat.FormatMetadata.ITALIC:
                html.append(f"<em>{entity_text}</em>")
            elif type == googlechat.FormatMetadata.UNDERLINE:
                html.append(f"<u>{entity_text}</u>")
            elif type == googlechat.FormatMetadata.STRIKE:
                html.append(f"<del>{entity_text}</del>")
            elif type == googlechat.FormatMetadata.MONOSPACE:
                html.append(f"<code>{entity_text}</code>")
            elif type == googlechat.FormatMetadata.MONOSPACE_BLOCK:
                html.append(f"<pre><code>{entity_text}</code></pre>")
            elif type == googlechat.FormatMetadata.FONT_COLOR:
                rgb_int = annotation.format_metadata.font_color
                color = (rgb_int + 2**31) & 0xFFFFFF
                html.append(f"<font color='#{color:x}'>{entity_text}</font>")
            elif type == googlechat.FormatMetadata.BULLETED_LIST_ITEM:
                html.append(f"<li>{entity_text}</li>")
            elif type == googlechat.FormatMetadata.BULLETED_LIST:
                html.append(f"<ul>{entity_text}</ul>")
            else:
                skip_entity = True
        elif annotation.HasField("url_metadata"):
            html.append(f"<a href='{annotation.url_metadata.url.url}'>{entity_text}</a>")
        elif annotation.HasField("user_mention_metadata"):
            gcid = annotation.user_mention_metadata.id.id
            user = await u.User.get_by_gcid(gcid)
            mxid = user.mxid if user else pu.Puppet.get_mxid_from_id(gcid)
            html.append(f"<a href='https://matrix.to/#/{mxid}'>{entity_text}</a>")
        else:
            skip_entity = True
        last_offset = relative_offset + (0 if skip_entity else annotation.length)
    html.append(escape(text[last_offset:]))

    return "".join(html)
