"""bot setting show if true

Revision ID: 45d5591e71ca
Revises: 4d6d093bbb81
Create Date: 2023-04-19 09:10:44.990442

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '45d5591e71ca'
down_revision = '4d6d093bbb81'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bot_settings', sa.Column('show_if_true_key', sa.String))


def downgrade() -> None:
    op.drop_column('bot_settings', 'show_if_true_key')
