"""Add receiver field to portals

Revision ID: fb42f7a67a6b
Revises: bfb775ce2cee
Create Date: 2019-05-17 21:19:04.152171

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "fb42f7a67a6b"
down_revision = "bfb775ce2cee"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("_portal_temp",
                    sa.Column("gid", sa.String(length=255), nullable=False),
                    sa.Column("receiver", sa.String(length=255), nullable=False, server_default=""),
                    sa.Column("conv_type", sa.SmallInteger(), nullable=False),
                    sa.Column("other_user_id", sa.String(length=255), nullable=True),
                    sa.Column("mxid", sa.String(length=255), nullable=True),
                    sa.Column("name", sa.String(), nullable=True),
                    sa.PrimaryKeyConstraint("gid", "receiver"),
                    sa.UniqueConstraint("mxid"))
    c = op.get_bind()
    c.execute("INSERT INTO _portal_temp (gid, receiver, conv_type, other_user_id, mxid, name) "
              "SELECT portal.gid, (CASE WHEN portal.conv_type = 2 THEN portal.gid ELSE '' END), "
              "       portal.conv_type, portal.other_user_id, portal.mxid, portal.name "
              "FROM portal")
    c.execute("DROP TABLE portal")
    c.execute("ALTER TABLE _portal_temp RENAME TO portal")


def downgrade():
    op.create_table("_portal_temp",
                    sa.Column("gid", sa.String(length=255), nullable=False),
                    sa.Column("conv_type", sa.SmallInteger(), nullable=False),
                    sa.Column("other_user_id", sa.String(length=255), nullable=True),
                    sa.Column("mxid", sa.String(length=255), nullable=True),
                    sa.Column("name", sa.String(), nullable=True),
                    sa.PrimaryKeyConstraint("gid"),
                    sa.UniqueConstraint("mxid"))
    c = op.get_bind()
    c.execute("INSERT INTO _portal_temp (gid, conv_type, other_user_id, mxid, name) "
              "SELECT portal.gid, portal.conv_type, portal.other_user_id, portal.mxid, portal.name "
              "FROM portal")
    c.execute("DROP TABLE portal")
    c.execute("ALTER TABLE _portal_temp RENAME TO portal")
