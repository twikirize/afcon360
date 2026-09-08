"""Stage 5-2 focused lifecycle tests: Event -> Accommodation assignment.

These tests close genuine gaps in the assignment negative/boundary surface that
the existing suites do not exercise:

  * invalid guest (registration not part of this event)      -> INVALID_EVENT_REGISTRATION
  * invalid booking (unknown booking reference)              -> ACCOMMODATION_BOOKING_NOT_FOUND
  * missing booking reference                                -> INVALID_EVENT_RESOURCE
  * booking in a non-assignable status                       -> ACCOMMODATION_BOOKING_UNAVAILABLE
  * inactive room type                                       -> ACCOMMODATION_ROOM_UNAVAILABLE
  * room capacity lower than booked guests                   -> ACCOMMODATION_CAPACITY_EXCEEDED
  * cross-context booking (context_id of another event)      -> BOOKING_EVENT_MISMATCH
  * provider/allocator veto                                  -> ALLOCATION_REJECTED
  * owner-linked cross-context booking remains assignable    -> positive boundary

They follow the exact fixture + assertion patterns of
tests/test_guest_coordination_accommodation.py and
tests/test_assignment_ownership_boundary.py.
"""

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.events.guest_coordination_service import GuestCoordinationService, CoordinationError
from app.extensions import db
from app.accommodation.models.booking import AccommodationBooking


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
def other_actor():
    """A second user that owns foreign bookings / a foreign event."""
    from app.identity.models.user import User

    unique_suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"other_owner_{unique_suffix}",
        email=f"other_owner_{unique_suffix}@example.com",
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
def other_event(other_actor):
    """A second event used for cross-event / cross-context negative cases."""
    from app.events.models import Event

    unique_slug = f"other-event-{uuid.uuid4().hex[:8]}"
    ev = Event(
        public_id=str(uuid.uuid4()),
        event_ref=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        slug=unique_slug,
        name="Other Event",
        organizer_id=other_actor.id,
        city="Other City",
        country="UG",
        description="Other event",
        category="general",
        max_capacity=100,
        registration_fee=Decimal("0.00"),
        currency="USD",
        start_date=datetime.now(timezone.utc).date(),
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


def _make_booking(**overrides):
    """Build (without committing) an AccommodationBooking with optional overrides."""
    check_in = datetime.now(timezone.utc).date()
    check_out = check_in + timedelta(days=2)
    defaults = dict(
        booking_reference=f"BOOK-{uuid.uuid4().hex[:8].upper()}",
        idempotency_key=f"idemp-{uuid.uuid4().hex}",
        property_id=1,
        room_type_id=1,
        host_user_id=1,
        guest_user_id=1,
        booked_by_user_id=1,
        check_in=check_in,
        check_out=check_out,
        num_nights=(check_out - check_in).days,
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
        booking_type="self",
        payment_timing="pay_now",
        payment_guaranteed=True,
        guarantee_type="payment_confirmed",
    )
    defaults.update(overrides)
    return AccommodationBooking(**defaults)


# Stage 5-2 lifecycle tests ----------------------------------------------------

def test_invalid_guest_registration_raises_invalid_event_registration(
    event, actor, registration, booking, monkeypatch
):
    """A registration_ref that does not belong to this event must be rejected."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, "REG-DOES-NOT-EXIST", booking.booking_reference
        )
    assert exc.value.code == "INVALID_EVENT_REGISTRATION"


def test_unknown_booking_reference_raises_accommodation_booking_not_found(
    event, actor, registration, monkeypatch
):
    """An unknown booking reference must be rejected."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, "BOOK-DOES-NOT-EXIST"
        )
    assert exc.value.code == "ACCOMMODATION_BOOKING_NOT_FOUND"


def test_missing_booking_reference_raises_invalid_event_resource(
    event, actor, registration, monkeypatch
):
    """An empty booking reference must be rejected."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, "   "
        )
    assert exc.value.code == "INVALID_EVENT_RESOURCE"


def test_booking_in_non_assignable_status_rejected(
    event, actor, registration, booking, monkeypatch
):
    """A booking not in {held, confirmed, pending, pending_approval} must be rejected."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    booking.status = "cancelled"
    db.session.commit()
    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, booking.booking_reference
        )
    assert exc.value.code == "ACCOMMODATION_BOOKING_UNAVAILABLE"


def test_inactive_room_type_rejected(
    event, actor, registration, booking, room_type, monkeypatch
):
    """An inactive room type must be rejected by the assignment validation."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    room_type.is_active = False
    db.session.commit()
    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, booking.booking_reference
        )
    assert exc.value.code == "ACCOMMODATION_ROOM_UNAVAILABLE"


def test_room_capacity_below_booked_guests_rejected(
    event, actor, registration, booking, room_type, monkeypatch
):
    """Assignment must reject when the room type cannot host the booked guests."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    booking.num_guests = 3
    room_type.max_guests = 2
    db.session.commit()
    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, booking.booking_reference
        )
    assert exc.value.code == "ACCOMMODATION_CAPACITY_EXCEEDED"


def test_cross_context_booking_rejected_when_not_owner(
    event, other_event, actor, other_actor, registration, property_, room_type, monkeypatch
):
    """A booking whose context_id belongs to another event must be rejected.

    This is the context-linked cross-event case: booking.event_id is set but
    points to a different event, so neither event-linked nor owner-linked.
    """
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    foreign_booking = _make_booking(
        event_id=other_event.id,
        property_id=property_.id,
        room_type_id=room_type.id,
        host_user_id=other_actor.id,
        guest_user_id=other_actor.id,
        booked_by_user_id=other_actor.id,
        context_id=str(other_event.id),
    )
    db.session.add(foreign_booking)
    db.session.commit()

    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, foreign_booking.booking_reference
        )
    assert exc.value.code == "BOOKING_EVENT_MISMATCH"


def test_provider_allocator_veto_rejected(
    event, actor, registration, booking, monkeypatch
):
    """The allocator/provider veto must fail the assignment closed."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )

    def veto_capability(*args, **kwargs):
        return False

    booking.can_assign_guest = veto_capability
    db.session.commit()

    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, booking.booking_reference
        )
    assert exc.value.code == "ALLOCATION_REJECTED"


def test_owner_linked_cross_context_booking_remains_assignable(
    event, other_event, actor, registration, property_, room_type, monkeypatch
):
    """An organizer's own booked accommodation stays assignable even when the
    booking is tagged with a different event's context (owner-linked path)."""
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )
    own_booking = _make_booking(
        event_id=other_event.id,
        property_id=property_.id,
        room_type_id=room_type.id,
        host_user_id=actor.id,
        guest_user_id=actor.id,
        booked_by_user_id=actor.id,
        context_id=str(other_event.id),
    )
    db.session.add(own_booking)
    db.session.commit()

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, own_booking.booking_reference
    )
    assert assignment.accommodation_booking_id == own_booking.id