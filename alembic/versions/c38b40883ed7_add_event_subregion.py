"""add event subregion

Revision ID: c38b40883ed7
Revises: cab415340273
Create Date: 2024-07-09 13:01:43.018715

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c38b40883ed7'
down_revision = 'cab415340273'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('subregion', sa.String))


def downgrade() -> None:
    op.drop_column('events', 'subregion')
