"""
Wallet-owned marketplace invoices/payment intents.

An invoice is an obligation, not a transaction: creating one never moves money.
Transactions and ledger entries remain the canonical record after collection.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Numeric,
    String, UniqueConstraint, PrimaryKeyConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db


class MarketplaceInvoice(db.Model):
    """One immutable-price payment obligation for a marketplace service."""

    __tablename__ = "wallet_marketplace_invoices"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_wallet_marketplace_invoices"),
        CheckConstraint("amount > 0", name="ck_marketplace_invoice_amount_positive"),
        CheckConstraint(
            "status IN ('pending', 'due', 'paid', 'cash_received', "
            "'failed', 'cancelled', 'refunded')",
            name="ck_marketplace_invoice_status_valid",
        ),
        CheckConstraint(
            "settlement_timing IN ('pay_on_completion')",
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
        """Whether the service obligation is resolved; cash is distinct from a ledger payment."""
        return self.status in {"paid", "cash_received"}

    def __repr__(self):
        return (
            f"<MarketplaceInvoice {self.id} {self.service_code}:"
            f"{self.service_reference} {self.amount} {self.currency} {self.status}>"
        )
