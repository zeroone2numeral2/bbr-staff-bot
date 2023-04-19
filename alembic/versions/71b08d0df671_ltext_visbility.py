"""ltext visbility

Revision ID: 71b08d0df671
Revises: c3ada0acd3d0
Create Date: 2023-04-19 11:12:40.971097

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '71b08d0df671'
down_revision = 'c3ada0acd3d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('localized_texts', sa.Column('show_if_true_bot_setting_key', sa.String))


def downgrade() -> None:
    op.drop_column('localized_texts', 'show_if_true_bot_setting_key')
