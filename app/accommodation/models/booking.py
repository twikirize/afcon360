# app/accommodation/models/booking.py
"""
Booking models - High-standard, using Python Enums with String DB storage
"""

from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date,
    ForeignKey, Integer, Text, Numeric, JSON,
    Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.extensions import db
from app.models.base import BaseModel
from app.utils.id_kinds import IDKind
import secrets
import enum


# ==========================================
# Namespaced Enums for Booking (Python only)
# ==========================================

class AccommodationBookingStatus(enum.Enum):
    """Booking status - stored as string in DB"""
    # New states (specification)
    DRAFT = "draft"
    HELD = "held"
    PENDING_PAYMENT = "pending_payment"
    PENDING_APPROVAL = "pending_approval"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    EXPIRED = "expired"
    REFUNDED = "refunded"
    
    # Legacy states (for backward compatibility)
    PENDING = "pending"
    PAYMENT_PARTIAL = "payment_partial"


class AccommodationPaymentStatus(enum.Enum):
    """Payment status - stored as string in DB"""
    UNPAID = "unpaid"
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIAL_REFUND = "partial_refund"


class AccommodationPaymentMethod(enum.Enum):
    """Payment method - stored as string in DB"""
    WALLET = "wallet"
    CARD = "card"
    MOBILE_MONEY = "mobile_money"
    BANK_TRANSFER = "bank_transfer"


class BookingContextType(enum.Enum):
    """Context type - stored as string in DB"""
    NONE = "none"
    EVENT = "event"
    TOUR = "tour"
    CORPORATE = "corporate"
    GROUP = "group"
    INDIVIDUAL = "individual"
    SPONSOR = "sponsor"
    ORGANIZER = "organizer"
    ASSIGNED = "assigned"


# ==========================================
# Booking Model
# ==========================================

class AccommodationBooking(BaseModel):
    __tablename__ = "accommodation_bookings"
    __table_args__ = (
        UniqueConstraint("booking_reference", name="uq_booking_reference"),
        UniqueConstraint("idempotency_key", name="uq_booking_idempotency"),
        Index("idx_booking_property_dates", "property_id", "check_in", "check_out"),
        Index("idx_booking_guest_status", "guest_user_id", "status"),
        Index("idx_booking_status_created", "status", "created_at"),
        Index("idx_booking_dates", "check_in", "check_out"),
        Index("idx_booking_context", "context_type", "context_id"),  # ⚠️ This references context_type which is defined later
        Index("idx_booking_primary_guest", "primary_guest_id", "primary_guest_email"),
        Index("idx_booking_booked_by", "booked_by_user_id"),
        Index("idx_booking_group", "group_booking_id"),
        Index("idx_booking_type", "booking_type"),
        Index("idx_booking_check_in", "check_in"),
        Index("idx_booking_check_out", "check_out"),
        Index("idx_booking_created_at", "created_at"),
        CheckConstraint("check_out > check_in", name="ck_valid_dates"),
        CheckConstraint("num_guests >= 1", name="ck_guests_positive"),
        CheckConstraint("rooms_requested >= 1", name="ck_rooms_requested_positive"),
        CheckConstraint("num_nights >= 1", name="ck_nights_positive"),
        CheckConstraint("total_amount >= 0", name="ck_total_amount_positive"),
        CheckConstraint("security_deposit_amount >= 0", name="ck_security_deposit_positive"),
    )

    # -------------------------------
    # Identifiers
    # -------------------------------
    booking_reference = Column(String(50), nullable=False, unique=True, index=True)
    idempotency_key = Column(String(64), unique=True, index=True, nullable=True)

    # -------------------------------
    # Relationships
    # -------------------------------
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="RESTRICT"), nullable=False)
    accommodation_property = relationship("Property", back_populates="bookings")

    room_type_id = Column(BigInteger, ForeignKey("accommodation_room_types.id", ondelete="RESTRICT"), nullable=True, index=True)
    room_type = relationship("RoomType", backref="bookings")

    guest_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    guest = relationship("User", foreign_keys=[guest_user_id], backref="accommodation_bookings")

    host_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    host = relationship("User", foreign_keys=[host_user_id])

    # -------------------------------
    # Booking Details
    # -------------------------------
    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)
    num_nights = Column(Integer, nullable=False)
    num_guests = Column(Integer, nullable=False, default=1)
    # Group bookings reserve one quantity atomically; room assignment is deferred.
    rooms_requested = Column(Integer, nullable=False, default=1, server_default="1")

    # -------------------------------
    # Pricing Snapshot
    # -------------------------------
    nightly_rate = Column(Numeric(10, 2), nullable=False)
    cleaning_fee = Column(Numeric(10, 2), default=0)
    service_fee = Column(Numeric(10, 2), default=0)
    taxes = Column(Numeric(10, 2), default=0)
    total_amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")

    # -------------------------------
    # Payment (String storage)
    # -------------------------------
    payment_method = Column(String(50), nullable=True)
    payment_status = Column(String(50), default=AccommodationPaymentStatus.PENDING.value, nullable=False)
    wallet_txn_id = Column(String(255), nullable=True, info={"id_kind": IDKind.EXTERNAL_STRING_ID})
    paid_at = Column(DateTime(timezone=True), nullable=True)

    # -------------------------------
    # Refund
    # -------------------------------
    refund_amount = Column(Numeric(10, 2), default=0)
    refunded_at = Column(DateTime(timezone=True), nullable=True)

    # -------------------------------
    # Booking Status (String storage)
    # -------------------------------
    status = Column(String(50), default=AccommodationBookingStatus.DRAFT.value, nullable=False)

    # -------------------------------
    # Cancellation / Host Approval
    # -------------------------------
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    host_approved_at = Column(DateTime(timezone=True), nullable=True)
    host_rejected_at = Column(DateTime(timezone=True), nullable=True)
    host_rejection_reason = Column(Text, nullable=True)
    approval_reason = Column(Text, nullable=True)
    approved_by_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    approved_by_user = relationship("User", foreign_keys=[approved_by_user_id])

    # -------------------------------
    # Guest Snapshot
    # -------------------------------
    # Legacy mirrors are optional because third-party and group bookings may
    # collect the guest roster after payment via the claim-link flow.
    guest_name = Column(String(255), nullable=True)
    guest_email = Column(String(255), nullable=True)
    guest_phone = Column(String(50), nullable=True)
    special_requests = Column(Text, nullable=True)
    host_message = Column(Text, nullable=True)

    # -------------------------------
    # Context Fields (String storage)
    # -------------------------------
    context_type = Column(String(50), default=BookingContextType.NONE.value, nullable=False)  # ✅ Has default
    context_id = Column(String(100), nullable=True, info={"id_kind": IDKind.EXTERNAL_STRING_ID})
    context_metadata = Column(JSON, default=dict)

    # -------------------------------
    # Event Orchestration
    # -------------------------------
    event_id = Column(BigInteger, nullable=True, index=True, info={"id_kind": IDKind.CROSS_MODULE_REF})
    event_participation_id = Column(BigInteger, nullable=True, index=True, info={"id_kind": IDKind.CROSS_MODULE_REF})

    # -------------------------------
    # Check-in/out Tracking
    # -------------------------------
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    checked_out_at = Column(DateTime(timezone=True), nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Separate deadlines for different booking phases
    hold_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    approval_deadline = Column(DateTime(timezone=True), nullable=True, index=True)
    registration_deadline = Column(DateTime(timezone=True), nullable=True, index=True)

    # ==========================================
    # NEW: Booking Owner Identity (D-003, D-004)
    # ==========================================
    # The user who legally owns the booking. May differ from booked_by_user_id
    # (the Creator) in third-party bookings.
    booking_owner_id = Column(BigInteger, ForeignKey("users.id"), nullable=True, index=True)
    booking_owner = relationship("User", foreign_keys=[booking_owner_id])

    # When the Owner authenticated and claimed the booking (third-party only)
    owner_claimed_at = Column(DateTime(timezone=True), nullable=True)

    # Email of the Owner if they do not yet have an AFCON360 account
    owner_email = Column(String(255), nullable=True)

    # Single-use secure token (hashed) for the Owner claiming flow
    claim_token_hash = Column(String(64), nullable=True, index=True)

    # ==========================================
    # NEW: Multi-guest / Third-party booking fields
    # ==========================================

    # Who is the primary guest staying (can be different from booker)
    primary_guest_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    primary_guest_name = Column(String(255), nullable=True)
    primary_guest_email = Column(String(255), nullable=True)
    primary_guest_phone = Column(String(50), nullable=True)

    # Who paid/booked (always the logged-in user who created the booking)
    booked_by_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    booked_by_user = relationship("User", foreign_keys=[booked_by_user_id])
    booked_by_name_snapshot = Column(String(255), nullable=True)
    booked_by_email_snapshot = Column(String(255), nullable=True)

    # Booking type classification
    booking_type = Column(String(30), nullable=False, default='self')  # self, third_party, group, event_assigned

    # Group bookings (multiple rooms for same trip)
    group_booking_id = Column(String(100), nullable=True, info={"id_kind": IDKind.EXTERNAL_STRING_ID})  # UUID shared across multiple bookings
    group_size = Column(Integer, nullable=True)  # Total people in group
    room_number = Column(Integer, nullable=True)  # Which room in group (1,2,3...)

    # Special instructions for the guest
    guest_instructions = Column(Text, nullable=True)

    # -------------------------------
    # Room Assignment & Check-in/out
    # -------------------------------
    assigned_room_id = Column(BigInteger, ForeignKey("accommodation_rooms.id"), nullable=True, index=True)
    assigned_room = relationship("Room", foreign_keys=[assigned_room_id])

    checked_in_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    checked_out_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    is_checked_in = Column(Boolean, default=False, nullable=False)
    is_checked_out = Column(Boolean, default=False, nullable=False)

    # ==========================================
    # NEW: Payment Timing & Amounts
    # ==========================================
    payment_timing = Column(String(30), nullable=True)  # pay_now, deposit, pay_on_arrival, invoice
    amount_paid = Column(Numeric(10, 2), default=0)
    amount_due = Column(Numeric(10, 2), default=0)
    deposit_amount = Column(Numeric(10, 2), default=0)
    balance_due_date = Column(Date, nullable=True)

    # ==========================================
    # NEW: Security Deposit (D-012)
    # ==========================================
    security_deposit_amount = Column(Numeric(10, 2), default=0)
    security_deposit_held = Column(Boolean, default=False)
    security_deposit_released_at = Column(DateTime(timezone=True), nullable=True)

    # ==========================================
    # NEW: Payment Guarantee
    # ==========================================
    payment_guaranteed = Column(Boolean, default=False)
    guarantee_type = Column(String(30), nullable=True)  # wallet_balance, card_authorization, deposit, none

    # ==========================================
    # NEW: Policy Snapshot (JSON)
    # ==========================================
    policy_snapshot = Column(JSON, default=dict)

    # ==========================================
    # NEW: Guest Identity
    # ==========================================
    guest_identity_id = Column(BigInteger, ForeignKey("accommodation_guest_identity_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    guest_identity = relationship("GuestIdentityProfile", foreign_keys=[guest_identity_id])
    commission = relationship("BookingCommission", back_populates="booking", uselist=False, cascade="all, delete-orphan")

    # -------------------------------
    # Relationships (continued)
    # -------------------------------
    status_history = relationship("BookingStatusHistory", back_populates="booking", cascade="all, delete-orphan")
    review = relationship("Review", back_populates="booking", uselist=False)
    room_assignments = relationship("RoomBooking", back_populates="booking", cascade="all, delete-orphan")
    guest_registrations = relationship("GuestRegistration", back_populates="booking", cascade="all, delete-orphan")
    special_requests_list = relationship("BookingSpecialRequest", back_populates="booking", cascade="all, delete-orphan")
    registration_link = relationship("BookingRegistrationLink", back_populates="booking", uselist=False, cascade="all, delete-orphan")

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def listing(self):
        """Return the property listing (clear alias for accommodation_property)"""
        return self.accommodation_property

    @property
    def status_enum(self) -> AccommodationBookingStatus:
        """Get status as enum for type-safe operations"""
        return AccommodationBookingStatus(self.status)

    @property
    def payment_status_enum(self) -> AccommodationPaymentStatus:
        """Get payment status as enum"""
        return AccommodationPaymentStatus(self.payment_status)

    @property
    def context_type_enum(self) -> BookingContextType:
        """Get context type as enum"""
        return BookingContextType(self.context_type)

    @property
    def is_ready_for_checkin(self) -> bool:
        """
        Computed property - not stored in DB.
        Returns True if guest can check in.
        """
        if (
            self.status != AccommodationBookingStatus.CONFIRMED.value
            or self.payment_status_enum not in [
                AccommodationPaymentStatus.PAID,
                AccommodationPaymentStatus.PARTIALLY_PAID,
            ]
            or self.check_in > date.today()
            or not self.all_required_guests_registered
        ):
            return False

        # Check property-level guest identity requirement (D-005)
        try:
            from app.accommodation.models.booking_policy import PropertyBookingPolicy

            policy = PropertyBookingPolicy.query.filter_by(
                property_id=self.property_id
            ).first()
            if policy and policy.require_guest_identity:
                return self.all_required_guests_registered
        except Exception:
            pass

        return True

    @property
    def check_in_date_reached(self) -> bool:
        """True once the check-in date is today or in the past."""
        return bool(self.check_in) and self.check_in <= date.today()

    @property
    def registration_deadline_passed(self) -> bool:
        """
        True when the soft registration deadline is in the past.

        This is a *soft* limit: it never blocks check-in on its own. It only
        drives guest reminders and the host "registration incomplete" flag.
        """
        if not self.registration_deadline:
            return False
        deadline = self.registration_deadline
        # Column is timezone-aware, but SQLite/legacy rows can return naive values.
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline < datetime.now(timezone.utc)

    @property
    def registration_incomplete(self) -> bool:
        """
        True when guests still need to register.

        Used to show a warning badge to the host. Never used to deny a stay.
        """
        return not self.all_required_guests_registered

    @property
    def registration_needs_attention(self) -> bool:
        """True when the deadline lapsed and registration is still incomplete."""
        return self.registration_deadline_passed and self.registration_incomplete

    @property
    def all_required_guests_registered(self) -> bool:
        """Check if all required guests are registered for this booking."""
        try:
            from app.accommodation.models.guest_registration import GuestRegistration

            registrations = GuestRegistration.query.filter_by(booking_id=self.id).all()
            if not registrations:
                return False
            return all(
                r.status in ("completed", "skipped") for r in registrations
            )
        except Exception:
            return bool(self.primary_guest_id or self.guest_user_id or self.guest_email)

    # -------------------------------
    # Core Methods
    # -------------------------------
    def generate_reference(self):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        random_part = secrets.token_hex(4).upper()
        self.booking_reference = f"ACC-{timestamp}-{random_part}"

    def calculate_nights(self):
        self.num_nights = (self.check_out - self.check_in).days
        return self.num_nights

    def calculate_totals(self):
        self.num_nights = self.calculate_nights()
        self.total_amount = (self.nightly_rate * self.num_nights) + self.cleaning_fee + self.service_fee + self.taxes
        return self.total_amount

    def mark_paid(self, transaction_id=None):
        self.payment_status = AccommodationPaymentStatus.PAID.value
        self.paid_at = datetime.now(timezone.utc)
        self.wallet_txn_id = transaction_id
        if not self.payment_method:
            self.payment_method = "wallet"

    def confirm(self):
        from app.accommodation.state_machine.booking_states import BookingStateMachine

        BookingStateMachine.transition(
            self,
            AccommodationBookingStatus.CONFIRMED,
            changed_by_user_id=self.guest_user_id,
            reason="Booking confirmed",
            trigger="model_confirm",
        )

    def cancel(self, user_id, reason=None):
        can_cancel, msg, refund = self.can_cancel()
        if not can_cancel:
            return False, msg, 0

        from app.accommodation.state_machine.booking_states import BookingStateMachine

        BookingStateMachine.transition(
            self,
            AccommodationBookingStatus.CANCELLED,
            changed_by_user_id=user_id,
            reason=reason,
            trigger="model_cancel",
        )
        self.cancelled_at = datetime.now(timezone.utc)
        self.cancelled_by_user_id = user_id
        self.cancellation_reason = reason

        if refund > 0:
            self.refund_amount = refund
            self.payment_status = AccommodationPaymentStatus.REFUNDED.value
            self.refunded_at = datetime.now(timezone.utc)

        return True, msg, refund

    # -------------------------------
    # Cancellation policy / refund engine
    # -------------------------------
    CANCELLABLE_STATUSES = [
        AccommodationBookingStatus.DRAFT,
        AccommodationBookingStatus.HELD,
        AccommodationBookingStatus.PENDING,
        AccommodationBookingStatus.PENDING_PAYMENT,
        AccommodationBookingStatus.PENDING_APPROVAL,
        AccommodationBookingStatus.CONFIRMED,
        AccommodationBookingStatus.CHECKED_IN,
    ]

    def _cancellation_policy_context(self):
        """
        Resolve the effective cancellation policy for this booking.

        Precedence:
          1. Policy snapshot taken at booking time (immutable for the guest)
          2. PropertyBookingPolicy row (host-configured, authoritative today)
          3. Property.cancellation_policy (legacy fallback)
        Returns (policy_obj_or_None, policy_name).
        """
        policy_obj = None
        try:
            from app.accommodation.models.booking_policy import PropertyBookingPolicy

            policy_obj = PropertyBookingPolicy.query.filter_by(
                property_id=self.property_id
            ).first()
        except Exception:
            policy_obj = None

        snapshot_name = None
        if isinstance(self.policy_snapshot, dict):
            snapshot_name = self.policy_snapshot.get("cancellation_policy")

        name = snapshot_name or (policy_obj.cancellation_policy if policy_obj else None)
        if not name:
            try:
                name = self.accommodation_property.cancellation_policy
            except Exception:
                name = None
        return policy_obj, (name or "non_refundable")

    @staticmethod
    def _apply_policy_tiers(policy_name: str, base: Decimal, days_remaining: int) -> Decimal:
        """Pure policy → refund mapping (used when no policy row is available)."""
        if base <= 0:
            return Decimal("0.00")
        if policy_name == "flexible":
            return base if days_remaining >= 1 else Decimal("0.00")
        if policy_name == "moderate":
            if days_remaining >= 5:
                return base
            if days_remaining >= 1:
                return base * Decimal("0.5")
            return Decimal("0.00")
        if policy_name == "strict":
            return base * Decimal("0.5") if days_remaining >= 7 else Decimal("0.00")
        if policy_name == "super_strict":
            if days_remaining >= 30:
                return base * Decimal("0.5")
            if days_remaining >= 14:
                return base * Decimal("0.25")
            return Decimal("0.00")
        return Decimal("0.00")

    def get_cancellation_quote(self) -> dict:
        """
        Single source of truth for cancellation outcomes (pre- and post-check-in).

        Returns a dict:
          allowed, message, phase, policy, refundable_base, refund, fine,
          nights_remaining / days_until_checkin
        The FINE is the explicit penalty line item = refundable_base - refund.
        """
        def _q(v):
            return Decimal(v or 0).quantize(Decimal("0.01"))

        quote = {
            "allowed": False,
            "message": "Cannot cancel at this stage",
            "phase": "none",
            "policy": None,
            "refundable_base": Decimal("0.00"),
            "refund": Decimal("0.00"),
            "fine": Decimal("0.00"),
            "nights_remaining": 0,
            "days_until_checkin": 0,
        }

        if self.status_enum not in self.CANCELLABLE_STATUSES:
            return quote

        policy_obj, policy_name = self._cancellation_policy_context()
        quote["policy"] = policy_name
        total = Decimal(self.total_amount or 0)

        # -------- Mid-stay cancellation (already checked in) --------
        if self.status_enum == AccommodationBookingStatus.CHECKED_IN:
            nights_remaining = (self.check_out - date.today()).days
            quote["phase"] = "mid_stay"
            quote["nights_remaining"] = max(nights_remaining, 0)
            quote["allowed"] = True

            if nights_remaining <= 0:
                quote["message"] = "No refund — stay already completed"
                return quote

            base = min(
                (total * Decimal(nights_remaining)) / Decimal(self.num_nights or 1),
                total,
            )
            # Mid-stay tiers (see BACKLOG.md — pending finance sign-off):
            # flexible = full remaining, moderate = full remaining (>=1 night),
            # strict = 50% of remaining, super_strict/non_refundable = 0.
            if policy_name in ("flexible", "moderate"):
                refund = base
            elif policy_name == "strict":
                refund = base * Decimal("0.5")
            elif policy_name == "super_strict":
                refund = base * Decimal("0.25")
            else:
                refund = Decimal("0.00")

            quote["refundable_base"] = _q(base)
            quote["refund"] = _q(refund)
            quote["fine"] = _q(base - refund)
            quote["message"] = (
                f"Mid-stay cancellation under '{policy_name}' policy: "
                f"{quote['refund']} refunded on {quote['refundable_base']} remaining, "
                f"fine {quote['fine']}"
            )
            return quote

        # -------- Pre-check-in cancellation --------
        days_until = (self.check_in - date.today()).days
        quote["phase"] = "pre_checkin"
        quote["days_until_checkin"] = days_until
        quote["allowed"] = True
        quote["refundable_base"] = _q(total)

        if policy_obj is not None:
            refund = policy_obj.get_cancellation_refund(days_until, total)
        else:
            refund = self._apply_policy_tiers(policy_name, total, days_until)

        quote["refund"] = _q(refund)
        quote["fine"] = _q(total - Decimal(refund))
        if quote["refund"] <= 0:
            quote["message"] = f"No refund under '{policy_name}' policy"
        elif quote["refund"] >= quote["refundable_base"]:
            quote["message"] = "Full refund"
        else:
            quote["message"] = (
                f"Partial refund of {quote['refund']} under '{policy_name}' policy "
                f"(fine {quote['fine']})"
            )
        return quote

    def can_cancel(self):
        """Backwards-compatible wrapper around get_cancellation_quote()."""
        quote = self.get_cancellation_quote()
        return quote["allowed"], quote["message"], quote["refund"]


# ==========================================
# Booking Status History
# ==========================================

class BookingStatusHistory(BaseModel):
    __tablename__ = 'accommodation_booking_status_history'

    id = Column(BigInteger, primary_key=True)
    booking_id = Column(BigInteger, ForeignKey('accommodation_bookings.id'), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    changed_at = Column(DateTime, default=func.now(), nullable=False)
    changed_by = Column(BigInteger, nullable=True)  # user_id who made the change
    trigger = Column(String(100), nullable=True)  # What triggered the change (e.g., 'payment_callback', 'host_action')
    change_metadata = Column(JSON, nullable=True)  # Additional data about the transition

    # Relationships
    booking = relationship("AccommodationBooking", back_populates="status_history")

    @property
    def from_status_enum(self):
        return AccommodationBookingStatus(self.from_status) if self.from_status else None

    @property
    def to_status_enum(self):
        return AccommodationBookingStatus(self.to_status) if self.to_status else None
