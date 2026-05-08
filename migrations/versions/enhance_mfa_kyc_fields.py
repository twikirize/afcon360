"""Enhance MFA and KYC fields

Revision ID: enhance_mfa_kyc_fields
Revises: 9a90ef638142
Create Date: 2025-05-07 17:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'enhance_mfa_kyc_fields'
down_revision = '9a90ef638142'
branch_labels = None
depends_on = None


def upgrade():
    # Enhance MFASecret table
    op.add_column('mfa_secrets', sa.Column('backup_codes', sa.Text(), nullable=True))
    op.add_column('mfa_secrets', sa.Column('device_name', sa.String(length=100), nullable=True))
    op.add_column('mfa_secrets', sa.Column('last_used', sa.DateTime(), nullable=True))
    op.add_column('mfa_secrets', sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False))
    
    # Enhance KycRecord table
    op.add_column('kyc_records', sa.Column('expiry_date', sa.DateTime(), nullable=True))
    op.add_column('kyc_records', sa.Column('enhanced_risk_score', sa.Float(), server_default=sa.text('0.0'), nullable=True))
    op.add_column('kyc_records', sa.Column('risk_factors', sa.JSON(), server_default=sa.text('[]'), nullable=True))
    op.add_column('kyc_records', sa.Column('aml_screened', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('kyc_records', sa.Column('pep_screened', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('kyc_records', sa.Column('sanctions_screened', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    
    # Add indexes for performance
    op.create_index('ix_mfa_secrets_user_active', 'mfa_secrets', ['user_id', 'is_active'])
    op.create_index('ix_kyc_records_expiry', 'kyc_records', ['expiry_date'])
    op.create_index('ix_kyc_records_risk', 'kyc_records', ['enhanced_risk_score'])


def downgrade():
    # Remove indexes
    op.drop_index('ix_kyc_records_risk', table_name='kyc_records')
    op.drop_index('ix_kyc_records_expiry', table_name='kyc_records')
    op.drop_index('ix_mfa_secrets_user_active', table_name='mfa_secrets')
    
    # Remove enhanced KycRecord columns
    op.drop_column('kyc_records', 'sanctions_screened')
    op.drop_column('kyc_records', 'pep_screened')
    op.drop_column('kyc_records', 'aml_screened')
    op.drop_column('kyc_records', 'risk_factors')
    op.drop_column('kyc_records', 'enhanced_risk_score')
    op.drop_column('kyc_records', 'expiry_date')
    
    # Remove enhanced MFASecret columns
    op.drop_column('mfa_secrets', 'created_at')
    op.drop_column('mfa_secrets', 'last_used')
    op.drop_column('mfa_secrets', 'device_name')
    op.drop_column('mfa_secrets', 'backup_codes')
