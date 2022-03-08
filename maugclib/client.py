"""Abstract class for writing chat clients."""

from __future__ import annotations

from typing import Iterator
import asyncio
import base64
import binascii
import cgi
import datetime
import logging
import os
import random

from google.protobuf import message as proto
from yarl import URL
import aiohttp

from . import auth, channel, event, exceptions, googlechat_pb2, http_utils, parsers

logger = logging.getLogger(__name__)
dl_log = logger.getChild("download")
UPLOAD_URL = "https://chat.google.com/uploads"
# API key for `key` parameter (from Hangouts web client)
API_KEY = "AIzaSyD7InnYR3VKdb4j2rMUEbTCIr2VyEazl6k"
# Base URL for API requests:
GC_BASE_URL = "https://chat.google.com"


class Client:
    """Instant messaging client for Google Chat.

    Maintains a connections to the servers, emits events, and accepts commands.

    Args:
        token_manager: (auth.TokenManager): The token manager.
        max_retries (int): (optional) Maximum number of connection attempts
            hangups will make before giving up. Defaults to 5.
        retry_backoff_base (int): (optional) The base term for the exponential
            backoff. The following equation is used when calculating the number
            of seconds to wait prior to each retry:
            retry_backoff_base^(# of retries attempted thus far)
            Defaults to 2.
    """

    def __init__(
        self, token_manager: auth.TokenManager, max_retries: int = 5, retry_backoff_base: int = 2
    ) -> None:
        self._max_retries = max_retries
        self._retry_backoff_base = retry_backoff_base

        self.on_connect = event.Event("Client.on_connect")
        """
        :class:`.Event` fired when the client connects for the first time.
        """

        self.on_reconnect = event.Event("Client.on_reconnect")
        """
        :class:`.Event` fired when the client reconnects after being
        disconnected.
        """

        self.on_disconnect = event.Event("Client.on_disconnect")
        """
        :class:`.Event` fired when the client is disconnected.
        """

        self.on_stream_event = event.Event("Client.on_stream_event")
        """
        :class:`.Event` fired when an update arrives from the server.

        Args:
            state_update: A ``StateUpdate`` message.
        """

        # http_utils.Session instance (populated by .connect()):
        self._session = None

        # The token manager that renews our tokens for us.
        self._token_manager = token_manager

        # channel.Channel instance (populated by .connect()):
        self._channel = None

        # Future for Channel.listen (populated by .connect()):
        self._listen_future = None

        self.gc_request_header = googlechat_pb2.RequestHeader(
            client_type=googlechat_pb2.RequestHeader.ClientType.IOS,
            client_version=2440378181258,
            client_feature_capabilities=googlechat_pb2.ClientFeatureCapabilities(
                spam_room_invites_level=googlechat_pb2.ClientFeatureCapabilities.FULLY_SUPPORTED,
            ),
        )

        # String identifying this client (populated later):
        self._client_id = None

        # String email address for this account (populated later):
        self._email = None

        # Active client management parameters:
        # Time in seconds that the client as last set as active:
        self._last_active_secs = 0.0
        # ActiveClientState enum int value or None:
        self._active_client_state = None

    ##########################################################################
    # Public methods
    ##########################################################################

    async def connect(self, max_age: float) -> None:
        """Establish a connection to the chat server.

        Returns when an error has occurred, or :func:`disconnect` has been
        called.
        """
        proxy = os.environ.get("HTTP_PROXY")
        self._session = http_utils.Session(self._token_manager, proxy=proxy)
        try:
            self._channel = channel.Channel(
                self._session, self._max_retries, self._retry_backoff_base
            )

            # Forward the Channel events to the Client events.
            self._channel.on_connect.add_observer(self.on_connect.fire)
            self._channel.on_reconnect.add_observer(self.on_reconnect.fire)
            self._channel.on_disconnect.add_observer(self.on_disconnect.fire)
            self._channel.on_receive_array.add_observer(self._on_receive_array)

            # Wrap the coroutine in a Future so it can be cancelled.
            self._listen_future = asyncio.ensure_future(self._channel.listen(max_age))
            # Listen for StateUpdate messages from the Channel until it
            # disconnects.
            try:
                await self._listen_future
            except asyncio.CancelledError:
                # If this task is cancelled, we need to cancel our child task
                # as well. We don't need an additional yield because listen
                # cancels immediately.
                self._listen_future.cancel()
            logger.info("Client.connect returning because Channel.listen returned")
        finally:
            await self._session.close()

    def disconnect(self) -> None:
        """Gracefully disconnect from the server.

        When disconnection is complete, :func:`connect` will return.
        """
        logger.info("Graceful disconnect requested")
        # Cancel the listen task. We don't need an additional yield because
        # listen cancels immediately.
        self._listen_future.cancel()

    async def download_attachment(
        self, url: str | URL, max_size: int
    ) -> tuple[bytearray, str, str]:
        """
        Download an attachment that was present in a chat message.

        Args:
            url: The URL from :prop:`ChatMessageEvent.attachments`
            max_size: The maximum size to download. If this is greater than zero and
                the Content-Length response header is greater than this value, then the
                attachment will not be downloaded and a :class:`FileTooLargeError` will
                be raised instead.

        Returns:
            A tuple containing the raw data, the mime type (from Content-Type)
            and the file name (from Content-Disposition).
        """
        if isinstance(url, str):
            url = URL(url)
        resp: aiohttp.ClientResponse
        sess: aiohttp.ClientSession | None = None
        depth = 0
        try:
            # Usually there are 4 redirects for files and 1 for images
            while depth < 10:
                depth += 1
                if url.host.endswith(".google.com"):
                    logger.log(5, "Fetching %s with auth", url)
                    req = self._session.fetch_raw_ctx("GET", url, allow_redirects=False)
                else:
                    if not sess:
                        sess = aiohttp.ClientSession()
                    logger.log(5, "Fetching %s without auth", url)
                    req = sess.get(url, allow_redirects=False)

                async with req as resp:
                    # Follow redirects manually in order to re-add authorization headers
                    # when redirected from googleusercontent.com back to chat.google.com
                    if resp.status in (301, 302, 307, 308):
                        url = URL(resp.headers["Location"])
                        logger.log(5, "Redirected to %s", url)
                        continue

                    resp.raise_for_status()
                    try:
                        _, params = cgi.parse_header(resp.headers["Content-Disposition"])
                        filename = params.get("filename") or url.path.split("/")[-1]
                    except KeyError:
                        filename = url.path.split("/")[-1]
                    mime = resp.headers["Content-Type"]
                    data = await self.read_with_max_size(resp, max_size)
                    return data, mime, filename
        finally:
            if sess:
                await sess.close()

    @staticmethod
    async def read_with_max_size(resp: aiohttp.ClientResponse, max_size: int) -> bytearray:
        content_length = int(resp.headers.get("Content-Length", "0"))
        if 0 < max_size < content_length:
            raise exceptions.FileTooLargeError("File size larger than maximum")
        size_str = "unknown length" if content_length == 0 else f"{content_length} bytes"
        dl_log.info(f"Reading file download response with {size_str} (max: {max_size})")
        data = bytearray(content_length)
        mv = memoryview(data) if content_length > 0 else None
        read_size = 0
        max_size += 1
        while True:
            block = await resp.content.read(max_size)
            if not block:
                break
            max_size -= len(block)
            if max_size <= 0:
                raise exceptions.FileTooLargeError("File size larger than maximum")
            if len(data) >= read_size + len(block):
                mv[read_size : read_size + len(block)] = block
            elif len(data) > read_size:
                dl_log.warning("File being downloaded is bigger than expected")
                mv[read_size:] = block[: len(data) - read_size]
                mv.release()
                mv = None
                data.extend(block[len(data) - read_size :])
            else:
                if mv is not None:
                    mv.release()
                    mv = None
                data.extend(block)
            read_size += len(block)
        if mv is not None:
            mv.release()
        dl_log.info(f"Successfully read {read_size} bytes of file download response")
        return data

    async def upload_file(
        self,
        data: bytes,
        group_id: str,
        filename: str,
        mime_type: str,
    ) -> googlechat_pb2.UploadMetadata:
        headers = {
            "x-goog-upload-protocol": "resumable",
            "x-goog-upload-command": "start",
            "x-goog-upload-content-length": f"{len(data)}",
            "x-goog-upload-content-type": mime_type,
            "x-goog-upload-file-name": filename,
        }

        params = {
            "group_id": group_id,
        }

        # request an upload URL
        res = await self._base_request(UPLOAD_URL, None, "", None, headers, params)

        try:
            upload_url = res.headers["x-goog-upload-url"]
        except KeyError:
            raise exceptions.NetworkError("image upload failed: can not acquire an upload url")

        # upload the image to the upload URL
        headers = {
            "x-goog-upload-command": "upload, finalize",
            "x-goog-upload-protocol": "resumable",
            "x-goog-upload-offset": "0",
        }

        res = await self._base_request(upload_url, None, "", data, headers=headers, method="PUT")

        try:
            upload_metadata = googlechat_pb2.UploadMetadata()
            upload_metadata.ParseFromString(base64.b64decode(res.body))
        except binascii.Error as e:
            raise exceptions.NetworkError("Failed to decode base64 response: {}".format(e))
        except proto.DecodeError as e:
            raise exceptions.NetworkError(
                "Failed to decode Protocol Buffer response: {}".format(e)
            )

        return upload_metadata

    async def update_read_timestamp(
        self, conversation_id: str, read_timestamp: datetime.datetime
    ) -> None:
        try:
            await self.proto_mark_group_read_state(
                googlechat_pb2.MarkGroupReadstateRequest(
                    request_header=self.gc_request_header,
                    id=parsers.group_id_from_id(conversation_id),
                    last_read_time=parsers.to_timestamp(read_timestamp),
                )
            )
        except exceptions.NetworkError as e:
            logger.warning("Failed to update read timestamp: {}".format(e))
            raise

    async def react(
        self,
        conversation_id: str,
        thread_id: str,
        message_id: str,
        emoji: str,
        remove: bool = False,
    ) -> None:
        await self.proto_update_reaction(
            googlechat_pb2.UpdateReactionRequest(
                request_header=self.gc_request_header,
                emoji=googlechat_pb2.Emoji(unicode=emoji),
                message_id=googlechat_pb2.MessageId(
                    parent_id=googlechat_pb2.MessageParentId(
                        topic_id=googlechat_pb2.TopicId(
                            group_id=parsers.group_id_from_id(conversation_id),
                            topic_id=thread_id or message_id,
                        )
                    ),
                    message_id=message_id or thread_id,
                ),
                type=(
                    googlechat_pb2.UpdateReactionRequest.REMOVE
                    if remove
                    else googlechat_pb2.UpdateReactionRequest.ADD
                ),
            )
        )

    async def delete_message(
        self, conversation_id: str, thread_id: str, message_id: str
    ) -> googlechat_pb2.DeleteMessageResponse:
        return await self.proto_delete_message(
            googlechat_pb2.DeleteMessageRequest(
                request_header=self.gc_request_header,
                message_id=googlechat_pb2.MessageId(
                    parent_id=googlechat_pb2.MessageParentId(
                        topic_id=googlechat_pb2.TopicId(
                            group_id=parsers.group_id_from_id(conversation_id),
                            topic_id=thread_id or message_id,
                        )
                    ),
                    message_id=message_id or thread_id,
                ),
            )
        )

    async def edit_message(
        self,
        conversation_id: str,
        thread_id: str,
        message_id: str,
        text: str,
        annotations: list[googlechat_pb2.Annotation] | None = None,
    ) -> googlechat_pb2.EditMessageResponse:
        return await self.proto_edit_message(
            googlechat_pb2.EditMessageRequest(
                request_header=self.gc_request_header,
                message_id=googlechat_pb2.MessageId(
                    parent_id=googlechat_pb2.MessageParentId(
                        topic_id=googlechat_pb2.TopicId(
                            group_id=parsers.group_id_from_id(conversation_id),
                            topic_id=thread_id or message_id,
                        )
                    ),
                    message_id=message_id or thread_id,
                ),
                text_body=text,
                annotations=annotations,
                message_info=googlechat_pb2.MessageInfo(
                    accept_format_annotations=True,
                ),
            )
        )

    async def send_message(
        self,
        conversation_id: str,
        text: str = "",
        annotations: list[googlechat_pb2.Annotation] | None = None,
        thread_id: str | None = None,
        local_id: str | None = None,
    ) -> googlechat_pb2.CreateTopicResponse | googlechat_pb2.CreateMessageResponse:
        try:
            local_id = local_id or f"hangups%{random.randint(0, 0xffffffffffffffff)}"
            if thread_id:
                request = googlechat_pb2.CreateMessageRequest(
                    request_header=self.gc_request_header,
                    parent_id=googlechat_pb2.MessageParentId(
                        topic_id=googlechat_pb2.TopicId(
                            group_id=parsers.group_id_from_id(conversation_id),
                            topic_id=thread_id,
                        ),
                    ),
                    local_id=local_id,
                    text_body=text,
                    annotations=annotations,
                    message_info=googlechat_pb2.MessageInfo(
                        accept_format_annotations=True,
                    ),
                )
                return await self.proto_create_message(request)
            else:
                request = googlechat_pb2.CreateTopicRequest(
                    request_header=self.gc_request_header,
                    group_id=parsers.group_id_from_id(conversation_id),
                    local_id=local_id,
                    text_body=text,
                    history_v2=True,
                    annotations=annotations,
                    message_info=googlechat_pb2.MessageInfo(
                        accept_format_annotations=True,
                    ),
                )
                return await self.proto_create_topic(request)
        except exceptions.NetworkError as e:
            logger.warning("Failed to send message: {}".format(e))
            raise

    async def mark_typing(
        self, conversation_id: str, thread_id: str | None = None, typing: bool = True
    ) -> int:
        group_id = parsers.group_id_from_id(conversation_id)
        if thread_id:
            context = googlechat_pb2.TypingContext(
                topic_id=googlechat_pb2.TopicId(
                    group_id=group_id,
                    topic_id=thread_id,
                )
            )
        else:
            context = googlechat_pb2.TypingContext(group_id=group_id)
        resp = await self.proto_set_typing_state(
            googlechat_pb2.SetTypingStateRequest(
                request_header=self.gc_request_header,
                state=googlechat_pb2.TYPING if typing else googlechat_pb2.STOPPED,
                context=context,
            )
        )
        return resp.start_timestamp_usec

    ##########################################################################
    # Private methods
    ##########################################################################

    async def _on_receive_array(self, array: list) -> None:
        """Parse channel array and call the appropriate events."""
        if array[0] == "noop":
            pass  # This is just a keep-alive, ignore it.
        else:
            if "data" in array[0]:
                data = array[0]["data"]

                resp = googlechat_pb2.StreamEventsResponse()
                resp.ParseFromString(base64.b64decode(data))

                # An event can have multiple bodies embedded in it. However,
                # instead of pushing all bodies in the same place, there first
                # one is a separate field. So to simplify handling, we muck
                # around with the class by swapping the embedded bodies into
                # the top level body field and fire the event like it was the
                # toplevel body.
                for evt in self.split_event_bodies(resp.event):
                    await self.on_stream_event.fire(evt)

    @staticmethod
    def split_event_bodies(evt: googlechat_pb2.Event) -> Iterator[googlechat_pb2.Event]:
        embedded_bodies = evt.bodies
        if len(embedded_bodies) > 0:
            evt.ClearField("bodies")

        if evt.HasField("body"):
            yield evt

        body: googlechat_pb2.Event.EventBody
        for body in embedded_bodies:
            evt_copy = googlechat_pb2.Event()
            evt_copy.CopyFrom(evt)
            evt_copy.body.CopyFrom(body)
            evt_copy.type = body.event_type
            yield evt_copy

    async def _gc_request(
        self, endpoint, request_pb: proto.Message, response_pb: proto.Message
    ) -> None:
        """Send a Protocol Buffer formatted chat API request.

        Args:
            endpoint (str): The chat API endpoint to use.
            request_pb: The request body as a Protocol Buffer message.
            response_pb: The response body as a Protocol Buffer message.

        Raises:
            NetworkError: If the request fails.
        """
        logger.debug("Sending Protocol Buffer request %s:\n%s", endpoint, request_pb)
        res = await self._base_request(
            "{}/api/{}?rt=b".format(GC_BASE_URL, endpoint),
            "application/x-protobuf",  # Request body is Protocol Buffer.
            "proto",  # Response body is Protocol Buffer.
            request_pb.SerializeToString(),
        )
        try:
            response_pb.ParseFromString(res.body)
        except proto.DecodeError as e:
            raise exceptions.NetworkError(
                "Failed to decode Protocol Buffer response: {}".format(e)
            )
        logger.debug("Received Protocol Buffer response:\n%s", response_pb)

    async def _base_request(
        self,
        url: str,
        content_type: str | None,
        response_type: str,
        data: str | bytes | None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        method: str = "POST",
    ):
        """Send a generic authenticated POST request.

        Args:
            url (str): URL of request.
            content_type (str): Request content type.
            response_type (str): The desired response format. Valid options
                are: 'json' (JSON), 'protojson' (pblite), and 'proto' (binary
                Protocol Buffer). 'proto' requires manually setting an extra
                header 'X-Goog-Encode-Response-If-Executable: base64'.
            data (str): Request body data.

        Returns:
            FetchResponse: Response containing HTTP code, cookies, and body.

        Raises:
            NetworkError: If the request fails.
        """
        if headers is None:
            headers = {}

        if content_type is not None:
            headers["content-type"] = content_type

        if response_type == "proto":
            # This header is required for Protocol Buffer responses. It causes
            # them to be base64 encoded:
            headers["X-Goog-Encode-Response-If-Executable"] = "base64"

        if params is None:
            params = {}

        params.update(
            {
                # "alternative representation type" (desired response format).
                "alt": response_type,
                # API key (required to avoid 403 Forbidden "Daily Limit for
                # Unauthenticated Use Exceeded. Continued use requires signup").
                "key": API_KEY,
            }
        )
        res = await self._session.fetch(
            method,
            url,
            headers=headers,
            params=params,
            data=data,
        )
        return res

    ###########################################################################
    # API request methods - wrappers for self._pb_request for calling
    # particular APIs.
    ###########################################################################

    async def proto_get_user_presence(
        self, get_user_presence_request: googlechat_pb2.GetUserPresenceRequest
    ) -> googlechat_pb2.GetUserPresenceResponse:
        """Return one or more user presences."""

        response = googlechat_pb2.GetUserPresenceResponse()
        await self._gc_request("get_user_presence", get_user_presence_request, response)
        return response

    async def proto_get_members(
        self, get_members_request: googlechat_pb2.GetMembersRequest
    ) -> googlechat_pb2.GetMembersResponse:
        """Return one or more members"""

        response = googlechat_pb2.GetMembersResponse()
        await self._gc_request("get_members", get_members_request, response)
        return response

    async def proto_paginated_world(
        self, paginate_world_request: googlechat_pb2.PaginatedWorldRequest
    ) -> googlechat_pb2.PaginatedWorldResponse:
        """Gets a list of all conversations"""
        response = googlechat_pb2.PaginatedWorldResponse()

        await self._gc_request("paginated_world", paginate_world_request, response)

        return response

    async def proto_get_self_user_status(
        self, get_self_user_status_request: googlechat_pb2.GetSelfUserStatusRequest
    ) -> googlechat_pb2.GetSelfUserStatusResponse:
        """Return info about the current user.

        Replace get_self_info.
        """
        response = googlechat_pb2.GetSelfUserStatusResponse()
        await self._gc_request("get_self_user_status", get_self_user_status_request, response)
        return response

    async def proto_get_group(
        self, get_group_request: googlechat_pb2.GetGroupRequest
    ) -> googlechat_pb2.GetGroupResponse:
        """Looks up a group chat"""
        response = googlechat_pb2.GetGroupResponse()
        await self._gc_request("get_group", get_group_request, response)
        return response

    async def proto_mark_group_read_state(
        self, mark_group_read_state_request: googlechat_pb2.MarkGroupReadstateRequest
    ) -> googlechat_pb2.MarkGroupReadstateResponse:
        """Marks the group's read state."""
        response = googlechat_pb2.MarkGroupReadstateResponse()
        await self._gc_request("mark_group_readstate", mark_group_read_state_request, response)
        return response

    async def proto_create_topic(
        self, create_topic_request: googlechat_pb2.CreateTopicRequest
    ) -> googlechat_pb2.CreateTopicResponse:
        """Creates a topic (sends a message)"""
        response = googlechat_pb2.CreateTopicResponse()
        await self._gc_request("create_topic", create_topic_request, response)
        return response

    async def proto_create_message(
        self, create_message_request: googlechat_pb2.CreateMessageRequest
    ) -> googlechat_pb2.CreateMessageResponse:
        """Creates a message which is a response to a thread"""
        response = googlechat_pb2.CreateMessageResponse()
        await self._gc_request("create_message", create_message_request, response)
        return response

    async def proto_update_reaction(
        self, update_reaction_request: googlechat_pb2.UpdateReactionRequest
    ) -> googlechat_pb2.UpdateReactionResponse:
        """Reacts to a message"""
        response = googlechat_pb2.UpdateReactionResponse()
        await self._gc_request("update_reaction", update_reaction_request, response)
        return response

    async def proto_delete_message(
        self, delete_message_request: googlechat_pb2.DeleteMessageRequest
    ) -> googlechat_pb2.DeleteMessageResponse:
        response = googlechat_pb2.DeleteMessageResponse()
        await self._gc_request("delete_message", delete_message_request, response)
        return response

    async def proto_edit_message(
        self, edit_message_request: googlechat_pb2.EditMessageRequest
    ) -> googlechat_pb2.EditMessageResponse:
        response = googlechat_pb2.EditMessageResponse()
        await self._gc_request("edit_message", edit_message_request, response)
        return response

    async def proto_set_typing_state(
        self, set_typing_state_request: googlechat_pb2.SetTypingStateRequest
    ) -> googlechat_pb2.SetTypingStateResponse:
        response = googlechat_pb2.SetTypingStateResponse()
        await self._gc_request("set_typing_state", set_typing_state_request, response)
        return response

    async def proto_catch_up_user(
        self, catch_up_user_request: googlechat_pb2.CatchUpUserRequest
    ) -> googlechat_pb2.CatchUpResponse:
        response = googlechat_pb2.CatchUpResponse()
        await self._gc_request("catch_up_user", catch_up_user_request, response)
        return response

    async def proto_catch_up_group(
        self, catch_up_group_request: googlechat_pb2.CatchUpGroupRequest
    ) -> googlechat_pb2.CatchUpResponse:
        response = googlechat_pb2.CatchUpResponse()
        await self._gc_request("catch_up_group", catch_up_group_request, response)
        return response

    async def proto_list_topics(
        self, list_topics_request: googlechat_pb2.ListTopicsRequest
    ) -> googlechat_pb2.ListTopicsResponse:
        response = googlechat_pb2.ListTopicsResponse()
        await self._gc_request("list_topics", list_topics_request, response)
        return response

    async def proto_list_messages(
        self, list_messages_request: googlechat_pb2.ListMessagesRequest
    ) -> googlechat_pb2.ListMessagesResponse:
        response = googlechat_pb2.ListMessagesResponse()
        await self._gc_request("list_messages", list_messages_request, response)
        return response

    async def proto_send_stream_event(
        self, stream_events_request: googlechat_pb2.StreamEventsRequest
    ) -> None:
        await self._channel.send_stream_event(stream_events_request)
