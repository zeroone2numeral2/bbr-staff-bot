"""event validity notifications

Revision ID: 23304df82140
Revises: 5688af82d59a
Create Date: 2023-09-12 12:38:48.153504

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '23304df82140'
down_revision = '5688af82d59a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('dates_from_hashtags', sa.Boolean))
    op.add_column('events', sa.Column('send_validity_notifications', sa.Boolean))


def downgrade() -> None:
    op.drop_column('events', 'dates_from_hashtags')
    op.drop_column('events', 'send_validity_notifications')
