"""Event.not_a_party

Revision ID: 9f1d3046199d
Revises: ee674947eb12
Create Date: 2023-09-26 09:38:17.396433

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '9f1d3046199d'
down_revision = 'ee674947eb12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('not_a_party', sa.Boolean))


def downgrade() -> None:
    op.drop_column('events', 'not_a_party')

