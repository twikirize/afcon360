"""add auth configuration table

Revision ID: add_auth_configuration
Revises: 526b870ba631
Create Date: 2026-05-04 01:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_auth_configuration'
down_revision = '526b870ba631'
branch_labels = None
depends_on = None


def upgrade():
    # Create auth_configurations table
    op.create_table(
        'auth_configurations',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('google_oauth_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('google_client_id', sa.String(length=255), nullable=True),
        sa.Column('google_client_secret', sa.String(length=255), nullable=True),
        sa.Column('sendgrid_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sendgrid_api_key', sa.String(length=255), nullable=True),
        sa.Column('sendgrid_from_email', sa.String(length=255), nullable=True),
        sa.Column('sendgrid_from_name', sa.String(length=255), server_default='AFCON360', nullable=True),
        sa.Column('twilio_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('twilio_account_sid', sa.String(length=255), nullable=True),
        sa.Column('twilio_auth_token', sa.String(length=255), nullable=True),
        sa.Column('twilio_phone_number', sa.String(length=255), nullable=True),
        sa.Column('africa_talking_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('africa_talking_username', sa.String(length=255), nullable=True),
        sa.Column('africa_talking_api_key', sa.String(length=255), nullable=True),
        sa.Column('sms_provider_preference', sa.String(length=50), server_default='auto', nullable=False),
        sa.Column('african_countries', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('email_verification_required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('phone_verification_required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('google_oauth_required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('kyc_required_for_tier_2', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('kyc_required_for_tier_3', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('allow_email_password_signup', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('allow_google_oauth_signup', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_verification_rate_limit', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('sms_verification_rate_limit', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_by', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Insert default configuration
    op.execute("""
        INSERT INTO auth_configurations (
            google_oauth_enabled, sendgrid_enabled, twilio_enabled, africa_talking_enabled,
            sms_provider_preference, african_countries, email_verification_required,
            phone_verification_required, google_oauth_required, kyc_required_for_tier_2,
            kyc_required_for_tier_3, allow_email_password_signup, allow_google_oauth_signup,
            email_verification_rate_limit, sms_verification_rate_limit
        ) VALUES (
            true, true, false, false,
            'auto', '["UG", "KE", "TZ", "RW", "BI", "CD", "SS", "ET", "SO", "DZ", "AO", "BW", "NA", "ZA", "ZW", "ZM", "MW", "MZ", "NG", "GH", "CI", "SN", "ML", "BF", "NE", "TD", "SD", "LY", "EG", "MA", "TN"]',
            false, false, false, true, true, true, true, 5, 3
        )
    """)


def downgrade():
    op.drop_table('auth_configurations')
