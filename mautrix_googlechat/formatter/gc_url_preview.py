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

from typing import Any

from yarl import URL
import aiohttp

from maugclib import googlechat_pb2 as googlechat

from .. import portal as po, user as u

try:
    from mautrix.crypto.attachments import encrypt_attachment
except ImportError:
    decrypt_attachment = encrypt_attachment = None

_upload_cache: dict[str, dict] = {}
DRIVE_OPEN_URL = URL("https://drive.google.com/open")
DRIVE_THUMBNAIL_URL = URL("https://drive.google.com/thumbnail")
# Alternate URL: https://lh3.google.com/d/{id}=w{width}


async def _reupload_preview(source: u.User | None, url: str, encrypt: bool) -> dict:
    try:
        return _upload_cache[url]
    except KeyError:
        pass

    max_size = po.Portal.matrix.media_config.upload_size
    bot = po.Portal.bridge.az.intent

    try:
        data, mime, _ = await source.client.download_attachment(url, max_size=max_size)
    except aiohttp.ClientError:
        return {}
    output = {
        "og:image:type": mime,
        "matrix:image:size": len(data),
    }
    file = None
    if encrypt:
        data, file = encrypt_attachment(data)
        output["beeper:image:encryption"] = file.serialize()
        mime = "application/octet-stream"
    mxc = await bot.upload_media(data, mime_type=mime)
    if file:
        output["beeper:image:encryption"]["url"] = mxc
    else:
        output["og:image"] = mxc
    _upload_cache[url] = output
    return output


def _has_matching_drive_annotation(annotations: list[googlechat.Annotation], url: str) -> bool:
    for ann in annotations:
        if ann.drive_metadata.id and ann.drive_metadata.id in url:
            return True
    return False


async def gc_previews_to_beeper(
    source: u.User,
    text: str,
    annotations: list[googlechat.Annotation],
    encrypt: bool = False,
) -> list[dict[str, Any]]:
    url_previews = []
    for ann in annotations:
        if ann.url_metadata.should_not_render:
            continue
        matched_url = text[ann.start_index : ann.start_index + ann.length]
        if (
            ann.HasField("url_metadata")
            and ann.url_metadata.title
            and not _has_matching_drive_annotation(annotations, ann.url_metadata.url.url)
        ):
            preview = await gc_url_to_beeper(source, matched_url, ann.url_metadata, encrypt)
        elif ann.HasField("drive_metadata") and ann.drive_metadata.title:
            preview = await gc_drive_to_beeper(source, matched_url, ann.drive_metadata, encrypt)
        else:
            continue
        url_previews.append({k: v for k, v in preview.items() if v})
    return url_previews


async def gc_url_to_beeper(
    source: u.User, matched_url: str, meta: googlechat.UrlMetadata, encrypt: bool
) -> dict[str, Any]:
    preview = {
        "matched_url": matched_url,
        "og:url": meta.url.url,
        "og:title": meta.title,
        "og:description": meta.snippet,
    }
    if meta.image_url:
        preview.update(await _reupload_preview(source, meta.image_url, encrypt))
        preview["og:image:width"] = meta.int_image_width
        preview["og:image:height"] = meta.int_image_height
    return preview


async def gc_drive_to_beeper(
    source: u.User, matched_url: str, meta: googlechat.DriveMetadata, encrypt: bool
) -> dict[str, Any]:
    open_url = str(DRIVE_OPEN_URL.with_query({"id": meta.id}))
    preview = {
        "matched_url": matched_url or open_url,
        "og:url": open_url,
        "og:title": meta.title,
    }
    if meta.thumbnail_width:
        if not meta.thumbnail_url:
            meta.thumbnail_url = str(
                DRIVE_THUMBNAIL_URL.with_query(
                    {
                        "sz": f"w{meta.thumbnail_width}",
                        "id": meta.id,
                    }
                )
            )
        preview.update(await _reupload_preview(source, meta.thumbnail_url, encrypt))
        preview["og:image:width"] = meta.thumbnail_width
        preview["og:image:height"] = meta.thumbnail_height
    return preview
