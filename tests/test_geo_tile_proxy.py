"""GEO — server-side raster tile proxy (map availability contract).

Proves the map fix at the HTTP boundary:

  * ``GET /geo/api/tiles/<z>/<x>/<y>.png`` is a DISCOVERY endpoint: an
    anonymous rider gets tiles, exactly like geocode/reverse. A map outage
    must never block the search-and-book path.
  * our server is the only caller of the upstream, and it identifies itself
    with a first-party User-Agent (the reason OpenStreetMap answered the app
    with "418 Access blocked");
  * tiles are cached, so panning a map does not re-fetch the same tile;
  * an impossible index answers 404 with zero upstream traffic; an upstream
    refusal, timeout or non-image answer becomes 502, never a 500 and never a
    grey tile pretending to be a map;
  * the OSM attribution travels on every answered tile.

The upstream is always a controlled localhost fake — no external traffic.
"""

import base64
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

URL = "/geo/api/tiles/12/3287/2074.png"

# 1x1 transparent PNG — a real image body, not a placeholder string.
TILE_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYA"
    "AjCB0C8AAAAASUVORK5CYII="
)


class _FakeTiles(BaseHTTPRequestHandler):
    mode = "ok"
    calls = []

    def log_message(self, *args):  # keep pytest output clean
        pass

    def do_GET(self):
        type(self).calls.append({
            "path": self.path,
            "user_agent": self.headers.get("User-Agent", ""),
        })
        if type(self).mode == "error":
            self.send_response(500)
            self.end_headers()
            return
        if type(self).mode == "not_image":
            body = b'{"success": false}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(TILE_BYTES)))
        self.end_headers()
        self.wfile.write(TILE_BYTES)


@pytest.fixture()
def fake_tiles(monkeypatch):
    _FakeTiles.calls = []
    _FakeTiles.mode = "ok"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeTiles)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("GEO_TILES_UPSTREAM_URL", base_url + "/{z}/{x}/{y}.png")
    yield base_url, _FakeTiles
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture()
def memory_tile_cache(monkeypatch):
    """Deterministic cache for the cache-contract test (Redis is off in tests)."""
    from app.geo import tile_proxy

    store = {}
    monkeypatch.setattr(tile_proxy, "_cache_get", lambda key: store.get(key))
    monkeypatch.setattr(tile_proxy, "_cache_set", lambda key, body: store.__setitem__(key, body))
    return store


def test_anonymous_rider_receives_a_tile(anonymous_client, fake_tiles):
    resp = anonymous_client.get(URL)
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"
    assert resp.data == TILE_BYTES
    assert resp.headers["X-Pamoja-Tile-Source"] == "upstream"
    assert resp.headers["X-Pamoja-Tile-Attribution"]
    assert "immutable" in resp.headers["Cache-Control"]


def test_server_identifies_itself_to_the_upstream(anonymous_client, fake_tiles):
    """The upstream must see a first-party User-Agent, not the app's."""
    _, handler = fake_tiles
    anonymous_client.get(URL)
    assert handler.calls, "the upstream was never called"
    assert handler.calls[0]["user_agent"].startswith("Pamoja/")
    assert handler.calls[0]["path"].endswith("/12/3287/2074.png")


def test_repeat_tile_is_served_from_cache(anonymous_client, fake_tiles, memory_tile_cache):
    _, handler = fake_tiles
    first = anonymous_client.get(URL)
    second = anonymous_client.get(URL)
    assert first.status_code == second.status_code == 200
    assert second.headers["X-Pamoja-Tile-Source"] == "cache"
    assert second.data == TILE_BYTES
    assert len(handler.calls) == 1, "a cached tile must not re-fetch the upstream"


@pytest.mark.parametrize("path", [
    "/geo/api/tiles/24/1/1.png",      # zoom beyond the layer's ceiling
    "/geo/api/tiles/3/9/1.png",       # x outside 0..2^z-1
    "/geo/api/tiles/3/1/9.png",       # y outside 0..2^z-1
])
def test_impossible_index_is_404_without_upstream_traffic(anonymous_client, fake_tiles, path):
    _, handler = fake_tiles
    resp = anonymous_client.get(path)
    assert resp.status_code == 404
    assert resp.headers["X-Pamoja-Tile-Status"] == "invalid_index"
    assert handler.calls == []


def test_upstream_error_answers_502_not_500(anonymous_client, fake_tiles):
    _, handler = fake_tiles
    handler.mode = "error"
    resp = anonymous_client.get(URL)
    assert resp.status_code == 502
    assert resp.headers["X-Pamoja-Tile-Status"] == "upstream_unavailable"
    assert resp.headers["Cache-Control"] == "no-store"


def test_upstream_non_image_answers_502(anonymous_client, fake_tiles):
    _, handler = fake_tiles
    handler.mode = "not_image"
    resp = anonymous_client.get(URL)
    assert resp.status_code == 502
    assert resp.headers["X-Pamoja-Tile-Status"] == "upstream_not_image"


def test_missing_redis_degrades_to_direct_fetch_without_error(app, anonymous_client, fake_tiles):
    """Redis is disabled in the suite; tiles must still be served."""
    with app.app_context():
        from app.geo import tile_proxy

        body, source = tile_proxy.fetch_tile(12, 3287, 2074)
    assert body == TILE_BYTES
    assert source in ("upstream", "cache")
