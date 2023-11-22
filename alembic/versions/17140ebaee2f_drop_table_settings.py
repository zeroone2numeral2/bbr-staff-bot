"""drop table settings

Revision ID: 17140ebaee2f
Revises: 658e12d018b2
Create Date: 2023-03-29 19:28:29.193132

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '17140ebaee2f'
down_revision = '658e12d018b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('settings')


def downgrade() -> None:
    op.create_table(
        'settings',
        sa.Column('key', sa.String, primary_key=True),
        sa.Column('language', sa.String, primary_key=True),
        sa.Column('value', sa.String),
        sa.Column('updated_on', sa.DateTime),
        sa.Column('updated_by', sa.Integer, sa.ForeignKey('users.user_id'))
    )
