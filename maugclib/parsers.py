"""Parsing helper functions."""

import datetime

from . import googlechat_pb2

##############################################################################
# Message parsing utils
##############################################################################


def from_timestamp(microsecond_timestamp):
    """Convert a microsecond timestamp to a UTC datetime instance."""
    # Create datetime without losing precision from floating point (yes, this
    # is actually needed):
    return datetime.datetime.fromtimestamp(
        microsecond_timestamp // 1000000, datetime.timezone.utc
    ).replace(microsecond=(microsecond_timestamp % 1000000))


def to_timestamp(datetime_timestamp):
    """Convert UTC datetime to microsecond timestamp used by Hangouts."""
    return int(datetime_timestamp.timestamp() * 1000000)


def id_from_group_id(group_id: googlechat_pb2.GroupId) -> str:
    if group_id.HasField("dm_id"):
        return f"dm:{group_id.dm_id.dm_id}"
    elif group_id.HasField("space_id"):
        return f"space:{group_id.space_id.space_id}"
    else:
        return ""


def group_id_from_id(conversation_id: str) -> googlechat_pb2.GroupId:
    if conversation_id.startswith("dm:"):
        return googlechat_pb2.GroupId(
            dm_id=googlechat_pb2.DmId(
                dm_id=conversation_id[len("dm:") :],
            )
        )
    elif conversation_id.startswith("space:"):
        return googlechat_pb2.GroupId(
            space_id=googlechat_pb2.SpaceId(
                space_id=conversation_id[len("space:") :],
            )
        )
    else:
        raise ValueError("Invalid conversation ID")
