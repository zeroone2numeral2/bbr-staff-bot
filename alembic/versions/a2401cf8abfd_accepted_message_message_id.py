"""accepted message message_id

Revision ID: a2401cf8abfd
Revises: db08018da65e
Create Date: 2023-05-11 17:58:05.311104

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2401cf8abfd'
down_revision = 'db08018da65e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('application_requests', sa.Column('accepted_message_message_id', sa.Integer))


def downgrade() -> None:
    op.drop_column('application_requests', 'accepted_message_message_id')
