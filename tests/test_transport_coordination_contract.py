# tests/test_transport_coordination_contract.py
"""Transport Coordination Contract (Stage 5T-2) test matrix.

Covers:
  T1 - self-book passenger reservation (passenger == booker)
  T2 - book-for-another passenger reservation (booker != passenger)
  T3 - multi-passenger / capacity enforcement (add_passenger fills the seat
       target, then the contract rejects over-capacity reservations)
  T4 - validate_booking_for_assignment accepts an eligible booking and
       rejects an unknown reference
  T5 - transport-domain eligibility is Transport-owned: non-assignable status,
       unapproved/unverified driver, inactive vehicle, over-capacity vehicle
  T6 - reservation idempotency (same event assignment -> same passenger)
  T7 - atomic reassignment (same event assignment onto a new booking retires
       the old reservation in the same transaction)
  T8 - event-scope guard (booking tagged to another event is rejected)
  T9 - fail-closed reads + retire_invalid_transport_assignment
  T10 - cancel releases the passenger reservation; no double release
  T11 - legacy write rerouted (Booking.event_id set via the contract tag)
  T12 - Events owns event scope: owner-linked booking assigns, unrelated
       booking is rejected with BOOKING_EVENT_MISMATCH
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.events.guest_coordination_service import GuestCoordinationService, CoordinationError
from app.extensions import db
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    PassengerStatus,
    ProviderType,
    ServiceType,
    TransportPassenger,
    VerificationTier,
    Vehicle,
)
from app.transport.services.coordination_contract import (
    TransportCoordinationContract,
    TransportCoordinationContractError,
)
from app.transport.services.passenger_service import get_passenger_service

pytestmark = pytest.mark.usefixtures("db_session")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def actor():
    """Organizer / coordinator with event-owner permission."""
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
def other_user():
    """A second user (unrelated booker / passenger)."""
    from app.identity.models.user import User

    unique_suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"coord_other_{unique_suffix}",
        email=f"other_{unique_suffix}@example.com",
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
    """An Event owned by the actor (owner permission passes coordination)."""
    from app.events.models import Event

    ev = Event(
        public_id=str(uuid.uuid4()),
        event_ref=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        slug=f"test-event-{uuid.uuid4().hex[:8]}",
        name="Test Event",
        organizer_id=actor.id,
        city="Test City",
        country="UG",
        description="Test event description",
        category="general",
        max_capacity=100,
        registration_fee=0,
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
    from app.events.models import TicketType

    tt = TicketType(
        event_id=event.id,
        name="General",
        price=0,
        capacity=100,
        is_active=True,
    )
    db.session.add(tt)
    db.session.commit()
    return tt


@pytest.fixture
def event_guest():
    from app.events.models import EventGuest

    guest = EventGuest(
        full_name="John Doe",
        email=f"john.doe_{uuid.uuid4().hex[:8]}@example.com",
    )
    db.session.add(guest)
    db.session.commit()
    return guest


@pytest.fixture
def registration(event, ticket_type, event_guest):
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
        registration_fee=0,
        guest_id=event_guest.id,
        booking_type="self",
    )
    db.session.add(reg)
    seq = int(uuid.uuid4().int % 10 ** 8)
    reg.generate_refs(event_slug=event.slug, sequence=seq)
    db.session.commit()
    return reg


@pytest.fixture
def driver(actor):
    """A fully eligible driver record."""
    from app.transport.models import DriverProfile

    d = DriverProfile(
        user_id=actor.id,
        driver_code=f"DRV-{uuid.uuid4().hex[:6].upper()}",
        verification_tier=VerificationTier.PLATFORM_VERIFIED,
        compliance_status=ComplianceStatus.APPROVED,
        is_online=True,
        is_available=True,
        max_passenger_capacity=4,
    )
    db.session.add(d)
    db.session.commit()
    return d


@pytest.fixture
def vehicle():
    """An active, available vehicle."""
    v = Vehicle(
        owner_type="driver",
        owner_id=1,
        license_plate=f"UG{uuid.uuid4().hex[:8].upper()}",
        make="Test",
        model="Model",
        year=2023,
        vehicle_type="Sedan",
        vehicle_class="comfort",
        passenger_capacity=4,
        current_location={"latitude": 1.2, "longitude": 3.4},
        status="active",
        is_available=True,
    )
    db.session.add(v)
    db.session.commit()
    return v


def _make_booking(actor, driver, vehicle, **overrides):
    """Create a confirmed, driver/vehicle-assigned transport booking."""
    b = Booking(
        user_id=actor.id,
        provider_type=ProviderType.INDIVIDUAL_DRIVER,
        service_type=ServiceType.ON_DEMAND,
        pickup_location={"latitude": 1.2, "longitude": 3.4},
        dropoff_location={"latitude": 5.6, "longitude": 7.8},
        pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
        passenger_count=4,
        base_price=100.00,
        currency="USD",
        status=BookingStatus.CONFIRMED,
        booking_reference=f"TB{uuid.uuid4().hex[:10].upper()}",
        assigned_driver_id=driver.id,
        assigned_vehicle_id=vehicle.id,
    )
    for k, v in overrides.items():
        setattr(b, k, v)
    db.session.add(b)
    db.session.commit()
    return b


@pytest.fixture
def booking(actor, driver, vehicle):
    return _make_booking(actor, driver, vehicle)


@pytest.fixture
def second_booking(actor, driver, vehicle):
    return _make_booking(actor, driver, vehicle)


# ---------------------------------------------------------------------------
# T1 - self-book reservation (passenger == booker)
# ---------------------------------------------------------------------------

def test_t1_self_book_contract_reservation(actor, booking, event):
    """A booker who is the passenger gets a CONFIRMED passenger reservation."""
    from app.events.models import EventAssignment

    assignment = EventAssignment(event_id=event.id, registration_id=None, attendee_id=actor.id)
    db.session.add(assignment)
    db.session.flush()

    result = TransportCoordinationContract.ensure_passenger_reservation(
        booking.booking_reference,
        event_assignment_id=assignment.id,
        event_id=event.id,
        full_name=actor.username,
        email=actor.email,
        phone=None,
        user_id=actor.id,
        reason="assignment",
    )
    db.session.commit()

    passenger = db.session.get(TransportPassenger, result["passenger_id"])
    assert passenger is not None
    assert passenger.user_id == actor.id
    assert passenger.status == PassengerStatus.CONFIRMED
    assert passenger.event_assignment_id == assignment.id
    assert result["passenger_public_id"] == passenger.public_id
    # Transport owns the booking -> event tag (no Events-side write).
    assert booking.event_id == event.id


# ---------------------------------------------------------------------------
# T2 - book-for-another reservation (booker != passenger)
# ---------------------------------------------------------------------------

def test_t2_book_for_another_preserves_separate_identities(
    actor, other_user, booking, event
):
    """Booking.user_id (booker) and TransportPassenger.user_id (passenger) differ."""
    from app.events.models import EventAssignment

    assignment = EventAssignment(event_id=event.id, registration_id=None, attendee_id=other_user.id)
    db.session.add(assignment)
    db.session.flush()

    result = TransportCoordinationContract.ensure_passenger_reservation(
        booking.booking_reference,
        event_assignment_id=assignment.id,
        event_id=event.id,
        full_name=other_user.username,
        email=other_user.email,
        phone=None,
        user_id=other_user.id,
        reason="assignment",
    )
    db.session.commit()

    passenger = db.session.get(TransportPassenger, result["passenger_id"])
    assert booking.user_id == actor.id  # booker
    assert passenger.user_id == other_user.id  # passenger
    assert booking.user_id != passenger.user_id
    assert passenger.status == PassengerStatus.CONFIRMED


# ---------------------------------------------------------------------------
# T3 - capacity enforcement (Transport-owned, authoritative)
# ---------------------------------------------------------------------------

def test_t3_capacity_rejects_when_add_passenger_flow_fills_booking(
    actor, booking, event
):
    """add_passenger fills the booking's seat target; the contract then owns
    the authoritative capacity and rejects the event reservation."""
    from app.events.models import EventAssignment

    svc = get_passenger_service()
    booking.passenger_count = 1
    db.session.commit()

    # Two passengers already riding on a one-seat booking.
    svc.add_passenger(booking, name="Passenger One", email="one@example.com")
    svc.add_passenger(booking, name="Passenger Two", email="two@example.com")
    db.session.commit()

    assignment = EventAssignment(event_id=event.id, registration_id=None, attendee_id=actor.id)
    db.session.add(assignment)
    db.session.flush()

    # The contract rejects the event reservation: active passengers (2) exceed
    # the booking seat target (1) -> TRANSPORT_BOOKING_FULL.
    with pytest.raises(TransportCoordinationContractError) as excinfo:
        TransportCoordinationContract.ensure_passenger_reservation(
            booking.booking_reference,
            event_assignment_id=assignment.id,
            event_id=event.id,
            full_name="Event Rider",
            email="rider@example.com",
            user_id=actor.id,
            reason="assignment",
        )
        db.session.commit()
    assert excinfo.value.code == "TRANSPORT_BOOKING_FULL"


# ---------------------------------------------------------------------------
# T4 - preflight validation
# ---------------------------------------------------------------------------

def test_t4_validate_accepts_eligible_and_rejects_unknown(booking):
    data = TransportCoordinationContract.validate_booking_for_assignment(
        booking.booking_reference
    )
    assert data["booking_id"] == booking.id
    assert data["status"] == "confirmed"

    with pytest.raises(TransportCoordinationContractError) as excinfo:
        TransportCoordinationContract.validate_booking_for_assignment(
            f"TB-{uuid.uuid4().hex[:10].upper()}"
        )
    assert excinfo.value.code == "TRANSPORT_BOOKING_NOT_FOUND"


# ---------------------------------------------------------------------------
# T5 - transport-owned eligibility (status / driver / vehicle / capacity)
# ---------------------------------------------------------------------------

def test_t5_cancelled_booking_is_not_assignable(actor, driver, vehicle, event):
    b = _make_booking(actor, driver, vehicle, status=BookingStatus.CANCELLED)
    with pytest.raises(TransportCoordinationContractError) as excinfo:
        TransportCoordinationContract.validate_booking_for_assignment(b.booking_reference)
    assert excinfo.value.code == "TRANSPORT_BOOKING_UNAVAILABLE"


def test_t5_unapproved_driver_is_rejected(actor, driver, vehicle):
    driver.verification_tier = VerificationTier.PENDING
    driver.compliance_status = ComplianceStatus.PENDING_REVIEW
    driver.is_online = False
    db.session.commit()
    b = _make_booking(actor, driver, vehicle)
    with pytest.raises(TransportCoordinationContractError) as excinfo:
        TransportCoordinationContract.validate_booking_for_assignment(b.booking_reference)
    assert excinfo.value.code == "DRIVER_UNAVAILABLE"


def test_t5_vehicle_capacity_below_target_is_rejected(actor, driver):
    v = Vehicle(
        owner_type="driver",
        owner_id=1,
        license_plate=f"UG{uuid.uuid4().hex[:8].upper()}",
        make="Test",
        model="Model",
        year=2023,
        vehicle_type="Sedan",
        vehicle_class="comfort",
        passenger_capacity=1,
        current_location={"latitude": 1.2, "longitude": 3.4},
        status="active",
        is_available=True,
    )
    db.session.add(v)
    db.session.commit()
    b = _make_booking(actor, driver, v, passenger_count=3)
    with pytest.raises(TransportCoordinationContractError) as excinfo:
        TransportCoordinationContract.validate_booking_for_assignment(b.booking_reference)
    assert excinfo.value.code == "TRANSPORT_CAPACITY_EXCEEDED"


# ---------------------------------------------------------------------------
# T6 - reservation idempotency
# ---------------------------------------------------------------------------

def test_t6_reservation_is_idempotent_for_same_assignment(actor, booking, event):
    from app.events.models import EventAssignment

    assignment = EventAssignment(event_id=event.id, registration_id=None, attendee_id=actor.id)
    db.session.add(assignment)
    db.session.flush()

    first = TransportCoordinationContract.ensure_passenger_reservation(
        booking.booking_reference,
        event_assignment_id=assignment.id,
        event_id=event.id,
        email=actor.email,
        user_id=actor.id,
        reason="assignment",
    )
    second = TransportCoordinationContract.ensure_passenger_reservation(
        booking.booking_reference,
        event_assignment_id=assignment.id,
        event_id=event.id,
        email=actor.email,
        user_id=actor.id,
        reason="assignment",
    )
    db.session.commit()

    assert second["passenger_id"] == first["passenger_id"]
    active = TransportPassenger.query.filter(
        TransportPassenger.booking_id == booking.id,
        TransportPassenger.status != PassengerStatus.CANCELLED,
    ).all()
    assert len(active) == 1


# ---------------------------------------------------------------------------
# T7 - atomic reassignment onto a new booking
# ---------------------------------------------------------------------------

def test_t7_reservation_reassignment_retires_old_in_same_transaction(
    actor, booking, second_booking, event
):
    from app.events.models import EventAssignment

    assignment = EventAssignment(event_id=event.id, registration_id=None, attendee_id=actor.id)
    db.session.add(assignment)
    db.session.flush()

    first = TransportCoordinationContract.ensure_passenger_reservation(
        booking.booking_reference,
        event_assignment_id=assignment.id,
        event_id=event.id,
        email=actor.email,
        user_id=actor.id,
        reason="assignment",
    )
    second = TransportCoordinationContract.ensure_passenger_reservation(
        second_booking.booking_reference,
        event_assignment_id=assignment.id,
        event_id=event.id,
        email=actor.email,
        user_id=actor.id,
        reason="reassignment",
    )
    db.session.commit()

    old = db.session.get(TransportPassenger, first["passenger_id"])
    new = db.session.get(TransportPassenger, second["passenger_id"])
    assert old.booking_id == booking.id
    assert old.status == PassengerStatus.CANCELLED
    assert old.is_deleted is False
    assert (old.passenger_metadata or {}).get("release_reason") == "reassignment"
    assert new.booking_id == second_booking.id
    assert new.status == PassengerStatus.CONFIRMED
    assert new.event_assignment_id == assignment.id
    assert second["passenger_id"] != first["passenger_id"]


# ---------------------------------------------------------------------------
# T8 - event-scope guard
# ---------------------------------------------------------------------------

def test_t8_booking_tagged_to_other_event_is_rejected(actor, other_user, booking, event):
    from app.events.models import Event, EventAssignment

    other_event = Event(
        public_id=str(uuid.uuid4()),
        event_ref=f"EVT-{uuid.uuid4().hex[:8].upper()}",
        slug=f"test-event-{uuid.uuid4().hex[:8]}",
        name="Other Event",
        organizer_id=other_user.id,
        city="Other City",
        country="UG",
        description="Other event",
        category="general",
        max_capacity=50,
        registration_fee=0,
        currency="USD",
        start_date=datetime.now(timezone.utc).date(),
        end_date=datetime.now(timezone.utc).date() + timedelta(days=1),
        status="pending_approval",
    )
    db.session.add(other_event)
    db.session.commit()
    booking.event_id = other_event.id
    db.session.commit()

    assignment = EventAssignment(event_id=event.id, registration_id=None, attendee_id=actor.id)
    db.session.add(assignment)
    db.session.flush()

    with pytest.raises(TransportCoordinationContractError) as excinfo:
        TransportCoordinationContract.ensure_passenger_reservation(
            booking.booking_reference,
            event_assignment_id=assignment.id,
            event_id=event.id,
            email=actor.email,
            user_id=actor.id,
            reason="assignment",
        )
        db.session.commit()
    assert excinfo.value.code == "TRANSPORT_BOOKING_EVENT_MISMATCH"


# ---------------------------------------------------------------------------
# T9 - fail-closed reads + retire_invalid_transport_assignment
# ---------------------------------------------------------------------------

def test_t9_stale_booking_reads_unassigned_then_retired(
    actor, event, registration, booking, monkeypatch
):
    from app.events.models import EventAssignment

    assignment = GuestCoordinationService.assign_transport(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    assert assignment.transport_booking_id == booking.id
    journey = GuestCoordinationService.guest_journey(event, actor, registration.registration_ref)
    assert journey["capabilities"]["transport"]["status"] == "assigned"

    # Cancel the booking behind the assignment: the read is fail-closed.
    booking.status = BookingStatus.CANCELLED
    db.session.commit()
    journey = GuestCoordinationService.guest_journey(event, actor, registration.registration_ref)
    assert journey["capabilities"]["transport"]["status"] == "unassigned"

    # Event-side sweeper retires the stale pointer through the contract.
    retired = GuestCoordinationService.retire_invalid_transport_assignment(
        assignment, removed_by_user_id=actor.id, reason="test retire"
    )
    db.session.refresh(assignment)
    assert retired is True
    assert assignment.transport_booking_id is None
    active = TransportPassenger.query.filter(
        TransportPassenger.event_assignment_id == assignment.id,
        TransportPassenger.status != PassengerStatus.CANCELLED,
    ).all()
    assert active == []
    # Idempotent: nothing to retire the second time.
    assert GuestCoordinationService.retire_invalid_transport_assignment(
        assignment, removed_by_user_id=actor.id
    ) is False


# ---------------------------------------------------------------------------
# T10 - cancel releases the reservation (no double release)
# ---------------------------------------------------------------------------

def test_t10_cancel_releases_passenger_and_prevents_double_release(
    actor, event, registration, booking
):
    from app.events.models import EventAssignment

    assignment = GuestCoordinationService.assign_transport(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    passenger = TransportPassenger.query.filter(
        TransportPassenger.event_assignment_id == assignment.id,
        TransportPassenger.status != PassengerStatus.CANCELLED,
    ).first()
    assert passenger is not None

    result = GuestCoordinationService.cancel(
        event, actor, registration.registration_ref, "transport"
    )
    assert result.transport_booking_id is None
    db.session.refresh(passenger)
    assert passenger.status == PassengerStatus.CANCELLED
    assert passenger.is_deleted is False
    assert (passenger.passenger_metadata or {}).get("release_reason") == "assignment cancelled"

    active = TransportPassenger.query.filter(
        TransportPassenger.event_assignment_id == assignment.id,
        TransportPassenger.status != PassengerStatus.CANCELLED,
    ).count()
    assert active == 0

    # Second cancel has nothing to release.
    with pytest.raises(CoordinationError) as excinfo:
        GuestCoordinationService.cancel(event, actor, registration.registration_ref, "transport")
    assert excinfo.value.code == "ASSIGNMENT_NOT_FOUND"


# ---------------------------------------------------------------------------
# T11 - legacy write rerouted through the contract tag
# ---------------------------------------------------------------------------

def test_t11_legacy_service_write_tags_booking_via_contract(
    actor, event, registration, booking
):
    from app.events.models import EventAssignment
    from app.events.services import EventService

    # The legacy path looks up participation by user_id.
    registration.user_id = actor.id
    db.session.commit()

    result, error = EventService.assign_service_to_attendee(
        attendee_id=actor.id,
        identifier=event.slug,
        booking_type="transport",
        booking_id=booking.id,
        managed_by=actor.id,
    )
    assert error is None
    assert result is not None
    assert result["transport_booking_id"] == booking.id
    db.session.refresh(booking)
    # The event tag was written by the Transport contract, not Events code.
    assert booking.event_id == event.id
    assignment = EventAssignment.query.filter_by(
        event_id=event.id, transport_booking_id=booking.id
    ).first()
    assert assignment is not None


# ---------------------------------------------------------------------------
# T12 - Events owns event scope (owner-linked assign / mismatch reject)
# ---------------------------------------------------------------------------

def test_t12_owner_linked_booking_assigns_through_service(
    actor, event, registration, booking
):
    assignment = GuestCoordinationService.assign_transport(
        event, actor, registration.registration_ref, booking.booking_reference
    )
    assert assignment.transport_booking_id == booking.id
    db.session.refresh(booking)
    assert booking.event_id == event.id
    passenger = TransportPassenger.query.filter(
        TransportPassenger.event_assignment_id == assignment.id,
        TransportPassenger.status != PassengerStatus.CANCELLED,
    ).first()
    assert passenger is not None
    assert passenger.status == PassengerStatus.CONFIRMED


def test_t12_unrelated_booking_is_rejected(
    actor, other_user, event, registration, driver, vehicle
):
    # Booking belongs to an unrelated booker and is not tagged to the event:
    # Events rejects it before Transport is even consulted.
    foreign = _make_booking(other_user, driver, vehicle)
    with pytest.raises(CoordinationError) as excinfo:
        GuestCoordinationService.assign_transport(
            event, actor, registration.registration_ref, foreign.booking_reference
        )
    assert excinfo.value.code == "BOOKING_EVENT_MISMATCH"