"""Fix 2.4 proof: tile provider supplied by config, not hardcoded.

Three tests, per docs/transport/fixes/Fix-2.4-contract.md Section 6:

1. test_default_config_uses_osm — with no env override, the base Config
   class resolves both keys to their OSM defaults.
2. test_env_override_changes_url_template — an env override is picked up
   because the module is reloaded so the os.getenv(...) defaults are
   re-read. Env is restored (monkeypatch.undo) and the module reloaded
   again so no sentinel bakes into the Config class.
3. test_both_templates_render_config_values — both rider templates render
   the configured URL/attribution (positive) and neither contains the OSM
   hardcode (negative). This formalizes the manual proof: real app, real
   test client, sentinel config, assert rendered HTML.

No conftest.py changes: all fixtures come from tests/conftest.py.
"""
from importlib import reload

import app.config as app_config

OSM_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = "\u00a9 OpenStreetMap"

SENTINEL_TILE_URL = "https://tiles.example.test/{z}/{x}/{y}.png"
SENTINEL_ATTRIBUTION = "Tiles <a href='https://example.test'>Example</a> Tiles"


def test_default_config_uses_osm(monkeypatch):
    monkeypatch.delenv("TILE_PROVIDER_URL_TEMPLATE", raising=False)
    monkeypatch.delenv("TILE_PROVIDER_ATTRIBUTION", raising=False)
    reload(app_config)
    try:
        assert app_config.Config.TILE_PROVIDER_URL_TEMPLATE == OSM_TILE_URL
        assert app_config.Config.TILE_PROVIDER_ATTRIBUTION == OSM_ATTRIBUTION
    finally:
        reload(app_config)


def test_env_override_changes_url_template(monkeypatch):
    monkeypatch.setenv("TILE_PROVIDER_URL_TEMPLATE", SENTINEL_TILE_URL)
    monkeypatch.setenv("TILE_PROVIDER_ATTRIBUTION", SENTINEL_ATTRIBUTION)
    reload(app_config)
    try:
        assert app_config.Config.TILE_PROVIDER_URL_TEMPLATE == SENTINEL_TILE_URL
        assert app_config.Config.TILE_PROVIDER_ATTRIBUTION == SENTINEL_ATTRIBUTION
    finally:
        monkeypatch.undo()
        reload(app_config)


def test_both_templates_render_config_values(app, client):
    app.config.update(
        TILE_PROVIDER_URL_TEMPLATE=SENTINEL_TILE_URL,
        TILE_PROVIDER_ATTRIBUTION=SENTINEL_ATTRIBUTION,
    )

    for path, template in [
        ("/transport/", "home.html"),
        ("/transport/new-home", "new_home.html"),
    ]:
        resp = client.get(path)
        assert resp.status_code == 200, (
            f"{path} returned {resp.status_code}; expected 200"
        )
        body = resp.get_data(as_text=True)
        assert f"tileUrl: '{SENTINEL_TILE_URL}'" in body, (
            f"{template} does not render the configured tile URL"
        )
        assert f'attribution: "{SENTINEL_ATTRIBUTION}"' in body, (
            f"{template} does not render the configured attribution"
        )
        assert OSM_TILE_URL not in body, (
            f"{template} still contains the hardcoded OSM tile URL"
        )