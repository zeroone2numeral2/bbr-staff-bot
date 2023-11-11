"""localata

Revision ID: 22e853ce3c15
Revises: bc678867d676
Create Date: 2023-11-11 17:15:35.885693

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '22e853ce3c15'
down_revision = 'bc678867d676'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('localata', sa.Boolean))


def downgrade() -> None:
    op.drop_column('events', 'localata')
