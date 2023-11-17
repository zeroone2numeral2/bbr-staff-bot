"""reset requests

Revision ID: e62a2e9962cf
Revises: 1c961abac998
Create Date: 2023-11-17 11:31:21.754135

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e62a2e9962cf'
down_revision = '1c961abac998'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('application_requests', sa.Column('reset', sa.Boolean))


def downgrade() -> None:
    op.drop_column('application_requests', 'reset')
