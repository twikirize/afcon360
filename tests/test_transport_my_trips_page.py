"""T-12 behavioral proof: My Trips page renders upcoming/past sections.

The route passes light booking dicts (S-03 get_user_bookings shape) and
splits them in Python; the template renders both sections plus an
honest empty state. The booking service is stubbed — no database rows
needed. Login uses the codebase's session-cookie pattern.

Also covers the My Trips list contract: server-side search (q forwarded
to the service, real SQL proof) and past-list pagination (Load more
chunk endpoint serves one page of the fragment).
"""
import uuid
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


def test_home_pane_serves_my_trips_fragment(client, test_user, monkeypatch):
    """Dashboard pane load of /transport/ (?_pane=1, XHR) must return the
    My Trips HTML fragment - never a full document (it is injected into
    #shellContent) and never JSON."""
    import app.transport.routes as routes_mod

    active = _ride("TR-PANE-1", "confirmed", timedelta(hours=2))
    monkeypatch.setattr(
        routes_mod, "get_booking_service", lambda: _stub_service([active])
    )
    _login_as(client, test_user)

    resp = client.get(
        "/transport/?_pane=1",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200, resp.status_code
    text = resp.get_data(as_text=True)
    assert "My Trips" in text
    assert "TR-PANE-1" in text
    assert "Upcoming" in text
    assert "<!DOCTYPE" not in text
    assert "<html" not in text.lower()


def test_bookings_pane_returns_fragment_not_json(client, test_user, monkeypatch):
    """/transport/bookings?_pane=1 must return the HTML fragment even for
    an XHR caller; without the _pane branch _json_or_template would hand
    the dashboard shell raw JSON to inject."""
    import app.transport.routes as routes_mod

    active = _ride("TR-PANE-2", "assigned", timedelta(hours=1))
    monkeypatch.setattr(
        routes_mod, "get_booking_service", lambda: _stub_service([active])
    )
    _login_as(client, test_user)

    resp = client.get(
        "/transport/bookings?_pane=1",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200, resp.status_code
    text = resp.get_data(as_text=True)
    assert "TR-PANE-2" in text
    assert '"status"' not in text[:80]
    assert "<!DOCTYPE" not in text


def test_past_list_paginates_with_load_more(client, test_user, monkeypatch):
    """Past trips render one page at a time (10/page) with a Load more
    button carrying the next page number; later pages render only their
    own slice. The pane chunk endpoint (?_pane=1&page=N) serves the same
    fragment so the client can append without a full reload."""
    import app.transport.routes as routes_mod

    base = datetime.now(timezone.utc)
    past = []
    for i in range(1, 26):
        ride = _ride(f"TR-P-{i:02d}", "completed", timedelta(days=-i - 1))
        # Deterministic newest-first order: TR-P-01 newest … TR-P-25 oldest.
        ride["created_at"] = (base - timedelta(minutes=i)).isoformat()
        past.append(ride)
    monkeypatch.setattr(
        routes_mod, "get_booking_service", lambda: _stub_service(past)
    )
    _login_as(client, test_user)

    resp = client.get("/transport/bookings")
    assert resp.status_code == 200, resp.status_code
    text = resp.get_data(as_text=True)
    assert "TR-P-01" in text
    assert "TR-P-10" in text
    assert "TR-P-11" not in text
    assert 'data-page="1"' in text
    assert "Load more past trips" in text
    assert 'data-next-page="2"' in text
    assert "Showing 10 of 25 past trips" in text

    resp3 = client.get("/transport/bookings?page=3")
    text3 = resp3.get_data(as_text=True)
    assert "TR-P-21" in text3
    assert "TR-P-25" in text3
    assert "TR-P-01" not in text3
    assert "Load more past trips" not in text3

    chunk = client.get(
        "/transport/bookings?_pane=1&page=2",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert chunk.status_code == 200, chunk.status_code
    chunk_text = chunk.get_data(as_text=True)
    assert "TR-P-11" in chunk_text
    assert "TR-P-20" in chunk_text
    assert "TR-P-01" not in chunk_text
    assert "<!DOCTYPE" not in chunk_text


def test_search_passes_q_to_service_and_renders_no_results_state(
    client, test_user, monkeypatch
):
    """q from the search box reaches get_user_bookings as a kwarg, and a
    no-match search renders the dedicated empty state (not the generic
    'No trips yet')."""
    import app.transport.routes as routes_mod

    svc = _stub_service([])
    monkeypatch.setattr(routes_mod, "get_booking_service", lambda: svc)
    _login_as(client, test_user)

    resp = client.get("/transport/bookings", query_string={"q": "Nakawa"})
    assert resp.status_code == 200, resp.status_code
    text = resp.get_data(as_text=True)
    assert "No trips match" in text
    assert 'value="Nakawa"' in text
    assert "No trips yet" not in text

    svc.get_user_bookings.assert_called_once()
    _, kwargs = svc.get_user_bookings.call_args
    assert kwargs.get("q") == "Nakawa"


def test_search_filters_real_booking_rows(client, test_user):
    """Server-side search proof against the real SQL path: only bookings
    whose pickup address text matches q are rendered, per user scope."""
    from app.extensions import db
    from app.transport.models import (
        Booking,
        BookingStatus,
        ProviderType,
        ServiceType,
    )

    uid = db.session.merge(test_user).id
    db.session.rollback()

    ref_n = f"TB{uuid.uuid4().hex[:10].upper()}"
    ref_e = f"TB{uuid.uuid4().hex[:10].upper()}"

    def _row(address, ref):
        return Booking(
            user_id=uid,
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            pickup_location={
                "latitude": 0.3,
                "longitude": 32.6,
                "address": address,
            },
            dropoff_location={
                "latitude": 0.4,
                "longitude": 32.7,
                "address": "Dropoff",
            },
            pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
            passenger_count=2,
            base_price=100.00,
            currency="USD",
            status=BookingStatus.CONFIRMED,
            booking_reference=ref,
        )

    db.session.add_all(
        [
            _row("Nakawa Central Stage", ref_n),
            _row("Entebbe Ring Road", ref_e),
        ]
    )
    db.session.commit()
    _login_as(client, test_user)

    resp = client.get("/transport/bookings", query_string={"q": "Nakawa"})
    assert resp.status_code == 200, resp.status_code
    text = resp.get_data(as_text=True)
    assert ref_n in text
    assert ref_e not in text

    resp2 = client.get("/transport/bookings", query_string={"q": "Entebbe"})
    assert resp2.status_code == 200, resp2.status_code
    text2 = resp2.get_data(as_text=True)
    assert ref_e in text2
    assert ref_n not in text2


def test_trip_fare_and_time_render_human_readable(
    client, test_user, monkeypatch
):
    """SMALL-01 (P6 + J1): trip rows render fares at two-decimal precision
    and ISO pickup strings through the human-readable datetime convention
    (no raw '35.1' fare, no raw ISO timestamp)."""
    import app.transport.routes as routes_mod

    when = datetime(2026, 9, 28, 9, 20, tzinfo=timezone.utc)
    ride = _ride("TR-FMT-1", "completed", timedelta(days=-1), price=35.10)
    ride["pickup_time"] = when.isoformat()
    monkeypatch.setattr(
        routes_mod, "get_booking_service", lambda: _stub_service([ride])
    )
    _login_as(client, test_user)

    resp = client.get("/transport/bookings")
    assert resp.status_code == 200, resp.status_code
    text = resp.get_data(as_text=True)
    assert "35.10 USD" in text
    assert when.strftime("%d %b %Y, %H:%M") in text
    assert when.isoformat() not in text


def test_trip_fare_value_matrix(client, test_user, monkeypatch):
    """SMALL-01 verification (P6): 0 renders 0.00 (a real zero, not a
    fallback), numeric strings format, and None renders the panel's
    unavailable placeholder — never a fabricated 0.00."""
    import app.transport.routes as routes_mod

    def _priced(ref, price):
        ride = _ride(ref, "completed", timedelta(days=-1), price=price)
        return ride

    rides = [
        _priced("TR-FMT-ZERO", 0),
        _priced("TR-FMT-STR", "35.10"),
        _priced("TR-FMT-NONE", None),
    ]
    monkeypatch.setattr(
        routes_mod, "get_booking_service", lambda: _stub_service(rides)
    )
    _login_as(client, test_user)

    resp = client.get("/transport/bookings")
    assert resp.status_code == 200, resp.status_code
    text = resp.get_data(as_text=True)
    assert "0.00 USD" in text
    assert "35.10 USD" in text
    assert "TR-FMT-NONE" in text
    assert '<span class="td-mono">—</span>' in text
