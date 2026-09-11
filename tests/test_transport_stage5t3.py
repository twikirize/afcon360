# tests/test_transport_stage5t3.py
"""Stage 5T-3: Event-side assignment lifecycle matrix.

Extends the Stage 5T-2 contract matrix (tests/test_transport_coordination_contract.py)
by proving the Event side of the transport assignment lifecycle - both through
the Event coordination service and through the real HTTP routes (the UI path).

Coverage map (T5T3-01 .. T5T3-15):

  T5T3-01  attendee -> valid booking assignment        [5T-2 T12] + route (this file)
  T5T3-02  passenger created / reused per assignment   [5T-2 T1/T6]
  T5T3-03  EventAssignment <-> TransportPassenger      [5T-2 T1/T7]
  T5T3-04  self-book (booker == passenger)             [5T-2 T1]
  T5T3-05  book-for-another (booker != passenger)      [5T-2 T2]
  T5T3-06  multiple attendees -> independent seats     [IMPLEMENTED HERE]
  T5T3-07  transport-owned authoritative capacity      [5T-2 T3/T5]
  T5T3-08  capacity failure -> no partial Event wire   [IMPLEMENTED HERE]
  T5T3-09  stale booking fail-closed read + retire     [5T-2 T9]
  T5T3-10  cancellation releases passenger/no double   [5T-2 T10]
  T5T3-11  atomic reassignment via Event service       [5T-2 T7] + T5T3-14 (here)
  T5T3-12  cross-event / unrelated booking rejected    [5T-2 T8/T12]
  T5T3-13  direct Transport without Events still works [IMPLEMENTED HERE]
  T5T3-14  rollback leaves Event + Transport consistent [IMPLEMENTED HERE]
  T5T3-15  existing Event coordination routes (UI)     [IMPLEMENTED HERE]

Ownership contract under test: Transport owns passenger lifecycle and capacity
(TransportCoordinationContract); Events owns the EventAssignment pointer and
the outer transaction. A failed reservation must roll back BOTH sides with no
partial Event-state.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.events.guest_coordination_service import (
    GuestCoordinationService,
    CoordinationError,
)
from app.extensions import db
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    PassengerStatus,
    ProviderType,
    ServiceType,
    TransportPassenger,
    VerificationTier,
    Vehicle,
)
from app.transport.services.passenger_service import get_passenger_service


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
        username=f"stage5t3_actor_{unique_suffix}",
        email=f"stage5t3_actor_{unique_suffix}@example.com",
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
        slug=f"stage5t3-event-{uuid.uuid4().hex[:8]}",
        name="Stage 5T-3 Event",
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


def _make_registration(event, ticket_type, guest):
    """Create a confirmed registration for an existing guest."""
    from app.events.models import EventRegistration

    reg = EventRegistration(
        event_id=event.id,
        ticket_type_id=ticket_type.id,
        full_name=guest.full_name,
        email=guest.email,
        phone=guest.phone,
        nationality=guest.nationality,
        status="confirmed",
        payment_status="free",
        registration_fee=0,
        guest_id=guest.id,
        booking_type="self",
    )
    db.session.add(reg)
    seq = int(uuid.uuid4().int % 10 ** 8)
    reg.generate_refs(event_slug=event.slug, sequence=seq)
    db.session.commit()
    return reg


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
    return _make_registration(event, ticket_type, event_guest)


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


def _active_passengers_for_assignment(assignment_id):
    return TransportPassenger.query.filter(
        TransportPassenger.event_assignment_id == assignment_id,
        TransportPassenger.status != PassengerStatus.CANCELLED,
    ).all()


# ---------------------------------------------------------------------------
# T5T3-06 - multiple attendees get independent seats in one booking
# ---------------------------------------------------------------------------

def test_t5t3_06_multiple_attendees_independent_reservations(
    actor, event, ticket_type, event_guest, driver, vehicle, db_session
):
    """Two attendees assigned to the same booking produce two independent
    CONFIRMED reservations, each correlated to its own EventAssignment."""
    from app.events.models import EventGuest, EventAssignment

    second_guest = EventGuest(
        full_name="Jane Doe",
        email=f"jane.doe_{uuid.uuid4().hex[:8]}@example.com",
    )
    db.session.add(second_guest)
    db.session.commit()

    reg1 = _make_registration(event, ticket_type, event_guest)
    reg2 = _make_registration(event, ticket_type, second_guest)

    booking = _make_booking(actor, driver, vehicle, passenger_count=2)

    a1 = GuestCoordinationService.assign_transport(
        event, actor, reg1.registration_ref, booking.booking_reference
    )
    a2 = GuestCoordinationService.assign_transport(
        event, actor, reg2.registration_ref, booking.booking_reference
    )

    assert a1.id != a2.id
    assert a1.transport_booking_id == booking.id
    assert a2.transport_booking_id == booking.id
    db.session.refresh(booking)
    # Transport contract tagged the booking to the event.
    assert booking.event_id == event.id

    active1 = _active_passengers_for_assignment(a1.id)
    active2 = _active_passengers_for_assignment(a2.id)
    assert len(active1) == 1
    assert len(active2) == 1
    assert active1[0].status == PassengerStatus.CONFIRMED
    assert active2[0].status == PassengerStatus.CONFIRMED
    assert active1[0].id != active2[0].id
    assert active1[0].event_assignment_id == a1.id == active1[0].event_assignment_id
    assert active2[0].event_assignment_id == a2.id
    assert {p.booking_id for p in active1 + active2} == {booking.id}


# ---------------------------------------------------------------------------
# T5T3-08 - capacity failure must not leave partial Event state
# ---------------------------------------------------------------------------

def test_t5t3_08_capacity_failure_no_partial_event_assignment(
    actor, event, ticket_type, event_guest, driver, vehicle, db_session
):
    """An over-capacity booking rejects the event assignment AND rolls back the
    freshly-created EventAssignment - no partial Event-side pointer survives."""
    from app.events.models import EventAssignment

    reg = _make_registration(event, ticket_type, event_guest)

    # Booking declares 1 seat and Transport fills it via PassengerService.
    booking = _make_booking(actor, driver, vehicle, passenger_count=1)
    svc = get_passenger_service()
    svc.add_passenger(booking, name="Rider One", email="rider.one@example.com")
    db.session.commit()

    with pytest.raises(CoordinationError) as excinfo:
        GuestCoordinationService.assign_transport(
            event, event.organizer, reg.registration_ref, booking.booking_reference
        )
    assert excinfo.value.code == "TRANSPORT_BOOKING_FULL"

    # The EventAssignment created during the attempt was rolled back entirely.
    remaining = EventAssignment.query.filter_by(
        event_id=event.id, registration_id=reg.id
    ).first()
    assert remaining is None

    # Transport passenger state is untouched: existing rider remains.
    active = TransportPassenger.query.filter(
        TransportPassenger.booking_id == booking.id,
        TransportPassenger.status != PassengerStatus.CANCELLED,
    ).all()
    assert len(active) == 1
    assert active[0].name == "Rider One"

    # No reservation was ever created for an event that never assigned.
    assert TransportPassenger.query.filter(
        TransportPassenger.event_assignment_id.isnot(None),
        TransportPassenger.booking_id == booking.id,
    ).count() == 0


# ---------------------------------------------------------------------------
# T5T3-13 - direct Transport booking works without any Events involvement
# ---------------------------------------------------------------------------

def test_t5t3_13_direct_transport_without_events(
    actor, booking, db_session
):
    """A Transport booking with no Event still accepts passengers directly -
    booker-as-passenger (LINKED) and an accountless passenger (PENDING)."""
    from app.events.models import EventAssignment

    assert booking.event_id is None

    svc = get_passenger_service()
    self_passenger = svc.add_passenger(
        booking, name=actor.username, email=actor.email, user_id=actor.id
    )
    accountless = svc.add_passenger(
        booking, name="Guest Rider", email="guest.rider@example.com"
    )
    db.session.commit()

    assert self_passenger.status == PassengerStatus.LINKED
    assert self_passenger.user_id == actor.id
    assert accountless.status == PassengerStatus.PENDING
    assert accountless.user_id is None

    # No event coordination state was created.
    assert booking.event_id is None
    assert EventAssignment.query.filter_by(
        transport_booking_id=booking.id, is_deleted=False
    ).first() is None
    assert TransportPassenger.query.filter(
        TransportPassenger.event_assignment_id.isnot(None),
        TransportPassenger.booking_id == booking.id,
    ).count() == 0

    # Both reservations remain active on the booking.
    active = TransportPassenger.query.filter(
        TransportPassenger.booking_id == booking.id,
        TransportPassenger.status != PassengerStatus.CANCELLED,
    ).all()
    assert {p.id for p in active} == {self_passenger.id, accountless.id}


# ---------------------------------------------------------------------------
# T5T3-14 - failed reassignment rolls back BOTH sides consistently
# ---------------------------------------------------------------------------

def test_t5t3_14_reassignment_failure_leaves_prior_state_intact_and_session_usable(
    actor, event, ticket_type, event_guest, driver, vehicle, booking, db_session
):
    """Reassigning an attendee to a full booking fails cleanly: the prior
    assignment (booking A + its CONFIRMED passenger) survives, nothing is
    created on B, and the session remains usable for another assignment."""
    from app.events.models import EventAssignment

    reg = _make_registration(event, ticket_type, event_guest)

    # First assignment: booking A succeeds.
    assignment_a = GuestCoordinationService.assign_transport(
        event, actor, reg.registration_ref, booking.booking_reference
    )
    passenger_a = _active_passengers_for_assignment(assignment_a.id)
    assert len(passenger_a) == 1
    assert passenger_a[0].status == PassengerStatus.CONFIRMED

    # Booking B exists but is full (1 seat, 1 Transport passenger already).
    booking_b = _make_booking(actor, driver, vehicle, passenger_count=1)
    svc = get_passenger_service()
    svc.add_passenger(booking_b, name="B Rider", email="b.rider@example.com")
    db.session.commit()

    with pytest.raises(CoordinationError) as excinfo:
        GuestCoordinationService.assign_transport(
            event, actor, reg.registration_ref, booking_b.booking_reference
        )
    assert excinfo.value.code == "TRANSPORT_BOOKING_FULL"

    # Assignment still points at booking A; A's reservation survives.
    assignment_after = db.session.get(EventAssignment, assignment_a.id)
    assert assignment_after.transport_booking_id == booking.id
    passenger_after = _active_passengers_for_assignment(assignment_a.id)
    assert len(passenger_after) == 1
    assert passenger_after[0].id == passenger_a[0].id
    assert passenger_after[0].status == PassengerStatus.CONFIRMED

    # Nothing was created on the full booking B.
    assert TransportPassenger.query.filter(
        TransportPassenger.booking_id == booking_b.id,
        TransportPassenger.event_assignment_id.isnot(None),
    ).count() == 0

    # The session is fully usable: a third booking assigns successfully and,
    # being a reassignment, atomically retires the old reservation.
    booking_c = _make_booking(actor, driver, vehicle, passenger_count=4)
    assignment_c = GuestCoordinationService.assign_transport(
        event, actor, reg.registration_ref, booking_c.booking_reference
    )
    assert assignment_c.id == assignment_a.id
    assert assignment_c.transport_booking_id == booking_c.id
    db.session.refresh(passenger_a[0])
    assert passenger_a[0].status == PassengerStatus.CANCELLED
    assert passenger_a[0].is_deleted is False
    assert (passenger_a[0].passenger_metadata or {}).get("release_reason") == "assignment"
    active_c = _active_passengers_for_assignment(assignment_c.id)
    assert len(active_c) == 1
    assert active_c[0].booking_id == booking_c.id
    assert active_c[0].status == PassengerStatus.CONFIRMED


# ---------------------------------------------------------------------------
# T5T3-15 - existing Event coordination routes drive the lifecycle (UI path)
# ---------------------------------------------------------------------------

def test_t5t3_15_event_coordination_routes_end_to_end(app, client):
    """The real HTTP routes (attendee-list/event-hub UI path) assign, present
    on the coordination dashboard, and cancel a transport assignment."""
    from app.identity.models.user import User
    from app.events.models import (
        Event,
        EventGuest,
        EventAssignment,
        EventRegistration,
        TicketType,
    )

    with app.app_context():
        actor = User(
            public_id=str(uuid.uuid4()),
            username=f"route_actor_{uuid.uuid4().hex[:8]}",
            email=f"route_actor_{uuid.uuid4().hex[:8]}@example.com",
            is_verified=True,
            is_active=True,
            email_verified=True,
        )
        actor.set_password("Password123!")
        db.session.add(actor)
        db.session.commit()

        ev = Event(
            public_id=str(uuid.uuid4()),
            event_ref=f"EVT-{uuid.uuid4().hex[:8].upper()}",
            slug=f"route-event-{uuid.uuid4().hex[:8]}",
            name="Route Test Event",
            organizer_id=actor.id,
            city="Test City",
            country="UG",
            description="Route test event",
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

        tt = TicketType(
            event_id=ev.id, name="General", price=0, capacity=100, is_active=True
        )
        db.session.add(tt)
        db.session.commit()

        guest = EventGuest(
            full_name="Route Guest",
            email=f"route.guest_{uuid.uuid4().hex[:8]}@example.com",
        )
        db.session.add(guest)
        db.session.commit()

        reg = EventRegistration(
            event_id=ev.id,
            ticket_type_id=tt.id,
            full_name=guest.full_name,
            email=guest.email,
            phone=guest.phone,
            nationality=guest.nationality,
            status="confirmed",
            payment_status="free",
            registration_fee=0,
            guest_id=guest.id,
            booking_type="self",
        )
        db.session.add(reg)
        seq = int(uuid.uuid4().int % 10 ** 8)
        reg.generate_refs(event_slug=ev.slug, sequence=seq)
        db.session.commit()

        driver = DriverProfile(
            user_id=actor.id,
            driver_code=f"DRV-{uuid.uuid4().hex[:6].upper()}",
            verification_tier=VerificationTier.PLATFORM_VERIFIED,
            compliance_status=ComplianceStatus.APPROVED,
            is_online=True,
            is_available=True,
            max_passenger_capacity=4,
        )
        db.session.add(driver)
        db.session.commit()

        veh = Vehicle(
            owner_type="driver",
            owner_id=1,
            license_plate=f"UG{uuid.uuid4().hex[:8].upper()}",
            make="Route",
            model="Model",
            year=2023,
            vehicle_type="Sedan",
            vehicle_class="comfort",
            passenger_capacity=4,
            current_location={"latitude": 1.2, "longitude": 3.4},
            status="active",
            is_available=True,
        )
        db.session.add(veh)
        db.session.commit()

        bok = Booking(
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
            assigned_vehicle_id=veh.id,
        )
        db.session.add(bok)
        db.session.commit()

        actor_public_id = str(actor.public_id)
        event_public_id = str(ev.public_id)
        registration_ref = reg.registration_ref
        booking_ref = bok.booking_reference
        event_id = ev.id
        reg_id = reg.id
        booking_id = bok.id

    with client.session_transaction() as sess:
        sess["_user_id"] = actor_public_id

    base = f"/events/{event_public_id}"

    # Dashboard starts unassigned.
    resp = client.get(f"{base}/coordination")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["transport_assigned"] == 0

    # Assign through the POST route (the UI attendee-list/hub path).
    resp = client.post(
        f"{base}/transport/assign",
        json={"registration_ref": registration_ref, "booking_ref": booking_ref},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["status"] == "active"

    with app.app_context():
        assignment = EventAssignment.query.filter_by(
            event_id=event_id, registration_id=reg_id, is_deleted=False
        ).first()
        assert assignment is not None
        assert assignment.transport_booking_id == booking_id
        passenger = _active_passengers_for_assignment(assignment.id)
        assert len(passenger) == 1
        assert passenger[0].status == PassengerStatus.CONFIRMED
        # Contract tag: booking now points at the event.
        assert db.session.get(Booking, assignment.transport_booking_id).event_id is not None

    # Dashboard now reports one transport assignment.
    resp = client.get(f"{base}/coordination")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["transport_assigned"] == 1

    # Cancel through the DELETE route.
    resp = client.delete(f"{base}/coordination/{registration_ref}/transport")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["status"] == "cancelled"

    with app.app_context():
        assignment = EventAssignment.query.filter_by(
            event_id=event_id, registration_id=reg_id, is_deleted=False
        ).first()
        assert assignment is not None
        assert assignment.transport_booking_id is None
        passenger = _active_passengers_for_assignment(assignment.id)
        assert passenger == []
        archived = TransportPassenger.query.filter(
            TransportPassenger.event_assignment_id == assignment.id,
        ).all()
        assert len(archived) == 1
        assert archived[0].status == PassengerStatus.CANCELLED
        assert (archived[0].passenger_metadata or {}).get("release_reason") == "assignment cancelled"

    # Dashboard reflects the release.
    resp = client.get(f"{base}/coordination")
    assert resp.status_code == 200
    assert resp.get_json()["transport_assigned"] == 0