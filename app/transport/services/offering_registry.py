"""AFCON360 Transport - TransportOffering catalog registry (TH-3-D3).

Read-only accessor. Caches primitive snapshots, never ORM objects.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.extensions import db, cache
from app.transport.models import TransportOffering

logger = logging.getLogger(__name__)

_CACHE_KEY = "transport:offerings:active:v1"
_CACHE_TTL = 300

_DEFAULT_OFFERINGS = (
    {"code": "cab_solo",   "display_name": "Cab (Solo)",   "min_seats": 1,  "max_seats": 1,  "default_seats": 1,  "booking_mode": "private"},
    {"code": "cab_family", "display_name": "Cab (Family)", "min_seats": 1,  "max_seats": 4,  "default_seats": 4,  "booking_mode": "private"},
    {"code": "van",        "display_name": "Van",          "min_seats": 4,  "max_seats": 20, "default_seats": 12, "booking_mode": "private"},
    {"code": "shuttle",    "display_name": "Shuttle",      "min_seats": 6,  "max_seats": 20, "default_seats": 14, "booking_mode": "shared"},
    {"code": "minibus",    "display_name": "Minibus",      "min_seats": 10, "max_seats": 30, "default_seats": 20, "booking_mode": "shared"},
    {"code": "bus",        "display_name": "Bus",          "min_seats": 30, "max_seats": 60, "default_seats": 50, "booking_mode": "shared"},
    {"code": "coach",      "display_name": "Coach",        "min_seats": 40, "max_seats": 80, "default_seats": 60, "booking_mode": "shared"},
)


class TransportOfferingRegistry:

    @staticmethod
    def get(offering_code: str) -> Optional[TransportOffering]:
        if not offering_code:
            return None
        # Always read from DB — the catalog is small and changes are rare,
        # so we prefer a single source of truth over a stale ORM cache.
        return TransportOffering.query.filter_by(
            code=str(offering_code).strip().lower(),
            is_active=True,
            is_deleted=False,
        ).first()

    @staticmethod
    def list_active_snapshots() -> List[Dict]:
        """Return primitive snapshots for read-only consumers.

        Cache stores primitives, not ORM objects.
        """
        try:
            cached = cache.get(_CACHE_KEY)
            if cached:
                return cached
        except Exception:
            cached = None

        rows = (
            TransportOffering.query
            .filter_by(is_active=True, is_deleted=False)
            .order_by(TransportOffering.code.asc())
            .all()
        )
        snapshots = [
            {
                "id": r.id,
                "code": r.code,
                "display_name": r.display_name,
                "min_seats": r.min_seats,
                "max_seats": r.max_seats,
                "default_seats": r.default_seats,
                "booking_mode": r.booking_mode,
            }
            for r in rows
        ]
        try:
            cache.set(_CACHE_KEY, snapshots, timeout=_CACHE_TTL)
        except Exception:
            pass
        return snapshots

    @staticmethod
    def ensure_defaults() -> int:
        created = 0
        for spec in _DEFAULT_OFFERINGS:
            exists = TransportOffering.query.filter_by(
                code=spec["code"], is_deleted=False
            ).first()
            if exists:
                continue
            db.session.add(TransportOffering(**spec))
            created += 1
        if created:
            db.session.commit()
            TransportOfferingRegistry.invalidate_cache()
            logger.info("Seeded %d default offerings", created)
        return created

    @staticmethod
    def invalidate_cache() -> None:
        try:
            cache.delete(_CACHE_KEY)
        except Exception:
            pass


def get_offering_registry():
    return TransportOfferingRegistry