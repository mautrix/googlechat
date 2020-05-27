"""Add bridge notice room column for users

Revision ID: ab5435bd192e
Revises: c319c2ce8698
Create Date: 2020-05-27 16:37:49.407252

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab5435bd192e'
down_revision = 'c319c2ce8698'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column('notice_room', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column('notice_room')
