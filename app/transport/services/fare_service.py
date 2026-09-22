# app/transport/services/fare_service.py
"""
AFCON360 Transport - canonical fare engine (fare node).

Single source of truth for fare math. BOTH the pre-submit estimate
(preview endpoint, booking creation) and the authoritative final fare
(payment) flow through here, so preview and final can never silently
use different implementations.

Current status (honest):
- Fare tables are CODE-MANAGED constants (no admin/config surface,
  no versioning, no audit yet). Ownership: Transport maintainers via
  reviewed code change + deploy. FARE_VERSION exists so stored
  explanations can later be tied to a table revision; per-booking
  version stamping is future governance work.
- Surge uses the server-local clock hour (rush 07-09, 17-19 -> 1.3).
  The timezone basis is UNDEFINED by product; changing it would change
  live prices, so it is preserved verbatim and recorded as a product
  decision, not silently "fixed".
- Distance is caller-supplied kilometres (booking creation stores the
  caller's estimated_distance, default 5). The engine never invents
  distance; callers must label defaults truthfully.
- Currency: engine is currency-agnostic (amounts as given); callers
  attach currency. Rounding: none beyond Decimal arithmetic (future
  minor-units work).

GEO boundary: the engine consumes distance/time NUMBERS supplied by
authorized domain/GEO services. GEO never calculates fares.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

# Fare table revision. Bump when (and only when) the constants below
# change through a reviewed, authorized change.
FARE_VERSION = 1

# Configuration storage (governance node): the operator-managed fare
# tables live in the TransportSetting row below; the constants in this
# module are the audited fallback used when no configured row exists.
FARE_SETTINGS_KEY = "fare.tables"
FARE_SETTINGS_CATEGORY = "pricing"
FARE_SETTINGS_PERMISSION = "transport.settings"

CURRENCY_DEFAULT = "USD"

BASE_FARES = {
    "on_demand": Decimal("10"),
    "airport_transfer": Decimal("25"),
    "stadium_shuttle": Decimal("15"),
    "hotel_transfer": Decimal("20"),
    "city_tour": Decimal("30"),
}
BASE_FARE_DEFAULT = Decimal("10")

DISTANCE_RATE_PER_KM = Decimal("2.5")
DEFAULT_DISTANCE_KM = Decimal("5")

CLASS_MULTIPLIERS = {
    "economy": Decimal("1.0"),
    "comfort": Decimal("1.2"),
    "premium": Decimal("1.5"),
    "van": Decimal("1.8"),
    "luxury": Decimal("2.0"),
}
CLASS_DEFAULT = "comfort"

PEAK_HOURS = (range(7, 10), range(17, 20))
PEAK_MULTIPLIER = Decimal("1.3")
OFFPEAK_MULTIPLIER = Decimal("1.0")

MINIMUM_FARE = Decimal("5.00")

REQUIRED_TABLE_KEYS = ("base_fares", "distance_rate_per_km",
                       "class_multipliers", "minimum_fare", "peak")


def _default_tables():
    return {
        "base_fares": {k: float(v) for k, v in BASE_FARES.items()},
        "distance_rate_per_km": float(DISTANCE_RATE_PER_KM),
        "class_multipliers": {k: float(v) for k, v in CLASS_MULTIPLIERS.items()},
        "minimum_fare": float(MINIMUM_FARE),
        "peak": {"hours": [[7, 10], [17, 20]],
                 "multiplier": float(PEAK_MULTIPLIER)},
    }


def validate_tables(tables):
    """Shape validation for operator-supplied fare tables. Raises
    ValueError naming the problem. Shapes only: key sets stay
    product-owned (unknown services/classes fall back exactly as the
    engine always has)."""
    if not isinstance(tables, dict):
        raise ValueError("tables must be an object")
    missing = [k for k in REQUIRED_TABLE_KEYS if k not in tables]
    if missing:
        raise ValueError(f"tables missing keys: {missing}")

    def _num(value, label, minimum=0.0):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{label} must be numeric") from None
        if number < minimum or number != number:  # NaN guard
            raise ValueError(f"{label} must be >= {minimum}")
        return number

    base = tables["base_fares"]
    if not isinstance(base, dict) or not base:
        raise ValueError("base_fares must be a non-empty object")
    for key, value in base.items():
        _num(value, f"base_fares[{key}]")
    classes = tables["class_multipliers"]
    if not isinstance(classes, dict) or not classes:
        raise ValueError("class_multipliers must be a non-empty object")
    for key, value in classes.items():
        if _num(value, f"class_multipliers[{key}]") <= 0:
            raise ValueError(f"class_multipliers[{key}] must be > 0")
    _num(tables["distance_rate_per_km"], "distance_rate_per_km")
    _num(tables["minimum_fare"], "minimum_fare")
    peak = tables["peak"]
    if not isinstance(peak, dict):
        raise ValueError("peak must be an object")
    hours = peak.get("hours")
    if (not isinstance(hours, list) or not hours or not all(
            isinstance(pair, list) and len(pair) == 2
            and all(isinstance(h, int) and 0 <= h <= 24 for h in pair)
            for pair in hours)):
        raise ValueError("peak.hours must be [[start, end], ...] hour pairs")
    _num(peak.get("multiplier"), "peak.multiplier", minimum=1.0)
    return True


def _coerce_tables(raw):
    """Validated tables dict from a stored blob, or None when the blob
    is absent/invalid (fail-closed to audited defaults; never crash
    pricing, never invent)."""
    if not isinstance(raw, dict):
        return None
    tables = raw.get("tables", raw)
    try:
        validate_tables(tables)
    except ValueError:
        return None
    return tables


def _stored_versions():
    """All known table versions: current row plus history, newest
    first. Each item: (version, effective_from, tables)."""
    from app.transport.models import TransportSetting
    versions = []
    try:
        row = TransportSetting.query.filter_by(
            key=FARE_SETTINGS_KEY, is_deleted=False).first()
    except Exception:
        return versions
    if row is None:
        return versions
    current = row.value if isinstance(row.value, dict) else {}
    try:
        versions.append((
            int(current.get("version", 0)),
            current.get("effective_from"),
            current.get("tables", current),
        ))
    except (TypeError, ValueError):
        pass
    for entry in (row.modification_history or []):
        if not isinstance(entry, dict):
            continue
        old = entry.get("old_value")
        if not isinstance(old, dict):
            continue
        try:
            versions.append((
                int(old.get("version", 0)),
                old.get("effective_from"),
                old.get("tables", old),
            ))
        except (TypeError, ValueError):
            continue
    return versions


def _parse_time(value):
    from datetime import timezone as _tz
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value.strip():
        try:
            moment = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_tz.utc)
    return moment


def resolve_tables(at=None):
    """Tables + version effective at a moment (default now).

    Returns (tables_dict, version_int, effective_from_iso_or_None).
    Unknown/absent/invalid configuration falls back to the audited
    module defaults at FARE_VERSION. Staged future versions (effective
    in the future) are never active early.
    """
    from datetime import timezone as _tz
    ref = at if isinstance(at, datetime) else datetime.now(_tz.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=_tz.utc)
    best = None
    for version, effective_raw, tables in _stored_versions():
        effective = _parse_time(effective_raw)
        if effective is None or effective > ref:
            continue
        if best is None or version > best[0]:
            candidate = _coerce_tables({"tables": tables})
            if candidate is not None:
                best = (version, effective_raw, candidate)
    if best is not None:
        return best[2], best[0], best[1]
    return _default_tables(), FARE_VERSION, None


def tables_version_at(moment):
    """Version number effective at a moment (history explainability
    without per-booking stamping: version = latest effective <= time).
    Falls back to FARE_VERSION when unconfigured."""
    _, version, _ = resolve_tables(at=moment)
    return version


def read_configuration():
    """Current fare configuration record for administration: version,
    effective_from, tables, plus audit trail (changed_at per version).
    Never raises for missing/invalid rows (reports defaults)."""
    tables, version, effective_from = resolve_tables()
    history = []
    try:
        from app.transport.models import TransportSetting
        row = TransportSetting.query.filter_by(
            key=FARE_SETTINGS_KEY, is_deleted=False).first()
        raw_history = (row.modification_history or []) if row else []
    except Exception:
        raw_history = []
    for entry in raw_history:
        if not isinstance(entry, dict):
            continue
        old = entry.get("old_value") or {}
        actor_name = None
        try:
            from app.identity.models.user import User
            from app.extensions import db as _db
            actor = _db.session.get(User, entry.get("changed_by"))
            actor_name = getattr(actor, "username", None)
        except Exception:
            actor_name = None
        history.append({
            "version": old.get("version") if isinstance(old, dict) else None,
            "changed_at": entry.get("changed_at"),
            # Username only: internal user IDs are never exposed.
            "changed_by": actor_name,
        })
    return {
        "key": FARE_SETTINGS_KEY,
        "version": version,
        "effective_from": effective_from,
        "tables": tables,
        "history": history,
    }


def update_fare_tables(tables, *, actor_user_id, effective_from=None):
    """Operator write path (governance node). Validates completeness,
    assigns the next version, and persists through the existing
    TransportSetting audit trail (old/new/at/by + cache invalidation).

    Reasons/approvals are NOT stored: the shared history schema has no
    reason field, and reshaping shared audit infra is out of scope
    (documented limitation). effective_from defaults to now; a future
    timestamp stages the version without activating it.
    Returns {version, effective_from}.
    """
    from datetime import timezone as _tz
    from app.extensions import db
    from app.transport.models import TransportSetting

    validate_tables(tables)
    if effective_from is None:
        effective = datetime.now(_tz.utc)
    elif isinstance(effective_from, datetime):
        effective = effective_from
    elif isinstance(effective_from, str) and effective_from.strip():
        try:
            effective = datetime.fromisoformat(effective_from.strip())
        except ValueError:
            raise ValueError(
                "effective_from must be ISO-8601") from None
    else:
        raise ValueError("effective_from must be ISO-8601")
    if effective.tzinfo is None:
        effective = effective.replace(tzinfo=_tz.utc)

    current_version = 0
    try:
        row = TransportSetting.query.filter_by(
            key=FARE_SETTINGS_KEY, is_deleted=False).first()
        if row is not None and isinstance(row.value, dict):
            current_version = int(row.value.get("version", 0))
    except (TypeError, ValueError):
        current_version = 0
    version = current_version + 1
    value = {
        "version": version,
        "effective_from": effective.isoformat(),
        "tables": tables,
    }
    if row is None:
        row = TransportSetting(
            key=FARE_SETTINGS_KEY,
            value=value,
            name="Fare tables (canonical engine)",
            description=("Operator-managed fare tables consumed by the "
                         "canonical FareService. Requires "
                         "'transport.settings' permission."),
            category=FARE_SETTINGS_CATEGORY,
            data_type="json",
            default_value=value,
            is_public=False,
            is_advanced=True,
            requires_permission=FARE_SETTINGS_PERMISSION,
        )
        db.session.add(row)
        db.session.commit()
    else:
        from app.transport.models import update_setting
        update_setting(FARE_SETTINGS_KEY, value, modified_by=actor_user_id)
    return {"version": version,
            "effective_from": effective.isoformat()}


def _surge_for_hour(hour: int, tables=None) -> Decimal:
    tables = tables or _default_tables()
    try:
        peak = tables.get("peak", {})
        multiplier = Decimal(str(peak.get("multiplier", 1.0)))
        for start, end in peak.get("hours", []):
            if int(start) <= hour < int(end):
                return multiplier
    except Exception:
        pass
    return OFFPEAK_MULTIPLIER


def calculate_estimate(service_type: Any = None,
                       vehicle_class: Any = None,
                       distance_km: Any = None,
                       at: Optional[datetime] = None) -> Dict[str, Any]:
    """Canonical pre-submit estimate. Pure function of its inputs.

    at: reference time for BOTH the rush-hour rule and the fare-table
    version resolution (server-local clock preserved verbatim; None
    means now). Returns totals plus the full input/breakdown record
    so estimates stay explainable, including which table version
    priced them.
    """
    tables, version, effective_from = resolve_tables(at=at)
    base_map = tables["base_fares"]
    class_map = tables["class_multipliers"]
    service_key = str(service_type or "on_demand").lower()
    base = Decimal(str(base_map.get(
        service_key, base_map.get("on_demand", 10))))
    try:
        distance = Decimal(str(distance_km)) if distance_km is not None \
            else Decimal(str(tables.get("default_distance_km", 5)))
    except Exception:
        distance = Decimal(str(tables.get("default_distance_km", 5)))
    if distance < 0:
        distance = Decimal(str(tables.get("default_distance_km", 5)))
    class_key = str(vehicle_class or CLASS_DEFAULT).lower()
    multiplier = Decimal(str(class_map.get(
        class_key, class_map.get(CLASS_DEFAULT, 1.0))))
    ref = at if isinstance(at, datetime) else datetime.now()
    surge = _surge_for_hour(ref.hour, tables)
    rate = Decimal(str(tables.get("distance_rate_per_km", 2.5)))
    distance_charge = distance * rate
    subtotal = base + distance_charge
    total = (subtotal * multiplier) * surge
    return {
        "currency": CURRENCY_DEFAULT,
        "version": version,
        "effective_from": effective_from,
        "inputs": {
            "service_type": service_key,
            "vehicle_class": class_key,
            "distance_km": float(distance),
            "surge_hour": ref.hour,
        },
        "breakdown": {
            "base_fare": float(base),
            "distance_charge": float(distance_charge),
            "class_multiplier": float(multiplier),
            "surge_multiplier": float(surge),
        },
        "surge_multiplier": surge,
        "total": total,
    }


def calculate_final(base_price: Any,
                    toll_fees: Any = None,
                    parking_fees: Any = None,
                    promotion_discount: Any = None,
                    minimum_fare: Any = None) -> Decimal:
    """Canonical final fare from authoritative trip facts.

    Same math the payment path has always used: base + tolls/parking
    - promo, floored at the active minimum. minimum_fare=None resolves
    the currently active configured floor (matching the estimate
    path's tables); pass an explicit value for deterministic,
    context-free computation. Documented differences vs the
    estimate: tolls/parking known only at trip time, promos applied
    at payment, floor applies to finals only.
    """
    def _dec(value: Any) -> Decimal:
        try:
            return Decimal(str(value)) if value is not None else Decimal("0.00")
        except Exception:
            return Decimal("0.00")

    floor = (_dec(minimum_fare) if minimum_fare is not None
             else Decimal(str(resolve_tables()[0].get("minimum_fare", 5.0))))
    final_price = (_dec(base_price) + _dec(toll_fees)
                   + _dec(parking_fees) - _dec(promotion_discount))
    return max(final_price, floor)


__all__ = [
    "FARE_VERSION",
    "BASE_FARES",
    "DISTANCE_RATE_PER_KM",
    "DEFAULT_DISTANCE_KM",
    "CLASS_MULTIPLIERS",
    "PEAK_MULTIPLIER",
    "OFFPEAK_MULTIPLIER",
    "MINIMUM_FARE",
    "FARE_SETTINGS_KEY",
    "calculate_estimate",
    "calculate_final",
    "validate_tables",
    "resolve_tables",
    "tables_version_at",
    "read_configuration",
    "update_fare_tables",
]
