from mautrix.client.state_store.sqlalchemy import RoomState, UserProfile

from .message import Message
from .portal import Portal
from .puppet import Puppet
from .user import User, UserPortal, Contact


def init(db_engine) -> None:
    for table in Portal, Message, User, Puppet, UserProfile, RoomState, UserPortal, Contact:
        table.db = db_engine
        table.t = table.__table__
        table.c = table.t.c
        table.column_names = table.c.keys()
