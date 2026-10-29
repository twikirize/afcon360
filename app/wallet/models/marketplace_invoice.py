"""
Wallet-owned marketplace invoices/payment intents.

An invoice is an obligation, not a transaction: creating one never moves money.
Transactions and ledger entries remain the canonical record after collection.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Numeric,
    String, UniqueConstraint, PrimaryKeyConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db


class MarketplacePaymentAttempt(db.Model):
    """Individual payment attempt for a marketplace invoice.
    
    Each attempt is recorded regardless of outcome. This enables audit trail,
    retry handling, and provider callback verification without duplicating
    the canonical ledger. A successful attempt creates a Wallet transaction
    and an allocation linking the transaction to the invoice.
    """
    __tablename__ = "wallet_marketplace_payment_attempts"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_wallet_marketplace_payment_attempts"),
        CheckConstraint(
            "amount > 0", name="ck_marketplace_attempt_amount_positive"
        ),
        CheckConstraint(
            "status IN ('created', 'pending', 'requires_action', 'succeeded', 'failed', 'cancelled', 'expired')",
            name="ck_marketplace_attempt_status_valid",
        ),
        Index(
            "ix_wallet_marketplace_attempt_invoice",
            "invoice_id",
        ),
        Index(
            "ix_wallet_marketplace_attempt_provider_ref",
            "provider_reference",
        ),
        Index(
            "ix_wallet_marketplace_attempt_status_created",
            "status", "created_at",
        ),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey(
            "wallet_marketplace_invoices.id",
            name="fk_marketplace_attempt_invoice",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    attempt_number = db.Column(db.Integer, nullable=False, default=1)
    amount = db.Column(Numeric(18, 6), nullable=False)
    currency = db.Column(String(10), nullable=False)
    payment_method = db.Column(String(50), nullable=False)
    provider_name = db.Column(String(50), nullable=True)
    provider_reference = db.Column(String(255), nullable=True)
    status = db.Column(
        String(24), nullable=False, default="created", server_default="created",
    )
    idempotency_key = db.Column(String(255), nullable=True)
    error_code = db.Column(String(50), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    attempt_metadata = db.Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at = db.Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )
    updated_at = db.Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at = db.Column(DateTime(timezone=True), nullable=True)

    invoice = db.relationship("MarketplaceInvoice", backref=db.backref(
        "payment_attempts", lazy="dynamic", order_by="MarketplacePaymentAttempt.attempt_number"
    ))

    def __repr__(self):
        return (
            f"<MarketplacePaymentAttempt {self.id} invoice={self.invoice_id}"
            f" #{self.attempt_number} {self.amount} {self.currency} {self.status}>"
        )


class MarketplaceAllocation(db.Model):
    """Allocation of a successful payment transaction to an invoice.
    
    This enables partial payments, multiple payment sources, and precise
    tracking of how much of each transaction satisfies the invoice.
    The sum of allocations for an invoice must not exceed the invoice amount.
    """
    __tablename__ = "wallet_marketplace_allocations"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_wallet_marketplace_allocations"),
        CheckConstraint(
            "amount > 0", name="ck_marketplace_allocation_amount_positive"
        ),
        UniqueConstraint(
            "transaction_id", "invoice_id",
            name="uq_marketplace_allocation_transaction_invoice",
        ),
        Index(
            "ix_wallet_marketplace_allocation_invoice",
            "invoice_id",
        ),
        Index(
            "ix_wallet_marketplace_allocation_transaction",
            "transaction_id",
        ),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey(
            "transactions.id",
            name="fk_marketplace_allocation_transaction",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    invoice_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey(
            "wallet_marketplace_invoices.id",
            name="fk_marketplace_allocation_invoice",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    amount = db.Column(Numeric(18, 6), nullable=False)
    currency = db.Column(String(10), nullable=False)
    allocation_metadata = db.Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at = db.Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    invoice = db.relationship("MarketplaceInvoice", backref=db.backref(
        "allocations", lazy="dynamic")
    )

    def __repr__(self):
        return (
            f"<MarketplaceAllocation {self.id} txn={self.transaction_id}"
            f" invoice={self.invoice_id} {self.amount} {self.currency}>"
        )


class MarketplaceInvoice(db.Model):
    """One immutable-price payment obligation for a marketplace service."""

    __tablename__ = "wallet_marketplace_invoices"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_wallet_marketplace_invoices"),
        CheckConstraint("amount > 0", name="ck_marketplace_invoice_amount_positive"),
        CheckConstraint(
            "status IN ('pending', 'due', 'paid', 'cash_received', "
            "'failed', 'cancelled', 'refunded', 'partially_paid', "
            "'partially_refunded', 'refund_pending')",
            name="ck_marketplace_invoice_status_valid",
        ),
        CheckConstraint(
            "settlement_timing IN ('pay_on_completion', 'pay_now', "
            "'deposit', 'pay_on_arrival')",
            name="ck_marketplace_invoice_timing_valid",
        ),
        UniqueConstraint(
            "idempotency_key", name="uq_wallet_marketplace_invoice_idempotency",
        ),
        UniqueConstraint(
            "service_code", "service_reference",
            name="uq_marketplace_invoice_service_reference",
        ),
        Index(
            "ix_wallet_marketplace_invoice_payer_status",
            "payer_user_id", "status",
        ),
        Index("ix_wallet_marketplace_invoice_status_created", "status", "created_at"),
        Index("ix_wallet_marketplace_invoice_transaction", "transaction_id"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Deterministic caller key. A retry for the same operation resolves to the
    # same invoice; it must never create a second collection obligation.
    idempotency_key = db.Column(String(255), nullable=False)
    service_code = db.Column(String(50), nullable=False)
    service_reference = db.Column(String(255), nullable=False)
    payer_user_id = db.Column(
        BigInteger, ForeignKey("users.id", name="fk_wallet_marketplace_invoice_payer", ondelete="RESTRICT"), nullable=False,
    )

    amount = db.Column(Numeric(18, 6), nullable=False)
    currency = db.Column(String(10), nullable=False)
    payment_method = db.Column(String(50), nullable=False)
    settlement_timing = db.Column(
        String(32), nullable=False, default="pay_on_completion",
        server_default="pay_on_completion",
    )

    # Optional context for future market/payer-specific provider eligibility.
    # Neither value is inferred from nationality or browser-provided currency.
    service_country_code = db.Column(String(2), nullable=True)
    payer_country_code = db.Column(String(2), nullable=True)

    # 'pending' means the invoice exists but the service is not yet completed;
    # 'due' means settlement is now permitted; 'paid' means Wallet has a
    # completed canonical transaction; 'cash_received' records cash received
    # directly by a driver without pretending cash entered the platform ledger.
    status = db.Column(
        String(24), nullable=False, default="pending", server_default="pending",
    )
    transaction_id = db.Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", name="fk_wallet_marketplace_invoice_transaction", ondelete="RESTRICT"),
        nullable=True,
    )
    provider_reference = db.Column(String(255), nullable=True)
    cash_received_by_user_id = db.Column(
        BigInteger, ForeignKey("users.id", name="fk_wallet_marketplace_invoice_cash_receiver", ondelete="SET NULL"), nullable=True,
    )
    invoice_metadata = db.Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    receipt_metadata = db.Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))

    created_at = db.Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )
    updated_at = db.Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    due_at = db.Column(DateTime(timezone=True), nullable=True)
    paid_at = db.Column(DateTime(timezone=True), nullable=True)
    cash_received_at = db.Column(DateTime(timezone=True), nullable=True)
    cancelled_at = db.Column(DateTime(timezone=True), nullable=True)

    @property
    def is_settled(self):
        """Whether the service obligation is fully resolved; cash is distinct from a ledger payment."""
        return self.status in {"paid", "cash_received"}

    @property
    def is_fully_paid(self):
        """Whether the invoice is fully paid (no partial)."""
        return self.status == "paid"

    @property
    def outstanding_amount(self):
        """Calculate remaining amount to be paid on this invoice."""
        if self.is_fully_paid or self.status == "cash_received":
            return Decimal("0")
        # Sum successful allocations
        paid = sum(
            (Decimal(str(a.amount)) for a in self.allocations if a.amount),
            Decimal("0")
        )
        remaining = Decimal(str(self.amount)) - paid
        return max(remaining, Decimal("0"))

    def __repr__(self):
        return (
            f"<MarketplaceInvoice {self.id} {self.service_code}:"
            f"{self.service_reference} {self.amount} {self.currency} {self.status}>"
        )
