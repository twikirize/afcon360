"""Create payment configuration tables

Revision ID: create_payment_config_tables
Revises: 9a90ef638142
Create Date: 2026-05-10 03:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'create_payment_config_tables'
down_revision = '9a90ef638142'
branch_labels = None
depends_on = None


def upgrade():
    # Create payment_method_configs table
    op.create_table('payment_method_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('method_id', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('method_type', sa.String(length=50), nullable=False),
        sa.Column('provider_name', sa.String(length=50), nullable=False),
        sa.Column('country_code', sa.String(length=2), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('requires_phone', sa.Boolean(), nullable=False),
        sa.Column('api_key', sa.String(length=255), nullable=True),
        sa.Column('api_secret', sa.String(length=255), nullable=True),
        sa.Column('sandbox_url', sa.String(length=255), nullable=True),
        sa.Column('production_url', sa.String(length=255), nullable=True),
        sa.Column('use_sandbox', sa.Boolean(), nullable=False),
        sa.Column('supported_currencies', sa.JSON(), nullable=True),
        sa.Column('min_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('max_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('transaction_fee', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('config_json', sa.JSON(), nullable=True),
        sa.Column('last_tested_at', sa.DateTime(), nullable=True),
        sa.Column('last_test_result', sa.String(length=20), nullable=True),
        sa.Column('last_error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('method_id')
    )
    op.create_index(op.f('ix_payment_method_configs_method_id'), 'payment_method_configs', ['method_id'], unique=False)
    
    # Create event_payment_preferences table
    op.create_table('event_payment_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('accepted_methods', sa.JSON(), nullable=True),
        sa.Column('preferred_currency', sa.String(length=3), nullable=False),
        sa.Column('auto_convert_wallet', sa.Boolean(), nullable=False),
        sa.Column('wallet_conversion_rate', sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column('payment_settings', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_event_payment_preferences_event_id'), 'event_payment_preferences', ['event_id'], unique=False)
    op.create_index(op.f('ix_event_payment_preferences_user_id'), 'event_payment_preferences', ['user_id'], unique=False)


def downgrade():
    # Drop tables
    op.drop_index(op.f('ix_event_payment_preferences_user_id'), table_name='event_payment_preferences')
    op.drop_index(op.f('ix_event_payment_preferences_event_id'), table_name='event_payment_preferences')
    op.drop_table('event_payment_preferences')
    op.drop_index(op.f('ix_payment_method_configs_method_id'), table_name='payment_method_configs')
    op.drop_table('payment_method_configs')
