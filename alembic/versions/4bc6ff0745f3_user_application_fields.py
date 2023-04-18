"""User application fields

Revision ID: 4bc6ff0745f3
Revises: f5572a024d06
Create Date: 2023-04-18 15:30:41.929796

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4bc6ff0745f3'
down_revision = 'f5572a024d06'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('application_status', sa.Boolean))
    op.add_column('users', sa.Column('application_received_on', sa.DateTime))
    op.add_column('users', sa.Column('application_evaluated_on', sa.DateTime))
    op.add_column('users', sa.Column('application_evaluated_by', sa.Integer))
    op.add_column('users', sa.Column('can_evaluate_applications', sa.Boolean))


def downgrade() -> None:
    op.drop_column('users', 'application_status')
    op.drop_column('users', 'application_received_on')
    op.drop_column('users', 'application_evaluated_on')
    op.drop_column('users', 'application_evaluated_by')
    op.drop_column('users', 'can_evaluate_applications')
