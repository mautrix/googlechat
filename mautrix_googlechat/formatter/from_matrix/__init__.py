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
from mautrix.types import Format, TextMessageEventContent

from ..util import FormatError, add_surrogate, del_surrogate
from .parser import parse_html


async def matrix_to_googlechat(
    content: TextMessageEventContent,
) -> tuple[str, list[googlechat.Annotation] | None]:
    if content.format != Format.HTML or not content.formatted_body:
        return content.body, None
    try:
        text, entities = await parse_html(add_surrogate(content.formatted_body))
        return del_surrogate(text), entities
    except Exception as e:
        raise FormatError(f"Failed to convert Matrix format") from e


__all__ = ["matrix_to_googlechat"]
