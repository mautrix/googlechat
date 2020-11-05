"""Add profile set booleans to puppet table

Revision ID: fae20932d275
Revises: 52cd44bea796
Create Date: 2020-11-05 20:53:59.009317

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fae20932d275'
down_revision = '52cd44bea796'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('puppet', schema=None) as batch_op:
        batch_op.add_column(sa.Column('avatar_set', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('name_set', sa.Boolean(), server_default=sa.false(), nullable=False))
    # Fill the database with assumed data so the bridge doesn't spam a ton of no-op profile updates
    op.execute("UPDATE puppet SET name_set=true WHERE name<>''")
    op.execute("UPDATE puppet SET avatar_set=true WHERE photo_url<>''")


def downgrade():
    with op.batch_alter_table('puppet', schema=None) as batch_op:
        batch_op.drop_column('name_set')
        batch_op.drop_column('avatar_set')
