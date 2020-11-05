"""Stop using size-limited string fields

Revision ID: 52cd44bea796
Revises: 33078cd14618
Create Date: 2020-11-05 20:25:45.670609

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '52cd44bea796'
down_revision = '33078cd14618'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().engine.name != "postgresql":
        return

    op.alter_column("portal", "gid", type_=sa.Text())
    op.alter_column("portal", "receiver", type_=sa.Text())
    op.alter_column("portal", "other_user_id", type_=sa.Text())
    op.alter_column("portal", "mxid", type_=sa.Text())

    op.alter_column("message", "mxid", type_=sa.Text())
    op.alter_column("message", "mx_room", type_=sa.Text())
    op.alter_column("message", "gid", type_=sa.Text())
    op.alter_column("message", "receiver", type_=sa.Text())

    op.alter_column("puppet", "gid", type_=sa.Text())
    op.alter_column("puppet", "name", type_=sa.Text())
    op.alter_column("puppet", "photo_url", type_=sa.Text())
    op.alter_column("puppet", "custom_mxid", type_=sa.Text())
    op.alter_column("puppet", "next_batch", type_=sa.Text())

    op.alter_column("user", "mxid", type_=sa.Text())
    op.alter_column("user", "gid", type_=sa.Text())
    op.alter_column("user", "refresh_token", type_=sa.Text())
    op.alter_column("user", "notice_room", type_=sa.Text())

    op.alter_column("user_portal", "user", type_=sa.Text())
    op.alter_column("user_portal", "portal", type_=sa.Text())
    op.alter_column("user_portal", "portal_receiver", type_=sa.Text())

    op.alter_column("contact", "user", type_=sa.Text())
    op.alter_column("contact", "contact", type_=sa.Text())

    op.alter_column("mx_user_profile", "room_id", type_=sa.Text())
    op.alter_column("mx_user_profile", "user_id", type_=sa.Text())
    op.alter_column("mx_user_profile", "displayname", type_=sa.Text())
    op.alter_column("mx_user_profile", "avatar_url", type_=sa.Text())
    op.alter_column("mx_room_state", "room_id", type_=sa.Text())


def downgrade():
    if op.get_bind().engine.name != "postgresql":
        return

    op.alter_column("portal", "gid", type_=sa.String(255))
    op.alter_column("portal", "receiver", type_=sa.String(255))
    op.alter_column("portal", "other_user_id", type_=sa.String(255))
    op.alter_column("portal", "mxid", type_=sa.String(255))

    op.alter_column("message", "mxid", type_=sa.String(255))
    op.alter_column("message", "mx_room", type_=sa.String(255))
    op.alter_column("message", "gid", type_=sa.String(255))
    op.alter_column("message", "receiver", type_=sa.String(255))

    op.alter_column("puppet", "gid", type_=sa.String(255))
    op.alter_column("puppet", "name", type_=sa.String(255))
    op.alter_column("puppet", "photo_url", type_=sa.String(255))
    op.alter_column("puppet", "custom_mxid", type_=sa.String(255))
    op.alter_column("puppet", "next_batch", type_=sa.String(255))

    op.alter_column("user", "mxid", type_=sa.String(255))
    op.alter_column("user", "gid", type_=sa.String(255))
    op.alter_column("user", "refresh_token", type_=sa.String(255))
    op.alter_column("user", "notice_room", type_=sa.String(255))

    op.alter_column("user_portal", "user", type_=sa.String(255))
    op.alter_column("user_portal", "portal", type_=sa.String(255))
    op.alter_column("user_portal", "portal_receiver", type_=sa.String(255))

    op.alter_column("contact", "user", type_=sa.String(255))
    op.alter_column("contact", "contact", type_=sa.String(255))

    op.alter_column("mx_user_profile", "room_id", type_=sa.String(255))
    op.alter_column("mx_user_profile", "user_id", type_=sa.String(255))
    op.alter_column("mx_user_profile", "displayname", type_=sa.String())
    op.alter_column("mx_user_profile", "avatar_url", type_=sa.String(255))
    op.alter_column("mx_room_state", "room_id", type_=sa.String(255))
