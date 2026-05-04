"""Add owner_type and terms_accepted_at to accounts table

Revision ID: 526b870ba631
Revises: 326afa83a2fa
Create Date: 2026-05-04 00:22:10.627066

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '526b870ba631'
down_revision = '326afa83a2fa'
branch_labels = None
depends_on = None


def upgrade():
    # Create enum type for owner_type with uppercase values to match Python enum
    account_owner_type_enum = sa.Enum('USER', 'ORGANISATION', name='account_owner_type_enum', create_type=True)
    account_owner_type_enum.create(op.get_bind(), checkfirst=True)
    
    # Add owner_type column with default value 'USER' for existing records
    op.add_column('accounts', sa.Column('owner_type', account_owner_type_enum, nullable=False, server_default='USER'))
    
    # Add terms_accepted_at column
    op.add_column('accounts', sa.Column('terms_accepted_at', sa.DateTime(timezone=True), nullable=True))
    
    # Create index on owner_type
    op.create_index('ix_accounts_owner_type', 'accounts', ['owner_type'])


def downgrade():
    # Remove index on owner_type
    op.drop_index('ix_accounts_owner_type', table_name='accounts')
    
    # Remove terms_accepted_at column
    op.drop_column('accounts', 'terms_accepted_at')
    
    # Remove owner_type column
    op.drop_column('accounts', 'owner_type')
    
    # Drop enum type
    sa.Enum(name='account_owner_type_enum').drop(op.get_bind(), checkfirst=True)
