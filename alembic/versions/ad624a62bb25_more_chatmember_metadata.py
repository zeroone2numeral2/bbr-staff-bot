"""more ChatMember metadata

Revision ID: ad624a62bb25
Revises: 8f74d7ec6b1a
Create Date: 2023-06-20 17:39:44.304255

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ad624a62bb25'
down_revision = '8f74d7ec6b1a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chat_members', sa.Column('has_been_member', sa.Boolean))
    op.add_column('chat_members', sa.Column('kicked', sa.Boolean))


def downgrade() -> None:
    op.drop_column('chat_members', 'has_been_member')
    op.drop_column('chat_members', 'kicked')
