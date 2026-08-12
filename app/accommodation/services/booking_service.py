# app/accommodation/services/booking_service.py
"""
Booking Service - Production-grade booking creation, confirmation, and cancellation
Includes: Idempotency, anti-abuse, temporary holds, state management, and audit logging
"""

from flask import current_app
import secrets
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Union, Optional, List, Tuple
import enum
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.admin.models import ContentFlag
from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
    AccommodationPaymentStatus,
    BookingContextType
)
from app.accommodation.models.availability import AccommodationBlockedReason
from app.accommodation.models.room import RoomType, InventoryBlock, Room
from app.accommodation.services.pricing_service import PricingService
from app.accommodation.state_machine.booking_states import BookingStateMachine, InvalidStateTransition

logger = logging.getLogger(__name__)


def _assert_no_open_flags(entity_type: str, entity_id: int):
    """Raise ValueError if the entity has any unresolved ContentFlag records."""
    count = ContentFlag.query.filter_by(
        entity_type=entity_type,
        entity_id=entity_id,
        status="open",
    ).count()
    if count:
        raise ValueError(
            f"Cannot activate {entity_type} {entity_id}: open flags must be resolved first."
        )

from app.accommodation.utils import enum_value  # single source of truth


def check_cash_eligibility(guest_user, property_id, booking_amount):
    """
    Check if a guest is eligible to book with cash pay-on-arrival.

    Three-level control:
      1. Global (SystemConfig) — development mode, KYC requirements, limits
      2. Property (PropertyBookingPolicy) — per-property cash settings
      3. Guest (User) — KYC level, verification, booking history

    Returns dict: {'allowed': bool, 'reason': str, 'requires_deposit': bool}
    """
    from app.models.system_config import SystemConfig
    from app.accommodation.models.booking_policy import PropertyBookingPolicy
    from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus

    # --- Level 1: Global checks ---
    if not SystemConfig.get('payment_cash_globally_enabled', True):
        return {'allowed': False, 'reason': 'Cash payments are disabled system-wide.'}

    dev_mode = SystemConfig.get('payment_cash_development_mode', True)
    if dev_mode:
        try:
            policy = PropertyBookingPolicy.query.filter_by(property_id=property_id).first()
            if policy and hasattr(policy, 'allow_cash_payments') and not policy.allow_cash_payments:
                return {'allowed': False, 'reason': 'Cash payments not allowed for this property.'}
        except Exception:
            pass
        return {'allowed': True, 'reason': 'Development mode — all checks bypassed.', 'requires_deposit': False}

    # --- Level 2: Property policy ---
    try:
        policy = PropertyBookingPolicy.query.filter_by(property_id=property_id).first()
        if not policy:
            policy = PropertyBookingPolicy(property_id=property_id)
            db.session.add(policy)
            db.session.commit()

        if hasattr(policy, 'allow_cash_payments') and not policy.allow_cash_payments:
            return {'allowed': False, 'reason': 'Cash payments are not enabled for this property.'}
    except Exception:
        return {'allowed': False, 'reason': 'Cash payment policy not configured for this property.'}

    # --- Level 3: Guest verification checks ---
    checks = {}

    if SystemConfig.get('payment_cash_requires_kyc', True):
        min_kyc = SystemConfig.get('payment_cash_min_kyc_level', 2)
        checks['kyc_level'] = guest_user.kyc_level >= min_kyc
        if not checks['kyc_level']:
            return {'allowed': False, 'reason': f'KYC level {guest_user.kyc_level} is below minimum required ({min_kyc}).'}

    if SystemConfig.get('payment_cash_requires_verified_phone', True):
        checks['phone_verified'] = guest_user.phone_verified
        if not checks['phone_verified']:
            return {'allowed': False, 'reason': 'Phone verification is required for cash bookings.'}

    if SystemConfig.get('payment_cash_requires_verified_email', True):
        checks['email_verified'] = guest_user.email_verified
        if not checks['email_verified']:
            return {'allowed': False, 'reason': 'Email verification is required for cash bookings.'}

    if SystemConfig.get('payment_cash_requires_previous_booking', True):
        min_bookings = SystemConfig.get('payment_cash_min_previous_bookings', 1)
        if min_bookings is None:
            min_bookings = 1
        completed_count = AccommodationBooking.query.filter(
            AccommodationBooking.guest_user_id == guest_user.id,
            AccommodationBooking.status.in_([
                AccommodationBookingStatus.CONFIRMED.value,
                AccommodationBookingStatus.CHECKED_OUT.value,
            ]),
        ).count()
        checks['previous_bookings'] = completed_count >= min_bookings
        if not checks['previous_bookings']:
            return {'allowed': False, 'reason': f'At least {min_bookings} previous completed booking(s) required for cash payments.'}

    no_show_count = AccommodationBooking.query.filter(
        AccommodationBooking.guest_user_id == guest_user.id,
        AccommodationBooking.status == AccommodationBookingStatus.NO_SHOW.value,
    ).count()
    checks['no_no_shows'] = no_show_count == 0
    if not checks['no_no_shows']:
        return {'allowed': False, 'reason': f'Guests with no-show history cannot use cash payments.'}

    max_amount = SystemConfig.get('payment_cash_max_amount', 500000)
    checks['amount_limit'] = booking_amount <= max_amount
    if not checks['amount_limit']:
        return {'allowed': False, 'reason': f'Booking amount exceeds maximum cash limit ({max_amount}).'}

    return {
        'allowed': True,
        'reason': 'All fraud protection checks passed.',
        'requires_deposit': policy.cash_requires_deposit,
        'deposit_percentage': float(policy.cash_deposit_percentage) if policy.cash_deposit_percentage else 0,
    }


class BookingService:
    """
    Production-grade booking service with:
    - Idempotency (prevents duplicate bookings)
    - Anti-abuse prevention (rate limiting, hold limits)
    - Temporary holds for pending bookings
    - Atomic transactions with rollback
    - Full state machine integration
    - Audit logging via logger
    """

    # -------------------------
    # CREATE BOOKING
    # -------------------------
    @staticmethod
    def create_booking(
        property_id: int,
        guest_user_id: int,
        host_user_id: int,
        check_in: date,
        check_out: date,
        num_guests: int,
        guest_name: str,
        guest_email: str,
        guest_phone: str = None,
        special_requests: str = None,
        idempotency_key: str = None,
        ip_address: str = None,
        user_agent: str = None,
        context_type: 'BookingContextType' = None,
        context_id: str = None,
        context_metadata: dict = None,
        # NEW PARAMETERS
        booked_by_user_id: int = None,
        primary_guest_id: int = None,
        primary_guest_name: str = None,
        primary_guest_email: str = None,
        primary_guest_phone: str = None,
        booking_type: str = 'self',
        group_booking_id: str = None,
        room_number: int = None,
        guest_instructions: str = None,
        room_type_id: Optional[int] = None,
        skip_hold_creation: bool = False,
        payment_method: str = None,
        payment_timing: str = None,
        payment_guaranteed: bool = None,
        guarantee_type: str = None,
        # Booking Owner (D-003, D-004)
        booking_owner_id: int = None,
        owner_email: str = None,
        claim_token_hash: str = None,
    ) -> Tuple[Optional[AccommodationBooking], Optional[str]]:


        """
        Create a new booking with temporary hold.

        Args:
            skip_hold_creation: If True, assumes dates are already held (e.g., pre-payment hold)
                and will update existing temporary holds to 'booked' instead of creating new ones.

        Returns:
            (booking, error_message) - booking is None if error
        """
        from app.accommodation.models.property import Property
        from app.accommodation.models.room import RoomType

        try:
            # 1. IDEMPOTENCY CHECK
            if idempotency_key:
                existing = AccommodationBooking.query.filter_by(
                    idempotency_key=idempotency_key,
                    guest_user_id=guest_user_id
                ).first()
                if existing:
                    logger.info(f"Duplicate booking prevented: {idempotency_key}")
                    return existing, None

            # 2. BASIC VALIDATION
            if check_out <= check_in:
                return None, "Check-out must be after check-in"

            property = db.session.execute(
                select(Property).where(Property.id == property_id).with_for_update()
            ).scalar_one()
            if not property:
                return None, "Property not found"

            if not property.can_be_booked():
                return None, "Property is not available for booking"

            # Resolve room_type_id if not provided
            if not room_type_id:
                room_type = RoomType.query.filter_by(property_id=property_id, is_active=True).first()
                if room_type:
                    room_type_id = room_type.id

            # 3. ANTI-ABUSE PREVENTION (OPTIONAL)
            try:
                from app.accommodation.services.abuse_prevention_service import AbusePreventionService
                from app.models.system_config import SystemConfig

                # Skip anti-abuse checks in development mode
                if SystemConfig.get('payment_cash_development_mode', True):
                    logger.debug("Development mode — skipping anti-abuse checks")
                else:
                    ok, msg = AbusePreventionService.check_user_hold_limit(guest_user_id)
                    if not ok:
                        return None, msg

                    ok, msg = AbusePreventionService.check_property_hold_limit(property_id)
                    if not ok:
                        return None, msg

                    ok, msg = AbusePreventionService.check_rate_limit(guest_user_id)
                    if not ok:
                        return None, msg

                    ok, msg = AbusePreventionService.detect_suspicious_behavior(guest_user_id)
                    if not ok:
                        return None, msg

            except ImportError:
                logger.debug("Anti-abuse service not available, skipping checks")
            except Exception as e:
                logger.warning(f"Anti-abuse check failed: {e}")

            # 4. AVAILABILITY CHECK (concurrency-safe with row locking)
            if not skip_hold_creation:
                from app.accommodation.services.availability_service import AvailabilityService
                from app.accommodation.models.availability import BlockedDate

                # Lock inventory rows for update to prevent double-booking
                # the last available room. This serialises concurrent booking
                # attempts for the same room/date combination.
                if room_type_id:
                    InventoryBlock.query.filter(
                        InventoryBlock.room_type_id == room_type_id,
                        InventoryBlock.date_range_start <= check_out,
                        InventoryBlock.date_range_end >= check_in,
                    ).with_for_update().all()
                else:
                    BlockedDate.query.filter(
                        BlockedDate.property_id == property_id,
                        BlockedDate.blocked_date >= check_in,
                        BlockedDate.blocked_date < check_out,
                    ).with_for_update().all()

                is_available, blocked_dates, error = AvailabilityService.is_range_available(
                    property_id, check_in, check_out
                )
                if not is_available:
                    return None, error or "Selected dates are not available"
            else:
                # When skipping hold creation, we already have a hold. Just verify the property exists.
                is_available = True

            # 5. PRICE CALCULATION
            try:
                pricing = PricingService.calculate_total(
                    property, check_in, check_out, num_guests, room_type_id=room_type_id
                )
            except ValueError as e:
                return None, str(e)

            # 6. CREATE BOOKING
            # New bookings always start in DRAFT and then move through the
            # state machine so audit history is complete.
            requires_host_approval = (not property.instant_book or property.require_host_approval)
            initial_status = AccommodationBookingStatus.DRAFT.value

            # Resolve booker identity for snapshots
            from app.identity.models.user import User
            booker_user = db.session.get(User, booked_by_user_id or guest_user_id)
            booker_name_snapshot = booker_user.username if booker_user else (primary_guest_name or guest_name)
            booker_email_snapshot = booker_user.email if booker_user else (primary_guest_email or guest_email)

            booking = AccommodationBooking(
                property_id=property_id,
                room_type_id=room_type_id,
                guest_user_id=guest_user_id,
                host_user_id=host_user_id,
                check_in=check_in,
                check_out=check_out,
                num_nights=pricing['nights'],
                num_guests=num_guests,
                nightly_rate=pricing['nightly_rate'],
                cleaning_fee=pricing['cleaning_fee'],
                service_fee=pricing['service_fee'],
                taxes=pricing.get('taxes', Decimal('0')),
                total_amount=pricing['total'],
                currency=property.currency,
                guest_name=guest_name,
                guest_email=guest_email,
                guest_phone=guest_phone,
                special_requests=special_requests,
                context_type=enum_value(context_type) if context_type else BookingContextType.NONE.value,
                context_id=context_id,
                context_metadata=context_metadata or {},
                idempotency_key=idempotency_key,
                status=initial_status,
                payment_status=AccommodationPaymentStatus.PENDING.value,
                expires_at=datetime.now(timezone.utc) + timedelta(
                    minutes=current_app.config.get('BOOKING_HOLD_MINUTES', 15)
                ),  # Configurable hold duration
                # NEW FIELDS
                booked_by_user_id=booked_by_user_id or guest_user_id,  # Default to guest if not specified
                booked_by_name_snapshot=booker_name_snapshot,
                booked_by_email_snapshot=booker_email_snapshot,
                primary_guest_id=primary_guest_id,
                primary_guest_name=primary_guest_name or guest_name,
                primary_guest_email=primary_guest_email or guest_email,
                primary_guest_phone=primary_guest_phone or guest_phone,
                booking_type=booking_type,
                group_booking_id=group_booking_id,
                room_number=room_number,
                guest_instructions=guest_instructions,
                payment_method=payment_method,
                payment_timing=payment_timing,
                payment_guaranteed=payment_guaranteed if payment_guaranteed is not None else False,
                guarantee_type=guarantee_type or 'none',
                # Booking Owner (D-003, D-004)
                booking_owner_id=booking_owner_id,
                owner_email=owner_email,
                claim_token_hash=claim_token_hash,
            )

            booking.generate_reference()
            db.session.add(booking)
            db.session.flush()  # Get booking ID before blocking dates

            # 7. TEMPORARY HOLD ON DATES
            if skip_hold_creation:
                # Update existing temporary holds to booked (payment already succeeded)
                from app.accommodation.models.availability import BlockedDate
                existing_holds = BlockedDate.query.filter(
                    BlockedDate.property_id == booking.property_id,
                    BlockedDate.blocked_date.between(
                        booking.check_in,
                        booking.check_out - timedelta(days=1)
                    ),
                    BlockedDate.reason == enum_value(AccommodationBlockedReason.TEMPORARY_HOLD)
                ).all()

                for hold in existing_holds:
                    hold.reason = enum_value(AccommodationBlockedReason.BOOKED)
                    hold.booking_id = booking.id

                # Also update InventoryBlock holds for room type bookings
                if booking.room_type_id:
                    InventoryBlock.query.filter(
                        InventoryBlock.room_type_id == booking.room_type_id,
                        InventoryBlock.date_range_start == booking.check_in,
                        InventoryBlock.date_range_end == booking.check_out,
                        InventoryBlock.reason == AccommodationBlockedReason.TEMPORARY_HOLD.value,
                        InventoryBlock.booking_id.is_(None),
                    ).update(
                        {"reason": AccommodationBlockedReason.BOOKED.value, "booking_id": booking.id},
                        synchronize_session=False,
                    )

                logger.info(
                    f"Converted {len(existing_holds)} temporary holds to booked for booking {booking.booking_reference}"
                )
            else:
                # Use unit-based blocking when room_type_id is set
                from app.accommodation.services.availability_service import AvailabilityService
                if booking.room_type_id:
                    success, err = AvailabilityService.block_room_type_units(
                        room_type_id=booking.room_type_id,
                        check_in=booking.check_in,
                        check_out=booking.check_out,
                        units_to_block=booking.num_guests,
                        reason=AccommodationBlockedReason.TEMPORARY_HOLD.value,
                        booking_id=booking.id,
                        created_by=guest_user_id,
                    )
                    if not success:
                        logger.warning(
                            f"Could not block room type units for booking {booking.booking_reference}: {err}"
                        )
                else:
                    AvailabilityService.block_dates(
                        property_id=booking.property_id,
                        check_in=booking.check_in,
                        check_out=booking.check_out,
                        reason=enum_value(AccommodationBlockedReason.TEMPORARY_HOLD),
                        booking_id=booking.id,
                        created_by=guest_user_id
                    )

            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.HELD,
                changed_by_user_id=guest_user_id,
                reason="Inventory held for checkout",
                ip_address=ip_address,
                user_agent=user_agent,
                trigger="booking_created",
                metadata={"hold_expires_at": booking.expires_at.isoformat() if booking.expires_at else None},
            )

            if requires_host_approval:
                BookingStateMachine.transition(
                    booking,
                    AccommodationBookingStatus.PENDING_APPROVAL,
                    changed_by_user_id=guest_user_id,
                    reason="Host approval required",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    trigger="host_approval_required",
                )

            # 8. UPDATE GUEST PROFILE (create if not exists)
            from app.accommodation.models.guest_profile import GuestProfile
            profile = GuestProfile.query.filter_by(guest_user_id=guest_user_id).first()
            if not profile:
                profile = GuestProfile(
                    guest_user_id=guest_user_id,
                    preferred_currency=property.currency,
                )
                db.session.add(profile)
            # Update preferences from booking data
            profile.preferred_currency = property.currency
            profile.email_notifications = True  # default
            profile.sms_notifications = True    # default

            db.session.commit()

            # 9. CREATE PAYMENT LEDGER RECORD (thin wallet-linked index)
            from app.accommodation.models.booking_payment import AccommodationBookingPayment
            payment_event = AccommodationBookingPayment(
                booking_id=booking.id,
                wallet_txn_id=None,
                payment_reference=AccommodationBookingPayment.generate_payment_reference(),
                payment_status="pending",
                payment_method="pending",
            )
            db.session.add(payment_event)
            db.session.commit()

            logger.info(
                f"Booking created: {booking.booking_reference} | "
                f"Property: {property_id} | Guest: {guest_user_id} | "
                f"Amount: ${booking.total_amount} | Dates: {check_in} → {check_out}"
            )

            return booking, None

        except IntegrityError as e:
            db.session.rollback()
            if idempotency_key:
                existing = AccommodationBooking.query.filter_by(
                    idempotency_key=idempotency_key,
                    guest_user_id=guest_user_id
                ).first()
                if existing:
                    logger.info(f"Duplicate booking race-condition resolved: {idempotency_key}")
                    return existing, None
            logger.error(f"Integrity error during booking creation: {e}", exc_info=True)
            return None, "Unable to create booking. Please try again."

        except Exception as e:
            db.session.rollback()
            logger.error(f"Create booking failed for property {property_id}: {e}", exc_info=True)
            return None, "Unable to create booking. Please try again."



    # -------------------------
    # CHECK-IN
    # -------------------------
    @staticmethod
    def _check_in_block_reason(booking) -> str:
        """Explain why a booking cannot be checked in, for front-desk staff."""
        if booking.status != AccommodationBookingStatus.CONFIRMED.value:
            return f"Booking must be confirmed to check in (currently {booking.status})."

        if booking.check_in > date.today():
            return f"Check-in date is {booking.check_in.strftime('%b %d, %Y')} - too early to check in."

        if booking.payment_status == AccommodationPaymentStatus.UNPAID.value:
            if not BookingStateMachine._cash_eligible_at_checkin(booking):
                return "Booking is unpaid and not eligible for pay-on-arrival. Please collect payment first."

        if not BookingStateMachine._registration_satisfied(booking):
            return (
                "Guest registration is incomplete and the registration deadline "
                "has not passed yet. Ask the guest to complete registration online, "
                "or register them here and check in."
            )

        return "Booking is not ready for check-in."

    @staticmethod
    def check_in(booking_id: int, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Check in a booking and assign room if not already assigned.
        Enforces registration, payment, and date readiness via state machine.
        """
        booking = db.session.get(AccommodationBooking, booking_id)
        if not booking:
            return False, "Booking not found"

        if booking.is_checked_in:
            return False, "Booking is already checked in"

        try:
            # Enforce state-machine readiness (payment, registration, date).
            if not BookingStateMachine._can_check_in(booking):
                return False, BookingService._check_in_block_reason(booking)

            # Assign room if not assigned - must match booking's room type
            if not booking.assigned_room_id:
                available_room = Room.query.filter(
                    Room.property_id == booking.property_id,
                    Room.room_type_id == booking.room_type_id,
                    Room.is_active == True,
                    Room.status == "available",
                    Room.is_maintenance == False,
                ).first()

                if not available_room:
                    return False, "No available rooms for check-in"

                booking.assigned_room_id = available_room.id
                available_room.assign_booking(booking.id)

            # Create room booking assignment
            room_booking = RoomBooking(
                booking_id=booking.id,
                room_id=booking.assigned_room_id,
                check_in=booking.check_in,
                check_out=booking.check_out,
                status="checked_in",
                assigned_by=user_id,
            )
            db.session.add(room_booking)

            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.CHECKED_IN,
                changed_by_user_id=user_id,
                reason="Guest checked in",
                trigger="guest_check_in",
            )

            booking.checked_in_by = user_id
            booking.is_checked_in = True
            booking.checked_in_at = datetime.now(timezone.utc)

            db.session.commit()

            # Notify guest, host and module admins (listeners dispatch notifications).
            try:
                from app.notifications.signals import booking_checked_in
                booking_checked_in.send(booking, booking=booking)
            except Exception as sig_err:
                logger.warning(f"booking_checked_in signal failed for {booking_id}: {sig_err}")

            return True, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Check-in failed for booking {booking_id}: {e}", exc_info=True)
            return False, "Check-in failed. Please try again."

    # -------------------------
    # CHECK-OUT
    # -------------------------
    @staticmethod
    def check_out(booking_id: int, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Check out a booking and release the room.
        """
        booking = db.session.get(AccommodationBooking, booking_id)
        if not booking:
            return False, "Booking not found"

        if booking.status != AccommodationBookingStatus.CHECKED_IN.value:
            return False, "Only checked-in bookings can be checked out"

        if booking.is_checked_out:
            return False, "Booking is already checked out"

        try:
            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.CHECKED_OUT,
                changed_by_user_id=user_id,
                reason="Guest checked out",
                trigger="guest_check_out",
            )

            booking.checked_out_by = user_id
            booking.is_checked_out = True
            booking.checked_out_at = datetime.now(timezone.utc)

            # Release assigned room
            if booking.assigned_room_id:
                assigned_room = db.session.get(Room, booking.assigned_room_id)
                if assigned_room:
                    assigned_room.release()

            # Update room booking assignments
            for rb in booking.room_assignments:
                if rb.status == "checked_in":
                    rb.check_out()

            db.session.commit()

            # Notify guest, host and module admins (listeners dispatch notifications).
            try:
                from app.notifications.signals import booking_checked_out
                booking_checked_out.send(booking, booking=booking)
            except Exception as sig_err:
                logger.warning(f"booking_checked_out signal failed for {booking_id}: {sig_err}")

            return True, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Check-out failed for booking {booking_id}: {e}", exc_info=True)
            return False, "Check-out failed. Please try again."

    # -------------------------
    # CONFIRM BOOKING
    # -------------------------
    @staticmethod
    def confirm_booking(
        booking_id: int,
        wallet_transaction_id: str = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Confirm a booking after successful payment.
        Converts temporary hold to permanent booked status.
        """
        booking = db.session.execute(
            select(AccommodationBooking).where(AccommodationBooking.id == booking_id).with_for_update()
        ).scalar_one()

        if not booking:
            return False, "Booking not found"

        if (
            booking.status == AccommodationBookingStatus.CONFIRMED.value
            and booking.payment_status == AccommodationPaymentStatus.PAID.value
        ):
            return False, "Booking already paid and confirmed"

        confirmable_statuses = {
            AccommodationBookingStatus.DRAFT.value,
            AccommodationBookingStatus.HELD.value,
            AccommodationBookingStatus.PENDING.value,
            AccommodationBookingStatus.PENDING_PAYMENT.value,
            AccommodationBookingStatus.PAYMENT_PARTIAL.value,
        }
        if booking.status not in confirmable_statuses:
            return False, f"Cannot confirm booking in {booking.status!r} state"

        expires_at = booking.expires_at
        if expires_at:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if expires_at < datetime.now(timezone.utc):
                return False, "Booking has expired. Please create a new booking."

        try:
            # 1. RE-VERIFY AVAILABILITY (Exclude own hold)
            if booking.room_type_id:
                from app.accommodation.services.host_service import HostService
                avail = HostService.available_units(
                    booking.room_type_id,
                    booking.check_in,
                    booking.check_out,
                    exclude_booking_id=booking.id
                )
                if avail <= 0:
                    return False, "Selected dates are no longer available for this room type. Please contact support."

            from app.accommodation.services.availability_service import AvailabilityService
            is_available, blocked_dates, error = AvailabilityService.is_range_available(
                booking.property_id,
                booking.check_in,
                booking.check_out,
                exclude_booking_id=booking.id
            )
            if not is_available:
                return False, error or "Dates are no longer available. Please contact support."

            # Guard: cannot confirm booking if there are open ContentFlag records
            _assert_no_open_flags("accommodation_booking", booking.id)

            # 2. CONVERT TEMPORARY HOLD → PERMANENT BOOKED
            from app.accommodation.models.availability import BlockedDate
            BlockedDate.query.filter_by(booking_id=booking.id).update(
                {"reason": enum_value(AccommodationBlockedReason.BOOKED)}
            )

            # Also update InventoryBlock for room type bookings
            if booking.room_type_id:
                InventoryBlock.query.filter(
                    InventoryBlock.room_type_id == booking.room_type_id,
                    InventoryBlock.date_range_start == booking.check_in,
                    InventoryBlock.date_range_end == booking.check_out,
                    InventoryBlock.booking_id == booking.id,
                ).update(
                    {"reason": AccommodationBlockedReason.BOOKED.value},
                    synchronize_session=False,
                )

            # 3. UPDATE PAYMENT STATUS
            booking.payment_status = AccommodationPaymentStatus.PAID.value
            booking.wallet_txn_id = wallet_transaction_id
            booking.paid_at = datetime.now(timezone.utc)
            booking.payment_guaranteed = True
            if not booking.guarantee_type or booking.guarantee_type == 'none':
                booking.guarantee_type = 'payment_confirmed'

            # Update payment event ledger (thin wallet-linked index)
            try:
                BookingService.update_payment_event(
                    booking_id=booking.id,
                    payment_status="success",
                    payment_method=booking.payment_method,
                    payment_gateway="wallet" if booking.payment_method == "wallet" else booking.payment_method,
                    gateway_transaction_id=wallet_transaction_id,
                    wallet_txn_id=wallet_transaction_id,
                    idempotency_key=booking.idempotency_key,
                )
            except Exception as ledger_error:
                logger.warning(f"Failed to update payment event for booking {booking_id}: {ledger_error}")

            # 4. STATE TRANSITION (→ PENDING_PAYMENT → CONFIRMED)
            if booking.status in [
                AccommodationBookingStatus.DRAFT.value,
                AccommodationBookingStatus.HELD.value,
                AccommodationBookingStatus.PENDING.value,
            ]:
                if booking.status == AccommodationBookingStatus.DRAFT.value:
                    BookingStateMachine.transition(
                        booking,
                        AccommodationBookingStatus.HELD,
                        changed_by_user_id=booking.guest_user_id,
                        reason="Inventory held before payment confirmation",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        trigger="payment_confirmation",
                    )
                BookingStateMachine.transition(
                    booking,
                    AccommodationBookingStatus.PENDING_PAYMENT,
                    changed_by_user_id=booking.guest_user_id,
                    reason="Payment received; awaiting confirmation",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    trigger="payment_confirmation",
                )

            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.CONFIRMED,
                changed_by_user_id=booking.guest_user_id,
                reason="Payment confirmed",
                ip_address=ip_address,
                user_agent=user_agent,
                trigger="payment_confirmation",
                metadata={"wallet_transaction_id": wallet_transaction_id},
            )

            db.session.commit()
            logger.info(
                f"Booking confirmed: {booking.booking_reference} | "
                f"Transaction: {wallet_transaction_id} | "
                f"Amount: ${booking.total_amount}"
            )

            # Emit notification signal (listener notifies guest + host)
            try:
                from app.notifications.signals import booking_confirmed
                booking_confirmed.send(booking, booking=booking)
            except Exception as _ne:
                logger.warning(f"booking_confirmed signal failed: {_ne}")

            return True, None

        except InvalidStateTransition as e:
            db.session.rollback()
            logger.error(f"Invalid state transition for booking {booking_id}: {e}")
            return False, str(e)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Confirm booking failed for {booking_id}: {e}", exc_info=True)
            return False, "Unable to confirm booking. Please contact support."

    # -------------------------
    # HOST APPROVAL
    # -------------------------
    @staticmethod
    def approve_booking(
        booking_id: int,
        approved_by_user_id: int,
        reason: str = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Approve a booking that is in PENDING_APPROVAL state.
        Transitions to CONFIRMED.
        """
        booking = db.session.execute(
            select(AccommodationBooking).where(AccommodationBooking.id == booking_id).with_for_update()
        ).scalar_one()

        if not booking:
            return False, "Booking not found"

        if booking.status != AccommodationBookingStatus.PENDING_APPROVAL.value:
            return False, f"Cannot approve booking in {booking.status!r} state"

        try:
            booking.approved_by_user_id = approved_by_user_id
            booking.approval_reason = reason
            booking.host_approved_at = datetime.now(timezone.utc)

            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.CONFIRMED,
                changed_by_user_id=approved_by_user_id,
                reason=reason or "Approved by host",
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Convert temporary hold to permanent booked
            from app.accommodation.models.availability import BlockedDate
            BlockedDate.query.filter_by(booking_id=booking.id).update(
                {"reason": enum_value(AccommodationBlockedReason.BOOKED)}
            )

            # Also update InventoryBlock for room type bookings
            if booking.room_type_id:
                InventoryBlock.query.filter(
                    InventoryBlock.room_type_id == booking.room_type_id,
                    InventoryBlock.date_range_start == booking.check_in,
                    InventoryBlock.date_range_end == booking.check_out,
                    InventoryBlock.booking_id == booking.id,
                ).update(
                    {"reason": AccommodationBlockedReason.BOOKED.value},
                    synchronize_session=False,
                )

            db.session.commit()
            logger.info(
                f"Booking approved: {booking.booking_reference} | "
                f"By: {approved_by_user_id} | Reason: {reason}"
            )

            # Emit notification signal (listener notifies guest + host)
            try:
                from app.notifications.signals import booking_confirmed
                booking_confirmed.send(booking, booking=booking)
            except Exception as _ne:
                logger.warning(f"booking_confirmed signal failed: {_ne}")

            return True, None

        except InvalidStateTransition as e:
            db.session.rollback()
            logger.error(f"Invalid state transition for approval {booking_id}: {e}")
            return False, str(e)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Approve booking failed for {booking_id}: {e}", exc_info=True)
            return False, "Unable to approve booking. Please contact support."

    @staticmethod
    def reject_booking(
        booking_id: int,
        rejected_by_user_id: int,
        reason: str = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Reject a booking that is in PENDING_APPROVAL state.
        Transitions to CANCELLED.
        """
        booking = db.session.execute(
            select(AccommodationBooking).where(AccommodationBooking.id == booking_id).with_for_update()
        ).scalar_one()

        if not booking:
            return False, "Booking not found"

        if booking.status != AccommodationBookingStatus.PENDING_APPROVAL.value:
            return False, f"Cannot reject booking in {booking.status!r} state"

        try:
            old_status = booking.status
            from app.accommodation.models.availability import BlockedDate

            # Release blocked dates
            BlockedDate.query.filter_by(booking_id=booking.id).delete()

            # Also release InventoryBlock for room type bookings
            from app.accommodation.services.availability_service import AvailabilityService
            if booking.room_type_id:
                AvailabilityService.release_room_type_blocks(
                    room_type_id=booking.room_type_id,
                    check_in=booking.check_in,
                    check_out=booking.check_out,
                    booking_id=booking.id,
                )

            booking.host_rejected_at = datetime.now(timezone.utc)
            booking.host_rejection_reason = reason

            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.CANCELLED,
                changed_by_user_id=rejected_by_user_id,
                reason=reason or "Rejected by host",
                ip_address=ip_address,
                user_agent=user_agent,
            )

            booking.cancelled_at = datetime.now(timezone.utc)
            booking.cancelled_by_user_id = rejected_by_user_id
            booking.cancellation_reason = reason

            db.session.commit()
            logger.info(
                f"Booking rejected: {booking.booking_reference} | "
                f"By: {rejected_by_user_id} | Reason: {reason}"
            )
            return True, None

        except InvalidStateTransition as e:
            db.session.rollback()
            logger.error(f"Invalid state transition for rejection {booking_id}: {e}")
            return False, str(e)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Reject booking failed for {booking_id}: {e}", exc_info=True)
            return False, "Unable to reject booking. Please contact support."

    @staticmethod
    def record_policy_violation(
        property_id: int,
        reason: str = "Policy violation",
    ) -> Tuple[bool, Optional[str]]:
        """
        Record a policy violation for a property and auto-suspend if threshold exceeded.
        """
        try:
            prop = db.session.get(Property, property_id)
            if not prop:
                return False, "Property not found"

            prop.policy_violations = (prop.policy_violations or 0) + 1

            if prop.policy_violations >= (prop.auto_suspend_threshold or 5):
                prop.is_suspended = True
                prop.status = "suspended"
                prop.is_active = False
                prop.suspension_reason = f"Auto-suspended after {prop.policy_violations} policy violations: {reason}"
                logger.warning(
                    f"Property {property_id} auto-suspended after {prop.policy_violations} violations"
                )

            db.session.commit()
            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to record policy violation for property {property_id}: {e}", exc_info=True)
            return False, str(e)

    # -------------------------
    # CANCEL BOOKING
    # -------------------------
    @staticmethod
    def cancel_booking(
        booking_id: int,
        cancelled_by_user_id: int,
        reason: str = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[bool, Optional[str], Optional[Decimal]]:
        """
        Cancel a booking and process refund if applicable.
        """
        booking = db.session.execute(
            select(AccommodationBooking).where(AccommodationBooking.id == booking_id).with_for_update()
        ).scalar_one()

        if not booking:
            return False, "Booking not found", None

        # Authority check (D-004): only the Booking Owner, the booker, or the host may cancel.
        owner_id = booking.booking_owner_id or booking.booked_by_user_id
        if cancelled_by_user_id not in (owner_id, booking.host_user_id):
            return False, "You are not authorised to cancel this booking.", None

        quote = booking.get_cancellation_quote()
        can_cancel, msg, refund = quote["allowed"], quote["message"], quote["refund"]
        if not can_cancel:
            return False, msg, None

        try:
            old_status = booking.status
            from app.accommodation.models.availability import BlockedDate

            # 1. RELEASE ALL BLOCKED DATES
            BlockedDate.query.filter_by(booking_id=booking.id).delete()
            logger.debug(f"Released dates for booking {booking.booking_reference}")

            # Also release InventoryBlock for room type bookings
            from app.accommodation.services.availability_service import AvailabilityService
            if booking.room_type_id:
                AvailabilityService.release_room_type_blocks(
                    room_type_id=booking.room_type_id,
                    check_in=booking.check_in,
                    check_out=booking.check_out,
                    booking_id=booking.id,
                )

            # 2. STATE TRANSITION (→ CANCELLED)
            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.CANCELLED,
                changed_by_user_id=cancelled_by_user_id,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
                trigger="booking_cancelled"
            )

            booking.cancelled_at = datetime.now(timezone.utc)
            booking.cancelled_by_user_id = cancelled_by_user_id
            booking.cancellation_reason = reason

            # Persist the cancellation quote (explicit fine line item) so the
            # penalty is auditable and independent of the withheld refund.
            snapshot = dict(booking.policy_snapshot or {})
            snapshot["cancellation_outcome"] = {
                "policy": quote["policy"],
                "phase": quote["phase"],
                "refundable_base": str(quote["refundable_base"]),
                "refund": str(quote["refund"]),
                "fine": str(quote["fine"]),
                "nights_remaining": quote["nights_remaining"],
                "days_until_checkin": quote["days_until_checkin"],
                "cancelled_by": cancelled_by_user_id,
                "cancelled_at": booking.cancelled_at.isoformat(),
                "from_status": old_status,
            }
            booking.policy_snapshot = snapshot

            # Record host policy violation if host cancels a confirmed/active booking
            if (cancelled_by_user_id == booking.host_user_id and
                old_status in [
                    AccommodationBookingStatus.CONFIRMED.value,
                    AccommodationBookingStatus.CHECKED_IN.value,
                ]):
                BookingService.record_policy_violation(
                    property_id=booking.property_id,
                    reason=f"Host cancelled booking {booking.booking_reference}: {reason}",
                )

            # 3. PROCESS REFUND IF APPLICABLE
            if refund and refund > 0:
                booking.refund_amount = refund
                booking.payment_status = AccommodationPaymentStatus.REFUNDED.value
                booking.refunded_at = datetime.now(timezone.utc)
                BookingStateMachine.transition(
                    booking,
                    AccommodationBookingStatus.REFUNDED,
                    changed_by_user_id=cancelled_by_user_id,
                    reason="Refund processed",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    trigger="refund_processed"
                )
                logger.info(f"Refund of ${refund} processed for booking {booking.booking_reference}")

            db.session.commit()
            logger.info(
                f"Booking cancelled: {booking.booking_reference} | "
                f"Cancelled by: {cancelled_by_user_id} | "
                f"Refund: ${refund if refund else 0} | Fine: ${quote['fine']} | Reason: {reason}"
            )

            return True, msg, refund

        except InvalidStateTransition as e:
            db.session.rollback()
            logger.error(f"Invalid state transition for cancellation {booking_id}: {e}")
            return False, str(e), None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Cancel booking failed for {booking_id}: {e}", exc_info=True)
            return False, "Unable to cancel booking. Please contact support.", None

    # -------------------------
    # QUERY METHODS
    # -------------------------
    @staticmethod
    def get_booking_by_reference(reference: str) -> Optional[AccommodationBooking]:
        return AccommodationBooking.query.filter_by(booking_reference=reference).first()

    @staticmethod
    def get_user_bookings(user_id: int, status: str = None, limit: int = 50, offset: int = 0) -> list:
        query = AccommodationBooking.query.filter_by(guest_user_id=user_id)
        if status:
            try:
                query = query.filter_by(status=AccommodationBookingStatus(status).value)
            except ValueError:
                logger.warning(f"Invalid status filter: {status}")
        return query.order_by(AccommodationBooking.created_at.desc()).limit(limit).offset(offset).all()

    @staticmethod
    def get_host_bookings(host_user_id: int, status: str = None, limit: int = 50, offset: int = 0) -> list:
        query = AccommodationBooking.query.filter_by(host_user_id=host_user_id)
        if status:
            try:
                query = query.filter_by(status=AccommodationBookingStatus(status).value)
            except ValueError:
                logger.warning(f"Invalid status filter: {status}")
        return query.order_by(AccommodationBooking.created_at.desc()).limit(limit).offset(offset).all()

    @staticmethod
    def get_property_bookings(property_id: int, status: str = None, limit: int = 100, offset: int = 0) -> list:
        query = AccommodationBooking.query.filter_by(property_id=property_id)
        if status:
            try:
                query = query.filter_by(status=AccommodationBookingStatus(status).value)
            except ValueError:
                logger.warning(f"Invalid status filter: {status}")
        return query.order_by(AccommodationBooking.check_in.asc()).limit(limit).offset(offset).all()

    @staticmethod
    def get_pending_expired_bookings() -> list:
        return AccommodationBooking.query.filter(
            AccommodationBooking.status.in_([
                AccommodationBookingStatus.PENDING.value,
                AccommodationBookingStatus.PENDING_APPROVAL.value,
            ]),
            AccommodationBooking.expires_at < datetime.now(timezone.utc)
        ).all()

    @staticmethod
    def cleanup_expired_bookings() -> int:
        expired_bookings = BookingService.get_pending_expired_bookings()
        count = 0
        for booking in expired_bookings:
            try:
                success, _, _ = BookingService.cancel_booking(
                    booking.id,
                    cancelled_by_user_id=None,
                    reason="Booking expired (payment not completed)",
                    ip_address="system",
                    user_agent="system"
                )
                if success:
                    count += 1
                    logger.info(f"Cleaned up expired booking: {booking.booking_reference}")
            except Exception as e:
                logger.error(f"Failed to clean up expired booking {booking.id}: {e}")
        return count

    from typing import Optional, Union, List

    # ... rest of your code ...

    @staticmethod
    def get_bookings_by_context(
            context_type: Union[str, BookingContextType],
            context_id: Optional[str] = None,
            limit: Optional[int] = 100
    ) -> List[AccommodationBooking]:
        """
        Get bookings for a specific context (event, tour, etc.).

        Args:
            context_type: Context type as string or BookingContextType enum.
            context_id: Optional specific context ID to filter.
            limit: Maximum number of results to return. Use None for no limit.

        Returns:
            List of AccommodationBooking instances.
        """
        # Convert string to enum safely
        if isinstance(context_type, str):
            try:
                context_type = BookingContextType(context_type)
            except ValueError:
                logger.warning(f"Invalid context_type: {context_type}")
                return []

        # Build and execute query (DB stores string values, not enum objects)
        query = AccommodationBooking.query.filter_by(
            context_type=context_type.value
        ).order_by(AccommodationBooking.created_at.desc())

        if context_id:
            query = query.filter_by(context_id=context_id)

        if limit is not None:
            query = query.limit(limit)

        return query.all()

    # -------------------------
    # BOOKING OWNER CLAIM (D-003, D-004)
    # -------------------------
    @staticmethod
    def generate_claim_token(booking_id: int) -> str:
        """Generate a secure single-use claim token for a third-party booking."""
        import hashlib
        import secrets

        booking = db.session.get(AccommodationBooking, booking_id)
        if not booking:
            raise ValueError(f"Booking {booking_id} not found")

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        booking.claim_token_hash = token_hash
        db.session.commit()
        return raw_token

    @staticmethod
    def claim_booking(token: str, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Claim a third-party booking by verifying the token and linking
        the authenticated user as the Booking Owner.
        """
        import hashlib

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        booking = AccommodationBooking.query.filter_by(
            claim_token_hash=token_hash
        ).first()

        if not booking:
            return False, "Invalid or expired claim token."

        if booking.booking_owner_id is not None:
            return False, "This booking has already been claimed."

        user = db.session.get(User, user_id)
        if not user:
            return False, "User not found."

        booking.booking_owner_id = user_id
        booking.owner_claimed_at = datetime.now(timezone.utc)
        booking.claim_token_hash = None  # Single-use token
        db.session.commit()

        logger.info(
            f"Booking {booking.booking_reference} claimed by user {user_id}"
        )
        return True, None

    # -------------------------
    # PAYMENT LEDGER HELPERS
    # -------------------------
    @staticmethod
    def get_payment_event(booking_id: int, wallet_txn_id: str = None):
        """Get the payment event for a booking."""
        from app.accommodation.models.booking_payment import AccommodationBookingPayment
        query = AccommodationBookingPayment.query.filter_by(booking_id=booking_id)
        if wallet_txn_id:
            query = query.filter_by(wallet_txn_id=wallet_txn_id)
        return query.order_by(AccommodationBookingPayment.created_at.desc()).first()

    @staticmethod
    def update_payment_event(
        booking_id: int,
        payment_status: str,
        wallet_txn_id: str = None,
        payment_method: str = None,
        payment_gateway: str = None,
        gateway_transaction_id: str = None,
        failure_reason: str = None,
        idempotency_key: str = None,
    ) -> Optional['AccommodationBookingPayment']:
        """Create or update the thin payment event index for a booking.

        Idempotency: if *idempotency_key* is provided and a payment event
        already exists with that key, the existing event is returned
        immediately (and optionally updated if ``payment_status`` indicates
        a terminal state).  This prevents duplicate rows when payment
        callbacks or checkout steps are retried.
        """
        from app.accommodation.models.booking_payment import AccommodationBookingPayment

        # --- Idempotency guard ---
        if idempotency_key:
            existing = AccommodationBookingPayment.query.filter_by(
                idempotency_key=idempotency_key
            ).first()
            if existing:
                # If the caller is reporting a terminal state, update the
                # existing record so it doesn't stay in 'pending' forever.
                if payment_status in ("success", "failed", "refunded"):
                    existing.payment_status = payment_status
                    if wallet_txn_id:
                        existing.wallet_txn_id = wallet_txn_id
                    if failure_reason:
                        existing.failure_reason = failure_reason
                    db.session.commit()
                logger.info(
                    "Payment event idempotency hit for key=%s, booking=%s",
                    idempotency_key, booking_id
                )
                return existing

        # --- Normal path ---
        event = AccommodationBookingPayment.query.filter_by(
            booking_id=booking_id,
        ).order_by(AccommodationBookingPayment.created_at.desc()).first()

        if not event:
            event = AccommodationBookingPayment(
                booking_id=booking_id,
                wallet_txn_id=wallet_txn_id,
                payment_reference=AccommodationBookingPayment.generate_payment_reference(),
                payment_status=payment_status,
                payment_method=payment_method or "unknown",
                idempotency_key=idempotency_key,
            )
            db.session.add(event)
        else:
            if payment_status:
                event.payment_status = payment_status
            if wallet_txn_id:
                event.wallet_txn_id = wallet_txn_id
            if payment_method:
                event.payment_method = payment_method
            if payment_gateway:
                event.payment_gateway = payment_gateway
            if gateway_transaction_id:
                event.gateway_transaction_id = gateway_transaction_id
            if failure_reason:
                event.failure_reason = failure_reason
            if idempotency_key and not event.idempotency_key:
                # Backfill key on an existing event that was created before
                # this hardening.
                event.idempotency_key = idempotency_key

        if payment_status == "failed":
            event.retry_count = (event.retry_count or 0) + 1

        db.session.commit()
        return event


