"""HTTP request session."""
from __future__ import annotations

from typing import Any, AsyncIterator, cast
from contextlib import asynccontextmanager
from http.cookies import Morsel
import asyncio
import collections
import logging

from yarl import URL
import aiohttp
import async_timeout

from . import exceptions
from .auth import USER_AGENT, TokenManager

logger = logging.getLogger(__name__)
CONNECT_TIMEOUT = 30
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
ORIGIN_URL = "https://chat.google.com"

FetchResponse = collections.namedtuple("FetchResponse", ["code", "headers", "body"])


class Session:
    """Session for making HTTP requests to Google.

    Args:
        cookies (dict): Cookies to authenticate requests with.
        proxy (str): (optional) HTTP proxy URL to use for requests.
    """

    def __init__(self, token_manager: TokenManager, proxy: str = None) -> None:
        self._proxy = proxy
        # The server does not support quoting cookie values (see #498).
        self._cookie_jar = aiohttp.CookieJar(quote_cookie=False)
        timeout = aiohttp.ClientTimeout(connect=CONNECT_TIMEOUT)
        self._session = aiohttp.ClientSession(
            cookie_jar=self._cookie_jar,
            timeout=timeout,
            trust_env=True,
            headers={"User-Agent": USER_AGENT},
        )

        self._token_manager = token_manager

    def get_cookie(self, url: URL | str, name: str) -> Morsel[str]:
        filtered = self._cookie_jar.filter_cookies(url)

        return cast(Morsel, filtered.get(name, None))

    def clear_cookies(self) -> None:
        self._session.cookie_jar.clear()

    async def fetch(
        self,
        method: str,
        url: URL | str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
        data: Any = None,
    ) -> FetchResponse:
        """Make an HTTP request.

        Automatically uses configured HTTP proxy, and adds Google authorization
        header and cookies.

        Failures will be retried MAX_RETRIES times before raising NetworkError.

        Args:
            method (str): Request method.
            url (str): Request URL.
            params (dict): (optional) Request query string parameters.
            headers (dict): (optional) Request headers.
            allow_redirects (bool): Should redirects be followed automatically?
            data: (str): (optional) Request body data.

        Returns:
            FetchResponse: Response data.

        Raises:
            NetworkError: If the request fails.
        """
        logger.debug(
            "Sending request %s %s:\n%r",
            method,
            url,
            data if not data or len(data) < 64 * 1024 else f"{len(data)} bytes",
        )
        error_msg = "Request not attempted"
        for retry_num in range(MAX_RETRIES):
            try:
                async with self.fetch_raw_ctx(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    allow_redirects=allow_redirects,
                    data=data,
                ) as res:
                    async with async_timeout.timeout(REQUEST_TIMEOUT):
                        body = await res.read()
                logger.debug("Received response %d %s:\n%r", res.status, res.reason, body)
            except asyncio.TimeoutError:
                error_msg = "Request timed out"
            except aiohttp.ServerDisconnectedError as err:
                error_msg = "Server disconnected error: {}".format(err)
            except (aiohttp.ClientError, ValueError) as err:
                error_msg = "Request connection error: {}".format(err)
            else:
                break
            logger.info("Request attempt %d failed: %s", retry_num, error_msg)
        else:
            logger.info("Request failed after %d attempts", MAX_RETRIES)
            raise exceptions.NetworkError(error_msg)

        if res.status != 200:
            logger.info("Request returned unexpected status: %d %s", res.status, res.reason)
            raise exceptions.NetworkError(
                "Request return unexpected status: {}: {}".format(res.status, res.reason)
            )

        return FetchResponse(res.status, res.headers, body)

    async def fetch_raw(
        self,
        method: str,
        url: URL | str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
        data: Any = None,
    ) -> aiohttp.ClientResponse:
        """Make an HTTP request using aiohttp directly.

        Automatically uses configured HTTP proxy, and adds Google authorization
        header and cookies.

        Args:
            method (str): Request method.
            url (str): Request URL.
            params (dict): (optional) Request query string parameters.
            headers (dict): (optional) Request headers.
            allow_redirects (bool): Should redirects be followed automatically?
            data: (str): (optional) Request body data.

        Returns:
            aiohttp.ClientResponse: The HTTP response

        Raises:
            See ``aiohttp.ClientSession.request``.
        """
        resp = await self._fetch_raw(method, url, params, headers, allow_redirects, data)
        return await resp

    @asynccontextmanager
    async def fetch_raw_ctx(
        self,
        method: str,
        url: URL | str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
        data: Any = None,
    ) -> AsyncIterator[aiohttp.ClientResponse, None]:
        """Make an HTTP request using aiohttp directly.

        Automatically uses configured HTTP proxy, and adds Google authorization
        header and cookies.

        Args:
            method (str): Request method.
            url (str): Request URL.
            params (dict): (optional) Request query string parameters.
            headers (dict): (optional) Request headers.
            allow_redirects (bool): Should redirects be followed automatically?
            data: (str): (optional) Request body data.

        Yields:
            aiohttp.ClientResponse: The HTTP response

        Raises:
            See ``aiohttp.ClientSession.request``.
        """
        async with await self._fetch_raw(
            method, url, params, headers, allow_redirects, data
        ) as resp:
            yield resp

    async def _fetch_raw(
        self,
        method: str,
        url: URL | str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
        data: Any = None,
    ):
        # Ensure we don't accidentally send the authorization header to a
        # non-Google domain:
        if not URL(url).host.endswith(".google.com"):
            raise Exception("expected google.com domain")

        headers = headers or {}
        headers["Authorization"] = f"Bearer {await self._token_manager.get()}"
        headers["Connection"] = "Keep-Alive"
        return self._session.request(
            method,
            url,
            params=params,
            headers=headers,
            allow_redirects=allow_redirects,
            data=data,
            proxy=self._proxy,
            ssl=False,
        )

    async def close(self) -> None:
        """Close the underlying aiohttp.ClientSession."""
        await self._session.close()
