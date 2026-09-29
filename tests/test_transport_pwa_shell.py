"""J9 — Transport/rider PWA installability shell contract.

Pins the PWA shell so the driver/rider installable identity cannot
silently regress:
  * both manifests are valid JSON with coherent scope/start_url/icons;
  * every manifest icon src exists on disk with the declared dimensions;
  * both shells link exactly one manifest plus tab + iOS home-screen icons;
  * the driver service worker is publicly served with SW-safe headers;
  * global-manifest shortcuts resolve to registered routes.
"""
import json
import struct
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def _png_size(path: Path):
    with open(path, "rb") as fh:
        data = fh.read(33)
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", data[16:24])


def _load_manifest(name: str):
    path = STATIC / name
    assert path.exists(), f"manifest missing: {name}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_global_manifest_coherent():
    m = _load_manifest("manifest.json")
    assert m["scope"] == "/"
    assert m["start_url"].startswith("/")
    assert m["theme_color"] == m["background_color"] == "#667eea"
    sizes = set()
    for icon in m["icons"]:
        src = icon["src"]
        assert src.startswith("/static/")
        disk = STATIC / src[len("/static/"):]
        assert disk.exists(), f"manifest icon missing on disk: {src}"
        w, h = _png_size(disk)
        assert (w, h) == tuple(map(int, icon["sizes"].split("x"))), src
        sizes.add(icon["sizes"])
    assert {"192x192", "512x512"} <= sizes


def test_transport_manifest_coherent():
    m = _load_manifest("transport/manifest.json")
    assert m["scope"] == "/transport/"
    assert m["start_url"].startswith(m["scope"]), m["start_url"]
    for icon in m["icons"]:
        assert icon["src"].startswith("/static/")
        disk = STATIC / icon["src"][len("/static/"):]
        assert disk.exists(), f"transport icon missing: {icon['src']}"
        w, h = _png_size(disk)
        assert (w, h) == tuple(map(int, icon["sizes"].split("x")))


def test_shells_link_one_manifest_plus_icons():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert base.count('rel="manifest"') == 1
    assert "manifest.json" in base
    assert 'rel="icon"' in base
    assert 'rel="apple-touch-icon"' in base

    driver = (TEMPLATES / "transport/driver/base.html").read_text(
        encoding="utf-8"
    )
    assert driver.count('rel="manifest"') == 1
    assert "transport/manifest.json" in driver
    assert 'rel="icon"' in driver
    assert 'rel="apple-touch-icon"' in driver


def test_pwa_assets_served(client):
    for url, ctype in (
        ("/static/manifest.json", "application/json"),
        ("/static/transport/manifest.json", "application/json"),
        ("/static/icons/icon-192.png", "image/png"),
        ("/static/icons/icon-512.png", "image/png"),
    ):
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert ctype in resp.headers.get("Content-Type", ""), url


def test_driver_service_worker_public(client):
    resp = client.get("/transport/sw.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("Content-Type", "")
    assert resp.headers.get("Service-Worker-Allowed") == "/transport/"
    assert "no-store" in resp.headers.get("Cache-Control", "")


def test_global_shortcuts_resolve(client):
    assert client.get("/wallet/dashboard", follow_redirects=False).status_code in (
        200, 302,
    )
    assert client.get("/events", follow_redirects=False).status_code in (
        200, 302, 308,
    )
