"""Transport booking -> GEO geocoding consumption (geocoding node).

Proves the integration: map-pin flat coordinates resolve to canonical
booking endpoints, measured GEO straight-line distance prices the
booking (instead of the silent 5 km default), text-only bookings keep
exact legacy behavior, invalid coordinates fail honestly, and
coordinate bookings become matchable while text bookings stay
excluded. No Photon/live provider required; no road-distance claims.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.geo.interfaces import GeoPoint
from app.geo.services import straight_line_distance_m

LAT_A, LNG_A = 0.3150, 32.5820
LAT_B, LNG_B = 0.3350, 32.6000


def _user(app, tag="geo"):
    from app.extensions import db
    from app.identity.models.user import User
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"{tag}_{uid}",
                    email=f"{tag}_{uid}@test.example.com", is_active=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()
        return user.id


def _payload(**over):
    data = {
        "pickup_location": "Nile Stadium, Kampala",
        "dropoff_location": "Entebbe Airport",
        "pickup_time": (datetime.now(timezone.utc)
                        + timedelta(hours=1)).isoformat(),
        "service_type": "on_demand", "passenger_count": 1,
    }
    data.update(over)
    return data


def _create(app, user_id, **over):
    from app.transport.services.booking_service import get_booking_service
    with app.app_context():
        result = get_booking_service().create_booking(
            user_id, _payload(**over))
    assert result["success"] is True, result
    return result["data"]["booking_id"]


def _booking(app, booking_id):
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        return db.session.get(Booking, booking_id)


# --- canonical assembly -----------------------------------------------------------------

def test_pin_coordinates_become_canonical_endpoints(app):
    user_id = _user(app)
    booking_id = _create(
        app, user_id, pickup_latitude=LAT_A, pickup_longitude=LNG_A,
        dropoff_latitude=LAT_B, dropoff_longitude=LNG_B)
    booking = _booking(app, booking_id)
    assert booking.pickup_location["latitude"] == pytest.approx(LAT_A)
    assert booking.pickup_location["longitude"] == pytest.approx(LNG_A)
    assert booking.pickup_location["address"] == "Nile Stadium, Kampala"
    assert booking.dropoff_location["latitude"] == pytest.approx(LAT_B)


def test_text_only_booking_unchanged(app):
    user_id = _user(app)
    booking_id = _create(app, user_id)
    booking = _booking(app, booking_id)
    assert booking.pickup_location == "Nile Stadium, Kampala"
    assert float(booking.estimated_distance_km) == 5.0
    assert booking.booking_metadata["distance_basis"] == "planning_default"


def test_partial_coordinates_rejected(app):
    from app.transport.services.booking_service import get_booking_service
    from app.utils.exceptions import ValidationError
    user_id = _user(app)
    with app.app_context():
        with pytest.raises(ValidationError):
            get_booking_service().create_booking(
                user_id, _payload(pickup_latitude=LAT_A))


def test_out_of_range_coordinates_rejected(app):
    from app.transport.services.booking_service import get_booking_service
    from app.utils.exceptions import ValidationError
    user_id = _user(app)
    with app.app_context():
        with pytest.raises(ValidationError):
            get_booking_service().create_booking(
                user_id, _payload(pickup_latitude=999.0,
                                  pickup_longitude=LNG_A,
                                  dropoff_latitude=LAT_B,
                                  dropoff_longitude=LNG_B))


# --- measured distance --------------------------------------------------------------------

def test_measured_distance_prices_booking(app):
    user_id = _user(app)
    booking_id = _create(
        app, user_id, pickup_latitude=LAT_A, pickup_longitude=LNG_A,
        dropoff_latitude=LAT_B, dropoff_longitude=LNG_B)
    booking = _booking(app, booking_id)
    expected_km = straight_line_distance_m(
        GeoPoint(LAT_A, LNG_A), GeoPoint(LAT_B, LNG_B)) / 1000.0
    assert float(booking.estimated_distance_km) == pytest.approx(expected_km,
                                                                 abs=0.01)
    assert booking.booking_metadata["distance_basis"] == "straight_line_planner"
    assert booking.booking_metadata["distance_km"] == pytest.approx(expected_km)
    assert booking.booking_metadata["fare_version"] >= 1
    # Same canonical engine: (10 + km*2.5) * 1.2 [* surge].
    # Money columns keep cent precision; compare accordingly.
    assert float(booking.base_price) == pytest.approx(float(
        (Decimal("10") + Decimal(str(expected_km)) * Decimal("2.5"))
        * Decimal("1.2") * booking.surge_multiplier), abs=0.01)


def test_client_distance_preserved_without_coordinates(app):
    user_id = _user(app)
    booking_id = _create(app, user_id, estimated_distance=12)
    booking = _booking(app, booking_id)
    assert float(booking.estimated_distance_km) == 12.0
    assert booking.booking_metadata["distance_basis"] == "planning_default"


# --- matchability ------------------------------------------------------------------------------

def test_coordinate_booking_is_matchable_text_is_not(app):
    from app.transport.services.tracking_service import TrackingService

    driver_uid = _user(app, "drv")
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import (ComplianceStatus, DriverProfile,
                                      VerificationTier)
    with app.app_context():
        profile = DriverProfile(
            user_id=driver_uid, driver_code=f"GC-{uuid.uuid4().hex[:6]}",
            verification_tier=VerificationTier.PLATFORM_VERIFIED,
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True, is_online=True, is_available=True,
            max_passenger_capacity=4, vehicle_classes=["comfort"])
        db.session.add(profile)
        db.session.commit()
        driver_id = profile.id
        TrackingService.update_location("driver", driver_id, {
            "latitude": LAT_A, "longitude": LNG_A})
    user_id = _user(app, "pax")
    coord_id = _create(
        app, user_id, pickup_latitude=LAT_A, pickup_longitude=LNG_A,
        dropoff_latitude=LAT_B, dropoff_longitude=LNG_B)
    text_id = _create(app, user_id)
    with app.app_context():
        # Deterministic membership: the shared test DB accumulates
        # online drivers across suites, and get_nearby_drivers takes
        # an unordered LIMIT 50 (pre-existing robustness wart, not
        # this node). Take everyone else offline first, then restore.
        from app.extensions import db
        from app.transport.models import DriverProfile
        others = DriverProfile.query.filter(
            DriverProfile.id != driver_id,
            DriverProfile.is_online == True).all()  # noqa: E712
        others_snapshot = [(d.id, d.is_online) for d in others]
        try:
            (DriverProfile.query.filter(DriverProfile.id != driver_id)
             .update({DriverProfile.is_online: False}))
            db.session.commit()
            nearby = TrackingService.get_nearby_drivers(
                {"latitude": LAT_A, "longitude": LNG_A}, radius_km=5)
            assert any(d["driver_id"] == driver_id for d in nearby)
        finally:
            for did, was_online in others_snapshot:
                db.session.get(DriverProfile, did).is_online = was_online
            db.session.commit()
    # The coordinate booking's own pickup now resolves for matching,
    # while the text booking cannot (distance None) — the product gap,
    # proven at the boundary that matters.
    from app.transport.services.matching_service import MatchingService
    assert MatchingService._coordinates_or_none(
        {"latitude": LAT_A, "longitude": LNG_A}) == (LAT_A, LNG_A)
    assert MatchingService._coordinates_or_none(
        "Nile Stadium, Kampala") == (None, None)
    assert coord_id and text_id
