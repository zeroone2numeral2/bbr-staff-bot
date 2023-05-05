"""event date column

Revision ID: 49de6c426ecf
Revises: e1aa5c0345da
Create Date: 2023-05-05 09:46:06.579967

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '49de6c426ecf'
down_revision = 'e1aa5c0345da'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('start_date', sa.Date))


def downgrade() -> None:
    op.drop_column('events', 'start_date')
