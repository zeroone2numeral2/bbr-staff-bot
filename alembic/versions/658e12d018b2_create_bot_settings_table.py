"""create bot settings table

Revision ID: 658e12d018b2
Revises: 09a89acc239b
Create Date: 2023-03-29 16:52:14.698092

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '658e12d018b2'
down_revision = '09a89acc239b'
branch_labels = None
depends_on = None

# test


def upgrade() -> None:
    op.create_table(
        'bot_settings',
        sa.Column('key', sa.String, primary_key=True),
        sa.Column('value_bool', sa.Boolean),
        sa.Column('value_int', sa.Integer),
        sa.Column('value_float', sa.Float),
        sa.Column('value_str', sa.String),
        sa.Column('value_datetime', sa.DateTime),
        sa.Column('value_date', sa.Date),
        sa.Column('value_type', sa.String),
        sa.Column('updated_on', sa.DateTime),
        sa.Column('updated_by', sa.Integer, sa.ForeignKey('users.user_id'))
    )


def downgrade() -> None:
    op.drop_table('bot_settings')
