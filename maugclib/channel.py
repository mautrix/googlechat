"""Client for Google's BrowserChannel protocol.

BrowserChannel allows simulating a bidirectional socket in a web browser using
long-polling requests. It is used by the Hangouts web client to receive state
updates from the server. The "forward channel" sends "maps" (dictionaries) to
the server. The "backwards channel" receives "arrays" (lists) from the server.

Google provides a JavaScript BrowserChannel client as part of closure-library:
http://google.github.io/closure-library/api/class_goog_net_BrowserChannel.html

Source code is available here:
https://github.com/google/closure-library/blob/master/closure/goog/net/browserchannel.js

Unofficial protocol documentation is available here:
https://web.archive.org/web/20121226064550/http://code.google.com/p/libevent-browserchannel-server/wiki/BrowserChannelProtocol
"""
from __future__ import annotations

from typing import Iterator, NoReturn
import asyncio
import base64
import codecs
import json
import logging
import re
import time

import aiohttp
import async_timeout

from mautrix.util.opt_prometheus import Counter

from . import event, exceptions, googlechat_pb2, http_utils

logger = logging.getLogger(__name__)
Utf8IncrementalDecoder = codecs.getincrementaldecoder("utf-8")
LEN_REGEX = re.compile(r"([0-9]+)\n", re.MULTILINE)
CHANNEL_URL_BASE = "https://chat.google.com/webchannel/"
# Long-polling requests send heartbeats every 15-30 seconds, so if we miss two
# in a row, consider the connection dead.
PUSH_TIMEOUT = 60
MAX_READ_BYTES = 1024 * 1024

LONG_POLLING_REQUESTS = Counter(
    name="bridge_gc_started_long_polls",
    documentation="Number of long polling requests started",
)
LONG_POLLING_ERRORS = Counter(
    name="bridge_gc_long_poll_errors",
    documentation="Errors that stopped long polling",
    labelnames=["reason"],
)
RECEIVED_CHUNKS = Counter(
    name="bridge_gc_received_chunk_bytes",
    documentation="Received chunks from Google Chat long polling",
)


class ChannelSessionError(exceptions.HangupsError):
    """hangups channel session error"""


def _best_effort_decode(data_bytes):
    """Decode as much of data_bytes as possible as UTF-8."""
    decoder = Utf8IncrementalDecoder()
    return decoder.decode(data_bytes)


class ChunkParser:
    """Parse data from the backward channel into chunks.

    Responses from the backward channel consist of a sequence of chunks which
    are streamed to the client. Each chunk is prefixed with its length,
    followed by a newline. The length allows the client to identify when the
    entire chunk has been received.
    """

    def __init__(self) -> None:
        # Buffer for bytes containing utf-8 text:
        self._buf = b""

    def get_chunks(self, new_data_bytes: bytes) -> Iterator[str]:
        """Yield chunks generated from received data.

        The buffer may not be decodable as UTF-8 if there's a split multi-byte
        character at the end. To handle this, do a "best effort" decode of the
        buffer to decode as much of it as possible.

        The length is actually the length of the string as reported by
        JavaScript. JavaScript's string length function returns the number of
        code units in the string, represented in UTF-16. We can emulate this by
        encoding everything in UTF-16 and multiplying the reported length by 2.

        Note that when encoding a string in UTF-16, Python will prepend a
        byte-order character, so we need to remove the first two bytes.
        """
        self._buf += new_data_bytes

        while True:

            buf_decoded = _best_effort_decode(self._buf)
            buf_utf16 = buf_decoded.encode("utf-16")[2:]

            length_str_match = LEN_REGEX.match(buf_decoded)
            if length_str_match is None:
                break
            else:
                length_str = length_str_match.group(1)
                # Both lengths are in number of bytes in UTF-16 encoding.
                # The length of the submission:
                length = int(length_str) * 2
                # The length of the submission length and newline:
                length_length = len((length_str + "\n").encode("utf-16")[2:])
                if len(buf_utf16) - length_length < length:
                    break

                submission = buf_utf16[length_length : length_length + length]
                yield submission.decode("utf-16")
                # Drop the length and the submission itself from the beginning
                # of the buffer.
                drop_length = len((length_str + "\n").encode()) + len(
                    submission.decode("utf-16").encode()
                )
                self._buf = self._buf[drop_length:]


def _parse_sid_response(res: str) -> str:
    """Parse response format for request for new channel SID.

    Example format (after parsing JS):
    [ 0,["c","SID_HERE","",8,12]]]

    Returns SID
    """
    res = json.loads(res)
    sid = res[0][1][1]
    return sid


class Channel:
    """BrowserChannel client."""

    ##########################################################################
    # Public methods
    ##########################################################################

    def __init__(
        self, session: http_utils.Session, max_retries: int, retry_backoff_base: int
    ) -> None:
        """Create a new channel.

        Args:
            session (http_utils.Session): Request session.
            max_retries (int): Number of retries for long-polling request.
            retry_backoff_base (int): The base term for the long-polling
                exponential backoff.
        """

        # Event fired when channel connects with arguments ():
        self.on_connect = event.Event("Channel.on_connect")
        # Event fired when channel reconnects with arguments ():
        self.on_reconnect = event.Event("Channel.on_reconnect")
        # Event fired when channel disconnects with arguments ():
        self.on_disconnect = event.Event("Channel.on_disconnect")
        # Event fired when an array is received with arguments (array):
        self.on_receive_array = event.Event("Channel.on_receive_array")

        self._max_retries = max_retries
        self._retry_backoff_base = retry_backoff_base

        # True if the channel is currently connected:
        self._is_connected = False
        # True if the on_connect event has been called at least once:
        self._on_connect_called = False
        # Parser for assembling messages:
        self._chunk_parser = None
        # Session for HTTP requests:
        self._session = session

        # Discovered parameters:
        self._sid_param = None
        self._csessionid_param = None

        self._aid = 0
        self._ofs = 0  # used to track sent events
        self._rid = 0

    @property
    def is_connected(self):
        """Whether the channel is currently connected."""
        return self._is_connected

    async def listen(self, max_age: float) -> None:
        """Listen for messages on the backwards channel.

        This method only returns when the connection has been closed due to an
        error.
        """
        retries = 0  # Number of retries attempted so far
        skip_backoff = False

        self._csessionid_param = await self._register()
        start = time.monotonic()

        while retries <= self._max_retries:
            if start + max_age < time.monotonic():
                raise exceptions.ChannelLifetimeExpired()
            # After the first failed retry, back off exponentially longer after
            # each attempt.
            if retries > 0 and not skip_backoff:
                backoff_seconds = self._retry_backoff_base**retries
                logger.info(f"Backing off for {backoff_seconds} seconds")
                await asyncio.sleep(backoff_seconds)
            skip_backoff = False

            # Clear any previous push data, since if there was an error it
            # could contain garbage.
            self._chunk_parser = ChunkParser()
            try:
                await self._longpoll_request()
            except ChannelSessionError as err:
                logger.debug("Long-polling interrupted: %s", err)

                self._csessionid_param = await self._register()

                retries += 1
                skip_backoff = True
                continue
            except exceptions.NetworkError as err:
                logger.warning("Long-polling request failed: %s", err)
            else:
                # The connection closed successfully, so reset the number of
                # retries.
                retries = 0
                continue

            retries += 1
            logger.info("retry attempt count is now %s", retries)
            if self._is_connected:
                self._is_connected = False
                await self.on_disconnect.fire()

            # If the request ended with an error, the client must account for
            # messages being dropped during this time.

        logger.error("Ran out of retries for long-polling request")

    async def _register(self) -> str | None:
        # we need to clear our cookies because registering with a valid cookie
        # invalidates our cookie and doesn't get a new one sent back.
        self._session.clear_cookies()
        self._sid_param = None
        self._aid = 0
        self._ofs = 0

        headers = {"Content-Type": "application/x-protobuf"}
        res = await self._session.fetch_raw("POST", CHANNEL_URL_BASE + "register", headers=headers)

        if res.status != 200:
            raise exceptions.NetworkError(
                f"Request return unexpected status: {res.status}: {res.reason}"
            )

        body = await res.read()

        morsel = self._session.get_cookie(CHANNEL_URL_BASE, "COMPASS")
        logger.debug("Cookies: %s", self._session._cookie_jar._cookies)
        logger.debug("Register response: %s", body)
        logger.debug("Status: %s", res.status)
        logger.debug("Headers: %s", res.headers)
        if morsel is None:
            logger.warning("Failed to register channel (didn't get COMPASS cookie)")
        elif morsel.value.startswith("dynamite="):
            logger.info("Registered new channel successfully")
            return morsel.value[len("dynamite=") :]
        else:
            logger.warning("COMPASS cookie doesn't start with dynamite= (value: %s)", morsel.value)
        return None

    async def send_stream_event(self, events_request: googlechat_pb2.StreamEventsRequest):
        params = {
            "VER": 8,  # channel protocol version
            "RID": self._rid,  # request identifier
            "t": 1,  # trial
            "SID": self._sid_param,  # session ID
            "AID": self._aid,  # last acknowledged id
            "CI": 0,  # 0 if streaming/chunked requests should be used
        }

        self._rid += 1

        if self._csessionid_param is not None:
            params["csessionid"] = self._csessionid_param

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # base64 the raw protobuf
        b64_bytes = base64.b64encode(events_request.SerializeToString())

        json_body = json.dumps(
            {
                "data": b64_bytes.decode("ascii"),
            }
        )

        data = {
            "count": 1,
            "ofs": self._ofs,
            "req0___data__": json_body,
        }
        self._ofs += 1

        res = await self._session.fetch_raw(
            "POST",
            CHANNEL_URL_BASE + "events_encoded",
            headers=headers,
            params=params,
            data=data,
        )

        return res

    ##########################################################################
    # Private methods
    ##########################################################################

    async def _send_initial_ping(self):
        ping_event = googlechat_pb2.PingEvent(
            state=googlechat_pb2.PingEvent.State.ACTIVE,
            application_focus_state=googlechat_pb2.PingEvent.ApplicationFocusState.FOCUS_STATE_FOREGROUND,
            client_interactive_state=googlechat_pb2.PingEvent.ClientInteractiveState.INTERACTIVE,
            client_notifications_enabled=True,
        )

        logger.info("Sending initial ping request")
        return await self.send_stream_event(
            googlechat_pb2.StreamEventsRequest(
                ping_event=ping_event,
            )
        )

    async def _longpoll_request(self) -> None:
        """Open a long-polling request and receive arrays.

        This method uses keep-alive to make re-opening the request faster, but
        the remote server will set the "Connection: close" header once an hour.

        Raises hangups.NetworkError or ChannelSessionError.
        """
        params = {
            "VER": 8,  # channel protocol version
            "CVER": 22,  # client type
            "AID": self._aid,
            "t": 1,  # trial
        }

        self._rid += 1

        if self._sid_param is None:
            params.update(
                {
                    "$req": "count=0",  # noop request
                    "RID": "0",
                    "SID": "null",
                    "TYPE": "init",  # type of request
                }
            )
        else:
            params.update(
                {
                    "CI": 0,
                    "RID": "rpc",
                    "SID": self._sid_param,
                    "TYPE": "xmlhttp",
                }
            )

        logger.debug("Opening new long-polling request")
        LONG_POLLING_REQUESTS.inc()
        try:
            res: aiohttp.ClientResponse
            async with self._session.fetch_raw_ctx(
                "GET", CHANNEL_URL_BASE + "events_encoded", params=params
            ) as res:
                if res.status != 200:
                    if res.status == 400:
                        text = await res.text()
                        logger.info("400 %s response text: %s", res.reason, text)
                        if res.reason == "Unknown SID" or "Unknown SID" in text:
                            LONG_POLLING_ERRORS.labels(reason="sid invalid").inc()
                            raise ChannelSessionError("SID became invalid")
                    LONG_POLLING_ERRORS.labels(reason=f"http {res.status}").inc()
                    raise exceptions.NetworkError(
                        f"Request returned unexpected status: {res.status}: {res.reason}"
                    )

                initial_response = res.headers.get("X-HTTP-Initial-Response", None)
                if initial_response:
                    sid = _parse_sid_response(initial_response)
                    if self._sid_param != sid:
                        self._sid_param = sid
                        self._aid = 0
                        self._ofs = 0

                        await self._send_initial_ping()

                while True:
                    async with async_timeout.timeout(PUSH_TIMEOUT):
                        chunk = await res.content.read(MAX_READ_BYTES)
                    if not chunk:
                        break

                    await self._on_push_data(chunk)

        except asyncio.TimeoutError:
            LONG_POLLING_ERRORS.labels(reason="timeout").inc()
            raise exceptions.NetworkError("Request timed out")
        except aiohttp.ServerDisconnectedError as err:
            LONG_POLLING_ERRORS.labels(reason="server disconnected").inc()
            raise exceptions.NetworkError(f"Server disconnected error: {err}")
        except aiohttp.ClientPayloadError:
            LONG_POLLING_ERRORS.labels(reason="sid expiry").inc()
            raise ChannelSessionError("SID is about to expire")
        except aiohttp.ClientError as err:
            LONG_POLLING_ERRORS.labels(reason="connection error").inc()
            raise exceptions.NetworkError(f"Request connection error: {err}")
        LONG_POLLING_ERRORS.labels(reason="clean exit").inc()

    async def _on_push_data(self, data_bytes: bytes) -> None:
        """Parse push data and trigger events."""
        logger.debug("Received chunk:\n{}".format(data_bytes))
        RECEIVED_CHUNKS.inc(len(data_bytes))
        for chunk in self._chunk_parser.get_chunks(data_bytes):

            # Consider the channel connected once the first chunk is received.
            if not self._is_connected:
                if self._on_connect_called:
                    self._is_connected = True
                    await self.on_reconnect.fire()
                else:
                    self._on_connect_called = True
                    self._is_connected = True
                    await self.on_connect.fire()

            # chunk contains a container array
            container_array = json.loads(chunk)
            # container array is an array of inner arrays
            for inner_array in container_array:
                # inner_array always contains 2 elements, the array_id and the
                # data_array.
                array_id, data_array = inner_array
                logger.debug("Chunk contains data array with id %r:\n%r", array_id, data_array)
                await self.on_receive_array.fire(data_array)

                # update our last array id after we're done processing it
                self._aid = array_id
