"""modlog chat

Revision ID: 516d3113ef5c
Revises: ea4b1c9039c6
Create Date: 2023-08-24 17:40:37.234032

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '516d3113ef5c'
down_revision = 'ea4b1c9039c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chats', sa.Column('is_modlog_chat', sa.Boolean, default=False))


def downgrade() -> None:
    op.drop_column('chats', 'is_modlog_chat')
