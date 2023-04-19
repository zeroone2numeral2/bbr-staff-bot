"""user first seen

Revision ID: 35066b5e4a17
Revises: a55599ce4ca6
Create Date: 2023-03-31 13:29:30.031612

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '35066b5e4a17'
down_revision = 'a55599ce4ca6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('first_seen', sa.DateTime))


def downgrade() -> None:
    op.drop_column('users', 'first_seen')
