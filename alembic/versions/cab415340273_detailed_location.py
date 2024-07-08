"""detailed location

Revision ID: cab415340273
Revises: a46f8722a14c
Create Date: 2024-07-08 10:31:21.673350

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cab415340273'
down_revision = 'a46f8722a14c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('detailed_location', sa.String))


def downgrade() -> None:
    op.drop_column('events', 'detailed_location')
