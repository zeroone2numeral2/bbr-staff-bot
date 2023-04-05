"""ChatMember model

Revision ID: deeb7baeda64
Revises: 35066b5e4a17
Create Date: 2023-04-05 17:08:01.878240

"""
from alembic import op
from sqlalchemy import Column, Integer, Boolean, DateTime, String, ForeignKey


# revision identifiers, used by Alembic.
revision = 'deeb7baeda64'
down_revision = '35066b5e4a17'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_members',
        Column('user_id', Integer, ForeignKey('users.user_id'), primary_key=True),
        Column('chat_id', Integer, ForeignKey('chats.chat_id', ondelete="CASCADE"), primary_key=True),
        Column('status', String),
        Column('is_anonymous', Boolean, default=False),
        Column('custom_title', String, default=None),

        # ChatMemberAdministrator
        Column('can_be_edited', Boolean, default=False),
        Column('can_manage_chat', Boolean, default=True),
        Column('can_delete_messages', Boolean, default=False),
        Column('can_manage_video_chats', Boolean, default=False),
        Column('can_restrict_members', Boolean, default=False),
        Column('can_promote_members', Boolean, default=False),
        Column('can_change_info', Boolean, default=False),
        Column('can_invite_users', Boolean, default=False),
        Column('can_post_messages', Boolean, default=False),
        Column('can_edit_messages', Boolean, default=False),
        Column('can_pin_messages', Boolean, default=False),
        Column('can_manage_topics', Boolean, default=False),

        # ChatMemberRestricted
        Column('can_send_messages', Boolean, default=None),
        Column('can_send_audios', Boolean, default=None),
        Column('can_send_documents', Boolean, default=None),
        Column('can_send_photos', Boolean, default=None),
        Column('can_send_videos', Boolean, default=None),
        Column('can_send_video_notes', Boolean, default=None),
        Column('can_send_voice_notes', Boolean, default=None),
        Column('can_send_polls', Boolean, default=None),
        Column('can_send_other_messages', Boolean, default=None),
        Column('can_add_web_page_previews', Boolean, default=None),
        Column('until_date', DateTime, default=None),

        Column('created_on', DateTime),
        Column('updated_on', DateTime),
    )


def downgrade() -> None:
    op.drop_table('chat_members')
