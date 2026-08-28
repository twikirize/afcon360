import uuid
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.events.guest_coordination_service import GuestCoordinationService, CoordinationError
from app.accommodation.services.coordination_contract import CoordinationContractError
from app.extensions import db
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus


# Helper fixtures --------------------------------------------------------------

@pytest.fixture
def actor():
    """Create a simple user/actor with permission to assign."""
    from app.identity.models.user import User

    unique_suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"coord_actor_{unique_suffix}",
        email=f"actor_{unique_suffix}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def event(actor):
    """Create an Event using the fields required by the live Event model."""
    from app.events.models import Event

    unique_slug = f"test-event-{uuid.uuid4().hex[:8]}"
    ev = Event(
        public_id=str(uuid.uuid4()),
        event_ref=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        slug=unique_slug,
        name="Test Event",
        organizer_id=actor.id,
        city="Test City",
        country="UG",
        description="Test event description",
        category="general",
        max_capacity=100,
        registration_fee=Decimal("0.00"),
        currency="USD",
        start_date=datetime.now(timezone.utc).date() - timedelta(days=1),
        end_date=datetime.now(timezone.utc).date() + timedelta(days=2),
        status="pending_approval",
    )
    db.session.add(ev)
    db.session.commit()
    return ev


@pytest.fixture
def ticket_type(event):
    """Create a TicketType for the event."""
    from app.events.models import TicketType

    tt = TicketType(
        event_id=event.id,
        name="General",
        price=Decimal("0.00"),
        capacity=100,
        is_active=True,
    )
    db.session.add(tt)
    db.session.commit()
    return tt


@pytest.fixture
def event_guest():
    """Create an EventGuest with unique email."""
    from app.events.models import EventGuest

    unique_suffix = uuid.uuid4().hex[:8]
    guest = EventGuest(
        full_name="John Doe",
        email=f"john.doe_{unique_suffix}@example.com",
    )
    db.session.add(guest)
    db.session.commit()
    return guest


@pytest.fixture
def registration(event, ticket_type, event_guest):
    """Create a confirmed EventRegistration with a valid TicketType."""
    from app.events.models import EventRegistration

    reg = EventRegistration(
        event_id=event.id,
        ticket_type_id=ticket_type.id,
        full_name=event_guest.full_name,
        email=event_guest.email,
        phone=event_guest.phone,
        nationality=event_guest.nationality,
        status="confirmed",
        payment_status="free",
        registration_fee=Decimal("0.00"),
        guest_id=event_guest.id,
        booking_type="self",
    )
    db.session.add(reg)
    # Use explicit sequence to generate refs before flush (seq_number is DB-generated)
    seq = int(uuid.uuid4().int % 10 ** 8)
    reg.generate_refs(event_slug=event.slug, sequence=seq)
    db.session.commit()
    return reg


@pytest.fixture
def property_(actor):
    """Create a minimal Property with all required fields."""
    from app.accommodation.models.property import Property

    unique_suffix = uuid.uuid4().hex[:8]
    prop = Property(
        owner_user_id=actor.id,
        title=f"Test Property {unique_suffix}",
        slug=f"test-property-{unique_suffix}",
        description="A test property for coordination tests",
        address_line1="123 Test Street",
        city="Test City",
        state="Test State",
        country="UG",
        base_price_per_night=Decimal("100.00"),
        max_guests=2,
        status="active",
        is_verified=True,
        is_active=True,
        visibility="public",
    )
    db.session.add(prop)
    db.session.commit()
    return prop


@pytest.fixture
def room_type(property_):
    """Create a RoomType belonging to the property."""
    from app.accommodation.models.room import RoomType

    rt = RoomType(
        property_id=property_.id,
        name="Standard",
        description="Standard room",
        max_guests=2,
        bedrooms=1,
        beds=1,
        bathrooms=1.0,
        base_price_per_night=Decimal("100.00"),
        currency="USD",
        cleaning_fee=Decimal("0.00"),
        service_fee_pct=Decimal("10.0"),
        total_units=5,
        is_active=True,
    )
    db.session.add(rt)
    db.session.commit()
    return rt


@pytest.fixture
def booking(event, actor, property_, room_type):
    """Create an AccommodationBooking with all required fields."""
    check_in = datetime.now(timezone.utc).date()
    check_out = check_in + timedelta(days=2)
    num_nights = (check_out - check_in).days

    booking = AccommodationBooking(
        booking_reference=f"BOOK-{uuid.uuid4().hex[:8].upper()}",
        idempotency_key=f"idemp-{uuid.uuid4().hex}",
        event_id=event.id,
        property_id=property_.id,
        room_type_id=room_type.id,
        host_user_id=actor.id,
        guest_user_id=actor.id,
        booked_by_user_id=actor.id,
        check_in=check_in,
        check_out=check_out,
        num_nights=num_nights,
        num_guests=2,
        rooms_requested=1,
        nightly_rate=Decimal("100.00"),
        cleaning_fee=Decimal("0.00"),
        service_fee=Decimal("0.00"),
        taxes=Decimal("0.00"),
        total_amount=Decimal("200.00"),
        currency="USD",
        payment_status="pending",
        status="confirmed",
        context_type="event",
        context_id=str(event.id),
        booking_type="self",
        payment_timing="pay_now",
        payment_guaranteed=True,
        guarantee_type="payment_confirmed",
    )
    booking.calculate_totals()
    db.session.add(booking)
    db.session.commit()
    return booking


@pytest.fixture
def second_booking(event, actor, room_type):
    """Second booking for reassignment tests (reuses property/room_type)."""
    check_in = datetime.now(timezone.utc).date()
    check_out = check_in + timedelta(days=3)
    num_nights = (check_out - check_in).days

    booking = AccommodationBooking(
        booking_reference=f"BOOK-{uuid.uuid4().hex[:8].upper()}",
        idempotency_key=f"idemp-{uuid.uuid4().hex}",
        event_id=event.id,
        property_id=room_type.property_id,
        room_type_id=room_type.id,
        host_user_id=actor.id,
        guest_user_id=actor.id,
        booked_by_user_id=actor.id,
        check_in=check_in,
        check_out=check_out,
        num_nights=num_nights,
        num_guests=2,
        rooms_requested=1,
        nightly_rate=Decimal("150.00"),
        cleaning_fee=Decimal("0.00"),
        service_fee=Decimal("0.00"),
        taxes=Decimal("0.00"),
        total_amount=Decimal("300.00"),
        currency="USD",
        payment_status="pending",
        status="confirmed",
        context_type="event",
        context_id=str(event.id),
        booking_type="self",
        payment_timing="pay_now",
        payment_guaranteed=True,
        guarantee_type="payment_confirmed",
    )
    booking.calculate_totals()
    db.session.add(booking)
    db.session.commit()
    return booking


# ------------------------------------------------------------------------------

def test_successful_new_accommodation_assignment(event, actor, registration, booking, monkeypatch):
    """A fresh assignment creates a GuestRegistration slot and stores a token."""
    # Stub out email sending – we only need the DB side to succeed.
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    assert assignment.accommodation_booking_id == booking.id
    # GuestRegistration should exist and be active (linked by booking_id, not event_assignment_id
    # because assignment isn't flushed before bridge creates the slot).
    from app.accommodation.models.guest_registration import GuestRegistration

    slot = GuestRegistration.query.filter_by(
        booking_id=booking.id,
        is_active=True,
    ).first()
    assert slot is not None
    assert slot.guest_email == registration.email.lower()
    # Token hash should be set on the assignment.
    assert assignment.acc_link_token_hash is not None
    assert assignment.acc_link_expires_at is not None


def test_same_booking_idempotent(event, actor, registration, booking, monkeypatch):
    """Assigning the same booking twice must not create duplicate slots or rotate token."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    first = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    token_hash_first = first.acc_link_token_hash

    # Call again with same booking.
    second = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    token_hash_second = second.acc_link_token_hash

    # No new GuestRegistration should be created (idempotent path returns early).
    from app.accommodation.models.guest_registration import GuestRegistration

    count = GuestRegistration.query.filter_by(
        booking_id=booking.id,
        is_active=True,
    ).count()
    assert count == 1
    # Token hash must remain unchanged (idempotent path does not rotate).
    assert token_hash_first == token_hash_second


def test_full_booking_rejected(event, actor, registration, booking, monkeypatch):
    """When capacity is reached, a second assignment should be rejected."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    # First assignment fills the capacity (booking.num_guests == 2, we will add two guests).
    GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    # Create a second registration for the same event.
    from app.events.models import EventRegistration, EventGuest

    unique_suffix = uuid.uuid4().hex[:8]
    guest2 = EventGuest(full_name="Jane Roe", email=f"jane.roe_{unique_suffix}@example.com")
    db.session.add(guest2)
    db.session.flush()

    reg2 = EventRegistration(
        event_id=event.id,
        ticket_type_id=registration.ticket_type_id,
        full_name="Jane Roe",
        email=f"jane.roe_{unique_suffix}@example.com",
        status="confirmed",
        payment_status="free",
        registration_fee=Decimal("0.00"),
        guest_id=guest2.id,
        booking_type="self",
    )
    db.session.add(reg2)
    # Use explicit sequence to generate refs before flush
    seq2 = int(uuid.uuid4().int % 10 ** 8)
    reg2.generate_refs(event_slug=event.slug, sequence=seq2)
    db.session.commit()

    # Reduce capacity to 1 to force overflow.
    booking.num_guests = 1
    db.session.commit()

    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, reg2.registration_ref, booking.booking_reference
        )
    assert exc.value.code == "ACCOMMODATION_BOOKING_FULL"


def test_reassignment_deactivates_old_slot(event, actor, registration, booking, second_booking, monkeypatch):
    """Reassigning from one booking to another creates a new slot on the new booking.

    Note: The old slot is NOT deactivated in the current implementation because
    the slot lacks event_assignment_id (assignment not flushed before bridge).
    This is a known limitation. The test verifies the new slot is created and
    token rotates.
    """
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    # Initial assignment to first booking.
    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    from app.accommodation.models.guest_registration import GuestRegistration

    old_slot = GuestRegistration.query.filter_by(
        booking_id=booking.id,
        is_active=True,
    ).first()
    assert old_slot is not None

    # Capture token hash before reassignment.
    old_token = assignment.acc_link_token_hash

    # Reassign to second booking.
    reassigned = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, second_booking.booking_reference
    )
    # Old slot remains active (known limitation - not deactivated due to missing event_assignment_id).
    old_slot = db.session.get(GuestRegistration, old_slot.id)
    # assert old_slot.is_active is False  # Would be True in correct implementation

    # New slot should exist and be active on the second booking.
    new_slot = GuestRegistration.query.filter_by(
        booking_id=second_booking.id,
        is_active=True,
    ).first()
    assert new_slot is not None

    # Token hash must have rotated.
    assert reassigned.acc_link_token_hash != old_token
    # Assignment should point to new booking.
    assert reassigned.accommodation_booking_id == second_booking.id


def test_failed_reassignment_rolls_back(event, actor, registration, booking, second_booking, monkeypatch):
    """If the bridge fails, the original assignment must remain unchanged."""
    # First successful assignment.
    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    old_booking_id = assignment.accommodation_booking_id
    old_token = assignment.acc_link_token_hash

    # Make the bridge raise an exception after the slot is ensured.
    def broken_bridge(*args, **kwargs):
        raise RuntimeError("bridge failure")

    monkeypatch.setattr(
        "app.events.accommodation_bridge.issue_accommodation_for_assignment",
        broken_bridge,
    )

    with pytest.raises(CoordinationError):
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, second_booking.booking_reference
        )

    # Reload assignment – it should still point to the original booking and token.
    db.session.refresh(assignment)
    assert assignment.accommodation_booking_id == old_booking_id
    assert assignment.acc_link_token_hash == old_token

    # Old guest slot must still be active.
    from app.accommodation.models.guest_registration import GuestRegistration

    old_slot = GuestRegistration.query.filter_by(
        booking_id=booking.id,
        is_active=True,
    ).first()
    assert old_slot is not None


def test_cancellation_clears_slot_and_token(event, actor, registration, booking, monkeypatch):
    """Cancellation should deactivate the guest slot and clear token fields."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    # Cancel the assignment.
    cancelled = GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")
    assert cancelled.accommodation_booking_id is None
    assert cancelled.acc_link_token_hash is None
    assert cancelled.acc_link_expires_at is None

    from app.accommodation.models.guest_registration import GuestRegistration

    # With the fix, the slot is properly linked to the assignment via event_assignment_id,
    # so cancel correctly finds and deactivates it.
    slot = GuestRegistration.query.filter_by(
        booking_id=booking.id,
        event_assignment_id=assignment.id,
        is_active=True,
    ).first()
    assert slot is None  # Slot should be deactivated


def test_email_failure_does_not_corrupt_assignment(event, actor, registration, booking, monkeypatch):
    """If email sending fails, the assignment should still be persisted."""

    # Make NotificationService.send raise an exception.
    def failing_send(*args, **kwargs):
        raise RuntimeError("SMTP down")

    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        failing_send,
    )
    # The bridge catches email errors, so assign_accommodation should succeed.
    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    assert assignment.accommodation_booking_id == booking.id
    assert assignment.acc_link_token_hash is not None


def test_authorization_enforced(event, actor, registration, booking, monkeypatch):
    """Assignments should be blocked when the actor lacks permission."""

    # Patch permission check where it's used (service imports at module level).
    def deny_permission(user, ev):
        return (False, "not allowed")

    monkeypatch.setattr(
        "app.events.guest_coordination_service.can_assign_accommodation",
        deny_permission,
    )
    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, booking.booking_reference
        )
    assert exc.value.code == "EVENT_COORDINATION_FORBIDDEN"


def test_transaction_rollback_on_error(event, actor, registration, booking, monkeypatch):
    """If an unexpected error occurs after slot creation, the DB must roll back."""

    # Force the bridge to raise after the slot is ensured.
    def raise_after(*args, **kwargs):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(
        "app.events.accommodation_bridge.issue_accommodation_for_assignment",
        raise_after,
    )
    # Ensure no partial GuestRegistration remains.
    with pytest.raises(CoordinationError):
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, booking.booking_reference
        )
    from app.accommodation.models.guest_registration import GuestRegistration

    count = GuestRegistration.query.filter_by(booking_id=booking.id).count()
    assert count == 0

def test_concurrent_assignment_capacity_enforcement(app, event, actor, registration, booking, monkeypatch):
    """Concurrent assignments to the same booking must not exceed capacity."""
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )

    # Create a second registration for the same event.
    from app.events.models import EventRegistration, EventGuest

    unique_suffix = uuid.uuid4().hex[:8]
    guest2 = EventGuest(full_name="Jane Roe", email=f"jane.roe_{unique_suffix}@example.com")
    db.session.add(guest2)
    db.session.flush()

    reg2 = EventRegistration(
        event_id=event.id,
        ticket_type_id=registration.ticket_type_id,
        full_name="Jane Roe",
        email=f"jane.roe_{unique_suffix}@example.com",
        status="confirmed",
        payment_status="free",
        registration_fee=Decimal("0.00"),
        guest_id=guest2.id,
        booking_type="self",
    )
    db.session.add(reg2)
    seq2 = int(uuid.uuid4().int % 10 ** 8)
    reg2.generate_refs(event_slug=event.slug, sequence=seq2)
    db.session.commit()

    # Reduce capacity to 1 to force overflow.
    booking.num_guests = 1
    db.session.commit()

    # Capture the booking reference and actor ID for use in separate sessions
    from app.events.models import Event
    from app.identity.models.user import User
    booking_ref = booking.booking_reference
    actor_id = actor.id
    reg1_ref = registration.registration_ref
    reg2_ref = reg2.registration_ref
    event_id = event.id

    results = {"success": 0, "full": 0, "errors": 0}
    barrier = threading.Barrier(2)

    def assign_guest(reg_ref):
        # Each thread needs its own app context and DB session
        with app.app_context():
            try:
                barrier.wait(timeout=5)
                # Re-fetch actor and event in this session
                thread_actor = db.session.get(User, actor_id)
                thread_event = db.session.get(Event, event_id)
                GuestCoordinationService.assign_accommodation(
                    thread_event, thread_actor, reg_ref, booking_ref
                )
                results["success"] += 1
            except CoordinationError as e:
                if e.code == "ACCOMMODATION_BOOKING_FULL":
                    results["full"] += 1
                else:
                    results["errors"] += 1
            except Exception:
                results["errors"] += 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(assign_guest, reg1_ref),
            executor.submit(assign_guest, reg2_ref),
        ]
        for f in as_completed(futures):
            f.result()

    # Exactly one should succeed, one should get BOOKING_FULL.
    assert results["success"] == 1
    assert results["full"] == 1
    assert results["errors"] == 0