# app/geo/providers/base.py
"""
AFCON360 GEO - provider adapter base.

Every adapter MUST:
- implement one of the interfaces in app.geo.interfaces
- NEVER leak provider SDK objects to domain callers (return value objects)
- return truthful unresolved results on outage (never fake coordinates)
- expose name + is_available() for health/observability
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderHealth:
    name: str
    available: bool
    latency_ms: float = 0.0
    last_success: str = ""
    last_error: str = ""


class BaseProvider:
    name = "base"

    def is_available(self) -> bool:
        return False

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name,
                              available=self.is_available())


class ProviderFailure(Exception):
    """Explicit operational provider failure (transport / HTTP error /
    malformed provider payload).

    Raised ONLY for failures that must trigger fallback to the next
    provider in the chain. A valid provider response with zero useful
    candidates is NOT a failure: adapters return [] for that case and
    the service treats it as an honest no-result WITHOUT fallback.
    The service converts this exception into fallback-or-unresolved;
    it never reaches API callers.
    """
