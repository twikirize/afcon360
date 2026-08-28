"""
Tests for booking_mode feature (INSTANT vs HOST_APPROVAL).
"""
import pytest
import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
    AccommodationPaymentStatus,
)
from app.accommodation.models.property import Property
from app.accommodation.services.booking_service import BookingService
from app.accommodation.state_machine.booking_states import (
    BookingStateMachine,
    InvalidStateTransition,
)
from app.extensions import db


@pytest.fixture
def host_user(test_db):
    """Create a host user."""
    from app.identity.models.user import User

    user = User(
        email=f"host-{uuid.uuid4().hex[:6]}@example.com",
        username=f"host-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def guest_user(test_db):
    """Create a guest user."""
    from app.identity.models.user import User

    user = User(
        email=f"guest-{uuid.uuid4().hex[:6]}@example.com",
        username=f"guest-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def instant_property(host_user):
    """Create a property with INSTANT booking mode (default)."""
    prop = Property(
        owner_user_id=host_user.id,
        title="Instant Book Property",
        description="A property with instant booking enabled",
        property_type="apartment",
        address_line1="123 Main St",
        city="Kampala",
        country="UG",
        base_price_per_night=Decimal("100.00"),
        currency="UGX",
        max_guests=4,
        bedrooms=2,
        beds=2,
        bathrooms=1.5,
        cancellation_policy="moderate",
        check_in_time="14:00",
        check_out_time="11:00",
        min_stay_nights=1,
        status="published",
        visibility="public",
        is_publicly_visible=True,
        is_active=True,
        booking_mode="instant",  # Default
    )
    db.session.add(prop)
    db.session.commit()
    return prop


@pytest.fixture
def host_approval_property(host_user):
    """Create a property with HOST_APPROVAL booking mode."""
    prop = Property(
        owner_user_id=host_user.id,
        title="Host Approval Property",
        description="A property requiring host approval",
        property_type="apartment",
        address_line1="456 Oak Ave",
        city="Kampala",
        country="UG",
        base_price_per_night=Decimal("150.00"),
        currency="UGX",
        max_guests=4,
        bedrooms=2,
        beds=2,
        bathrooms=1.5,
        cancellation_policy="moderate",
        check_in_time="14:00",
        check_out_time="11:00",
        min_stay_nights=1,
        status="published",
        visibility="public",
        is_publicly_visible=True,
        is_active=True,
        booking_mode="host_approval",
    )
    db.session.add(prop)
    db.session.commit()
    return prop


class TestBookingModeInstant:
    """Tests for INSTANT booking mode (default)."""

    def test_instant_booking_created_as_draft_then_pending_payment(
        self, instant_property, guest_user
    ):
        """INSTANT bookings should transition DRAFT -> HELD -> PENDING_PAYMENT."""
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        booking, error = BookingService.create_booking(
            property_id=instant_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        assert error is None
        assert booking is not None
        # Should be in PENDING_PAYMENT after creation
        assert booking.status == AccommodationBookingStatus.PENDING_PAYMENT.value
        assert booking.payment_status == AccommodationPaymentStatus.PENDING.value

    def test_instant_booking_confirms_on_payment(
        self, instant_property, guest_user
    ):
        """INSTANT booking should transition to CONFIRMED after payment."""
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        booking, _ = BookingService.create_booking(
            property_id=instant_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        # Confirm payment
        success, error = BookingService.confirm_booking(
            booking_id=booking.id,
            wallet_transaction_id="test-txn-123",
        )

        assert success
        assert error is None

        # Reload and verify
        db.session.refresh(booking)
        assert booking.status == AccommodationBookingStatus.CONFIRMED.value
        assert booking.payment_status == AccommodationPaymentStatus.PAID.value

    def test_default_booking_mode_is_instant(self, host_user):
        """Properties should default to INSTANT booking mode."""
        prop = Property(
            owner_user_id=host_user.id,
            title="Default Property",
            description="Test",
            property_type="apartment",
            address_line1="123 Main St",
            city="Kampala",
            country="UG",
            base_price_per_night=Decimal("100.00"),
            currency="UGX",
            max_guests=4,
            status="published",
            is_active=True,
            # booking_mode not specified - should default to "instant"
        )
        db.session.add(prop)
        db.session.commit()

        assert prop.booking_mode == "instant"


class TestBookingModeHostApproval:
    """Tests for HOST_APPROVAL booking mode."""

    def test_host_approval_booking_created_as_pending_approval(
        self, host_approval_property, guest_user
    ):
        """HOST_APPROVAL bookings should transition to PENDING_APPROVAL."""
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        booking, error = BookingService.create_booking(
            property_id=host_approval_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        assert error is None
        assert booking is not None
        # Should be in PENDING_APPROVAL after creation
        assert booking.status == AccommodationBookingStatus.PENDING_APPROVAL.value
        assert booking.payment_status == AccommodationPaymentStatus.PENDING.value

    def test_host_approval_payment_received_stays_pending_approval(
        self, host_approval_property, guest_user
    ):
        """Payment for HOST_APPROVAL booking should NOT auto-confirm."""
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        booking, _ = BookingService.create_booking(
            property_id=host_approval_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        # Confirm payment
        success, error = BookingService.confirm_booking(
            booking_id=booking.id,
            wallet_transaction_id="test-txn-456",
        )

        assert success
        assert error is None

        # Reload and verify - should STILL be PENDING_APPROVAL
        db.session.refresh(booking)
        assert booking.status == AccommodationBookingStatus.PENDING_APPROVAL.value
        assert booking.payment_status == AccommodationPaymentStatus.PAID.value

    def test_host_can_approve_pending_booking(
        self, host_approval_property, guest_user, host_user
    ):
        """Host can approve a PENDING_APPROVAL booking."""
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        booking, _ = BookingService.create_booking(
            property_id=host_approval_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        # Host approves
        success, error = BookingService.approve_booking(
            booking_id=booking.id,
            approved_by_user_id=host_user.id,
            reason="Approved by host",
        )

        assert success
        assert error is None

        # Reload and verify - should be CONFIRMED
        db.session.refresh(booking)
        assert booking.status == AccommodationBookingStatus.CONFIRMED.value
        assert booking.host_approved_at is not None

    def test_host_can_reject_pending_booking(
        self, host_approval_property, guest_user, host_user
    ):
        """Host can reject a PENDING_APPROVAL booking."""
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        booking, _ = BookingService.create_booking(
            property_id=host_approval_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        # Host rejects
        success, error = BookingService.reject_booking(
            booking_id=booking.id,
            rejected_by_user_id=host_user.id,
            reason="Not available",
        )

        assert success
        assert error is None

        # Reload and verify - should be CANCELLED
        db.session.refresh(booking)
        assert booking.status == AccommodationBookingStatus.CANCELLED.value
        assert booking.host_rejected_at is not None

    def test_changing_mode_does_not_affect_existing_bookings(
        self, host_approval_property, guest_user, host_user
    ):
        """Changing booking_mode should not retroactively change existing bookings."""
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        # Create booking while in HOST_APPROVAL mode
        booking, _ = BookingService.create_booking(
            property_id=host_approval_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        assert booking.status == AccommodationBookingStatus.PENDING_APPROVAL.value

        # Change property to INSTANT mode
        host_approval_property.booking_mode = "instant"
        db.session.commit()

        # Existing booking should remain PENDING_APPROVAL
        db.session.refresh(booking)
        assert booking.status == AccommodationBookingStatus.PENDING_APPROVAL.value

        # New booking should be INSTANT
        new_booking, _ = BookingService.create_booking(
            property_id=host_approval_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in + timedelta(days=10),
            check_out=check_in + timedelta(days=12),
            num_guests=2,
            rooms_requested=1,
        )

        assert new_booking.status == AccommodationBookingStatus.PENDING_PAYMENT.value


class TestBookingModeAvailability:
    """Tests for availability validation in both modes."""

    def test_unavailable_property_cannot_be_instant_booked(
        self, instant_property, guest_user
    ):
        """Even INSTANT mode should validate availability."""
        # First, create and confirm a booking to block dates
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        booking1, _ = BookingService.create_booking(
            property_id=instant_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )
        BookingService.confirm_booking(booking1.id, "txn-1")

        # Second booking for same dates should fail
        guest2 = type('Guest', (), {'id': 99999})()  # Mock user
        from app.identity.models.user import User
        guest2 = User(
            email="guest2@example.com",
            username="guest2",
            password_hash="hash",
            email_verified=True,
            phone_verified=True,
            kyc_level=2,
        )
        db.session.add(guest2)
        db.session.commit()

        booking2, error = BookingService.create_booking(
            property_id=instant_property.id,
            guest_user_id=guest2.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        # Should fail due to availability
        assert booking2 is None or error is not None

    def test_host_approval_also_validates_availability(
        self, host_approval_property, guest_user
    ):
        """HOST_APPROVAL mode should also validate availability."""
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        # First booking
        booking1, _ = BookingService.create_booking(
            property_id=host_approval_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        # Second booking for same dates
        from app.identity.models.user import User
        guest2 = User(
            email="guest3@example.com",
            username="guest3",
            password_hash="hash",
            email_verified=True,
            phone_verified=True,
            kyc_level=2,
        )
        db.session.add(guest2)
        db.session.commit()

        booking2, error = BookingService.create_booking(
            property_id=host_approval_property.id,
            guest_user_id=guest2.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        # Should fail due to availability
        assert booking2 is None or error is not None


class TestPaymentValidation:
    """Tests for payment/availability validation before confirmation."""

    def test_instant_booking_requires_payment_validation(
        self, instant_property, guest_user
    ):
        """INSTANT bookings require payment validation before CONFIRMED."""
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        booking, _ = BookingService.create_booking(
            property_id=instant_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        # Should be PENDING_PAYMENT
        assert booking.status == AccommodationBookingStatus.PENDING_PAYMENT.value

        # Cannot confirm without payment (simulated by not calling confirm_booking)
        db.session.refresh(booking)
        assert booking.status != AccommodationBookingStatus.CONFIRMED.value

    def test_host_approval_booking_requires_payment_and_approval(
        self, host_approval_property, guest_user, host_user
    ):
        """HOST_APPROVAL bookings need both payment AND host approval."""
        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)

        booking, _ = BookingService.create_booking(
            property_id=host_approval_property.id,
            guest_user_id=guest_user.id,
            check_in=check_in,
            check_out=check_out,
            num_guests=2,
            rooms_requested=1,
        )

        # Initially PENDING_APPROVAL
        assert booking.status == AccommodationBookingStatus.PENDING_APPROVAL.value

        # Payment alone doesn't confirm
        BookingService.confirm_booking(booking.id, "txn-1")
        db.session.refresh(booking)
        assert booking.status == AccommodationBookingStatus.PENDING_APPROVAL.value

        # Host approval confirms
        BookingService.approve_booking(booking.id, host_user.id)
        db.session.refresh(booking)
        assert booking.status == AccommodationBookingStatus.CONFIRMED.value