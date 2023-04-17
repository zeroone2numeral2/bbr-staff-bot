"""chat metadata

Revision ID: 2df5dda460fc
Revises: c557d7ba72ee
Create Date: 2023-04-17 15:58:55.999556

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2df5dda460fc'
down_revision = 'c557d7ba72ee'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chats', sa.Column('username', sa.String))
    op.add_column('chats', sa.Column('type', sa.String))
    op.add_column('chats', sa.Column('is_forum', sa.Boolean))


def downgrade() -> None:
    op.drop_column('chats', 'is_admin')
    op.drop_column('chats', 'type')
    op.drop_column('chats', 'is_forum')
