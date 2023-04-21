"""telegram media values in bot settings

Revision ID: e1aa5c0345da
Revises: 71b08d0df671
Create Date: 2023-04-21 13:22:30.342579

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1aa5c0345da'
down_revision = '71b08d0df671'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bot_settings', sa.Column('value_media_file_id', sa.String))
    op.add_column('bot_settings', sa.Column('value_media_file_unique_id', sa.String))
    op.add_column('bot_settings', sa.Column('value_media_type', sa.String))


def downgrade() -> None:
    op.drop_column('bot_settings', 'value_media_file_id')
    op.drop_column('bot_settings', 'value_media_file_unique_id')
    op.drop_column('bot_settings', 'value_media_type')
