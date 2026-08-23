"""Staging server for AFCON360 high-concurrency inventory load testing.

Boots the real Flask app (same code path as production) on localhost with:
  * RATELIMIT_ENABLED = False   (so locust is not throttled)
  * WTF_CSRF_ENABLED = False    (so scripted login works)
  * Redis sessions enabled, but cookie flags relaxed for HTTP.
  * Served via Waitress (real thread pool) instead of Flask's single-process
    dev server, which saturates hard above ~100 concurrent users.

It points at the TEST database (never production), seeds one published event
with a limited ticket tier plus N load-test users, prints the identifiers the
locustfile needs, then serves traffic so locust/k6 can hammer the real
POST /events/<slug>/reserve endpoint.

Run (from project root, with the venv active):
    $env:EVENT_CAP=50; $env:LOADTEST_USERS=150
    python loadtest/staging_server.py
"""

import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env(PROJECT_ROOT / ".env.testing")
_test_db = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
if not _test_db:
    raise RuntimeError("No TEST_DATABASE_URL / DATABASE_URL configured")
os.environ["DATABASE_URL"] = _test_db
os.environ["REQUIRE_EMAIL_VERIFICATION"] = "false"

from app.config import Config


class StagingConfig(Config):
    """Config for the local load-test server (no throttling, Redis sessions)."""

    RATELIMIT_ENABLED = False
    WTF_CSRF_ENABLED = False

    # Keep Redis sessions (production-accurate). Relax cookie flags for HTTP.
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True

    SECRET_KEY = "loadtest-only-secret-not-for-production"
    REQUIRE_EMAIL_VERIFICATION = False
    DEBUG = False
    TESTING = False
    SERVER_NAME = None

    # NOTE: Waitress uses one process with a thread pool, so this pool is
    # shared across all threads — not multiplied per-worker the way it would
    # be under a multi-process server like Gunicorn. Keep it comfortably
    # under your test DB's max_connections.
    # Original pool sized for ~100 concurrent users (40 + 40 overflow).
    # Kept for reference — restore this when load testing at <= ~100 users
    # so the test DB's max_connections is not over-provisioned.
    # SQLALCHEMY_ENGINE_OPTIONS = {
    #     "pool_size": 40,
    #     "max_overflow": 40,
    #     "pool_pre_ping": True,
    #     "pool_timeout": 30,
    # }

    # Bigger connection pool for 150 concurrent users
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 80,
        "max_overflow": 80,          # total 160 connections
        "pool_pre_ping": True,
        "pool_timeout": 60,
    }


from app import create_app
from app.extensions import db
from sqlalchemy import text
from app.identity.models.user import User
from app.events.models import Event, EventStatus, TicketType
from werkzeug.security import generate_password_hash

CAP = int(os.getenv("EVENT_CAP", "200"))
USERS = int(os.getenv("LOADTEST_USERS", "500"))
PASSWORD = os.getenv("LOADTEST_PASSWORD", "LoadTest123!")
SLUG = os.getenv("LOADTEST_SLUG", "loadtest-onsale")


def _seed():
    # Organiser
    organizer = User(
        email="loadtest_organizer@example.com",
        username="loadtest_organizer",
    )
    # Default method (scrypt / pbkdf2:sha256:600000) is CPU-expensive; kept
    # for reference. Restore it for staging runs where login CPU cost must
    # match production, but expect higher CPU load under 150 concurrent logins.
    # organizer.password_hash = generate_password_hash(PASSWORD)
    organizer.password_hash = generate_password_hash(PASSWORD, method='pbkdf2:sha256:100000')
    db.session.add(organizer)
    db.session.flush()

    # Event — with explicit registration dates
    event = Event(
        name="Load Test Onsale",
        slug=SLUG,
        city="Kampala",
        organizer_id=organizer.id,
        status=EventStatus.PUBLISHED.value,
        registration_required=True,
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=30),
        registration_opens_at=datetime.now() - timedelta(days=1),
        registration_closes_at=datetime.now() + timedelta(days=30),
        currency="USD",
    )
    db.session.add(event)
    db.session.flush()

    # Ticket type — set available seats to capacity
    tt = TicketType(
        event_id=event.id,
        name="General Admission",
        price=10,
        capacity=CAP,
        available_seats=CAP,
        is_active=True,
        available_from=None,
        available_until=None,
    )
    db.session.add(tt)
    db.session.flush()

    # Load-test users
    for i in range(USERS):
        u = User(
            email=f"loadtest_{i}@example.com",
            username=f"ltuser_{i}",
        )
        u.is_active = True
        # Default method (scrypt / pbkdf2:sha256:600000) is CPU-expensive; kept
        # for reference. Restore it for staging runs where login CPU cost must
        # match production, but expect higher CPU load under 150 concurrent logins.
        # u.password_hash = generate_password_hash(PASSWORD)
        u.password_hash = generate_password_hash(PASSWORD, method='pbkdf2:sha256:100000')
        db.session.add(u)

    db.session.commit()
    return event, tt


def _seed_or_reseed():
    """Cleans previous load-test data and seeds fresh. Assumes app context."""
    prev = Event.query.filter_by(slug=SLUG).first()
    if prev:
        # Delete child rows first — several FKs to event_ticket_types use
        # ON DELETE RESTRICT and would otherwise block the ticket-type /
        # event deletion.
        tt_ids = [t.id for t in TicketType.query.filter_by(event_id=prev.id).all()]
        if tt_ids:
            db.session.execute(
                text("DELETE FROM event_ticket_holds WHERE ticket_type_id = ANY(:ids)"),
                {"ids": tt_ids},
            )
            db.session.execute(
                text("DELETE FROM event_registrations WHERE ticket_type_id = ANY(:ids)"),
                {"ids": tt_ids},
            )
        TicketType.query.filter_by(event_id=prev.id).delete()
        db.session.delete(prev)
        db.session.commit()
        User.query.filter(User.email.like("loadtest_%@example.com")).delete(
            synchronize_session=False
        )
        db.session.commit()

    event, tt = _seed()

    print("=" * 60)
    print("LOADTEST_SEED_READY")
    print(f"EVENT_SLUG={event.slug}")
    print(f"TICKET_TYPE_ID={tt.id}")
    print(f"EVENT_CAP={CAP}")
    print(f"LOADTEST_USERS={USERS}")
    print(f"LOADTEST_PASSWORD={PASSWORD}")
    print("HOST=http://127.0.0.1:5001")
    print(f"registration_opens_at={event.registration_opens_at}")
    print(f"registration_closes_at={event.registration_closes_at}")
    print(f"available_seats={tt.available_seats}")
    print("=" * 60)
    return event, tt


def main():
    app = create_app(StagingConfig)
    with app.app_context():
        _seed_or_reseed()

    use_waitress = os.getenv("USE_WAITRESS", "true").lower() == "true"
    if use_waitress:
        from waitress import serve
        # `threads` gives Waitress a real OS-thread pool for handling
        # concurrent requests — this is what lets it survive far more
        # simultaneous connections than Werkzeug's dev server, which
        # documents itself as unsuitable for this kind of load.
        threads = int(os.getenv("WAITRESS_THREADS", "32"))
        print(f"Serving via Waitress (threads={threads}) on http://127.0.0.1:5001")
        serve(app, host="127.0.0.1", port=5001, threads=threads)
    else:
        print("Serving via Flask dev server on http://127.0.0.1:5001")
        app.run(host="127.0.0.1", port=5001, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()

