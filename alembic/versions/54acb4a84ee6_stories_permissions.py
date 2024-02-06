"""stories permissions

Revision ID: 54acb4a84ee6
Revises: 82e272ea8f42
Create Date: 2024-02-06 17:41:12.160208

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '54acb4a84ee6'
down_revision = '82e272ea8f42'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chat_members', sa.Column('can_post_stories', sa.Boolean))
    op.add_column('chat_members', sa.Column('can_edit_stories', sa.Boolean))
    op.add_column('chat_members', sa.Column('can_delete_stories', sa.Boolean))


def downgrade() -> None:
    op.drop_column('chat_members', 'can_post_stories')
    op.drop_column('chat_members', 'can_edit_stories')
    op.drop_column('chat_members', 'can_delete_stories')
