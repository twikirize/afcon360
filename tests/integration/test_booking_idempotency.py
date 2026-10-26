"""
Fix 1.1 — Booking Idempotency integration tests.

These tests exercise BookingService.create_booking() directly, not via
the HTTP /transport/book route. The route is wrapped by pre-existing
decorators (@require_kyc_tier(2), @require_profile_completion) that are
not part of Fix 1.1. Calling the service isolates the idempotency
guarantee from those unrelated gates.

Guarantee under test:
  Same (idempotency_key, user_id) → exactly one Booking row.
  Second and subsequent submissions return the first booking's
  booking_reference without side effects.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pytest


def _unique_key(prefix):
    """Per-run unique idempotency key.

    The partial unique index ix_booking_idem is GLOBAL on
    idempotency_key (per Fix 1.1 contract Section 5). A fixed key
    whose Booking row survives a run would collide with a fresh
    test_user on the next run. Unique keys keep the suite
    repeatable regardless of leftover rows.
    """
    return f"{prefix}-{uuid.uuid4().hex}"


def _get_user_id(app, test_user):
    """Safely extract the internal user id from a detached User object.

    The test_user fixture commits and returns a detached instance.
    Attribute access on a detached instance triggers a refresh that
    fails with no session bound. merge() re-binds a transient copy to
    a fresh session so column values can be read reliably.
    """
    from app.extensions import db
    with app.app_context():
        merged = db.session.merge(test_user)
        uid = merged.id
        db.session.rollback()
        return uid


def _base_payload():
    # C1 (Node 3): UI-LOC-02A requires resolved coordinates at creation.
    # The string fields remain the rider labels; the coordinates are the
    # resolved endpoints the contract now demands.
    return {
        "pickup_location": "Test Pickup",
        "dropoff_location": "Test Dropoff",
        "pickup_latitude": 0.3136,
        "pickup_longitude": 32.5811,
        "dropoff_latitude": 0.3476,
        "dropoff_longitude": 32.5825,
        "service_type": "on_demand",
        "booking_mode": "instant",
        "pickup_time": "2026-12-31T10:00:00",
        "passenger_count": 1,
        "currency": "USD",
        "vehicle_class": "comfort",
        "payment_method": "cash",
    }


def _call_service(app, user_id, idem_key, payload=None):
    """Call BookingService.create_booking directly.

    Bypasses HTTP decorators (KYC tier 2, profile completion) which are
    pre-existing and out of scope for Fix 1.1.
    """
    from app.transport.services.booking_service import BookingService
    with app.app_context():
        data = _base_payload()
        if payload:
            data.update(payload)
        data["idempotency_key"] = idem_key
        service = BookingService()
        return service.create_booking(
            user_id, data, request_id=f"test-{idem_key}"
        )


def _count_bookings(app, idem_key, user_id):
    from app.transport.models import Booking
    with app.app_context():
        return Booking.query.filter_by(
            idempotency_key=idem_key,
            user_id=user_id,
            is_deleted=False,
        ).count()


def _get_booking_reference(app, idem_key, user_id):
    from app.transport.models import Booking
    with app.app_context():
        booking = Booking.query.filter_by(
            idempotency_key=idem_key,
            user_id=user_id,
            is_deleted=False,
        ).first()
        return booking.booking_reference if booking else None


def _cleanup_key(app, idem_key):
    """Delete every Booking row that carries a given idempotency_key.

    Threaded tests skip _isolate_db (conftest auto-cleanup), so they
    must self-clean every row they create -- established convention
    (see tests/test_transport_concurrent_claim.py _delete). Without
    this, the committed row survives the run and breaks the next run
    via the global unique index ix_booking_idem.
    """
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        Booking.query.filter_by(idempotency_key=idem_key).delete(
            synchronize_session=False
        )
        db.session.commit()


class TestBookingIdempotency:

    def test_first_post_creates_booking(self, app, test_user):
        """First submission with a new key creates exactly one booking."""
        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("idem-test-first")

        result = _call_service(app, user_id, idem_key)

        assert result.get("success") is True, f"Service failed: {result}"
        # First call must NOT be flagged as a replay
        assert result["data"].get("idempotent_replay") in (None, False)
        assert _count_bookings(app, idem_key, user_id) == 1

    def test_second_post_returns_existing_booking(self, app, test_user):
        """Second submission with the same key returns the same reference."""
        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("idem-test-second")

        first = _call_service(app, user_id, idem_key)
        assert first.get("success") is True
        ref_first = first["data"]["booking_reference"]

        second = _call_service(app, user_id, idem_key)
        assert second.get("success") is True
        assert second["data"]["booking_reference"] == ref_first
        assert second["data"].get("idempotent_replay") is True

        # Still exactly one row
        assert _count_bookings(app, idem_key, user_id) == 1

    def test_different_keys_create_different_bookings(self, app, test_user):
        """Different keys create separate bookings."""
        user_id = _get_user_id(app, test_user)
        key1 = _unique_key("idem-test-diff")
        key2 = _unique_key("idem-test-diff")

        r1 = _call_service(app, user_id, key1)
        r2 = _call_service(app, user_id, key2)

        assert r1.get("success") is True
        assert r2.get("success") is True

        ref1 = r1["data"]["booking_reference"]
        ref2 = r2["data"]["booking_reference"]
        assert ref1 != ref2

        assert _count_bookings(app, key1, user_id) == 1
        assert _count_bookings(app, key2, user_id) == 1

    @pytest.mark.threaded
    def test_concurrent_same_key_creates_exactly_one(self, app, test_user):
        """Five concurrent submissions with the same key → one row.

        The loser of the DB unique-index race must be converted into a
        replay, not a ServiceUnavailableError.
        """
        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("idem-test-concurrent")

        def submit():
            return _call_service(app, user_id, idem_key)

        results = []
        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(submit) for _ in range(5)]
                for f in as_completed(futures):
                    results.append(f.result())
            # Capture asserts BEFORE cleanup: _cleanup_key deletes the rows
            # and counting after cleanup would report 0.
            row_count = _count_bookings(app, idem_key, user_id)
            replay_count = sum(
                1 for r in results
                if r.get("data", {}).get("idempotent_replay")
            )
        finally:
            # Threaded tests skip _isolate_db auto-cleanup; remove the
            # committed keyed row so it cannot poison the next run via
            # the global unique index ix_booking_idem.
            _cleanup_key(app, idem_key)

        # Every thread must report success
        for r in results:
            assert r.get("success") is True, f"Thread failed: {r}"

        # Exactly one row existed at commit time
        assert row_count == 1

        # At least one result must be flagged as a replay
        assert replay_count >= 1, (
            f"Expected at least one replay among {len(results)} results; "
            f"got {replay_count}"
        )


class TestIdempotencyFingerprint:
    """PICKUP-TIME-AUTHORITY-P1 (patch #7 + Addendum-2 Option A).

    A replay is only valid when the same key arrives with the SAME trip
    (canonical fingerprint). A successful replay is a READ: no metadata
    mutation, no commit. Legacy rows without a fingerprint fail closed.
    """

    def test_replay_same_key_same_payload_is_read_only(self, app, test_user):
        """Addendum-2 Option A: the replay return writes nothing."""
        from app.extensions import db
        from app.transport.models import Booking

        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("p1-fp-read-only")

        first = _call_service(app, user_id, idem_key)
        assert first.get("success") is True

        with app.app_context():
            booking = Booking.query.filter_by(
                idempotency_key=idem_key, user_id=user_id,
                is_deleted=False).first()
            meta_before = dict(booking.booking_metadata or {})
            updated_before = booking.updated_at
            assert "trip_fingerprint" in meta_before
            db.session.rollback()

        second = _call_service(app, user_id, idem_key)
        assert second.get("success") is True
        assert second["data"].get("idempotent_replay") is True
        assert second["data"]["booking_reference"] == first["data"]["booking_reference"]

        with app.app_context():
            booking = Booking.query.filter_by(
                idempotency_key=idem_key, user_id=user_id,
                is_deleted=False).first()
            meta_after = dict(booking.booking_metadata or {})
            db.session.rollback()
        # No replay bookkeeping leaked into the row.
        assert "idempotent_replay" not in meta_after
        assert "replayed_at" not in meta_after
        assert meta_after == meta_before

    def test_replay_rejects_legacy_row_without_fingerprint(self, app, test_user):
        """A pre-P1 row has no trip_fingerprint: fail closed (Addendum 2)."""
        from app.extensions import db
        from app.transport.models import Booking
        from app.utils.exceptions import ValidationError

        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("p1-fp-legacy")

        first = _call_service(app, user_id, idem_key)
        assert first.get("success") is True

        # Simulate a legacy row: strip the fingerprint.
        with app.app_context():
            booking = Booking.query.filter_by(
                idempotency_key=idem_key, user_id=user_id,
                is_deleted=False).first()
            meta = dict(booking.booking_metadata or {})
            meta.pop("trip_fingerprint", None)
            booking.booking_metadata = meta
            db.session.commit()

        with pytest.raises(ValidationError) as exc:
            _call_service(app, user_id, idem_key)
        assert exc.value.field == "idempotency_key"
        assert _count_bookings(app, idem_key, user_id) == 1

    def test_replay_rejects_same_key_different_trip(self, app, test_user):
        """Same key + different trip is a client error, not a replay."""
        from app.utils.exceptions import ValidationError

        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("p1-fp-different-trip")

        first = _call_service(app, user_id, idem_key)
        assert first.get("success") is True

        with pytest.raises(ValidationError) as exc:
            _call_service(app, user_id, idem_key,
                          payload={"passenger_count": 3})
        assert "different trip" in str(exc.value.message)
        assert _count_bookings(app, idem_key, user_id) == 1

    def test_instant_replay_ignores_client_pickup_time_drift(
            self, app, test_user):
        """Instant fingerprint normalises pickup_time away: the server
        clock is the authority, so a retried client time cannot block
        the replay."""
        from datetime import datetime, timezone, timedelta

        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("p1-fp-instant-drift")

        first = _call_service(app, user_id, idem_key)
        assert first.get("success") is True

        drifted = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        second = _call_service(app, user_id, idem_key,
                               payload={"pickup_time": drifted})
        assert second.get("success") is True
        assert second["data"].get("idempotent_replay") is True
        assert second["data"]["booking_reference"] == first["data"]["booking_reference"]

    def test_scheduled_replay_fingerprint_guards_pickup_time(
            self, app, test_user):
        """Scheduled fingerprint hashes the explicit ISO pickup_time:
        same time replays, a different time is rejected."""
        from datetime import datetime, timezone, timedelta
        from app.utils.exceptions import ValidationError

        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("p1-fp-scheduled")
        sched = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()

        first = _call_service(
            app, user_id, idem_key,
            payload={"booking_mode": "scheduled", "pickup_time": sched})
        assert first.get("success") is True

        replay = _call_service(
            app, user_id, idem_key,
            payload={"booking_mode": "scheduled", "pickup_time": sched})
        assert replay.get("success") is True
        assert replay["data"].get("idempotent_replay") is True

        other = (datetime.now(timezone.utc) + timedelta(minutes=90)).isoformat()
        with pytest.raises(ValidationError) as exc:
            _call_service(
                app, user_id, idem_key,
                payload={"booking_mode": "scheduled", "pickup_time": other})
        assert "different trip" in str(exc.value.message)
        assert _count_bookings(app, idem_key, user_id) == 1

    @pytest.mark.threaded
    def test_concurrent_same_key_different_trip_one_wins(self, app, test_user):
        """Racing submissions: same key, DIFFERENT trips.

        Exactly one insert wins; every loser resolves to a field-precise
        client error (dedupe or IntegrityError fingerprint path), never
        a silent replay of the other trip and never a service outage.
        """
        from app.utils.exceptions import ValidationError

        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("p1-fp-race")

        def submit(passengers):
            return _call_service(app, user_id, idem_key,
                                 payload={"passenger_count": passengers})

        outcomes = []
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(submit, n) for n in (1, 2)]
                for f in as_completed(futures):
                    try:
                        outcomes.append(("ok", f.result()))
                    except ValidationError as e:
                        outcomes.append(("validation", e))
            row_count = _count_bookings(app, idem_key, user_id)
        finally:
            _cleanup_key(app, idem_key)

        wins = [o for o in outcomes if o[0] == "ok"]
        losses = [o for o in outcomes if o[0] == "validation"]
        assert len(wins) == 1, outcomes
        assert len(losses) == 1, outcomes
        assert wins[0][1]["data"].get("idempotent_replay") in (None, False)
        assert row_count == 1