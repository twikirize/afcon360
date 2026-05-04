"""add_verified_column_to_accounts

Revision ID: 326afa83a2fa
Revises: bd22abbdba18
Create Date: 2026-05-03 23:38:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '326afa83a2fa'
down_revision = 'bd22abbdba18'
branch_labels = None
depends_on = None


def upgrade():
    # First add the column as nullable (allow NULLs)
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('verified', sa.Boolean(), nullable=True))
    
    # Set default value for existing rows (assume existing wallets are verified)
    op.execute("UPDATE accounts SET verified = true WHERE verified IS NULL")
    
    # Now alter the column to be NOT NULL with default false
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.alter_column('verified', 
                              existing_type=sa.Boolean(),
                              nullable=False, 
                              server_default='false')


def downgrade():
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_column('verified')