"""parties messages discussion group message deleted

Revision ID: 9a83b2eb2e04
Revises: 22e853ce3c15
Create Date: 2023-11-13 13:36:26.799074

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a83b2eb2e04'
down_revision = '22e853ce3c15'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('parties_messages', sa.Column('discussion_group_message_deleted', sa.Boolean))


def downgrade() -> None:
    op.drop_column('parties_messages', 'discussion_group_message_deleted')
