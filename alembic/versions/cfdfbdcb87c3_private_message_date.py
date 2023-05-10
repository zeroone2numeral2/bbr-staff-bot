"""private_message date

Revision ID: cfdfbdcb87c3
Revises: 77d1bb8d4b94
Create Date: 2023-05-10 13:44:02.471486

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cfdfbdcb87c3'
down_revision = '77d1bb8d4b94'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('private_chat_messages', sa.Column('date', sa.DateTime))


def downgrade() -> None:
    op.drop_column('private_chat_messages', 'date')
