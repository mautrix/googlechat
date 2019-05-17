"""Add receiver and index fields to messages

Revision ID: 63ea9db2aa00
Revises: fb42f7a67a6b
Create Date: 2019-05-17 22:46:54.498744

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "63ea9db2aa00"
down_revision = "fb42f7a67a6b"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("message")
    op.create_table("message",
                    sa.Column("mxid", sa.String(length=255), nullable=True),
                    sa.Column("mx_room", sa.String(length=255), nullable=True),
                    sa.Column("gid", sa.String(length=255), nullable=False),
                    sa.Column("receiver", sa.String(length=255), nullable=False),
                    sa.Column("index", sa.SmallInteger(), nullable=False),
                    sa.PrimaryKeyConstraint("gid", "receiver", "index"),
                    sa.UniqueConstraint("mxid", "mx_room", name="_mx_id_room"))


def downgrade():
    op.drop_table("message")
    op.create_table("message",
                    sa.Column("mxid", sa.String(length=255), nullable=True),
                    sa.Column("mx_room", sa.String(length=255), nullable=True),
                    sa.Column("gid", sa.String(length=255), nullable=False),
                    sa.PrimaryKeyConstraint("gid"),
                    sa.UniqueConstraint("mxid", "mx_room", name="_mx_id_room"))
