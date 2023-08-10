"""application request invite link

Revision ID: 2122562bb66b
Revises: 4d76bf9221a4
Create Date: 2023-05-10 15:53:27.495919

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError


# revision identifiers, used by Alembic.
revision = '2122562bb66b'
down_revision = '4d76bf9221a4'
branch_labels = None
depends_on = None


def add_colum_skip_duplicate_column_error(table_name, column):
    try:
        op.add_column(table_name, column)
    except OperationalError as operational_error:
        if "duplicate column name" in str(operational_error):
            return
        raise operational_error


def upgrade() -> None:
    add_colum_skip_duplicate_column_error('application_requests', sa.Column('invite_link', sa.String))
    add_colum_skip_duplicate_column_error('application_requests', sa.Column('invite_link_can_be_revoked_after_join', sa.Boolean))
    add_colum_skip_duplicate_column_error('application_requests', sa.Column('invite_link_revoked', sa.Boolean))


def downgrade() -> None:
    op.drop_column('application_requests', 'invite_link')
    op.drop_column('application_requests', 'invite_link_can_be_revoked_after_join')
    op.drop_column('application_requests', 'invite_link_revoked')
