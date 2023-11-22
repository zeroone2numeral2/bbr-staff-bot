"""added Chat.is_evaluation_chat

Revision ID: 8f74d7ec6b1a
Revises: a2401cf8abfd
Create Date: 2023-06-19 12:25:34.232734

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '8f74d7ec6b1a'
down_revision = 'a2401cf8abfd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chats', sa.Column('is_evaluation_chat', sa.Boolean))


def downgrade() -> None:
    op.drop_column('chats', 'is_evaluation_chat')
