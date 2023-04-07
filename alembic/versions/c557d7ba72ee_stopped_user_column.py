"""stopped user column

Revision ID: c557d7ba72ee
Revises: deeb7baeda64
Create Date: 2023-04-07 10:58:44.103823

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c557d7ba72ee'
down_revision = 'deeb7baeda64'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('stopped', sa.Boolean, default=False))
    op.add_column('users', sa.Column('stopped_on', sa.DateTime, default=None))


def downgrade() -> None:
    op.drop_column('users', 'stopped')
    op.drop_column('users', 'stopped_on')
