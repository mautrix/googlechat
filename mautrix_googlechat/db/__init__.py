from mautrix.util.async_db import Database

from .upgrade import upgrade_table
from .reaction import Reaction
from .message import Message
from .portal import Portal
from .puppet import Puppet
from .user import User


def init(db: Database) -> None:
    for table in (Portal, Message, Reaction, User, Puppet):
        table.db = db


__all__ = ["upgrade_table", "init", "Message", "Reaction", "Portal", "User", "Puppet"]
