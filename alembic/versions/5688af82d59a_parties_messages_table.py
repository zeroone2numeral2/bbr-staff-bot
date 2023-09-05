"""parties messages table

Revision ID: 5688af82d59a
Revises: 4cee9654b8f1
Create Date: 2023-09-05 16:23:41.199725

"""
import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5688af82d59a'
down_revision = '4cee9654b8f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'parties_messages',
        sa.Column('chat_id', sa.Integer, sa.ForeignKey('chats.chat_id'), primary_key=True),
        sa.Column('message_id', sa.Integer, primary_key=True),
        sa.Column('events_type', sa.String, nullable=False),
        sa.Column('discussion_group_chat_id', sa.Integer),
        sa.Column('discussion_group_message_id', sa.Integer),
        sa.Column('discussion_group_received_on', sa.DateTime),
        sa.Column('discussion_group_message_json', sa.String),
        sa.Column('message_date', sa.DateTime),
        sa.Column('message_edit_date', sa.DateTime),
        sa.Column('force_sent', sa.Boolean),
        sa.Column('deleted', sa.Boolean),
        sa.Column('ignore', sa.Boolean),
        sa.Column('events_list', sa.String),
        sa.Column('created_on', sa.DateTime),
        sa.Column('updated_on', sa.DateTime, onupdate=datetime.datetime.utcnow),
        sa.Column('message_json', sa.String)
    )


def downgrade() -> None:
    op.drop_table('parties_messages')
