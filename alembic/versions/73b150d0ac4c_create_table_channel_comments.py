"""create table channel comments

Revision ID: 73b150d0ac4c
Revises: 93408f307bcc
Create Date: 2024-02-20 17:21:10.286576

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '73b150d0ac4c'
down_revision = '93408f307bcc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'channel_comments',
        sa.Column('chat_id', sa.Integer, sa.ForeignKey('chats.chat_id'), primary_key=True),
        sa.Column('message_id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.user_id'), default=None, nullable=True),
        sa.Column('sender_chat_id', sa.Integer),
        sa.Column('message_thread_id', sa.Integer),
        sa.Column('reply_to_message_id', sa.Integer),
        sa.Column('channel_post_chat_id', sa.Integer, sa.ForeignKey('chats.chat_id')),
        sa.Column('channel_post_message_id', sa.Integer),
        sa.Column('not_info', sa.Boolean),
        sa.Column('message_text', sa.String),
        sa.Column('message_date', sa.DateTime),
        sa.Column('message_edit_date', sa.DateTime),
        sa.Column('media_group_id', sa.Integer),
        sa.Column('media_file_id', sa.String),
        sa.Column('media_file_unique_id', sa.String),
        sa.Column('media_type', sa.String),
        sa.Column('media_file_path', sa.String),
        sa.Column('created_on', sa.DateTime),
        sa.Column('updated_on', sa.DateTime),
        sa.Column('message_json', sa.String),
        sa.ForeignKeyConstraint(
            ['channel_post_chat_id', 'channel_post_message_id'],
            ['events.chat_id', 'events.message_id'],
        ),)


def downgrade() -> None:
    op.drop_table('channel_comments')
