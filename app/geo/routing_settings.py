# app/geo/routing_settings.py
"""
Owner-selectable routing provider configuration.

Provider credentials NEVER live here. They stay in the environment
(``GEO_*`` variables) and are read by ``app.geo.config``. This module only
stores the non-secret selection in ``SystemConfig``:

    TRANSPORT_ROUTING_PROVIDER   valhalla|osrm|geoapify|graphhopper|ors|google|unresolved
    TRANSPORT_ROUTING_FALLBACKS  comma-separated provider names
    TRANSPORT_ROUTING_PROFILE    auto|motorcycle|pedestrian|bicycle|scooter|truck

When no database selection exists, the environment/Flask configuration is
used unchanged. The owner page can override the selection at runtime and
the routing singleton is rebuilt by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Tuple

from app.geo.config import GeoConfig, RoutingConfig, load_geo_config

PROVIDER_KEY = "TRANSPORT_ROUTING_PROVIDER"
FALLBACKS_KEY = "TRANSPORT_ROUTING_FALLBACKS"
PROFILE_KEY = "TRANSPORT_ROUTING_PROFILE"
CATEGORY = "transport_routing"

ALLOWED_PROVIDERS: Tuple[str, ...] = (
    "unresolved", "valhalla", "osrm", "geoapify", "graphhopper", "ors",
    "google",
)
ALLOWED_PROFILES: Tuple[str, ...] = (
    "auto", "motorcycle", "pedestrian", "bicycle", "scooter", "truck",
)

PROVIDER_LABELS = {
    "unresolved": "No road routing (straight-line fallback)",
    "valhalla": "Valhalla",
    "osrm": "OSRM",
    "geoapify": "Geoapify",
    "graphhopper": "GraphHopper",
    "ors": "OpenRouteService (ORS)",
    "google": "Google Maps Directions",
}

_MISSING = object()


@dataclass(frozen=True)
class RoutingSelection:
    provider: str
    fallbacks: Tuple[str, ...]
    profile: str
    source: str = "environment"
    allow_legacy_fallback: bool = True


def _read_db_value(key: str):
    try:
        from app.models.system_config import SystemConfig
        return SystemConfig.get(key, _MISSING)
    except Exception:
        return _MISSING


def _normalize_provider(value) -> str:
    provider = str(value or "").strip().lower()
    if provider in ("", "none"):
        provider = "unresolved"
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError(f"Unknown routing provider: {value!r}")
    return provider


def _normalize_profile(value) -> str:
    profile = str(value or "auto").strip().lower()
    if profile not in ALLOWED_PROFILES:
        raise ValueError(f"Unknown routing profile: {value!r}")
    return profile


def _normalize_fallbacks(value: object) -> Tuple[str, ...]:
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        parts = list(value)
    else:
        parts = []
    seen = set()
    ordered = []
    for part in parts:
        provider = str(part or "").strip().lower()
        if provider in ("", "none", "unresolved"):
            continue
        if provider not in ALLOWED_PROVIDERS:
            raise ValueError(f"Unknown routing fallback: {part!r}")
        if provider not in seen:
            seen.add(provider)
            ordered.append(provider)
    return tuple(ordered)


def validate_selection(provider, fallbacks, profile) -> RoutingSelection:
    """Strictly validate an owner form selection. Raises ValueError."""
    normalized_provider = _normalize_provider(provider)
    normalized_fallbacks = _normalize_fallbacks(fallbacks)
    if normalized_provider == "unresolved" and normalized_fallbacks:
        raise ValueError(
            "Choose a primary provider to use fallbacks, or clear all fallbacks")
    if normalized_provider in normalized_fallbacks:
        raise ValueError("The primary provider cannot also be a fallback")
    return RoutingSelection(
        provider=normalized_provider,
        fallbacks=normalized_fallbacks,
        profile=_normalize_profile(profile),
        source="database",
        allow_legacy_fallback=False,
    )


def resolve_routing_selection(
        base: RoutingConfig | None = None) -> RoutingSelection:
    """Resolve DB selection over environment defaults without raising."""
    base = base or RoutingConfig()
    raw_provider = _read_db_value(PROVIDER_KEY)
    raw_fallbacks = _read_db_value(FALLBACKS_KEY)
    raw_profile = _read_db_value(PROFILE_KEY)

    has_database_value = any(
        value is not _MISSING
        for value in (raw_provider, raw_fallbacks, raw_profile))

    provider = (base.provider
                if raw_provider is _MISSING or raw_provider in (None, "")
                else str(raw_provider))
    fallbacks = (base.fallbacks
                 if raw_fallbacks is _MISSING
                 else _normalize_fallbacks(raw_fallbacks))
    profile = (base.profile
               if raw_profile is _MISSING or raw_profile in (None, "")
               else str(raw_profile))

    try:
        return RoutingSelection(
            provider=_normalize_provider(provider),
            fallbacks=_normalize_fallbacks(fallbacks),
            profile=_normalize_profile(profile),
            source="database" if has_database_value else "environment",
            allow_legacy_fallback=not has_database_value,
        )
    except ValueError:
        return RoutingSelection(
            provider=_normalize_provider(base.provider),
            fallbacks=_normalize_fallbacks(base.fallbacks),
            profile=_normalize_profile(base.profile),
            source="environment",
            allow_legacy_fallback=True,
        )


def apply_routing_selection(config: GeoConfig,
                            selection: RoutingSelection | None = None
                            ) -> GeoConfig:
    """Return GeoConfig with the resolved routing selection applied."""
    base = getattr(config, "routing", None) or RoutingConfig()
    selection = selection or resolve_routing_selection(base)
    return replace(
        config,
        routing=replace(
            base,
            provider=selection.provider,
            fallbacks=selection.fallbacks,
            profile=selection.profile,
            allow_legacy_fallback=selection.allow_legacy_fallback,
        ),
    )


def load_effective_geo_config(app=None) -> GeoConfig:
    """Environment config plus the owner-selected DB routing override."""
    return apply_routing_selection(load_geo_config(app))


def save_routing_selection(provider, fallbacks, profile,
                           updated_by=None, commit: bool = True
                           ) -> RoutingSelection:
    """Persist a validated selection. Never stores credentials."""
    selection = validate_selection(provider, fallbacks, profile)
    from app.extensions import db
    from app.models.system_config import SystemConfig

    SystemConfig.set(
        PROVIDER_KEY, selection.provider, value_type="str",
        category=CATEGORY,
        description="Owner-selected transport routing provider (no keys)",
        updated_by=updated_by, commit=False)
    SystemConfig.set(
        FALLBACKS_KEY, ",".join(selection.fallbacks) or "none",
        value_type="str", category=CATEGORY,
        description="Ordered routing fallbacks (no keys)",
        updated_by=updated_by, commit=False)
    SystemConfig.set(
        PROFILE_KEY, selection.profile, value_type="str",
        category=CATEGORY,
        description="Routing profile for transport quotes",
        updated_by=updated_by, commit=False)
    if commit:
        db.session.commit()
    return selection


def adapter_status(config: GeoConfig) -> dict:
    """Configured/enabled booleans only; never key values."""
    def status(section, needs_key=False):
        section = getattr(config, section, None)
        configured = bool(getattr(section, "base_url", ""))
        if needs_key:
            configured = configured and bool(getattr(section, "api_key", ""))
        return {
            "enabled": bool(getattr(section, "enabled", False)),
            "configured": configured,
        }

    return {
        "valhalla": status("valhalla"),
        "osrm": status("osrm"),
        "geoapify": status("geoapify", needs_key=True),
        "graphhopper": status("graphhopper", needs_key=True),
        "ors": status("ors", needs_key=True),
        "google": status("google", needs_key=True),
    }
