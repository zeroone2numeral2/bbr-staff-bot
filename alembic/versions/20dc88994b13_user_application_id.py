"""user application_id

Revision ID: 20dc88994b13
Revises: cfdfbdcb87c3
Create Date: 2023-05-10 14:00:46.543689

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20dc88994b13'
down_revision = 'cfdfbdcb87c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('application_id', sa.Integer))


def downgrade() -> None:
    op.drop_column('users', 'application_id')
