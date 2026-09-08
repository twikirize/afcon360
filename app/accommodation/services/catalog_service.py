# app/accommodation/services/catalog_service.py
"""
Catalog service — database-backed accommodation option sets.

The host listing forms read their options (property type, listing type,
cancellation policy tier, booking mode, currency, cancellation policy types,
phases, no-show charge types) from these source tables instead of Python
constants. When the lookup tables have not been created (pre-migration) or
are empty (pre-seed/test bootstrap), the functions fall back to the canonical
constants in ``app.accommodation.catalog_data`` so the forms never render
with zero options.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from sqlalchemy.exc import ProgrammingError

from app.extensions import db
from app.accommodation.catalog_data import (
    BOOKING_MODES,
    CANCELLATION_POLICY_TIERS,
    CANCELLATION_POLICY_TYPES,
    CANCELLATION_PHASES,
    NO_SHOW_CHARGE_TYPES,
    CURRENCIES,
    LISTING_TYPE_LABELS,
    PROPERTY_TYPE_CATALOG,
)
from app.accommodation.models.catalog import (
    AccommodationBookingMode,
    AccommodationCancellationPhaseConfig,
    AccommodationCancellationPolicyTypeConfig,
    AccommodationCurrency,
    AccommodationListingTypeConfig,
    AccommodationNoShowChargeTypeConfig,
    AccommodationPolicyTier,
    AccommodationPropertyTypeConfig,
    PropertyTypeHostType,
    PropertyTypeListingType,
)

ALL_LISTING_TYPES = ("entire_place", "private_room", "shared_room")
ALL_HOST_TYPES = ("individual", "organisation")


def _safe_query(query):
    """Execute a query, catching ProgrammingError (missing table) and returning empty list."""
    try:
        return query.all()
    except ProgrammingError:
        # Table doesn't exist yet (pre-migration) — rollback the aborted transaction
        # and fall back to constants
        db.session.rollback()
        return []


def _ordered_active(model):
    return _safe_query(
        db.session.query(model)
        .filter(model.is_active.is_(True))
        .order_by(model.sort_order, model.code)
    )


# ---------------------------------------------------------------------------
# Property types
# ---------------------------------------------------------------------------

def get_property_type_config_map() -> dict:
    """Return ``{code: {label, commercial, host_types, listing_types}}``.

    Reads from the DB lookup tables; falls back to ``catalog_data`` when the
    tables are missing (pre-migration) or empty (unseeded).
    """
    rows = _ordered_active(AccommodationPropertyTypeConfig)
    if not rows:
        return {
            code: {
                "label": meta["label"],
                "commercial": meta["commercial"],
                "host_types": list(meta["host_types"]),
                "listing_types": list(meta["listing_types"]),
            }
            for code, meta in PROPERTY_TYPE_CATALOG.items()
        }

    host_map = defaultdict(list)
    for row in _safe_query(db.session.query(PropertyTypeHostType)):
        host_map[row.property_type_code].append(row.host_type)
    listing_map = defaultdict(list)
    for row in _safe_query(db.session.query(PropertyTypeListingType)):
        listing_map[row.property_type_code].append(row.listing_type_code)

    result = {}
    for row in rows:
        code = row.code
        seed = PROPERTY_TYPE_CATALOG.get(code, {})
        result[code] = {
            "label": row.label,
            "commercial": row.commercial,
            "host_types": host_map.get(code) or list(seed.get("host_types", ALL_HOST_TYPES)),
            "listing_types": listing_map.get(code) or list(seed.get("listing_types", ALL_LISTING_TYPES)),
        }
    return result


def get_property_type_catalog() -> dict:
    """JS-facing catalog: ``{code: {label, listing_types, commercial}}``."""
    return {
        code: {
            "label": meta["label"],
            "listing_types": list(meta["listing_types"]),
            "commercial": meta["commercial"],
        }
        for code, meta in get_property_type_config_map().items()
    }


def property_types_for_host(host_type: str) -> list[tuple[str, str]]:
    """Return (value, label) property-type choices valid for a host type."""
    return [
        (code, meta["label"])
        for code, meta in get_property_type_config_map().items()
        if host_type in meta["host_types"]
    ]


# ---------------------------------------------------------------------------
# Listing types
# ---------------------------------------------------------------------------

def get_listing_type_labels() -> dict:
    """``{code: label}`` for listing types (DB-first, constant fallback)."""
    rows = _safe_query(db.session.query(AccommodationListingTypeConfig))
    if not rows:
        return dict(LISTING_TYPE_LABELS)
    return {row.code: row.label for row in rows}


def listing_types_for_property(property_type: str) -> list[tuple[str, str]]:
    """Return (value, label) listing-type choices valid for a property type."""
    catalog = get_property_type_config_map()
    labels = get_listing_type_labels()
    meta = catalog.get(property_type)
    allowed = meta["listing_types"] if meta else ALL_LISTING_TYPES
    return [(value, labels.get(value, value.title())) for value in allowed]


# ---------------------------------------------------------------------------
# Cancellation policy tiers (simple tiers for PropertyBookingPolicy + host form)
# ---------------------------------------------------------------------------

def cancellation_policy_options() -> list[dict]:
    """DB-backed policy tier options (code, label, description, icon)."""
    rows = _ordered_active(AccommodationPolicyTier)
    if not rows:
        return [dict(tier) for tier in CANCELLATION_POLICY_TIERS]
    return [
        {
            "code": row.code,
            "label": row.label,
            "description": row.description,
            "icon": row.icon or "",
        }
        for row in rows
    ]


def cancellation_policy_choices() -> list[tuple[str, str]]:
    """(value, label) choices for the cancellation policy select field."""
    return [(opt["code"], opt["label"]) for opt in cancellation_policy_options()]


# ---------------------------------------------------------------------------
# Advanced cancellation policy types (for CancellationPolicy engine)
# ---------------------------------------------------------------------------

def cancellation_policy_type_options() -> list[dict]:
    """DB-backed advanced policy type options with phase rule defaults."""
    rows = _ordered_active(AccommodationCancellationPolicyTypeConfig)
    if not rows:
        return [dict(pt) for pt in CANCELLATION_POLICY_TYPES]
    return [
        {
            "code": row.code,
            "label": row.label,
            "description": row.description,
            "pre_checkin_days": row.pre_checkin_days,
            "pre_checkin_refund_pct": float(row.pre_checkin_refund_pct),
            "mid_stay_refund_pct": float(row.mid_stay_refund_pct),
            "no_show_penalty": float(row.no_show_penalty),
        }
        for row in rows
    ]


def cancellation_policy_type_choices() -> list[tuple[str, str]]:
    """(value, label) choices for the advanced policy type select field."""
    return [(opt["code"], opt["label"]) for opt in cancellation_policy_type_options()]


# ---------------------------------------------------------------------------
# Cancellation phases
# ---------------------------------------------------------------------------

def cancellation_phase_options() -> list[dict]:
    """DB-backed cancellation phase options."""
    rows = _ordered_active(AccommodationCancellationPhaseConfig)
    if not rows:
        return [dict(p) for p in CANCELLATION_PHASES]
    return [
        {"code": row.code, "label": row.label, "description": row.description}
        for row in rows
    ]


def cancellation_phase_choices() -> list[tuple[str, str]]:
    """(value, label) choices for the phase select field."""
    return [(opt["code"], opt["label"]) for opt in cancellation_phase_options()]


# ---------------------------------------------------------------------------
# No-show charge types
# ---------------------------------------------------------------------------

def no_show_charge_type_options() -> list[dict]:
    """DB-backed no-show charge type options."""
    rows = _ordered_active(AccommodationNoShowChargeTypeConfig)
    if not rows:
        return [dict(ns) for ns in NO_SHOW_CHARGE_TYPES]
    return [
        {"code": row.code, "label": row.label, "description": row.description}
        for row in rows
    ]


def no_show_charge_type_choices() -> list[tuple[str, str]]:
    """(value, label) choices for the no-show charge type select field."""
    return [(opt["code"], opt["label"]) for opt in no_show_charge_type_options()]


# ---------------------------------------------------------------------------
# Booking modes
# ---------------------------------------------------------------------------

def booking_mode_options() -> list[dict]:
    """DB-backed booking mode options (code, label, is_default)."""
    rows = _ordered_active(AccommodationBookingMode)
    if not rows:
        return [dict(mode) for mode in BOOKING_MODES]
    return [
        {"code": row.code, "label": row.label, "is_default": row.is_default}
        for row in rows
    ]


def booking_mode_choices() -> list[tuple[str, str]]:
    """(value, label) choices for the booking mode select field."""
    return [(opt["code"], opt["label"]) for opt in booking_mode_options()]


def default_booking_mode() -> str:
    """Code of the default booking mode (falls back to 'instant')."""
    options = booking_mode_options()
    default = next((opt for opt in options if opt["is_default"]), None)
    if default:
        return default["code"]
    return options[0]["code"] if options else "instant"


# ---------------------------------------------------------------------------
# Currencies
# ---------------------------------------------------------------------------

def currency_choices(fallback: Sequence[str] | None = None) -> list[str]:
    """Currency codes for the currency select field.

    DB-first. When the table is missing/empty, uses the provided ``fallback``
    (the app ``SUPPORTED_CURRENCIES`` config, preserving legacy behavior) or
    the ``catalog_data`` defaults.
    """
    rows = _ordered_active(AccommodationCurrency)
    if rows:
        return [row.code for row in rows]
    if fallback:
        return list(fallback)
    return [currency["code"] for currency in CURRENCIES]