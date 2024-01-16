"""request folder link

Revision ID: 82e272ea8f42
Revises: f6980505a3af
Create Date: 2024-01-16 10:44:48.982055

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '82e272ea8f42'
down_revision = 'f6980505a3af'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('application_requests', sa.Column('folder_link', sa.String))


def downgrade() -> None:
    op.drop_column('application_requests', 'folder_link')
