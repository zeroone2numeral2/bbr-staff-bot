"""event media file paths

Revision ID: d77e21283ee4
Revises: 73b150d0ac4c
Create Date: 2024-03-18 13:10:24.245523

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd77e21283ee4'
down_revision = '73b150d0ac4c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('media_file_paths', sa.String))


def downgrade() -> None:
    op.drop_column('events', 'media_file_paths')
