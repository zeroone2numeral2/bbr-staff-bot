"""evaluation buttons message

Revision ID: 14ed813c8296
Revises: 73b150d0ac4c
Create Date: 2024-02-21 16:59:08.005730

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '14ed813c8296'
down_revision = 'd77e21283ee4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('application_requests', sa.Column('evaluation_buttons_message_chat_id', sa.Integer))
    op.add_column('application_requests', sa.Column('evaluation_buttons_message_message_id', sa.Integer))
    op.add_column('application_requests', sa.Column('evaluation_buttons_message_text_html', sa.String))
    op.add_column('application_requests', sa.Column('evaluation_buttons_message_posted_on', sa.DateTime))
    op.add_column('application_requests', sa.Column('evaluation_buttons_message_json', sa.String))


def downgrade() -> None:
    op.drop_column('application_requests', 'evaluation_buttons_message_chat_id')
    op.drop_column('application_requests', 'evaluation_buttons_message_message_id')
    op.drop_column('application_requests', 'evaluation_buttons_message_text_html')
    op.drop_column('application_requests', 'evaluation_buttons_message_posted_on')
    op.drop_column('application_requests', 'evaluation_buttons_message_json')
