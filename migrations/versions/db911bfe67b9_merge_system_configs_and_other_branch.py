"""merge_system_configs_and_other_branch

Revision ID: db911bfe67b9
Revises: 100e8db8a57f, 20260706_add_system_configs_table
Create Date: 2026-07-06 23:09:51.186213

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'db911bfe67b9'
down_revision = ('100e8db8a57f', '20260706_configs')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
