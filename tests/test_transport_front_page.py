"""
Focused smoke tests for the Transport front page (GET /transport/).

Verifies the Stage 5T front-page correction:
- The page renders (200, not 500).
- No fabricated fares, fake driver-matching simulation, or dead href="#" links.
- Ride/service cards are sourced from the canonical ServiceType enum.
- Recent Rides are user-scoped only (anonymous visitors get an honest login CTA
  and a truthful empty state instead of made-up rides).
- The pane variant (?_pane=1) also renders without broken links.

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
    """Anonymous GET /transport/ must render 200 with truthful empty state."""
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

    # Real canonical service types rendered (from ServiceType enum)
    assert "Stadium Shuttle" in body
    assert "Airport Arrival" in body
    assert "City Tour" in body

    # Honest empty state for anonymous
    assert "Log in to view your rides" in body


def test_transport_front_page_no_fake_rating_or_stats(anonymous_client):
    """The stats must be honest — no fabricated 4.8 rating / total rides."""
    resp = anonymous_client.get("/transport/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "4.8" not in body
    # Total rides stat must not be a fabricated "12"
    assert 'stat-number">12<' not in body


def test_transport_front_page_services_come_from_enum(anonymous_client):
    """Service cards must be the 8 canonical ServiceType options."""
    resp = anonymous_client.get("/transport/")
    body = resp.get_data(as_text=True)
    for name in (
        "Airport Arrival",
        "Airport Departure",
        "Stadium Shuttle",
        "Hotel Transfer",
        "City Tour",
        "On-Demand Ride",
        "Scheduled Route",
        "Custom Tour",
    ):
        assert name in body, f"Missing canonical service card: {name}"


def test_transport_front_page_pane_renders(anonymous_client):
    """Pane variant must render 200 without dead links or fabricated data."""
    resp = anonymous_client.get("/transport/?_pane=1")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    body = resp.get_data(as_text=True)
    assert 'href="#"' not in body
    assert "UGX 15,000" not in body
    assert "Driver Found" not in body
    assert "Log in to Book" in body or "Continue Booking" in body


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


def test_transport_bookings_new_requires_login(anonymous_client):
    """Anonymous Book button target (bookings_new) is login-gated."""
    resp = anonymous_client.get("/transport/bookings/new", follow_redirects=False)
    assert resp.status_code in (301, 302), f"Expected login redirect, got {resp.status_code}"


def test_transport_front_page_book_flow_prefills_booking_form(anonymous_client, db_session):
    """Authenticated Book action prefills the canonical booking form."""
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
        "/transport/bookings/new",
        query_string={
            "pickup_location": "Nile Independence Stadium",
            "dropoff_location": "Entebbe International Airport",
            "service_type": "stadium_shuttle",
        },
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    body = resp.get_data(as_text=True)
    assert 'value="Nile Independence Stadium"' in body
    assert 'value="Entebbe International Airport"' in body
    # Stadium Shuttle is pre-selected.
    assert 'value="stadium_shuttle" selected' in body


def test_transport_front_page_recent_rides_are_user_scoped(anonymous_client, db_session):
    """A logged-in user must see only their own recent rides (not another's)."""
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

    # The user sees their own ride location and once (recent rides loop).
    assert my_note in body
    assert body.count(my_note) >= 1
    # The other user's pickup is NOT leaked.
    assert other_note not in body
    # Ride History (bookings index) is present for authenticated users.
    assert "Ride History" in body
