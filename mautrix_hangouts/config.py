# mautrix-hangouts - A Matrix-Hangouts puppeting bridge
# Copyright (C) 2019 Tulir Asokan
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
from typing import Dict, Tuple, List, Any

from mautrix.types import UserID
from mautrix.bridge.config import BaseBridgeConfig, ConfigUpdateHelper


class Config(BaseBridgeConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        super().do_update(helper)

        copy, copy_dict, base = helper

        copy("appservice.community_id")

        copy("bridge.username_template")
        copy("bridge.displayname_template")
        copy("bridge.community_template")
        copy("bridge.command_prefix")

        copy("bridge.initial_chat_sync")
        copy("bridge.invite_own_puppet_to_pm")
        copy("bridge.sync_with_custom_puppets")
        copy("bridge.login_shared_secret")
        copy("bridge.update_avatar_initial_sync")
        copy("bridge.encryption.allow")
        copy("bridge.encryption.default")
        copy("bridge.delivery_receipts")

        copy("bridge.web.auth.public")
        copy("bridge.web.auth.prefix")
        if self["bridge.web.auth.shared_secret"] == "generate":
            base["bridge.web.auth.shared_secret"] = self._new_token()
        else:
            copy("bridge.web.auth.shared_secret")

        copy_dict("bridge.permissions")

    def _get_permissions(self, key: str) -> Tuple[bool, bool, str]:
        level = self["bridge.permissions"].get(key, "")
        admin = level == "admin"
        user = level == "user" or admin
        return user, admin, level

    def get_permissions(self, mxid: UserID) -> Tuple[bool, bool, str]:
        permissions = self["bridge.permissions"] or {}
        if mxid in permissions:
            return self._get_permissions(mxid)

        homeserver = mxid[mxid.index(":") + 1:]
        if homeserver in permissions:
            return self._get_permissions(homeserver)

        return self._get_permissions("*")

    @property
    def namespaces(self) -> Dict[str, List[Dict[str, Any]]]:
        homeserver = self["homeserver.domain"]

        username_format = self["bridge.username_template"].lower().format(userid=".+")
        group_id = ({"group_id": self["appservice.community_id"]}
                    if self["appservice.community_id"] else {})

        return {
            "users": [{
                "exclusive": True,
                "regex": f"@{username_format}:{homeserver}",
                **group_id,
            }],
        }
