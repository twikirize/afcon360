"""AFCON360 GEO rider booking-scoped live tracking - contract tests.

Proves the tracking authority model: a rider sees the assigned
driver's live location ONLY through an active booking that currently
has that driver assigned. Server authorization (Transport-owned
subject), per-tick revalidation (terminal/release closes mid-stream),
truthful freshness states, public references only, latitude-first.

The full lifecycle matrix from the node rules is covered:
pre-assignment denied, active states allowed, terminal/released
closed, wrong actor denied, races close the stream.
"""

import itertools
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.transport.services.tracking_service import TrackingService
from tests.conftest import _login_client
from tests.test_geo_realtime import DeadRedis, FakeRedis

LAT, LNG = 0.3476, 32.5825  # asymmetric (swap-detecting)
LAT2, LNG2 = 0.3136, 32.5811


def _seed_owner(app, prefix="rider"):
    from app.extensions import db
    from app.identity.models.user import User
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"{prefix}_{uid}",
                    email=f"{prefix}_{uid}@test.example.com",
                    is_active=True, is_verified=True, email_verified=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()
        return user.id


def _seed_driver(app, prefix="RTD"):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import (ComplianceStatus, DriverProfile,
                                      VerificationTier)
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"{prefix.lower()}_{uid}",
                    email=f"{prefix.lower()}_{uid}@test.example.com",
                    is_active=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        profile = DriverProfile(
            user_id=user.id, driver_code=f"{prefix}-{uid[:6].upper()}",
            verification_tier=VerificationTier.PLATFORM_VERIFIED,
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True, is_online=True, is_available=True,
            max_passenger_capacity=4, vehicle_classes=["comfort"])
        db.session.add(profile)
        db.session.commit()
        return profile.id, profile.driver_code


def _seed_booking(app, owner_id, status, driver_id=None):
    from decimal import Decimal
    from app.extensions import db
    from app.transport.models import (Booking, ProviderType, ServiceType)
    with app.app_context():
        ref = f"RT-{uuid.uuid4().hex[:8].upper()}"
        booking = Booking(
            booking_reference=ref, user_id=owner_id,
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": LAT, "longitude": LNG},
            dropoff_location={"latitude": LAT2, "longitude": LNG2},
            pickup_time=datetime.now(timezone.utc) + timedelta(hours=1),
            passenger_count=1, base_price=Decimal("10.00"),
            subtotal=Decimal("10.00"), total_amount=Decimal("10.00"),
            final_price=Decimal("10.00"), status=status,
            assigned_driver_id=driver_id)
        db.session.add(booking)
        db.session.commit()
        return booking.id, ref


def _locate(app, driver_id, lat=LAT, lng=LNG):
    with app.app_context():
        result = TrackingService.update_location("driver", driver_id, {
            "latitude": lat, "longitude": lng, "accuracy": 3.0})
    assert result["success"] is True


def _rider_client(app, client, owner_id):
    from app.identity.models.user import User
    with app.app_context():
        from app.extensions import db
        user = db.session.get(User, owner_id)
        _login_client(client, user)
    return client


def _stream_url(ref):
    return f"/geo/stream/booking/{ref}"


# --- subject unit matrix ---------------------------------------------------------

def test_subject_unknown_booking_denied(app):
    owner = _seed_owner(app)
    with app.app_context():
        subject = TrackingService.get_rider_tracking_subject(
            "NO-SUCH-REF", owner, False)
    assert subject == {"allowed": False, "reason": "unknown_booking",
                       "booking_status": None, "driver_public_ref": None}


def test_subject_wrong_rider_denied(app):
    from app.transport.models import BookingStatus
    owner = _seed_owner(app, "owner")
    stranger = _seed_owner(app, "stranger")
    driver_id, _ = _seed_driver(app)
    _, ref = _seed_booking(app, owner, BookingStatus.ASSIGNED, driver_id)
    with app.app_context():
        subject = TrackingService.get_rider_tracking_subject(
            ref, stranger, False)
    assert subject["allowed"] is False
    assert subject["reason"] == "not_authorized"
    assert subject["driver_public_ref"] is None  # no driver leaked


def test_subject_pre_assignment_denied(app):
    from app.transport.models import BookingStatus
    owner = _seed_owner(app)
    for status in (BookingStatus.DRAFT, BookingStatus.PENDING_PAYMENT,
                   BookingStatus.CONFIRMED):
        _, ref = _seed_booking(app, owner, status)
        with app.app_context():
            subject = TrackingService.get_rider_tracking_subject(
                ref, owner, False)
        assert subject["allowed"] is False
        assert subject["reason"] == "not_trackable"


def test_subject_active_states_allowed(app):
    from app.transport.models import BookingStatus
    owner = _seed_owner(app)
    driver_id, code = _seed_driver(app)
    for status in (BookingStatus.ASSIGNED, BookingStatus.DRIVER_EN_ROUTE,
                   BookingStatus.PICKUP_ARRIVED, BookingStatus.IN_PROGRESS,
                   BookingStatus.DISPUTED):
        _, ref = _seed_booking(app, owner, status, driver_id)
        with app.app_context():
            subject = TrackingService.get_rider_tracking_subject(
                ref, owner, False)
        assert subject["allowed"] is True, status
        assert subject["driver_public_ref"] == code
        assert subject["booking_status"] == status.value


def test_subject_terminal_and_released_closed(app):
    from app.transport.models import BookingStatus
    owner = _seed_owner(app)
    driver_id, _ = _seed_driver(app)
    for status in (BookingStatus.COMPLETED, BookingStatus.CANCELLED,
                   BookingStatus.NO_SHOW):
        _, ref = _seed_booking(app, owner, status, driver_id)
        with app.app_context():
            subject = TrackingService.get_rider_tracking_subject(
                ref, owner, False)
        assert subject["allowed"] is False
        assert subject["reason"] == "not_trackable"
    # Released assignment on a live booking: closed, no fallback.
    _, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    with app.app_context():
        subject = TrackingService.get_rider_tracking_subject(
            ref, owner, False)
    assert subject["allowed"] is False


def test_subject_missing_driver_record_safe(app):
    from app.extensions import db
    from app.transport.models import BookingStatus, DriverProfile
    owner = _seed_owner(app)
    driver_id, _ = _seed_driver(app)
    _, ref = _seed_booking(app, owner, BookingStatus.ASSIGNED, driver_id)
    with app.app_context():
        # Driver removed after assignment: FK-safe soft delete.
        db.session.get(DriverProfile, driver_id).is_deleted = True
        db.session.commit()
        subject = TrackingService.get_rider_tracking_subject(
            ref, owner, False)
    assert subject == {"allowed": False, "reason": "no_driver",
                       "booking_status": "assigned",
                       "driver_public_ref": None}


# --- HTTP view ---------------------------------------------------------------------

def test_stream_redirects_anonymous(app, anonymous_client):
    resp = anonymous_client.get(_stream_url("ANY-REF"),
                                follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_stream_denies_unrelated_rider(app, authenticated_client):
    owner = _seed_owner(app)
    from app.transport.models import BookingStatus
    driver_id, _ = _seed_driver(app)
    _, ref = _seed_booking(app, owner, BookingStatus.ASSIGNED, driver_id)
    resp = authenticated_client.get(_stream_url(ref), follow_redirects=False)
    assert resp.status_code == 403


def test_stream_404_unknown_booking(app, admin_client):
    assert admin_client.get(_stream_url("NO-SUCH-REF")).status_code == 404


def test_stream_404_when_not_trackable(app, admin_client):
    from app.transport.models import BookingStatus
    owner = _seed_owner(app)
    _, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    assert admin_client.get(_stream_url(ref)).status_code == 404
    _, ref_done = _seed_booking(app, owner, BookingStatus.COMPLETED)
    assert admin_client.get(_stream_url(ref_done)).status_code == 404


def test_stream_snapshot_then_live_for_owner(app, client, monkeypatch):
    import app.transport.services.tracking_service as ts_mod
    from app.transport.models import BookingStatus

    fake = FakeRedis()
    monkeypatch.setattr(ts_mod, "redis_client", fake)
    monkeypatch.setattr("app.extensions.redis_client", fake)
    owner = _seed_owner(app)
    driver_id, code = _seed_driver(app)
    _, ref = _seed_booking(app, owner, BookingStatus.ASSIGNED, driver_id)
    _locate(app, driver_id)
    _rider_client(app, client, owner)

    resp = client.get(_stream_url(ref), buffered=False)
    assert resp.status_code == 200
    frames = list(itertools.islice(resp.response, 4))
    text = "".join(
        f.decode("utf-8") if isinstance(f, bytes) else f for f in frames)
    resp.close()
    assert "event: snapshot" in text
    assert code in text
    assert str(LAT) in text and str(LNG) in text
    assert "event: location" in text
    assert '"id":' not in text and "driver_id" not in text


def test_stream_missing_state_without_location(app, client):
    from app.transport.models import BookingStatus
    owner = _seed_owner(app)
    driver_id, _ = _seed_driver(app)
    _, ref = _seed_booking(app, owner, BookingStatus.ASSIGNED, driver_id)
    _rider_client(app, client, owner)
    resp = client.get(_stream_url(ref))
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert '"status": "missing"' in body
    assert ref in body


def test_stream_stale_snapshot_marks_stale(app, client, monkeypatch):
    import app.transport.services.tracking_service as ts_mod
    from app.extensions import db
    from app.geo.models import LocationObservation
    from app.transport.models import BookingStatus

    fake = FakeRedis()
    monkeypatch.setattr(ts_mod, "redis_client", fake)
    monkeypatch.setattr("app.extensions.redis_client", fake)
    owner = _seed_owner(app)
    driver_id, _ = _seed_driver(app)
    _, ref = _seed_booking(app, owner, BookingStatus.DRIVER_EN_ROUTE,
                           driver_id)
    _locate(app, driver_id)
    # Age the observation everywhere the snapshot can read it: the
    # snapshot prefers Redis, so the cached entry must age too (a
    # genuinely old reading, not a refreshed one).
    old = datetime.now(timezone.utc) - timedelta(seconds=400)
    with app.app_context():
        row = LocationObservation.query.order_by(
            LocationObservation.id.desc()).first()
        row.observed_at = old
        db.session.commit()
    import json as _json
    aged = {"latitude": LAT, "longitude": LNG, "accuracy": 3.0,
            "timestamp": old.isoformat()}
    fake.store[f"transport:tracking:driver:{driver_id}"] = _json.dumps(aged)
    _rider_client(app, client, owner)
    resp = client.get(_stream_url(ref), buffered=False)
    frames = list(itertools.islice(resp.response, 2))
    text = "".join(
        f.decode("utf-8") if isinstance(f, bytes) else f for f in frames)
    resp.close()
    assert '"fresh": false' in text


def test_stream_closes_mid_stream_on_completion(app, client, monkeypatch):
    """Cancellation/completion race: the open stream stops exposing
    driver locations once the booking turns terminal."""
    import app.transport.services.tracking_service as ts_mod
    from app.extensions import db
    from app.transport.models import Booking, BookingStatus

    fake = FakeRedis()
    monkeypatch.setattr(ts_mod, "redis_client", fake)
    monkeypatch.setattr("app.extensions.redis_client", fake)
    owner = _seed_owner(app)
    driver_id, code = _seed_driver(app)
    _, ref = _seed_booking(app, owner, BookingStatus.IN_PROGRESS, driver_id)
    _locate(app, driver_id)

    fired = {"done": False}

    real_pubsub = fake.pubsub

    def hook_pubsub():
        bus = real_pubsub()
        real_get = bus.get_message

        def hooked(timeout=0.0):
            if not fired["done"]:
                fired["done"] = True
                with app.app_context():
                    booking = Booking.query.filter_by(
                        booking_reference=ref).first()
                    booking.status = BookingStatus.COMPLETED
                    db.session.commit()
            return real_get(timeout=timeout)
        bus.get_message = hooked
        return bus

    monkeypatch.setattr(fake, "pubsub", hook_pubsub)
    _rider_client(app, client, owner)
    resp = client.get(_stream_url(ref), buffered=False)
    assert resp.status_code == 200
    frames = list(itertools.islice(resp.response, 4))
    text = "".join(
        f.decode("utf-8") if isinstance(f, bytes) else f for f in frames)
    resp.close()
    assert "event: snapshot" in text
    assert '"status": "closed"' in text
    # No live driver frame escapes after the terminal transition.
    assert "event: location" not in text
    assert code in text  # snapshot still identifies the (former) driver


def test_stream_closed_on_reopen_after_release(app, client):
    from app.extensions import db
    from app.transport.models import Booking, BookingStatus

    owner = _seed_owner(app)
    driver_id, _ = _seed_driver(app)
    _, ref = _seed_booking(app, owner, BookingStatus.ASSIGNED, driver_id)
    _rider_client(app, client, owner)
    assert client.get(_stream_url(ref)).status_code == 200
    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        booking.assigned_driver_id = None
        db.session.commit()
    assert client.get(_stream_url(ref)).status_code == 404


def test_stream_degrades_truthfully(app, client, monkeypatch):
    from app.transport.models import BookingStatus
    monkeypatch.setattr("app.extensions.redis_client",
                        DeadRedis())
    owner = _seed_owner(app)
    driver_id, _ = _seed_driver(app)
    _, ref = _seed_booking(app, owner, BookingStatus.ASSIGNED, driver_id)
    _locate(app, driver_id)
    _rider_client(app, client, owner)
    resp = client.get(_stream_url(ref))
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert '"status": "degraded"' in body


def test_multi_booking_isolation(app, client):
    """Rider A + Booking A -> allowed; Rider A + Booking B -> 403."""
    from app.transport.models import BookingStatus
    owner_a = _seed_owner(app, "aa")
    owner_b = _seed_owner(app, "bb")
    driver_id, code = _seed_driver(app)
    _, ref_a = _seed_booking(app, owner_a, BookingStatus.ASSIGNED,
                             driver_id)
    _, ref_b = _seed_booking(app, owner_b, BookingStatus.ASSIGNED,
                             driver_id)
    _locate(app, driver_id)
    _rider_client(app, client, owner_a)
    assert client.get(_stream_url(ref_a)).status_code == 200
    assert client.get(_stream_url(ref_b)).status_code == 403
    assert code  # payload scoping pinned in snapshot test


# --- rider page ----------------------------------------------------------------------

def test_booking_show_offers_tracking_card_to_owner(app, client):
    from app.transport.models import BookingStatus
    owner = _seed_owner(app)
    driver_id, _ = _seed_driver(app)
    booking_id, ref = _seed_booking(app, owner, BookingStatus.ASSIGNED,
                                    driver_id)
    _locate(app, driver_id)
    _rider_client(app, client, owner)
    resp = client.get(f"/transport/rides/{ref}")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert 'id="riderMap"' in html
    assert 'id="riderLiveState"' in html
    assert "/geo/stream/booking/" in html
    assert ref in html


def test_booking_show_hides_tracking_when_untrackable(app, client):
    from app.transport.models import BookingStatus
    owner = _seed_owner(app)
    booking_id, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    _rider_client(app, client, owner)
    resp = client.get(f"/transport/rides/{ref}")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert 'id="riderMap"' not in html
    assert "/geo/stream/booking/" not in html


def test_booking_show_denies_unrelated_rider(app, authenticated_client):
    from app.transport.models import BookingStatus
    owner = _seed_owner(app)
    booking_id, ref = _seed_booking(app, owner, BookingStatus.ASSIGNED)
    resp = authenticated_client.get(f"/transport/rides/{ref}",
                                    follow_redirects=False)
    assert resp.status_code in (302, 403, 404)
