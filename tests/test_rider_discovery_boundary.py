"""Rider discovery/commitment boundary — focused contract tests.

Discovery (anonymous-or-authenticated) vs commitment (authenticated):

  * GET /geo/api/geocode is anonymous (public candidates only);
  * POST /api/transport/ride-options is anonymous (already was);
  * POST /api/transport/fare/estimate still requires auth (not on the
    rider journey path; unchanged);
  * POST /transport/book while anonymous redirects to login (302) and
    creates NO booking row;
  * booking creation still assigns the server-side authenticated rider.

CSRF is disabled in the test app (conftest); the anonymous page renders
a token in production via the ungated context processor. No DB schema,
no provider changes, no UI changes in this file.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

GEO_URL = "/geo/api/geocode"


class _PhotonHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [32.5813539, 0.3177137]},
                "properties": {"name": "Kampala", "city": "Kampala",
                               "country": "Uganda"},
            }],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def boundary_photon():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PhotonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture()
def discovery_env(monkeypatch, boundary_photon):
    """Hermetic provider wiring regardless of operator .env."""
    monkeypatch.setenv("GEO_PHOTON_URL", boundary_photon)
    monkeypatch.setenv("GEO_PHOTON_ENABLED", "true")
    monkeypatch.setenv("GEOAPIFY_ENABLED", "false")
    monkeypatch.setenv("GEOAPIFY_API_KEY", "")


def test_anonymous_geocode_returns_public_candidates(
        anonymous_client, discovery_env):
    """Discovery: anonymous search resolves with no login redirect."""
    resp = anonymous_client.get(GEO_URL, query_string={"q": "Kampala"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "photon"
    assert payload["results"] != []
    blob = json.dumps(payload)
    assert "GEOAPIFY_API_KEY" not in blob


def test_anonymous_ride_options_reachable(anonymous_client):
    """Discovery: the options endpoint answers anonymous callers (no
    401/302). Fleet-dependent option ROWS are proven live in the browser
    with a seeded driver; this contract asserts reachability only, so it
    never depends on ambient fleet state."""
    resp = anonymous_client.post(
        "/api/transport/ride-options",
        json={"service_type": "on_demand", "currency": "USD",
              "pickup_latitude": 0.3136, "pickup_longitude": 32.5811,
              "dropoff_latitude": 0.3476, "dropoff_longitude": 32.5825},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert isinstance(payload["data"]["options"], list)


def test_anonymous_fare_estimate_still_requires_auth(anonymous_client):
    """Fare estimate keeps its existing auth gate (unchanged behavior)."""
    resp = anonymous_client.post(
        "/api/transport/fare/estimate",
        json={"service_type": "on_demand", "vehicle_class": "comfort",
              "currency": "USD", "estimated_distance_km": 5.0},
    )
    assert resp.status_code == 401


def _booking_count(app, key):
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        count = Booking.query.filter_by(
            idempotency_key=key, is_deleted=False).count()
        db.session.rollback()
        return count


def _form(**over):
    data = {
        "service_type": "on_demand",
        "provider_type": "individual_driver",
        "passenger_count": "1",
        "currency": "USD",
        "pickup_time": (datetime.now(timezone.utc).isoformat()),
        "payment_method": "cash",
        "vehicle_class": "comfort",
        "pickup_location": "Nakawa Riders Pickup Point",
        "dropoff_location": "Entebbe Airside Gate",
        "pickup_latitude": "0.3136",
        "pickup_longitude": "32.5811",
        "dropoff_latitude": "0.3476",
        "dropoff_longitude": "32.5825",
        "pickup_source": "gps",
        "dropoff_source": "map",
    }
    data.update(over)
    return data


def test_anonymous_book_post_redirects_and_creates_no_row(
        app, anonymous_client):
    """Commitment: an anonymous booking POST with a complete trip
    payload is redirected to login and persists NOTHING."""
    key = f"anon-{uuid.uuid4().hex}"
    resp = anonymous_client.post(
        "/transport/book", data=_form(idempotency_key=key),
        follow_redirects=False)
    assert resp.status_code in (301, 302, 303, 308)
    assert "/login" in resp.headers.get("Location", "")
    assert _booking_count(app, key) == 0


def _promote_to_tier2(app, user_id):
    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )
    from app.extensions import db
    from app.identity.models.user import User
    with app.app_context():
        real_user = db.session.get(User, user_id)
        real_user.phone_verified = True
        real_user.phone_verified_at = datetime.now(timezone.utc)
        if not real_user.phone:
            real_user.phone = f"+2567{uuid.uuid4().hex[:7]}"
        db.session.add(
            IndividualVerification(
                user_id=user_id,
                status="verified",
                scope={"identity": True, "address": True,
                       "national_id": True, "biometric": True},
            )
        )
        db.session.commit()
    from app.auth.kyc_compliance import calculate_kyc_tier
    with app.app_context():
        info = calculate_kyc_tier(user_id)
        assert info["tier"] >= 2


def test_authenticated_booking_assigns_server_side_rider(
        app, test_user, authenticated_client):
    """Commitment: the persisted booking belongs to the authenticated
    rider derived server-side from the session — never to any
    browser-supplied identity."""
    from app.extensions import db
    with app.app_context():
        merged = db.session.merge(test_user)
        rider_id = merged.id
        db.session.rollback()
    _promote_to_tier2(app, rider_id)
    key = f"owned-{uuid.uuid4().hex}"
    resp = authenticated_client.post(
        "/transport/book", data=_form(idempotency_key=key),
        follow_redirects=False)
    assert resp.status_code in (301, 302, 303, 308)
    location = resp.headers.get("Location", "")
    assert "/transport/rides/" in location
    from app.transport.models import Booking
    with app.app_context():
        booking = Booking.query.filter_by(
            idempotency_key=key, is_deleted=False).first()
        assert booking is not None
        assert booking.user_id == rider_id
        db.session.rollback()
