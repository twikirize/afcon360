# app/geo/providers/__init__.py
"""AFCON360 GEO provider adapters (routing / geocoding / tiles)."""

from app.geo.providers.base import (BaseProvider, ProviderFailure,
                                      ProviderHealth)
from app.geo.providers.geoapify import GeoapifyConfig, GeoapifyGeocoder
from app.geo.providers.geoapify_routing import GeoapifyRouter
from app.geo.providers.google import GoogleMapsConfig, GoogleMapsRouter
from app.geo.providers.graphhopper import (GraphHopperConfig,
                                           GraphHopperRouter)
from app.geo.providers.ors import ORSConfig, ORSRouter
from app.geo.providers.osrm import OSRMConfig, OSRMRouter
from app.geo.providers.photon import PhotonConfig, PhotonGeocoder
from app.geo.providers.tiles import TileProviderAdapter, TileProviderConfig
from app.geo.providers.valhalla import ValhallaConfig, ValhallaRouter

__all__ = [
    "BaseProvider",
    "ProviderFailure",
    "ProviderHealth",
    "GeoapifyConfig",
    "GeoapifyGeocoder",
    "GeoapifyRouter",
    "GoogleMapsConfig",
    "GoogleMapsRouter",
    "GraphHopperConfig",
    "GraphHopperRouter",
    "ORSConfig",
    "ORSRouter",
    "OSRMConfig",
    "OSRMRouter",
    "PhotonConfig",
    "PhotonGeocoder",
    "TileProviderAdapter",
    "TileProviderConfig",
    "ValhallaConfig",
    "ValhallaRouter",
]
