"""event end_date

Revision ID: 4cee9654b8f1
Revises: 516d3113ef5c
Create Date: 2023-08-31 16:19:48.869636

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4cee9654b8f1'
down_revision = '516d3113ef5c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('end_date', sa.Date, default=None))


def downgrade() -> None:
    op.drop_column('events', 'end_date')
