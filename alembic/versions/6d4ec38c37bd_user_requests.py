"""user requests

Revision ID: 6d4ec38c37bd
Revises: 20dc88994b13
Create Date: 2023-05-10 14:21:50.360717

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6d4ec38c37bd'
down_revision = '20dc88994b13'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('users', 'application_id')
    op.drop_column('users', 'application_status')
    op.drop_column('users', 'application_received_on')
    op.drop_column('users', 'application_evaluated_on')

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
