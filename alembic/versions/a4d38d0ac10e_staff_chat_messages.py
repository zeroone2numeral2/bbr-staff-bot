"""staff chat messages

Revision ID: a4d38d0ac10e
Revises: 9f1d3046199d
Create Date: 2023-09-27 16:57:52.949698

"""
import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a4d38d0ac10e'
down_revision = '9f1d3046199d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'staff_chat_messages',
        sa.Column('chat_id', sa.Integer, sa.ForeignKey('chats.chat_id'), primary_key=True),
        sa.Column('message_id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.String, nullable=True),
        sa.Column('is_topic_message', sa.Boolean),
        sa.Column('message_thread_id', sa.Integer),
        sa.Column('message_date', sa.DateTime),
        sa.Column('message_edit_date', sa.DateTime),
        sa.Column('deleted', sa.Boolean),
        sa.Column('text_hash', sa.String),
        sa.Column('text_hashing_version', sa.Integer),
        sa.Column('media_file_id', sa.String),
        sa.Column('media_file_unique_id', sa.String),
        sa.Column('media_group_id', sa.Integer),
        sa.Column('media_type', sa.String),
        sa.Column('created_on', sa.DateTime),
        sa.Column('updated_on', sa.DateTime, onupdate=datetime.datetime.utcnow),
        sa.Column('message_json', sa.String)
    )


def downgrade() -> None:
    op.drop_table('staff_chat_messages')
