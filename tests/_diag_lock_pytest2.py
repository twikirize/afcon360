import threading, time, uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from app.events.guest_coordination_service import GuestCoordinationService, CoordinationError
from app.extensions import db
from app.identity.models.user import User
from app.events.models import Event, TicketType, EventGuest, EventRegistration
from app.transport.models import (
    Booking, BookingStatus, ComplianceStatus, DriverProfile,
    ProviderType, ServiceType, VerificationTier, Vehicle,
)


@pytest.fixture
def actor():
    from app.identity.models.user import User
    unique_suffix = uuid.uuid4().hex[:8]
    user = User(public_id=str(uuid.uuid4()), username=f"diag3_actor_{unique_suffix}",
                email=f"diag3_actor_{unique_suffix}@example.com", is_verified=True, is_active=True, email_verified=True)
    user.set_password("Password123!")
    db.session.add(user); db.session.commit()
    return user


@pytest.fixture
def event(actor):
    from app.events.models import Event
    ev = Event(public_id=str(uuid.uuid4()), event_ref=f"EVT-{uuid.uuid4().hex[:8].upper()}",
               slug=f"diag3-event-{uuid.uuid4().hex[:8]}", name="Diag3 Event", organizer_id=actor.id,
               city="Test City", country="UG", description="d", category="general",
               max_capacity=100, registration_fee=0, currency="USD",
               start_date=datetime.now(timezone.utc).date() - timedelta(days=1),
               end_date=datetime.now(timezone.utc).date() + timedelta(days=2),
               status="pending_approval")
    db.session.add(ev); db.session.commit()
    return ev


@pytest.fixture
def ticket_type(event):
    from app.events.models import TicketType
    tt = TicketType(event_id=event.id, name="General", price=0, capacity=100, is_active=True)
    db.session.add(tt); db.session.commit()
    return tt


@pytest.fixture
def event_guest():
    from app.events.models import EventGuest
    g = EventGuest(full_name="John Doe", email=f"jd_{uuid.uuid4().hex[:8]}@example.com")
    db.session.add(g); db.session.commit()
    return g


@pytest.fixture
def driver(actor):
    from app.transport.models import DriverProfile
    d = DriverProfile(user_id=actor.id, driver_code=f"DRV-{uuid.uuid4().hex[:6].upper()}",
                      verification_tier=VerificationTier.PLATFORM_VERIFIED,
                      compliance_status=ComplianceStatus.APPROVED,
                      is_online=True, is_available=True, max_passenger_capacity=4)
    db.session.add(d); db.session.commit()
    return d


@pytest.fixture
def vehicle():
    v = Vehicle(owner_type="driver", owner_id=1, license_plate=f"UG{uuid.uuid4().hex[:4].upper()}",
                make="Test", model="Model", year=2023, vehicle_type="Sedan",
                vehicle_class="comfort", passenger_capacity=4,
                current_location={"lat": 1.2, "lng": 3.4}, status="active", is_available=True)
    db.session.add(v); db.session.commit()
    return v


@pytest.fixture
def booking(actor, driver, vehicle):
    b = Booking(user_id=actor.id, provider_type=ProviderType.INDIVIDUAL_DRIVER,
                service_type=ServiceType.ON_DEMAND,
                pickup_location={"lat": 1.2, "lng": 3.4}, dropoff_location={"lat": 5.6, "lng": 7.8},
                pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
                passenger_count=4, base_price=100.00, currency="USD",
                status=BookingStatus.CONFIRMED,
                booking_reference=f"TB{uuid.uuid4().hex[:10].upper()}",
                assigned_driver_id=driver.id, assigned_vehicle_id=vehicle.id)
    db.session.add(b); db.session.commit()
    return b


def _make_registration(event, ticket_type, guest):
    from app.events.models import EventRegistration
    reg = EventRegistration(event_id=event.id, ticket_type_id=ticket_type.id,
                            full_name=guest.full_name, email=guest.email, phone=guest.phone,
                            nationality=guest.nationality, status="confirmed", payment_status="free",
                            registration_fee=0, guest_id=guest.id, booking_type="self")
    db.session.add(reg)
    seq = int(uuid.uuid4().int % 10 ** 8)
    reg.generate_refs(event_slug=event.slug, sequence=seq)
    db.session.commit()
    return reg


def test_diag3(actor, event, ticket_type, event_guest, booking, db_session):
    import os
    from app.events.models import EventGuest

    second_guest = EventGuest(full_name="Jane Doe", email=f"jane.doe_{uuid.uuid4().hex[:8]}@example.com")
    db.session.add(second_guest)
    db.session.commit()

    reg1 = _make_registration(event, ticket_type, event_guest)
    reg2 = _make_registration(event, ticket_type, second_guest)

    booking.passenger_count = 2
    db.session.commit()

    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    stop = threading.Event()

    print("### about to assign; booking id=", booking.id, "ref=", booking.booking_reference)

    def watcher():
        w_eng = create_engine(str(url or ""))
        while not stop.is_set():
            try:
                with w_eng.connect() as wc:
                    rows = wc.execute(text(
                        "SELECT a.pid, a.state, a.application_name, a.client_port, a.backend_xid::text, "
                        "NOW()-a.xact_start age, left(a.query,90) q, "
                        "array_to_string(pg_blocking_pids(a.pid), ',') blockers "
                        "FROM pg_stat_activity a WHERE a.datname=current_database() AND a.pid<>pg_backend_pid() "
                        "AND a.state<>'idle'")).fetchall()
                    for r in rows:
                        print("   [W] pid=", r.pid, "state=", r.state, "app=", r.application_name,
                              "port=", r.client_port, "xid=", r.backend_xid, "age=", r.age,
                              "blockers=", r.blockers, "q=", repr(r.q))
                    locks = wc.execute(text(
                        "SELECT l.pid, l.locktype, l.mode, l.granted, l.relation::regclass rel, "
                        "l.page, l.tuple, l.transactionid::text txid, l.objid "
                        "FROM pg_locks l "
                        "WHERE l.pid<>pg_backend_pid() AND l.granted "
                        "AND l.locktype IN ('relation','tuple','transactionid','virtualxid','advisory') "
                        "AND (l.locktype<>'relation' OR l.relation='transport_bookings'::regclass "
                        "OR l.relation='users'::regclass OR l.relation='event_assignments'::regclass "
                        "OR l.relation='event_registrations'::regclass)")).fetchall()
                    for l in locks:
                        print("   [W] HELD pid=", l.pid, l.locktype, l.mode, "rel=", l.rel,
                              "page=", l.page, "tuple=", l.tuple, "txid=", l.txid, "objid=", l.objid)
            except Exception as e:
                print("   [W] watcher err", e)
            time.sleep(0.3)

    t = threading.Thread(target=watcher, daemon=True)
    t.start()
    try:
        a1 = GuestCoordinationService.assign_transport(event, actor, reg1.registration_ref, booking.booking_reference)
        print("### ASSIGN1 OK, id=", a1.id)
    except CoordinationError as e:
        print("### ASSIGN1 FAILED:", e.code, "-", e.message)
    stop.set()
    t.join(timeout=2)
    pytest.fail("diag-only test (expected)")