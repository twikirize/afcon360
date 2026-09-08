"""
Concurrency test for the RegistrationService row-lock (with_for_update) fix.

Regression target: two near-simultaneous registrations for the last open slot
must NOT both pass the active_count() check. Fires N concurrent create() calls
at a booking with num_guests = N - 1 and asserts exactly N - 1 succeed and the
over-capacity one raises ValueError — never N successes, never a deadlock.

See AFCON360_OUTSTANDING_TASKS.md Task 17.
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.guest_registration import GuestRegistration
from app.accommodation.models.property import Property
from app.accommodation.services.registration_service import RegistrationService
from app.extensions import db
from app.identity.models.user import User


def _make_booking(app, capacity):
    """Create (host user + property + booking with `capacity` slots), all
    committed, and return the booking row."""
    host = User(
        email=f"conc-host-{uuid.uuid4().hex[:8]}@example.com",
        username=f"conc-host-{uuid.uuid4().hex[:8]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        is_verified=True,
        is_active=True,
        kyc_level=2,
    )
    db.session.add(host)
    db.session.flush()

    prop = Property(
        title="Concurrency Test Property",
        slug=f"conc-prop-{uuid.uuid4().hex[:8]}",
        description="A test property for the row-lock concurrency test.",
        address_line1="123 Test Street",
        city="Kampala",
        country="UG",
        status="active",
        is_verified=True,
        is_active=True,
        base_price_per_night=Decimal("100.00"),
        currency="USD",
        max_guests=10,
        instant_book=True,
        owner_user_id=host.id,
    )
    db.session.add(prop)
    db.session.flush()

    booking = AccommodationBooking(
        guest_user_id=host.id,
        host_user_id=host.id,
        booked_by_user_id=host.id,
        property_id=prop.id,
        check_in=datetime.now(timezone.utc) + timedelta(days=30),
        check_out=datetime.now(timezone.utc) + timedelta(days=35),
        num_nights=5,
        num_guests=capacity,
        rooms_requested=1,
        nightly_rate=Decimal("100.00"),
        total_amount=Decimal("500.00"),
        currency="USD",
        status="confirmed",
        payment_status="paid",
        booking_reference=f"ACC-CONC-{uuid.uuid4().hex[:8].upper()}",
    )
    db.session.add(booking)
    db.session.commit()
    return booking


def _claim_slot(app, booking_id, worker_index, results):
    """Acquire the booking row lock in this thread's own session and try to
    claim one slot. `results` is shared: appends ('ok', i) or ('full', i)."""
    try:
        with app.app_context():
            try:
                booking = db.session.get(AccommodationBooking, booking_id)
                suffix = uuid.uuid4().hex[:8]
                RegistrationService.create(
                    booking,
                    name=f"Concurrent Guest {worker_index} {suffix}",
                    email=f"guest{worker_index}_{suffix}@example.com",
                    phone="+256700000000",
                    id_document_type="passport",
                    id_document_number=f"P{worker_index}{suffix}".upper(),
                    source="self",
                )
                results.append(("ok", worker_index))
            except ValueError as exc:
                results.append(("full", worker_index, str(exc)))
            finally:
                db.session.remove()
    except Exception as exc:  # pragma: no cover - surfaced via results on failure
        results.append(("error", worker_index, repr(exc)))


@pytest.mark.usefixtures("app")
class TestRegistrationRowLockConcurrency:
    def test_concurrent_creates_never_overfill(self, app, db_session):
        capacity = 4
        booking = _make_booking(app, capacity)
        booking_id = booking.id

        workers = capacity + 1  # one more than there are slots
        results = []
        start = time.monotonic()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_claim_slot, app, booking_id, i, results)
                for i in range(workers)
            ]
            for future in as_completed(futures, timeout=90):
                # Re-raise worker exceptions if any leaked past the handler.
                future.result(timeout=30)

        elapsed = time.monotonic() - start

        ok_count = sum(1 for r in results if r[0] == "ok")
        full_count = sum(1 for r in results if r[0] == "full")

        assert ok_count == capacity, (
            f"Expected exactly {capacity} successes, got {ok_count}: {results}"
        )
        assert full_count == 1, (
            f"Expected exactly 1 over-capacity rejection, got {full_count}: {results}"
        )
        assert all(r[0] in ("ok", "full") for r in results), (
            f"Non-ValueError failures: {[r for r in results if r[0] == 'error']}"
        )

        # The row lock must not hold the booking open long enough to become a
        # bottleneck under normal (non-concurrent) single-slot registration.
        assert elapsed < 60, (
            f"{workers} concurrent slot claims took {elapsed:.2f}s — possible "
            "lock-hold regression or deadlock"
        )

        with app.app_context():
            assert RegistrationService.active_count(booking_id) == capacity

    def test_sequential_create_stays_fast_after_lock_path(self, app, db_session):
        """Sanity: a plain single registration still commits quickly."""
        booking = _make_booking(app, 1)
        start = time.monotonic()
        with app.app_context():
            b = db.session.get(AccommodationBooking, booking.id)
            RegistrationService.create(
                b,
                name="Sequential Guest",
                email="seq@example.com",
                phone="+256700000001",
                id_document_type="passport",
                id_document_number="SEQ12345",
                source="host",
            )
        elapsed = time.monotonic() - start
        assert elapsed < 15, f"Sequential registration took {elapsed:.2f}s — too slow"
        with app.app_context():
            assert RegistrationService.active_count(booking.id) == 1