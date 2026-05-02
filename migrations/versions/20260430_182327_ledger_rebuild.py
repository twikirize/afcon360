"""
ledger_rebuild

Create double-entry ledger tables for financial-grade safety.

Revision ID: 20260430_182327
Revises: 
Create Date: 2026-04-30 18:23:27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '20260430_182327'
down_revision = 'fix_compliance_bigint_types'  # Depend on compliance bigint fix
branch_labels = None
depends_on = None


def upgrade():
    # ### Create ENUM types ###
    # Check if types exist before creating
    from sqlalchemy import text
    conn = op.get_bind()
    
    # Check and create entry_type_enum if not exists
    try:
        conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'entry_type_enum'"))
        # Type exists, skip creation
        entry_type_enum = postgresql.ENUM('DEBIT', 'CREDIT', name='entry_type_enum', create_type=True)
    except:
        # Type doesn't exist, create it
        entry_type_enum = postgresql.ENUM('DEBIT', 'CREDIT', name='entry_type_enum')
        entry_type_enum.create(op.get_bind())
    
    # Check and create transaction_type_enum if not exists
    try:
        conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'transaction_type_enum'"))
        # Type exists, skip creation
        transaction_type_enum = postgresql.ENUM(
            'deposit', 'withdraw', 'transfer', 'fee', 'refund', 'adjustment',
            name='transaction_type_enum', create_type=True
        )
    except:
        # Type doesn't exist, create it
        transaction_type_enum = postgresql.ENUM(
            'deposit', 'withdraw', 'transfer', 'fee', 'refund', 'adjustment',
            name='transaction_type_enum'
        )
        transaction_type_enum.create(op.get_bind())
    
    # Check and create transaction_status_enum if not exists
    try:
        conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'transaction_status_enum'"))
        # Type exists, skip creation
        transaction_status_enum = postgresql.ENUM(
            'pending', 'completed', 'failed', 'cancelled',
            name='transaction_status_enum', create_type=True
        )
    except:
        # Type doesn't exist, create it
        transaction_status_enum = postgresql.ENUM(
            'pending', 'completed', 'failed', 'cancelled',
            name='transaction_status_enum'
        )
        transaction_status_enum.create(op.get_bind())

    # ### Create accounts table ###
    op.create_table(
        'accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, default='USD'),
        sa.Column('is_frozen', sa.Boolean(), nullable=False, default=False),
        sa.Column('frozen_reason', sa.Text(), nullable=True),
        sa.Column('frozen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('daily_volume', sa.Numeric(18, 6), nullable=False, default=0),
        sa.Column('daily_volume_reset_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('monthly_volume', sa.Numeric(18, 6), nullable=False, default=0),
        sa.Column('monthly_volume_reset_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'currency', name='uq_accounts_user_currency')
    )
    
    op.create_index('ix_accounts_user_id', 'accounts', ['user_id'])
    op.create_index('ix_accounts_currency', 'accounts', ['currency'])

    # ### Create transactions table ###
    op.create_table(
        'transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('client_request_id', sa.String(255), nullable=False, unique=True),
        sa.Column('tx_type', postgresql.ENUM('deposit', 'withdraw', 'transfer', 'fee', 'refund', 'adjustment', name='transaction_type_enum'), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'completed', 'failed', 'cancelled', name='transaction_status_enum'), nullable=False, default='pending'),
        sa.Column('amount', sa.Numeric(18, 6), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('recipient_user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('external_reference', sa.String(255), nullable=True),
        sa.Column('payment_provider', sa.String(50), nullable=True),
        sa.Column('payment_method', sa.String(50), nullable=True),
        sa.Column('fee_amount', sa.Numeric(18, 6), nullable=True),
        sa.Column('fee_currency', sa.String(10), nullable=True),
        sa.Column('conversion_rate', sa.Numeric(18, 8), nullable=True),
        sa.Column('converted_amount', sa.Numeric(18, 6), nullable=True),
        sa.Column('converted_currency', sa.String(10), nullable=True),
        sa.Column('tx_metadata', postgresql.JSONB(), nullable=True, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
    )
    
    op.create_index('ix_transactions_client_request_id', 'transactions', ['client_request_id'], unique=True)
    op.create_index('ix_transactions_status', 'transactions', ['status'])
    op.create_index('ix_transactions_type', 'transactions', ['tx_type'])
    op.create_index('ix_transactions_created_at', 'transactions', ['created_at'])
    op.create_index('ix_transactions_user_id', 'transactions', ['user_id'])
    op.create_index('ix_transactions_external_ref', 'transactions', ['external_reference'])

    # Add check constraints
    op.create_check_constraint(
        'ck_transaction_amount_positive',
        'transactions',
        'amount > 0'
    )

    # ### Create ledger_entries table ###
    op.create_table(
        'ledger_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transactions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entry_type', postgresql.ENUM('DEBIT', 'CREDIT', name='entry_type_enum'), nullable=False),
        sa.Column('amount', sa.Numeric(18, 6), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False),
        sa.Column('meta', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    op.create_index('ix_ledger_account_id', 'ledger_entries', ['account_id'])
    op.create_index('ix_ledger_transaction_id', 'ledger_entries', ['transaction_id'])
    op.create_index('ix_ledger_currency', 'ledger_entries', ['currency'])
    op.create_index('ix_ledger_created_at', 'ledger_entries', ['created_at'])
    op.create_index('ix_ledger_account_currency', 'ledger_entries', ['account_id', 'currency'])
    
    # Check constraints
    op.create_check_constraint(
        'ck_ledger_amount_positive',
        'ledger_entries',
        'amount > 0'
    )

    # ### Create wallet_audit_logs table ###
    op.create_table(
        'wallet_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transactions.id', ondelete='CASCADE'), nullable=True),
        sa.Column('actor_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('before_state', postgresql.JSONB(), nullable=True, default=dict),
        sa.Column('after_state', postgresql.JSONB(), nullable=True, default=dict),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('request_id', sa.String(100), nullable=True),
        sa.Column('risk_score', sa.Numeric(5, 2), nullable=True),
        sa.Column('aml_flagged', sa.Boolean(), nullable=False, default=False),
        sa.Column('requires_review', sa.Boolean(), nullable=False, default=False),
        sa.Column('audit_metadata', postgresql.JSONB(), nullable=True, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    op.create_index('ix_wallet_audit_transaction_id', 'wallet_audit_logs', ['transaction_id'])
    op.create_index('ix_wallet_audit_actor_id', 'wallet_audit_logs', ['actor_id'])
    op.create_index('ix_wallet_audit_action', 'wallet_audit_logs', ['action'])
    op.create_index('ix_wallet_audit_created_at', 'wallet_audit_logs', ['created_at'])
    op.create_index('ix_wallet_audit_ip_address', 'wallet_audit_logs', ['ip_address'])
    op.create_index('ix_wallet_audit_actor_time', 'wallet_audit_logs', ['actor_id', 'created_at'])

    # ### Create idempotency_keys table ###
    op.create_table(
        'idempotency_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('key_value', sa.String(255), nullable=False, unique=True),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', sa.String(64), nullable=True),
        sa.Column('response_status', sa.Integer(), nullable=True),
        sa.Column('response_body', postgresql.JSONB(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('client_ip', sa.String(45), nullable=True),
    )
    
    op.create_index('ix_idempotency_key_value', 'idempotency_keys', ['key_value'], unique=True)
    op.create_index('ix_idempotency_expires_at', 'idempotency_keys', ['expires_at'])
    op.create_index('ix_idempotency_resource', 'idempotency_keys', ['resource_type', 'resource_id'])

    # ### Backfill existing data ###
    # Note: Create accounts for existing wallet users
    # This is a data migration that should run after schema changes
    op.execute("""
        INSERT INTO accounts (user_id, currency, is_frozen, created_at)
        SELECT DISTINCT user_id, home_currency, FALSE, NOW()
        FROM wallets
        WHERE user_id IS NOT NULL
        ON CONFLICT (user_id, currency) DO NOTHING;
    """)
    
    # Create ledger entries for existing transactions
    op.execute("""
        INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount, currency, created_at)
        SELECT 
            wt.id as transaction_id,
            a.id as account_id,
            CASE 
                WHEN wt.type = 'deposit' THEN 'CREDIT'::entry_type_enum
                WHEN wt.type IN ('withdrawal', 'send') THEN 'DEBIT'::entry_type_enum
                WHEN wt.type = 'receive' THEN 'CREDIT'::entry_type_enum
                ELSE 'CREDIT'::entry_type_enum
            END as entry_type,
            wt.amount,
            wt.currency,
            wt.created_at
        FROM wallet_transactions wt
        JOIN wallets w ON wt.wallet_id = w.id
        JOIN accounts a ON w.user_id = a.user_id
        WHERE w.user_id IS NOT NULL;
    """)

    # ### Add constraints to existing wallets table ###
    # Ensure user_id is unique to prevent duplicate wallet creation
    op.create_unique_constraint('uq_wallets_user_id', 'wallets', ['user_id'])
    
    # Add check constraint to prevent negative balances
    op.create_check_constraint(
        'ck_wallets_balance_home_nonnegative',
        'wallets',
        'balance_home >= 0'
    )
    op.create_check_constraint(
        'ck_wallets_balance_local_nonnegative',
        'wallets',
        'balance_local >= 0'
    )


def downgrade():
    # Drop tables in reverse order
    op.drop_table('idempotency_keys')
    op.drop_table('audit_logs')
    op.drop_table('ledger_entries')
    op.drop_table('transactions')
    op.drop_table('accounts')
    
    # Drop ENUM types
    op.execute('DROP TYPE IF EXISTS entry_type_enum;')
    op.execute('DROP TYPE IF EXISTS transaction_type_enum;')
    op.execute('DROP TYPE IF EXISTS transaction_status_enum;')
    
    # Remove constraints from wallets table
    op.drop_constraint('uq_wallets_user_id', 'wallets', type_='unique')
    op.drop_constraint('ck_wallets_balance_home_nonnegative', 'wallets', type_='check')
    op.drop_constraint('ck_wallets_balance_local_nonnegative', 'wallets', type_='check')
