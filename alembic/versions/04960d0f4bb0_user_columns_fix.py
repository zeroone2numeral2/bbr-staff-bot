"""user columns fix

Revision ID: 04960d0f4bb0
Revises: 4bc6ff0745f3
Create Date: 2023-04-18 16:22:45.372809

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '04960d0f4bb0'
down_revision = '4bc6ff0745f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('users', 'application_evaluated_by')
    op.add_column('users', sa.Column('application_evaluated_by_user_id', sa.Integer))


def downgrade() -> None:
    op.add_column('users', sa.Column('application_evaluated_by', sa.Integer))
    op.drop_column('users', 'application_evaluated_by_user_id')
