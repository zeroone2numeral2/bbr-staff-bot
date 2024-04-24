"""evaluation message button deleted

Revision ID: a46f8722a14c
Revises: 14ed813c8296
Create Date: 2024-03-20 12:54:24.578056

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a46f8722a14c'
down_revision = '14ed813c8296'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('application_requests', sa.Column('evaluation_buttons_message_deleted', sa.Boolean))


def downgrade() -> None:
    op.drop_column('application_requests', 'evaluation_buttons_message_deleted')
