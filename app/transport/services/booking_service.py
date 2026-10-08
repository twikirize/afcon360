"""AFCON360 Transport Module - Booking Service
Handles booking creation, management, and lifecycle
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
import random
import string
import json
import logging
import sqlalchemy as sa
from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.extensions import db, cache
from app.transport.models import (
    Booking,
    BookingStatus,
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
    BookingStatus.DRAFT:           [BookingStatus.PENDING_PAYMENT, BookingStatus.CANCELLED],
    BookingStatus.PENDING_PAYMENT: [BookingStatus.CONFIRMED, BookingStatus.CANCELLED],
    # MATCH-01-owned: CONFIRMED gains the NO_MATCH terminal edge (additive;
    # the pre-existing ASSIGNED and CANCELLED edges are unchanged).
    BookingStatus.CONFIRMED:       [BookingStatus.ASSIGNED, BookingStatus.NO_MATCH, BookingStatus.CANCELLED],
    BookingStatus.ASSIGNED:        [BookingStatus.DRIVER_EN_ROUTE, BookingStatus.CANCELLED],
    BookingStatus.DRIVER_EN_ROUTE: [BookingStatus.PICKUP_ARRIVED, BookingStatus.CANCELLED],
    BookingStatus.PICKUP_ARRIVED:  [BookingStatus.IN_PROGRESS, BookingStatus.NO_SHOW],
    BookingStatus.IN_PROGRESS:     [BookingStatus.COMPLETED, BookingStatus.DISPUTED],
    BookingStatus.COMPLETED:       [],
    BookingStatus.CANCELLED:       [],
    BookingStatus.NO_SHOW:         [],
    BookingStatus.DISPUTED:        [BookingStatus.COMPLETED, BookingStatus.CANCELLED],
    # MATCH-01-owned: terminal matching-failure state (additive).
    # The single outbound edge NO_MATCH -> CONFIRMED is the manual rider
    # "Try again" reopen (retry_matching only); nothing fires it automatically.
    BookingStatus.NO_MATCH:        [BookingStatus.CONFIRMED],
}


def _can_transition(current: BookingStatus, target: BookingStatus) -> bool:
    member = _status_member(current)
    if member is None:
        return False
    return target in STATUS_TRANSITIONS.get(member, [])


def _status_member(value: Any) -> Optional[BookingStatus]:
    """Normalize a stored status (plain str) or member to a member.

    Permanent-convention helper: storage is VARCHAR, so ORM attributes
    arrive as strings; the transition map stays member-keyed as the
    single source of truth. Unknown strings map to None (closed world).
    """
    if isinstance(value, BookingStatus):
        return value
    try:
        return BookingStatus(value)
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

            # Idempotency dedupe — before any fare calc or DB write
            key = (sanitized_data.get("idempotency_key") or "").strip() or None
            if key:
                existing = Booking.query.filter_by(
                    idempotency_key=key,
                    user_id=customer_id,
                    is_deleted=False,
                ).first()
                if existing:
                    existing.booking_metadata = existing.booking_metadata or {}
                    existing.booking_metadata["idempotent_replay"] = True
                    existing.booking_metadata["replayed_at"] = datetime.now(timezone.utc).isoformat()
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
            # Record the applied surge alongside the price (fare node):
            # the surge_multiplier column previously stayed at its 1.00
            # default even when rush pricing applied, making estimates
            # unexplainable. Same engine, same inputs — no price change.
            _applied_surge = _estimate["surge_multiplier"]

            try:
                raw = sanitized_data["pickup_time"]
                pickup_time = datetime.fromisoformat(str(raw))
                if pickup_time.tzinfo is None:
                    # Assume deployment-local TZ; Postgres TIMESTAMPTZ would
                    # otherwise coerce via the DB session TZ, which differs
                    # between dev and prod for the same naive input string.
                    local_tz = datetime.now().astimezone().tzinfo
                    pickup_time = pickup_time.replace(tzinfo=local_tz)
            except (ValueError, TypeError, KeyError):
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
                passenger_count=int(sanitized_data.get("passenger_count") or 1),
                luggage_count=int(sanitized_data.get("luggage_count") or 0),
                special_requirements=special_req,
                accessibility_requirements=sanitized_data.get("accessibility_requirements") or [],
                base_price=estimated_price,
                surge_multiplier=_applied_surge,
                estimated_distance_km=distance_for_fare,
                estimated_duration_minutes=sanitized_data.get("estimated_duration"),
                payment_method=sanitized_data.get("payment_method", "cash"),
                payment_status=PaymentStatus.PENDING,
                status=BookingStatus.PENDING_PAYMENT,
                currency=Currency(sanitized_data.get("currency") or "USD"),
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
                }
            }

        except ValidationError as e:
            db.session.rollback()
            record_metric("booking_creation", tags={"status": "failed", "error_type": "validation"}, value=1)
            raise

        except IntegrityError:
            # Concurrent same-key race: two threads passed the dedupe check,
            # one INSERT won, this one hit the partial unique index. The
            # winner's booking exists — return it as a replay.
            db.session.rollback()
            if key:
                winner = Booking.query.filter_by(
                    idempotency_key=key,
                    user_id=customer_id,
                    is_deleted=False,
                ).first()
                if winner is not None:
                    winner.booking_metadata = winner.booking_metadata or {}
                    winner.booking_metadata["idempotent_replay"] = True
                    winner.booking_metadata["replayed_at"] = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    db.session.commit()
                    return {
                        "success": True,
                        "message": "Booking already exists (concurrent replay)",
                        "data": {
                            "booking_id": winner.id,
                            "booking_reference": winner.booking_reference,
                            "idempotent_replay": True,
                        },
                    }
            logger.error("IntegrityError with no key — cannot recover", exc_info=True)
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
            BookingStatus.PENDING_PAYMENT.value,
            BookingStatus.CONFIRMED.value,
        }
        POST_ASSIGNMENT_CANCELLABLE_STATUSES = {
            BookingStatus.ASSIGNED.value,
            BookingStatus.DRIVER_EN_ROUTE.value,
            BookingStatus.PICKUP_ARRIVED.value,
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

            # Calculate fee (waived for safety cancellations)
            if is_safety_cancellation:
                cancellation_fee = Decimal("0.00")
            else:
                cancellation_fee = self._calculate_cancellation_fee(booking)
            refund_amount = float(booking.final_price - cancellation_fee)

            now = datetime.now(timezone.utc)

            if current_status in PRE_ASSIGNMENT_STATUSES:
                # Pre-assignment: simple status update (existing behavior)
                result = db.session.execute(
                    sa.update(Booking.__table__)
                    .where(
                        Booking.__table__.c.id == booking_id,
                        Booking.__table__.c.status.in_(list(PRE_ASSIGNMENT_STATUSES)),
                        Booking.__table__.c.is_deleted.is_(False),
                    )
                    .values(
                        status=BookingStatus.CANCELLED.value,
                        cancelled_at=now,
                        cancellation_reason=reason,
                        cancellation_reason_category=reason_category,
                        cancellation_safety_flag=safety_flag,
                        cancelled_stage=current_status,
                        cancellation_fee=cancellation_fee,
                    )
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    db.session.rollback()
                    raise ValidationError(
                        "Cannot cancel booking: it is no longer in a cancellable state"
                    )
                release_result = None
            else:
                # Post-assignment: use canonical release through AssignmentService
                # This atomically: sets status=CANCELLED, clears assigned_driver_id/vehicle_id,
                # releases driver/vehicle availability, cleans up offers
                try:
                    release_result = AssignmentService.release(
                        booking_id,
                        BookingStatus.CANCELLED,
                        actor=None,
                        reason=reason,
                        audit_extra={
                            "from": current_status,
                            "reason_category": reason_category,
                            "safety_flag": safety_flag,
                            "cancelled_by": "rider",
                        },
                    )
                    # Update the booking with additional cancellation metadata
                    # (AssignmentService.release sets status, cancelled_at, assigned_driver_id=None, assigned_vehicle_id=None)
                    db.session.execute(
                        sa.update(Booking.__table__)
                        .where(
                            Booking.__table__.c.id == booking_id,
                            Booking.__table__.c.is_deleted.is_(False),
                        )
                        .values(
                            cancellation_reason=reason,
                            cancellation_reason_category=reason_category,
                            cancellation_safety_flag=safety_flag,
                            cancelled_stage=current_status,
                            cancellation_fee=cancellation_fee,
                            cancellation_initiated_by="rider",
                        )
                        .execution_options(synchronize_session=False)
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
                    "booking_id": booking_id,
                    "cancellation_fee": float(cancellation_fee),
                    "refund_amount": refund_amount,
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

    @staticmethod
    def transition_status(booking_id: int, new_status: "BookingStatus",
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

        if not isinstance(new_status, BookingStatus):
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
            if new_status == BookingStatus.COMPLETED:
                booking.completed_at = now
            elif new_status == BookingStatus.CANCELLED:
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
        if new_status == BookingStatus.CONFIRMED:
            booking.confirmed_at = now
            # MATCH-01-owned: (re)start the matching window cursor. Kept in
            # booking_metadata (transient matching cursor, not audit history)
            # so confirmed_at keeps its first-confirmation meaning for the
            # rider timeline and admin reports (review Condition 1, option
            # chosen: dedicated cursor, zero-column variant).
            _stamp_matching_window_start(booking, now)
        elif new_status == BookingStatus.COMPLETED:
            booking.completed_at = now
        elif new_status == BookingStatus.CANCELLED:
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
        if booking.status == BookingStatus.NO_MATCH:
            return {"booking": booking, "replayed": True,
                    "reason": booking.no_match_reason}
        if booking.status != BookingStatus.CONFIRMED:
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
                Booking.__table__.c.status == BookingStatus.CONFIRMED.value,
                Booking.__table__.c.assigned_driver_id.is_(None),
                Booking.__table__.c.assigned_vehicle_id.is_(None),
                Booking.__table__.c.is_deleted.is_(False),
            )
            .values(
                status=BookingStatus.NO_MATCH.value,
                no_match_reason=reason,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.session.rollback()
            refreshed = db.session.get(Booking, booking_id)
            if refreshed is not None and refreshed.status == BookingStatus.NO_MATCH:
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
            "to": BookingStatus.NO_MATCH.value,
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
        admins use the admin status endpoint). Resets the matching-window
        cursor (review Condition 1) and clears no_match_reason so the CHECK
        holds; then immediately re-runs discover_and_offer so the rider
        lands on a live matching screen. No auto-retry exists anywhere else.
        """
        booking = db.session.get(Booking, booking_id)
        if not booking or booking.is_deleted:
            raise NotFoundError("Booking not found",
                                resource_type="booking",
                                resource_id=booking_id)
        if booking.user_id != user_id:
            raise PermissionError("Cannot retry another user's ride")
        if booking.status != BookingStatus.NO_MATCH:
            raise ValidationError(
                message=f"Retry is only available from no_match "
                        f"(current: {booking.status})",
                field="status",
            )
        now = datetime.now(timezone.utc)
        result = db.session.execute(
            sa.update(Booking.__table__)
            .where(
                Booking.__table__.c.id == booking_id,
                Booking.__table__.c.status == BookingStatus.NO_MATCH.value,
                Booking.__table__.c.is_deleted.is_(False),
            )
            .values(
                status=BookingStatus.CONFIRMED.value,
                no_match_reason=None,
                confirmed_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.session.rollback()
            raise ValidationError("Retry failed: ride is no longer in no_match")
        db.session.commit()
        db.session.expire_all()
        refreshed = db.session.get(Booking, booking_id)
        # Fresh window cursor (Condition 1): confirmed_at is re-stamped above
        # as the user-observable "search restarted" time AND the metadata
        # cursor is reset — either alone suffices; both are set so the
        # confirmed_at fallback path can never see a stale window.
        _stamp_matching_window_start(refreshed, now)
        refreshed.audit_log = (refreshed.audit_log or []) + [{
            "action": "retry_matching",
            "from": BookingStatus.NO_MATCH.value,
            "to": BookingStatus.CONFIRMED.value,
            "at": now.isoformat(),
            "reason": "rider_retry",
            "initiated_by": "rider",
        }]
        try:
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error auditing retry for {booking_id}: {e}",
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
        return {"booking": refreshed, "replayed": False,
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
            # If status is something like 'pending', we need to map to BookingStatus.PENDING
            # Using getattr to safely get enum member
            status_enum = getattr(BookingStatus, status_upper, None)
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

            excluded: List[BookingStatus] = []
            if not include_cancelled:
                excluded.append(BookingStatus.CANCELLED)
            if not include_draft:
                excluded.append(BookingStatus.DRAFT)
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
                Booking.status == BookingStatus.COMPLETED,
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
                    BookingStatus.CONFIRMED,
                    BookingStatus.ASSIGNED,
                    BookingStatus.IN_PROGRESS
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
            for status_enum in BookingStatus:
                count = Booking.query.filter(
                    Booking.created_at >= cutoff,
                    Booking.status == status_enum,
                    Booking.is_deleted == False
                ).count()
                by_status[status_enum.value] = count

            # Revenue metrics - using final_price for completed/confirmed
            revenue = db.session.query(func.sum(Booking.final_price)).filter(
                Booking.created_at >= cutoff,
                Booking.status.in_([BookingStatus.COMPLETED, BookingStatus.CONFIRMED]),
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
        """
        return {
            **booking.to_dict(),
            "pickup_location_text": booking.pickup_location_text,
            "dropoff_location_text": booking.dropoff_location_text,
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
            status_enum = getattr(BookingStatus, status.upper(), None)
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
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ASSIGNED, BookingStatus.DRIVER_EN_ROUTE]),
                Booking.pickup_time > now,
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(Booking.pickup_time.asc()).limit(limit).all()
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
                    Booking.status == BookingStatus.COMPLETED,
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
            bookings = Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
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
                Booking.status.in_([BookingStatus.ASSIGNED, BookingStatus.DRIVER_EN_ROUTE]),
                Booking.pickup_time > now,
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(Booking.pickup_time.asc()).first()
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
                Booking.status == BookingStatus.COMPLETED,
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

    def _calculate_cancellation_fee(self, booking: Booking) -> Decimal:
        """Cancellation fee tiers.

        DEV/TESTING: the immediate-cancel grace window is 0 minutes — any
        pickup_time at or before now is free to cancel. This is intentional
        while the platform is under test. Before production, restore the
        industry-standard 5-minute grace window (see BACKLOG.md BL-01).

        Tiers when pickup is in the future:
          > 24h  → 0
          > 4h   → 10%
          > 2h   → 25%
          <= 2h  → 50%
        """
        now = datetime.now(timezone.utc)
        pickup = booking.pickup_time
        if pickup is None:
            return Decimal("0.00")
        if pickup.tzinfo is None:
            pickup = pickup.replace(tzinfo=timezone.utc)

        hours_before = (pickup - now).total_seconds() / 3600.0
        final_price = booking.final_price or Decimal("0.00")

        if hours_before <= 0:
            return Decimal("0.00")
        if hours_before > 24:
            return Decimal("0.00")
        if hours_before > 4:
            return final_price * Decimal("0.10")
        if hours_before > 2:
            return final_price * Decimal("0.25")
        return final_price * Decimal("0.50")

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
DEMAND_EXCLUDED_STATUSES = (BookingStatus.DRAFT, BookingStatus.CANCELLED)


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

