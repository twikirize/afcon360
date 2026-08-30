"""Attendee-initiated accommodation booking orchestration.

Thin service layer that coordinates existing domain services to allow an event
attendee to book accommodation through the event flow.

Does NOT own:
- booking state (Accommodation owns AccommodationBooking)
- payment state (Payment owns AccommodationBookingPayment / TransactionModel)
- wallet state (Wallet owns ledger/accounts)
- accommodation capacity (Accommodation owns Property/RoomType/InventoryBlock)
- property policy (Accommodation owns PropertyBookingPolicy)
- payment processor logic (Accommodation/Wallet own their processors)

Only coordinates:
- BookingService.create_booking()
- AccommodationCoordinationContract.ensure_event_guest_slot()
- BookingPolicyEvaluator for payment requirements
- WalletService.transfer() for organizer-to-attendee funding
"""

from dataclasses import dataclass
from decimal import Decimal
from datetime import date
from typing import Optional, List, Dict, Any
from flask import current_app
from sqlalchemy import text

from app.extensions import db
from app.events.models import Event, EventRegistration, EventAssignment
from app.events.accommodation_bridge import issue_accommodation_for_assignment
from app.accommodation.services.booking_service import BookingService
from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
    AccommodationPaymentStatus,
    BookingContextType,
)
from app.accommodation.services.coordination_contract import (
    AccommodationCoordinationContract,
    CoordinationContractError,
)
from app.accommodation.state_machine.policy_evaluator import BookingPolicyEvaluator
from app.wallet.services.wallet_service import WalletService
from app.wallet.exceptions import (
    InsufficientBalanceError,
    ComplianceBlockError,
    LimitExceededError,
    WalletNotFoundError,
)


class AttendeeAccommodationBookingError(Exception):
    """Error raised when attendee accommodation booking orchestration fails."""
    
    def __init__(self, code: str, message: str = "", details: Optional[Dict] = None):
        self.code = code
        self.message = message or code
        self.details = details or {}
        super().__init__(self.message)


@dataclass
class BookingCreationResult:
    """Result of attendee-initiated accommodation booking creation."""
    booking: AccommodationBooking
    assignment: EventAssignment
    payment_timing: str
    payment_required: bool
    required_amount: Optional[Decimal] = None
    payment_options: Optional[List[str]] = None


class AttendeeAccommodationBookingService:
    """Orchestration service for attendee-initiated accommodation bookings via events."""
    
    @staticmethod
    def _require_event_attendee(event: Event, registration: EventRegistration) -> None:
        """Verify registration belongs to event and is confirmed."""
        if registration.event_id != event.id:
            raise AttendeeAccommodationBookingError(
                "REGISTRATION_EVENT_MISMATCH",
                "Registration does not belong to this event"
            )
        if registration.status != "confirmed":
            raise AttendeeAccommodationBookingError(
                "REGISTRATION_NOT_CONFIRMED",
                "Only confirmed attendees can book accommodation"
            )
    
    @staticmethod
    def _get_or_create_assignment(
        event: Event,
        registration: EventRegistration
    ) -> EventAssignment:
        """Get or create the EventAssignment for this registration."""
        attendee_id = registration.user_id or getattr(registration, "attendee_user_id", None)
        
        assignment = EventAssignment.query.filter_by(
            event_id=event.id,
            registration_id=registration.id,
        ).with_for_update().first()
        
        if assignment is None and attendee_id is not None:
            assignment = EventAssignment.query.filter_by(
                event_id=event.id,
                attendee_id=attendee_id,
            ).with_for_update().first()
            if assignment is not None:
                assignment.registration_id = registration.id
        
        if assignment is not None and getattr(assignment, "is_deleted", False):
            assignment.is_deleted = False
            assignment.deleted_at = None
        
        if assignment is None:
            assignment = EventAssignment(
                event_id=event.id,
                attendee_id=attendee_id,
                registration_id=registration.id,
            )
            db.session.add(assignment)
            db.session.flush()
        
        return assignment
    
    @staticmethod
    def _verify_property_availability(
        property_id: int,
        check_in: date,
        check_out: date,
        rooms_requested: int = 1,
        room_type_id: Optional[int] = None
    ) -> None:
        """Verify property has availability for the requested dates."""
        from app.accommodation.services.availability_service import AvailabilityService
        from app.accommodation.models.availability import BlockedDate
        from app.accommodation.models.room import InventoryBlock
        from app.accommodation.services.host_service import HostService
        
        if room_type_id:
            InventoryBlock.query.filter(
                InventoryBlock.room_type_id == room_type_id,
                InventoryBlock.date_range_start < check_out,
                InventoryBlock.date_range_end > check_in,
            ).with_for_update().all()
            
            available_units = HostService.available_units(
                room_type_id=room_type_id,
                check_in=check_in,
                check_out=check_out,
            )
            if available_units < rooms_requested:
                raise AttendeeAccommodationBookingError(
                    "INSUFFICIENT_CAPACITY",
                    f"Only {available_units} unit(s) available, but {rooms_requested} requested"
                )
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
            raise AttendeeAccommodationBookingError(
                "DATES_NOT_AVAILABLE",
                error or "Selected dates are not available"
            )
    
    @staticmethod
    def create_booking_for_attendee(
        event: Event,
        registration: EventRegistration,
        property_id: int,
        check_in: date,
        check_out: date,
        num_guests: int = 1,
        rooms_requested: int = 1,
        room_type_id: Optional[int] = None,
        payment_timing: Optional[str] = None,
        payment_method: Optional[str] = None,
        special_requests: Optional[str] = None,
        guest_name: Optional[str] = None,
        guest_email: Optional[str] = None,
        guest_phone: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BookingCreationResult:
        """
        Create an accommodation booking for an event attendee.
        
        This is the main entry point for attendee-initiated booking.
        The attendee must be a confirmed registrant of the event.
        
        Args:
            event: The event the attendee is registered for
            registration: The attendee's event registration
            property_id: Property to book
            check_in: Check-in date
            check_out: Check-out date
            num_guests: Number of guests
            rooms_requested: Number of rooms
            room_type_id: Specific room type (optional)
            payment_timing: Payment timing preference (pay_now, deposit, pay_on_arrival, pay_at_checkout, invoice)
            payment_method: Payment method preference
            special_requests: Special requests for the booking
            guest_name: Guest name (defaults to registration.full_name)
            guest_email: Guest email (defaults to registration.email)
            guest_phone: Guest phone
            idempotency_key: Idempotency key for duplicate prevention
            
        Returns:
            BookingCreationResult with booking, assignment, and payment requirements
            
        Raises:
            AttendeeAccommodationBookingError: If booking cannot be created
        """
        AttendeeAccommodationBookingService._require_event_attendee(event, registration)
        
        # Verify property exists and is bookable
        from app.accommodation.models.property import Property
        property_obj = db.session.get(Property, property_id)
        if not property_obj:
            raise AttendeeAccommodationBookingError("PROPERTY_NOT_FOUND", "Property not found")
        if not property_obj.can_be_booked():
            raise AttendeeAccommodationBookingError("PROPERTY_NOT_BOOKABLE", "Property is not available for booking")
        
        # Verify availability (acquires advisory lock on property to prevent race conditions)
        AttendeeAccommodationBookingService._verify_property_availability(
            property_id, check_in, check_out, rooms_requested, room_type_id
        )
        
        # Generate idempotency key if not provided
        if not idempotency_key:
            import uuid
            idempotency_key = f"event-acc-{event.id}-{registration.id}-{uuid.uuid4().hex}"
        
        # Get host user (property owner)
        host_user_id = property_obj.owner_user_id
        if not host_user_id:
            raise AttendeeAccommodationBookingError("PROPERTY_NO_HOST", "Property has no host assigned")
        
        # Get or create assignment
        assignment = AttendeeAccommodationBookingService._get_or_create_assignment(event, registration)
        
        # Create the accommodation booking using existing BookingService
        # Event context is passed via context_type and context_id
        booking, error = BookingService.create_booking(
            property_id=property_id,
            guest_user_id=registration.user_id or 0,  # Will be updated if guest has no account
            host_user_id=host_user_id,
            check_in=check_in,
            check_out=check_out,
            num_guests=num_guests,
            rooms_requested=rooms_requested,
            guest_name=guest_name or registration.full_name,
            guest_email=guest_email or registration.email,
            guest_phone=guest_phone or getattr(registration, "phone", None),
            special_requests=special_requests,
            idempotency_key=idempotency_key,
            context_type=BookingContextType.EVENT,
            context_id=str(event.public_id),
            context_metadata={
                "event_id": event.id,
                "event_slug": event.slug,
                "registration_ref": registration.registration_ref,
                "attendee_user_id": registration.user_id,
            },
            booked_by_user_id=registration.user_id or registration.id,  # Attendee books for themselves
            primary_guest_id=registration.user_id,
            primary_guest_name=guest_name or registration.full_name,
            primary_guest_email=guest_email or registration.email,
            primary_guest_phone=guest_phone or getattr(registration, "phone", None),
            booking_type="event_assigned",
            room_type_id=room_type_id,
            payment_method=payment_method,
            payment_timing=payment_timing,
            payment_guaranteed=False,  # Will be evaluated by policy
            guarantee_type="none",
        )
        
        if error:
            raise AttendeeAccommodationBookingError("BOOKING_CREATION_FAILED", error)
        
        # Link the booking to the event assignment
        assignment.accommodation_booking_id = booking.id
        
        # Create event guest slot in the booking via AccommodationCoordinationContract
        try:
            AccommodationCoordinationContract.ensure_event_guest_slot(
                booking.booking_reference,
                full_name=guest_name or registration.full_name,
                email=guest_email or registration.email,
                phone=guest_phone or getattr(registration, "phone", None),
                nationality=getattr(registration, "nationality", None),
                user_id=registration.user_id,
                event_assignment_id=assignment.id,
            )
        except CoordinationContractError as e:
            # If capacity exceeded, cancel the booking
            if e.code == "BOOKING_CAPACITY_EXCEEDED":
                db.session.rollback()
                raise AttendeeAccommodationBookingError(
                    "BOOKING_CAPACITY_EXCEEDED",
                    "Accommodation booking capacity exceeded"
                )
            raise AttendeeAccommodationBookingError("GUEST_SLOT_FAILED", str(e))
        
        # Issue completion link via bridge (creates token, sends email)
        issue_accommodation_for_assignment(event, registration, booking, assignment)
        
        db.session.commit()
        
        # Evaluate payment requirements using BookingPolicyEvaluator
        payment_decision = BookingPolicyEvaluator.can_confirm(booking)
        payment_req = BookingPolicyEvaluator._evaluate_payment_requirement(
            booking,
            BookingPolicyEvaluator.__dict__.get('_last_policy') or 
            __import__('app.accommodation.models.booking_policy', fromlist=['PropertyBookingPolicy']).PropertyBookingPolicy.query.filter_by(property_id=property_id).first() or
            __import__('app.accommodation.models.booking_policy', fromlist=['PropertyBookingPolicy']).PropertyBookingPolicy(property_id=property_id)
        )
        
        # Get allowed payment timings from property policy
        from app.accommodation.state_machine.policy_evaluator import PaymentPolicyEvaluator
        allowed_timings = PaymentPolicyEvaluator.get_allowed_payment_timings(property_id)
        
        return BookingCreationResult(
            booking=booking,
            assignment=assignment,
            payment_timing=booking.payment_timing or payment_timing or "pay_now",
            payment_required=payment_req.required,
            required_amount=payment_req.amount,
            payment_options=allowed_timings,
        )
    
    @staticmethod
    def fund_attendee_booking_from_organizer(
        event: Event,
        registration: EventRegistration,
        amount: Decimal,
        currency: str = "USD",
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transfer funds from event organizer to attendee for accommodation payment.
        
        This uses WalletService.transfer() - the ONLY wallet movement primitive.
        No "top-up" subsystem is created.
        
        Args:
            event: The event
            registration: The attendee's registration
            amount: Amount to transfer
            currency: Currency code
            idempotency_key: Idempotency key for the transfer
            
        Returns:
            WalletService.transfer() result
            
        Raises:
            AttendeeAccommodationBookingError: If transfer fails
        """
        if not registration.user_id:
            raise AttendeeAccommodationBookingError(
                "ATTENDEE_NO_ACCOUNT",
                "Attendee must have a user account to receive wallet funds"
            )
        
        # Get organizer's wallet account
        ws = WalletService()
        organizer_account = ws.account_repo.get_by_user_id(event.organizer_id, currency)
        if not organizer_account:
            raise AttendeeAccommodationBookingError(
                "ORGANIZER_NO_WALLET",
                f"Organizer has no {currency} wallet account"
            )
        
        # Get attendee's wallet account
        attendee_account = ws.account_repo.get_by_user_id(registration.user_id, currency)
        if not attendee_account:
            raise AttendeeAccommodationBookingError(
                "ATTENDEE_NO_WALLET",
                f"Attendee has no {currency} wallet account"
            )
        
        if not idempotency_key:
            import uuid
            idempotency_key = f"event-fund-{event.id}-{registration.id}-{uuid.uuid4().hex}"
        
        try:
            result = ws.transfer(
                from_account_id=str(organizer_account.id),
                to_account_id=str(attendee_account.id),
                amount=amount,
                currency=currency,
                client_request_id=idempotency_key,
                metadata={
                    "event_id": event.id,
                    "event_slug": event.slug,
                    "registration_ref": registration.registration_ref,
                    "purpose": "accommodation_funding",
                },
            )
            return result
        except InsufficientBalanceError as e:
            raise AttendeeAccommodationBookingError(
                "ORGANIZER_INSUFFICIENT_BALANCE",
                str(e)
            )
        except ComplianceBlockError as e:
            raise AttendeeAccommodationBookingError(
                "TRANSFER_COMPLIANCE_BLOCK",
                str(e)
            )
        except LimitExceededError as e:
            raise AttendeeAccommodationBookingError(
                "TRANSFER_LIMIT_EXCEEDED",
                str(e)
            )
        except WalletNotFoundError as e:
            raise AttendeeAccommodationBookingError(
                "WALLET_NOT_FOUND",
                str(e)
            )
        except Exception as e:
            raise AttendeeAccommodationBookingError(
                "TRANSFER_FAILED",
                f"Wallet transfer failed: {e}"
            )
    
    @staticmethod
    def get_booking_requirements(
        event: Event,
        registration: EventRegistration
    ) -> Dict[str, Any]:
        """
        Get payment and policy requirements for an attendee's accommodation booking.
        
        Returns a comprehensive view for frontend display, including:
        - Current booking (if exists)
        - Payment requirements for confirmation
        - Check-in requirements
        - Allowed payment timings
        - Financial summary
        """
        assignment = EventAssignment.query.filter_by(
            event_id=event.id,
            registration_id=registration.id,
        ).first()
        
        if not assignment or not assignment.accommodation_booking_id:
            return {
                "has_booking": False,
                "message": "No accommodation booking found for this attendee",
            }
        
        booking = db.session.get(AccommodationBooking, assignment.accommodation_booking_id)
        if not booking:
            return {
                "has_booking": False,
                "message": "Accommodation booking not found",
            }
        
        return BookingPolicyEvaluator.get_booking_requirements(booking)
    
    @staticmethod
    def cancel_attendee_booking(
        event: Event,
        registration: EventRegistration,
        actor_user_id: int,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Cancel an attendee's accommodation booking.
        
        Delegates to the existing AccommodationBooking.cancel() which handles
        refunds according to the booking's cancellation policy.
        
        Returns True on success, False on failure.
        """
        assignment = EventAssignment.query.filter_by(
            event_id=event.id,
            registration_id=registration.id,
        ).first()
        
        if not assignment or not assignment.accommodation_booking_id:
            return False
        
        booking = db.session.get(AccommodationBooking, assignment.accommodation_booking_id)
        if not booking:
            return False
        
        try:
            success, msg, refund = booking.cancel(
                actor_user_id,
                reason or f"Cancelled via event {event.slug}"
            )
            if success:
                # Clear the assignment link
                assignment.accommodation_booking_id = None
                db.session.commit()
            return success
        except Exception:
            db.session.rollback()
            return False
    
    @staticmethod
    def list_available_properties_for_event(
        event: Event,
        check_in: date,
        check_out: date,
        num_guests: int = 1,
        rooms_requested: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        List properties available for the event dates that the attendee can book.
        
        Queries the Accommodation module for properties in the event city
        that have availability for the requested dates.
        """
        from app.accommodation.models.property import Property, AccommodationPropertyStatus
        from app.accommodation.models.room import RoomType
        from app.accommodation.services.availability_service import AvailabilityService
        
        properties = Property.query.filter(
            Property.city == event.city,
            Property.country == event.country,
            Property.status == AccommodationPropertyStatus.ACTIVE.value,
            Property.is_deleted.is_(False),
        ).all()
        
        available = []
        for prop in properties:
            is_available, _, _ = AvailabilityService.is_range_available(
                prop.id, check_in, check_out
            )
            if not is_available:
                continue
            
            # Check if property has rooms that can accommodate the guests
            room_types = RoomType.query.filter_by(
                property_id=prop.id,
                is_active=True,
            ).all()
            
            has_capacity = any(
                rt.max_guests * rooms_requested >= num_guests
                for rt in room_types
            )
            
            if not has_capacity:
                continue
            
            # Get pricing for the dates
            from app.accommodation.services.pricing_service import PricingService
            try:
                pricing = PricingService.calculate_total(prop, check_in, check_out, num_guests)
                total_amount = pricing['total']
            except Exception:
                total_amount = prop.base_price_per_night * (check_out - check_in).days
            
            # Get payment policy
            from app.accommodation.services.payment_policy_service import PaymentPolicyService
            policy_options = PaymentPolicyService.get_allowed_options(
                prop.id, total_amount
            )
            
            available.append({
                "property_id": prop.id,
                "property_ref": prop.public_id,
                "title": prop.title,
                "description": prop.description[:200] if prop.description else "",
                "city": prop.city,
                "country": prop.country,
                "images": prop.gallery_images[:3] if prop.gallery_images else [],
                "total_amount": float(total_amount),
                "currency": prop.currency,
                "nights": (check_out - check_in).days,
                "payment_timings": policy_options['allowed_timings'],
                "payment_methods": [m['method_id'] for m in policy_options['payment_methods']],
                "cancellation_policy": policy_options['cancellation']['policy'],
            })
        
        return available