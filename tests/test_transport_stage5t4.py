# tests/test_transport_stage5t4.py
"""Stage 5T-4: Transport Reservation & Handoff — missing gap tests.

Extends Stage 5T-3 by proving the remaining handoff semantics that were not
explicitly covered: booking state-machine preservation and organisation-side
transport flow.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.events.guest_coordination_service import GuestCoordinationService, CoordinationError
from app.extensions import db
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    OrganisationTransportProfile,
    PassengerStatus,
    ProviderType,
    ServiceType,
    TransportPassenger,
    Vehicle,
    VerificationTier,
)
from app.transport.services.passenger_service import get_passenger_service


# ---------------------------------------------------------------------------
# Fixtures (reused from Stage 5T-3 pattern)
# ---------------------------------------------------------------------------

@pytest.fixture
def actor():
    """Organizer / coordinator with event-owner permission."""
    from app.identity.models.user import User

    unique_suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"stage5t4_actor_{unique_suffix}",
        email=f"stage5t4_actor_{unique_suffix}@example.com",
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
        username=f"stage5t4_other_{unique_suffix}",
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
        slug=f"stage5t4-event-{uuid.uuid4().hex[:8]}",
        name="Stage 5T-4 Event",
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
        license_plate=f"UG{uuid.uuid4().hex[:4].upper()}",
        make="Test",
        model="Model",
        year=2023,
        vehicle_type="Sedan",
        vehicle_class="comfort",
        passenger_capacity=4,
        current_location={"lat": 1.2, "lng": 3.4},
        status="active",
        is_available=True,
    )
    db.session.add(v)
    db.session.commit()
    return v


@pytest.fixture
def org_profile(actor):
    """An approved organisation transport profile."""
    from app.identity.models.organisation import Organisation

    org = Organisation(
        name=f"Test Transport Co {uuid.uuid4().hex[:6]}",
        slug=f"test-transport-{uuid.uuid4().hex[:6]}",
        email=f"org_{uuid.uuid4().hex[:6]}@example.com",
        country="UG",
        city="Kampala",
        is_verified=True,
        is_active=True,
    )
    db.session.add(org)
    db.session.flush()

    profile = OrganisationTransportProfile(
        organisation_id=org.id,
        registration_type="transport_company",
        compliance_status=ComplianceStatus.APPROVED,
        license_verified=True,
        insurance_verified=True,
        can_provide_on_demand=True,
        can_provide_airport_transfers=True,
        can_provide_city_tours=True,
        fleet_size=2,
        available_fleet_size=2,
        total_passenger_capacity=8,
        transport_manager_name="Manager",
        transport_manager_phone="+256700000000",
        transport_manager_email="mgr@example.com",
        accepts_bookings=True,
    )
    db.session.add(profile)
    db.session.commit()
    return profile


@pytest.fixture
def org_vehicle(org_profile):
    """A vehicle owned by the organisation."""
    v = Vehicle(
        owner_type="organisation",
        owner_id=org_profile.organisation_id,
        license_plate=f"UG{uuid.uuid4().hex[:4].upper()}",
        make="Org",
        model="Van",
        year=2023,
        vehicle_type="Van",
        vehicle_class="van",
        passenger_capacity=8,
        current_location={"lat": 1.2, "lng": 3.4},
        status="active",
        is_available=True,
    )
    db.session.add(v)
    db.session.commit()
    return v


def _make_booking(actor, driver, vehicle, **overrides):
    """Create a confirmed, driver/vehicle-assigned transport booking (individual driver)."""
    b = Booking(
        user_id=actor.id,
        provider_type=ProviderType.INDIVIDUAL_DRIVER,
        service_type=ServiceType.ON_DEMAND,
        pickup_location={"lat": 1.2, "lng": 3.4},
        dropoff_location={"lat": 5.6, "lng": 7.8},
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


def _make_org_booking(org_profile, org_vehicle, **overrides):
    """Create a confirmed, organisation-assigned transport booking."""
    b = Booking(
        user_id=org_profile.organisation_id,  # org as booker (provider)
        provider_type=ProviderType.TRANSPORT_COMPANY,
        service_type=ServiceType.ON_DEMAND,
        pickup_location={"lat": 1.2, "lng": 3.4},
        dropoff_location={"lat": 5.6, "lng": 7.8},
        pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
        passenger_count=4,
        base_price=100.00,
        currency="USD",
        status=BookingStatus.CONFIRMED,
        booking_reference=f"TB{uuid.uuid4().hex[:10].upper()}",
        provider_id=org_profile.id,
        assigned_vehicle_id=org_vehicle.id,
    )
    for k, v in overrides.items():
        setattr(b, k, v)
    db.session.add(b)
    db.session.commit()
    return b


def _active_passengers_for_assignment(assignment_id):
    return TransportPassenger.query.filter(
        TransportPassenger.event_assignment_id == assignment_id,
        TransportPassenger.status != PassengerStatus.CANCELLED,
    ).all()


# ---------------------------------------------------------------------------
# R5 - Transport booking lifecycle is not incorrectly advanced by Event coordination
# ---------------------------------------------------------------------------

def test_t5t4_01_transport_booking_status_preserved_through_assign_reassign_cancel(
    actor, event, ticket_type, event_guest, driver, vehicle, registration, db_session
):
    """Full assign -> reassign -> cancel cycle must never move the booking status.

    Transport booking lifecycle (status transitions CONFIRMED -> ASSIGNED ->
    DRIVER_EN_ROUTE -> PICKUP_ARRIVED -> IN_PROGRESS -> COMPLETED) is owned by
    the Transport domain state machine; Events coordination must leave booking
    status untouched.
    """
    state_before = booking.status if (booking := _make_booking(actor, driver, vehicle)) else None

    # We need a second booking for reassignment
    booking_a = _make_booking(actor, driver, vehicle)
    booking_b = _make_booking(actor, driver, vehicle)
    state_before_a = booking_a.status
    state_before_b = booking_b.status

    # First assignment to booking A
    assignment_a = GuestCoordinationService.assign_transport(
        event, actor, registration.registration_ref, booking_a.booking_reference
    )
    db.session.refresh(booking_a)
    assert booking_a.status == state_before_a, "First assignment must not change booking status"

    # Reassign to booking B
    assignment_b = GuestCoordinationService.assign_transport(
        event, actor, registration.registration_ref, booking_b.booking_reference
    )
    db.session.refresh(booking_a)
    db.session.refresh(booking_b)
    assert booking_a.status == state_before_a, "Reassignment must not change old booking status"
    assert booking_b.status == state_before_b, "Reassignment must not change new booking status"

    # Cancel the assignment
    GuestCoordinationService.cancel(event, actor, registration.registration_ref, "transport")
    db.session.refresh(booking_a)
    db.session.refresh(booking_b)
    assert booking_a.status == state_before_a, "Cancel must not change old booking status"
    assert booking_b.status == state_before_b, "Cancel must not change new booking status"

    # Verify the assignment pointer is cleared but booking status unchanged
    from app.events.models import EventAssignment
    assignment = EventAssignment.query.filter_by(
        event_id=event.id, registration_id=registration.id, is_deleted=False
    ).first()
    assert assignment is not None
    assert assignment.transport_booking_id is None


# ---------------------------------------------------------------------------
# R11 Case C - Organisation/provider-side transport flow works without Events
# ---------------------------------------------------------------------------

def test_t5t4_02_direct_organisation_transport_booking_works_without_events(
    org_profile, org_vehicle, db_session
):
    """An organisation transport booking (provider = transport_company) accepts
    passengers directly without any Events involvement.

    This mirrors the individual-driver flow in T5T3-13 but uses an
    OrganisationTransportProfile as the provider.
    """
    from app.events.models import EventAssignment

    booking = _make_org_booking(org_profile, org_vehicle, passenger_count=4)

    assert booking.event_id is None
    assert booking.provider_type == ProviderType.TRANSPORT_COMPANY
    assert booking.provider_id == org_profile.id

    svc = get_passenger_service()

    # Add a passenger linked to a user (simulating a known rider)
    rider_user = db.session.query(__import__('app.identity.models.user', fromlist=['User']).User).filter_by(email="rider@example.com").first()
    if not rider_user:
        from app.identity.models.user import User
        rider_user = User(
            public_id=str(uuid.uuid4()),
            username=f"rider_{uuid.uuid4().hex[:6]}",
            email="rider@example.com",
            is_verified=True,
            is_active=True,
            email_verified=True,
        )
        rider_user.set_password("Password123!")
        db.session.add(rider_user)
        db.session.flush()

    self_passenger = svc.add_passenger(
        booking, name=rider_user.username, email=rider_user.email, user_id=rider_user.id
    )
    accountless = svc.add_passenger(
        booking, name="Guest Rider", email="guest.rider@example.com"
    )
    db.session.commit()

    assert self_passenger.status == PassengerStatus.LINKED
    assert self_passenger.user_id == rider_user.id
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
# Additional handoff sanity: passenger count sync on contract reservation
# ---------------------------------------------------------------------------

def test_t5t4_03_contract_reservation_syncs_booking_passenger_count(
    actor, event, ticket_type, event_guest, driver, vehicle, registration, db_session
):
    """When the contract creates a passenger reservation, the booking's
    passenger_count is not automatically inflated; capacity remains
    authoritative via the declared seat target (booking.passenger_count).
    """
    booking = _make_booking(actor, driver, vehicle, passenger_count=2)

    # Before contract reservation, booking has no Transport passengers
    initial_count = TransportPassenger.query.filter(
        TransportPassenger.booking_id == booking.id,
        TransportPassenger.status != PassengerStatus.CANCELLED,
    ).count()
    assert initial_count == 0

    # Assign via Events service (which calls the contract)
    assignment = GuestCoordinationService.assign_transport(
        event, actor, registration.registration_ref, booking.booking_reference
    )

    # After assignment, exactly one active reservation exists
    active = _active_passengers_for_assignment(assignment.id)
    assert len(active) == 1
    assert active[0].status == PassengerStatus.CONFIRMED

    # The booking's declared passenger_count (capacity target) is unchanged
    db.session.refresh(booking)
    assert booking.passenger_count == 2


# ---------------------------------------------------------------------------
# Handoff correlation: EventAssignment <-> TransportPassenger round-trip
# ---------------------------------------------------------------------------

def test_t5t4_04_event_assignment_can_locate_its_transport_passenger(
    actor, event, ticket_type, event_guest, driver, vehicle, registration, db_session
):
    """Given an EventAssignment, the correlated TransportPassenger can be
    retrieved and has correct identity fields.
    """
    booking = _make_booking(actor, driver, vehicle, passenger_count=1)

    assignment = GuestCoordinationService.assign_transport(
        event, actor, registration.registration_ref, booking.booking_reference
    )

    passenger = _active_passengers_for_assignment(assignment.id)
    assert len(passenger) == 1
    p = passenger[0]

    # Correlation fields
    assert p.event_assignment_id == assignment.id
    assert p.booking_id == booking.id

    # Identity snapshot from registration
    assert p.name == registration.full_name
    assert p.email == registration.email.lower() if registration.email else None
    assert p.phone == registration.phone
    assert p.user_id == getattr(registration, "user_id", None)

    # Status is CONFIRMED (not LINKED unless user_id matches and claim happened)
    assert p.status == PassengerStatus.CONFIRMED