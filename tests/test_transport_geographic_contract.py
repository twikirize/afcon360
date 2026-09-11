# tests/test_transport_geographic_contract.py
"""TH-3-Contract: Canonical Geographic Coordinate Contract - Focused Verification.

Proves every defect found in the TH-3 geographic audit is fixed:

  TC-01  Canonical 'latitude'/'longitude' keys accepted everywhere
  TC-02  Legacy 'lat'/'lng' keys rejected -> no silent false proximity
  TC-03  Malformed/partial/out-of-range canonical coords -> None (not 0)
  TC-04  Booking boundary rejects legacy/partial coords with ValidationError
  TC-05  Matching freshness gate: only fresh canonical locations matchable
  TC-06  Provider payload carries current_location + location_updated_at
  TC-07  Ingestion: TrackingService.update_location persists canonical pair,
         keeps vehicle cascade, survives Redis unavailability with TTL 300
  TC-08  Distance/ETA reflect proximity when location present
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    ProviderType,
    ServiceType,
    Vehicle,
    VehicleClass,
)
from app.transport.services import get_provider_service
from app.transport.services.booking_service import _validate_booking_location_coordinates
from app.transport.services.matching_service import MatchingService
from app.transport.services.tracking_service import TrackingService
from app.utils.exceptions import ValidationError


def _canonical(latitude=-1.2833, longitude=36.8167):
    return {'latitude': latitude, 'longitude': longitude}


def _legacy():
    return {'lat': -1.2833, 'lng': 36.8167}


def _driver(location, updated_at):
    return {
        'driver_id': 1,
        'driver_code': 'DRV-TEST',
        'average_rating': 4.5,
        'acceptance_rate': 90,
        'vehicle_classes': ['comfort'],
        'service_types': ['on_demand'],
        'current_location': location,
        'location_updated_at': updated_at,
    }


def _transient_booking(pickup=None):
    return Booking(
        pickup_location=pickup or _canonical(),
        service_type=ServiceType.ON_DEMAND,
        passenger_count=1,
    )


# ---------------------------------------------------------------------------
# TC-01/TC-02/TC-03  - Coordinate contract: canonical accepted, legacy rejected
# ---------------------------------------------------------------------------

class TestCoordinateContract:
    def test_canonical_coordinates_parsed_to_floats(self):
        assert TrackingService._coordinates_or_none(_canonical()) == (-1.2833, 36.8167)

    def test_matching_parses_canonical_coordinates(self):
        assert MatchingService._coordinates_or_none(_canonical()) == (-1.2833, 36.8167)

    def test_legacy_lat_lng_rejected(self):
        assert TrackingService._coordinates_or_none(_legacy()) == (None, None)

    def test_partial_canonical_rejected(self):
        assert TrackingService._coordinates_or_none({'latitude': 1.0}) == (None, None)
        assert TrackingService._coordinates_or_none({'longitude': 1.0}) == (None, None)

    def test_out_of_range_rejected(self):
        assert TrackingService._coordinates_or_none(_canonical(latitude=91.0)) == (None, None)
        assert TrackingService._coordinates_or_none(_canonical(longitude=181.0)) == (None, None)
        assert TrackingService._coordinates_or_none(_canonical(latitude=-91.0)) == (None, None)

    def test_non_dict_rejected(self):
        assert TrackingService._coordinates_or_none("Kampala") == (None, None)
        assert TrackingService._coordinates_or_none(None) == (None, None)


class TestDistanceNeverFalseZero:
    def test_canonical_distance_positive(self):
        d = TrackingService._calculate_distance(_canonical(), _canonical(-1.2921, 36.8219))
        assert isinstance(d, float) and d > 0

    def test_legacy_keys_distance_is_none_not_zero(self):
        d = TrackingService._calculate_distance(_legacy(), _canonical())
        assert d is None

    def test_partial_coordinates_distance_is_none(self):
        d = TrackingService._calculate_distance({'latitude': 1.0}, _canonical())
        assert d is None

    def test_malformed_pair_distance_is_none(self):
        d = TrackingService._calculate_distance(_canonical(), {'lat': -1.0, 'lng': 36.0})
        assert d is None

    def test_matching_distance_is_none_for_legacy(self):
        assert MatchingService._calculate_distance(_legacy(), _canonical()) is None


# ---------------------------------------------------------------------------
# TC-04  - Booking boundary rejects non-canonical geographic coordinates
# ---------------------------------------------------------------------------

class TestBookingLocationBoundary:
    def test_canonical_dict_passes(self):
        result = _validate_booking_location_coordinates(_canonical(), 'pickup_location')
        assert result == _canonical()

    def test_legacy_keys_rejected(self):
        with pytest.raises(ValidationError):
            _validate_booking_location_coordinates(_legacy(), 'pickup_location')

    def test_both_key_sets_rejected(self):
        with pytest.raises(ValidationError):
            _validate_booking_location_coordinates(
                {'latitude': 1.0, 'longitude': 2.0, 'lat': 1.0, 'lng': 2.0},
                'dropoff_location',
            )

    def test_partial_canonical_rejected(self):
        with pytest.raises(ValidationError):
            _validate_booking_location_coordinates({'latitude': 1.0}, 'pickup_location')

    def test_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            _validate_booking_location_coordinates(_canonical(latitude=120.0), 'pickup_location')

    def test_string_address_passes_through(self):
        assert _validate_booking_location_coordinates('Kampala', 'pickup_location') == 'Kampala'

    def test_none_passes_through(self):
        assert _validate_booking_location_coordinates(None, 'pickup_location') is None

    def test_error_message_names_canonical_keys(self):
        with pytest.raises(ValidationError) as exc_info:
            _validate_booking_location_coordinates(_legacy(), 'pickup_location')
        assert 'latitude' in str(exc_info.value)


# ---------------------------------------------------------------------------
# TC-05  - Matching freshness gate + TC-08 distance/ETA
# ---------------------------------------------------------------------------

class TestDriverRankingFreshness:
    def test_fresh_canonical_driver_ranked(self):
        ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        ranked = MatchingService._rank_drivers_for_booking(
            [_driver(_canonical(), ts)], _transient_booking()
        )
        assert len(ranked) == 1
        assert ranked[0]['match_score'] >= 40
        assert 'estimated_arrival_time' in ranked[0]

    def test_fresh_legacy_location_excluded(self):
        ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        ranked = MatchingService._rank_drivers_for_booking(
            [_driver(_legacy(), ts)], _transient_booking()
        )
        assert ranked == []

    def test_stale_location_excluded(self):
        ts = (datetime.now(timezone.utc) - timedelta(seconds=310)).isoformat()
        ranked = MatchingService._rank_drivers_for_booking(
            [_driver(_canonical(), ts)], _transient_booking()
        )
        assert ranked == []

    def test_missing_timestamp_excluded(self):
        ranked = MatchingService._rank_drivers_for_booking(
            [_driver(_canonical(), None)], _transient_booking()
        )
        assert ranked == []

    def test_missing_location_excluded(self):
        ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        ranked = MatchingService._rank_drivers_for_booking(
            [_driver(None, ts)], _transient_booking()
        )
        assert ranked == []

    def test_garbage_timestamp_excluded(self):
        ranked = MatchingService._rank_drivers_for_booking(
            [_driver(_canonical(), 'not-a-date')], _transient_booking()
        )
        assert ranked == []

    def test_empty_driver_list(self):
        assert MatchingService._rank_drivers_for_booking([], _transient_booking()) == []

    def test_eta_grows_from_proximity(self):
        ts = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        ranked = MatchingService._rank_drivers_for_booking(
            [_driver(_canonical(), ts)], _transient_booking()
        )
        assert ranked[0]['estimated_arrival_time'] >= 5


# ---------------------------------------------------------------------------
# TC-07  - Ingestion through TrackingService + prerequisite DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def user():
    from app.identity.models.user import User

    unique = uuid.uuid4().hex[:8]
    u = User(
        public_id=str(uuid.uuid4()),
        username=f"tgeo_user_{unique}",
        email=f"tgeo_user_{unique}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    u.set_password("Password123!")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def driver_profile(user):
    dp = DriverProfile(
        user_id=user.id,
        driver_code=f"DRV-{uuid.uuid4().hex[:6].upper()}",
        verification_tier='platform_verified',
        compliance_status=ComplianceStatus.APPROVED,
        is_active=True,
        is_online=True,
        is_available=True,
        max_passenger_capacity=4,
        vehicle_classes=['comfort'],
    )
    db.session.add(dp)
    db.session.commit()
    return dp


@pytest.fixture
def vehicle(driver_profile):
    v = Vehicle(
        owner_type='driver',
        owner_id=driver_profile.id,
        license_plate=f"UG-{uuid.uuid4().hex[:4].upper()}",
        make="Toyota",
        model="Corolla",
        year=2022,
        vehicle_type="sedan",
        vehicle_class=VehicleClass.COMFORT,
        passenger_capacity=4,
        status='active',
        is_available=True,
    )
    db.session.add(v)
    db.session.commit()
    db.session.add(DriverVehicleHistory(
        driver_id=driver_profile.id,
        vehicle_id=v.id,
        started_at=datetime.now(timezone.utc),
        ended_at=None,
        assignment_reason='shift_start',
    ))
    db.session.commit()
    return v


class TestTrackingServiceIngestion:
    def test_persists_canonical_location(self, app, db_session, driver_profile, monkeypatch):
        recorder = {}

        class FakeRedis:
            def setex(self, key, ttl, value):
                recorder['key'] = key
                recorder['ttl'] = ttl
                recorder['value'] = value

        monkeypatch.setattr(
            'app.transport.services.tracking_service.redis_client', FakeRedis()
        )
        result = TrackingService.update_location(
            'driver', driver_profile.id, {'latitude': -1.2833, 'longitude': 36.8167}
        )
        assert result['success'] is True
        db.session.refresh(driver_profile)
        assert driver_profile.last_location.get('latitude') == -1.2833
        assert driver_profile.last_location.get('longitude') == 36.8167
        assert 'latitude' in driver_profile.last_location
        assert 'longitude' in driver_profile.last_location
        assert 'lat' not in driver_profile.last_location

    def test_redis_ttl_is_300(self, app, db_session, driver_profile, monkeypatch):
        recorder = {}

        class FakeRedis:
            def setex(self, key, ttl, value):
                recorder['key'] = key
                recorder['ttl'] = ttl

        monkeypatch.setattr(
            'app.transport.services.tracking_service.redis_client', FakeRedis()
        )
        TrackingService.update_location(
            'driver', driver_profile.id, {'latitude': -1.2833, 'longitude': 36.8167}
        )
        assert recorder['ttl'] == TrackingService.LOCATION_TTL_SECONDS == 300
        assert recorder['key'] == f"{TrackingService.REDIS_PREFIX}:driver:{driver_profile.id}"

    def test_redis_failure_tolerated(self, app, db_session, driver_profile, monkeypatch):
        class FakeRedis:
            def setex(self, *args, **kwargs):
                raise ConnectionError('no redis')

        monkeypatch.setattr(
            'app.transport.services.tracking_service.redis_client', FakeRedis()
        )
        result = TrackingService.update_location(
            'driver', driver_profile.id, {'latitude': -1.2833, 'longitude': 36.8167}
        )
        assert result['success'] is True
        db.session.refresh(driver_profile)
        assert driver_profile.last_location is not None

    def test_missing_keys_rejected(self, app, db_session, driver_profile):
        with pytest.raises(ValidationError):
            TrackingService.update_location('driver', driver_profile.id, {})

    def test_out_of_range_rejected(self, app, db_session, driver_profile):
        with pytest.raises(ValidationError):
            TrackingService.update_location(
                'driver', driver_profile.id, {'latitude': 91.0, 'longitude': 0.0}
            )

    def test_vehicle_cascade_preserved(self, app, db_session, driver_profile, vehicle, monkeypatch):
        class FakeRedis:
            def setex(self, *args, **kwargs):
                pass

        monkeypatch.setattr(
            'app.transport.services.tracking_service.redis_client', FakeRedis()
        )
        TrackingService.update_location(
            'driver', driver_profile.id, {'latitude': -1.2833, 'longitude': 36.8167}
        )
        db.session.refresh(driver_profile)
        db.session.refresh(vehicle)
        assert driver_profile.current_vehicle is not None
        assert driver_profile.current_vehicle.id == vehicle.id
        assert vehicle.current_location.get('latitude') == -1.2833
        assert vehicle.current_location.get('longitude') == 36.8167

    def test_location_updated_at_set(self, app, db_session, driver_profile, monkeypatch):
        class FakeRedis:
            def setex(self, *args, **kwargs):
                pass

        monkeypatch.setattr(
            'app.transport.services.tracking_service.redis_client', FakeRedis()
        )
        TrackingService.update_location(
            'driver', driver_profile.id, {'latitude': -1.2833, 'longitude': 36.8167}
        )
        db.session.refresh(driver_profile)
        assert driver_profile.location_updated_at is not None


# ---------------------------------------------------------------------------
# TC-06  - Provider payload exposes location + freshness to the matcher
# ---------------------------------------------------------------------------

class TestProviderAvailabilityPayload:
    def test_payload_carries_location_fields(self, app, db_session, driver_profile, monkeypatch):
        class FakeRedis:
            def setex(self, *args, **kwargs):
                pass

        monkeypatch.setattr(
            'app.transport.services.tracking_service.redis_client', FakeRedis()
        )
        TrackingService.update_location(
            'driver', driver_profile.id, {'latitude': -1.2833, 'longitude': 36.8167}
        )
        db.session.refresh(driver_profile)

        # The provider pool query is intentionally unordered (no ORDER BY) and
        # truncated by `limit` (see provider_service.get_available_drivers).
        # Once the shared test DB accumulates >= `limit` committed eligible
        # drivers from other suites, the fixture driver (last inserted) can be
        # truncated from the arbitrary first-`limit` subset, making the test
        # depend on external DB state. Keep the pool call bounded and make the
        # assertion order-independent: within this test's transaction, mark
        # every other driver non-eligible so the fixture driver is
        # deterministically the only eligible row regardless of how polluted
        # the shared DB is. The update is never committed; the db_session
        # teardown rolls it back, so other suites' committed data is untouched.
        DriverProfile.query.filter(DriverProfile.id != driver_profile.id).update(
            {DriverProfile.is_online: False, DriverProfile.is_available: False},
            synchronize_session=False,
        )
        drivers = get_provider_service().get_available_drivers(limit=100)
        match = [d for d in drivers if d['driver_code'] == driver_profile.driver_code]
        assert len(match) == 1
        payload = match[0]
        assert payload['current_location']['latitude'] == -1.2833
        assert payload['current_location']['longitude'] == 36.8167
        assert 'lat' not in payload['current_location']
        assert payload['location_updated_at'] is not None
        datetime.fromisoformat(payload['location_updated_at'])