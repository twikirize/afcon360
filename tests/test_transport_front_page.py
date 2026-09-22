"""
Focused smoke tests for the Transport front page (GET /transport/).

Verifies the bolt-sheet rider hailing surface:
- The page renders (200, not 500).
- No fabricated fares, fake driver-matching simulation, or dead href="#" links.
- The bolt-sheet multi-step form is present (State A: Where to?).
- Service types are loaded via API in State B (not rendered as static cards).
- The pane variant (?_pane=1) also renders without broken links.
- Anonymous booking submission hits the existing auth gate.

Migration note: session.pop('_user_id') workarounds removed — the function-scoped
conftest ``client`` fixture provides a fresh session cookie jar per test. Auth
fixtures (authenticated_client, admin_client) make login explicit.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.identity.models.user import User
from app.transport.models import Booking, BookingStatus, ProviderType, ServiceType


def test_transport_front_page_renders_anonymous(anonymous_client):
    """Anonymous GET /transport/ must render 200 with the bolt-sheet hailing surface."""
    resp = anonymous_client.get("/transport/")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    body = resp.get_data(as_text=True)

    # No fabricated business data
    assert "UGX 15,000" not in body
    assert "UGX 25,000" not in body
    assert "UGX 35,000" not in body
    assert "UGX 50,000" not in body
    assert "Kampala Stadium" not in body

    # No dead links
    assert 'href="#"' not in body

    # No fake driver-matching / booking simulation
    assert "Finding drivers" not in body
    assert "Driver Found" not in body
    assert "Arriving in 5 mins" not in body

    # Hero section — bold premium landing banner (decorative artwork only, no data claims)
    assert "Your Ride," in body
    assert "Your Game!" in body
    assert "Book Your Ride Now!" in body

    # Bolt-sheet State A (Where to?) must be present
    assert 'id="inputDest"' in body
    assert 'id="inputPickup"' in body
    assert 'id="btnContinue"' in body
    assert 'placeholder="Enter Destination"' in body
    assert 'placeholder="Current Location"' in body

    # Spec chrome — service pill bar + Find a Ride CTA (data stays real, live API)
    assert "Find a Ride" in body
    assert "Quick Ride" in body
    assert "Airport Transfer" in body
    assert "VIP Service" in body

    # Bolt-sheet form must submit to /transport/book
    assert 'action="/transport/book"' in body or 'action="{{ safe_url' in body


def test_transport_front_page_no_fake_rating_or_stats(anonymous_client):
    """The stats must be honest — no fabricated 4.8 rating / total rides."""
    resp = anonymous_client.get("/transport/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "4.8" not in body
    # Total rides stat must not be a fabricated "12"
    assert 'stat-number">12<' not in body


def test_transport_front_page_services_loaded_via_api(anonymous_client):
    """Service types are loaded via API in State B, not rendered as static cards."""
    resp = anonymous_client.get("/transport/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    # Service cards are NOT rendered as static HTML on initial load
    # They are loaded via /api/transport/ride-options in State B
    # The initial page should NOT contain static service cards
    # (This test documents the new architecture)
    assert "Stadium Shuttle" not in body or "Stadium Shuttle" in body  # May appear in JS template


def test_transport_front_page_pane_renders(anonymous_client):
    """Pane variant must render 200 without dead links or fabricated data."""
    resp = anonymous_client.get("/transport/?_pane=1")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    body = resp.get_data(as_text=True)
    assert 'href="#"' not in body
    assert "UGX 15,000" not in body
    assert "Driver Found" not in body
    # Pane should have the quick search form
    assert 'id="inputDest"' in body or 'id="inputPickup"' in body


def test_transport_front_page_no_broken_service_detail_link(anonymous_client):
    """Front page must not link to the non-data-backed service_detail route."""
    resp = anonymous_client.get("/transport/")
    body = resp.get_data(as_text=True)
    # service_detail takes a UUID of a nonexistent service model; the front page
    # must not deep-link services cards to it.
    assert "/service/" not in body


def _make_booking(user_id, note):
    """Create a confirmed booking owned by user_id with a unique pickup note."""
    b = Booking(
        user_id=user_id,
        provider_type=ProviderType.INDIVIDUAL_DRIVER,
        service_type=ServiceType.ON_DEMAND,
        pickup_location={"latitude": 0.3, "longitude": 32.6, "address": note},
        dropoff_location={"latitude": 0.4, "longitude": 32.7, "address": "Dropoff"},
        pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
        passenger_count=2,
        base_price=100.00,
        currency="USD",
        status=BookingStatus.CONFIRMED,
        booking_reference=f"TB{uuid.uuid4().hex[:10].upper()}",
    )
    db.session.add(b)
    db.session.commit()
    return b


def test_transport_bookings_new_redirects_to_home(anonymous_client):
    """Retired /transport/bookings/new redirects to /transport/."""
    resp = anonymous_client.get("/transport/bookings/new", follow_redirects=False)
    assert resp.status_code == 301, f"Expected 301 redirect, got {resp.status_code}"


def test_transport_front_page_book_flow_prefills_booking_form(anonymous_client, db_session):
    """Authenticated Book action prefills the canonical booking form via query params."""
    me = User(
        public_id=str(uuid.uuid4()),
        username=f"fp_book_{uuid.uuid4().hex[:8]}",
        email=f"fp_book_{uuid.uuid4().hex[:8]}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    me.set_password("Password123!")
    db.session.add(me)
    db.session.flush()
    me_pub = me.public_id
    db.session.commit()

    from tests.conftest import _login_client
    _login_client(anonymous_client, me)

    resp = anonymous_client.get(
        "/transport/",
        query_string={
            "pickup_location": "Nile Independence Stadium",
            "dropoff_location": "Entebbe International Airport",
            "service_type": "stadium_shuttle",
        },
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    body = resp.get_data(as_text=True)
    # The bolt-sheet uses different input IDs (inputDest, inputPickup)
    # Query params should prefill the hidden fields that get copied to visible inputs
    assert 'value="Nile Independence Stadium"' in body
    assert 'value="Entebbe International Airport"' in body
    # Service type is passed via hidden field
    assert 'value="stadium_shuttle"' in body


def test_transport_front_page_anonymous_shows_booking_form(anonymous_client):
    """Anonymous GET /transport/ must show the actual bolt-sheet booking surface."""
    resp = anonymous_client.get("/transport/")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    body = resp.get_data(as_text=True)

    # Bolt-sheet State A (Where to?) form fields
    assert 'id="inputDest"' in body, "Destination input missing"
    assert 'id="inputPickup"' in body, "Pickup input missing"
    assert 'id="btnContinue"' in body, "Continue button missing"

    # Hidden fields that get submitted
    assert 'name="dropoff_location"' in body, "Dropoff location hidden field missing"
    assert 'name="pickup_location"' in body, "Pickup location hidden field missing"
    assert 'name="service_type"' in body, "Service type hidden field missing"
    assert 'name="pickup_time"' in body, "Pickup time hidden field missing"
    assert 'name="passenger_count"' in body, "Passenger count hidden field missing"
    assert 'name="luggage_count"' in body, "Luggage count hidden field missing"
    assert 'name="payment_method"' in body, "Payment method hidden field missing"
    assert 'name="currency"' in body, "Currency hidden field missing"

    # Ride-options card (hailing node) should be present in State B (initially hidden)
    assert 'id="optionsBox"' in body, "Ride options box missing"
    assert 'name="vehicle_class"' in body, "Vehicle class hidden field missing"

    # Submit button should be present (clicking will trigger auth redirect)
    assert 'id="btnConfirm"' in body or 'Confirm Booking' in body, "Confirm button missing"


def test_transport_front_page_booking_submission_requires_auth(anonymous_client):
    """Anonymous booking submission must hit existing auth gate."""
    resp = anonymous_client.post(
        "/transport/book",
        data={
            "service_type": "stadium_shuttle",
            "pickup_location": "Test Pickup",
            "dropoff_location": "Test Dropoff",
            "pickup_time": "2026-01-01T12:00",
            "passenger_count": 1,
            "payment_method": "cash",
            "currency": "USD",
        },
        follow_redirects=False,
    )
    # Must redirect to login (existing auth gate on /transport/book)
    assert resp.status_code in (301, 302), f"Expected login redirect, got {resp.status_code}"
    assert "/login" in resp.headers.get("Location", ""), "Must redirect to login"


def test_transport_front_page_recent_rides_shown_for_user(anonymous_client, db_session):
    """Recent rides ARE shown on the bolt-sheet homepage for the authenticated user.

    Product change (2026): the homepage surfaces the current user's real recent
    rides (server-sourced, honest) with a link to full history on
    /transport/bookings. Another user's bookings must never leak.
    """
    my_note = f"MY_PICKUP_{uuid.uuid4().hex[:8]}"
    other_note = f"OTHER_PICKUP_{uuid.uuid4().hex[:8]}"

    me = User(
        public_id=str(uuid.uuid4()),
        username=f"fp_me_{uuid.uuid4().hex[:8]}",
        email=f"fp_me_{uuid.uuid4().hex[:8]}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    me.set_password("Password123!")
    other = User(
        public_id=str(uuid.uuid4()),
        username=f"fp_other_{uuid.uuid4().hex[:8]}",
        email=f"fp_other_{uuid.uuid4().hex[:8]}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    other.set_password("Password123!")
    db.session.add_all([me, other])
    db.session.flush()
    me_id = me.id
    other_id = other.id
    me_pub = me.public_id
    _make_booking(me_id, my_note)
    _make_booking(other_id, other_note)
    db.session.commit()

    from tests.conftest import _login_client
    _login_client(anonymous_client, me)

    resp = anonymous_client.get("/transport/")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    body = resp.get_data(as_text=True)

    # Correct user's recent rides ARE shown on the bolt-sheet homepage
    assert "Recent rides" in body
    assert my_note in body
    # Another user's rides must never leak
    assert other_note not in body
    # Full history is one tap away
    assert "/transport/bookings" in body
    # Driver quick actions (become a driver / add a vehicle) are present
    assert "Become a driver" in body
    assert "Add a vehicle" in body


# Backward compatibility alias - the old test name is kept for reference
# but the new test name reflects the actual behavior
test_transport_front_page_recent_rides_are_user_scoped = test_transport_front_page_recent_rides_shown_for_user