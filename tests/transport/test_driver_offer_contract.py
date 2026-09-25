"""Driver offer visible contract (DRIVER-OFFER-UX-REPAIR-1).

Locks what a driver receives for a ride request, end to end:

  Booking (source of truth)
  -> OfferService (thin Redis lifecycle + read-time enrichment)
  -> GET /api/transport/drivers/me/offers (explicit shaped contract)
  -> driver dashboard offer card (rendered fields + honest fallbacks)
  -> new_booking driver notification (type, pointer, link, message)

Redis stays thin by design: only booking_reference / driver_id /
vehicle_id / status / expires_at are stored. Everything the driver
sees beyond that is enriched at READ time from the authoritative
Booking row, so enriched fields can never go stale in Redis and no
passenger PII ever enters transient storage.
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


def _make_rich_booking(app, rider_id, *, ref=None, coords_only=False,
                       basis="straight_line_planner"):
    """Booking with addresses, class, fare, currency and distance basis."""
    from app.transport.models import (
        Booking,
        BookingStatus,
        ProviderType,
        ServiceType,
    )

    with app.app_context():
        if coords_only:
            pickup_location = {"latitude": 0.3136, "longitude": 32.5811}
            dropoff_location = {"latitude": 0.3476, "longitude": 32.5825}
            pickup_address = None
            dropoff_address = None
        else:
            pickup_location = {
                "latitude": 0.3136,
                "longitude": 32.5811,
                "address": "Kampala Road, Kampala",
            }
            dropoff_location = {
                "latitude": 0.3476,
                "longitude": 32.5825,
                "address": "Entebbe Airport",
            }
            pickup_address = "Kampala Road, Kampala"
            dropoff_address = "Entebbe Airport"
        booking = Booking(
            user_id=rider_id,
            booking_reference=ref or f"OC{uuid.uuid4().hex[:8].upper()}",
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            service_subtype="comfort",
            pickup_location=pickup_location,
            pickup_address=pickup_address,
            dropoff_location=dropoff_location,
            dropoff_address=dropoff_address,
            pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
            passenger_count=2,
            base_price=150.0,
            currency="USD",
            estimated_distance_km=7.5,
            status=BookingStatus.CONFIRMED,
            booking_metadata={
                "vehicle_class": "comfort",
                "distance_basis": basis,
            },
        )
        db.session.add(booking)
        db.session.commit()
        return booking.id, booking.booking_reference


def _offer(app, monkeypatch, ref, profile_id, vehicle_id):
    from app.transport.services.offer_service import OfferService

    monkeypatch.setattr(
        "app.transport.services.offer_service.redis_client", _FakeRedis())
    with app.app_context():
        return OfferService.create_offer(ref, profile_id, vehicle_id)


# ----------------------------------------------------------------------
# Offer API contract
# ----------------------------------------------------------------------

class TestOfferApiContract:
    def test_enriched_fields_present(self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id)
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _login(client, driver)

        resp = client.get("/api/transport/drivers/me/offers")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        offers = resp.get_json()["data"]["offers"]
        assert len(offers) == 1
        offer = offers[0]

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

    def test_internal_ids_not_exposed(self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id)
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _login(client, driver)

        resp = client.get("/api/transport/drivers/me/offers")
        offer = resp.get_json()["data"]["offers"][0]
        assert "driver_id" not in offer
        assert "vehicle_id" not in offer
        # The public reference is the only identifier clients need:
        # polling, card actions and accept all key on booking_reference.
        assert offer["booking_reference"] == ref

    def test_forbidden_fields_absent(self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id)
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _login(client, driver)

        resp = client.get("/api/transport/drivers/me/offers")
        offer = resp.get_json()["data"]["offers"][0]
        blob = str(offer)
        for forbidden in (
            "passenger_details",
            "pickup_contact",
            "dropoff_contact",
            "phone",
            "email",
            "username",
            "organisation",
            "final_price",
            "wallet",
        ):
            assert forbidden not in offer, forbidden
            assert forbidden not in blob, forbidden
        assert "user_id" not in offer

    def test_driver_isolation(self, app, client, monkeypatch):
        driver_a = _seed_driver(app)
        vehicle_id = _make_ready(app, driver_a)
        driver_b = _seed_driver(app)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id)
        _offer(app, monkeypatch, ref, driver_a.driver_profile_id, vehicle_id)

        _login(client, driver_b)
        resp = client.get("/api/transport/drivers/me/offers")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["data"]["offers"] == []

    def test_cross_driver_vehicle_withheld(self, app, client, monkeypatch):
        from app.transport.services.offer_service import OfferService

        driver_a = _seed_driver(app)
        _make_ready(app, driver_a)
        driver_b = _seed_driver(app)
        vehicle_b = _make_ready(app, driver_b)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id)
        # Offer nominally points driver A at driver B's vehicle.
        _offer(app, monkeypatch, ref, driver_a.driver_profile_id, vehicle_b)
        _login(client, driver_a)

        resp = client.get("/api/transport/drivers/me/offers")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        offer = resp.get_json()["data"]["offers"][0]
        assert offer["vehicle"] is None
        # The request itself is still fully visible.
        assert offer["pickup"]["text"] == "Kampala Road, Kampala"

        with app.app_context():
            thin = {
                "booking_reference": ref,
                "driver_id": driver_a.driver_profile_id,
                "vehicle_id": 999999999,
                "status": "offered",
                "expires_at": int(time.time()) + 300,
            }
            assert OfferService.enrich_offer(thin)["vehicle"] is None

    def test_coords_fallback_when_no_address(self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id, coords_only=True)
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _login(client, driver)

        resp = client.get("/api/transport/drivers/me/offers")
        offer = resp.get_json()["data"]["offers"][0]
        assert offer["pickup"]["text"] == "0.3136, 32.5811"
        assert offer["destination"]["text"] == "0.3476, 32.5825"

    def test_planning_default_distance_withheld(self, app, client,
                                                monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id, basis="planning_default")
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _login(client, driver)

        resp = client.get("/api/transport/drivers/me/offers")
        offer = resp.get_json()["data"]["offers"][0]
        assert offer["distance_km"] is None


# ----------------------------------------------------------------------
# Dashboard card
# ----------------------------------------------------------------------

class TestOfferCardRenders:
    def test_card_shows_contract_fields(self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id)
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _enter_driver_context(client, driver)

        body = client.get(
            "/transport/driver-dashboard").data.decode("utf-8")
        assert "Kampala Road, Kampala" in body
        assert "Entebbe Airport" in body
        assert ref in body
        assert "2 pax" in body
        assert "Comfort" in body
        assert "Fare estimate:" in body
        assert "USD" in body
        assert "150" in body
        assert "Est. 7.5 km" in body
        assert "expires in" in body
        # The estimate must never read as earnings, payout or guarantee
        # (scoped to the offer card: the unrelated Earnings panel has
        # its own pre-existing "payout schedules" copy).
        assert "New ride request" in body
        segment = body.split("New ride request", 1)[1][:4000].lower()
        assert "payout" not in segment
        assert "guaranteed" not in segment
        assert "your earning" not in segment
        assert "driver earning" not in segment
        assert "/api/transport/drivers/me/offers/" + ref + "/accept" in body
        assert "/api/transport/drivers/me/offers/" + ref + "/decline" in body

    def test_card_approx_wording_for_planning_default(
            self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id, basis="planning_default")
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _enter_driver_context(client, driver)

        body = client.get(
            "/transport/driver-dashboard").data.decode("utf-8")
        # Fare stays, but is flagged approximate; no km figure is shown
        # and nothing claims actual/route/travelled distance.
        assert "Approx. fare estimate" in body
        assert "Est. 7.5 km" not in body
        lowered = body.lower()
        assert "actual distance" not in lowered
        assert "route distance" not in lowered
        assert "travelled distance" not in lowered

    def test_card_coords_fallback_no_literals(self, app, client, monkeypatch):
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id, coords_only=True)
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _enter_driver_context(client, driver)

        body = client.get(
            "/transport/driver-dashboard").data.decode("utf-8")
        assert "0.3136, 32.5811" in body
        assert "0.3476, 32.5825" in body


# ----------------------------------------------------------------------
# Notification contract
# ----------------------------------------------------------------------

class TestOfferNotificationContract:
    def test_new_booking_message_pointer_and_link(self, app):
        from app.transport.services.notification_service import (
            NotificationService,
        )
        from app.notifications.models import NotificationModule

        driver = _seed_driver(app)
        with app.app_context():
            result = NotificationService.send_driver_notification(
                driver.driver_profile_id,
                "new_booking",
                {
                    "booking_reference": "OCREF123",
                    "pickup_location": "Kampala Road, Kampala",
                    "dropoff_location": "Entebbe Airport",
                },
            )
        assert result["success"] is True, result

        with app.app_context():
            from app.notifications.models import Notification

            row = (
                Notification.query.filter(
                    Notification.user_id == driver.id,
                    Notification.module == NotificationModule.TRANSPORT.value,
                )
                .order_by(Notification.id.desc())
                .first()
            )
            assert row is not None
            assert row.type == "booking_update"
            assert "OCREF123" in row.body
            assert "Kampala Road, Kampala" in row.body
            assert "Entebbe Airport" in row.body
            # DurableService.send stores the data payload in context.
            assert (row.context or {}).get("booking_reference") == "OCREF123"
            assert (row.context or {}).get("booking_id") == "OCREF123"
            assert row.link == "/transport/driver-dashboard"

    def test_internal_id_and_reference_stay_distinct(self, app):
        from app.transport.models import Booking
        from app.transport.services.notification_service import (
            NotificationService,
        )
        from app.notifications.models import Notification

        driver = _seed_driver(app)
        rider = _seed_driver(app)
        booking_id, ref = _make_rich_booking(app, rider.id)
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            assert stored is not None
            internal_id = stored.id
            result = NotificationService.send_driver_notification(
                driver.driver_profile_id,
                "new_booking",
                {
                    "booking_reference": ref,
                    "pickup_location": "Kampala Road, Kampala",
                    "dropoff_location": "Entebbe Airport",
                },
            )
        assert result["success"] is True, result
        assert result["data"]["result"].get("notification_id") not in (
            None, "", "n/a")

        with app.app_context():
            row = (
                Notification.query.filter(
                    Notification.user_id == driver.id,
                )
                .order_by(Notification.id.desc())
                .first()
            )
            assert row is not None
            # The internal integer id lives nowhere in the driver row;
            # both pointer fields carry the PUBLIC reference string,
            # per the transport notification convention.
            assert isinstance(internal_id, int)
            assert (row.context or {}).get("booking_reference") == ref
            assert (row.context or {}).get("booking_id") == ref
            assert (row.context or {}).get("booking_id") != internal_id
            assert "booking_id" not in (row.context or {}).get(
                "booking_reference", "")
            # Still resolves to a driver-facing destination.
            assert row.link == "/transport/driver-dashboard"
            assert row.user_id == driver.id


class TestEnrichmentFailures:
    """Enrichment degrades per failure class without crashing the read."""

    def test_missing_booking_serves_thin_and_logs(self, app, monkeypatch):
        from unittest.mock import MagicMock

        import app.transport.services.offer_service as offer_module
        from app.transport.services.offer_service import OfferService

        monkeypatch.setattr(
            "app.transport.services.offer_service.redis_client", _FakeRedis())
        mock_log = MagicMock()
        monkeypatch.setattr(offer_module, "logger", mock_log)
        with app.app_context():
            OfferService.create_offer("OC-NOBOOK", 11, 22)
            offers = OfferService.list_driver_offers(11)
        assert len(offers) == 1
        assert offers[0]["booking_reference"] == "OC-NOBOOK"
        assert "pickup" not in offers[0]
        assert "ttl_remaining" in offers[0]
        mock_log.info.assert_called()
        assert any("no booking row" in str(call)
                   for call in mock_log.info.call_args_list)

    def test_db_failure_serves_thin_logs_and_keeps_list(
            self, app, monkeypatch):
        from unittest.mock import MagicMock

        import app.transport.services.offer_service as offer_module
        from app.transport.models import Booking
        from app.transport.services.offer_service import OfferService

        monkeypatch.setattr(
            "app.transport.services.offer_service.redis_client", _FakeRedis())
        mock_log = MagicMock()
        monkeypatch.setattr(offer_module, "logger", mock_log)
        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        rider = _seed_driver(app)
        _, ref = _make_rich_booking(app, rider.id)
        with app.app_context():
            OfferService.create_offer(
                ref, driver.driver_profile_id, vehicle_id)

            class _BoomQuery:
                def filter(self, *args, **kwargs):
                    raise RuntimeError("database unavailable")

            monkeypatch.setattr(Booking, "query", _BoomQuery())
            offers = OfferService.list_driver_offers(
                driver.driver_profile_id)
        # The list survives: one thin offer, lookup failure observed.
        assert len(offers) == 1
        assert offers[0]["booking_reference"] == ref
        assert "pickup" not in offers[0]
        mock_log.warning.assert_called()
        assert any("booking lookup failed" in str(call)
                   for call in mock_log.warning.call_args_list)


class TestLocationEndToEnd:
    """Original rider text through the REAL creation path to the offer."""

    def _create_via_service(self, app, rider_id, payload):
        from app.transport.services import get_booking_service

        with app.app_context():
            return get_booking_service().create_booking(rider_id, payload)

    def test_text_only_locations_no_fabricated_coords(
            self, app, client, monkeypatch):
        from app.transport.models import Booking

        rider = _seed_driver(app)
        result = self._create_via_service(app, rider.id, {
            "pickup_location": "Kampala Serena",
            "dropoff_location": "Entebbe Airport",
            "pickup_time": (
                datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
            "service_type": "on_demand",
        })
        assert result["success"] is True, result
        ref = result["data"]["booking_reference"]

        with app.app_context():
            stored = Booking.query.filter_by(
                booking_reference=ref).first()
            assert stored is not None
            # Original human text survives verbatim at the source.
            assert stored.pickup_location == "Kampala Serena"
            assert stored.dropoff_location == "Entebbe Airport"

        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _login(client, driver)

        offer = client.get(
            "/api/transport/drivers/me/offers").get_json()["data"]["offers"][0]
        assert offer["pickup"]["text"] == "Kampala Serena"
        assert offer["destination"]["text"] == "Entebbe Airport"
        # Nothing fabricated: no coordinates exist, none are claimed.
        assert offer["pickup"]["latitude"] is None
        assert offer["pickup"]["longitude"] is None
        assert offer["destination"]["latitude"] is None

    def test_text_plus_coordinates_both_preserved(
            self, app, client, monkeypatch):
        from app.transport.models import Booking

        rider = _seed_driver(app)
        result = self._create_via_service(app, rider.id, {
            "pickup_location": {
                "latitude": 0.3476,
                "longitude": 32.5825,
                "address": "Kampala Serena",
            },
            "dropoff_location": {
                "latitude": 0.3136,
                "longitude": 32.5811,
                "address": "Entebbe Airport",
            },
            "pickup_time": (
                datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
            "service_type": "on_demand",
        })
        assert result["success"] is True, result
        ref = result["data"]["booking_reference"]

        with app.app_context():
            stored = Booking.query.filter_by(
                booking_reference=ref).first()
            assert stored is not None
            assert stored.pickup_location["address"] == "Kampala Serena"
            assert stored.pickup_location["latitude"] == 0.3476

        driver = _seed_driver(app)
        vehicle_id = _make_ready(app, driver)
        _offer(app, monkeypatch, ref, driver.driver_profile_id, vehicle_id)
        _login(client, driver)

        offer = client.get(
            "/api/transport/drivers/me/offers").get_json()["data"]["offers"][0]
        assert offer["pickup"]["text"] == "Kampala Serena"
        assert offer["pickup"]["latitude"] == pytest.approx(0.3476)
        assert offer["pickup"]["longitude"] == pytest.approx(32.5825)
        assert offer["destination"]["text"] == "Entebbe Airport"
        assert offer["destination"]["latitude"] == pytest.approx(0.3136)


class TestEndpointDisplay:
    def test_chain_address_then_location_then_coords_then_none(self):
        from app.transport.services.offer_service import (
            format_endpoint_display,
        )

        assert format_endpoint_display(
            "  Kampala Road ", {"address": "Other"})["text"] == "Kampala Road"
        assert format_endpoint_display(
            None, {"address": "Entebbe Airport"})["text"] == "Entebbe Airport"
        assert format_endpoint_display(
            None,
            {"latitude": 0.3136, "longitude": 32.5811})["text"] == (
            "0.3136, 32.5811")
        assert format_endpoint_display(None, {})["text"] is None
        assert format_endpoint_display(None, None)["text"] is None
