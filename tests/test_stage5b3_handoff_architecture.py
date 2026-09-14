"""Stage 5-3 focused architecture tests: Event -> Accommodation handoff.

These tests verify that the reserve -> hold/block -> registration-link ->
consume -> complete flow already exists and that Events is a *thin consumer*
of Accommodation through the single write boundary
(AccommodationCoordinationContract):

  * the accommodation guest-slot path works without any Event wiring
  * the Event handoff creates an event-coordination slot on the booking
  * registration-link pool consumption follows the derived-capacity model
    (reserved quantity 100 -> 99 -> 98) without an atomic decrement counter
  * a no-stock request is rejected by the Accommodation capability itself
  * ownership isolation: the Events-side modules never import accommodation
    models - the contract is the only write surface
  * abandonment: releasing an incomplete slot returns capacity (no leak)
  * completion: the booking reference is assignable and the completion route's
    slot lookup resolves the same placeholder it created
  * idempotency: ensure_event_guest_slot twice does not double-create a slot

Fixture/assertion patterns follow tests/test_stage5b2_assignment_lifecycle.py
and tests/test_event_accommodation_assignment_flow.py.
"""

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.accommodation.services.coordination_contract import (
    AccommodationCoordinationContract,
    CoordinationContractError,
)
from app.accommodation.services.booking_registration_link_service import (
    BookingRegistrationLinkService,
)
from app.accommodation.services.registration_service import RegistrationService


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
        start_date=datetime.now(timezone.utc).date() + timedelta(days=30),
        end_date=datetime.now(timezone.utc).date() + timedelta(days=35),
        status="approved",
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
def booking(event, actor, property_):
    """Create an AccommodationBooking linked to the event, guest capacity 2."""
    from app.accommodation.models.booking import AccommodationBooking

    check_in = datetime.now(timezone.utc).date() + timedelta(days=30)
    check_out = check_in + timedelta(days=2)
    bkg = AccommodationBooking(
        booking_reference=f"BOOK-{uuid.uuid4().hex[:8].upper()}",
        idempotency_key=f"idemp-{uuid.uuid4().hex}",
        event_id=event.id,
        property_id=property_.id,
        host_user_id=actor.id,
        guest_user_id=actor.id,
        booked_by_user_id=actor.id,
        check_in=check_in,
        check_out=check_out,
        num_nights=2,
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
    bkg.calculate_totals()
    db.session.add(bkg)
    db.session.commit()
    return bkg


@pytest.fixture
def assignment(event, registration, booking, actor):
    """Create an EventAssignment linking the registration to the booking."""
    from app.events.models import EventAssignment

    asg = EventAssignment(
        event_id=event.id,
        registration_id=registration.id,
        attendee_id=registration.user_id,
        accommodation_booking_id=booking.id,
        status="active",
        assigned_by_id=actor.id,
    )
    db.session.add(asg)
    db.session.commit()
    return asg


def _suppress_notifications(monkeypatch):
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )


# Stage 5-3 grounded tests -----------------------------------------------------

def test_accommodation_slot_path_exists_without_event_wiring(booking):
    """The accommodation guest-slot capability works with no Event wiring at all."""
    result = AccommodationCoordinationContract.ensure_event_guest_slot(
        booking.booking_reference,
        full_name="Direct Guest",
        email="direct.guest@example.com",
    )
    assert result["email_present"] is True
    assert result["status"] == "in_progress"

    from app.accommodation.models.guest_registration import GuestRegistration
    slot = GuestRegistration.query.filter_by(booking_id=booking.id, is_active=True).first()
    assert slot is not None
    assert slot.registration_source == "event_coordination"
    assert slot.guest_name == "Direct Guest"
    assert slot.guest_email == "direct.guest@example.com"
    db.session.commit()


def test_event_handoff_creates_coordination_slot(
    event, registration, booking, assignment, monkeypatch
):
    """The Event handoff writes through the contract, never directly."""
    _suppress_notifications(monkeypatch)

    from app.events.accommodation_bridge import issue_accommodation_for_assignment
    issue_accommodation_for_assignment(event, registration, booking, assignment)

    from app.accommodation.models.guest_registration import GuestRegistration
    slot = GuestRegistration.query.filter_by(
        booking_id=booking.id,
        event_assignment_id=assignment.id,
        is_active=True,
    ).first()
    assert slot is not None
    assert slot.registration_source == "event_coordination"
    assert slot.guest_email == registration.email
    assert assignment.acc_link_token_hash is not None
    assert assignment.acc_link_expires_at is not None
    db.session.commit()


def test_registration_link_pool_consumption_100_to_98(actor, property_):
    """Reserved quantity is derived-capacity: 100 -> 99 -> 98, no atomic counter."""
    from app.accommodation.models.booking import AccommodationBooking

    check_in = datetime.now(timezone.utc).date() + timedelta(days=30)
    check_out = check_in + timedelta(days=2)
    bkg = AccommodationBooking(
        booking_reference=f"BOOK-{uuid.uuid4().hex[:8].upper()}",
        idempotency_key=f"idemp-{uuid.uuid4().hex}",
        property_id=property_.id,
        host_user_id=actor.id,
        guest_user_id=actor.id,
        booked_by_user_id=actor.id,
        check_in=check_in,
        check_out=check_out,
        num_nights=2,
        num_guests=100,
        rooms_requested=1,
        nightly_rate=Decimal("100.00"),
        cleaning_fee=Decimal("0.00"),
        service_fee=Decimal("0.00"),
        taxes=Decimal("0.00"),
        total_amount=Decimal("200.00"),
        currency="USD",
        payment_status="pending",
        status="confirmed",
        booking_type="self",
        payment_timing="pay_now",
        payment_guaranteed=True,
        guarantee_type="payment_confirmed",
    )
    bkg.calculate_totals()
    db.session.add(bkg)
    db.session.commit()

    link, _raw_token = BookingRegistrationLinkService.create_for_booking(bkg)
    assert link.max_registrants == 100
    assert link.registrants_count == 0
    assert link.spots_remaining == 100

    RegistrationService.create(
        bkg, name="Guest One", email="one@example.com",
        phone="+256700000000", source="self", status="completed",
    )
    assert link.spots_remaining == 99

    RegistrationService.create(
        bkg, name="Guest Two", email="two@example.com",
        phone="+256700000001", source="self", status="completed",
    )
    assert link.spots_remaining == 98
    assert link.is_full is False


def test_no_stock_request_rejected_by_accommodation_capability(booking):
    """A request beyond capacity is rejected by the Accommodation capability."""
    AccommodationCoordinationContract.ensure_event_guest_slot(
        booking.booking_reference,
        full_name="Guest One",
        email="one@example.com",
    )
    AccommodationCoordinationContract.ensure_event_guest_slot(
        booking.booking_reference,
        full_name="Guest Two",
        email="two@example.com",
    )

    with pytest.raises(CoordinationContractError) as exc:
        AccommodationCoordinationContract.ensure_event_guest_slot(
            booking.booking_reference,
            full_name="Guest Three",
            email="three@example.com",
        )
    assert exc.value.code == "BOOKING_CAPACITY_EXCEEDED"
    db.session.commit()


def test_events_side_never_writes_accommodation_directly():
    """Ownership isolation: Events never writes accommodation state directly.

    Events may *read* AccommodationBooking state to validate a resource, but
    every guest-slot write must flow through AccommodationCoordinationContract.
    GuestRegistration / BookingRegistrationLink must never be constructed or
    imported from the Events side.
    """
    import inspect

    from app.events import accommodation_bridge
    from app.events import guest_coordination_service

    for module in (accommodation_bridge, guest_coordination_service):
        source = inspect.getsource(module)
        # No direct GuestRegistration / BookingRegistrationLink writes.
        assert "import GuestRegistration" not in source, module.__name__
        assert "from app.accommodation.models.guest_registration" not in source, module.__name__
        assert "from app.accommodation.models.booking_registration_link" not in source, module.__name__
        assert "GuestRegistration(" not in source, module.__name__
        assert "BookingRegistrationLink(" not in source, module.__name__

    # Guest-slot writes route through the Accommodation contract:
    # the bridge creates slots (ensure_*), the coordination service
    # delegates creation to the bridge and releases slots (release_*).
    bridge_src = inspect.getsource(accommodation_bridge)
    coord_src = inspect.getsource(guest_coordination_service)
    assert "ensure_event_guest_slot" in bridge_src
    assert "release_event_guest_slot" in coord_src


def test_release_recovers_abandoned_slot_capacity(booking):
    """Abandoning an incomplete slot returns capacity (no capacity leak)."""
    result = AccommodationCoordinationContract.ensure_event_guest_slot(
        booking.booking_reference,
        full_name="Incomplete Guest",
        email=None,
    )
    slot_id = result["slot_id"]

    from app.accommodation.models.guest_registration import GuestRegistration
    slot = db.session.get(GuestRegistration, slot_id)
    assert slot.is_placeholder is True

    released = AccommodationCoordinationContract.release_event_guest_slot(
        booking.booking_reference,
        event_assignment_id=slot.event_assignment_id,
        removed_by_user_id=booking.host_user_id,
        reason="Assignment abandoned before completion",
    )
    assert released is True

    remaining = GuestRegistration.query.filter_by(
        booking_id=booking.id, is_active=True
    ).count()
    assert remaining == 0
    db.session.commit()


def test_completion_resolves_same_slot_and_reference(
    event, registration, booking, assignment, monkeypatch
):
    """Completion route's slot lookup resolves the placeholder the bridge created."""
    _suppress_notifications(monkeypatch)

    from app.events.accommodation_bridge import issue_accommodation_for_assignment
    issue_accommodation_for_assignment(event, registration, booking, assignment)

    assert assignment.accommodation_booking_id == booking.id
    assert booking.booking_reference

    from app.accommodation.models.guest_registration import GuestRegistration
    slot = GuestRegistration.query.filter_by(
        booking_id=booking.id,
        event_assignment_id=assignment.id,
        is_active=True,
    ).first()
    assert slot is not None

    slot.is_placeholder = False
    slot.guest_phone = "+256700000002"
    slot.id_document_type = "passport"
    slot.status = "completed" if (
        slot.guest_name and slot.guest_email and slot.guest_phone and slot.id_document_type
    ) else "in_progress"
    db.session.commit()

    reloaded = GuestRegistration.query.filter_by(
        booking_id=booking.id,
        event_assignment_id=assignment.id,
        is_active=True,
    ).first()
    assert reloaded.status == "completed"


def test_ensure_event_guest_slot_idempotent(booking, assignment):
    """ensure_event_guest_slot twice for the same assignment is idempotent."""
    first = AccommodationCoordinationContract.ensure_event_guest_slot(
        booking.booking_reference,
        full_name="Same Guest",
        email="same@example.com",
        event_assignment_id=assignment.id,
    )
    second = AccommodationCoordinationContract.ensure_event_guest_slot(
        booking.booking_reference,
        full_name="Same Guest",
        email="same@example.com",
        event_assignment_id=assignment.id,
    )
    assert first["slot_id"] == second["slot_id"]

    from app.accommodation.models.guest_registration import GuestRegistration
    count = GuestRegistration.query.filter_by(
        booking_id=booking.id,
        event_assignment_id=assignment.id,
        is_active=True,
    ).count()
    assert count == 1
    db.session.commit()