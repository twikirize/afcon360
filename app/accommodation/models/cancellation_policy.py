"""
Cancellation Policy Model - Production-grade policy engine for cancellations and refunds.

Supports industry-standard policy types with per-property overrides.
Policy snapshot taken at booking time preserves historical rules.
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


class CancellationPolicyType(str):
    """Cancellation policy type constants (stored as strings in DB)."""
    FLEXIBLE = "FLEX"
    MODERATE = "MOD"
    STRICT = "STRICT"
    SUPER_STRICT = "SUPER"
    NO_SHOW = "NOSHOW"


class CancellationPhase(str):
    """Cancellation phase constants."""
    PRE_CHECKIN = "pre_checkin"
    MID_STAY = "mid_stay"
    NO_SHOW = "no_show"


class CancellationPolicy(BaseModel):
    """
    Cancellation policy definition with phase-specific rules.
    
    Supports:
    - System defaults (property_id = NULL)
    - Per-property overrides (property_id = specific property)
    - Snapshot preservation at booking time
    
    Phase rules:
    - pre_checkin: cancellation before check-in date
    - mid_stay: cancellation after check-in but before check-out
    - no_show: guest never arrives on check-in date
    """
    __tablename__ = "accommodation_cancellation_policies"
    __table_args__ = (
        Index("idx_cancel_policy_property", "property_id"),
        Index("idx_cancel_policy_active", "is_active"),
        Index("idx_cancel_policy_name", "name"),
        UniqueConstraint("property_id", "name", name="uq_cancel_policy_per_property"),
        CheckConstraint("pre_checkin_days >= 0", name="ck_pre_checkin_days_positive"),
        CheckConstraint("pre_checkin_refund_pct >= 0 AND pre_checkin_refund_pct <= 100", name="ck_pre_checkin_refund_range"),
        CheckConstraint("mid_stay_refund_pct >= 0 AND mid_stay_refund_pct <= 100", name="ck_mid_stay_refund_range"),
        CheckConstraint("no_show_penalty >= 0", name="ck_no_show_penalty_positive"),
    )

    # -------------------------------
    # Identifiers
    # -------------------------------
    name = Column(String(20), nullable=False, default=CancellationPolicyType.FLEXIBLE)
    # Values: FLEX, MOD, STRICT, SUPER, NOSHOW

    # -------------------------------
    # Relationships
    # -------------------------------
    property_id = Column(
        BigInteger, 
        ForeignKey("accommodation_properties.id", ondelete="CASCADE"), 
        nullable=True, 
        index=True
    )
    property = relationship("Property", back_populates="cancellation_policies")

    # -------------------------------
    # Phase-specific Rules
    # -------------------------------
    # Pre-check-in: days before check-in for full/partial refund
    pre_checkin_days = Column(Integer, nullable=False, default=1)
    # Percentage refund for pre-check-in (e.g., 100.00 = full refund)
    pre_checkin_refund_pct = Column(Numeric(5, 2), nullable=False, default=100.00)
    
    # Mid-stay: percentage refund for unused nights (pro-rata basis)
    mid_stay_refund_pct = Column(Numeric(5, 2), nullable=False, default=100.00)
    
    # No-show: fixed penalty amount (full first night or full stay)
    no_show_penalty = Column(Numeric(10, 2), nullable=False, default=0.00)

    # -------------------------------
    # Payment Timing Specific Overrides
    # -------------------------------
    # For pay_on_arrival: if penalty > 0, create debt record
    pay_on_arrival_penalty_type = Column(String(30), nullable=True, default="debt")
    # Values: debt (create CancellationPenalty), charge_card (attempt charge), none
    
    # For deposit_only: refund deposit if eligible
    deposit_refundable = Column(Boolean, default=True)

    # -------------------------------
    # Fee Refundability
    # -------------------------------
    refundable_cleaning_fee = Column(Boolean, default=False)
    refundable_service_fee = Column(Boolean, default=False)
    refundable_taxes = Column(Boolean, default=False)

    # -------------------------------
    # Status
    # -------------------------------
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)

    # -------------------------------
    # Metadata
    # -------------------------------
    description = Column(Text, nullable=True)
    policy_metadata = Column(JSON, default=dict)

    def __repr__(self):
        return f"<CancellationPolicy {self.name} property={self.property_id}>"

    # -------------------------------
    # Policy Resolution Methods
    # -------------------------------
    @classmethod
    def get_effective_policy(cls, property_id: int, policy_name: str = None) -> "CancellationPolicy":
        """
        Get the effective policy for a property.
        
        Resolution order:
        1. Property-specific override for the given policy_name
        2. Property-specific default (is_default=True)
        3. System default for the given policy_name
        4. System default (is_default=True)
        """
        # 1. Property-specific override for exact name
        if policy_name:
            policy = cls.query.filter_by(
                property_id=property_id,
                name=policy_name,
                is_active=True
            ).first()
            if policy:
                return policy
        
        # 2. Property-specific default
        policy = cls.query.filter_by(
            property_id=property_id,
            is_default=True,
            is_active=True
        ).first()
        if policy:
            return policy
        
        # 3. System default for exact name
        if policy_name:
            policy = cls.query.filter_by(
                property_id=None,
                name=policy_name,
                is_active=True
            ).first()
            if policy:
                return policy
        
        # 4. System default
        return cls.query.filter_by(
            property_id=None,
            is_default=True,
            is_active=True
        ).first()

    @classmethod
    def create_system_defaults(cls) -> list:
        """Create the five standard system default policies."""
        defaults = [
            cls(
                name=CancellationPolicyType.FLEXIBLE,
                property_id=None,
                is_default=True,
                description="Full refund if cancelled at least 1 day before check-in",
                pre_checkin_days=1,
                pre_checkin_refund_pct=Decimal("100.00"),
                mid_stay_refund_pct=Decimal("100.00"),
                no_show_penalty=Decimal("0.00"),
            ),
            cls(
                name=CancellationPolicyType.MODERATE,
                property_id=None,
                is_default=True,
                description="Full refund 5+ days before, 50% refund 1-4 days before",
                pre_checkin_days=5,
                pre_checkin_refund_pct=Decimal("100.00"),
                mid_stay_refund_pct=Decimal("100.00"),
                no_show_penalty=Decimal("0.00"),
            ),
            cls(
                name=CancellationPolicyType.STRICT,
                property_id=None,
                is_default=True,
                description="50% refund 7+ days before, no refund within 7 days",
                pre_checkin_days=7,
                pre_checkin_refund_pct=Decimal("50.00"),
                mid_stay_refund_pct=Decimal("50.00"),
                no_show_penalty=Decimal("0.00"),
            ),
            cls(
                name=CancellationPolicyType.SUPER_STRICT,
                property_id=None,
                is_default=True,
                description="50% refund 30+ days, 25% refund 14-29 days, no refund within 14 days",
                pre_checkin_days=30,
                pre_checkin_refund_pct=Decimal("50.00"),
                mid_stay_refund_pct=Decimal("25.00"),
                no_show_penalty=Decimal("0.00"),
            ),
            cls(
                name=CancellationPolicyType.NO_SHOW,
                property_id=None,
                is_default=True,
                description="Full first night charged for no-show",
                pre_checkin_days=0,
                pre_checkin_refund_pct=Decimal("0.00"),
                mid_stay_refund_pct=Decimal("0.00"),
                no_show_penalty=Decimal("1.00"),  # Will be interpreted as "full first night"
            ),
        ]
        return defaults

    # -------------------------------
    # Quote Calculation
    # -------------------------------
    def calculate_quote(
        self,
        total_amount: Decimal,
        amount_paid: Decimal,
        payment_timing: str,
        check_in: Date,
        check_out: Date,
        cancellation_date: Date,
        is_checked_in: bool = False,
        nights_remaining: int = None,
    ) -> dict:
        """
        Calculate cancellation quote for a booking.
        
        Args:
            total_amount: Total booking amount
            amount_paid: Amount already paid
            payment_timing: pay_now, deposit, pay_on_arrival, invoice
            check_in: Check-in date
            check_out: Check-out date
            cancellation_date: Date of cancellation
            is_checked_in: Whether guest has already checked in
            nights_remaining: For mid-stay, nights left in stay
            
        Returns:
            Dict with: allowed, refund, fine, message, phase, policy
        """
        from datetime import date as date_cls
        
        def _q(v):
            return Decimal(v or 0).quantize(Decimal("0.01"))
        
        quote = {
            "allowed": True,
            "message": "",
            "phase": CancellationPhase.PRE_CHECKIN,
            "policy": self.name,
            "refundable_base": Decimal("0.00"),
            "refund": Decimal("0.00"),
            "fine": Decimal("0.00"),
            "nights_remaining": 0,
            "days_until_checkin": 0,
        }
        
        total = _q(total_amount)
        paid = _q(amount_paid)
        
        # Determine phase
        if is_checked_in or (cancellation_date >= check_in and cancellation_date < check_out):
            quote["phase"] = CancellationPhase.MID_STAY
            if nights_remaining is None:
                nights_remaining = (check_out - cancellation_date).days
            quote["nights_remaining"] = max(nights_remaining, 0)
        elif cancellation_date >= check_in:
            quote["phase"] = CancellationPhase.NO_SHOW
        else:
            quote["phase"] = CancellationPhase.PRE_CHECKIN
            days_until = (check_in - cancellation_date).days
            quote["days_until_checkin"] = max(days_until, 0)
        
        # Calculate refundable base based on payment timing
        if payment_timing == "pay_now":
            refundable_base = paid
        elif payment_timing == "deposit":
            refundable_base = paid
        elif payment_timing == "pay_on_arrival":
            refundable_base = total  # No money held, but used for penalty calculation
        else:
            refundable_base = total
        
        quote["refundable_base"] = _q(refundable_base)
        
        # Apply phase-specific rules
        if quote["phase"] == CancellationPhase.PRE_CHECKIN:
            days_until = quote["days_until_checkin"]
            
            # Check if within free cancellation window
            if days_until >= self.pre_checkin_days:
                refund_pct = self.pre_checkin_refund_pct
            else:
                # Within window - use graduated refund if available
                refund_pct = self.pre_checkin_refund_pct
            
            # For moderate/strict policies, apply graduated refunds
            if self.name == CancellationPolicyType.MODERATE:
                if days_until >= 5:
                    refund_pct = Decimal("100.00")
                elif days_until >= 1:
                    refund_pct = Decimal("50.00")
                else:
                    refund_pct = Decimal("0.00")
            elif self.name == CancellationPolicyType.STRICT:
                if days_until >= 7:
                    refund_pct = Decimal("50.00")
                else:
                    refund_pct = Decimal("0.00")
            elif self.name == CancellationPolicyType.SUPER_STRICT:
                if days_until >= 30:
                    refund_pct = Decimal("50.00")
                elif days_until >= 14:
                    refund_pct = Decimal("25.00")
                else:
                    refund_pct = Decimal("0.00")
            elif self.name == CancellationPolicyType.NO_SHOW:
                refund_pct = Decimal("0.00")
            elif self.name == CancellationPolicyType.FLEXIBLE:
                if days_until >= 1:
                    refund_pct = Decimal("100.00")
                else:
                    refund_pct = Decimal("0.00")
            
            refund = _q(refundable_base * (refund_pct / Decimal("100.00")))
            
        elif quote["phase"] == CancellationPhase.MID_STAY:
            # Pro-rata refund for unused nights
            total_nights = (check_out - check_in).days
            if total_nights > 0 and nights_remaining > 0:
                unused_ratio = Decimal(nights_remaining) / Decimal(total_nights)
                refund_pct = self.mid_stay_refund_pct / Decimal("100.00")
                refund = _q(refundable_base * unused_ratio * refund_pct)
            else:
                refund = Decimal("0.00")
                
        elif quote["phase"] == CancellationPhase.NO_SHOW:
            # No-show penalty
            if self.no_show_penalty >= 1:
                # Interpret as full first night or full stay
                if self.no_show_penalty == 1:
                    # Full first night
                    nightly_rate = total / (check_out - check_in).days if (check_out - check_in).days > 0 else total
                    fine = _q(nightly_rate)
                else:
                    # Full stay or custom amount
                    fine = _q(self.no_show_penalty)
            else:
                # Percentage-based
                fine = _q(refundable_base * (self.no_show_penalty / Decimal("100.00")))
            
            refund = Decimal("0.00")
            quote["fine"] = _q(fine)
        
        quote["refund"] = _q(refund)
        
        if quote["phase"] != CancellationPhase.NO_SHOW:
            quote["fine"] = _q(refundable_base - refund)
        
        # Generate message
        if quote["refund"] <= 0 and quote.get("fine", 0) <= 0:
            quote["message"] = f"No refund under '{self.name}' policy"
        elif quote["refund"] >= quote["refundable_base"]:
            quote["message"] = f"Full refund ({quote['refund']}) under '{self.name}' policy"
        elif quote["phase"] == CancellationPhase.NO_SHOW:
            quote["message"] = f"No-show penalty: {quote['fine']} charged"
        else:
            quote["message"] = (
                f"Partial refund of {quote['refund']} under '{self.name}' policy "
                f"(fine {quote['fine']})"
            )
        
        # For pay_on_arrival, allowed is always True but fine creates debt
        if payment_timing == "pay_on_arrival" and quote.get("fine", 0) > 0:
            quote["allowed"] = True  # Host can always cancel, guest creates debt
            quote["message"] += " (debt created for penalty)"
        
        return quote


class CancellationPenalty(BaseModel):
    """
    Penalty/debt record for pay-on-arrival cancellations.
    
    Ensures idempotency via unique idempotency_key.
    """
    __tablename__ = "accommodation_cancellation_penalties"
    __table_args__ = (
        Index("idx_cancel_penalty_booking", "booking_id"),
        Index("idx_cancel_penalty_status", "status"),
        Index("idx_cancel_penalty_idempotency", "idempotency_key", unique=True),
    )

    DEBT_STATUS_CHOICES = [
        ("PENDING", "pending"),
        ("CHARGED", "charged"),
        ("PAID", "paid"),
        ("WAIVED", "waived"),
        ("FAILED", "failed"),
    ]

    booking_id = Column(
        BigInteger, 
        ForeignKey("accommodation_bookings.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    booking = relationship("AccommodationBooking", backref="cancellation_penalties")

    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    
    status = Column(
        String(20), 
        nullable=False, 
        default="PENDING"
    )
    # Values: PENDING, CHARGED, PAID, WAIVED, FAILED

    # Idempotency key to prevent duplicate penalties
    idempotency_key = Column(String(100), unique=True, nullable=False, index=True)

    # Payment attempt tracking
    charge_attempted_at = Column(DateTime(timezone=True), nullable=True)
    charge_succeeded_at = Column(DateTime(timezone=True), nullable=True)
    charge_failure_reason = Column(Text, nullable=True)
    wallet_transaction_id = Column(String(255), nullable=True)

    # Metadata
    penalty_metadata = Column(JSON, default=dict)

    def __repr__(self):
        return f"<CancellationPenalty booking={self.booking_id} amount={self.amount} status={self.status}>"