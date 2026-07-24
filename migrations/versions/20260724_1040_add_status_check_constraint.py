"""add status check constraint

Revision ID: 20260724_1040
Revises: 18288f7196e0
Create Date: 2026-07-24 10:30:24.710663

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260724_1040'
down_revision = '18288f7196e0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        'ck_transaction_status_valid',
        'transactions',
        sa.column('status').in_(['pending', 'completed', 'failed', 'cancelled'])
    )


def downgrade():
    op.drop_constraint('ck_transaction_status_valid', 'transactions', type_='check')
