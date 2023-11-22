"""event start week

Revision ID: 3193bf7a3816
Revises: a4d38d0ac10e
Create Date: 2023-10-03 15:17:47.034965

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '3193bf7a3816'
down_revision = 'a4d38d0ac10e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('start_week', sa.Integer))


def downgrade() -> None:
    op.drop_column('events', 'start_week')

