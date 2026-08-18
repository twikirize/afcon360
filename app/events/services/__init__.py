"""Compatibility exports for Event services."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_legacy_path = Path(__file__).resolve().parent.parent / "services.py"
_legacy_spec = spec_from_file_location("app.events._legacy_services", _legacy_path)
_legacy = module_from_spec(_legacy_spec)
_legacy_spec.loader.exec_module(_legacy)

EventService = _legacy.EventService
IdempotencyChecker = _legacy.IdempotencyChecker
SoldOutException = getattr(_legacy, "SoldOutException", Exception)

from app.events.services.guest_coordination_service import (  # noqa: E402
    CoordinationError,
    GuestCoordinationService,
)

__all__ = [
    "CoordinationError",
    "EventService",
    "IdempotencyChecker",
    "GuestCoordinationService",
    "SoldOutException",
]
