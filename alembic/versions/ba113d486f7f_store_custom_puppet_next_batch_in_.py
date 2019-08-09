"""Store custom puppet next_batch in database

Revision ID: ba113d486f7f
Revises: 63ea9db2aa00
Create Date: 2019-08-09 23:56:24.125130

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ba113d486f7f"
down_revision = "63ea9db2aa00"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("puppet") as batch_op:
        batch_op.add_column(sa.Column("next_batch", sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table("puppet") as batch_op:
        batch_op.drop_column("next_batch")
