"""T-12 behavioral proof: My Trips page renders upcoming/past sections.

The route passes light booking dicts (S-03 get_user_bookings shape) and
splits them in Python; the template renders both sections plus an
honest empty state. The booking service is stubbed — no database rows
needed. Login uses the codebase's session-cookie pattern.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


def _ride(ref, status, pickup_delta, price=100.00):
    when = datetime.now(timezone.utc) + pickup_delta
    return {
        "booking_id": 1000 + abs(hash(ref)) % 8000,
        "booking_reference": ref,
        "pickup_location": "Nakawa",
        "dropoff_location": "Garden City",
        "status": status,
        "pickup_time": when.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "final_price": price,
        "currency": "USD",
    }


def _stub_service(rides):
    svc = MagicMock()
    svc.get_user_bookings.return_value = rides
    return svc


def _login_as(client, user):
    from app.extensions import db

    app = client.application
    with app.app_context():
        merged = db.session.merge(user)
        pid = str(merged.public_id)
        db.session.rollback()
    with client.session_transaction() as sess:
        sess["_user_id"] = pid
        sess["_fresh"] = True
    return client


def test_populated_renders_upcoming_and_past(client, test_user, monkeypatch):
    import app.transport.routes as routes_mod

    active = _ride("TR-UPCOMING-1", "confirmed", timedelta(hours=2))
    old = _ride("TR-PAST-1", "completed", timedelta(days=-1))
    monkeypatch.setattr(
        routes_mod, "get_booking_service", lambda: _stub_service([active, old])
    )
    _login_as(client, test_user)

    resp = client.get("/transport/bookings")
    assert resp.status_code == 200, resp.status_code
    text = resp.get_data(as_text=True)
    assert "TR-UPCOMING-1" in text
    assert "TR-PAST-1" in text
    assert text.index("Upcoming") < text.index("TR-UPCOMING-1")
    assert text.index("Past") < text.index("TR-PAST-1")
    assert "Track" in text


def test_empty_renders_honest_empty_state(client, test_user, monkeypatch):
    import app.transport.routes as routes_mod

    monkeypatch.setattr(
        routes_mod, "get_booking_service", lambda: _stub_service([])
    )
    _login_as(client, test_user)

    resp = client.get("/transport/bookings")
    assert resp.status_code == 200, resp.status_code
    text = resp.get_data(as_text=True)
    assert "No trips yet" in text
    assert 'class="trip-card"' not in text
