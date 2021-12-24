"""Google login authentication using OAuth 2.0.

Logging into Hangouts using OAuth2 requires a private scope only whitelisted
for certain clients. This module uses the client ID and secret from iOS, so it
will appear to Google to be an iOS device. Access can be revoked from this
page:
    https://security.google.com/settings/security/activity

This module should avoid logging any sensitive login information.
"""
from __future__ import annotations

from typing import Any
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import logging
import platform
import urllib.parse
import urllib.request

import aiohttp

try:
    from aiohttp_socks import ProxyConnector
except ImportError:
    ProxyConnector = None

logger = logging.getLogger(__name__)

OAUTH2_CLIENT_ID = "936475272427.apps.googleusercontent.com"
OAUTH2_CLIENT_SECRET = "KWsJlkaMn1jGLxQpWxMnOox-"
OAUTH2_SCOPES = [
    "https://www.google.com/accounts/OAuthLogin",
    "https://www.googleapis.com/auth/userinfo.email",
]
OAUTH2_TOKEN_REQUEST_URL = "https://accounts.google.com/o/oauth2/token"
USER_AGENT = "hangups/0.5.0 ({} {})".format(platform.system(), platform.machine())


class GoogleAuthError(Exception):
    """A Google authentication request failed."""


class RefreshTokenCache(ABC):
    @abstractmethod
    async def get(self) -> str:
        pass

    @abstractmethod
    async def set(self, refresh_token: str) -> None:
        pass


class TokenManager:
    def __init__(self, refresh_token_cache: RefreshTokenCache) -> None:
        connector = None
        try:
            http_proxy = urllib.request.getproxies()["http"]
        except KeyError:
            pass
        else:
            if ProxyConnector:
                # if the HTTP_PROXY environment variable is found set it up and assume
                # we're in a debugging environment so disable certificate verification
                # as well.
                logger.info(
                    "Found http_proxy environment, assuming debug "
                    "environment and disabling TLS certificate verification"
                )
                connector = ProxyConnector.from_url(http_proxy, verify_ssl=False)
            else:
                logger.warning("http_proxy is set, but aiohttp-socks is not installed")

        # a requests.Session for handling our requests
        self.session = aiohttp.ClientSession(
            connector=connector,
            headers={
                "User-Agent": USER_AGENT,
            },
        )

        # the refresh_token_cache so we can use and update it as necessary.
        self.refresh_token_cache = refresh_token_cache

        # access_token is the normal oauth access token which is used to get
        # the dynamite token. It's only used during run time and isn't stored
        # in the cache.
        self.access_token = None

        # oauth_expiration get's set to a datetime of when the oauth token
        # expires. This is necessary because a dynamite token expires hourly
        # but oauth tokens expire about every 24 hours, so we need to know to
        # refresh the oauth token so we can request a new dynamite token when
        # that happens.
        self.oauth_expiration = None

        # storage for the dynamite token and the datetime for when it will
        # expire.
        self.dynamite_token = None
        self.dynamite_expiration = None

    async def _token_request(self, data: dict[str, Any]) -> dict[str, Any]:
        """Make OAuth token request.

        Raises GoogleAuthError if authentication fails.

        Returns dict response.
        """
        try:
            r = await self.session.post(OAUTH2_TOKEN_REQUEST_URL, data=data)
            r.raise_for_status()
        except aiohttp.ClientError as e:
            raise GoogleAuthError("Token request failed: {}".format(e))
        else:
            res = await r.json()
            # If an error occurred, a key 'error' will contain an error code.
            if "error" in res:
                raise GoogleAuthError("Token request error: {!r}".format(res["error"]))
            return res

    @staticmethod
    async def from_authorization_code(
        authorization_code: str,
        refresh_token_cache: RefreshTokenCache,
    ) -> TokenManager:
        r = TokenManager(refresh_token_cache)

        data = {
            "client_id": OAUTH2_CLIENT_ID,
            "client_secret": OAUTH2_CLIENT_SECRET,
            "code": authorization_code,
            "grant_type": "authorization_code",
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        }

        res = await r._token_request(data)

        # store the new access token
        r.access_token = res["access_token"]

        # set it's expiration
        expires_in = timedelta(seconds=int(res["expires_in"]))
        r.oauth_expiration = datetime.now() + expires_in

        # store the new refresh token
        await r.refresh_token_cache.set(res["refresh_token"])

        # finally get the dynamite token
        await r._refresh_dynamite()

        return r

    async def _refresh_oauth(self) -> None:
        """Request a new access token from the refresh_token stored in the
        cache."""

        refresh_token = await self.refresh_token_cache.get()
        if refresh_token is None:
            raise GoogleAuthError("Refresh token not found")

        data = {
            "client_id": OAUTH2_CLIENT_ID,
            "client_secret": OAUTH2_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        res = await self._token_request(data)

        # store the new access token
        self.access_token = res["access_token"]

        # store the new expiration time
        expires_in = timedelta(seconds=int(res["expires_in"]))
        self.oauth_expiration = datetime.now() + expires_in

    @staticmethod
    async def from_refresh_token(refresh_token_cache: RefreshTokenCache) -> TokenManager:
        r = TokenManager(refresh_token_cache)

        await r._refresh_dynamite()

        return r

    async def _refresh_dynamite(self) -> None:
        """Use the oauth access token to get a dynamite token.

        Raises GoogleAuthError if the dynamite token couldn't be acquired.
        """

        # check the oauth_expiration before using the access token
        if self.oauth_expiration is None or datetime.now() >= self.oauth_expiration:
            await self._refresh_oauth()

        headers = {
            "Authorization": "Bearer {}".format(self.access_token),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "app_id": "com.google.Dynamite",
            "client_id": "576267593750-sbi1m7khesgfh1e0f2nv5vqlfa4qr72m.apps.googleusercontent.com",
            "passcode_present": "YES",
            "response_type": "token",
            "scope": " ".join(
                [
                    "https://www.googleapis.com/auth/dynamite",
                    "https://www.googleapis.com/auth/drive",
                    "https://www.googleapis.com/auth/mobiledevicemanagement",
                    "https://www.googleapis.com/auth/notifications",
                    "https://www.googleapis.com/auth/supportcontent",
                    "https://www.googleapis.com/auth/chat.integration",
                    "https://www.googleapis.com/auth/peopleapi.readonly",
                ]
            ),
        }

        try:
            r = await self.session.post(
                "https://oauthaccountmanager.googleapis.com/v1/issuetoken",
                headers=headers,
                data=data,
            )
            r.raise_for_status()
        except aiohttp.ClientError as e:
            raise GoogleAuthError("OAuthLogin request failed: {}".format(e))

        body = await r.json()

        try:
            self.dynamite_token = body["token"]
            expires_in = timedelta(seconds=int(body["expiresIn"]))
            self.dynamite_expiration = datetime.now() + expires_in
        except IndexError:
            raise GoogleAuthError("Failed to find the dynamite token")

    async def get(self) -> str:
        if self.dynamite_expiration is None or datetime.now() >= self.dynamite_expiration:
            await self._refresh_dynamite()

        return self.dynamite_token
