"""Rider/admin booking page split contract.

/transport/bookings/<id> (and its detail sub-pages timeline/payments/edit)
is admin-only: transport_admin_required + removed from the rider endpoint
whitelist, so riders are hard-blocked (redirect, no booking data).

Riders get /transport/rides/<booking_reference> instead — keyed by the
public reference only (dual-ID law): live matching view before a driver
accepts, management view (driver identity, tracking, cancel, chat
placeholder) once assigned.
"""

from app.transport.models import BookingStatus
from tests.test_geo_rider_tracking import (
    _rider_client,
    _seed_booking,
    _seed_driver,
    _seed_owner,
)


def _html(resp):
    return resp.data.decode("utf-8")


def test_rider_blocked_from_admin_booking_page(app, client):
    owner = _seed_owner(app, "blk")
    booking_id, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    _rider_client(app, client, owner)
    resp = client.get(f"/transport/bookings/{booking_id}",
                      follow_redirects=False)
    assert resp.status_code == 302, resp.status_code
    location = resp.headers.get("Location", "")
    assert "/transport/bookings/" not in location, location
    assert ref not in _html(resp)


def test_anonymous_blocked_from_admin_booking_page(app, client):
    owner = _seed_owner(app, "anon")
    booking_id, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    resp = client.get(f"/transport/bookings/{booking_id}",
                      follow_redirects=False)
    assert resp.status_code in (302, 403), resp.status_code
    assert ref not in _html(resp)


def test_rider_blocked_from_admin_detail_subpages(app, client):
    owner = _seed_owner(app, "sub")
    booking_id, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    _rider_client(app, client, owner)
    for path in (f"/transport/bookings/{booking_id}/timeline",
                 f"/transport/bookings/{booking_id}/payments",
                 f"/transport/bookings/{booking_id}/edit"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 302, f"{path} -> {resp.status_code}"
        assert "/transport/bookings/" not in resp.headers.get("Location", "")
        assert ref not in _html(resp)


def test_rider_page_matching_view(app, client):
    owner = _seed_owner(app, "match")
    booking_id, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    _rider_client(app, client, owner)
    resp = client.get(f"/transport/rides/{ref}")
    assert resp.status_code == 200, resp.status_code
    html = _html(resp)
    assert 'id="riderMatching"' in html
    assert "Finding your driver" in html
    assert "rider_matching.js" in html  # poller actually loads (block renders)
    assert "Chat with driver" in html
    assert ref in html
    # no link ever points a rider at the admin detail page
    assert 'href="/transport/bookings/' not in html


def test_rider_page_management_view_shows_driver(app, client):
    owner = _seed_owner(app, "mgmt")
    driver_id, driver_code = _seed_driver(app)
    booking_id, ref = _seed_booking(app, owner, BookingStatus.ASSIGNED,
                                    driver_id)
    _rider_client(app, client, owner)
    resp = client.get(f"/transport/rides/{ref}")
    assert resp.status_code == 200, resp.status_code
    html = _html(resp)
    assert 'id="riderMatching"' not in html
    assert "rider_matching.js" not in html  # no polling after assignment
    # The card shows the canonical display name (identity precedence:
    # profile -> username); it must carry SOME driver identity.
    with app.app_context():
        from app.extensions import db
        from app.transport.models import DriverProfile
        profile = db.session.get(DriverProfile, driver_id)
        expected_name = profile.user.display_name
    assert expected_name in html        # driver identity is on the page
    assert "Cancel Booking" not in html  # Policy A: no rider cancel post-assign
    assert 'href="/transport/bookings/' not in html


def test_rider_page_foreign_rider_denied(app, authenticated_client):
    owner = _seed_owner(app, "own")
    booking_id, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    resp = authenticated_client.get(f"/transport/rides/{ref}",
                                    follow_redirects=False)
    assert resp.status_code == 403, resp.status_code


def test_rider_page_unknown_reference_404(app, client):
    owner = _seed_owner(app, "nf")
    _seed_booking(app, owner, BookingStatus.CONFIRMED)
    _rider_client(app, client, owner)
    resp = client.get("/transport/rides/NO-SUCH-REF")
    assert resp.status_code == 404, resp.status_code


def test_rider_cancel_is_ref_keyed(app, client):
    owner = _seed_owner(app, "cxl")
    booking_id, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    _rider_client(app, client, owner)
    resp = client.post(f"/transport/rides/{ref}/cancel", json={})
    assert resp.status_code == 200, (resp.status_code, _html(resp))
    payload = resp.get_json()
    assert payload["status"] == "success", payload
    with app.app_context():
        from app.extensions import db
        from app.transport.models import Booking
        booking = db.session.get(Booking, booking_id)
        assert booking.status == BookingStatus.CANCELLED.value, booking.status


def test_rider_foreign_cancel_denied(app, authenticated_client):
    owner = _seed_owner(app, "fcxl")
    booking_id, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    resp = authenticated_client.post(f"/transport/rides/{ref}/cancel",
                                     json={})
    assert resp.status_code == 403, resp.status_code
    with app.app_context():
        from app.extensions import db
        from app.transport.models import Booking
        booking = db.session.get(Booking, booking_id)
        assert booking.status == BookingStatus.CONFIRMED.value, booking.status


def test_my_trips_links_point_at_rider_page(app, client):
    owner = _seed_owner(app, "idx")
    booking_id, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    _rider_client(app, client, owner)
    resp = client.get("/transport/bookings")
    assert resp.status_code == 200, resp.status_code
    html = _html(resp)
    assert f'/transport/rides/{ref}"' in html, html
    assert 'href="/transport/bookings/' not in html


def test_admin_detail_subpages_render_with_booking(app, admin_client):
    """F-02: admin timeline/payments/edit receive the ORM booking context
    (attribute access, .strftime, relationships, enum .value)."""
    owner = _seed_owner(app, "adm")
    booking_id, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    for path, marker in (
        (f"/transport/bookings/{booking_id}/timeline", "Timeline"),
        (f"/transport/bookings/{booking_id}/payments",
         "No payment records yet"),
        (f"/transport/bookings/{booking_id}/edit", "Edit Booking"),
    ):
        resp = admin_client.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
        html = _html(resp)
        assert ref in html, path
        assert marker in html, path
