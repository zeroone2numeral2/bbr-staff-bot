"""User inviter

Revision ID: 4d6d093bbb81
Revises: 4bc6ff0745f3
Create Date: 2023-04-18 16:54:04.203180

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4d6d093bbb81'
down_revision = '4bc6ff0745f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('invited_by_user_id', sa.Integer))


def downgrade() -> None:
    op.drop_column('users', 'invited_by_user_id')
