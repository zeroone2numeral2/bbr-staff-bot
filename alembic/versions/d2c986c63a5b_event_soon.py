"""event soon

Revision ID: d2c986c63a5b
Revises: ad624a62bb25
Create Date: 2023-08-08 14:54:12.989879

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd2c986c63a5b'
down_revision = 'ad624a62bb25'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('soon', sa.Boolean))


def downgrade() -> None:
    op.drop_column('events', 'soon')
