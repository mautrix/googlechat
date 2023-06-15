from __future__ import annotations

from typing import Any
import json


class HangupsError(Exception):
    """An ambiguous error occurred."""


class NetworkError(HangupsError):
    """A network error occurred."""


class ConversationTypeError(HangupsError):
    """An action was performed on a conversation that doesn't support it."""


class ChannelLifetimeExpired(HangupsError):
    pass


class SIDError(HangupsError):
    pass


class SIDExpiringError(SIDError):
    def __init__(self) -> None:
        super().__init__("SID is about to expire")


class SIDInvalidError(SIDError):
    def __init__(self) -> None:
        super().__init__("SID became invalid")


class FileTooLargeError(HangupsError):
    pass


class NotLoggedInError(HangupsError):
    pass


class ResponseError(HangupsError):
    body: Any

    def __init__(self, message: str, body: Any) -> None:
        super().__init__(message)
        self.body = body


class ResponseNotJSONError(ResponseError):
    def __init__(self, request_name: str, body: Any) -> None:
        super().__init__(f"{request_name} returned non-JSON body", body)


class UnexpectedResponseDataError(ResponseError):
    pass


class UnexpectedStatusError(ResponseError):
    error_code: str | None
    error_desc: str | None
    status: int
    reason: str

    def __init__(self, request: str, status: int, reason: str, body: Any) -> None:
        self.status = status
        self.reason = reason
        message = f"{request} failed with HTTP {status} {reason}"
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass
        self.status = status
        if isinstance(body, dict) and "error" in body:
            self.error_code = body.get("error", "")
            self.error_desc = body.get("error_description", "")
            message += f": {self.error_code}: {self.error_desc}"
        else:
            self.error_code = None
            self.error_desc = None
        super().__init__(message, body)
