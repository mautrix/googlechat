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
from mautrix.bridge import Bridge
from mautrix.types import RoomID, UserID
from mautrix.bridge.state_store.asyncpg import PgBridgeStateStore
from mautrix.util.async_db import Database

from .config import Config
from .db import init as init_db, upgrade_table
from .user import User
from .portal import Portal
from .puppet import Puppet
from .matrix import MatrixHandler
from .web import GoogleChatAuthServer
from .version import version, linkified_version
from . import commands as _


class GoogleChatBridge(Bridge):
    name = "mautrix-googlechat"
    module = "mautrix_googlechat"
    command = "python -m mautrix-googlechat"
    description = "A Matrix-Google Chat puppeting bridge."
    repo_url = "https://github.com/mautrix/googlechat"
    real_user_content_key = "net.maunium.googlechat.puppet"
    version = version
    markdown_version = linkified_version
    config_class = Config
    matrix_class = MatrixHandler

    db: Database
    config: Config
    matrix: MatrixHandler
    auth_server: GoogleChatAuthServer
    state_store: PgBridgeStateStore

    def make_state_store(self) -> None:
        self.state_store = PgBridgeStateStore(self.db, self.get_puppet, self.get_double_puppet)

    def prepare_db(self) -> None:
        self.db = Database(self.config["appservice.database"], upgrade_table=upgrade_table,
                           loop=self.loop, db_args=self.config["appservice.database_opts"])
        init_db(self.db)

    def prepare_bridge(self) -> None:
        super().prepare_bridge()
        self.auth_server = GoogleChatAuthServer(self.config["bridge.web.auth.shared_secret"],
                                                self.config["hangouts.device_name"], self.loop)
        self.az.app.add_subapp(self.config["bridge.web.auth.prefix"], self.auth_server.app)

    async def resend_bridge_info(self) -> None:
        self.config["bridge.resend_bridge_info"] = False
        self.config.save()
        self.log.info("Re-sending bridge info state event to all portals")
        async for portal in Portal.all():
            await portal.update_bridge_info()
        self.log.info("Finished re-sending bridge info state events")

    def prepare_stop(self) -> None:
        self.shutdown_actions = (user.stop() for user in User.by_mxid.values())
        self.log.debug("Stopping puppet syncers")
        for puppet in Puppet.by_custom_mxid.values():
            puppet.stop()

    async def stop(self) -> None:
        await super().stop()
        self.log.debug("Saving user sessions")
        for user in User.by_mxid.values():
            await user.save()

    async def start(self) -> None:
        await self.db.start()
        await self.state_store.upgrade_table.upgrade(self.db.pool)
        if self.matrix.e2ee:
            self.matrix.e2ee.crypto_db.override_pool(self.db.pool)
        self.add_startup_actions(User.init_cls(self))
        self.add_startup_actions(Puppet.init_cls(self))
        Portal.init_cls(self)
        if self.config["bridge.resend_bridge_info"]:
            self.add_startup_actions(self.resend_bridge_info())
        await super().start()

    async def get_portal(self, room_id: RoomID) -> Portal:
        return await Portal.get_by_mxid(room_id)

    async def get_puppet(self, user_id: UserID, create: bool = False) -> Puppet:
        return await Puppet.get_by_mxid(user_id, create=create)

    async def get_double_puppet(self, user_id: UserID) -> Puppet:
        return await Puppet.get_by_custom_mxid(user_id)

    async def get_user(self, user_id: UserID, create: bool = True) -> User:
        return await User.get_by_mxid(user_id, create=create)

    def is_bridge_ghost(self, user_id: UserID) -> bool:
        return bool(Puppet.get_id_from_mxid(user_id))

    async def count_logged_in_users(self) -> int:
        return len([user for user in User.by_mxid.values() if user.gcid])


GoogleChatBridge().run()
