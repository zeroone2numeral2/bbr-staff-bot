"""accepted message message_id

Revision ID: a2401cf8abfd
Revises: db08018da65e
Create Date: 2023-05-11 17:58:05.311104

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError


# revision identifiers, used by Alembic.
revision = 'a2401cf8abfd'
down_revision = 'db08018da65e'
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
    add_colum_skip_duplicate_column_error('application_requests', sa.Column('accepted_message_message_id', sa.Integer))


def downgrade() -> None:
    op.drop_column('application_requests', 'accepted_message_message_id')
