import json

from app.models.system_config import SystemConfig


def _polygon():
    return {
        "type": "Polygon",
        "coordinates": [[
            [32.5, 0.3], [32.7, 0.3], [32.7, 0.5],
            [32.5, 0.5], [32.5, 0.3],
        ]],
    }


def _area_config(enabled=True):
    return {
        "version": 1,
        "enabled": enabled,
        "allow_cross_area_routes": False,
        "areas": [{
            "id": "kampala",
            "name": "Kampala",
            "country_code": "UG",
            "active": True,
            "services": ["transport"],
            "geometry": _polygon(),
        }],
    }


def test_public_service_area_check_reports_supported_and_unsupported_points(
        app, anonymous_client, monkeypatch):
    monkeypatch.setattr(
        "app.geo.service_areas.get_service_area_config",
        lambda: _area_config(),
    )
    inside = anonymous_client.post(
        "/geo/api/service-area/check",
        json={"service": "transport", "latitude": 0.4, "longitude": 32.6},
    )
    outside = anonymous_client.post(
        "/geo/api/service-area/check",
        json={"service": "transport", "latitude": 0.8, "longitude": 32.6},
    )

    assert inside.status_code == 200
    assert inside.get_json()["data"]["supported"] is True
    assert "within an active service area" in inside.get_json()["data"]["message"]
    assert outside.status_code == 200
    assert outside.get_json()["data"]["supported"] is False
    assert "outside Pamoja" in outside.get_json()["data"]["message"]
    assert "no-store" in outside.headers["Cache-Control"]


def test_service_area_check_rejects_invalid_service_and_coordinates(
        app, anonymous_client):
    bad_service = anonymous_client.post(
        "/geo/api/service-area/check",
        json={"service": "flights", "latitude": 0.4, "longitude": 32.6},
    )
    bad_coordinate = anonymous_client.post(
        "/geo/api/service-area/check",
        json={"service": "transport", "latitude": 100, "longitude": 32.6},
    )
    assert bad_service.status_code == 400
    assert bad_service.get_json()["code"] == "INVALID_SERVICE"
    assert bad_coordinate.status_code == 400
    assert bad_coordinate.get_json()["code"] == "INVALID_SERVICE_AREA_INPUT"


def test_owner_can_manage_and_toggle_service_area_enforcement(
        app, admin_client):
    with app.app_context():
        SystemConfig.query.filter_by(key="GEO_SERVICE_AREAS").delete()
        from app.extensions import db
        db.session.commit()

    page = admin_client.get("/admin/owner/geofencing")
    assert page.status_code == 200
    assert b"Service areas" in page.data

    created = admin_client.post(
        "/admin/owner/geofencing",
        data={
            "action": "save_area",
            "name": "Kampala",
            "country_code": "UG",
            "active": "on",
            "services": ["transport"],
            "geometry": json.dumps(_polygon()),
        },
        follow_redirects=False,
    )
    assert created.status_code == 302

    with app.app_context():
        saved = SystemConfig.get("GEO_SERVICE_AREAS")
        assert saved["enabled"] is False
        assert saved["areas"][0]["id"] == "kampala"
        assert saved["areas"][0]["active"] is True

    enabled = admin_client.post(
        "/admin/owner/geofencing",
        data={"action": "save_settings", "enabled": "on"},
        follow_redirects=False,
    )
    assert enabled.status_code == 302
    with app.app_context():
        assert SystemConfig.get("GEO_SERVICE_AREAS")["enabled"] is True

    disabled = admin_client.post(
        "/admin/owner/geofencing",
        data={"action": "save_settings"},
        follow_redirects=False,
    )
    assert disabled.status_code == 302
    with app.app_context():
        assert SystemConfig.get("GEO_SERVICE_AREAS")["enabled"] is False


def test_standard_user_cannot_manage_service_areas(app, authenticated_client):
    response = authenticated_client.get("/admin/owner/geofencing")
    assert response.status_code == 403



def test_geocode_results_receive_fresh_service_area_annotations_and_no_store(
        app, anonymous_client, monkeypatch):
    from app.geo.interfaces import GeocodeResult

    class FakeGeocoder:
        def geocode(self, query, limit=5):
            return [
                GeocodeResult(
                    latitude=0.4, longitude=32.6, display_name="Inside",
                    provider="fake", resolved=True,
                ),
                GeocodeResult(
                    latitude=0.8, longitude=32.6, display_name="Outside",
                    provider="fake", resolved=True,
                ),
            ]

    monkeypatch.setattr("app.geo.routes._geo_cache_get", lambda key: None)
    monkeypatch.setattr("app.geo.routes._geo_cache_set", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.geo.services.build_geocoding_service",
        lambda config: FakeGeocoder(),
    )
    monkeypatch.setattr(
        "app.geo.service_areas.get_service_area_config",
        lambda: _area_config(),
    )

    response = anonymous_client.get(
        "/geo/api/geocode?service=transport&q=sample place"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["results"][0]["service_area"]["supported"] is True
    assert payload["results"][1]["service_area"]["supported"] is False
    assert "no-store" in response.headers["Cache-Control"]
