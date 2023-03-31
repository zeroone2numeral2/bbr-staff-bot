"""chat destination type

Revision ID: 379ef134c45c
Revises: 17140ebaee2f
Create Date: 2023-03-31 12:04:10.732407

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '379ef134c45c'
down_revision = '17140ebaee2f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chats', sa.Column('is_staff_chat', sa.Boolean, default=False))
    op.add_column('chats', sa.Column('is_users_chat', sa.Boolean, default=False))


def downgrade() -> None:
    op.drop_column('chats', 'is_staff_chat')
    op.drop_column('chats', 'is_users_chat')
