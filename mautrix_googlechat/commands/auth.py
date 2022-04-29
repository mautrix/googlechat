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
import textwrap

from maugclib.auth import GoogleAuthError, TokenManager
from mautrix.bridge.commands import HelpSection, command_handler
from mautrix.errors import MForbidden
from mautrix.types import EventID

from .. import puppet as pu, user as u
from ..web.auth import make_login_url
from .typehint import CommandEvent

SECTION_AUTH = HelpSection("Authentication", 10, "")


@command_handler(
    needs_auth=False,
    management_only=True,
    help_section=SECTION_AUTH,
    help_text="Log in to Google Chat",
)
async def login(evt: CommandEvent) -> EventID:
    direct_login_url = make_login_url(evt.config["hangouts.device_name"])
    instructions = f"""
        1. Open [this link]({direct_login_url}) in your browser.
        2. Log into your Google account normally.
        3. When you reach the loading screen after logging in that says *"One moment please..."*,
           press `F12` to open developer tools.
        4. Select the "Application" (Chrome) or "Storage" (Firefox) tab.
        5. In the sidebar, expand "Cookies" and select `https://accounts.google.com`.
        6. In the cookie list, find the `oauth_code` row and double-click on the value,
           then copy the value and send it here.
    """
    evt.sender.command_status = {
        "action": "Login",
        "room_id": evt.room_id,
        "next": enter_oauth_code,
    }
    return await evt.reply(textwrap.dedent(instructions.lstrip("\n").rstrip()))


async def enter_oauth_code(evt: CommandEvent) -> EventID:
    if len(evt.args) == 0:
        return await evt.reply(
            "Please enter the value of the `oauth_code` cookie, "
            "or use the `cancel` command to cancel."
        )

    try:
        await evt.az.intent.redact(evt.room_id, evt.event_id)
    except MForbidden as e:
        evt.log.warning(f"Failed to redact OAuth token during login: {e}")

    try:
        token_mgr = await TokenManager.from_authorization_code(
            evt.args[0], u.UserRefreshTokenCache(evt.sender)
        )
    except GoogleAuthError as e:
        evt.log.exception(f"Login for {evt.sender.mxid} failed")
        return await evt.reply(f"Failed to log in: {e}")
    except Exception:
        evt.log.exception(f"Login for {evt.sender.mxid} errored")
        return await evt.reply("Unknown error logging in (see logs for more details)")
    else:
        evt.sender.login_complete(token_mgr)
        await evt.sender.name_future
        return await evt.reply(
            f"Successfully logged in as {evt.sender.name} &lt;{evt.sender.email}&gt; "
            f"({evt.sender.gcid})"
        )


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
