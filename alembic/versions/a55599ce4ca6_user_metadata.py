"""user metadata

Revision ID: a55599ce4ca6
Revises: 379ef134c45c
Create Date: 2023-03-31 12:16:37.232834

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a55599ce4ca6'
down_revision = '379ef134c45c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_bot', sa.Boolean, default=False))
    op.add_column('users', sa.Column('first_name', sa.String, default=None))
    op.add_column('users', sa.Column('last_name', sa.String, default=None))
    op.add_column('users', sa.Column('is_premium', sa.Boolean, default=False))


def downgrade() -> None:
    op.drop_column('users', 'is_bot')
    op.drop_column('users', 'first_name')
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'is_premium')
