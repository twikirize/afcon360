"""RIDER-ROAD-ROUTE-PREVIEW-01 website contract checks."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_rider_page_loads_road_route_preview_styles_and_script():
    template = _read("templates/transport/new_home.html")
    assert "css/modules/transport/road-route-preview.css" in template
    assert "js/modules/transport/road-route-preview.js" in template
    assert 'id="roadRouteSummary"' in template
    assert "transport_api.route_preview" in template
    assert 'id="roadRouteRetry"' in template


def test_route_preview_client_uses_same_origin_api_and_csrf():
    client = _read("static/js/modules/transport/road-route-preview.js")
    assert "summary.getAttribute('data-endpoint')" in client
    assert "X-CSRFToken" in client
    assert "credentials: 'same-origin'" in client
    assert "method: 'POST'" in client
    assert "AbortController" in client
    assert "mySequence !== sequence" in client


def test_route_preview_client_never_calls_valhalla_or_fabricates_route():
    client = _read("static/js/modules/transport/road-route-preview.js")
    assert "valhalla1.openstreetmap.de" not in client
    assert "https://valhalla" not in client
    assert "window.__mapRenderRoadRoute(data.geometry)" in client
    assert "window.__mapClearRoadRoute()" in client
    assert "resolved !== true" in client
    assert "distance_m" in client and "duration_s" in client
    assert "straight_line_distance" not in client


def test_rider_map_draws_only_provider_geometry_not_endpoint_connector():
    template = _read("templates/transport/new_home.html")
    start = template.index("window.__mapRenderRoadRoute = function(geometry)")
    end = template.index("function writeFields()", start)
    map_adapter = template[start:end]
    assert "L.polyline(points" in map_adapter
    assert "point.latitude" in map_adapter
    assert "point.longitude" in map_adapter
    assert "L.polyline([[p.lat, p.lng], [d.lat, d.lng]]" not in template
    assert "dashArray: '8 8'" not in template
    assert "afcon360:route-preview-inputs-changed" in template


def test_route_preview_is_visually_mobile_responsive_and_truthful():
    css = _read("static/css/modules/transport/road-route-preview.css")
    template = _read("templates/transport/new_home.html")
    assert "@media (max-width: 420px)" in css
    assert '.road-route-summary[hidden]' in css
    preview_client = _read("static/js/modules/transport/road-route-preview.js")
    assert "Preliminary road route" in preview_client
    assert "afcon360:fare-route-resolved" in preview_client
    assert "This is the exact road route used to calculate the fare options" in preview_client
    assert "fare estimates continue to use straight-line distance" not in template


def test_ride_options_uses_server_road_measurement_for_signed_fare_quotes():
    ride_options = _read("app/transport/api/ride_options_routes.py")
    assert "measure_road_route(pickup, dropoff)" in ride_options
    assert 'distance_basis = route["distance_basis"]' in ride_options
    assert "route_duration_s=route[\"duration_s\"]" in ride_options
    assert "route_provider=route[\"provider\"]" in ride_options
    assert "issue_fare_quote(" in ride_options
    assert "straight_line" not in ride_options
