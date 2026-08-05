"""
Accommodation module payment event index.

This table is intentionally thin. The canonical source of truth for every
financial event is app.wallet.models.transaction.TransactionModel.
AccommodationBookingPayment exists only to:
- map an accommodation booking to its wallet transaction
- cache payment_status for fast module-level queries
- retain a human-readable payment_reference
- track module-specific retry count

Do NOT duplicate wallet fields here (amount, currency, gateway timestamps,
failure reason, reconciliation). Read those from TransactionModel via
wallet_txn_id.
"""

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, BigInteger, String, Integer, Text, Index, UniqueConstraint, ForeignKey, DateTime
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class AccommodationBookingPayment(BaseModel):
    """
    Thin module-level index into wallet TransactionModel.

    Canonical fields:
        wallet_txn_id  → TransactionModel.id / external_reference
        payment_status → cached from TransactionModel.status
        payment_method / payment_gateway / gateway_transaction_id → cached for convenience

    Module-specific fields:
        retry_count    → accommodation retry tracking
    """

    __tablename__ = "accommodation_booking_payments"
    __table_args__ = (
        Index("idx_ac_book_payment_booking", "booking_id", "payment_status"),
        Index("idx_ac_book_payment_wallet_txn", "wallet_txn_id"),
        Index("idx_ac_book_payment_reference", "payment_reference", unique=True),
        UniqueConstraint("booking_id", "payment_reference", name="uq_ac_booking_payment_ref"),
        Index("idx_ac_book_payment_idempotency", "idempotency_key"),
    )

    booking_id = Column(
        BigInteger,
        ForeignKey("accommodation_bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking = relationship("AccommodationBooking", backref="payment_events")

    # Idempotency key for payment callback deduplication (P1 audit requirement)
    idempotency_key = Column(String(256), unique=True, nullable=True)

    # Canonical wallet reference
    wallet_txn_id = Column(String(255), nullable=True)

    # Human-readable reference for guests/hosts
    payment_reference = Column(String(50), unique=True, nullable=False)

    # Cached payment state (derived from TransactionModel)
    payment_status = Column(String(30), nullable=False, default="pending")
    payment_method = Column(String(50), nullable=True)
    payment_gateway = Column(String(50), nullable=True)
    gateway_transaction_id = Column(String(255), nullable=True)

    # Module-specific tracking
    failure_reason = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    def __repr__(self):
        return (
            f"<AccommodationBookingPayment booking={self.booking_id} "
            f"ref={self.payment_reference} status={self.payment_status} "
            f"wallet_txn={self.wallet_txn_id}>"
        )

    @staticmethod
    def generate_payment_reference():
        import secrets
        random_part = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(10))
        return f"PAY-{random_part}"
