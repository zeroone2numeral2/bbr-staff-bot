"""event media_type

Revision ID: 77d1bb8d4b94
Revises: 49de6c426ecf
Create Date: 2023-05-08 09:48:50.314027

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '77d1bb8d4b94'
down_revision = '49de6c426ecf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('events', sa.Column('media_type', sa.String))


def downgrade() -> None:
    op.drop_column('events', 'media_type')
