# app/geo/providers/__init__.py
"""AFCON360 GEO provider adapters (Geoapify / Valhalla / Photon / tiles)."""

from app.geo.providers.base import (BaseProvider, ProviderFailure,
                                      ProviderHealth)
from app.geo.providers.geoapify import GeoapifyConfig, GeoapifyGeocoder
from app.geo.providers.photon import PhotonConfig, PhotonGeocoder
from app.geo.providers.tiles import TileProviderAdapter, TileProviderConfig
from app.geo.providers.valhalla import ValhallaConfig, ValhallaRouter

__all__ = [
    "BaseProvider",
    "ProviderFailure",
    "ProviderHealth",
    "GeoapifyConfig",
    "GeoapifyGeocoder",
    "PhotonConfig",
    "PhotonGeocoder",
    "TileProviderAdapter",
    "TileProviderConfig",
    "ValhallaConfig",
    "ValhallaRouter",
]
