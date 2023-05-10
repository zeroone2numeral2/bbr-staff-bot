"""application request invite link

Revision ID: 2122562bb66b
Revises: 4d76bf9221a4
Create Date: 2023-05-10 15:53:27.495919

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2122562bb66b'
down_revision = '4d76bf9221a4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('application_requests', sa.Column('invite_link', sa.String))
    op.add_column('application_requests', sa.Column('invite_link_can_be_revoked_after_join', sa.Boolean))
    op.add_column('application_requests', sa.Column('invite_link_revoked', sa.Boolean))


def downgrade() -> None:
    op.drop_column('application_requests', 'invite_link')
    op.drop_column('application_requests', 'invite_link_can_be_revoked_after_join')
    op.drop_column('application_requests', 'invite_link_revoked')
