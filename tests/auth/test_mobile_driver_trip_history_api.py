from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace


def _driver_mobile_context(monkeypatch):
    from app.auth import mobile_api

    user = SimpleNamespace(id=451, public_id="driver-public-451")
    profile = SimpleNamespace(id=902, user_id=user.id)
    calls = {}

    def require_context(expected_client=None):
        calls["expected_client"] = expected_client
        return {
            "user": user,
            "record": {"client": "driver"},
        }, None

    monkeypatch.setattr(mobile_api, "require_mobile_context", require_context)
    monkeypatch.setattr(
        mobile_api,
        "_current_driver",
        lambda: (profile, None, 200),
    )
    return user, profile, calls


def _trip_row():
    return {
        "id": 70001,
        "booking_reference": "AF360-TRIP-001",
        "status": "completed",
        "booking_mode": "scheduled",
        "pickup_time": datetime(2026, 11, 10, 8, 30, tzinfo=timezone.utc),
        "pickup_schedule": {
            "utc_datetime": "2026-11-10T08:30:00+00:00",
            "timezone_name": "Africa/Kampala",
            "internal_remark": "must not be exposed",
        },
        "pickup_location_text": "Kampala Road, Kampala",
        "dropoff_location_text": "Entebbe Airport",
        "pickup_location": {"latitude": 0.31, "longitude": 32.58},
        "passenger_count": 2,
        "final_price": Decimal("120.00"),
        "currency": "USD",
        "payment_method": "wallet",
        "payment_status": "captured",
        "can_mark_no_show": False,
        "created_at": datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc),
        # These values must never be part of the native Driver response.
        "user_id": 888,
        "assigned_driver_id": 902,
        "vehicle_id": 991,
        "passenger_name": "Private Passenger",
        "passenger_phone": "+256700000000",
        "passenger_email": "passenger@example.test",
        "booking_metadata": {
            "private_note": "must not leak",
            "completed_by_driver_profile_id": 902,
        },
    }



def test_mobile_driver_all_trip_history_merges_deduplicates_and_sorts_both_scopes(
    client, monkeypatch
):
    from app.transport.services.booking_service import BookingService

    _user, profile, calls = _driver_mobile_context(monkeypatch)
    service_calls = {}

    recent = _trip_row()
    recent["booking_reference"] = "AF360-TRIP-RECENT"
    recent["created_at"] = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)

    overlap_recent = _trip_row()
    overlap_recent["booking_reference"] = "AF360-TRIP-OVERLAP"
    overlap_recent["status"] = "completed"
    overlap_recent["pickup_time"] = datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc)

    upcoming = _trip_row()
    upcoming["booking_reference"] = "AF360-TRIP-UPCOMING"
    upcoming["status"] = "assigned"
    upcoming["pickup_time"] = datetime(2026, 11, 14, 8, 0, tzinfo=timezone.utc)
    upcoming["created_at"] = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)

    overlap_upcoming = dict(overlap_recent)
    overlap_upcoming["status"] = "assigned"
    overlap_upcoming["pickup_time"] = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)

    def recent_bookings(self, driver_user_id, limit=10):
        service_calls["recent"] = (driver_user_id, limit)
        return [recent, overlap_recent]

    def upcoming_bookings(self, driver_user_id, limit=5):
        service_calls["upcoming"] = (driver_user_id, limit)
        return [upcoming, overlap_upcoming]

    monkeypatch.setattr(BookingService, "get_driver_recent_bookings", recent_bookings)
    monkeypatch.setattr(BookingService, "get_driver_upcoming_bookings", upcoming_bookings)

    response = client.get(
        "/api/mobile/v1/driver/trips?scope=all&limit=5",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert calls["expected_client"] == "driver"
    assert service_calls == {
        "recent": (profile.user_id, 5),
        "upcoming": (profile.user_id, 5),
    }

    data = response.get_json()["data"]
    assert data["scope"] == "all"
    assert data["limit"] == 5
    assert data["count"] == 3
    assert [item["booking_reference"] for item in data["items"]] == [
        "AF360-TRIP-UPCOMING",
        "AF360-TRIP-OVERLAP",
        "AF360-TRIP-RECENT",
    ]
    # The upcoming copy is authoritative when one booking is present in
    # both service results during an assignment/status transition.
    overlap = next(
        item for item in data["items"]
        if item["booking_reference"] == "AF360-TRIP-OVERLAP"
    )
    assert overlap["status"] == "assigned"
    assert "passenger_phone" not in response.get_data(as_text=True)


def test_mobile_driver_trip_history_route_is_registered_for_get(app):
    routes = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/mobile/v1/driver/trips"
    ]
    assert len(routes) == 1
    assert "GET" in routes[0].methods

def test_mobile_driver_trip_history_requires_driver_bearer(client):
    response = client.get("/api/mobile/v1/driver/trips?scope=recent")

    assert response.status_code == 401
    assert response.get_json()["code"] == "mobile_auth_required"


def test_mobile_driver_recent_trip_history_is_self_scoped_and_redacted(
    client, monkeypatch
):
    from app.transport.services.booking_service import BookingService

    _user, profile, calls = _driver_mobile_context(monkeypatch)
    service_calls = {}

    def recent(self, driver_user_id, limit=10):
        service_calls.update(driver_user_id=driver_user_id, limit=limit)
        return [_trip_row()]

    monkeypatch.setattr(BookingService, "get_driver_recent_bookings", recent)

    response = client.get(
        "/api/mobile/v1/driver/trips?scope=recent&limit=7",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert calls["expected_client"] == "driver"
    assert service_calls == {"driver_user_id": profile.user_id, "limit": 7}

    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["scope"] == "recent"
    assert body["data"]["count"] == 1
    assert body["data"]["limit"] == 7

    item = body["data"]["items"][0]
    assert item == {
        "booking_reference": "AF360-TRIP-001",
        "status": "completed",
        "booking_mode": "scheduled",
        "pickup_time": "2026-11-10T08:30:00+00:00",
        "pickup_schedule": {
            "utc_datetime": "2026-11-10T08:30:00+00:00",
            "timezone_name": "Africa/Kampala",
        },
        "pickup": {"address": "Kampala Road, Kampala"},
        "dropoff": {"address": "Entebbe Airport"},
        "passenger_count": 2,
        "fare_amount": "120.00",
        "currency": "USD",
        "payment_method": "wallet",
        "payment_status": "captured",
        "can_mark_no_show": False,
        "created_at": "2026-11-09T08:00:00+00:00",
        "completed_at": "2026-11-09T09:00:00+00:00",
    }

    serialized = response.get_data(as_text=True).lower()
    for forbidden in (
        "passenger_name",
        "private passenger",
        "passenger_phone",
        "+256700000000",
        "passenger_email",
        "passenger@example.test",
        "user_id",
        "assigned_driver_id",
        "vehicle_id",
        "booking_metadata",
        "internal_remark",
        "must not be exposed",
        "private_note",
        "completed_by_driver_profile_id",
        '"id"',
    ):
        assert forbidden.lower() not in serialized


def test_mobile_driver_trip_history_uses_upcoming_service_and_validates_scope_and_limit(
    client, monkeypatch
):
    from app.transport.services.booking_service import BookingService

    _user, profile, calls = _driver_mobile_context(monkeypatch)
    service_calls = {}

    def upcoming(self, driver_user_id, limit=10):
        service_calls.update(driver_user_id=driver_user_id, limit=limit)
        return []

    monkeypatch.setattr(BookingService, "get_driver_upcoming_bookings", upcoming)

    response = client.get(
        "/api/mobile/v1/driver/trips?scope=upcoming&limit=20",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "scope": "upcoming",
        "items": [],
        "count": 0,
        "limit": 20,
    }
    assert service_calls == {"driver_user_id": profile.user_id, "limit": 20}
    assert calls["expected_client"] == "driver"

    invalid_scope = client.get(
        "/api/mobile/v1/driver/trips?scope=everything",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )
    assert invalid_scope.status_code == 400
    assert invalid_scope.get_json()["code"] == "driver_trip_scope_invalid"

    invalid_limit = client.get(
        "/api/mobile/v1/driver/trips?scope=recent&limit=21",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )
    assert invalid_limit.status_code == 400
    assert invalid_limit.get_json()["code"] == "driver_trip_limit_invalid"

    non_integer_limit = client.get(
        "/api/mobile/v1/driver/trips?scope=recent&limit=10.5",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )
    assert non_integer_limit.status_code == 400
    assert non_integer_limit.get_json()["code"] == "driver_trip_limit_invalid"
