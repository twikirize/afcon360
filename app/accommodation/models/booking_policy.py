# app/accommodation/models/booking_policy.py
"""
Booking Policy Models - Define cancellation, deposit, and payment policies per property
"""

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date,
    ForeignKey, Integer, Text, Numeric, JSON,
    Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class PropertyBookingPolicy(BaseModel):
    """
    Booking policy for a specific property.
    Controls cancellation, deposits, payment timing, and guest requirements.
    """
    __tablename__ = "accommodation_property_booking_policies"
    __table_args__ = (
        Index("idx_policy_property", "property_id"),
        Index("idx_policy_active", "is_active"),
        UniqueConstraint("property_id", name="uq_policy_per_property"),
        CheckConstraint("deposit_percentage >= 0 AND deposit_percentage <= 100", name="ck_deposit_percentage_range"),
        CheckConstraint("free_cancel_hours >= 0", name="ck_free_cancel_hours_positive"),
        CheckConstraint("reservation_hold_minutes >= 0", name="ck_hold_minutes_positive"),
        CheckConstraint("balance_due_days_before_checkin >= 0", name="ck_balance_due_days_positive"),
        CheckConstraint("verification_level IN ('none','basic_identity','document_upload','biometric_liveness','third_party_attestation')", name="ck_verification_level_valid"),
        CheckConstraint("security_deposit_amount >= 0", name="ck_security_deposit_positive"),
    )

    # -------------------------------
    # Relationships
    # -------------------------------
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False,
                         index=True)
    property = relationship("Property", back_populates="booking_policy")

    # -------------------------------
    # Cancellation Policy
    # -------------------------------
    cancellation_policy = Column(String(50), nullable=False, default="flexible")
    # Values: flexible, moderate, strict, super_strict, non_refundable

    # Free cancellation window (hours before check-in)
    free_cancel_hours = Column(Integer, nullable=False, default=24)

    # No-show policy
    no_show_charge_type = Column(String(30), nullable=False, default="full")
    # Values: none, full, deposit, nightly_rate

    no_show_charge_amount = Column(Numeric(10, 2), nullable=True)

    # -------------------------------
    # Payment Timing
    # -------------------------------
    allow_pay_now = Column(Boolean, default=True)
    allow_pay_on_arrival = Column(Boolean, default=False)
    allow_deposit_payment = Column(Boolean, default=False)
    deposit_percentage = Column(Numeric(5, 2), default=0)  # 0-100
    balance_due_days_before_checkin = Column(Integer, default=0)

    # -------------------------------
    # Payment Guarantee
    # -------------------------------
    require_payment_guarantee = Column(Boolean, default=False)
    # If true, guest must have valid payment method even if not charged

    # -------------------------------
    # Reservation Hold
    # -------------------------------
    reservation_hold_minutes = Column(Integer, default=30)  # How long to hold without payment

    # -------------------------------
    # Guest Requirements
    # -------------------------------
    require_guest_identity = Column(Boolean, default=False)
    require_guest_phone = Column(Boolean, default=True)
    require_guest_email = Column(Boolean, default=True)
    # Guest identity verification level (D-006)
    verification_level = Column(String(30), nullable=False, default="none", server_default="none")
    # Values: none, basic_identity, document_upload, biometric_liveness, third_party_attestation

    # Host-configurable required registration fields (D-024)
    required_registration_fields = Column(JSON, default=list, server_default="[]")
    # Options: full_name, phone, email, id_document_type, id_document_number, date_of_birth, nationality

    # Age restrictions
    minimum_age = Column(Integer, nullable=True)  # Minimum age to book
    maximum_age = Column(Integer, nullable=True)  # Maximum age (for senior-only properties)

    # -------------------------------
    # Cash Payment Protection
    # -------------------------------
    allow_cash_payments = Column(Boolean, default=True, nullable=False, server_default='true')
    cash_requires_deposit = Column(Boolean, default=True, nullable=False, server_default='true')
    cash_deposit_percentage = Column(Numeric(5, 2), default=30, server_default='30')
    cash_max_amount = Column(Numeric(10, 2), default=500000, server_default='500000')
    cash_requires_verified_guest = Column(Boolean, default=True, nullable=False, server_default='true')
    cash_requires_previous_booking = Column(Boolean, default=False, nullable=False, server_default='false')
    cash_min_kyc_level = Column(Integer, default=2, server_default='2')
    cash_min_previous_bookings = Column(Integer, default=0, server_default='0')

    # -------------------------------
    # Security Deposit (D-012)
    # -------------------------------
    require_security_deposit = Column(Boolean, default=False, nullable=False, server_default='false')
    security_deposit_amount = Column(Numeric(10, 2), default=0, server_default='0')

    # -------------------------------
    # Status
    # -------------------------------
    is_active = Column(Boolean, default=True, nullable=False)

    # -------------------------------
    # Methods
    # -------------------------------
    def __repr__(self):
        return f"<PropertyBookingPolicy property={self.property_id} policy={self.cancellation_policy}>"

    def get_cancellation_refund(self, days_until_checkin: int, total_amount: Decimal) -> Decimal:
        """
        Calculate refund amount based on cancellation policy and days until check-in.
        """
        if self.cancellation_policy == "flexible":
            if days_until_checkin >= 1:
                return total_amount
            return Decimal('0')

        elif self.cancellation_policy == "moderate":
            if days_until_checkin >= 5:
                return total_amount
            elif days_until_checkin >= 1:
                return total_amount * Decimal('0.5')
            return Decimal('0')

        elif self.cancellation_policy == "strict":
            if days_until_checkin >= 7:
                return total_amount * Decimal('0.5')
            return Decimal('0')

        elif self.cancellation_policy == "super_strict":
            if days_until_checkin >= 30:
                return total_amount * Decimal('0.5')
            elif days_until_checkin >= 14:
                return total_amount * Decimal('0.25')
            return Decimal('0')

        else:  # non_refundable
            return Decimal('0')

    def can_cancel_free(self, days_until_checkin: int) -> bool:
        """Check if booking can be cancelled for free."""
        return days_until_checkin >= (self.free_cancel_hours / 24)