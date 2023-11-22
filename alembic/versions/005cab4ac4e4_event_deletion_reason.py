"""event deletion reason

Revision ID: 005cab4ac4e4
Revises: e62a2e9962cf
Create Date: 2023-11-22 09:59:57.858906

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005cab4ac4e4'
down_revision = 'e62a2e9962cf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('deleted_reason', sa.Integer))
    op.add_column('events', sa.Column('deleted_on', sa.DateTime))


def downgrade() -> None:
    op.drop_column('events', 'deleted_reason')
    op.drop_column('events', 'deleted_on')
