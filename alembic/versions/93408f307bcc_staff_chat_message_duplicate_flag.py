"""staff chat message duplicate flag

Revision ID: 93408f307bcc
Revises: 54acb4a84ee6
Create Date: 2024-02-14 09:48:25.257284

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '93408f307bcc'
down_revision = '54acb4a84ee6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('staff_chat_messages', sa.Column('duplicate', sa.Boolean))


def downgrade() -> None:
    op.drop_column('staff_chat_messages', 'duplicate')
