"""user requests

Revision ID: 6d4ec38c37bd
Revises: 20dc88994b13
Create Date: 2023-05-10 14:21:50.360717

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.exc import OperationalError

# revision identifiers, used by Alembic.
revision = '6d4ec38c37bd'
down_revision = '20dc88994b13'
branch_labels = None
depends_on = None


def drop_column_safe(table_name, column_name):
    try:
        op.drop_column(table_name, column_name)
    except OperationalError:
        pass


def upgrade() -> None:
    drop_column_safe('users', 'application_id')
    drop_column_safe('users', 'application_status')
    drop_column_safe('users', 'application_received_on')
    drop_column_safe('users', 'application_evaluated_on')

    # this returns an error: just leave the column there
    # op.drop_column('users', 'application_evaluated_by_user_id')

    op.add_column('users', sa.Column('pending_request_id', sa.Integer))
    op.add_column('users', sa.Column('last_request_id', sa.Integer))
    op.add_column('users', sa.Column('last_request_status', sa.Boolean))


def downgrade() -> None:
    op.add_column('users', sa.Column('application_id', sa.Integer))
    op.add_column('users', sa.Column('application_status', sa.Boolean))
    op.add_column('users', sa.Column('application_received_on', sa.DateTime))
    op.add_column('users', sa.Column('application_evaluated_on', sa.DateTime))

    # dropping this colum returns an error, so we don't need to create it again
    # op.add_column('users', sa.Column('application_evaluated_by_user_id', sa.Integer))

    op.drop_column('users', 'pending_request_id')
    op.drop_column('users', 'last_request_id')
    op.drop_column('users', 'last_request_status')
