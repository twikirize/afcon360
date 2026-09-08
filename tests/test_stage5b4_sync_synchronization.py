"""Stage 5-4 synchronization proofs + regression tests: EventAssignment <-> AccommodationBooking.

Two synchronization properties that must keep holding:

  1. reassignment is atomic - the old guest slot is released and the new slot is
     ensured inside the SAME transaction as the assignment pointer change, so a
     failure after the release leaves no committed intermediate window
  2. a booking cancelled on the Accommodation side (BookingService.cancel_booking)
     is NOT auto-propagated to the Events module - the EventAssignment keeps
     pointing at the cancelled booking, the guest slot stays active, and the
     completion token stays live (the asymmetric architecture, classification C)

The asymmetric architecture is made safe by the Stage 5-4 correction (C1-C4):

  C1 (read revalidation) - dashboard rows/count, guest_journey, attendee-list
    and statistics treat non-assignable bookings (cancelled/refunded/deleted)
    as "not currently assigned" and never present them as active.
  C2 (fail-closed completion) - /accommodation/assignment/<token> rejects an
    assignment whose booking is missing/deleted/non-assignable.
  C3 (retire on detection) - retire_invalid_accommodation_assignment() releases
    the Accommodation guest slot via the contract and clears the pointer + token
    idempotently, in one transaction.
  C4 (attendee self-service cancel) - cancel_attendee_booking() releases the
    slot and clears pointer + token in the same transaction.

Fixture/assertion patterns follow tests/test_stage5b3_handoff_architecture.py and
tests/test_stage5b2_assignment_lifecycle.py.
"""

import uuid
import hashlib
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.events.models import EventAssignment
from app.events.guest_coordination_service import GuestCoordinationService, CoordinationError
from app.events.accommodation_bridge import issue_accommodation_for_assignment
from app.events.accommodation_booking_service import AttendeeAccommodationBookingService
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


# Stage 5-4 grounded tests -----------------------------------------------------

def test_reassignment_is_atomic_no_partial_committed_window(
    event, actor, registration, property_, monkeypatch
):
    """Reassignment (old slot release + new slot ensure) shares ONE transaction.

    If the new-slot creation fails after the old slot was released, the whole
    transition rolls back: the assignment still points at the OLD booking, the
    OLD slot is still active, and the NEW booking has no slot. There is no
    committed intermediate window where the attendee appears unassigned.
    """
    _suppress_notifications(monkeypatch)

    old = _make_booking(event, property_)
    new = _make_booking(event, property_)
    db.session.add_all([old, new])
    db.session.commit()

    assigned = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, old.booking_reference
    )
    assignment_id = assigned.id
    reloaded = db.session.get(EventAssignment, assignment_id)
    assert reloaded.accommodation_booking_id == old.id
    assert GuestRegistration.query.filter_by(
        booking_id=old.id, is_active=True
    ).count() == 1
    assert GuestRegistration.query.filter_by(
        booking_id=new.id, is_active=True
    ).count() == 0

    # Simulate new-booking capacity exhaustion AFTER the old slot was released.
    def fail_new_slot(*args, **kwargs):
        raise CoordinationContractError(
            "BOOKING_CAPACITY_EXCEEDED", "Capacity exhausted during discovery proof"
        )

    monkeypatch.setattr(
        "app.events.accommodation_bridge.issue_accommodation_for_assignment", fail_new_slot
    )

    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, new.booking_reference
        )
    assert exc.value.code == "ACCOMMODATION_BOOKING_FULL"

    after = db.session.get(EventAssignment, assignment_id)
    assert after.accommodation_booking_id == old.id
    assert GuestRegistration.query.filter_by(
        booking_id=old.id, is_active=True
    ).count() == 1
    assert GuestRegistration.query.filter_by(
        booking_id=new.id, is_active=True
    ).count() == 0


def test_booking_cancel_after_assignment_is_not_propagated_to_event(
    event, actor, host, registration, property_, monkeypatch
):
    """Accommodation-side cancellation does NOT synchronize back to the Events
    module. This is the asymmetric gap (classification C): after
    BookingService.cancel_booking(), the EventAssignment still references the
    cancelled booking, the guest slot stays active, and the completion token
    stays live."""
    _suppress_notifications(monkeypatch)

    booking = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add(booking)
    db.session.commit()

    assignment = EventAssignment(
        event_id=event.id,
        registration_id=registration.id,
        attendee_id=registration.user_id,
        accommodation_booking_id=booking.id,
        status="active",
        assigned_by_id=actor.id,
    )
    db.session.add(assignment)
    db.session.flush()
    issue_accommodation_for_assignment(event, registration, booking, assignment)
    db.session.commit()

    assert assignment.accommodation_booking_id == booking.id
    assert assignment.acc_link_token_hash
    slot = GuestRegistration.query.filter_by(
        booking_id=booking.id, event_assignment_id=assignment.id, is_active=True
    ).first()
    assert slot is not None

    from app.accommodation.services.booking_service import BookingService

    ok, msg, refund = BookingService.cancel_booking(
        booking.id, cancelled_by_user_id=actor.id, reason="discovery gap proof"
    )
    assert ok is True, msg
    db.session.refresh(booking)
    # pay_now with a refundable base terminal state is "refunded"; otherwise the
    # state machine leaves the booking "cancelled". Both sit OUTSIDE the assignable
    # set {held, confirmed, pending, pending_approval}.
    assert booking.status in {"cancelled", "refunded"}

    # Accommodation itself now considers the booking non-assignable...
    with pytest.raises(CoordinationError) as exc:
        GuestCoordinationService.assign_accommodation(
            event, actor, registration.registration_ref, booking.booking_reference
        )
    assert exc.value.code == "ACCOMMODATION_BOOKING_UNAVAILABLE"

    # THE GAP: no accommodation->event propagation.
    reloaded = db.session.get(EventAssignment, assignment.id)
    assert reloaded.accommodation_booking_id == booking.id
    assert reloaded.acc_link_token_hash
    slot_after = GuestRegistration.query.filter_by(
        booking_id=booking.id, event_assignment_id=assignment.id, is_active=True
    ).first()
    assert slot_after is not None and slot_after.is_active is True


# --- Stage 5-4 correction regression tests (C1-C4) ----------------------------

def _make_assignment_with_slot(event, actor, registration, booking):
    """Assign a booking to the attendee and set a known completion token."""
    assignment = GuestCoordinationService.assign_accommodation(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    slot = GuestRegistration.query.filter_by(
        booking_id=booking.id, event_assignment_id=assignment.id, is_active=True
    ).first()
    assert slot is not None, "slot must exist after assignment"
    raw = f"completion-token-{uuid.uuid4().hex}"
    assignment.acc_link_token_hash = hashlib.sha256(raw.encode()).hexdigest()
    assignment.acc_link_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    db.session.commit()
    return assignment, slot, raw


def _cancel_booking_side(booking_id, user_id, reason="cancelled on accommodation side"):
    """Cancel a booking through the Accommodation module (no Event sync)."""
    from app.accommodation.services.booking_service import BookingService

    ok, msg, refund = BookingService.cancel_booking(
        booking_id, cancelled_by_user_id=user_id, reason=reason
    )
    assert ok is True, msg
    return refund


def test_c1_cancelled_booking_is_not_presented_as_active_assignment(
    event, actor, host, registration, property_, monkeypatch
):
    """C1 read revalidation: after an Accommodation-side cancel, Event reads
    (dashboard rows/count and guest_journey) treat the attendee as unassigned
    even though the EventAssignment row still points at the booking."""
    _suppress_notifications(monkeypatch)

    booking = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add(booking)
    db.session.commit()

    assignment, slot, _ = _make_assignment_with_slot(event, actor, registration, booking)

    # Reading before cancel: assigned.
    dash_data = GuestCoordinationService.dashboard(event, actor)
    row = dash_data["items"][0]
    assert row["accommodation_assigned"] is True
    assert row["accommodation"] is not None
    assert dash_data["accommodation_assigned"] == 1
    journey = GuestCoordinationService.guest_journey(
        event, actor, registration.registration_ref
    )
    assert journey["capabilities"]["accommodation"]["status"] == "assigned"

    _cancel_booking_side(booking.id, actor.id)
    db.session.refresh(booking)
    assert booking.status in {"cancelled", "refunded"}

    # Reading after cancel: the stale reference is revalidated away (read-only;
    # the assignment row itself must be untouched, matching the asymmetric gap).
    dash_data2 = GuestCoordinationService.dashboard(event, actor)
    row2 = dash_data2["items"][0]
    assert row2["accommodation_assigned"] is False
    assert row2["accommodation"] is None
    assert dash_data2["accommodation_assigned"] == 0
    journey2 = GuestCoordinationService.guest_journey(
        event, actor, registration.registration_ref
    )
    assert journey2["capabilities"]["accommodation"]["status"] == "unassigned"

    reloaded = db.session.get(EventAssignment, assignment.id)
    assert reloaded.accommodation_booking_id == booking.id
    assert reloaded.acc_link_token_hash


def test_c2_completion_route_fails_closed_for_cancelled_booking(
    app, event, actor, host, registration, property_, monkeypatch
):
    """C2 + C3: /accommodation/assignment/<token> fails closed once the booking
    is cancelled and retires the invalid assignment in one transaction."""
    _suppress_notifications(monkeypatch)

    booking = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add(booking)
    db.session.commit()

    assignment, slot, raw = _make_assignment_with_slot(event, actor, registration, booking)
    _cancel_booking_side(booking.id, actor.id)

    # The client request tears the session down, so capture primitive ids first
    # and re-fetch fresh rows afterwards.
    assignment_id = assignment.id
    booking_id = booking.id
    with app.test_client() as client:
        response = client.get(f"/accommodation/assignment/{raw}")
    assert response.status_code == 404

    # The assignment was retired: pointer + token cleared, slot released.
    reloaded = db.session.get(EventAssignment, assignment_id)
    assert reloaded.accommodation_booking_id is None
    assert reloaded.acc_link_token_hash is None
    assert reloaded.acc_link_expires_at is None
    assert GuestRegistration.query.filter_by(
        booking_id=booking_id, event_assignment_id=assignment_id, is_active=True
    ).count() == 0


def test_c3_retire_invalid_assignment_is_idempotent(
    event, actor, host, registration, property_, monkeypatch
):
    """C3: retire_invalid_accommodation_assignment releases the slot and clears
    the pointer + token once, and is safe to call again (returns False)."""
    _suppress_notifications(monkeypatch)

    booking = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add(booking)
    db.session.commit()

    assignment, slot, _ = _make_assignment_with_slot(event, actor, registration, booking)
    _cancel_booking_side(booking.id, actor.id)

    retired = GuestCoordinationService.retire_invalid_accommodation_assignment(
        assignment, reason="cancelled booking regression"
    )
    assert retired is True

    reloaded = db.session.get(EventAssignment, assignment.id)
    assert reloaded.accommodation_booking_id is None
    assert reloaded.acc_link_token_hash is None
    assert reloaded.acc_link_expires_at is None
    assert GuestRegistration.query.filter_by(
        booking_id=booking.id, event_assignment_id=assignment.id, is_active=True
    ).count() == 0

    # Idempotent second call.
    again = GuestCoordinationService.retire_invalid_accommodation_assignment(
        db.session.get(EventAssignment, assignment.id), reason="second call"
    )
    assert again is False


def test_c4_attendee_cancel_releases_slot_and_clears_pointer(
    event, actor, host, registration, property_, monkeypatch
):
    """C4: cancel_attendee_booking releases the Accommodation guest slot and
    clears pointer + token in the same transaction; active-slot count drops."""
    _suppress_notifications(monkeypatch)

    booking = _make_booking(
        event, property_, host_user_id=host.id, guest_user_id=actor.id, booked_by_user_id=actor.id
    )
    db.session.add(booking)
    db.session.commit()

    assignment, slot, _ = _make_assignment_with_slot(event, actor, registration, booking)
    assert GuestRegistration.query.filter_by(
        booking_id=booking.id, event_assignment_id=assignment.id, is_active=True
    ).count() == 1

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
    assert GuestRegistration.query.filter_by(
        booking_id=booking.id, event_assignment_id=assignment.id, is_active=True
    ).count() == 0

    # The event now (read-)presents the attendee as unassigned.
    dash_after = GuestCoordinationService.dashboard(event, actor)
    assert dash_after["accommodation_assigned"] == 0