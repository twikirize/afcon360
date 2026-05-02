"""
Add FX rate and transaction tables for multi-currency support.

Revision ID: add_fx_tables
Revises: 20260430_182327
Create Date: 2026-05-01 00:40:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_fx_tables'
down_revision = '20260430_182327'
branch_labels = None
depends_on = None


def upgrade():
    # Create fx_rates table
    op.create_table(
        'fx_rates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('base_currency', sa.String(length=3), nullable=False),
        sa.Column('quote_currency', sa.String(length=3), nullable=False),
        sa.Column('rate', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('spread', sa.Numeric(precision=10, scale=6), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('base_currency', 'quote_currency', name='uq_fx_pair')
    )
    op.create_index(op.f('ix_fx_rates_base_currency'), 'fx_rates', ['base_currency'], unique=False)
    op.create_index(op.f('ix_fx_rates_quote_currency'), 'fx_rates', ['quote_currency'], unique=False)
    op.create_index('idx_fx_pair_timestamp', 'fx_rates', ['base_currency', 'quote_currency', 'timestamp'], unique=False)
    op.create_index(op.f('ix_fx_rates_timestamp'), 'fx_rates', ['timestamp'], unique=False)

    # Create fx_transactions table
    op.create_table(
        'fx_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source_currency', sa.String(length=3), nullable=False),
        sa.Column('source_amount', sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column('source_account_id', sa.Integer(), nullable=False),
        sa.Column('dest_currency', sa.String(length=3), nullable=False),
        sa.Column('dest_amount', sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column('dest_account_id', sa.Integer(), nullable=False),
        sa.Column('fx_rate', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('fx_source', sa.String(length=50), nullable=False),
        sa.Column('spread', sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column('platform_fee', sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_id')
    )
    op.create_index(op.f('ix_fx_transactions_user_id'), 'fx_transactions', ['user_id'], unique=False)
    op.create_index('idx_fx_user_status', 'fx_transactions', ['user_id', 'status'], unique=False)
    op.create_index(op.f('ix_fx_transactions_created_at'), 'fx_transactions', ['created_at'], unique=False)


def downgrade():
    op.drop_index('idx_fx_user_status', table_name='fx_transactions')
    op.drop_index(op.f('ix_fx_transactions_created_at'), table_name='fx_transactions')
    op.drop_index(op.f('ix_fx_transactions_user_id'), table_name='fx_transactions')
    op.drop_table('fx_transactions')
    
    op.drop_index('idx_fx_pair_timestamp', table_name='fx_rates')
    op.drop_index(op.f('ix_fx_rates_timestamp'), table_name='fx_rates')
    op.drop_index(op.f('ix_fx_rates_quote_currency'), table_name='fx_rates')
    op.drop_index(op.f('ix_fx_rates_base_currency'), table_name='fx_rates')
    op.drop_table('fx_rates')
