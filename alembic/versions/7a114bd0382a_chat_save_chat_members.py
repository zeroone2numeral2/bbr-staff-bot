"""Chat.save_chat_members

Revision ID: 7a114bd0382a
Revises: d2c986c63a5b
Create Date: 2023-08-22 15:19:29.639022

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7a114bd0382a'
down_revision = 'd2c986c63a5b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chats', sa.Column('save_chat_members', sa.Boolean))


def downgrade() -> None:
    op.drop_column('chats', 'save_chat_members')
