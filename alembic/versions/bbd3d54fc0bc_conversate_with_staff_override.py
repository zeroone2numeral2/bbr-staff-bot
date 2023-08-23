"""conversate with staff override

Revision ID: bbd3d54fc0bc
Revises: 7a114bd0382a
Create Date: 2023-08-23 13:00:11.493159

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bbd3d54fc0bc'
down_revision = '7a114bd0382a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('conversate_with_staff_override', sa.Boolean))


def downgrade() -> None:
    op.drop_column('users', 'conversate_with_staff_override')
