"""AFCON360 Transport Module - Booking Service
Handles booking creation, management, and lifecycle
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Any
import random
import string
import json
import hashlib
import logging
import sqlalchemy as sa
from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.extensions import db, cache
from app.transport.models import (
    Booking,
    BookingStatus as BookingStatusPy,
    DriverProfile,
)
from app.utils.enums import (
    ServiceType,
    ProviderType,
    VehicleClass,
    Currency,
    PaymentStatus,
)
from app.core.validators import validate_coordinates
from app.geo.services import geocode_result_from_candidate
from app.utils.exceptions import ValidationError, NotFoundError, PermissionError, ServiceUnavailableError
from app.utils.security import sanitize_input
from app.utils.validators import validate_booking_request
from app.utils.monitoring import monitor_endpoint, record_metric
from app.utils.audit import audit_log
from app.transport.services.location_snapshot import (
    build_canonical_location_snapshot,
    build_canonical_snapshot_from_coordinates,
    SOURCE_METHOD_PAIRS,
)

# Module-level logger (doesn't need app context)
logger = logging.getLogger(__name__)

# CANCEL-FEE-SCHEDULED-P1 policy. Caps are face value in the booking
# currency; nothing here converts currency or touches the wallet.
SCHEDULED_BOOKING_MODE = "scheduled"
CANCEL_FEE_STANDARD_RATE = Decimal("0.20")
CANCEL_FEE_LATE_RATE = Decimal("0.40")
CANCEL_FEE_STANDARD_CAP = Decimal("10000.00")
CANCEL_FEE_LATE_CAP = Decimal("20000.00")
NO_SHOW_FEE_RATE = Decimal("0.40")
NO_SHOW_FEE_CAP = Decimal("20000.00")
NO_SHOW_GRACE = timedelta(minutes=15)
DRIVER_LATE_CANCEL_CREDIT_RATE = Decimal("0.80")


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _money(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")
    return amount.quantize(Decimal("0.01"))


def _booking_mode(booking) -> str:
    metadata = getattr(booking, "booking_metadata", None) or {}
    if isinstance(metadata, dict):
        return str(metadata.get("booking_mode") or "").strip().lower()
    return ""


def _booking_currency_code(booking) -> str:
    currency = getattr(booking, "currency", None)
    if hasattr(currency, "value"):
        currency = getattr(currency, "value", currency)
    return str(currency or "UGX").strip().upper()


def _validate_booking_location_coordinates(location: Any, field_name: str) -> Any:
    """Enforce the canonical geographic contract at the booking boundary.

    - Non-dict payloads (address-only / free text) pass through unchanged.
    - 'lat'/'lng' keys are REJECTED (must use 'latitude'/'longitude').
    - Canonical coordinates must be BOTH present and valid ranges.
    """
    if not isinstance(location, dict):
        return location
    if "lat" in location or "lng" in location:
        raise ValidationError(
            f"{field_name} geographic coordinates must use 'latitude'/'longitude' keys; 'lat'/'lng' are not accepted",
            field=field_name,
        )
    has_lat = location.get("latitude") is not None
    has_lng = location.get("longitude") is not None
    if has_lat != has_lng:
        raise ValidationError(
            f"{field_name} must include both 'latitude' and 'longitude'",
            field=field_name,
        )
    if has_lat:
        validate_coordinates(location["latitude"], location["longitude"])
    return location


def _resolve_canonical_location(raw_location: Any, data: Dict[str, Any],
                                prefix: str, field_name: str) -> Any:
    """Resolve a booking endpoint to its truthful representation.

    Empty-string lat/lng (which the form posts when no map pin was placed)
    are treated as ABSENT, not as coordinates. This is what the form
    actually sends — treating "" as a coordinate is the bug that produced
    'pickup_location coordinates must be numeric'.
    """
    if isinstance(raw_location, dict) and (
            raw_location.get("latitude") is not None
            or raw_location.get("longitude") is not None):
        return _validate_booking_location_coordinates(raw_location, field_name)

    def _blank(v):
        return v is None or (isinstance(v, str) and not v.strip())

    lat_raw = data.get(f"{prefix}_latitude") if isinstance(data, dict) else None
    lng_raw = data.get(f"{prefix}_longitude") if isinstance(data, dict) else None

    # No pins placed → falls back to typed address (unchanged behaviour)
    if _blank(lat_raw) and _blank(lng_raw):
        return _validate_booking_location_coordinates(raw_location, field_name)

    # One pin placed, the other missing → refuse rather than silently degrade
    if _blank(lat_raw) or _blank(lng_raw):
        raise ValidationError(
            message=f"{field_name} must include both 'latitude' and 'longitude'",
        )

    # Type narrowing (pyright): _blank() above already excluded None and
    # blank strings, but the checker cannot see through the helper. Reject
    # anything that is not a numeric scalar here; the canonical validator
    # below still owns the coordinate verdict (bool included — bool passes
    # isinstance(int) and is rejected there, never laundered by float()).
    if not isinstance(lat_raw, (str, int, float)) or not isinstance(lng_raw, (str, int, float)):
        raise ValidationError(
            message=f"{field_name} coordinates must be numeric",
        )

    # UI-LOC-02A: validate RAW values before float() launders
    # bool/nan/inf into floats. Canonical validator owns the verdict.
    try:
        validate_coordinates(lat_raw, lng_raw)
    except Exception:
        raise ValidationError(
            message=f"{field_name} coordinates must be numeric",
        )

    try:
        lat = float(lat_raw)
        lng = float(lng_raw)
    except (TypeError, ValueError):
        raise ValidationError(
            message=f"{field_name} coordinates must be numeric",
        )

    validate_coordinates(lat, lng)
    resolved: Dict[str, Any] = {"latitude": lat, "longitude": lng}
    if isinstance(raw_location, str) and raw_location.strip():
        resolved["address"] = raw_location.strip()
    elif isinstance(raw_location, dict) and raw_location.get("address"):
        resolved["address"] = raw_location.get("address")
    return resolved


def _measured_distance_km(pickup_location: Any,
                          dropoff_location: Any) -> Optional[float]:
    """GEO straight-line kilometres between two canonical endpoints,
    or None unless BOTH carry valid coordinates. Planning input only:
    explicitly not road distance, ETA, or fare distance."""
    def _coords(location: Any):
        if not isinstance(location, dict):
            return None
        raw_lat = location.get("latitude")
        raw_lng = location.get("longitude")
        # Type narrowing (pyright) + 02A bool hygiene: only numeric scalars
        # reach float(); bool can never be a coordinate (fail-closed None).
        if (isinstance(raw_lat, bool) or isinstance(raw_lng, bool)
                or not isinstance(raw_lat, (str, int, float))
                or not isinstance(raw_lng, (str, int, float))):
            return None
        try:
            lat = float(raw_lat)
            lng = float(raw_lng)
        except (TypeError, ValueError):
            return None
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return None
        return lat, lng

    origin = _coords(pickup_location)
    destination = _coords(dropoff_location)
    if origin is None or destination is None:
        return None
    from app.geo.interfaces import GeoPoint
    from app.geo.services import straight_line_distance_m
    return straight_line_distance_m(
        GeoPoint(origin[0], origin[1]),
        GeoPoint(destination[0], destination[1])) / 1000.0


# Valid status transitions - enforced server-side.
# Single source of truth (moved here from api/booking_routes.py so the
# admin status endpoint and moderation flows share one contract).
STATUS_TRANSITIONS = {
    BookingStatusPy.DRAFT:           [BookingStatusPy.PENDING_PAYMENT, BookingStatusPy.CANCELLED],
    BookingStatusPy.PENDING_PAYMENT: [BookingStatusPy.CONFIRMED, BookingStatusPy.CANCELLED],
    # MATCH-01-owned: CONFIRMED gains the NO_MATCH terminal edge (additive;
    # the pre-existing ASSIGNED and CANCELLED edges are unchanged).
    BookingStatusPy.CONFIRMED:       [BookingStatusPy.ASSIGNED, BookingStatusPy.NO_MATCH, BookingStatusPy.CANCELLED],
    BookingStatusPy.ASSIGNED:        [BookingStatusPy.DRIVER_EN_ROUTE, BookingStatusPy.CANCELLED],
    BookingStatusPy.DRIVER_EN_ROUTE: [BookingStatusPy.PICKUP_ARRIVED, BookingStatusPy.CANCELLED],
    BookingStatusPy.PICKUP_ARRIVED:  [BookingStatusPy.IN_PROGRESS, BookingStatusPy.NO_SHOW],
    BookingStatusPy.IN_PROGRESS:     [BookingStatusPy.COMPLETED, BookingStatusPy.DISPUTED],
    BookingStatusPy.COMPLETED:       [],
    BookingStatusPy.CANCELLED:       [],
    BookingStatusPy.NO_SHOW:         [],
    BookingStatusPy.DISPUTED:        [BookingStatusPy.COMPLETED, BookingStatusPy.CANCELLED],
    # MATCH-01-owned: terminal matching-failure state (additive).
    # The single outbound edge NO_MATCH -> CONFIRMED is the manual rider
    # "Try again" reopen (retry_matching only); nothing fires it automatically.
    BookingStatusPy.NO_MATCH:        [BookingStatusPy.CONFIRMED],
}


def _can_transition(current: BookingStatusPy, target: BookingStatusPy) -> bool:
    member = _status_member(current)
    if member is None:
        return False
    return target in STATUS_TRANSITIONS.get(member, [])


def _status_member(value: Any) -> Optional[BookingStatusPy]:
    """Normalize a stored status (plain str) or member to a member.

    Permanent-convention helper: storage is VARCHAR, so ORM attributes
    arrive as strings; the transition map stays member-keyed as the
    single source of truth. Unknown strings map to None (closed world).
    """
    if isinstance(value, BookingStatusPy):
        return value
    try:
        return BookingStatusPy(value)
    except (ValueError, TypeError):
        return None


def allowed_transition_values(current: Any) -> List[str]:
    """Lowercase allowed-transition values for any stored/member status."""
    member = _status_member(current)
    if member is None:
        return []
    return [s.value for s in STATUS_TRANSITIONS.get(member, [])]


# --- MATCH-01-owned: matching-window cursor helpers (additive) ---
# The 3-minute matching window is measured from a cursor stored in
# booking_metadata["matching_started_at"] (ISO-8601), NOT from confirmed_at:
# confirmed_at is first-confirmation audit history rendered by the rider
# timeline (rider_status_sync.js), the rider/admin templates and several
# tests, so retry must not rewrite it (review Condition 1). Rows created
# before MATCH-01 fall back to confirmed_at (back-compat).
MATCHING_WINDOW_META_KEY = "matching_started_at"


def _stamp_matching_window_start(booking: Booking, now: datetime) -> None:
    """(Re)start the matching window cursor on an in-memory Booking row.

    Caller commits. Overwrites any previous cursor (retry semantics).
    """
    meta = dict(booking.booking_metadata or {})
    meta[MATCHING_WINDOW_META_KEY] = now.isoformat()
    booking.booking_metadata = meta


def _matching_window_start(booking: Booking) -> Optional[datetime]:
    """Window cursor as aware datetime, or None when unknowable."""
    meta = booking.booking_metadata or {}
    raw = meta.get(MATCHING_WINDOW_META_KEY) if isinstance(meta, dict) else None
    if raw:
        try:
            parsed = datetime.fromisoformat(str(raw))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, TypeError):
            pass
    fallback = getattr(booking, "confirmed_at", None)
    if fallback is not None and fallback.tzinfo is None:
        fallback = fallback.replace(tzinfo=timezone.utc)
    return fallback


def _trip_fingerprint(data: Dict[str, Any]) -> str:
    """Canonical request fingerprint for idempotency-key reuse checks.

    Normalises the fields that define WHAT trip a request asks for.
    Client-supplied pickup_time is deliberately NOT hashed for instant
    rides (it may differ between retries; the server clock is the
    authority). Scheduled rides hash the explicit ISO pickup_time, but
    only after mode-aware validation has accepted it. A request with no
    valid booking_mode is fingerprinted in the scheduled branch so that
    any later retry with a valid mode never matches it (fail-closed).
    """
    mode = str(data.get("booking_mode") or "").strip().lower()
    if mode == "instant":
        pickup_fp = "instant"
    else:
        raw = data.get("pickup_time")
        try:
            dt = datetime.fromisoformat(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            pickup_fp = dt.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            pickup_fp = ""
    canonical = {
        "booking_mode": mode,
        "pickup_time": pickup_fp,
        "service_type": str(data.get("service_type") or "").strip().lower(),
        "vehicle_class": str(data.get("vehicle_class") or "comfort").strip().lower(),
        "pickup_address": str(data.get("pickup_address") or "").strip().lower(),
        "dropoff_address": str(data.get("dropoff_address") or "").strip().lower(),
        "passenger_count": str(data.get("passenger_count") or "1"),
    }
    raw_payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


class BookingService:
    """Instance-based service for managing transport bookings"""

    CACHE_PREFIX = "transport:booking"
    BOOKING_CACHE_TTL = 300  # 5 minutes
    def __init__(self):
        self.cache_prefix = self.CACHE_PREFIX
        self.cache_ttl = self.BOOKING_CACHE_TTL
        logger.debug("BookingService initialized")

    # =========================================================
    # Core Booking Operations
    # =========================================================

    @monitor_endpoint("create_booking")
    def create_booking(self, customer_id: int, booking_data: Dict[str, Any],
                       request_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            sanitized_data = booking_data or {}

            # Request-receipt clock (6C): captured BEFORE any fare call,
            # retry sleep or dedupe so the scheduled lead-time (and, from
            # Deploy 2, the server pickup_time itself) is measured from
            # this instant — never from a later clock read that already
            # includes processing latency.
            request_received_at = datetime.now(timezone.utc)

            # Idempotency dedupe — before any fare calc or DB write.
            # Addendum-2 Option A: a successful replay is a READ. No
            # metadata mutation, no commit. The same key with a
            # different trip is a client error, not a replay.
            key = (sanitized_data.get("idempotency_key") or "").strip() or None
            if key:
                existing = Booking.query.filter_by(
                    idempotency_key=key,
                    user_id=customer_id,
                    is_deleted=False,
                ).first()
                if existing:
                    stored_fp = (existing.booking_metadata or {}).get(
                        "trip_fingerprint")
                    if stored_fp is None:
                        logger.info(
                            f"Idempotent replay rejected: key exists without a "
                            f"trip fingerprint (legacy row) for "
                            f"user_id={customer_id}"
                        )
                        raise ValidationError(
                            message="Idempotency key exists but cannot be "
                                    "verified. Refresh the page and try again.",
                            field="idempotency_key",
                        )
                    if stored_fp != _trip_fingerprint(sanitized_data):
                        logger.info(
                            f"Idempotent replay rejected: key reused with a "
                            f"different trip for user_id={customer_id}"
                        )
                        raise ValidationError(
                            message="idempotency_key reused with a different trip",
                            field="idempotency_key",
                        )
                    logger.info(
                        f"Idempotent replay returned existing booking "
                        f"id={existing.id} (read-only)"
                    )
                    return {
                        "success": True,
                        "data": {
                            "booking_id": existing.id,
                            "booking_reference": existing.booking_reference,
                            "idempotent_replay": True,
                        },
                    }

            is_valid, validation_errors = validate_booking_request(sanitized_data)
            if not is_valid:
                raise ValidationError(
                    message="; ".join(validation_errors) or "Booking validation failed"
                )

            # Resolve coordinates from form data (mirrors old _resolve_canonical_location logic)
            def _extract_coords(data: Dict[str, Any], prefix: str) -> tuple[Optional[float], Optional[float]]:
                def _blank(v):
                    return v is None or (isinstance(v, str) and not v.strip())
                lat_raw = data.get(f"{prefix}_latitude") if isinstance(data, dict) else None
                lng_raw = data.get(f"{prefix}_longitude") if isinstance(data, dict) else None
                if _blank(lat_raw) or _blank(lng_raw):
                    return None, None
                # UI-LOC-02A / Node 2 correction: validate RAW values BEFORE
                # float() launders bool/NaN/Inf into floats (float(True)
                # == 1.0). The canonical validator owns the verdict on the
                # raw input; only validated raw values reach float().
                try:
                    validate_coordinates(lat_raw, lng_raw)
                except (TypeError, ValueError, ValidationError):
                    return None, None
                try:
                    lat = float(lat_raw)
                    lng = float(lng_raw)
                except (TypeError, ValueError):
                    return None, None
                try:
                    validate_coordinates(lat, lng)
                except (TypeError, ValueError, ValidationError):
                    return None, None
                return lat, lng

            pickup_lat, pickup_lng = _extract_coords(sanitized_data, "pickup")
            dropoff_lat, dropoff_lng = _extract_coords(sanitized_data, "dropoff")

            # UI-LOC-02A: text-only bookings are rejected at creation (safety closure)
            # Both pickup and dropoff must have resolved coordinates
            if pickup_lat is None or pickup_lng is None:
                raise ValidationError(
                    message="pickup_location must include both 'latitude' and 'longitude'",
                    field="pickup_location",
                )
            if dropoff_lat is None or dropoff_lng is None:
                raise ValidationError(
                    message="dropoff_location must include both 'latitude' and 'longitude'",
                    field="dropoff_location",
                )

            # Build canonical location snapshots per Node 1 contract (Node 2)
            # Pass resolved coordinates via location_payload dict so snapshot builder has them
            pickup_loc_raw = sanitized_data.get("pickup_location")
            pickup_payload = dict(pickup_loc_raw) if isinstance(pickup_loc_raw, dict) else {}
            pickup_payload["latitude"] = pickup_lat
            pickup_payload["longitude"] = pickup_lng

            dropoff_loc_raw = sanitized_data.get("dropoff_location")
            dropoff_payload = dict(dropoff_loc_raw) if isinstance(dropoff_loc_raw, dict) else {}
            dropoff_payload["latitude"] = dropoff_lat
            dropoff_payload["longitude"] = dropoff_lng

            # Use pickup_location string as explicit_address if no pickup_address provided
            pickup_explicit_address = sanitized_data.get("pickup_address")
            if not pickup_explicit_address:
                pickup_loc_raw = sanitized_data.get("pickup_location")
                if isinstance(pickup_loc_raw, str) and pickup_loc_raw.strip():
                    pickup_explicit_address = pickup_loc_raw.strip()

            dropoff_explicit_address = sanitized_data.get("dropoff_address")
            if not dropoff_explicit_address:
                dropoff_loc_raw = sanitized_data.get("dropoff_location")
                if isinstance(dropoff_loc_raw, str) and dropoff_loc_raw.strip():
                    dropoff_explicit_address = dropoff_loc_raw.strip()

            # Node 3 (D3): the rider form marks HOW each endpoint was chosen.
            # The marker is only ever carried through — the contract pairing
            # table supplies the single method for that source, so a client
            # can never mismatch a pair, and the source is never re-inferred
            # from coordinates after the fact. An absent/empty marker keeps
            # the historical inference path unchanged.
            def _source_hint(prefix: str) -> tuple[Optional[str], Optional[str]]:
                raw = sanitized_data.get(f"{prefix}_source")
                if raw is None:
                    return None, None
                if isinstance(raw, str):
                    raw = raw.strip()
                if not raw:
                    return None, None
                method = SOURCE_METHOD_PAIRS.get(raw)
                if method is None:
                    raise ValidationError(
                        message=f"{prefix}_source must be one of "
                                f"{sorted(SOURCE_METHOD_PAIRS)}",
                        field=f"{prefix}_source",
                    )
                return raw, method

            pickup_source, pickup_method = _source_hint("pickup")
            dropoff_source, dropoff_method = _source_hint("dropoff")

            # UI-01: a "search" source is an evidence claim (H2). The
            # only truthful backing is the provider result the rider's
            # picker echoed back in <prefix>_geocode - one item exactly
            # as GET /geo/api/geocode returned it (JSON string from the
            # browser form, or a dict from a JSON API caller). Without
            # it the canonical builder would refuse the claim anyway;
            # failing here keeps the error field-precise and no row is
            # created. gps/map/absent markers pass NO evidence - the
            # historical behaviour is unchanged.
            def _search_geocode_result(prefix: str):
                field = f"{prefix}_source"
                missing = (f"{prefix}_source 'search' requires "
                           f"{prefix}_geocode provider evidence")
                raw = sanitized_data.get(f"{prefix}_geocode")
                if isinstance(raw, str):
                    text = raw.strip()
                    if not text:
                        raise ValidationError(message=missing, field=field)
                    try:
                        candidate = json.loads(text)
                    except ValueError as exc:
                        raise ValidationError(
                            message=missing, field=field) from exc
                elif isinstance(raw, dict):
                    candidate = raw
                else:
                    raise ValidationError(message=missing, field=field)
                if not isinstance(candidate, dict):
                    raise ValidationError(message=missing, field=field)
                try:
                    return geocode_result_from_candidate(candidate)
                except ValidationError as exc:
                    raise ValidationError(
                        message=f"{missing} ({exc.message})",
                        field=field,
                    ) from exc

            pickup_geocode_result = (
                _search_geocode_result("pickup")
                if pickup_source == "search" else None)
            dropoff_geocode_result = (
                _search_geocode_result("dropoff")
                if dropoff_source == "search" else None)

            try:
                pickup_snapshot = build_canonical_location_snapshot(
                    location_payload=pickup_payload,
                    geocode_result=pickup_geocode_result,
                    explicit_address=pickup_explicit_address,
                    source=pickup_source,
                    resolution_method=pickup_method,
                )
                dropoff_snapshot = build_canonical_location_snapshot(
                    location_payload=dropoff_payload,
                    geocode_result=dropoff_geocode_result,
                    explicit_address=dropoff_explicit_address,
                    source=dropoff_source,
                    resolution_method=dropoff_method,
                )
            except ValueError as exc:
                # The canonical builder is the authority on whether a
                # provenance claim is satisfiable; an unsatisfiable claim is
                # a client error, not a server error.
                raise ValidationError(
                    message=str(exc),
                    field="pickup_location",
                ) from exc

            # Ensure both locations are resolved with canonical coordinates
            def _ensure_canonical_coords(loc, field_name):
                if not isinstance(loc, dict) or loc.get("latitude") is None or loc.get("longitude") is None:
                    raise ValidationError(
                        message=f"{field_name} must be a resolved location with coordinates",
                        field=field_name,
                    )

            _ensure_canonical_coords(pickup_snapshot, "pickup_location")
            _ensure_canonical_coords(dropoff_snapshot, "dropoff_location")

            # UI-LOC-02A: booking-bound pricing has no silent fallback.
            # Measured GEO straight-line distance from resolved coordinates
            # is the ONLY booking fare basis. Explicit estimates live in
            # fare_routes.FareEstimateResource (planning_default labelled).
            measured_km = _measured_distance_km(pickup_snapshot,
                                                dropoff_snapshot)
            if measured_km is None:
                raise ValidationError(
                    message="Resolved coordinates required for fare calculation",
                    field="pickup_location",
                )
            distance_for_fare = measured_km
            distance_basis = "straight_line_planner"

            # Canonical fare engine (fare node): one computation feeds the
            # stored price, the recorded surge, and the stored distance
            # basis, so they can never diverge (e.g. across an hour
            # boundary between two calls).
            # Chosen class (hailing node): the ride picker submits the
            # selected class; it is persisted in service_subtype and
            # booking_metadata for class-aware matching.
            chosen_class = sanitized_data.get("vehicle_class", "comfort")
            from app.transport.services.fare_service import calculate_estimate
            _estimate = calculate_estimate(
                service_type=sanitized_data.get("service_type", "on_demand"),
                vehicle_class=chosen_class,
                distance_km=distance_for_fare,
            )
            estimated_price = _estimate["total"]
            # The fare engine owns denomination. Payment eligibility is checked
            # against the exact server-calculated amount, never a client hint or
            # a zero-amount catalogue lookup.
            fare_currency_code = str(_estimate.get("currency") or "USD").strip().upper()
            try:
                fare_currency = Currency(fare_currency_code)
            except ValueError as exc:
                raise ServiceUnavailableError(
                    "Fare service returned an unsupported currency"
                ) from exc

            requested_currency = sanitized_data.get("currency")
            if requested_currency and str(requested_currency).strip().upper() != fare_currency_code:
                raise ValidationError(
                    message=(
                        "This fare is quoted in %s. No automatic currency "
                        "conversion is applied." % fare_currency_code
                    ),
                    field="currency",
                )

            payment_method = str(
                sanitized_data.get("payment_method") or ""
            ).strip().lower()
            if not payment_method:
                raise ValidationError(
                    message="Choose a payment method before requesting the ride",
                    field="payment_method",
                )
            from app.transport.services.payment_methods import (
                get_available_transport_payment_methods,
                require_ready_transport_payment_method,
            )
            eligible_methods = get_available_transport_payment_methods(
                customer_id,
                currency_code=fare_currency_code,
                amount=estimated_price,
                payment_timing="pay_on_completion",
            )
            require_ready_transport_payment_method(
                eligible_methods, payment_method
            )
            # Record the applied surge alongside the price (fare node):
            # the surge_multiplier column previously stayed at its 1.00
            # default even when rush pricing applied, making estimates
            # unexplainable. Same engine, same inputs — no price change.
            _applied_surge = _estimate["surge_multiplier"]

            from zoneinfo import ZoneInfo

            # Resolve the app zone once, from config. Never from the
            # machine's local timezone, and never implicitly UTC — both
            # are silent-bug factories.
            _APP_TZ_NAME = current_app.config.get('APP_TZ', 'Africa/Nairobi')
            _APP_TZ = ZoneInfo(_APP_TZ_NAME)

            _raw_mode = sanitized_data.get('booking_mode')
            if _raw_mode is None or str(_raw_mode).strip() == '':
                raise ValidationError(
                    message=(
                        "booking_mode is required ('instant' or 'scheduled'). "
                        "Refresh the page and try again."
                    ),
                    field="booking_mode",
                )
            booking_mode = str(_raw_mode).strip().lower()
            if booking_mode not in ('instant', 'scheduled'):
                raise ValidationError(
                    message="booking_mode must be 'instant' or 'scheduled'",
                    field="booking_mode",
                )

            if booking_mode == 'scheduled':
                try:
                    raw = sanitized_data["pickup_time"]
                    pickup_time = datetime.fromisoformat(str(raw))
                    if pickup_time.tzinfo is None:
                        # Naive input is interpreted as the configured app
                        # zone — the contract the form posts under. Never
                        # machine-local, never UTC by accident.
                        pickup_time = pickup_time.replace(tzinfo=_APP_TZ)
                except (ValueError, TypeError, KeyError):
                    raise ValidationError(
                        message="Scheduled pickups require an explicit pickup_time",
                        field="pickup_time",
                    )
                # Lead time is measured from request receipt (6C), not from
                # a clock read after fare/dedupe latency. The DB constraint
                # (ck_pickup_time_sane) stays universal — it catches
                # clearly-past bookings regardless of mode.
                minimum_lead = request_received_at + timedelta(minutes=15)
                if pickup_time < minimum_lead:
                    raise ValidationError(
                        message=(
                            "Scheduled pickups must be at least 15 minutes from now. "
                            "For an immediate ride, choose 'Now'."
                        ),
                        field="pickup_time",
                    )
            else:
                # Instant: the server clock is the pickup-time authority.
                # Any client-supplied pickup_time is IGNORED — the stale-UI
                # replay hole (a client resending an old pickup_time whose
                # grace expired) is closed here. The ck_pickup_time_sane
                # 5-minute grace absorbs this call's own processing latency.
                pickup_time = datetime.now(timezone.utc)

            special_req = sanitized_data.get("special_requirements") or {}
            if isinstance(special_req, str):
                special_req = {"note": special_req}

            booking = Booking(
                user_id=customer_id,
                provider_type=ProviderType(
                    (sanitized_data.get("provider_type") or "individual_driver").lower()
                ),
                service_type=ServiceType(sanitized_data["service_type"].lower()),
                pickup_location=pickup_snapshot,
                dropoff_location=dropoff_snapshot,
                pickup_time=pickup_time,
                pickup_mode=booking_mode,
                request_received_at=request_received_at,
                passenger_count=int(sanitized_data.get("passenger_count") or 1),
                luggage_count=int(sanitized_data.get("luggage_count") or 0),
                special_requirements=special_req,
                accessibility_requirements=sanitized_data.get("accessibility_requirements") or [],
                base_price=estimated_price,
                surge_multiplier=_applied_surge,
                estimated_distance_km=distance_for_fare,
                estimated_duration_minutes=sanitized_data.get("estimated_duration"),
                payment_method=payment_method,
                payment_status=PaymentStatus.PENDING,
                status=BookingStatusPy.PENDING_PAYMENT,
                currency=fare_currency,
                service_subtype=chosen_class,
                idempotency_key=key,
                booking_metadata={
                    "customer_id": customer_id,
                    "request_id": request_id,
                    "vehicle_class": chosen_class,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "fare_version": _estimate.get("version"),
                    "fare_effective_from": _estimate.get("effective_from"),
                    "distance_km": float(distance_for_fare)
                    if distance_for_fare is not None else None,
                    "distance_basis": distance_basis,
                    "booking_mode": booking_mode,  # 'instant' | 'scheduled'
                    "trip_fingerprint": _trip_fingerprint(sanitized_data),
                }
            )

            db.session.add(booking)
            db.session.flush()  # flush to get booking.id before creating lifecycle events

            # Create lifecycle events for pickup and dropoff
            from app.transport.models import LocationLifecycleEvent
            now = datetime.now(timezone.utc)
            
            # Pickup lifecycle event
            pickup_event = LocationLifecycleEvent(
                booking_id=booking.id,
                endpoint="pickup",
                event_type="BOOKING_LOCATION_SET",
                snapshot=pickup_snapshot,
                actor_user_id=customer_id,
                transition_at=now,
                event_metadata={"created_by": "booking_service"}
            )
            # Dropoff lifecycle event
            dropoff_event = LocationLifecycleEvent(
                booking_id=booking.id,
                endpoint="dropoff",
                event_type="BOOKING_LOCATION_SET",
                snapshot=dropoff_snapshot,
                actor_user_id=customer_id,
                transition_at=now,
                event_metadata={"created_by": "booking_service"}
            )
            db.session.add(pickup_event)
            db.session.add(dropoff_event)
            db.session.commit()

            self._invalidate_listing_caches()

            record_metric("booking_created", tags={
                "service_type": booking.service_type.value,
                "provider_type": booking.provider_type.value
            }, value=1)

            audit_log(
                action="booking_created",
                resource_type="booking",
                resource_id=booking.id,
                user_id=customer_id,
                details={
                    "booking_reference": booking.booking_reference,
                    "service_type": booking.service_type.value,
                    "base_price": float(estimated_price),
                    "request_id": request_id,
                }
            )

            # Emit notification signal (listener notifies customer)
            try:
                from app.notifications.signals import transport_booking_created
                transport_booking_created.send(booking, booking=booking)
            except Exception as _ne:
                logger.warning(f"transport_booking_created signal failed: {_ne}")

            return {
                "success": True,
                "message": "Booking created successfully",
                "data": {
                    "booking_id": booking.id,
                    "booking_public_id": booking.booking_reference,
                    "booking_reference": booking.booking_reference,
                    "estimated_price": float(estimated_price),
                    "status": booking.status,
                    "pickup_time": booking.pickup_time.isoformat()
                    if booking.pickup_time else None,
                    "booking_mode": booking_mode,
                }
            }

        except ValidationError as e:
            db.session.rollback()
            record_metric("booking_creation", tags={"status": "failed", "error_type": "validation"}, value=1)
            raise

        except IntegrityError as e:
            # Concurrent same-key race: two threads passed the dedupe check,
            # one INSERT won, this one hit the partial unique index. The
            # winner's booking exists — return it as a replay, but ONLY if
            # its fingerprint matches this request (Addendum-2 Option A:
            # the replay return is a read; no metadata write, no commit).
            db.session.rollback()
            if key:
                winner = Booking.query.filter_by(
                    idempotency_key=key,
                    user_id=customer_id,
                    is_deleted=False,
                ).first()
                if winner is not None:
                    stored_fp = (winner.booking_metadata or {}).get(
                        "trip_fingerprint")
                    if stored_fp is None:
                        raise ValidationError(
                            message="Idempotency key exists but cannot be "
                                    "verified. Refresh the page and try again.",
                            field="idempotency_key",
                        )
                    if stored_fp != _trip_fingerprint(sanitized_data):
                        raise ValidationError(
                            message="idempotency_key reused with a different trip",
                            field="idempotency_key",
                        )
                    logger.info(
                        f"Concurrent idempotent replay returned existing "
                        f"booking id={winner.id} (read-only)"
                    )
                    return {
                        "success": True,
                        "message": "Booking already exists (concurrent replay)",
                        "data": {
                            "booking_id": winner.id,
                            "booking_reference": winner.booking_reference,
                            "idempotent_replay": True,
                        },
                    }
            # Structural (CHECK-constraint) rejects are client errors with a
            # usable field, not service outages. Match by constraint name.
            _constraint_name = getattr(
                getattr(getattr(e, "orig", None), "diag", None),
                "constraint_name", None)
            _structural = {
                "ck_pickup_mode_valid": (
                    "booking_mode",
                    "booking_mode must be 'instant' or 'scheduled'.",
                ),
                "ck_pickup_time_mode_aware": (
                    "pickup_time",
                    "Pickup time does not match the selected booking mode.",
                ),
            }
            if _constraint_name in _structural:
                _field, _msg = _structural[_constraint_name]
                logger.info(
                    f"Structural constraint {_constraint_name} rejected booking "
                    f"for user_id={customer_id}"
                )
                raise ValidationError(message=_msg, field=_field)
            logger.error(
                f"IntegrityError with constraint={_constraint_name} — "
                f"cannot recover", exc_info=True)
            raise ServiceUnavailableError("Booking service temporarily unavailable")

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error in booking creation: {e}", exc_info=True)
            record_metric("booking_creation", tags={"status": "failed", "error_type": "database"}, value=1)
            raise ServiceUnavailableError("Booking service temporarily unavailable")

    @monitor_endpoint("get_booking")
    def get_booking(self, booking_id: int) -> Dict[str, Any]:
        cache_key = f"{self.cache_prefix}:{booking_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            booking = db.session.get(Booking, booking_id)
            if not booking or booking.is_deleted:
                raise NotFoundError("Booking not found", resource_type="booking", resource_id=booking_id)

            result = booking.to_dict()
            cache.set(cache_key, result, timeout=self.cache_ttl)
            return result

        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting booking {booking_id}: {e}", exc_info=True)
            raise ServiceUnavailableError("Could not retrieve booking details")

    @monitor_endpoint("cancel_booking")
    def cancel_booking(self, booking_id: int, user_id: int,
                       reason: Optional[str] = None,
                       reason_category: Optional[str] = None,
                       safety_flag: bool = False) -> Dict[str, Any]:
        """Cancel a booking with stage-aware policy.

        Rider may cancel in these stages:
          - PENDING_PAYMENT, CONFIRMED (pre-assignment): no fee normally
          - ASSIGNED: low/no protection during initial grace
          - DRIVER_EN_ROUTE: driver-protection compensation may apply
          - PICKUP_ARRIVED: stronger driver protection may apply
          - IN_PROGRESS, COMPLETED: NOT allowed (separate safety process)

        Safety/mismatch cancellations (reason_category in safety_categories)
        waive the cancellation fee.
        """
        from app.transport.services.assignment_service import (
            AssignmentService,
            DispatchClaimError,
            ACTIVE_ASSIGNMENT_STATUSES,
        )

        # Stage definitions
        PRE_ASSIGNMENT_STATUSES = {
            BookingStatusPy.PENDING_PAYMENT.value,
            BookingStatusPy.CONFIRMED.value,
        }
        POST_ASSIGNMENT_CANCELLABLE_STATUSES = {
            BookingStatusPy.ASSIGNED.value,
            BookingStatusPy.DRIVER_EN_ROUTE.value,
            BookingStatusPy.PICKUP_ARRIVED.value,
        }
        ALL_CANCELLABLE_STATUSES = PRE_ASSIGNMENT_STATUSES | POST_ASSIGNMENT_CANCELLABLE_STATUSES
        SAFETY_CATEGORIES = {
            'driver_vehicle_mismatch',
            'driver_identity_mismatch',
            'safety_concern',
            'driver_requested_cancel',
            'unexpected_driver_behaviour',
        }

        try:
            booking = db.session.get(Booking, booking_id)
            if not booking:
                raise NotFoundError("Booking not found", resource_type="booking", resource_id=booking_id)

            # Authorization: rider (booker), assigned driver, or provider/admin
            if booking.user_id != user_id and booking.assigned_driver_id != user_id and booking.provider_id != user_id:
                raise PermissionError("Cannot cancel another user's booking")

            if booking.is_deleted:
                raise NotFoundError("Booking not found", resource_type="booking", resource_id=booking_id)

            current_status = booking.status
            if current_status not in ALL_CANCELLABLE_STATUSES:
                raise ValidationError(
                    f"Cannot cancel booking in {current_status} stage. "
                    "Normal rider cancellation is only available before the trip starts."
                )

            # Determine if this is a safety/mismatch cancellation (fee waiver)
            is_safety_cancellation = (reason_category or '').lower() in SAFETY_CATEGORIES
            safety_flag = bool(safety_flag) or is_safety_cancellation

            # CANCEL-FEE-SCHEDULED-P1: only the rider pays; instant and
            # mode-less bookings are fail-safe zero; safety always waives.
            is_rider = (booking.user_id == user_id)
            initiated_by = "rider" if is_rider else "admin"
            policy = self._cancellation_policy(booking)
            cancellation_fee = policy["fee"]
            fee_tier = policy["tier"]
            if is_safety_cancellation:
                cancellation_fee = Decimal("0.00")
                fee_tier = "safety"
            elif not is_rider:
                cancellation_fee = Decimal("0.00")
                fee_tier = "non_rider"

            now = datetime.now(timezone.utc)
            booking_reference = booking.booking_reference
            final_price = _money(booking.final_price)
            refund_amount = _money(max(
                Decimal("0.00"), final_price - cancellation_fee
            ))

            metadata = dict(booking.booking_metadata or {})
            metadata["cancellation"] = {
                "fee": str(cancellation_fee),
                "currency": policy["currency"],
                "tier": fee_tier,
                "policy": "scheduled_v1",
                "recorded_uncollected": True,
                "initiated_by": initiated_by,
                "scheduled": policy["scheduled"],
                "percentage": (
                    0 if fee_tier in {"safety", "non_rider"}
                    else policy["percentage"]
                ),
                "at": now.isoformat(),
            }

            driver_credit = Decimal("0.00")
            if is_rider and cancellation_fee > 0 and booking.assigned_driver_id:
                driver = db.session.get(DriverProfile, booking.assigned_driver_id)
                if driver is not None:
                    driver_credit = _money(
                        cancellation_fee * DRIVER_LATE_CANCEL_CREDIT_RATE
                    )
                    metadata = self._append_driver_credit(
                        metadata,
                        booking=booking,
                        driver=driver,
                        amount=driver_credit,
                        currency=policy["currency"],
                        reason="late_cancellation",
                        now=now,
                    )
                else:
                    logger.warning(
                        "Assigned driver profile %s missing for booking %s; "
                        "cancellation credit not recorded",
                        booking.assigned_driver_id, booking_reference,
                    )

            audit_details = {
                "booking_reference": booking_reference,
                "fee": str(cancellation_fee),
                "currency": policy["currency"],
                "tier": fee_tier,
                "scheduled": policy["scheduled"],
                "recorded_uncollected": True,
                "initiated_by": initiated_by,
                "safety": safety_flag,
                "driver_credit": str(driver_credit),
            }

            if current_status in PRE_ASSIGNMENT_STATUSES:
                # Pre-assignment: one guarded UPDATE, including fee metadata.
                result = db.session.execute(
                    sa.update(Booking.__table__)
                    .where(
                        Booking.__table__.c.id == booking_id,
                        Booking.__table__.c.status.in_(list(PRE_ASSIGNMENT_STATUSES)),
                        Booking.__table__.c.is_deleted.is_(False),
                    )
                    .values(
                        status=BookingStatusPy.CANCELLED.value,
                        cancelled_at=now,
                        cancellation_reason=reason,
                        cancellation_reason_category=reason_category,
                        cancellation_safety_flag=safety_flag,
                        cancelled_stage=current_status,
                        cancellation_fee=cancellation_fee,
                        cancellation_initiated_by=initiated_by,
                        booking_metadata=metadata,
                    )
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    db.session.rollback()
                    raise ValidationError(
                        "Cannot cancel booking: it is no longer in a cancellable state"
                    )
                audit_log(
                    action="booking_cancellation_fee_recorded",
                    resource_type="booking",
                    resource_id=booking_id,
                    user_id=user_id,
                    details=audit_details,
                    db_session=db.session,
                )
                release_result = None
            else:
                # Post-assignment: compose fee/credit metadata first, then
                # let AssignmentService.release commit it atomically with
                # status= CANCELLED and resource clearing.
                try:
                    booking.cancelled_at = now
                    booking.cancellation_reason = reason
                    booking.cancellation_reason_category = reason_category
                    booking.cancellation_safety_flag = safety_flag
                    booking.cancelled_stage = current_status
                    booking.cancellation_fee = cancellation_fee
                    booking.cancellation_initiated_by = initiated_by
                    booking.booking_metadata = metadata
                    db.session.flush()
                    audit_log(
                        action="booking_cancellation_fee_recorded",
                        resource_type="booking",
                        resource_id=booking_id,
                        user_id=user_id,
                        details=audit_details,
                        db_session=db.session,
                    )
                    db.session.flush()
                    release_result = AssignmentService.release(
                        booking_id,
                        BookingStatusPy.CANCELLED,
                        actor=None,
                        reason=reason,
                        audit_extra={
                            "from": current_status,
                            "reason_category": reason_category,
                            "safety_flag": safety_flag,
                            "cancelled_by": initiated_by,
                            "cancellation_fee": str(cancellation_fee),
                            "fee_tier": fee_tier,
                            "driver_credit": str(driver_credit),
                        },
                    )
                except DispatchClaimError as e:
                    db.session.rollback()
                    raise ValidationError(e.message)

            db.session.commit()
            db.session.expire_all()
            self._invalidate_booking_caches(booking_id)

            # Send cancellation notification (includes driver if assigned)
            try:
                from app.transport.services.notification_service import NotificationService
                NotificationService.send_transport_notification(
                    booking_id=booking_id,
                    notification_type="booking_cancelled",
                    extra_data={
                        "cancellation_reason": reason,
                        "cancellation_reason_category": reason_category,
                        "safety_flag": safety_flag,
                    },
                )
            except Exception as e:
                logger.warning(f"Cancellation notification failed for booking {booking_id}: {e}")

            record_metric("booking_cancelled", tags={
                "status": "success",
                "stage": current_status,
                "safety": str(safety_flag).lower(),
            }, value=1)

            return {
                "success": True,
                "message": "Booking cancelled successfully",
                "data": {
                    "booking_reference": booking_reference,
                    "cancellation_fee": float(cancellation_fee),
                    "refund_amount": float(refund_amount),
                    "currency": policy["currency"],
                    "fee_tier": fee_tier,
                    "recorded_uncollected": True,
                    "driver_credit": float(driver_credit),
                    "stage_at_cancellation": current_status,
                    "safety_cancellation": safety_flag,
                    "release": release_result,
                }
            }

        except (NotFoundError, PermissionError, ValidationError) as e:
            db.session.rollback()
            record_metric("booking_cancelled", tags={"status": "failed", "error_type": type(e).__name__}, value=1)
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error cancelling booking {booking_id}: {e}", exc_info=True)
            raise ServiceUnavailableError("Could not cancel booking")

    @monitor_endpoint("mark_no_show")
    def mark_no_show(self, booking_id: int, driver_user_id: int,
                     reason: Optional[str] = None) -> Dict[str, Any]:
        """Record a scheduled rider no-show after the 15-minute grace.

        Only the assigned driver may call this. The no-show fee is 40% of
        the fare capped at 20,000 face value; the driver accrues 100% of
        that fee as uncollected metadata. The status transition and
        resource release remain owned by ``transition_status`` /
        ``AssignmentService`` — this method never writes the status
        directly and never writes ``no_show_at``.
        """
        from app.transport.services.assignment_service import (
            AssignmentService,
            DispatchClaimError,
        )

        try:
            booking = db.session.get(Booking, booking_id)
            if not booking or booking.is_deleted:
                raise NotFoundError(
                    "Booking not found", resource_type="booking",
                    resource_id=booking_id,
                )

            driver = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if driver is None:
                raise PermissionError(
                    "Only the assigned driver may mark a rider no-show"
                )

            metadata = dict(booking.booking_metadata or {})
            no_show = metadata.get("no_show") or {}
            if booking.status == BookingStatusPy.NO_SHOW.value:
                # Release clears assigned_driver_id, so idempotency is
                # proven by the recorded driver_code, not a live FK.
                if no_show.get("driver_code") != driver.driver_code:
                    raise PermissionError(
                        "Only the assigned driver may mark a rider no-show"
                    )
                return {
                    "success": True,
                    "message": "Rider no-show already recorded",
                    "data": {
                        "booking_reference": booking.booking_reference,
                        "status": BookingStatusPy.NO_SHOW.value,
                        "cancellation_fee": float(
                            _money(no_show.get("fee"))
                        ),
                        "driver_credit": float(
                            _money(no_show.get("driver_credit"))
                        ),
                        "currency": no_show.get("currency")
                        or _booking_currency_code(booking),
                        "idempotent": True,
                    },
                }

            if booking.assigned_driver_id != driver.id:
                raise PermissionError(
                    "Only the assigned driver may mark a rider no-show"
                )

            if booking.status != BookingStatusPy.PICKUP_ARRIVED.value:
                raise ValidationError(
                    "A rider no-show can only be recorded after the driver "
                    "has arrived at the pickup location"
                )
            if _booking_mode(booking) != SCHEDULED_BOOKING_MODE:
                raise ValidationError(
                    "Rider no-show is only available for scheduled rides"
                )

            pickup = _as_utc(booking.pickup_time)
            if pickup is None:
                raise ValidationError(
                    "Rider no-show requires a released pickup time"
                )

            now = datetime.now(timezone.utc)
            if now < pickup + NO_SHOW_GRACE:
                raise ValidationError(
                    "Rider no-show can only be recorded 15 minutes after "
                    "the scheduled pickup time"
                )

            fee = self._calculate_no_show_fee(booking)
            currency = _booking_currency_code(booking)
            driver_user_public_id = getattr(
                getattr(driver, "user", None), "public_id", None
            )

            metadata["no_show"] = {
                "fee": str(fee),
                "currency": currency,
                "recorded_uncollected": True,
                "grace_minutes": int(NO_SHOW_GRACE.total_seconds() // 60),
                "marked_at": now.isoformat(),
                "marked_by": "driver",
                "driver_code": driver.driver_code,
                "driver_user_public_id": (
                    str(driver_user_public_id)
                    if driver_user_public_id is not None else None
                ),
                "driver_credit": str(fee),
            }
            metadata = self._append_driver_credit(
                metadata,
                booking=booking,
                driver=driver,
                amount=fee,
                currency=currency,
                reason="no_show",
                now=now,
            )

            booking.cancellation_fee = fee
            booking.cancellation_reason = reason or "rider_no_show"
            booking.cancellation_reason_category = "rider_no_show"
            booking.cancellation_safety_flag = False
            booking.cancelled_stage = BookingStatusPy.PICKUP_ARRIVED.value
            booking.cancellation_initiated_by = "driver"
            booking.booking_metadata = metadata
            db.session.flush()

            audit_log(
                action="booking_no_show_recorded",
                resource_type="booking",
                resource_id=booking_id,
                user_id=driver_user_id,
                details={
                    "booking_reference": booking.booking_reference,
                    "fee": str(fee),
                    "currency": currency,
                    "driver_credit": str(fee),
                    "recorded_uncollected": True,
                    "driver_code": driver.driver_code,
                    "driver_user_public_id": (
                        str(driver_user_public_id)
                        if driver_user_public_id is not None else None
                    ),
                },
                db_session=db.session,
            )
            db.session.flush()

            self.transition_status(
                booking_id,
                BookingStatusPy.NO_SHOW,
                reason=reason or "rider_no_show",
                initiated_by="driver",
                actor=None,
            )
            self._invalidate_booking_caches(booking_id)

            return {
                "success": True,
                "message": "Rider no-show recorded",
                "data": {
                    "booking_reference": booking.booking_reference,
                    "status": BookingStatusPy.NO_SHOW.value,
                    "cancellation_fee": float(fee),
                    "driver_credit": float(fee),
                    "currency": currency,
                    "recorded_uncollected": True,
                    "idempotent": False,
                },
            }

        except DispatchClaimError as e:
            db.session.rollback()
            raise ValidationError(e.message)
        except (NotFoundError, PermissionError, ValidationError):
            db.session.rollback()
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(
                f"Database error marking no-show for booking {booking_id}: {e}",
                exc_info=True,
            )
            raise ServiceUnavailableError("Could not record rider no-show")

    @monitor_endpoint("driver_cancel")
    def driver_cancel(self, booking_id: int, driver_user_id: int,
                      reason: Optional[str] = None) -> Dict[str, Any]:
        """Driver cancels an accepted trip before it starts.

        The ride becomes NO_MATCH so the rider is prompted to search again;
        the driver/vehicle assignment is released atomically and the rider
        is notified. This is deliberately NOT a paid cancellation: no
        cancellation_* field, fee, wallet, or earnings write occurs. Driver
        accountability is recorded as booking metadata plus the canonical
        ``dispatch_release`` audit row.

        Allowed only in ASSIGNED / DRIVER_EN_ROUTE / PICKUP_ARRIVED. Once
        IN_PROGRESS, the driver must complete the trip (or support must
        intervene); a started trip is never cancelled by this path.
        """
        from app.transport.services.assignment_service import (
            AssignmentService,
            DispatchClaimError,
        )

        try:
            booking = db.session.get(
                Booking, booking_id, with_for_update=True
            )
            if not booking or booking.is_deleted:
                raise NotFoundError(
                    "Booking not found", resource_type="booking",
                    resource_id=booking_id,
                )

            driver = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if driver is None:
                raise PermissionError(
                    "Only the assigned driver may cancel this trip"
                )

            current_status = (
                booking.status.value
                if hasattr(booking.status, "value")
                else str(booking.status)
            )
            metadata = dict(booking.booking_metadata or {})
            existing = metadata.get("driver_cancellations")
            if not isinstance(existing, list):
                existing = []

            if current_status == BookingStatusPy.NO_MATCH.value:
                if metadata.get("no_match_cause") != "driver_cancelled":
                    raise ValidationError(
                        "This ride is already closed as no match"
                    )
                recorded = existing[-1] if existing else {}
                if recorded.get("driver_code") != driver.driver_code:
                    raise PermissionError(
                        "Only the driver who cancelled this trip may replay it"
                    )
                return {
                    "success": True,
                    "message": "Trip cancellation already recorded",
                    "data": {
                        "booking_reference": booking.booking_reference,
                        "status": BookingStatusPy.NO_MATCH.value,
                        "no_match_reason": booking.no_match_reason,
                        "cancelled_stage": recorded.get("stage"),
                        "idempotent": True,
                    },
                }

            if current_status == BookingStatusPy.IN_PROGRESS.value:
                raise ValidationError(
                    "This trip has already started. Complete the trip or "
                    "contact support; drivers cannot cancel an in-progress "
                    "trip."
                )
            if current_status not in {
                BookingStatusPy.ASSIGNED.value,
                BookingStatusPy.DRIVER_EN_ROUTE.value,
                BookingStatusPy.PICKUP_ARRIVED.value,
            }:
                raise ValidationError(
                    f"Cannot cancel a trip in {current_status} stage"
                )
            if booking.assigned_driver_id != driver.id:
                raise PermissionError(
                    "Only the assigned driver may cancel this trip"
                )

            now = datetime.now(timezone.utc)
            driver_user_public_id = getattr(
                getattr(driver, "user", None), "public_id", None
            )
            record = {
                "driver_code": driver.driver_code,
                "driver_user_public_id": (
                    str(driver_user_public_id)
                    if driver_user_public_id is not None else None
                ),
                "stage": current_status,
                "reason": reason or "driver_cancelled",
                "at": now.isoformat(),
                "booking_reference": booking.booking_reference,
            }
            metadata["no_match_cause"] = "driver_cancelled"
            metadata["driver_cancellations"] = list(existing) + [record]
            booking.booking_metadata = metadata
            booking.audit_log = (booking.audit_log or []) + [{
                "action": "driver_cancelled_before_start",
                "from": current_status,
                "to": BookingStatusPy.NO_MATCH.value,
                "at": now.isoformat(),
                "reason": record["reason"],
                "driver_code": driver.driver_code,
                "driver_user_public_id": record["driver_user_public_id"],
            }]
            db.session.flush()

            release_result = AssignmentService.release_to_no_match(
                booking_id,
                "all_rejected",
                actor=None,
                audit_extra={
                    "from": current_status,
                    "cancelled_by": "driver",
                    "driver_code": driver.driver_code,
                    "driver_user_public_id": record["driver_user_public_id"],
                },
            )
            self._invalidate_booking_caches(booking_id)

            try:
                from app.transport.services.notification_service import (
                    NotificationService,
                )
                NotificationService.send_booking_notification(
                    booking_id,
                    "driver_cancelled",
                    {
                        "driver_cancelled_stage": current_status,
                        "reason": record["reason"],
                    },
                )
            except Exception as e:
                logger.warning(
                    f"Driver-cancel notification failed for booking "
                    f"{booking_id}: {e}"
                )

            record_metric(
                "driver_trip_cancelled",
                tags={"stage": current_status, "status": "success"},
                value=1,
            )
            return {
                "success": True,
                "message": (
                    "Trip cancelled. The rider has been notified and asked "
                    "to search again."
                ),
                "data": {
                    "booking_reference": booking.booking_reference,
                    "status": BookingStatusPy.NO_MATCH.value,
                    "no_match_reason": "all_rejected",
                    "cancelled_stage": current_status,
                    "idempotent": False,
                    "release": release_result,
                },
            }

        except DispatchClaimError as e:
            db.session.rollback()
            raise ValidationError(e.message)
        except (NotFoundError, PermissionError, ValidationError):
            db.session.rollback()
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(
                f"Database error cancelling trip {booking_id} by driver: {e}",
                exc_info=True,
            )
            raise ServiceUnavailableError("Could not cancel the trip")

    @staticmethod
    def transition_status(booking_id: int, new_status: "BookingStatusPy",
                          *, reason: Optional[str] = None,
                          initiated_by: str = "admin",
                          actor=None) -> Dict[str, Any]:
        """Canonical guarded booking status transition (STATUS_TRANSITIONS).

        Single authority shared by the admin status endpoint and the
        moderator action. Enforces the transition map; terminal
        transitions on assigned bookings go through
        AssignmentService.release (status + assignment clearing + resource
        freeing in one transaction); lifecycle timestamps, cancellation
        fields and audit_log entries mirror the established semantics.

        Returns {"booking": refreshed Booking, "release": release result
        or None}. Raises NotFoundError / ValidationError (illegal edge) /
        DispatchClaimError (release refusal) / ServiceUnavailableError.
        """
        from app.transport.services.assignment_service import (
            AssignmentService,
            DispatchClaimError,
            TERMINAL_RELEASE_STATUSES,
        )

        if not isinstance(new_status, BookingStatusPy):
            raise ValidationError(
                message=f"Invalid status: {new_status}",
                field="status",
            )

        booking = db.session.get(Booking, booking_id)
        if not booking or booking.is_deleted:
            raise NotFoundError("Booking not found",
                                resource_type="booking",
                                resource_id=booking_id)

        if not _can_transition(booking.status, new_status):
            raise ValidationError(
                message=f"Cannot transition from {booking.status} "
                        f"to {new_status.value}",
                field="status",
            )

        old_status = booking.status
        now = datetime.now(timezone.utc)

        if new_status in TERMINAL_RELEASE_STATUSES and (
            booking.assigned_driver_id is not None
            or booking.assigned_vehicle_id is not None
        ):
            if new_status == BookingStatusPy.COMPLETED:
                booking.completed_at = now
            elif new_status == BookingStatusPy.CANCELLED:
                booking.cancelled_at = now
                booking.cancellation_reason = (
                    reason if reason is not None else "admin_action"
                )
                booking.cancellation_initiated_by = initiated_by
            try:
                release_result = AssignmentService.release(
                    booking_id,
                    new_status,
                    actor=actor,
                    reason=reason,
                    audit_extra={"from": old_status},
                )
            except DispatchClaimError:
                db.session.rollback()
                raise
            refreshed = db.session.get(Booking, booking_id)
            logger.info(
                f"Booking {booking_id} released via canonical dispatch "
                f"-> {new_status.value}"
            )
            return {"booking": refreshed, "release": release_result}

        booking.status = new_status

        # Set lifecycle timestamps automatically
        if new_status == BookingStatusPy.CONFIRMED:
            booking.confirmed_at = now
            # MATCH-01-owned: (re)start the matching window cursor. Kept in
            # booking_metadata (transient matching cursor, not audit history)
            # so confirmed_at keeps its first-confirmation meaning for the
            # rider timeline and admin reports (review Condition 1, option
            # chosen: dedicated cursor, zero-column variant).
            _stamp_matching_window_start(booking, now)
        elif new_status == BookingStatusPy.COMPLETED:
            booking.completed_at = now
        elif new_status == BookingStatusPy.CANCELLED:
            booking.cancelled_at = now
            booking.cancellation_reason = (
                reason if reason is not None else "admin_action"
            )
            booking.cancellation_initiated_by = initiated_by

        # Append to audit log
        booking.audit_log = (booking.audit_log or []) + [{
            "action": "status_changed",
            "from": old_status,
            "to": new_status.value,
            "at": now.isoformat(),
            "reason": reason,
        }]

        try:
            db.session.commit()
            logger.info(
                f"Booking {booking_id} status: {old_status} → "
                f"{new_status.value}"
            )
            # transition_status is a @staticmethod: invalidate via an
            # instance (cheap; prefix is a class constant).
            BookingService()._invalidate_booking_caches(booking_id)
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error transitioning booking {booking_id}: {e}",
                         exc_info=True)
            raise ServiceUnavailableError("Could not transition booking")
        return {"booking": booking, "release": None}

    # =========================================================
    # MATCH-01-owned: terminal matching-failure transitions (additive).
    # cancel_booking and its helpers above are untouched.
    # =========================================================

    @staticmethod
    def mark_no_match(booking_id: int, reason: str,
                      *, initiated_by: str = "system") -> Dict[str, Any]:
        """Close a CONFIRMED+unassigned booking as NO_MATCH with a reason.

        ``reason`` must be ``no_supply`` (no candidates ever offered within
        the window) or ``all_rejected`` (pool exhausted). Idempotent: a
        booking already in NO_MATCH returns success without rewriting
        (review Condition 5 — rider poll + beat may both fire).

        App-level invariant (holds pre-migration): NO_MATCH without a valid
        reason is refused here; the DB CHECK (chk_no_match_reason) enforces
        the same post-migration. Never touches cancellation_* fields, never
        assigns a driver, never refunds — matching failure is not a
        cancellation.
        """
        from app.transport.services.matching_service import NO_MATCH_REASONS

        if reason not in NO_MATCH_REASONS:
            raise ValidationError(
                message=f"Invalid no_match reason: {reason}",
                field="no_match_reason",
            )
        booking = db.session.get(Booking, booking_id)
        if not booking or booking.is_deleted:
            raise NotFoundError("Booking not found",
                                resource_type="booking",
                                resource_id=booking_id)
        if booking.status == BookingStatusPy.NO_MATCH:
            return {"booking": booking, "replayed": True,
                    "reason": booking.no_match_reason}
        if booking.status != BookingStatusPy.CONFIRMED:
            raise ValidationError(
                message=f"Cannot mark no_match from {booking.status}",
                field="status",
            )
        if (booking.assigned_driver_id is not None
                or booking.assigned_vehicle_id is not None):
            raise ValidationError(
                message="Cannot mark no_match on an assigned booking",
                field="status",
            )
        now = datetime.now(timezone.utc)
        old_status = booking.status
        result = db.session.execute(
            sa.update(Booking.__table__)
            .where(
                Booking.__table__.c.id == booking_id,
                Booking.__table__.c.status == BookingStatusPy.CONFIRMED.value,
                Booking.__table__.c.assigned_driver_id.is_(None),
                Booking.__table__.c.assigned_vehicle_id.is_(None),
                Booking.__table__.c.is_deleted.is_(False),
            )
            .values(
                status=BookingStatusPy.NO_MATCH.value,
                no_match_reason=reason,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.session.rollback()
            refreshed = db.session.get(Booking, booking_id)
            if refreshed is not None and refreshed.status == BookingStatusPy.NO_MATCH:
                return {"booking": refreshed, "replayed": True,
                        "reason": refreshed.no_match_reason}
            raise ValidationError(
                "Cannot mark no_match: booking is no longer awaiting matching"
            )
        db.session.commit()
        db.session.expire_all()
        refreshed = db.session.get(Booking, booking_id)
        refreshed.audit_log = (refreshed.audit_log or []) + [{
            "action": "marked_no_match",
            "from": old_status,
            "to": BookingStatusPy.NO_MATCH.value,
            "at": now.isoformat(),
            "reason": reason,
            "initiated_by": initiated_by,
        }]
        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error appending no_match audit for {booking_id}: {e}",
                         exc_info=True)
            raise ServiceUnavailableError("Could not record matching outcome")
        BookingService()._invalidate_booking_caches(booking_id)
        logger.info(f"Booking {booking_id} marked no_match ({reason})")
        return {"booking": refreshed, "replayed": False, "reason": reason}

    @staticmethod
    def retry_matching(booking_id: int, user_id: int) -> Dict[str, Any]:
        """Manual rider "Try again": NO_MATCH -> CONFIRMED + fresh window.

        Authorization mirrors cancel_booking's rider check (booker only;
        admins use the admin status endpoint). The status change, the
        no_match_reason clear (so chk_no_match_reason holds) and the
        matching-window cursor reset (review Condition 1) happen in ONE
        ORM transaction on a FOR UPDATE-locked row, so no recovery or
        dispatch beat can observe CONFIRMED with a stale cursor.
        confirmed_at is first-confirmation audit history and is
        deliberately NOT rewritten. Then immediately re-runs
        discover_and_offer. No auto-retry exists anywhere else.
        """
        booking = db.session.get(Booking, booking_id, with_for_update=True)
        if not booking or booking.is_deleted:
            raise NotFoundError("Booking not found",
                                resource_type="booking",
                                resource_id=booking_id)
        if booking.user_id != user_id:
            raise PermissionError("Cannot retry another user's ride")
        if booking.status != BookingStatusPy.NO_MATCH:
            raise ValidationError(
                message=f"Retry is only available from no_match "
                        f"(current: {booking.status})",
                field="status",
            )
        now = datetime.now(timezone.utc)
        booking.status = BookingStatusPy.CONFIRMED
        booking.no_match_reason = None
        # Driver-cancel provenance is closed by the retry: a new match
        # attempt must not inherit the previous close cause.
        metadata = dict(booking.booking_metadata or {})
        metadata.pop("no_match_cause", None)
        booking.booking_metadata = metadata
        # Fresh window cursor (Condition 1): metadata cursor reset in the
        # same transaction as the status change. confirmed_at is left
        # untouched as immutable first-confirmation audit history.
        _stamp_matching_window_start(booking, now)
        booking.audit_log = (booking.audit_log or []) + [{
            "action": "retry_matching",
            "from": BookingStatusPy.NO_MATCH.value,
            "to": BookingStatusPy.CONFIRMED.value,
            "at": now.isoformat(),
            "reason": "rider_retry",
            "initiated_by": "rider",
        }]
        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error committing retry for {booking_id}: {e}",
                         exc_info=True)
            raise ServiceUnavailableError("Could not restart matching")
        BookingService()._invalidate_booking_caches(booking_id)
        offers_created = 0
        try:
            from app.transport.services.matching_service import MatchingService
            outcome = MatchingService.discover_and_offer(booking_id)
            offers_created = int(outcome.get("offers_created", 0))
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Retry re-dispatch soft-failed for {booking_id}: {e}")
        return {"booking": booking, "replayed": False,
                "offers_created": offers_created}

    # =========================================================
    # List & Analytics (Enhanced for Admin Dashboard)
    # =========================================================

    @monitor_endpoint("count_bookings")
    def count_bookings(self) -> int:
        """Count total number of active bookings"""
        try:
            return Booking.query.filter_by(is_deleted=False).count()
        except Exception as e:
            logger.error(f"Error counting bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("count_bookings_by_status")
    def count_bookings_by_status(self, status: str) -> int:
        """Count bookings with specific status (for dashboard)"""
        try:
            # Map input string to BookingStatus enum
            status_upper = status.upper()
            # If status is something like 'pending', we need to map to BookingStatusPy.PENDING
            # Using getattr to safely get enum member
            status_enum = getattr(BookingStatusPy, status_upper, None)
            if status_enum is None:
                logger.error(f"Invalid status string: {status}")
                return 0

            return Booking.query.filter_by(
                status=status_enum,
                is_deleted=False
            ).count()
        except Exception as e:
            logger.error(f"Error counting bookings by status: {e}", exc_info=True)
            return 0

    @monitor_endpoint("get_recent_bookings")
    def get_recent_bookings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent bookings (for dashboard)"""
        try:
            bookings = Booking.query.filter_by(
                is_deleted=False
            ).order_by(
                Booking.created_at.desc()
            ).limit(limit).all()
            return [b.to_dict() for b in bookings]
        except Exception as e:
            logger.error(f"Error getting recent bookings: {e}", exc_info=True)
            return []

    @monitor_endpoint("get_user_bookings")
    def get_user_bookings(
        self,
        user_id: int,
        limit: int = 5,
        *,
        include_cancelled: bool = False,
        include_draft: bool = False,
        q: str = "",
    ) -> List[Dict[str, Any]]:
        """Recent bookings for one authenticated user.

        Default excludes bookings that never became rides:
          * CANCELLED — user withdrew, no trip happened
          * DRAFT     — never submitted, only a skeleton

        Callers that need the full history (e.g. My Trips list) can opt in
        via ``include_cancelled=True`` / ``include_draft=True``.

        ``q`` (optional) narrows the result to bookings whose reference,
        pickup/dropoff address, or pickup/dropoff location text contains
        the term (case-insensitive). Wildcard characters in ``q`` are
        escaped so they match literally.

        Used by the Transport front page to render a truthful, user-scoped
        Recent Rides list. Never returns another user's bookings.
        """
        try:
            query = Booking.query.filter(
                Booking.user_id == user_id,
                Booking.is_deleted == False  # noqa: E712
            )

            excluded: List[BookingStatusPy] = []
            if not include_cancelled:
                excluded.append(BookingStatusPy.CANCELLED)
            if not include_draft:
                excluded.append(BookingStatusPy.DRAFT)
            if excluded:
                query = query.filter(~Booking.status.in_(excluded))

            term = (q or "").strip()
            if term:
                escaped = (
                    term.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                pattern = f"%{escaped}%"
                query = query.filter(
                    sa.or_(
                        Booking.booking_reference.ilike(pattern),
                        Booking.pickup_address.ilike(pattern),
                        Booking.dropoff_address.ilike(pattern),
                        sa.cast(Booking.pickup_location, sa.Text).ilike(pattern),
                        sa.cast(Booking.dropoff_location, sa.Text).ilike(pattern),
                    )
                )

            bookings = (
                query
                .order_by(
                    Booking.created_at.desc()
                ).limit(limit).all()
            )
            # Build the light-weight dict explicitly (Booking.to_dict depends on
            # app.core.serializers.ModelSerializer which is not present).
            routes = []
            for b in bookings:
                pickup = b.pickup_address
                if not pickup and isinstance(b.pickup_location, dict):
                    pickup = b.pickup_location.get("address") or b.pickup_location.get(
                        "name") or b.pickup_location.get("label")
                dropoff = b.dropoff_address
                if not dropoff and isinstance(b.dropoff_location, dict):
                    dropoff = b.dropoff_location.get("address") or b.dropoff_location.get(
                        "name") or b.dropoff_location.get("label")
                routes.append({
                    "booking_id": b.id,
                    "booking_reference": b.booking_reference,
                    "pickup_location": pickup or "Pickup",
                    "dropoff_location": dropoff or "Destination",
                    "status": b.status if b.status else None,
                    "pickup_time": b.pickup_time.isoformat() if b.pickup_time else None,
                    "booking_mode": (
                        b.booking_metadata.get("booking_mode")
                        if isinstance(b.booking_metadata, dict) else None
                    ),
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                    "final_price": float(b.final_price) if b.final_price is not None else None,
                    "currency": b.currency.value if b.currency else None,
                })
            return routes
        except Exception as e:
            logger.error(f"Error getting bookings for user {user_id}: {e}", exc_info=True)
            return []

    @monitor_endpoint("count_user_bookings")
    def count_user_bookings(self, user_id: int) -> int:
        """Count the active (non-deleted) bookings for a single user."""
        try:
            return Booking.query.filter(
                Booking.user_id == user_id,
                Booking.is_deleted == False  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting bookings for user {user_id}: {e}", exc_info=True)
            return 0

    @monitor_endpoint("get_today_bookings_count")
    def get_today_bookings_count(self) -> int:
        """Get number of bookings created today"""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            return Booking.query.filter(
                Booking.created_at >= today_start,
                Booking.is_deleted == False
            ).count()
        except Exception as e:
            logger.error(f"Error counting today's bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("get_today_revenue")
    def get_today_revenue(self) -> float:
        """Get total revenue from today's completed bookings"""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            # Use final_price as the actual paid amount
            revenue = db.session.query(func.sum(Booking.final_price)).filter(
                Booking.created_at >= today_start,
                Booking.status == BookingStatusPy.COMPLETED,
                Booking.is_deleted == False
            ).scalar() or 0
            return float(revenue)
        except Exception as e:
            logger.error(f"Error calculating today's revenue: {e}", exc_info=True)
            return 0.0

    @monitor_endpoint("get_active_bookings_count")
    def get_active_bookings_count(self) -> int:
        """Get count of active bookings (in progress, confirmed, assigned)"""
        try:
            return Booking.query.filter(
                Booking.status.in_([
                    BookingStatusPy.CONFIRMED,
                    BookingStatusPy.ASSIGNED,
                    BookingStatusPy.IN_PROGRESS
                ]),
                Booking.is_deleted == False
            ).count()
        except Exception as e:
            logger.error(f"Error counting active bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("generate_booking_report")
    def generate_booking_report(self, days: int = 30) -> Dict[str, Any]:
        """Generate comprehensive booking report for dashboard"""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Total bookings in period
            total = Booking.query.filter(
                Booking.created_at >= cutoff,
                Booking.is_deleted == False
            ).count()

            # Bookings by status
            by_status = {}
            for status_enum in BookingStatusPy:
                count = Booking.query.filter(
                    Booking.created_at >= cutoff,
                    Booking.status == status_enum,
                    Booking.is_deleted == False
                ).count()
                by_status[status_enum.value] = count

            # Revenue metrics - using final_price for completed/confirmed
            revenue = db.session.query(func.sum(Booking.final_price)).filter(
                Booking.created_at >= cutoff,
                Booking.status.in_([BookingStatusPy.COMPLETED, BookingStatusPy.CONFIRMED]),
                Booking.is_deleted == False
            ).scalar() or 0

            # Daily breakdown for charts
            daily_data = []
            for i in range(days):
                day = cutoff + timedelta(days=i)
                next_day = day + timedelta(days=1)
                day_count = Booking.query.filter(
                    Booking.created_at >= day,
                    Booking.created_at < next_day,
                    Booking.is_deleted == False
                ).count()
                daily_data.append({
                    'date': day.strftime('%Y-%m-%d'),
                    'count': day_count
                })

            return {
                "period_days": days,
                "total_bookings": total,
                "by_status": by_status,
                "total_revenue": float(revenue),
                "average_booking_value": float(revenue / total) if total else 0,
                "daily_breakdown": daily_data
            }

        except Exception as e:
            logger.error(f"Error generating booking report: {e}", exc_info=True)
            return {
                "period_days": days,
                "total_bookings": 0,
                "by_status": {},
                "total_revenue": 0,
                "average_booking_value": 0,
                "daily_breakdown": []
            }

    # =========================================================
    # Admin Listing & Driver-scoped Queries
    # =========================================================

    @monitor_endpoint("list_all_bookings")
    def list_all_bookings(self, page: int = 1, per_page: int = 25) -> Dict[str, Any]:
        """List all bookings with pagination (admin dashboard)."""
        try:
            query = Booking.query.filter_by(
                is_deleted=False
            ).order_by(Booking.created_at.desc())
            paginated = query.paginate(page=page, per_page=per_page, error_out=False)
            return {
                'items': [b.to_dict() for b in paginated.items],
                'total': paginated.total,
                'page': page,
                'per_page': per_page,
                'pages': paginated.pages,
            }
        except Exception as e:
            logger.error(f"Error listing all bookings: {e}", exc_info=True)
            return {
                'items': [], 'total': 0,
                'page': page, 'per_page': per_page, 'pages': 0,
            }

    @staticmethod
    def _driver_trip_row(booking: Booking) -> Dict[str, Any]:
        """Serialized booking row plus its canonical display strings.

        ModelSerializer serializes columns only, so the derived
        ``pickup_location_text`` / ``dropoff_location_text`` properties
        never reached the driver dashboard context (Node 3, D1) and every
        trip route rendered its literal 'Pickup' / 'Dropoff' fallback.

        CANCEL-FEE-SCHEDULED-P1 adds the metadata mode and the server's
        no-show eligibility. The driver page must never decide the grace
        window client-side.
        """
        status = getattr(booking, "status", "")
        if hasattr(status, "value"):
            status = status.value
        mode = _booking_mode(booking)
        pickup = _as_utc(getattr(booking, "pickup_time", None))
        now = datetime.now(timezone.utc)
        can_mark_no_show = bool(
            status == BookingStatusPy.PICKUP_ARRIVED.value
            and mode == SCHEDULED_BOOKING_MODE
            and pickup is not None
            and now >= pickup + NO_SHOW_GRACE
            and getattr(booking, "assigned_driver_id", None) is not None
        )
        payment_status = getattr(booking, "payment_status", None)
        if hasattr(payment_status, "value"):
            payment_status = payment_status.value
        metadata = booking.booking_metadata or {}
        return {
            **booking.to_dict(),
            "booking_mode": mode,
            "can_mark_no_show": can_mark_no_show,
            "pickup_location_text": booking.pickup_location_text,
            "dropoff_location_text": booking.dropoff_location_text,
            # Explicit driver-workspace display facts. Do not expose the full
            # booking metadata blob merely to show a post-trip cash action.
            "payment_method": booking.payment_method,
            "payment_status": payment_status,
            "completed_by_driver_profile_id": metadata.get(
                "completed_by_driver_profile_id"
            ),
        }

    @monitor_endpoint("get_driver_bookings")
    def get_driver_bookings(self, driver_user_id: int) -> List[Dict[str, Any]]:
        """Get bookings assigned to a driver, looked up by the driver's user_id.

        The driver dashboard calls this to show the driver's assigned rides.
        """
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return []
            bookings = Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(Booking.created_at.desc()).limit(20).all()
            return [self._driver_trip_row(b) for b in bookings]
        except Exception as e:
            logger.error(f"Error getting driver bookings for user {driver_user_id}: {e}", exc_info=True)
            return []

    @monitor_endpoint("count_bookings_since")
    def count_bookings_since(self, since: datetime) -> int:
        """Count bookings created since a given datetime."""
        try:
            return Booking.query.filter(
                Booking.created_at >= since,
                Booking.is_deleted == False,  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting bookings since {since}: {e}", exc_info=True)
            return 0

    @monitor_endpoint("count_driver_bookings")
    def count_driver_bookings(self, driver_user_id: int) -> int:
        """Count total bookings for a driver (by user_id)."""
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return 0
            return Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.is_deleted == False,  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting driver bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("count_driver_bookings_by_status")
    def count_driver_bookings_by_status(self, driver_user_id: int, status: str) -> int:
        """Count driver bookings with a specific status."""
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return 0
            status_enum = getattr(BookingStatusPy, status.upper(), None)
            if status_enum is None:
                return 0
            return Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.status == status_enum,
                Booking.is_deleted == False,  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting driver bookings by status: {e}", exc_info=True)
            return 0

    @monitor_endpoint("get_driver_upcoming_bookings")
    def get_driver_upcoming_bookings(self, driver_user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Get upcoming bookings for a driver."""
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return []
            now = datetime.now(timezone.utc)
            bookings = Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.status.in_([BookingStatusPy.CONFIRMED, BookingStatusPy.ASSIGNED, BookingStatusPy.DRIVER_EN_ROUTE]),
                sa.or_(
                    Booking.pickup_mode == "instant",
                    Booking.pickup_time > now,
                ),
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(
                func.coalesce(Booking.pickup_time, Booking.created_at).asc()
            ).limit(limit).all()
            return [self._driver_trip_row(b) for b in bookings]
        except Exception as e:
            logger.error(f"Error getting driver upcoming bookings: {e}", exc_info=True)
            return []

    @monitor_endpoint("get_driver_earnings")
    def get_driver_earnings(self, driver_user_id: int) -> float:
        """Total driver earnings across completed + captured bookings.

        Applies the driver's commission_rate (percentage the PLATFORM keeps)
        so the returned number is the driver's payout, not the gross fare the
        rider paid.

        Note: commission_rate lives on DriverProfile, not per-booking. If the
        rate changes over time, historical completed bookings are recomputed
        at the current rate. Snapshotting the rate per booking is deferred
        (see S-18).
        """
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return 0.0

            gross = (
                db.session.query(func.sum(Booking.final_price))
                .filter(
                    Booking.assigned_driver_id == profile.id,
                    Booking.status == BookingStatusPy.COMPLETED,
                    Booking.payment_status == PaymentStatus.CAPTURED,
                    Booking.is_deleted == False,  # noqa: E712
                )
                .scalar()
                or 0
            )
            gross = float(gross)
            if gross <= 0:
                return 0.0

            rate = profile.commission_rate
            if rate is None:
                rate_pct = 15.0
            else:
                try:
                    rate_pct = float(rate)
                except (TypeError, ValueError):
                    rate_pct = 15.0

            if rate_pct < 0:
                rate_pct = 0.0
            elif rate_pct > 100:
                rate_pct = 100.0

            return round(gross * (1.0 - rate_pct / 100.0), 2)

        except Exception as e:
            logger.error(f"Error getting driver earnings: {e}", exc_info=True)
            return 0.0

    @monitor_endpoint("get_driver_recent_bookings")
    def get_driver_recent_bookings(self, driver_user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent bookings for a driver."""
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return []
            completed_by_this_driver = sa.and_(
                Booking.status == BookingStatusPy.COMPLETED.value,
                Booking.booking_metadata["completed_by_driver_profile_id"].astext
                == str(profile.id),
            )
            bookings = Booking.query.filter(
                sa.or_(
                    Booking.assigned_driver_id == profile.id,
                    completed_by_this_driver,
                ),
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(Booking.created_at.desc()).limit(limit).all()
            return [self._driver_trip_row(b) for b in bookings]
        except Exception as e:
            logger.error(f"Error getting driver recent bookings: {e}", exc_info=True)
            return []

    @monitor_endpoint("get_driver_next_booking")
    def get_driver_next_booking(self, driver_user_id: int) -> Optional[Dict[str, Any]]:
        """Get the next upcoming booking for a driver."""
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return None
            now = datetime.now(timezone.utc)
            booking = Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.status.in_([BookingStatusPy.ASSIGNED, BookingStatusPy.DRIVER_EN_ROUTE]),
                sa.or_(
                    Booking.pickup_mode == "instant",
                    Booking.pickup_time > now,
                ),
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(
                func.coalesce(Booking.pickup_time, Booking.created_at).asc()
            ).first()
            return booking.to_dict() if booking else None
        except Exception as e:
            logger.error(f"Error getting driver next booking: {e}", exc_info=True)
            return None

    @monitor_endpoint("count_org_bookings")
    def count_org_bookings(self, org_id: int) -> int:
        """Count bookings for an organisation."""
        try:
            return Booking.query.filter(
                Booking.provider_id == org_id,
                Booking.is_deleted == False,  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting org bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("count_org_today_bookings")
    def count_org_today_bookings(self, org_id: int) -> int:
        """Count today's bookings for an organisation."""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            return Booking.query.filter(
                Booking.provider_id == org_id,
                Booking.created_at >= today_start,
                Booking.is_deleted == False,  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting org today bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("get_org_revenue")
    def get_org_revenue(self, org_id: int) -> float:
        """Get total revenue for an organisation from completed bookings."""
        try:
            revenue = db.session.query(func.sum(Booking.final_price)).filter(
                Booking.provider_id == org_id,
                Booking.status == BookingStatusPy.COMPLETED,
                Booking.is_deleted == False,  # noqa: E712
            ).scalar() or 0
            return float(revenue)
        except Exception as e:
            logger.error(f"Error getting org revenue: {e}", exc_info=True)
            return 0.0

    @monitor_endpoint("get_org_recent_bookings")
    def get_org_recent_bookings(self, org_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent bookings for an organisation."""
        try:
            bookings = Booking.query.filter(
                Booking.provider_id == org_id,
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(Booking.created_at.desc()).limit(limit).all()
            return [b.to_dict() for b in bookings]
        except Exception as e:
            logger.error(f"Error getting org recent bookings: {e}", exc_info=True)
            return []

    # =========================================================
    # Private Helper Methods
    # =========================================================

    def get_cancellation_policy(self, booking: Booking) -> Dict[str, Any]:
        """Public preview of the scheduled cancellation policy."""
        return self._cancellation_policy(booking)

    def _cancellation_policy(self, booking: Booking,
                             now: Optional[datetime] = None) -> Dict[str, Any]:
        """Scheduled cancellation policy, computed server-side.

        Scheduled mode is the metadata gate from PICKUP-TIME-AUTHORITY-P1.
        Instant and mode-less bookings are deliberately free (fail-safe).
        Boundary rules use timedeltas so exact 1h / 15m cannot drift.
        """
        current = _as_utc(now) or datetime.now(timezone.utc)
        currency = _booking_currency_code(booking)
        scheduled = _booking_mode(booking) == SCHEDULED_BOOKING_MODE

        if not scheduled:
            return {
                "scheduled": False,
                "fee": Decimal("0.00"),
                "currency": currency,
                "tier": "not_scheduled",
                "percentage": 0,
                "cap": Decimal("0.00"),
                "pickup_time": None,
            }

        pickup = _as_utc(booking.pickup_time)
        if pickup is None:
            return {
                "scheduled": True,
                "fee": Decimal("0.00"),
                "currency": currency,
                "tier": "unreleased_pickup",
                "percentage": 0,
                "cap": Decimal("0.00"),
                "pickup_time": None,
            }

        fare = max(Decimal("0.00"), _money(booking.final_price))
        delta = pickup - current

        if delta > timedelta(hours=1):
            return {
                "scheduled": True,
                "fee": Decimal("0.00"),
                "currency": currency,
                "tier": "more_than_1h",
                "percentage": 0,
                "cap": Decimal("0.00"),
                "pickup_time": pickup,
            }

        if delta >= timedelta(minutes=15):
            percentage = 20
            cap = CANCEL_FEE_STANDARD_CAP
        else:
            percentage = 40
            cap = CANCEL_FEE_LATE_CAP

        fee = min(
            (fare * Decimal(percentage) / Decimal("100")).quantize(
                Decimal("0.01")
            ),
            cap,
            fare,
        )
        return {
            "scheduled": True,
            "fee": _money(fee),
            "currency": currency,
            "tier": "15m_to_1h" if percentage == 20 else "under_15m",
            "percentage": percentage,
            "cap": cap,
            "pickup_time": pickup,
        }

    def _calculate_cancellation_fee(self, booking: Booking,
                                    now: Optional[datetime] = None) -> Decimal:
        """Scheduled-only cancellation fee.

        > 1h              → 0
        15m through 1h    → 20%, cap 10,000
        < 15m or past     → 40%, cap 20,000
        Instant/mode-less → 0 (fail-safe)
        """
        return self._cancellation_policy(booking, now=now)["fee"]

    def _calculate_no_show_fee(self, booking: Booking) -> Decimal:
        """40% of fare, capped at 20,000 and never above the fare."""
        fare = max(Decimal("0.00"), _money(booking.final_price))
        return _money(min(
            (fare * NO_SHOW_FEE_RATE).quantize(Decimal("0.01")),
            NO_SHOW_FEE_CAP,
            fare,
        ))

    def _append_driver_credit(self, metadata: Dict[str, Any], *,
                              booking: Booking, driver: DriverProfile,
                              amount: Decimal, currency: str,
                              reason: str,
                              now: datetime) -> Dict[str, Any]:
        """Append a non-wallet driver credit fact to booking metadata."""
        credit = _money(amount)
        if credit <= 0:
            return metadata
        driver_user = getattr(driver, "user", None)
        user_public_id = getattr(driver_user, "public_id", None)
        credits = list(metadata.get("driver_cancellation_credits") or [])
        credits.append({
            "driver_code": driver.driver_code,
            "driver_user_public_id": (
                str(user_public_id) if user_public_id is not None else None
            ),
            "amount": str(credit),
            "currency": currency,
            "reason": reason,
            "recorded_uncollected": True,
            "booking_reference": booking.booking_reference,
            "at": now.isoformat(),
        })
        metadata["driver_cancellation_credits"] = credits
        return metadata

    def _generate_booking_code(self) -> str:
        letters = ''.join(random.choices(string.ascii_uppercase, k=3))
        numbers = ''.join(random.choices(string.digits, k=3))
        return f"AFC{letters}{numbers}"

    def _invalidate_booking_caches(self, booking_id: int):
        cache.delete(f"{self.cache_prefix}:{booking_id}")
        self._invalidate_listing_caches()

    def _invalidate_listing_caches(self):
        try:
            client = getattr(cache.cache, "_client", None)
            if client is not None and callable(getattr(client, "scan_iter", None)):
                for key in client.scan_iter(f"{self.cache_prefix}:list:*"):
                    cache.delete(key)
                return
        except Exception:
            pass
        cache.delete(f"{self.cache_prefix}:list:recent")
        cache.delete(f"{self.cache_prefix}:list:all")


# =========================================================
# Demand signal for GEO aggregation (roadmap GEO-17)
# =========================================================

# Demand counts submitted requests EXCEPT drafts (never submitted) and
# cancellations (withdrawn). no_show/disputed stay: a request
# demonstrably existed. Transport-owned rule: GEO aggregates the
# points but never decides which bookings count.
DEMAND_EXCLUDED_STATUSES = (BookingStatusPy.DRAFT, BookingStatusPy.CANCELLED)


def booking_request_points(since, until):
    """Read-only authoritative demand points for GEO aggregation.

    Returns (points, skipped_invalid) where points are
    (latitude, longitude, None) tuples from booking pickup locations
    created in [since, until]. Only canonical latitude/longitude
    floats count; anything else is skipped and counted (never raise,
    never fabricate). No identifiers are returned.

    Raises ValueError on missing/invalid window.
    """
    from datetime import timezone as _tz

    if since is None or until is None:
        raise ValueError("since and until are required (ISO-8601)")
    try:
        start = (since if isinstance(since, datetime)
                 else datetime.fromisoformat(str(since).strip()))
        end = (until if isinstance(until, datetime)
               else datetime.fromisoformat(str(until).strip()))
    except (ValueError, AttributeError):
        raise ValueError("since/until must be ISO-8601 datetimes") from None
    if start.tzinfo is None:
        start = start.replace(tzinfo=_tz.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=_tz.utc)
    if start > end:
        raise ValueError("since must not be after until")

    stmt = (
        sa.select(
            Booking.pickup_location.op("->")("latitude"),
            Booking.pickup_location.op("->")("longitude"),
        )
        .where(
            Booking.is_deleted.is_(False),
            ~Booking.status.in_(DEMAND_EXCLUDED_STATUSES),
            Booking.created_at >= start,
            Booking.created_at <= end,
        )
        .execution_options(yield_per=1000)
    )
    result = db.session.execute(stmt)
    points: List[Any] = []
    skipped = 0
    # Row values are native JSON scalars (-> preserves type: numbers,
    # strings, booleans, nulls), so the float()/range/skip logic below
    # is exactly the legacy Python semantics.
    for lat_val, lng_val in result:
        try:
            lat = float(lat_val)
            lng = float(lng_val)
        except (TypeError, ValueError):
            skipped += 1
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            skipped += 1
            continue
        points.append((lat, lng, None))
    return points, skipped


# =========================================================
# Singleton getter
# =========================================================
from threading import Lock

_booking_service_instance = None
_booking_service_lock = Lock()


def get_booking_service() -> BookingService:
    """Get singleton instance of BookingService"""
    global _booking_service_instance
    if _booking_service_instance is None:
        with _booking_service_lock:
            if _booking_service_instance is None:
                _booking_service_instance = BookingService()
                logger.debug("BookingService singleton created")
    return _booking_service_instance

