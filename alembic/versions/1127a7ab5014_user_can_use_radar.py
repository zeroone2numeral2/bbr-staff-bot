"""user can use radar

Revision ID: 1127a7ab5014
Revises: 3193bf7a3816
Create Date: 2023-10-23 13:12:10.170585

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1127a7ab5014'
down_revision = '3193bf7a3816'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('can_use_radar', sa.Boolean))


def downgrade() -> None:
    op.drop_column('users', 'can_use_radar')
