"""DRIVER-OFFER-UX-REPAIR-1E — passenger first name on the pre-accept offer.

Contract: the driver sees WHO is requesting the ride — first name only —
sourced from the canonical transport passenger identity path:

  * another-passenger booking → first active ``TransportPassenger`` row
    (existing canonical order: created_at asc, soft-deleted/cancelled
    excluded); the booking CREATOR's identity must NOT be used;
  * account-linked passenger row without a usable name → the linked
    ``User.display_name`` first token;
  * row-less self-booking (``create_booking`` never writes a passenger
    row) → the booking creator's ``display_name`` first token.

Privacy boundary: the offer carries ``passenger {first_name}`` ONLY.
No surname ships (only the first whitespace token), no phone, no
email, no user/passenger/booking internal ids, and an email-shaped
value is never accepted as a first name. When no safe name exists the
``passenger`` key is omitted entirely and the offer itself survives
(safe degradation — 1C-6).
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db

from tests.transport.test_driver_console import (
    _enter_driver_context,
    _login,
    _make_ready,
    _seed_driver,
)
from tests.test_transport_concurrent_claim import _FakeRedis

pytestmark = pytest.mark.usefixtures("db_session")


def _seed_rider(app, display_name=None):
    """Rider user; optional canonical profile display name."""
    from app.identity.models.user import User

    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(
            username=f"rider_{uid}",
            email=f"rider_{uid}@test.example.com",
            is_active=True,
            is_verified=True,
            email_verified=True,
        )
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        if display_name:
            from app.profile.models import UserProfile

            db.session.add(UserProfile(
                user_id=user.public_id,
                full_name=display_name,
                display_name=display_name,
            ))
        db.session.commit()
        return user.id


def _make_booking(app, rider_id, passenger_count=1):
    from app.transport.models import (
        Booking,
        BookingStatus,
        ProviderType,
        ServiceType,
    )

    with app.app_context():
        booking = Booking(
            user_id=rider_id,
            booking_reference=f"PX{uuid.uuid4().hex[:8].upper()}",
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            service_subtype="comfort",
            pickup_location={
                "latitude": 0.3136,
                "longitude": 32.5811,
                "address": "Kampala Road, Kampala",
            },
            pickup_address="Kampala Road, Kampala",
            dropoff_location={
                "latitude": 0.3476,
                "longitude": 32.5825,
                "address": "Entebbe Airport",
            },
            dropoff_address="Entebbe Airport",
            pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
            passenger_count=passenger_count,
            base_price=150.0,
            currency="USD",
            estimated_distance_km=7.5,
            status=BookingStatus.CONFIRMED,
            booking_metadata={
                "vehicle_class": "comfort",
                "distance_basis": "straight_line_planner",
            },
        )
        db.session.add(booking)
        db.session.commit()
        return booking.id, booking.booking_reference


def _add_passenger(app, booking_id, **kwargs):
    from app.transport.models import Booking
    from app.transport.services.passenger_service import (
        get_passenger_service,
    )

    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        assert booking is not None
        passenger = get_passenger_service().add_passenger(booking, **kwargs)
        db.session.commit()  # service only flushes
        return passenger


def _enrich(app, ref):
    from app.transport.services.offer_service import OfferService

    with app.app_context():
        return OfferService.enrich_offer({
            "booking_reference": ref,
            "status": "offered",
            "expires_at": int(time.time()) + 300,
        })


def _offer(app, monkeypatch, ref, profile_id, vehicle_id):
    from app.transport.services.offer_service import OfferService

    monkeypatch.setattr(
        "app.transport.services.offer_service.redis_client", _FakeRedis())
    with app.app_context():
        return OfferService.create_offer(ref, profile_id, vehicle_id)


# ----------------------------------------------------------------------
# 1. + 2. Identity source: self-passenger vs another passenger
# ----------------------------------------------------------------------

class TestPassengerFirstNameSource:
    def test_self_booking_uses_creator_display_name(self, app):
        rider_id = _seed_rider(app, display_name="Ama Njeri")
        _, ref = _make_booking(app, rider_id)

        offer = _enrich(app, ref)

        assert offer["passenger"] == {"first_name": "Ama"}

    def test_other_passenger_row_beats_creator(self, app):
        rider_id = _seed_rider(app, display_name="Creator Person")
        booking_id, ref = _make_booking(app, rider_id)
        _add_passenger(app, booking_id, name="Jane Q Traveller")

        offer = _enrich(app, ref)

        assert offer["passenger"]["first_name"] == "Jane"
        blob = str(offer)
        assert "Creator" not in blob   # booking creator is NOT the passenger
        assert "Traveller" not in blob  # surname never ships

    def test_linked_passenger_without_name_uses_linked_user(self, app):
        rider_id = _seed_rider(app, display_name="Creator Person")
        linked_id = _seed_rider(app, display_name="Kofi Mensah")
        booking_id, ref = _make_booking(app, rider_id)
        _add_passenger(app, booking_id, user_id=linked_id)

        offer = _enrich(app, ref)

        assert offer["passenger"]["first_name"] == "Kofi"
        assert "Creator" not in str(offer)

    def test_nameless_passenger_omits_key_and_keeps_offer(self, app):
        rider_id = _seed_rider(app, display_name="Ama Njeri")
        booking_id, ref = _make_booking(app, rider_id)
        _add_passenger(app, booking_id, email="traveler@example.com")

        offer = _enrich(app, ref)

        # A passenger row exists but yields no safe name: the creator
        # is never substituted and no contact value leaks.
        assert "passenger" not in offer
        assert "Ama" not in str(offer)
        assert "traveler@example.com" not in str(offer)
        # The rest of the offer contract is untouched.
        assert offer["pickup"]["text"] == "Kampala Road, Kampala"
        assert offer["destination"]["text"] == "Entebbe Airport"
        assert offer["fare_estimate"]["amount"] == pytest.approx(150.0)


# ----------------------------------------------------------------------
# 3. API contract
# ----------------------------------------------------------------------

class TestPassengerFirstNameApi:
    def test_api_exposes_passenger_first_name_only(
            self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider_id = _seed_rider(app, display_name="Creator Person")
        booking_id, ref = _make_booking(app, rider_id)
        _add_passenger(app, booking_id, name="Jane Q Traveller")
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _login(client, driver)

        resp = client.get("/api/transport/drivers/me/offers")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        offers = resp.get_json()["data"]["offers"]
        assert len(offers) == 1
        assert offers[0]["passenger"] == {"first_name": "Jane"}

    def test_privacy_no_pii_or_internal_ids(self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider_id = _seed_rider(app, display_name="Creator Person")
        booking_id, ref = _make_booking(app, rider_id)
        _add_passenger(app, booking_id, name="Jane Q Traveller")
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _login(client, driver)

        resp = client.get("/api/transport/drivers/me/offers")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        offer = resp.get_json()["data"]["offers"][0]

        assert set(offer["passenger"].keys()) == {"first_name"}
        for forbidden_key in ("driver_id", "vehicle_id", "user_id",
                              "passenger_id", "booking_id"):
            assert forbidden_key not in offer
        blob = str(offer)
        for forbidden in ("phone", "email", "username", "user_id",
                          "passenger_details", "Creator", "Traveller"):
            assert forbidden not in blob


# ----------------------------------------------------------------------
# 4. UI contract
# ----------------------------------------------------------------------

class TestPassengerFirstNameCard:
    def test_card_shows_passenger_first_name(self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider_id = _seed_rider(app, display_name="Creator Person")
        booking_id, ref = _make_booking(app, rider_id)
        _add_passenger(app, booking_id, name="Jane Q Traveller")
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _enter_driver_context(client, driver)

        body = client.get(
            "/transport/driver-dashboard").data.decode("utf-8")

        assert "Passenger: Jane" in body
        assert ref in body
        assert "Accept" in body
        # First name only: no surname, no creator identity on the card.
        assert "Traveller" not in body
        assert "Creator" not in body


# ----------------------------------------------------------------------
# 6. Existing offer contract remains intact with the new field
# ----------------------------------------------------------------------

class TestExistingContractIntact:
    def test_existing_fields_remain_with_passenger_added(
            self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider_id = _seed_rider(app, display_name="Ama Njeri")
        _, ref = _make_booking(app, rider_id, passenger_count=2)
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _login(client, driver)

        resp = client.get("/api/transport/drivers/me/offers")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        offer = resp.get_json()["data"]["offers"][0]

        assert offer["booking_reference"] == ref
        assert offer["status"] == "offered"
        assert offer["pickup"]["text"] == "Kampala Road, Kampala"
        assert offer["destination"]["text"] == "Entebbe Airport"
        assert offer["fare_estimate"]["amount"] == pytest.approx(150.0)
        assert offer["fare_estimate"]["currency"] == "USD"
        assert offer["ride_class"] == "comfort"
        assert offer["service_type"] == "on_demand"
        assert offer["passenger_count"] == 2
        assert offer["distance_km"] == pytest.approx(7.5)
        assert offer["distance_basis"] == "straight_line_planner"
        assert offer["expires_at"] > int(time.time())
        assert 0 < offer["ttl_remaining"] <= 300
        assert offer["vehicle"]["license_plate"] is not None
        assert offer["vehicle"]["make"] == "Toyota"
        # Self-passenger fallback still produces the new field.
        assert offer["passenger"] == {"first_name": "Ama"}
