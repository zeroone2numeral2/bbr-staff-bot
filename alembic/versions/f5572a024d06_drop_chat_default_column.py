"""drop Chat.default column

Revision ID: f5572a024d06
Revises: 2df5dda460fc
Create Date: 2023-04-18 15:22:40.183668

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f5572a024d06'
down_revision = '2df5dda460fc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('chats', 'default')


def downgrade() -> None:
    op.add_column('chats', sa.Column('default', sa.Boolean))
