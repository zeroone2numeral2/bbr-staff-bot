"""settings categories

Revision ID: bc678867d676
Revises: 695d81dc57ec
Create Date: 2023-11-09 12:46:05.768697

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'bc678867d676'
down_revision = '695d81dc57ec'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bot_settings', sa.Column('category', sa.String))


def downgrade() -> None:
    op.drop_column('bot_settings', 'category')
