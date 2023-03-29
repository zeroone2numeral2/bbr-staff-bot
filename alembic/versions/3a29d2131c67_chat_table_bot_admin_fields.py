"""chat table bot admin fields

Revision ID: 3a29d2131c67
Revises: 
Create Date: 2023-03-29 14:16:28.237121

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3a29d2131c67'
down_revision = None
branch_labels = None
depends_on = None

# test


def upgrade() -> None:
    op.add_column('chats', sa.Column('is_admin', sa.Boolean, default=False))
    op.add_column('chats', sa.Column('can_delete_messages', sa.Boolean, default=False))


def downgrade() -> None:
    op.drop_column('chats', 'is_admin')
    op.drop_column('chats', 'can_delete_messages')
