"""Owner routing selection contract tests (no credentials, no I/O)."""

import pytest

from app.geo.config import GeoConfig, RoutingConfig
from app.geo.routing_settings import (
    FALLBACKS_KEY,
    PROFILE_KEY,
    PROVIDER_KEY,
    adapter_status,
    apply_routing_selection,
    resolve_routing_selection,
    validate_selection,
)
from app.geo.providers.geoapify import GeoapifyConfig
from app.geo.providers.google import GoogleMapsConfig
from app.geo.providers.graphhopper import GraphHopperConfig
from app.geo.providers.ors import ORSConfig
from app.geo.providers.osrm import OSRMConfig
from app.geo.providers.photon import PhotonConfig
from app.geo.providers.tiles import TileProviderConfig
from app.geo.providers.valhalla import ValhallaConfig


def _patch_db(monkeypatch, mapping):
    from app.models.system_config import SystemConfig

    def fake_get(cls, key, default=None):
        return mapping.get(key, default)

    monkeypatch.setattr(SystemConfig, "get", classmethod(fake_get))


def test_validate_selection_normalizes_and_rejects_duplicate_primary():
    selection = validate_selection(" OSRM ", ["Geoapify", "geoapify"], "AUTO")
    assert selection.provider == "osrm"
    assert selection.fallbacks == ("geoapify",)
    assert selection.profile == "auto"
    with pytest.raises(ValueError):
        validate_selection("osrm", ["osrm"], "auto")
    with pytest.raises(ValueError):
        validate_selection("unresolved", ["geoapify"], "auto")
    with pytest.raises(ValueError):
        validate_selection("unknown-engine", [], "auto")
    with pytest.raises(ValueError):
        validate_selection("osrm", [], "flying")


def test_database_selection_overrides_environment(monkeypatch):
    _patch_db(monkeypatch, {
        PROVIDER_KEY: "google",
        FALLBACKS_KEY: "ors, geoapify",
        PROFILE_KEY: "motorcycle",
    })
    base = RoutingConfig(provider="valhalla", fallbacks=("osrm",), profile="auto")
    selection = resolve_routing_selection(base)
    assert selection.provider == "google"
    assert selection.fallbacks == ("ors", "geoapify")
    assert selection.profile == "motorcycle"
    assert selection.source == "database"
    assert selection.allow_legacy_fallback is False


def test_no_database_selection_keeps_environment(monkeypatch):
    _patch_db(monkeypatch, {})
    base = RoutingConfig(provider="osrm", fallbacks=("geoapify",),
                         profile="pedestrian")
    selection = resolve_routing_selection(base)
    assert selection.provider == "osrm"
    assert selection.fallbacks == ("geoapify",)
    assert selection.profile == "pedestrian"
    assert selection.source == "environment"
    assert selection.allow_legacy_fallback is True


def test_invalid_database_selection_falls_back_to_environment(monkeypatch):
    _patch_db(monkeypatch, {PROVIDER_KEY: "not-an-engine"})
    base = RoutingConfig(provider="osrm")
    selection = resolve_routing_selection(base)
    assert selection.provider == "osrm"
    assert selection.source == "environment"


def test_apply_selection_disables_legacy_fallback_for_explicit_db(monkeypatch):
    _patch_db(monkeypatch, {PROVIDER_KEY: "unresolved"})
    config = GeoConfig(
        valhalla=ValhallaConfig(base_url="http://valhalla.test", enabled=True),
        photon=PhotonConfig(),
        tiles=TileProviderConfig(),
    )
    effective = apply_routing_selection(config)
    assert effective.routing.provider == "unresolved"
    assert effective.routing.allow_legacy_fallback is False


def test_save_roundtrip_stores_only_selection(app, db_session):
    from app.extensions import db
    from app.models.system_config import SystemConfig
    from app.geo.routing_settings import save_routing_selection

    keys = (PROVIDER_KEY, FALLBACKS_KEY, PROFILE_KEY)
    originals = {key: SystemConfig.get(key, None) for key in keys}
    try:
        save_routing_selection("google", ["ors", "geoapify"], "motorcycle")
        selection = resolve_routing_selection(RoutingConfig())
        assert selection.provider == "google"
        assert selection.fallbacks == ("ors", "geoapify")
        assert selection.profile == "motorcycle"
        assert selection.source == "database"
        for key in keys:
            row = SystemConfig.query.filter_by(key=key).first()
            assert row is not None
            assert row.category == "transport_routing"
            assert "secret" not in (row.value or "").lower()

        save_routing_selection("osrm", [], "auto")
        selection = resolve_routing_selection(
            RoutingConfig(fallbacks=("geoapify",)))
        assert selection.provider == "osrm"
        assert selection.fallbacks == ()
    finally:
        for key, original in originals.items():
            row = SystemConfig.query.filter_by(key=key).first()
            if original is None:
                if row is not None:
                    db.session.delete(row)
            elif row is not None:
                row.value = original
        db.session.commit()


def test_adapter_status_never_contains_credentials():
    config = GeoConfig(
        valhalla=ValhallaConfig(base_url="http://valhalla.test", enabled=True),
        photon=PhotonConfig(),
        tiles=TileProviderConfig(),
        geoapify=GeoapifyConfig(base_url="http://geoapify.test",
                                api_key="geo-secret", enabled=True),
        osrm=OSRMConfig(base_url="http://osrm.test", enabled=True),
        graphhopper=GraphHopperConfig(base_url="http://gh.test",
                                      api_key="gh-secret", enabled=True),
        ors=ORSConfig(base_url="http://ors.test", api_key="ors-secret",
                      enabled=True),
        google=GoogleMapsConfig(base_url="http://google.test",
                                api_key="google-secret", enabled=True),
    )
    status = adapter_status(config)
    assert status["google"] == {"enabled": True, "configured": True}
    assert "secret" not in repr(status)
