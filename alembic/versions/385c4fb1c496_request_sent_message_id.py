"""request sent message id

Revision ID: 385c4fb1c496
Revises: bbd3d54fc0bc
Create Date: 2023-08-23 14:47:51.272579

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '385c4fb1c496'
down_revision = 'bbd3d54fc0bc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('application_requests', sa.Column('request_sent_message_message_id', sa.Integer))


def downgrade() -> None:
    op.drop_column('application_requests', 'request_sent_message_message_id')
