"""added column network_chat

Revision ID: d7fdd977312e
Revises: c38b40883ed7
Create Date: 2024-08-06 12:25:28.274323

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7fdd977312e'
down_revision = 'c38b40883ed7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chats', sa.Column('network_chat', sa.Boolean))


def downgrade() -> None:
    op.drop_column('chats', 'network_chat')
