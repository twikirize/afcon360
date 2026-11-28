import pytest

from app.geo.service_areas import (
    assess_driver_for_pickup_area,
    assess_service_area_trip,
    check_service_area_point,
    point_in_geometry,
    validate_geometry,
    validate_service_area_config,
)


def polygon(west=32.0, south=0.0, east=33.0, north=1.0):
    return {
        "type": "Polygon",
        "coordinates": [[
            [west, south], [east, south], [east, north],
            [west, north], [west, south],
        ]],
    }


def area(area_id="kampala", name="Kampala", geometry=None, active=True):
    return {
        "id": area_id, "name": name, "country_code": "UG",
        "active": active, "services": ["transport"],
        "geometry": geometry or polygon(),
    }


def config(*areas, enabled=True, cross=False):
    return {
        "version": 1, "enabled": enabled,
        "allow_cross_area_routes": cross, "areas": list(areas),
    }


def test_point_inside_and_polygon_boundary_are_supported():
    geometry = polygon()
    assert point_in_geometry(0.5, 32.5, geometry)
    assert point_in_geometry(0.0, 32.5, geometry)
    assert not point_in_geometry(1.1, 32.5, geometry)


def test_polygon_hole_is_excluded():
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [[32, 0], [33, 0], [33, 1], [32, 1], [32, 0]],
            [[32.2, 0.2], [32.8, 0.2], [32.8, 0.8],
             [32.2, 0.8], [32.2, 0.2]],
        ],
    }
    assert point_in_geometry(0.1, 32.1, geometry)
    assert not point_in_geometry(0.5, 32.5, geometry)


def test_multipolygon_supports_separate_service_pockets():
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            polygon(32, 0, 33, 1)["coordinates"],
            polygon(34, 0, 35, 1)["coordinates"],
        ],
    }
    assert point_in_geometry(0.5, 32.5, geometry)
    assert point_in_geometry(0.5, 34.5, geometry)
    assert not point_in_geometry(0.5, 33.5, geometry)


def test_invalid_or_unclosed_polygon_is_rejected():
    bad = polygon()
    bad["coordinates"][0][-1] = [32.5, 0.5]
    with pytest.raises(ValueError, match="must be closed"):
        validate_geometry(bad)


def test_inactive_area_does_not_grant_service():
    result = check_service_area_point(
        0.5, 32.5, config=config(area(active=False))
    )
    assert result["enabled"] is True
    assert result["supported"] is False
    assert result["reason"] == "no_active_service_area"


def test_disabled_geofencing_bypasses_area_restriction():
    result = check_service_area_point(
        -1.0, 35.0, config=config(area(), enabled=False)
    )
    assert result["supported"] is True
    assert result["reason"] == "geofencing_disabled"


def test_trip_requires_both_endpoints_in_same_area_by_default():
    settings = config(
        area(),
        area("nairobi", "Nairobi", polygon(36, -2, 38, 1)),
    )
    trip = assess_service_area_trip(
        {"latitude": 0.5, "longitude": 32.5},
        {"latitude": -1.0, "longitude": 37.0},
        config=settings,
    )
    assert trip["supported"] is False
    assert trip["reason"] == "cross_area_route_not_enabled"


def test_cross_area_trip_can_be_enabled_explicitly():
    settings = config(
        area(),
        area("nairobi", "Nairobi", polygon(36, -2, 38, 1)),
        cross=True,
    )
    trip = assess_service_area_trip(
        {"latitude": 0.5, "longitude": 32.5},
        {"latitude": -1.0, "longitude": 37.0},
        config=settings,
    )
    assert trip["supported"] is True


def test_non_transport_area_does_not_enable_rides():
    accommodation = area()
    accommodation["services"] = ["accommodation"]
    result = check_service_area_point(
        0.5, 32.5, config=config(accommodation)
    )
    assert result["supported"] is False
    assert result["reason"] == "no_active_service_area"


def test_admin_config_rejects_duplicate_area_ids():
    with pytest.raises(ValueError, match="Duplicate"):
        validate_service_area_config(config(area(), area()))



def test_driver_must_be_in_same_active_area_as_pickup():
    settings = config(area())
    accepted = assess_driver_for_pickup_area(
        0.6, 32.6, 0.5, 32.5, config=settings
    )
    outside = assess_driver_for_pickup_area(
        1.5, 32.5, 0.5, 32.5, config=settings
    )
    assert accepted["supported"] is True
    assert outside["supported"] is False
    assert outside["reason"] == "driver_outside_active_area"


def test_driver_in_different_active_city_is_not_matched_to_pickup():
    settings = config(
        area(),
        area("nairobi", "Nairobi", polygon(36, -2, 38, 1)),
        cross=True,
    )
    result = assess_driver_for_pickup_area(
        -1.0, 37.0, 0.5, 32.5, config=settings
    )
    assert result["supported"] is False
    assert result["reason"] == "driver_in_different_service_area"


def test_driver_area_check_is_bypassed_when_geofencing_disabled():
    result = assess_driver_for_pickup_area(
        -1.0, 37.0, 0.5, 32.5,
        config=config(area(), enabled=False),
    )
    assert result["supported"] is True
    assert result["reason"] == "geofencing_disabled"


def test_cannot_enable_geofencing_without_active_transport_area():
    with pytest.raises(ValueError, match="at least one active service area"):
        validate_service_area_config(
            config(area(active=False), enabled=True)
        )



def test_non_transport_area_can_enable_global_geofence():
    tourism = area()
    tourism["services"] = ["tourism"]
    result = validate_service_area_config(config(tourism, enabled=True))
    assert result["enabled"] is True
    assert result["areas"][0]["services"] == ["tourism"]


def test_service_area_error_identifies_unsupported_place():
    from app.geo.service_areas import service_area_error

    status = check_service_area_point(
        -1.0, 35.0, config=config(area())
    )
    status["field"] = "location"
    assert "outside Pamoja's currently supported service areas" in service_area_error(status)
