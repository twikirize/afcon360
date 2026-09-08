import os, uuid
os.environ["FLASK_ENV"] = "testing"
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text

from app import create_app
from app.config import TestingConfig
from app.extensions import db

from app.identity.models.user import User
from app.events.models import Event, TicketType, EventGuest, EventRegistration
from app.transport.models import (
    Booking, BookingStatus, ComplianceStatus, DriverProfile,
    ProviderType, ServiceType, VerificationTier, Vehicle,
)
from app.events.guest_coordination_service import GuestCoordinationService, CoordinationError

app = create_app(config_object=TestingConfig)
app.config["WTF_CSRF_ENABLED"] = False

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
print("URL:", TEST_DATABASE_URL.split("@")[-1])

with app.app_context():
    suf = uuid.uuid4().hex[:8]
    user = User(public_id=str(uuid.uuid4()), username=f"diag_actor_{suf}",
                email=f"diag_actor_{suf}@example.com", is_verified=True, is_active=True, email_verified=True)
    user.set_password("Password123!")
    db.session.add(user); db.session.commit()

    ev = Event(public_id=str(uuid.uuid4()), event_ref=f"EVT-{uuid.uuid4().hex[:8].upper()}",
               slug=f"diag-event-{suf}", name="Diag", organizer_id=user.id, city="Kampala",
               country="UG", category="general", max_capacity=100, registration_fee=0,
               currency="USD",
               start_date=datetime.now(timezone.utc).date() - timedelta(days=1),
               end_date=datetime.now(timezone.utc).date() + timedelta(days=2),
               status="pending_approval")
    db.session.add(ev); db.session.commit()

    tt = TicketType(event_id=ev.id, name="General", price=0, capacity=100, is_active=True)
    db.session.add(tt); db.session.commit()

    g1 = EventGuest(full_name="John A", email=f"ja_{suf}@example.com")
    db.session.add(g1)
    g2 = EventGuest(full_name="Jane B", email=f"jb_{suf}@example.com")
    db.session.add(g2); db.session.commit()

    d = DriverProfile(user_id=user.id, driver_code=f"DRV-{uuid.uuid4().hex[:6].upper()}",
                      verification_tier=VerificationTier.PLATFORM_VERIFIED,
                      compliance_status=ComplianceStatus.APPROVED,
                      is_online=True, is_available=True, max_passenger_capacity=4)
    db.session.add(d); db.session.commit()

    v = Vehicle(owner_type="driver", owner_id=1, license_plate=f"UG{uuid.uuid4().hex[:4].upper()}",
                make="Test", model="Model", year=2023, vehicle_type="Sedan",
                vehicle_class="comfort", passenger_capacity=4,
                current_location={"lat": 1.2, "lng": 3.4}, status="active", is_available=True)
    db.session.add(v); db.session.commit()

    b = Booking(user_id=user.id, provider_type=ProviderType.INDIVIDUAL_DRIVER,
                service_type=ServiceType.ON_DEMAND,
                pickup_location={"lat": 1.2, "lng": 3.4}, dropoff_location={"lat": 5.6, "lng": 7.8},
                pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
                passenger_count=2, base_price=100.00, currency="USD",
                status=BookingStatus.CONFIRMED,
                booking_reference=f"TB{uuid.uuid4().hex[:10].upper()}",
                assigned_driver_id=d.id, assigned_vehicle_id=v.id)
    db.session.add(b); db.session.commit()
    print("booking id:", b.id, "ref:", b.booking_reference, "pid(conn):")

    for i in (1, 2):
        g = g1 if i == 1 else g2
        reg = EventRegistration(event_id=ev.id, ticket_type_id=tt.id, full_name=g.full_name,
                                email=g.email, status="confirmed", payment_status="free",
                                registration_fee=0, guest_id=g.id, booking_type="self")
        db.session.add(reg)
        seq = int(uuid.uuid4().int % 10 ** 8)
        reg.generate_refs(event_slug=ev.slug, sequence=seq)
        db.session.commit()
        if i == 1:
            reg1 = reg

    multi_engine = create_engine(TEST_DATABASE_URL)
    with multi_engine.connect() as c2:
        rows = c2.execute(text(
            "SELECT pid, usename, state, wait_event_type, wait_event, now()-xact_start age, left(query,120) q "
            "FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()")).fetchall()
        print("=== OTHER SESSIONS BEFORE ASSIGN ===")
        for r in rows:
            print(" pid=", r.pid, "state=", r.state, "wait=", r.wait_event_type, r.wait_event, "age=", r.age, "q=", repr(r.q))
        locks = c2.execute(text(
            "SELECT locktype, mode, granted, pid, relation::regclass rel FROM pg_locks "
            "WHERE locktype<>'virtualxid' AND pid<>pg_backend_pid()")).fetchall()
        print("=== LOCKS HELD BY OTHERS BEFORE ASSIGN ===")
        for l in locks:
            print(" ", l)

    import threading, time
    stop = threading.Event()

    def watcher():
        w_eng = create_engine(TEST_DATABASE_URL)
        while not stop.is_set():
            try:
                with w_eng.connect() as wc:
                    rows = wc.execute(text(
                        "SELECT pid, state, wait_event_type, wait_event, now()-xact_start age, left(query,100) q "
                        "FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() "
                        "AND state<>'idle'")).fetchall()
                    if rows:
                        for r in rows:
                            print("  [WATCH] pid=", r.pid, "state=", r.state, "wait=", r.wait_event_type, r.wait_event,
                                  "age=", r.age, "q=", repr(r.q))
                    locks = wc.execute(text(
                        "SELECT l.pid, l.locktype, l.mode, l.granted, l.relation::regclass rel "
                        "FROM pg_locks l WHERE l.locktype IN ('relation','tuple','transactionid') "
                        "AND l.pid<>pg_backend_pid() AND l.granted=false")).fetchall()
                    if locks:
                        print("  [WATCH] BLOCKED-BY CANDIDATES (ungranted from my view):")
                        for l in locks:
                            print("    pid=", l.pid, l.locktype, l.mode, "granted?", l.granted, "rel=", l.rel)
            except Exception as e:
                print("  [WATCH] err", e)
            time.sleep(0.4)

    t = threading.Thread(target=watcher, daemon=True)
    t.start()
    try:
        a1 = GuestCoordinationService.assign_transport(ev, user, reg1.registration_ref, b.booking_reference)
        print("ASSIGN1 OK, assignment id:", a1.id)
    except CoordinationError as e:
        print("ASSIGN1 FAILED:", e.code, "-", e.message)
    stop.set()
    t.join(timeout=2)

    try:
        a2 = GuestCoordinationService.assign_transport(ev, user, reg2.registration_ref, b.booking_reference)
        print("ASSIGN2 OK, assignment id:", a2.id)
    except CoordinationError as e:
        print("ASSIGN2 FAILED:", e.code, "-", e.message)

    db.session.rollback()
    db.session.remove()