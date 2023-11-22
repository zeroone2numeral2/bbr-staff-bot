"""drop not_a_party

Revision ID: f6980505a3af
Revises: 005cab4ac4e4
Create Date: 2023-11-22 11:27:20.037959

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6980505a3af'
down_revision = '005cab4ac4e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('events', 'not_a_party')


def downgrade() -> None:
    op.add_column('events', sa.Column('not_a_party', sa.Boolean))
