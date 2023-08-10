"""staff and log message text

Revision ID: 4d76bf9221a4
Revises: 6d4ec38c37bd
Create Date: 2023-05-10 15:19:19.902963

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError


# revision identifiers, used by Alembic.
revision = '4d76bf9221a4'
down_revision = '6d4ec38c37bd'
branch_labels = None
depends_on = None


def add_colum_skip_duplicate_column_error(table_name, column):
    try:
        op.add_column(table_name, column)
    except OperationalError as operational_error:
        if "duplicate column name" in str(operational_error.detail):
            return
        raise operational_error


def upgrade() -> None:
    add_colum_skip_duplicate_column_error('application_requests', sa.Column('staff_message_text_html', sa.String))
    add_colum_skip_duplicate_column_error('application_requests', sa.Column('log_message_text_html', sa.String))


def downgrade() -> None:
    op.drop_column('application_requests', 'staff_message_text_html')
    op.drop_column('application_requests', 'log_message_text_html')
