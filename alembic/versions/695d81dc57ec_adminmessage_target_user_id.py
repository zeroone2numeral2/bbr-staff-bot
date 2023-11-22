"""AdminMessage target user_id

Revision ID: 695d81dc57ec
Revises: 1127a7ab5014
Create Date: 2023-11-09 09:33:05.630941

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '695d81dc57ec'
down_revision = '1127a7ab5014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('admin_messages', sa.Column('target_user_id', sa.Integer))
    op.alter_column('admin_messages', column_name='user_id', new_column_name='staff_user_id')


def downgrade() -> None:
    op.drop_column('admin_messages', 'target_user_id')
    op.alter_column('admin_messages', column_name='staff_user_id', new_column_name='user_id')
