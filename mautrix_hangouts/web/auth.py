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
from typing import Optional, Dict, Any, Callable
from concurrent import futures
from enum import Enum
from time import time
import urllib.parse
import pkg_resources
import asyncio
import logging
import string
import random

from aiohttp import web

from hangups import CredentialsPrompt, GoogleAuthError, get_auth
from hangups.auth import OAUTH2_CLIENT_ID, OAUTH2_SCOPES
from mautrix.types import UserID
from mautrix.util.signed_token import sign_token, verify_token

from .. import user as u


class ErrorResponse(Exception):
    def __init__(self, status_code: int, error: str, errcode: str,
                 extra_data: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.message = error
        self.error = error
        self.errcode = errcode
        self.payload = {
            **(extra_data or {}),
            "error": self.error,
            "errcode": self.errcode
        }


@web.middleware
async def error_middleware(request: web.Request, handler) -> web.Response:
    try:
        return await handler(request)
    except ErrorResponse as e:
        return web.json_response(status=e.status_code, data=e.payload)


log = logging.getLogger("mau.hg.auth")

LOGIN_TIMEOUT = 10 * 60


def make_login_url(device_name: str) -> str:
    query = urllib.parse.urlencode({
        "scope": "+".join(OAUTH2_SCOPES),
        "client_id": OAUTH2_CLIENT_ID,
        "device_name": device_name,
    }, safe='+')
    return f"https://accounts.google.com/o/oauth2/programmatic_auth?{query}"


class HangoutsAuthServer:
    loop: asyncio.AbstractEventLoop
    app: web.Application
    ongoing: Dict[UserID, 'WebCredentialsPrompt']
    shared_secret: Optional[str]
    secret_key: str
    device_name: str

    def __init__(self, shared_secret: Optional[str], device_name: str,
                 loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self.loop = loop or asyncio.get_event_loop()
        self.app = web.Application(loop=self.loop, middlewares=[error_middleware])
        self.ongoing = {}
        self.device_name = device_name
        self.shared_secret = shared_secret
        self.secret_key = "".join(random.choices(string.ascii_lowercase + string.digits, k=64))
        self.app.router.add_post("/api/verify", self.verify)
        self.app.router.add_post("/api/start", self.start_login)
        self.app.router.add_post("/api/cancel", self.cancel_login)
        self.app.router.add_post("/api/logout", self.logout)
        self.app.router.add_post("/api/{post_type}", self.login_step)
        self.app.router.add_get("/api/whoami", self.whoami)
        self.app.router.add_get("", self.redirect_index)
        self.app.router.add_get("/", self.get_index)
        self.app.router.add_static("/", pkg_resources.resource_filename("mautrix_hangouts",
                                                                        "web/static/"))

    @staticmethod
    async def redirect_index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(pkg_resources.resource_filename("mautrix_hangouts",
                                                                "web/static/login-redirect.html"))

    @staticmethod
    async def get_index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(pkg_resources.resource_filename("mautrix_hangouts",
                                                                "web/static/login.html"))

    def make_token(self, user_id: UserID) -> str:
        return sign_token(self.secret_key, {
            "user_id": user_id,
            "expiry": int(time()) + LOGIN_TIMEOUT,
        })

    def verify_token(self, request: web.Request, allow_expired: bool = False) -> Optional[UserID]:
        try:
            token = request.headers["Authorization"]
        except KeyError:
            raise ErrorResponse(401, "Missing access token", "M_MISSING_TOKEN")
        if not token.startswith("Bearer "):
            raise ErrorResponse(401, "Invalid authorization header content", "M_MISSING_TOKEN")
        token = token[len("Bearer "):]
        if self.shared_secret and token == self.shared_secret:
            try:
                return UserID(request.query["user_id"])
            except KeyError:
                raise ErrorResponse(400, "Missing user_id query parameter", "M_BAD_REQUEST")
        data = verify_token(self.secret_key, token)
        if not data:
            raise ErrorResponse(401, "Invalid access token", "M_UNKNOWN_TOKEN")
        elif not allow_expired and data["expiry"] < int(time()):
            raise ErrorResponse(401, "Access token expired", "M_EXPIRED_TOKEN")
        return data["user_id"]

    async def verify(self, request: web.Request) -> web.Response:
        return web.json_response({
            "user_id": self.verify_token(request),
        })

    async def logout(self, request: web.Request) -> web.Response:
        user_id = self.verify_token(request)
        user = u.User.get_by_mxid(user_id)
        if not await user.is_logged_in():
            raise ErrorResponse(400, "You're not logged in", "M_FORBIDDEN")
        await user.logout()
        return web.json_response({})

    async def whoami(self, request: web.Request) -> web.Response:
        user_id = self.verify_token(request)
        user = u.User.get_by_mxid(user_id)
        return web.json_response({
            "permissions": user.level,
            "mxid": user.mxid,
            "hangouts": {
                "name": user.name,
                "gid": user.gid,
                "connected": user.connected,
            } if user.client else None,
        })

    async def start_login(self, request: web.Request) -> web.Response:
        user_id = self.verify_token(request)
        manual = request.query.get("manual")
        if manual and (manual == "1" or manual.lower() == "true"):
            manual = True
        else:
            manual = False
        user = u.User.get_by_mxid(user_id)
        if user.client:
            return web.json_response({
                "status": "success",
                "name": await user.name_future,
            })
        try:
            return web.json_response(self.ongoing[user.mxid].current_status)
        except KeyError:
            pass
        login = WebCredentialsPrompt(self, user, manual, self.device_name, self.loop)
        self.ongoing[user.mxid] = login
        try:
            return web.json_response(await login.start())
        except asyncio.CancelledError:
            raise ErrorResponse(410, "Login cancelled", "HANGOUTS_LOGIN_CANCELLED")

    async def cancel_login(self, request: web.Request) -> web.Response:
        user_id = self.verify_token(request)
        try:
            login = self.ongoing[user_id]
        except KeyError:
            raise ErrorResponse(404, "No ongoing login", "HANGOUTS_NO_ONGOING_LOGIN")
        login.cancel()
        return web.json_response({
            "status": "cancelled",
        })

    async def login_step(self, request: web.Request) -> web.Response:
        user_id = self.verify_token(request, allow_expired=True)
        try:
            login = self.ongoing[user_id]
        except KeyError:
            raise ErrorResponse(404, "No ongoing login", "HANGOUTS_NO_ONGOING_LOGIN")
        try:
            credential_type = CredentialType(request.match_info["post_type"])
        except (KeyError, ValueError):
            raise ErrorResponse(400, "Unknown credential type", "HANGOUTS_UNKNOWN_CREDENTIAL_TYPE")
        data = await request.json()
        if not data:
            raise ErrorResponse(400, "Body is not JSON", "M_BAD_REQUEST")
        try:
            credential_value = data[credential_type.value]
        except KeyError:
            raise ErrorResponse(400, "Request body did not contain credential", "M_BAD_REQUEST")
        if login.expecting != credential_type:
            raise ErrorResponse(400, ("Unexpected credential type. Expected "
                                      f"{login.expecting.value}, got {credential_type.value}"),
                                "HANGOUTS_UNEXPECTED_CREDENTIAL_TYPE",
                                {"expected": login.expecting.value, "got": credential_type.value})
        try:
            return web.json_response(await login.send_credential(credential_value))
        except asyncio.CancelledError:
            raise ErrorResponse(410, "Login cancelled", "HANGOUTS_LOGIN_CANCELLED")


class CredentialType(Enum):
    AUTHORIZATION = "authorization"
    EMAIL = "email"
    PASSWORD = "password"
    VERIFICATION = "verification"


class SingleItemBidiChannel:
    to_sync: futures.Future
    to_async: futures.Future

    def init(self, do_before_result: Callable[[], None]) -> asyncio.Future:
        self.to_async = futures.Future()
        do_before_result()
        return asyncio.wrap_future(self.to_async)

    async def send_to_sync(self, value: Any, do_before_result: Callable[[], None]) -> Any:
        self.to_async = futures.Future()
        self.to_sync.set_result(value)
        do_before_result()
        return await asyncio.wrap_future(self.to_async)

    def send_to_async(self, value: Any, do_before_result: Callable[[], None]) -> Any:
        self.to_sync = futures.Future()
        self.to_async.set_result(value)
        do_before_result()
        return self.to_sync.result(timeout=LOGIN_TIMEOUT)

    def finish(self, value: Any):
        self.to_async.set_result(value)

    def cancel(self) -> None:
        if self.to_sync:
            self.to_sync.cancel()
        if self.to_async:
            self.to_async.cancel()


class WebCredentialsPrompt(CredentialsPrompt):
    loop: asyncio.AbstractEventLoop
    auth_server: 'HangoutsAuthServer'
    user: 'u.User'
    device_name: str
    current_status: Dict
    cancelled: bool

    queue: SingleItemBidiChannel
    expecting: Optional[CredentialType]

    def __init__(self, auth_server: 'HangoutsAuthServer', user: 'u.User', manual: bool,
                 device_name: str, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.auth_server = auth_server
        self.user = user
        self.device_name = device_name
        self.manual = manual
        self.queue = SingleItemBidiChannel()
        self.cancelled = False

    def _set_expecting(self, expecting: Any) -> None:
        self.expecting = expecting

    # region Asyncio -> Login thread

    async def start(self) -> dict:
        return await self.queue.init(lambda: self._ensure_get_auth())

    async def send_credential(self, credential: Optional[str] = None) -> dict:
        if self.cancelled:
            raise asyncio.CancelledError()
        return await self.queue.send_to_sync(credential,
                                             lambda: self._set_expecting(None))

    # endregion
    # region Starting login thread

    def _ensure_get_auth(self) -> None:
        asyncio.ensure_future(self._get_auth(), loop=self.loop)

    async def _get_auth(self) -> None:
        try:
            cookies = await self.loop.run_in_executor(None, get_auth,
                                                      self,
                                                      u.UserRefreshTokenCache(self.user),
                                                      self.manual)
            await self.user.login_complete(cookies)
            self.current_status = {
                "status": "success",
                "name": await self.user.name_future,
            }
            self.queue.finish(self.current_status)
        except GoogleAuthError as e:
            log.exception(f"Login for {self.user.mxid} failed")
            self.current_status = {"status": "fail", "error": str(e)}
            self.queue.finish(self.current_status)
        except Exception:
            log.exception(f"Login for {self.user.mxid} errored")
        try:
            del self.auth_server.ongoing[self.user.mxid]
        except KeyError:
            pass

    # endregion
    # region Login thread

    def cancel(self) -> None:
        self.cancelled = True
        try:
            del self.auth_server.ongoing[self.user.mxid]
        except KeyError:
            pass
        self.queue.cancel()

    def _receive_credential(self, result_type: CredentialType) -> Optional[str]:
        if self.cancelled:
            return None
        self.current_status = {
            "next_step": result_type.value,
        }
        if result_type == CredentialType.AUTHORIZATION:
            self.current_status["manual_auth_url"] = make_login_url(self.device_name)
        try:
            return self.queue.send_to_async(self.current_status,
                                            lambda: self._set_expecting(result_type))
        except futures.TimeoutError:
            self.cancel()
            return None
        except futures.CancelledError:
            return None

    def get_email(self) -> Optional[str]:
        return self._receive_credential(CredentialType.EMAIL)

    def get_password(self) -> Optional[str]:
        return self._receive_credential(CredentialType.PASSWORD)

    def get_verification_code(self) -> Optional[str]:
        return self._receive_credential(CredentialType.VERIFICATION)

    def get_authorization_code(self) -> Optional[str]:
        return self._receive_credential(CredentialType.AUTHORIZATION)

    # endregion
