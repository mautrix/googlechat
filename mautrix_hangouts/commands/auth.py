# mautrix-hangouts - A Matrix-Hangouts puppeting bridge
# Copyright (C) 2020 Tulir Asokan
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
from mautrix.client import Client
from mautrix.bridge import custom_puppet as cpu

from hangups import hangouts_pb2 as hangouts

from .. import puppet as pu
from . import command_handler, CommandEvent, SECTION_AUTH


@command_handler(needs_auth=False, management_only=True,
                 help_section=SECTION_AUTH, help_text="Log in to Hangouts")
async def login(evt: CommandEvent) -> None:
    token = evt.processor.context.auth_server.make_token(evt.sender.mxid)
    public_prefix = evt.config["bridge.web.auth.public"]
    url = f"{public_prefix}#{token}"
    await evt.reply(f"Please visit the [login portal]({url}) to log in.")


@command_handler(needs_auth=True, management_only=True, help_args="<_access token_>",
                 help_section=SECTION_AUTH, help_text="Replace your Hangouts account's Matrix "
                                                      "puppet with your Matrix account")
async def login_matrix(evt: CommandEvent) -> None:
    puppet = pu.Puppet.get_by_gid(evt.sender.gid)
    _, homeserver = Client.parse_mxid(evt.sender.mxid)
    if homeserver != pu.Puppet.hs_domain:
        await evt.reply("You can't log in with an account on a different homeserver")
        return
    try:
        await puppet.switch_mxid(" ".join(evt.args), evt.sender.mxid)
        await evt.reply("Successfully replaced your Hangouts account's "
                        "Matrix puppet with your Matrix account.")
    except cpu.OnlyLoginSelf:
        await evt.reply("You may only log in with your own Matrix account")
    except cpu.InvalidAccessToken:
        await evt.reply("Invalid access token")


@command_handler(needs_auth=True, management_only=True, help_section=SECTION_AUTH)
async def logout(evt: CommandEvent) -> None:
    puppet = pu.Puppet.get_by_gid(evt.sender.gid)
    await evt.sender.logout()
    if puppet and puppet.is_real_user:
        await puppet.switch_mxid(None, None)


@command_handler(needs_auth=True, management_only=True, help_section=SECTION_AUTH)
async def ping(evt: CommandEvent) -> None:
    try:
        info = await evt.sender.client.get_self_info(hangouts.GetSelfInfoRequest(
            request_header=evt.sender.client.get_request_header()
        ))
    except Exception as e:
        evt.log.exception("Failed to get user info", exc_info=True)
        await evt.reply(f"Failed to get user info: {e}")
        return
    name = info.self_entity.properties.display_name
    email = (f" &lt;{info.self_entity.properties.email[0]}&gt;"
             if info.self_entity.properties.email else "")
    id = info.self_entity.id.gaia_id
    await evt.reply(f"You're logged in as {name}{email} ({id})", allow_html=False)


@command_handler(needs_auth=True, management_only=True, help_section=SECTION_AUTH)
async def logout_matrix(evt: CommandEvent) -> None:
    puppet = pu.Puppet.get_by_gid(evt.sender.gid)
    if not puppet.is_real_user:
        await evt.reply("You're not logged in with your Matrix account")
        return
    await puppet.switch_mxid(None, None)
    await evt.reply("Restored the original puppet for your Hangouts account")


@command_handler(needs_auth=False, management_only=True, help_section=SECTION_AUTH,
                 help_text="Mark this room as your bridge notice room")
async def set_notice_room(evt: CommandEvent) -> None:
    evt.sender.notice_room = evt.room_id
    evt.sender.save()
    await evt.reply("This room has been marked as your bridge notice room")
