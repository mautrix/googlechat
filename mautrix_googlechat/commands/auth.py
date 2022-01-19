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
from mautrix.bridge.commands import HelpSection, command_handler

from .. import puppet as pu
from .typehint import CommandEvent

SECTION_AUTH = HelpSection("Authentication", 10, "")


@command_handler(
    needs_auth=False,
    management_only=True,
    help_section=SECTION_AUTH,
    help_text="Log in to Google Chat",
)
async def login(evt: CommandEvent) -> None:
    token = evt.bridge.auth_server.make_token(evt.sender.mxid)
    public_prefix = evt.config["bridge.web.auth.public"]
    url = f"{public_prefix}#{token}"
    await evt.reply(f"Please visit the [login portal]({url}) to log in.")


@command_handler(
    needs_auth=True,
    management_only=True,
    help_section=SECTION_AUTH,
    help_text="Log out from Google Chat",
)
async def logout(evt: CommandEvent) -> None:
    puppet = await pu.Puppet.get_by_gcid(evt.sender.gcid)
    await evt.sender.logout()
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
