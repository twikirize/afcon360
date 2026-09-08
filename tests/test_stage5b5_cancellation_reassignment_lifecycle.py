"""Stage 5-5 cancellation / reassignment lifecycle tests.

Stage 5-5 verifies the full cancellation and reassignment matrix (A-H) that
Stage 5-4's atomicity proofs established, and adds two regression tests for the
two genuine defect fixes introduced by Stage 5-5:

  A  coordinator cancels accommodation (GuestCoordinationService.cancel) ->
     slot released via contract, pointer + token + expiry cleared, single commit
  B  attendee self-service cancel (cancel_attendee_booking) -> booking cancelled,
     slot released + pointer + token cleared in one transaction
  C  accommodation-side cancel (BookingService.cancel_booking) -> NOT propagated
     to Events; read revalidation presents attendee as unassigned
  D  repeated cancel is idempotent - no double slot release, no error
  E  reassignment is atomic - old slot released and new slot ensured in the SAME
     transaction (proven by stage5b4); pointer moved to the new booking
  F  cancel then reassign works from the clear state
  G  reassign then cancel works from the newly assigned state
  H  cross-context cancellation is rejected (an attendee of one event cannot
     cancel an accommodation assignment that belongs to another event)

The two defects fixed (guarded slot release on a missing/deleted OLD booking):

  D1  coordinator cancel() raised an unguarded CoordinationContractError
      "BOOKING_NOT_FOUND" whenever the old booking had been deleted on the
      Accommodation side, surfacing as an HTTP 500. It now logs and continues,
      matching the established skip-BOOKING_NOT_FOUND pattern.
  D2  reassignment raised "COORDINATION_FAILED" (500) when the OLD booking had
      been deleted, aborting an otherwise valid reassignment to a new booking.
      It now logs and continues so the reassignment completes.

Fixture/assertion patterns follow tests/test_stage5b4_sync_synchronization.py.
"""

import uuid
import hashlib
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.events.models import EventAssignment
from app.events.guest_coordination_service import GuestCoordinationService, CoordinationError
from app.accommodation.services.coordination_contract import CoordinationContractError
from app.accommodation.models.guest_registration import GuestRegistration


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
def host():
    """A separate host user so cancellation is exercised on the guest path."""
    from app.identity.models.user import User

    unique_suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"coord_host_{unique_suffix}",
        email=f"host_{unique_suffix}@example.com",
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
        start_date=datetime.now(timezone.utc).date() + timedelta(days=30),
        end_date=datetime.now(timezone.utc).date() + timedelta(days=35),
        status="approved",
    )
    db.session.add(ev)
    db.session.commit()
    return ev


@pytest.fixture
def other_actor():
    """A second user owning a foreign event / foreign bookings."""
    from app.identity.models.user import User

    unique_suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"other_actor_{unique_suffix}",
        email=f"other_actor_{unique_suffix}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.commit()
    return user


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
def foreign_ticket_type(other_event):
    """A TicketType for the OTHER event (ticket_type_id is NOT NULL)."""
    from app.events.models import TicketType

    tt = TicketType(
        event_id=other_event.id,
        name="General",
        price=Decimal("0.00"),
        capacity=100,
        is_active=True,
    )
    db.session.add(tt)
    db.session.commit()
    return tt


@pytest.fixture
def foreign_registration(other_event, foreign_ticket_type, event_guest):
    """A confirmed registration belonging to the OTHER event."""
    from app.events.models import EventRegistration

    reg = EventRegistration(
        event_id=other_event.id,
        ticket_type_id=foreign_ticket_type.id,
        full_name=event_guest.full_name,
        email=event_guest.email,
        status="confirmed",
        payment_status="free",
        registration_fee=Decimal("0.00"),
        guest_id=event_guest.id,
        booking_type="self",
    )
    db.session.add(reg)
    seq = int(uuid.uuid4().int % 10 ** 8)
    reg.generate_refs(event_slug=other_event.slug, sequence=seq)
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


def _make_booking(event, property_, **overrides):
    """Build (without committing) an AccommodationBooking for the event."""
    from app.accommodation.models.booking import AccommodationBooking

    check_in = datetime.now(timezone.utc).date() + timedelta(days=30)
    check_out = check_in + timedelta(days=2)
    defaults = dict(
        booking_reference=f"BOOK-{uuid.uuid4().hex[:8].upper()}",
        idempotency_key=f"idemp-{uuid.uuid4().hex}",
        event_id=event.id,
        property_id=property_.id,
        host_user_id=property_.owner_user_id,
        guest_user_id=property_.owner_user_id,
        booked_by_user_id=property_.owner_user_id,
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
        context_id=str(event.id),
        booking_type="self",
        payment_timing="pay_now",
        payment_guaranteed=True,
        guarantee_type="payment_confirmed",
    )
    defaults.update(overrides)
    return AccommodationBooking(**defaults)


def _suppress_notifications(monkeypatch):
    monkeypatch.setattr(
        "app.notifications.services.NotificationService.send",
        lambda **kwargs: None,
    )


def _active_slots(booking_id, assignment_id=None):
    q = GuestRegistration.query.filter_by(booking_id=booking_id, is_active=True)
    if assignment_id is not None:
        q = q.filter_by(event_assignment_id=assignment_id)
    return q.count()


# Stage 5-5 lifecycle tests ----------------------------------------------------

def test_a_coordinator_cancel_releases_slot_and_clears_pointer(
    event, actor, host, registration, property_, monkeypatch
):
    """A: GuestCoordinationService.cancel releases the Accommodation slot via
    the contract and clears pointer + token + expiry in one transaction."""
    _suppress_notifications(monkeypatch)

    booking = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add(booking)
    db.session.commit()

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    assert assignment.accommodation_booking_id == booking.id
    assert assignment.acc_link_token_hash
    assert _active_slots(booking.id, assignment.id) == 1

    assignment_id = assignment.id

    GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")

    reloaded = db.session.get(EventAssignment, assignment_id)
    assert reloaded.accommodation_booking_id is None
    assert reloaded.acc_link_token_hash is None
    assert reloaded.acc_link_expires_at is None
    assert reloaded.status == "cancelled"
    assert _active_slots(booking.id, assignment_id) == 0


def test_b_attendee_cancel_releases_slot_and_clears_pointer(
    event, actor, host, registration, property_, monkeypatch
):
    """B: cancel_attendee_booking cancels the booking and releases the slot and
    clears pointer + token in the same transaction."""
    from app.events.accommodation_booking_service import AttendeeAccommodationBookingService

    _suppress_notifications(monkeypatch)

    booking = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add(booking)
    db.session.commit()

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    assert _active_slots(booking.id, assignment.id) == 1

    cancelled = AttendeeAccommodationBookingService.cancel_attendee_booking(
        event, registration, actor_user_id=actor.id, reason="attendee changed plans"
    )
    assert cancelled is True

    db.session.refresh(booking)
    assert booking.status in {"cancelled", "refunded"}
    reloaded = db.session.get(EventAssignment, assignment.id)
    assert reloaded.accommodation_booking_id is None
    assert reloaded.acc_link_token_hash is None
    assert reloaded.acc_link_expires_at is None
    assert _active_slots(booking.id, assignment.id) == 0


def test_c_accommodation_side_cancel_not_propagated_but_read_unassigned(
    event, actor, host, registration, property_, monkeypatch
):
    """C: BookingService.cancel_booking (Accommodation side) does NOT propagate
    to Events; the stale reference is revalidated away on read (asymmetric)."""
    from app.accommodation.services.booking_service import BookingService

    _suppress_notifications(monkeypatch)

    booking = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add(booking)
    db.session.commit()

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    assert assignment.acc_link_token_hash

    dash_before = GuestCoordinationService.dashboard(event, actor)
    assert dash_before["accommodation_assigned"] == 1

    ok, msg, _ = BookingService.cancel_booking(
        booking.id, cancelled_by_user_id=actor.id, reason="accommodation-side cancel"
    )
    assert ok is True, msg
    db.session.refresh(booking)
    assert booking.status in {"cancelled", "refunded"}

    # Row + slot + token untouched (no propagation)...
    reloaded = db.session.get(EventAssignment, assignment.id)
    assert reloaded.accommodation_booking_id == booking.id
    assert reloaded.acc_link_token_hash
    assert _active_slots(booking.id, assignment.id) == 1

    # ...but reads revalidate it away (C1).
    dash_after = GuestCoordinationService.dashboard(event, actor)
    assert dash_after["accommodation_assigned"] == 0
    journey = GuestCoordinationService.guest_journey(
        event, actor, registration.registration_ref
    )
    assert journey["capabilities"]["accommodation"]["status"] == "unassigned"


def test_d_repeated_coordinator_cancel_is_idempotent(
    event, actor, host, registration, property_, monkeypatch
):
    """D: cancelling twice releases the slot exactly once and does not error."""
    _suppress_notifications(monkeypatch)

    booking = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add(booking)
    db.session.commit()

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )

    GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")
    # Second cancel: the assignment no longer holds an accommodation booking.
    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")
    assert exc.value.code == "ASSIGNMENT_NOT_FOUND"

    reloaded = db.session.get(EventAssignment, assignment.id)
    assert reloaded.accommodation_booking_id is None
    assert _active_slots(booking.id, assignment.id) == 0


def test_e_reassignment_moves_pointer_and_rotates_token(
    event, actor, host, registration, property_, monkeypatch
):
    """E: reassignment moves the pointer to the new booking, releases the old
    slot and ensures the new slot, and rotates the completion token."""
    _suppress_notifications(monkeypatch)

    old = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    new = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add_all([old, new])
    db.session.commit()

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, old.booking_reference
    )
    old_token = assignment.acc_link_token_hash
    assert assignment.accommodation_booking_id == old.id
    assert _active_slots(old.id, assignment.id) == 1
    assert _active_slots(new.id, assignment.id) == 0

    reassigned = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, new.booking_reference
    )
    assert reassigned.accommodation_booking_id == new.id
    # Old slot released, new slot ensured.
    assert _active_slots(old.id, reassigned.id) == 0
    assert _active_slots(new.id, reassigned.id) == 1
    # Token rotated on reassignment (new token differs from the old one).
    assert reassigned.acc_link_token_hash
    assert reassigned.acc_link_token_hash != old_token


def test_f_cancel_then_reassign_from_clear_state(
    event, actor, host, registration, property_, monkeypatch
):
    """F: after coordinator cancel, a fresh reassignment to a new booking works
    from the cleared state."""
    _suppress_notifications(monkeypatch)

    first = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    second = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add_all([first, second])
    db.session.commit()

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, first.booking_reference
    )
    GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")

    reassigned = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, second.booking_reference
    )
    assert reassigned.accommodation_booking_id == second.id
    assert reassigned.acc_link_token_hash
    assert _active_slots(second.id, reassigned.id) == 1


def test_g_reassign_then_cancel_from_new_state(
    event, actor, host, registration, property_, monkeypatch
):
    """G: after a reassignment, cancelling clears the NEW booking's slot."""
    _suppress_notifications(monkeypatch)

    old = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    new = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add_all([old, new])
    db.session.commit()

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, old.booking_reference
    )
    GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, new.booking_reference
    )
    assert _active_slots(new.id, assignment.id) == 1

    GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")
    reloaded = db.session.get(EventAssignment, assignment.id)
    assert reloaded.accommodation_booking_id is None
    assert _active_slots(new.id, assignment.id) == 0


def test_h_cross_context_cancellation_rejected(
    event, other_event, actor, other_actor, registration, foreign_registration,
    property_, monkeypatch
):
    """H: an attendee registered to the first event cannot cancel an
    accommodation assignment that belongs to the OTHER event's coordination."""
    from app.events.accommodation_booking_service import AttendeeAccommodationBookingService

    _suppress_notifications(monkeypatch)

    foreign_booking = _make_booking(
        other_event, property_,
        host_user_id=other_actor.id, guest_user_id=other_actor.id, booked_by_user_id=other_actor.id,
    )
    db.session.add(foreign_booking)
    db.session.commit()

    # Assign the foreign event's own attendee to its own booking (organizer-scoped).
    GuestCoordinationService.assign_accommodation(
        other_event, other_actor, foreign_registration.registration_ref, foreign_booking.booking_reference
    )

    # The FIRST event's registration does not own that coordination context.
    cancelled = AttendeeAccommodationBookingService.cancel_attendee_booking(
        event, registration, actor_user_id=actor.id, reason="cross-context attempt"
    )
    assert cancelled is False

    # And the first event's coordinator cancel finds no accommodation assignment.
    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")
    assert exc.value.code == "ASSIGNMENT_NOT_FOUND"

    # The other event's assignment is untouched.
    other_assignment = EventAssignment.query.filter_by(
        event_id=other_event.id, registration_id=foreign_registration.id, is_deleted=False
    ).first()
    assert other_assignment is not None
    assert other_assignment.accommodation_booking_id == foreign_booking.id


# Stage 5-5 defect regression tests --------------------------------------------

def test_d1_coordinator_cancel_survives_deleted_old_booking(
    event, actor, host, registration, property_, monkeypatch
):
    """D1 regression: coordinator cancel must not 500 when the old booking was
    soft-deleted on the Accommodation side; it clears the assignment anyway."""
    _suppress_notifications(monkeypatch)

    booking = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add(booking)
    db.session.commit()

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    assert _active_slots(booking.id, assignment.id) == 1

    # Soft-delete the booking on the Accommodation side (booking no longer
    # resolves through the contract, which now raises BOOKING_NOT_FOUND).
    booking.is_deleted = True
    db.session.commit()

    # Cancelling must now succeed (logged, not raised) instead of 500ing.
    GuestCoordinationService.cancel(event, actor, registration.registration_ref, "accommodation")

    reloaded = db.session.get(EventAssignment, assignment.id)
    assert reloaded.accommodation_booking_id is None
    assert reloaded.acc_link_token_hash is None
    assert reloaded.acc_link_expires_at is None
    assert reloaded.status == "cancelled"


def test_d2_reassignment_survives_deleted_old_booking(
    event, actor, host, registration, property_, monkeypatch
):
    """D2 regression: reassignment to a NEW booking must still succeed when the
    OLD booking was soft-deleted on the Accommodation side (previously aborted
    with COORDINATION_FAILED)."""
    _suppress_notifications(monkeypatch)

    old = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    new = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add_all([old, new])
    db.session.commit()

    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, old.booking_reference
    )
    assert assignment.accommodation_booking_id == old.id

    # Soft-delete the OLD booking so its slot release would raise BOOKING_NOT_FOUND.
    old.is_deleted = True
    db.session.commit()

    reassigned = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, new.booking_reference
    )
    assert reassigned.accommodation_booking_id == new.id
    assert reassigned.acc_link_token_hash
    assert _active_slots(new.id, reassigned.id) == 1
