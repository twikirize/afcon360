from datetime import datetime
from sqlalchemy import UniqueConstraint, Index
from app.extensions import db


class Wallet(db.Model):
    """
    A wallet that can belong to either a User or an Organisation.
    Each owner can have exactly one wallet.
    """
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_wallet_user"),
        UniqueConstraint("organisation_id", name="uq_wallet_org"),
        Index("ix_wallets_currency_pair", "home_currency", "local_currency"),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    # Explicit ownership
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    organisation_id = db.Column(db.BigInteger, db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True, index=True)

    # Wallet metadata
    home_currency = db.Column(db.String(10), nullable=False, default="USD")
    local_currency = db.Column(db.String(10), nullable=False, default="UGX")
    nationality = db.Column(db.String(5), default="UG")
    location = db.Column(db.String(5), default="UG")
    verified = db.Column(db.Boolean, nullable=False, default=False)

    # Add these to the Wallet class (after the 'verified' column)

    # Public identifier
    wallet_ref = db.Column(db.String(32), unique=True, nullable=True)

    # Freeze functionality
    is_frozen = db.Column(db.Boolean, nullable=False, default=False)
    frozen_reason = db.Column(db.Text, nullable=True)
    frozen_at = db.Column(db.DateTime, nullable=True)

    # Daily volume tracking
    daily_volume_home = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    daily_volume_local = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    daily_volume_reset_at = db.Column(db.DateTime, nullable=True)

    # Monthly volume tracking
    monthly_volume_home = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    monthly_volume_local = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    monthly_volume_reset_at = db.Column(db.DateTime, nullable=True)

    # Reconciliation
    last_reconciliation_at = db.Column(db.DateTime, nullable=True)

    # Balances
    balance_home = db.Column(db.Numeric(18, 2), nullable=False, default=0)
    balance_local = db.Column(db.Numeric(18, 2), nullable=False, default=0)

    # Optimistic lock + lifecycle
    version = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = db.relationship("User", back_populates="wallet", uselist=False)
    organisation = db.relationship("Organisation", back_populates="wallet", uselist=False)


    def generate_wallet_ref(self):
        """Generate unique public wallet reference."""
        import secrets
        self.wallet_ref = f"wal_{secrets.token_urlsafe(16)}"

    def __repr__(self):
        return f"<Wallet id={self.id} user_id={self.user_id} org_id={self.organisation_id}>"


class Transaction(db.Model):
    """
    Immutable transaction ledger for a wallet.
    """
    __tablename__ = "wallet_transactions"
    __table_args__ = (
        Index("ix_wallet_tx_wallet_id", "wallet_id"),
        Index("ix_wallet_tx_type_currency", "type", "currency"),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    wallet_id = db.Column(db.BigInteger, db.ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)

    # Identifiers
    tx_id = db.Column(db.String(64), index=True, nullable=True)
    client_request_id = db.Column(db.String(128), index=True, nullable=True)

    # Transaction details
    type = db.Column(db.String(40), nullable=False)  # deposit, withdraw, transfer
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    meta = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationship back to wallet
    wallet = db.relationship(
        "Wallet",
        backref=db.backref("transactions", lazy="dynamic", cascade="all, delete-orphan"),
        lazy="joined",
    )

    def __repr__(self):
        return f"<Transaction id={self.id} wallet_id={self.wallet_id} type={self.type} amount={self.amount} {self.currency}>"


# ============================================================================
# NEW MODELS - Add at bottom of existing models.py
# ============================================================================

class AgentCommission(db.Model):
    """Agent commission tracking - replaces in-memory agent_tracker.py"""
    __tablename__ = "agent_commissions"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    commission_ref = db.Column(db.String(64), unique=True, nullable=False)
    agent_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    source_type = db.Column(db.String(30), nullable=False)  # peer_transfer, withdrawal, deposit
    source_id = db.Column(db.String(64), nullable=False)
    recipient_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending, paid, cancelled
    paid_at = db.Column(db.DateTime, nullable=True)
    paid_by = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    extra_data = db.Column(db.JSON, nullable=True, default=dict)  # renamed: 'metadata' is reserved by SQLAlchemy
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_agent_commissions_agent', 'agent_id'),
        Index('ix_agent_commissions_status', 'status'),
        Index('ix_agent_commissions_source', 'source_type', 'source_id'),
    )

    def __repr__(self):
        return f"<AgentCommission {self.commission_ref} agent={self.agent_id} amount={self.amount}>"


class PayoutRequest(db.Model):
    """Agent payout requests - replaces in-memory agent_payouts.py"""
    __tablename__ = "payout_requests"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    request_ref = db.Column(db.String(64), unique=True, nullable=False)
    agent_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    payment_method = db.Column(db.String(30), nullable=False)  # bank, mobile_money, cash
    payment_details = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending, approved, rejected, paid
    approved_by = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    paid_by = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_payout_requests_agent', 'agent_id'),
        Index('ix_payout_requests_status', 'status'),
    )

    def __repr__(self):
        return f"<PayoutRequest {self.request_ref} agent={self.agent_id} amount={self.amount}>"


class LedgerEntry(db.Model):
    """Double-entry ledger for audit and reconciliation"""
    __tablename__ = "ledger_entries"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    entry_ref = db.Column(db.String(64), unique=True, nullable=False)
    transaction_id = db.Column(db.BigInteger, db.ForeignKey("wallet_transactions.id", ondelete="CASCADE"),
                               nullable=False)
    wallet_id = db.Column(db.BigInteger, db.ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    entry_type = db.Column(db.String(20), nullable=False)  # debit, credit
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    balance_before = db.Column(db.Numeric(18, 2), nullable=False)
    balance_after = db.Column(db.Numeric(18, 2), nullable=False)
    counterparty_wallet_id = db.Column(db.BigInteger, db.ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True)
    description = db.Column(db.Text, nullable=True)
    extra_data = db.Column(db.JSON, nullable=True, default=dict)  # renamed: 'metadata' is reserved by SQLAlchemy
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_ledger_entries_wallet', 'wallet_id'),
        Index('ix_ledger_entries_transaction', 'transaction_id'),
        Index('ix_ledger_entries_type', 'entry_type'),
    )

    def __repr__(self):
        return f"<LedgerEntry {self.entry_ref} {self.entry_type} {self.amount}>"


class IdempotencyKey(db.Model):
    """Idempotency keys for duplicate request prevention"""
    __tablename__ = "idempotency_keys"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    key_value = db.Column(db.String(128), unique=True, nullable=False)
    resource_type = db.Column(db.String(50), nullable=False)  # deposit, withdraw, transfer
    resource_id = db.Column(db.String(64), nullable=True)  # transaction_id after processing
    response_cache = db.Column(db.JSON, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_idempotency_keys_expiry', 'expires_at'),
        Index('ix_idempotency_keys_resource', 'resource_type', 'resource_id'),
    )

    def __repr__(self):
        return f"<IdempotencyKey {self.key_value} type={self.resource_type}>"