"""AFCON360 GEO-14 realtime location delivery - contract tests.

Proves the GEO delivery boundary (envelope / publication / SSE iteration)
plus the Transport producer hook and the admin-only SSE authorization that
mirrors the existing driver-location read surfaces. No business logic in
GEO: freshness here is geographic recency only.

Coordinate order is latitude-first everywhere; the suite pins an
asymmetric point so a lat/lng swap fails loudly.
"""

import itertools
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.geo.realtime import (
    CHANNEL_PREFIX,
    ENTITY_TYPES,
    EVENT_LOCATION_UPDATED,
    EVENT_VERSION,
    build_location_event,
    format_sse,
    iter_location_events,
    location_channel,
    parse_location_event,
    publish_location_event,
)
from app.utils.exceptions import ValidationError

LAT, LNG = 0.3136, 32.5811  # asymmetric Kampala point (swap-detecting)


def _location(ts=None, **over):
    payload = {"latitude": LAT, "longitude": LNG, "accuracy": 5.0,
               "timestamp": (ts or datetime.now(timezone.utc)).isoformat()}
    payload.update(over)
    return payload


# --- envelope -------------------------------------------------------------

def test_envelope_carries_public_ref_and_lat_first_coords():
    event = build_location_event("driver", "DRV-ABC123", _location())
    assert event["version"] == EVENT_VERSION
    assert event["event"] == EVENT_LOCATION_UPDATED
    assert event["entity_type"] == "driver"
    assert event["public_ref"] == "DRV-ABC123"
    assert (event["latitude"], event["longitude"]) == (LAT, LNG)
    assert event["fresh"] is True
    assert event["observed_at"]


def test_envelope_marks_stale_reading_without_refreshing_it():
    old = datetime.now(timezone.utc) - timedelta(seconds=400)
    event = build_location_event("driver", "DRV-ABC123", _location(ts=old))
    assert event["fresh"] is False
    assert event["age_s"] == pytest.approx(400, abs=5)
    # observed_at stays the original reading - never "now"
    assert event["observed_at"] == old.isoformat()


def test_envelope_rejects_invalid_coordinates():
    with pytest.raises(ValidationError):
        build_location_event("driver", "DRV-ABC123",
                             _location(latitude=999.0))
    with pytest.raises(ValidationError):
        build_location_event("driver", "DRV-ABC123", {"latitude": LAT})


def test_envelope_rejects_bad_scope():
    with pytest.raises(ValueError):
        build_location_event("rider", "DRV-ABC123", _location())
    with pytest.raises(ValueError):
        build_location_event("driver", "  ", _location())


def test_envelope_exposes_no_internal_ids():
    blob = json.dumps(build_location_event("driver", "DRV-ABC123",
                                           _location()))
    assert "driver_id" not in blob
    assert '"id"' not in blob


def test_channel_is_scoped_per_entity():
    assert location_channel("driver", "DRV-ABC123") == (
        f"{CHANNEL_PREFIX}:driver:DRV-ABC123")
    assert location_channel("vehicle", "UBA-1") != (
        location_channel("driver", "UBA-1"))


# --- parsing (never raises, never fabricates) ------------------------------

def test_parse_round_trip():
    event = build_location_event("vehicle", "UBA-007", _location())
    parsed = parse_location_event(json.dumps(event).encode("utf-8"))
    assert parsed is not None
    assert (parsed["latitude"], parsed["longitude"]) == (LAT, LNG)
    assert parsed["public_ref"] == "UBA-007"
    assert parsed["fresh"] is True


@pytest.mark.parametrize("raw", [
    b"not json at all {{{",
    json.dumps({"version": 999, "event": EVENT_LOCATION_UPDATED}),
    json.dumps({"version": 1, "event": "something.else"}),
    # redis subscribe-confirmation shape
    {"type": "subscribe", "channel": b"x", "data": 1},
    ["a", "list"],
    None,
    42,
    json.dumps({"version": 1, "event": EVENT_LOCATION_UPDATED,
                "entity_type": "driver", "public_ref": "D",
                "latitude": 91.0, "longitude": 0.0,
                "observed_at": "2026-01-01T00:00:00+00:00",
                "age_s": 1.0, "fresh": True}),
    json.dumps({"version": 1, "event": EVENT_LOCATION_UPDATED,
                "entity_type": "driver", "public_ref": "",
                "latitude": LAT, "longitude": LNG,
                "observed_at": "2026-01-01T00:00:00+00:00",
                "age_s": 1.0, "fresh": True}),
    json.dumps({"version": 1, "event": EVENT_LOCATION_UPDATED,
                "entity_type": "driver", "public_ref": "D",
                "latitude": LAT, "longitude": LNG,
                "observed_at": "", "age_s": 1.0, "fresh": "yes"}),
])
def test_parse_rejects_malformed(raw):
    assert parse_location_event(raw) is None


# --- publication (best-effort) ----------------------------------------------

class FakePubSub:
    """Raw payload queue for the iterator contract."""

    def __init__(self, messages):
        self._messages = list(messages)

    def get_message(self, timeout=0.0):
        # Raw payloads only (mirrors the view's _next_channel_payload,
        # which unwraps pub/sub frames before this layer sees them).
        if not self._messages:
            return None
        return self._messages.pop(0)


class FakeChannelBus:
    """Channel queues fed by FakeRedis.publish (in-process pub/sub)."""

    def __init__(self, channels):
        self._channels = channels
        self._subscribed = []

    def subscribe(self, channel):
        self._subscribed.append(channel)

    def get_message(self, timeout=0.0):
        for channel in self._subscribed:
            queue = self._channels.get(channel, [])
            if queue:
                return {"type": "message", "channel": channel,
                        "data": queue.pop(0)}
        return None


class FakeRedis:
    def __init__(self):
        self.published = []
        self.store = {}
        self.channels = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def publish(self, channel, message):
        self.published.append((channel, message))
        self.channels.setdefault(channel, []).append(message)
        return 1

    def pubsub(self):
        return FakeChannelBus(self.channels)


class DeadRedis:
    def setex(self, *a, **k):
        raise RuntimeError("redis down")

    def get(self, *a, **k):
        raise RuntimeError("redis down")

    def publish(self, *a, **k):
        raise RuntimeError("redis down")

    def pubsub(self, *a, **k):
        raise RuntimeError("redis down")


def test_publish_returns_true_and_scopes_channel():
    fake = FakeRedis()
    event = build_location_event("driver", "DRV-ABC123", _location())
    assert publish_location_event(fake, "driver", "DRV-ABC123", event) is True
    assert len(fake.published) == 1
    channel, message = fake.published[0]
    assert channel == location_channel("driver", "DRV-ABC123")
    assert json.loads(message)["public_ref"] == "DRV-ABC123"


def test_publish_never_raises_when_redis_down():
    event = build_location_event("driver", "DRV-ABC123", _location())
    assert publish_location_event(DeadRedis(), "driver", "DRV-ABC123",
                                  event) is False


# --- SSE iteration -----------------------------------------------------------

def test_stream_snapshot_then_live_then_heartbeat():
    # Raw channel payloads (the view unwraps pub/sub frames first;
    # subscribe-confirmations never reach this layer - parse rejects them).
    live = json.dumps(build_location_event("driver", "D1", _location()))
    frames = list(itertools.islice(
        iter_location_events(
            FakePubSub([live, None, live]).get_message,
            snapshot_event=build_location_event("driver", "D1",
                                                _location())),
        5))
    assert frames[0].startswith("retry: ")
    assert frames[1].startswith("event: snapshot\n")
    assert frames[2].startswith("event: location\n")
    assert frames[3] == ": heartbeat\n\n"
    assert frames[4].startswith("event: location\n")


def test_format_sse_frame_shape():
    frame = format_sse("snapshot", {"a": 1})
    assert frame.startswith("event: snapshot\ndata: ")
    assert frame.endswith("\n\n")
    assert frame.count("\n") == 3


# --- producer hook ------------------------------------------------------------

def _seed_driver_with_user(app):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import (ComplianceStatus, DriverProfile,
                                      VerificationTier)
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"rt_{uid}",
                    email=f"rt_{uid}@test.example.com", is_active=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        profile = DriverProfile(
            user_id=user.id, driver_code=f"RT-{uid[:6].upper()}",
            verification_tier=VerificationTier.PENDING,
            compliance_status=ComplianceStatus.PENDING_REVIEW,
            is_active=True, is_online=True, is_available=True,
            max_passenger_capacity=4, vehicle_classes=["comfort"])
        db.session.add(profile)
        db.session.commit()
        return profile.id, profile.driver_code


def test_update_location_publishes_scoped_event(app, monkeypatch):
    import app.transport.services.tracking_service as ts_mod
    from app.transport.services.tracking_service import TrackingService

    fake = FakeRedis()
    monkeypatch.setattr(ts_mod, "redis_client", fake)
    driver_id, driver_code = _seed_driver_with_user(app)
    with app.app_context():
        result = TrackingService.update_location("driver", driver_id, {
            "latitude": LAT, "longitude": LNG, "accuracy": 3.0})
    assert result["success"] is True
    assert len(fake.published) == 1
    channel, message = fake.published[0]
    assert channel == location_channel("driver", driver_code)
    payload = json.loads(message)
    assert (payload["latitude"], payload["longitude"]) == (LAT, LNG)
    assert payload["public_ref"] == driver_code


def test_update_location_succeeds_when_redis_down(app, monkeypatch):
    import app.transport.services.tracking_service as ts_mod
    from app.transport.services.tracking_service import TrackingService

    monkeypatch.setattr(ts_mod, "redis_client", DeadRedis())
    driver_id, _ = _seed_driver_with_user(app)
    with app.app_context():
        result = TrackingService.update_location("driver", driver_id, {
            "latitude": LAT, "longitude": LNG})
    # persisted state stays authoritative even with no live push
    assert result["success"] is True


# --- SSE view ------------------------------------------------------------------

def _stream_url(entity_type, public_ref):
    return f"/geo/stream/location/{entity_type}/{public_ref}"


def test_stream_redirects_anonymous_to_login(app, anonymous_client):
    # NOTE: never combine anonymous + authenticated clients in one test:
    # both fixtures share the same function-scoped `client`, so the
    # "anonymous" request would inherit the login session (gotcha found
    # during GEO-14: anon read 403 instead of 302 until split).
    resp = anonymous_client.get(_stream_url("driver", "DRV-X"),
                                follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_stream_denies_non_admin(app, authenticated_client):
    resp = authenticated_client.get(_stream_url("driver", "DRV-X"),
                                    follow_redirects=False)
    assert resp.status_code == 403


def test_stream_404_on_unknown_scope_or_ref(app, admin_client):
    assert admin_client.get(_stream_url("rider", "DRV-X")).status_code == 404
    assert admin_client.get(
        _stream_url("driver", "NO-SUCH-DRIVER")).status_code == 404


def test_stream_missing_state_when_no_location(app, admin_client):
    driver_id, driver_code = _seed_driver_with_user(app)
    assert driver_id is not None
    resp = admin_client.get(_stream_url("driver", driver_code))
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    body = resp.data.decode("utf-8")
    assert "event: state" in body
    assert '"status": "missing"' in body
    assert driver_code in body


def test_stream_snapshot_then_live_event(app, admin_client, monkeypatch):
    import app.transport.services.tracking_service as ts_mod
    from app.transport.services.tracking_service import TrackingService

    # Same in-process bus for producer and stream: proves
    # publish -> channel -> SSE end to end.
    fake = FakeRedis()
    monkeypatch.setattr(ts_mod, "redis_client", fake)
    monkeypatch.setattr("app.extensions.redis_client", fake)
    driver_id, driver_code = _seed_driver_with_user(app)
    with app.app_context():
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT, "longitude": LNG})

    resp = admin_client.get(_stream_url("driver", driver_code),
                            buffered=False)
    assert resp.status_code == 200
    frames = list(itertools.islice(resp.response, 3))
    text = "".join(
        f.decode("utf-8") if isinstance(f, bytes) else f for f in frames)
    resp.close()
    assert "event: snapshot" in text
    assert driver_code in text
    assert str(LAT) in text and str(LNG) in text
    assert "event: location" in text


def test_stream_degrades_truthfully_when_channel_down(app, admin_client,
                                                      monkeypatch):
    monkeypatch.setattr("app.extensions.redis_client", DeadRedis())
    driver_id, driver_code = _seed_driver_with_user(app)
    assert driver_id is not None
    resp = admin_client.get(_stream_url("driver", driver_code))
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert '"status": "degraded"' in body
    assert "snapshot only" in body


# --- CASE C consumer repair ------------------------------------------------------

def test_drivers_location_page_renders_driver(app, admin_client):
    """GEO-14 CASE C: the route previously 500'd ('driver' undefined)."""
    from app.extensions import db
    from app.transport.models import DriverProfile

    driver_id, driver_code = _seed_driver_with_user(app)
    with app.app_context():
        driver = db.session.get(DriverProfile, driver_id)
        driver.last_location = {"latitude": LAT, "longitude": LNG,
                                "accuracy": 5.0}
        db.session.commit()
    resp = admin_client.get(f"/transport/drivers/{driver_id}/location")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert driver_code in html
    assert "driverMap" in html
    assert "geo-realtime.js" in html
    # stream URL is assembled in JS (encodeURIComponent), so pin both parts
    assert "/geo/stream/location/driver/" in html
    assert driver_code in html
