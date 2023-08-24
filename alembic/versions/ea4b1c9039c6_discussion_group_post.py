"""discussion group post

Revision ID: ea4b1c9039c6
Revises: 385c4fb1c496
Create Date: 2023-08-24 09:33:08.973780

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ea4b1c9039c6'
down_revision = '385c4fb1c496'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('discussion_group_chat_id', sa.Integer))
    op.add_column('events', sa.Column('discussion_group_message_id', sa.Integer))
    op.add_column('events', sa.Column('discussion_group_received_on', sa.DateTime))
    op.add_column('events', sa.Column('discussion_group_message_json', sa.String))


def downgrade() -> None:
    op.drop_column('events', 'discussion_group_chat_id')
    op.drop_column('events', 'discussion_group_message_id')
    op.drop_column('events', 'discussion_group_received_on')
    op.drop_column('events', 'discussion_group_message_json')
