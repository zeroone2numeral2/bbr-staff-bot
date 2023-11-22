"""chat types

Revision ID: db08018da65e
Revises: d2b81ab15dac
Create Date: 2023-05-11 11:56:10.881612

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'db08018da65e'
down_revision = 'd2b81ab15dac'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chats', sa.Column('is_events_chat', sa.Boolean))
    op.add_column('chats', sa.Column('is_log_chat', sa.Boolean))


def downgrade() -> None:
    op.drop_column('chats', 'is_events_chat')
    op.drop_column('chats', 'is_log_chat')
