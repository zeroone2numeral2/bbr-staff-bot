"""create localized texts table

Revision ID: 09a89acc239b
Revises: 3a29d2131c67
Create Date: 2023-03-29 16:30:57.957700

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '09a89acc239b'
down_revision = '3a29d2131c67'
branch_labels = None
depends_on = None

# test


def upgrade() -> None:
    op.create_table(
        'localized_texts',
        sa.Column('key', sa.String, primary_key=True),
        sa.Column('language', sa.String, primary_key=True),
        sa.Column('value', sa.String),
        sa.Column('updated_on', sa.DateTime),
        sa.Column('updated_by', sa.Integer, sa.ForeignKey('users.user_id'))
    )


def downgrade() -> None:
    op.drop_table('localized_texts')
