# mautrix-googlechat - A Matrix-Google Chat puppeting bridge
# Copyright (C) 2023 Tulir Asokan
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
import json

from maugclib import Cookies, NotLoggedInError
from mautrix.bridge.commands import HelpSection, command_handler
from mautrix.errors import MForbidden
from mautrix.types import EventID

from .. import puppet as pu
from .typehint import CommandEvent

SECTION_AUTH = HelpSection("Authentication", 10, "")


@command_handler(
    needs_auth=True,
    management_only=True,
    help_section=SECTION_AUTH,
    help_text="Log out from Google Chat",
)
async def logout(evt: CommandEvent) -> None:
    puppet = await pu.Puppet.get_by_gcid(evt.sender.gcid)
    await evt.sender.logout(is_manual=True)
    if puppet and puppet.is_real_user:
        await puppet.switch_mxid(None, None)
    await evt.reply("Successfully logged out")


@command_handler(
    needs_auth=True,
    management_only=True,
    help_section=SECTION_AUTH,
    help_text="Check if you're logged into Google Chat",
)
async def ping(evt: CommandEvent) -> None:
    try:
        self_info = await evt.sender.get_self()
    except Exception as e:
        evt.log.exception("Failed to get user info", exc_info=True)
        await evt.reply(f"Failed to get user info: {e}")
        return
    name = self_info.name
    email = f" &lt;{self_info.email}&gt;" if self_info.email else ""
    id = self_info.user_id.id
    await evt.reply(f"You're logged in as {name}{email} ({id})", allow_html=False)


@command_handler(
    needs_auth=False,
    management_only=True,
    help_section=SECTION_AUTH,
    help_text="Mark this room as your bridge notice room",
)
async def set_notice_room(evt: CommandEvent) -> None:
    evt.sender.notice_room = evt.room_id
    await evt.sender.save()
    await evt.reply("This room has been marked as your bridge notice room")


@command_handler(
    needs_auth=False,
    management_only=True,
    help_section=SECTION_AUTH,
    help_text=(
        "Set the cookies required for auth. See https://docs.mau.fi/bridges/python/googlechat/authentication.html for instructions"
    ),
)
async def login_cookie(evt: CommandEvent) -> EventID:
    if len(evt.args) == 0:
        return await evt.reply("Please enter a JSON object with the cookies.")

    try:
        await evt.az.intent.redact(evt.room_id, evt.event_id)
    except MForbidden as e:
        evt.log.warning(f"Failed to redact cookies during login: {e}")

    try:
        data = json.loads(" ".join(evt.args))
    except Exception as e:
        return await evt.reply(f"Invalid JSON: {e}")

    try:
        await evt.sender.connect(Cookies(**{k.lower(): v for k, v in data.items()}))
    except NotLoggedInError:
        return await evt.reply("Those cookies don't seem to be valid")
    await evt.sender.name_future
    return await evt.reply(
        f"Successfully logged in as {evt.sender.name} &lt;{evt.sender.email}&gt; "
        f"({evt.sender.gcid})"
    )
