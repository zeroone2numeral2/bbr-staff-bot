"""chat can_invite_users

Revision ID: d2b81ab15dac
Revises: 2122562bb66b
Create Date: 2023-05-10 16:22:46.751125

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd2b81ab15dac'
down_revision = '2122562bb66b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chats', sa.Column('can_invite_users', sa.Boolean))


def downgrade() -> None:
    op.drop_column('chats', 'can_invite_users')
