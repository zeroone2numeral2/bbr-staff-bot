"""validity change message columns

Revision ID: ee674947eb12
Revises: 23304df82140
Create Date: 2023-09-13 15:36:26.044438

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'ee674947eb12'
down_revision = '23304df82140'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('validity_notification_chat_id', sa.Integer))
    op.add_column('events', sa.Column('validity_notification_message_id', sa.Integer))
    op.add_column('events', sa.Column('validity_notification_sent_on', sa.DateTime))
    op.add_column('events', sa.Column('validity_notification_message_json', sa.String))


def downgrade() -> None:
    op.drop_column('events', 'validity_notification_chat_id')
    op.drop_column('events', 'validity_notification_message_id')
    op.drop_column('events', 'validity_notification_sent_on')
    op.drop_column('events', 'validity_notification_message_json')
