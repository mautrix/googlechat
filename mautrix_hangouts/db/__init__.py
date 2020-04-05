from mautrix.bridge.db import RoomState, UserProfile

from .message import Message
from .portal import Portal
from .puppet import Puppet
from .user import User, UserPortal, Contact

try:
    from mautrix.bridge.db.nio_state_store import init as init_nio_db
except ImportError:
    init_nio_db = None


def init(db_engine) -> None:
    for table in Portal, Message, User, Puppet, UserProfile, RoomState, UserPortal, Contact:
        table.db = db_engine
        table.t = table.__table__
        table.c = table.t.c
        table.column_names = table.c.keys()
    if init_nio_db:
        init_nio_db(db_engine)
