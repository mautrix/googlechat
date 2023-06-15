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
from __future__ import annotations

from typing import Any
import asyncio
import logging

from aiohttp import web

from maugclib import Cookies
from maugclib.exceptions import NotLoggedInError, ResponseError
from mautrix.types import UserID

from .. import user as u


class ErrorResponse(Exception):
    def __init__(
        self,
        status_code: int,
        error: str,
        errcode: str,
        extra_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.message = error
        self.error = error
        self.errcode = errcode
        self.payload = {**(extra_data or {}), "error": self.error, "errcode": self.errcode}


@web.middleware
async def error_middleware(request: web.Request, handler) -> web.Response:
    try:
        return await handler(request)
    except ErrorResponse as e:
        return web.json_response(status=e.status_code, data=e.payload)


log = logging.getLogger("mau.gc.auth")

LOGIN_TIMEOUT = 10 * 60


class GoogleChatAuthServer:
    app: web.Application
    shared_secret: str | None

    def __init__(self, shared_secret: str | None) -> None:
        self.ongoing = {}
        self.shared_secret = shared_secret

        self.app = web.Application(middlewares=[error_middleware])
        self.app.router.add_get("/v1/whoami", self.whoami)
        self.app.router.add_post("/v1/login", self.login)
        self.app.router.add_post("/v1/logout", self.logout)
        self.app.router.add_post("/v1/reconnect", self.reconnect)

        self.legacy_app = web.Application(middlewares=[error_middleware])
        self.legacy_app.router.add_post("/api/verify", self.verify)
        self.legacy_app.router.add_post("/api/logout", self.logout)
        self.legacy_app.router.add_post("/api/authorization", self.login)
        self.legacy_app.router.add_post("/api/reconnect", self.reconnect)
        self.legacy_app.router.add_get("/api/whoami", self.whoami)

    def verify_token(self, request: web.Request) -> UserID | None:
        try:
            token = request.headers["Authorization"]
        except KeyError:
            raise ErrorResponse(401, "Missing access token", "M_MISSING_TOKEN")
        if not token.startswith("Bearer "):
            raise ErrorResponse(401, "Invalid authorization header content", "M_MISSING_TOKEN")
        token = token[len("Bearer ") :]
        if not self.shared_secret or token != self.shared_secret:
            raise ErrorResponse(401, "Invalid access token", "M_UNKNOWN_TOKEN")
        try:
            return UserID(request.query["user_id"])
        except KeyError:
            raise ErrorResponse(400, "Missing user_id query parameter", "M_MISSING_PARAM")

    async def verify(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "user_id": self.verify_token(request),
            }
        )

    async def logout(self, request: web.Request) -> web.Response:
        user_id = self.verify_token(request)
        user = await u.User.get_by_mxid(user_id)
        await user.logout(is_manual=True)
        return web.json_response({})

    async def whoami(self, request: web.Request) -> web.Response:
        user_id = self.verify_token(request)
        user = await u.User.get_by_mxid(user_id)
        return web.json_response(
            {
                "permissions": user.level,
                "mxid": user.mxid,
                "googlechat": {
                    "name": user.name,
                    "email": user.email,
                    "id": user.gcid,
                    "connected": user.connected,
                }
                if user.client
                else None,
            }
        )

    async def reconnect(self, request: web.Request) -> web.Response:
        user_id = self.verify_token(request)
        user = await u.User.get_by_mxid(user_id)
        user.reconnect()
        return web.json_response({})

    async def login(self, request: web.Request) -> web.Response:
        user_id = self.verify_token(request)
        user = await u.User.get_by_mxid(user_id)
        if user.client:
            await user.name_future
            return web.json_response(
                {
                    "status": "success",
                    "name": user.name,
                    "email": user.email,
                }
            )
        data = await request.json()
        if not data:
            raise ErrorResponse(400, "Body is not JSON", "M_NOT_JSON")
        try:
            cookies = Cookies(**{k.lower(): v for k, v in data["cookies"].items()})
        except TypeError:
            raise ErrorResponse(
                400, "Request body did not contain the required fields", "M_BAD_REQUEST"
            )
        user.user_agent = data.get("user_agent", None)

        user.log.debug("Trying to log in with cookies")
        try:
            if not await user.connect(cookies, get_self=True):
                return web.json_response(
                    {
                        "status": "fail",
                        "error": "Failed to get own info after login",
                    }
                )
        except (ResponseError, NotLoggedInError) as e:
            log.exception(f"Login for {user.mxid} failed")
            return web.json_response(
                {
                    "status": "fail",
                    "error": str(e),
                }
            )
        except Exception:
            log.exception(f"Login for {user.mxid} errored")
            return web.json_response(
                {
                    "status": "fail",
                    "error": "internal error",
                },
                status=500,
            )
        else:
            await asyncio.wait_for(asyncio.shield(user.name_future), 20)
            return web.json_response(
                {
                    "status": "success",
                    "name": user.name,
                    "email": user.email,
                }
            )
