from typing import TYPE_CHECKING

from mautrix.bridge.commands import CommandEvent as BaseCommandEvent

if TYPE_CHECKING:
    from ..__main__ import GoogleChatBridge
    from ..user import User


class CommandEvent(BaseCommandEvent):
    bridge: "GoogleChatBridge"
    sender: "User"
