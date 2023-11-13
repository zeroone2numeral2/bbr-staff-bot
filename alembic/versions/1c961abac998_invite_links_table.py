"""invite links table

Revision ID: 1c961abac998
Revises: 9a83b2eb2e04
Create Date: 2023-11-13 18:14:40.775679

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1c961abac998'
down_revision = '9a83b2eb2e04'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'invite_links',
        sa.Column('link_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('chat_id', sa.Integer, sa.ForeignKey('chats.chat_id')),
        sa.Column('destination', sa.String),
        sa.Column('created_on', sa.DateTime),
        sa.Column('used_by_user_id', sa.Integer),
        sa.Column('used_on', sa.DateTime),
        sa.Column('sent_to_user_user_id', sa.Integer),
        sa.Column('sent_to_user_message_id', sa.Integer),
        sa.Column('sent_to_user_message_ids_to_delete', sa.String),
        sa.Column('sent_to_user_via_reply_markup', sa.Boolean),
        sa.Column('sent_to_user_link_removed', sa.Boolean),
        sa.Column('sent_to_user_on', sa.DateTime),
        sa.Column('invite_link', sa.String),
        sa.Column('creator_user_id', sa.Integer),
        sa.Column('creates_join_request', sa.Boolean),
        sa.Column('is_primary', sa.Boolean),
        sa.Column('name', sa.String),
        sa.Column('expire_date', sa.DateTime),
        sa.Column('member_limit', sa.Integer),
        sa.Column('pending_join_request_count', sa.Integer),
        sa.Column('can_be_revoked', sa.Boolean),
        sa.Column('revoked_on', sa.DateTime)
    )


def downgrade() -> None:
    op.drop_table('invite_links')
