"""user invited on

Revision ID: c3ada0acd3d0
Revises: 45d5591e71ca
Create Date: 2023-04-19 11:06:44.843519

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3ada0acd3d0'
down_revision = '45d5591e71ca'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('invited_on', sa.DateTime))


def downgrade() -> None:
    op.drop_column('users', 'invited_on')
