"""
payment_identity_architecture

Implements the frozen Payment Identity Architecture:

1. New table `payment_identities` — separate concept from Account:
   stores PHONE/EMAIL/AFCON360_ID/MERCHANT_CODE identities that RESOLVE
   to an eligible account. Does NOT add phone/email/merchant columns to Account.

2. Backfill `account_number` for every existing account that has NULL.
   Account numbers are stable, human-facing identifiers generated WITHOUT
   reference to internal DB IDs (user_id / org_id / primary key).

This migration does not change balances, ledger history, owner, currency,
account type, or account ID.

Revision ID: f4a1b2c3d5e6
Revises: 5cc5d7b15a1b
"""

import secrets
import string

from alembic import op
import sqlalchemy as sa


revision = 'f4a1b2c3d5e6'
down_revision = '5cc5d7b15a1b'
branch_labels = None
depends_on = None


_ALPHANUM = string.ascii_uppercase + string.digits

_OWNER_PREFIX = {
    'user': 'ACC',
    'organisation': 'ORG',
    'platform': 'PLT',
    'system': 'SYS',
}

_TYPE_ABBR = {
    'revenue': 'REV',
    'escrow': 'ESC',
    'operations': 'OPS',
    'settlement': 'SET',
    'reserve': 'RSV',
    'user_wallet': 'WAL',
    'org_wallet': 'WAL',
}


def _rand(n):
    return ''.join(secrets.choice(_ALPHANUM) for _ in range(n))


def _gen_number(owner_type, currency, account_type):
    prefix = _OWNER_PREFIX.get(owner_type, 'ACC')
    cur = (currency or 'UGX').upper()
    if owner_type in ('platform', 'system'):
        abbr = _TYPE_ABBR.get(account_type or '', 'GEN')
        return f"{prefix}-{abbr}-{cur}-{_rand(4)}"
    return f"{prefix}-{cur}-{_rand(6)}"


def upgrade():
    # ---- 1. Create payment_identities table ----
    op.create_table(
        'payment_identities',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('identity_type', sa.String(20), nullable=False),
        sa.Column('identity_value', sa.String(320), nullable=False),
        sa.Column('normalized_value', sa.String(320), nullable=False),
        sa.Column('owner_type', sa.String(20), nullable=False),
        sa.Column('owner_id', sa.BigInteger, nullable=False),
        sa.Column('account_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_verified', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('is_primary', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('identity_type', 'normalized_value',
                            name='uq_payment_identity_type_normalized'),
    )
    op.create_index('ix_payment_identity_owner', 'payment_identities',
                    ['owner_type', 'owner_id'])
    op.create_index('ix_payment_identity_account', 'payment_identities', ['account_id'])
    op.create_index('ix_payment_identity_normalized', 'payment_identities',
                    ['normalized_value'])

    # ---- 2. Backfill account_number for existing NULL accounts ----
    bind = op.get_bind()
    accounts = bind.execute(
        sa.text(
            "SELECT id, owner_type, currency, account_type, account_number "
            "FROM accounts WHERE account_number IS NULL"
        )
    ).fetchall()

    for acc_id, owner_type, currency, account_type, _ in accounts:
        candidate = None
        for _attempt in range(10):
            candidate = _gen_number(owner_type, currency, account_type)
            exists = bind.execute(
                sa.text("SELECT 1 FROM accounts WHERE account_number = :an"),
                {'an': candidate}
            ).first()
            if not exists:
                break
        bind.execute(
            sa.text("UPDATE accounts SET account_number = :an WHERE id = :aid"),
            {'an': candidate, 'aid': acc_id}
        )


def downgrade():
    op.drop_index('ix_payment_identity_normalized', table_name='payment_identities')
    op.drop_index('ix_payment_identity_account', table_name='payment_identities')
    op.drop_index('ix_payment_identity_owner', table_name='payment_identities')
    op.drop_table('payment_identities')
    # NOTE: backfilled account_number values are intentionally left in place;
    # they are harmless stable identifiers and reverting them is not required.
