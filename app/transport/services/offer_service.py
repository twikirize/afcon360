# app/transport/services/offer_service.py
"""
AFCON360 Transport - Transient Offer Service (TH-3-D2).

Redis-backed, short-TTL offer surface used to *advertise* a proposed
(driver, vehicle) match to a driver. Offers are purely transient and are
NEVER authoritative: ownership is decided exclusively by the canonical
``AssignmentService.claim``. All operations here must degrade safely when
Redis is unavailable -- a lost/expired offer must never corrupt, stall, or
bypass assignment state.

Keys:
  transport:offer:{booking_ref}                 -> HASH (offer metadata + status)
  transport:driver:{driver_id}:offers           -> SET  (booking refs offered to the driver)
  transport:offer:index:booking:{booking_ref}   -> SET  (driver ids offered on the booking)

Offer status values: ``offered`` -> ``accepted`` (via atomic Lua CAS only).
"""
import logging
import time
from typing import Any, Dict, List, Optional

from flask import current_app

from app.extensions import redis_client
from app.transport.services.assignment_service import DispatchClaimError

logger = logging.getLogger(__name__)

OFFER_STATUS_OFFERED = "offered"
OFFER_STATUS_ACCEPTED = "accepted"

_DEFAULT_TTL_SECONDS = 300

# Lua is atomic: a single offer can be accepted exactly once and only by
# its intended driver. KEYS[1]=offer hash, KEYS[2]=driver set,
# KEYS[3]=booking index; ARGV[1]=driver_id, ARGV[2]=expected status,
# ARGV[3]=target status, ARGV[4]=booking_ref.
_ACCEPT_SCRIPT = """
local state = redis.call('HGET', KEYS[1], 'status')
if state ~= ARGV[2] then
    return 0
end
local owner = redis.call('HGET', KEYS[1], 'driver_id')
if owner ~= ARGV[1] then
    return 0
end
redis.call('HSET', KEYS[1], 'status', ARGV[3])
redis.call('SREM', KEYS[2], ARGV[4])
redis.call('SREM', KEYS[3], ARGV[1])
return 1
"""

# Lua: withdraw an offer that still belongs to the given driver (decline).
_DECLINE_SCRIPT = """
local owner = redis.call('HGET', KEYS[1], 'driver_id')
if owner ~= ARGV[1] then
    return 0
end
local state = redis.call('HGET', KEYS[1], 'status')
redis.call('SREM', KEYS[2], ARGV[2])
redis.call('SREM', KEYS[3], ARGV[1])
redis.call('DEL', KEYS[1])
return 1
"""


class OfferUnavailableError(Exception):
    """The offer store (Redis) is unavailable or the operation failed."""


def _to_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if value is None:
        return ""
    return str(value)


def _enum_value(value: Any) -> Optional[str]:
    """Unwrap a SQLAlchemy Enum member to its plain string value."""
    if value is None:
        return None
    return getattr(value, "value", value)


def format_endpoint_display(
    address: Optional[str], location: Any
) -> Dict[str, Any]:
    """Canonical safe display for one trip endpoint (pickup OR dropoff).

    Authority chain (no invention, no PII):
      1. explicit address text (``pickup_address`` / ``dropoff_address``);
      2. ``pickup_location`` / ``dropoff_location`` JSONB text keys
         (``address`` -> ``name`` -> ``label``) — same chain as
         ``Booking.pickup_location_text`` and the rider ``loc_text`` macro;
      3. canonical coordinates ``"lat, lng"`` when the JSONB carries
         valid numbers (truthful, map-usable, never fabricated);
      4. None when nothing authoritative exists (callers render an
         honest "to be confirmed" line — never a literal
         "Pickup"/"Dropoff" masquerading as data).
    """
    text: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    if isinstance(address, str) and address.strip():
        text = address.strip()
    if text is None and isinstance(location, dict):
        for key in ("address", "name", "label"):
            candidate = location.get(key)
            if isinstance(candidate, str) and candidate.strip():
                text = candidate.strip()
                break
        try:
            raw_lat = location.get("latitude")
            raw_lng = location.get("longitude")
            latitude = float(raw_lat) if raw_lat is not None else None
            longitude = float(raw_lng) if raw_lng is not None else None
        except (TypeError, ValueError):
            latitude, longitude = None, None
        if not (
            isinstance(latitude, float)
            and isinstance(longitude, float)
            and -90.0 <= latitude <= 90.0
            and -180.0 <= longitude <= 180.0
        ):
            latitude, longitude = None, None
    elif text is None and isinstance(location, str) and location.strip():
        text = location.strip()
    if text is None and latitude is not None and longitude is not None:
        text = f"{latitude:.4f}, {longitude:.4f}"
    return {"text": text, "latitude": latitude, "longitude": longitude}


class OfferService:
    """Transient offer store. Never authoritative for assignment state."""

    PREFIX_OFFER = "transport:offer"
    PREFIX_DRIVER = "transport:driver"
    PREFIX_INDEX = "transport:offer:index"
    DEFAULT_TTL_SECONDS = _DEFAULT_TTL_SECONDS

    # ------------------------------------------------------------------ #
    # Keys
    # ------------------------------------------------------------------ #
    @classmethod
    def _offer_key(cls, booking_ref: str) -> str:
        return f"{cls.PREFIX_OFFER}:{booking_ref}"

    @classmethod
    def _driver_key(cls, driver_id: int) -> str:
        return f"{cls.PREFIX_DRIVER}:{driver_id}:offers"

    @classmethod
    def _index_key(cls, booking_ref: str) -> str:
        return f"{cls.PREFIX_INDEX}:booking:{booking_ref}"

    @classmethod
    def _ttl(cls) -> int:
        return int(
            current_app.config.get("TRANSPORT_OFFER_TTL_SECONDS", cls.DEFAULT_TTL_SECONDS)
        )

    # ------------------------------------------------------------------ #
    # Create
    # ------------------------------------------------------------------ #
    @classmethod
    def create_offer(
        cls,
        booking_ref: str,
        driver_id: int,
        vehicle_id: int,
        *,
        ttl: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Advertise a proposed (driver, vehicle) match for a booking.

        Raises ``OfferUnavailableError`` when Redis is unavailable; the
        caller must treat this as a soft failure and leave the booking
        CONFIRMED/unassigned for rediscovery.
        """
        ttl = ttl or cls._ttl()
        expires_at = int(time.time()) + ttl
        key = cls._offer_key(booking_ref)
        dkey = cls._driver_key(driver_id)
        ikey = cls._index_key(booking_ref)
        try:
            redis_client.hset(
                key,
                mapping={
                    "booking_reference": booking_ref,
                    "driver_id": _to_str(driver_id),
                    "vehicle_id": _to_str(vehicle_id),
                    "status": OFFER_STATUS_OFFERED,
                    "expires_at": _to_str(expires_at),
                },
            )
            redis_client.expire(key, ttl)
            redis_client.sadd(dkey, booking_ref)
            redis_client.sadd(ikey, _to_str(driver_id))
        except Exception as exc:
            logger.warning("offer create failed (Redis) for %s: %s", booking_ref, exc)
            raise OfferUnavailableError(f"offer store unavailable: {exc}") from exc

        offer = {
            "booking_reference": booking_ref,
            "driver_id": driver_id,
            "vehicle_id": vehicle_id,
            "status": OFFER_STATUS_OFFERED,
            "expires_at": expires_at,
            "ttl": ttl,
        }
        logger.info("Offer created for booking %s -> driver %s (ttl=%ss)",
                    booking_ref, driver_id, ttl)
        return offer

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    @classmethod
    def get_offer(
        cls, booking_ref: str, driver_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Read the current offer for a booking (optionally filtered to a
        driver). Returns None when missing/expired/Redis unavailable."""
        try:
            data = redis_client.hgetall(cls._offer_key(booking_ref))
        except Exception:
            return None
        if not data:
            return None
        offer: Dict[str, Any] = {_to_str(k): _to_str(v) for k, v in data.items()}
        if driver_id is not None and offer.get("driver_id") != _to_str(driver_id):
            return None
        offer["driver_id"] = int(offer.get("driver_id") or 0) or None
        offer["vehicle_id"] = int(offer.get("vehicle_id") or 0) or None
        try:
            offer["expires_at"] = int(offer.get("expires_at") or 0)
        except (TypeError, ValueError):
            offer["expires_at"] = 0
        return offer

    @classmethod
    def list_driver_offers(cls, driver_id: int) -> List[Dict[str, Any]]:
        """All live (status=offered) offers for a driver.

        Presentation enrichment (DRIVER-OFFER-UX-REPAIR-1): each offer
        is enriched at READ time from the authoritative ``Booking`` row
        (plus the driver's own proposed ``Vehicle``). Redis stays thin
        — lifecycle/state only — so enriched fields can never go stale
        in the transient store. Enrichment never raises: a missing or
        unreadable booking degrades to the thin lifecycle dict.
        """
        try:
            refs = redis_client.smembers(cls._driver_key(driver_id))
        except Exception:
            return []
        offers: List[Dict[str, Any]] = []
        for ref in refs or []:
            offer = cls.get_offer(_to_str(ref), driver_id=driver_id)
            if offer and offer.get("status") == OFFER_STATUS_OFFERED:
                offers.append(cls.enrich_offer(offer))
        return offers

    @classmethod
    def get_offer_detail(
        cls, booking_ref: str, driver_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Single live offer with the driver-visible enrichment applied."""
        offer = cls.get_offer(booking_ref, driver_id=driver_id)
        if not offer:
            return None
        return cls.enrich_offer(offer)

    @classmethod
    def enrich_offer(cls, offer: Dict[str, Any]) -> Dict[str, Any]:
        """Attach the approved driver-visible contract to a thin offer.

        Explicit shaped contract (no ORM serialization, no user/org
        internals, no passenger PII, no extra booking columns, and —
        per the operating-system identity rule — no internal database
        IDs: the booking reference is the public identifier, so the
        thin ``driver_id`` / ``vehicle_id`` lifecycle keys are stripped
        here and never reach the browser):

          booking_reference, status,
          expires_at, ttl_remaining,
          pickup {text, latitude, longitude},
          destination {text, latitude, longitude},
          fare_estimate {amount (base_price estimate, NEVER the final
            fare, NEVER driver earnings), currency} | None,
          ride_class | None, service_type | None,
          passenger_count (int),
          distance_km + distance_basis (only when the stored basis is
            the measured straight-line planner value; the planning
            default is withheld, never mislabelled),
          vehicle {license_plate, make, model, vehicle_class} | None,
            and only when a valid driver↔vehicle relationship is
            proven at read time (see _offer_vehicle_or_none).

        ETA is deliberately absent: ``estimated_duration_minutes`` is
        raw caller input, not an authoritative ETA. Passenger identity
        is deliberately absent: no driver surface (pre- or
        post-accept) exposes it today, so the offer must not invent
        that disclosure.

        Failure handling (1C-6), each class distinct:
          * missing Booking row (stale index) → thin offer + info log;
          * booking lookup failure → thin offer + warning log;
          * unexpected mapping error → thin offer + exception log
            (traceback preserved for operators).
        The dashboard/API therefore survive any enrichment failure,
        and no failure mode is silent.
        """
        ref = offer.get("booking_reference")
        enriched: Dict[str, Any] = {
            "booking_reference": ref,
            "status": offer.get("status"),
            "expires_at": offer.get("expires_at"),
        }
        try:
            now = int(time.time())
            expires_at = int(offer.get("expires_at") or 0)
        except (TypeError, ValueError):
            now, expires_at = 0, 0
        enriched["ttl_remaining"] = max(0, expires_at - now) if expires_at else 0

        try:
            from app.transport.models import Booking

            booking = (
                Booking.query.filter(
                    Booking.booking_reference == ref,
                    Booking.is_deleted == False,  # noqa: E712
                ).first()
                if ref
                else None
            )
        except Exception as exc:
            logger.warning(
                "offer enrichment booking lookup failed for %s: %s",
                ref,
                exc,
            )
            return enriched
        if booking is None:
            logger.info(
                "offer enrichment: no booking row for %s (stale index); "
                "serving thin offer",
                ref,
            )
            return enriched

        detail: Dict[str, Any] = {}
        try:
            detail["pickup"] = format_endpoint_display(
                getattr(booking, "pickup_address", None),
                getattr(booking, "pickup_location", None),
            )
            detail["destination"] = format_endpoint_display(
                getattr(booking, "dropoff_address", None),
                getattr(booking, "dropoff_location", None),
            )

            base_price = getattr(booking, "base_price", None)
            detail["fare_estimate"] = {
                "amount": float(base_price) if base_price is not None else None,
                "currency": _enum_value(getattr(booking, "currency", None))
                or "USD",
            }

            metadata = getattr(booking, "booking_metadata", None) or {}
            ride_class = getattr(booking, "service_subtype", None) or (
                metadata.get("vehicle_class") if isinstance(metadata, dict) else None
            )
            detail["ride_class"] = ride_class
            detail["service_type"] = _enum_value(
                getattr(booking, "service_type", None)
            )
            try:
                detail["passenger_count"] = int(
                    getattr(booking, "passenger_count", 1) or 1
                )
            except (TypeError, ValueError):
                detail["passenger_count"] = 1

            distance = getattr(booking, "estimated_distance_km", None)
            basis = (
                metadata.get("distance_basis")
                if isinstance(metadata, dict)
                else None
            )
            if basis == "straight_line_planner" and distance is not None:
                try:
                    detail["distance_km"] = float(distance)
                    detail["distance_basis"] = basis
                except (TypeError, ValueError):
                    detail["distance_km"] = None
                    detail["distance_basis"] = None
            else:
                detail["distance_km"] = None
                detail["distance_basis"] = basis

            detail["vehicle"] = cls._offer_vehicle_or_none(
                offer, booking, ref
            )
        except Exception:
            logger.exception(
                "offer enrichment mapping failed for %s; serving thin offer",
                ref,
            )
            return enriched
        enriched.update(detail)
        return enriched

    @classmethod
    def _offer_vehicle_or_none(
        cls, offer: Dict[str, Any], booking: Any, ref: Any
    ) -> Optional[Dict[str, Any]]:
        """Proposed vehicle details, only with a proven association.

        The offer carries the candidate ``vehicle_id`` chosen at
        dispatch time. At read time the requesting driver must still be
        associated with that vehicle, proven by EITHER:
          * an active ``DriverVehicleHistory`` row
            (driver_id + vehicle_id + ``ended_at`` NULL) — the same
            relation behind ``DriverProfile.current_vehicle``; or
          * direct ownership (``Vehicle.owner_type == 'driver'`` and
            ``owner_id`` == requesting profile id) — covers
            owned-but-not-yet-driven vehicles.
        Anything else (cross-driver id, reassigned vehicle, deleted
        row) yields None: another driver's or a stale vehicle's details
        must never render on this driver's card. Read-only; no
        ownership mutation, no history redesign.
        """
        from app.transport.models import DriverVehicleHistory, Vehicle

        try:
            driver_key = offer.get("driver_id")
            driver_id = int(driver_key) if driver_key is not None else None
            candidate = offer.get("vehicle_id") or getattr(
                booking, "assigned_vehicle_id", None
            )
            vehicle_id = int(candidate) if candidate is not None else None
        except (TypeError, ValueError):
            return None
        if not driver_id or not vehicle_id:
            return None
        try:
            associated = (
                DriverVehicleHistory.query.filter(
                    DriverVehicleHistory.driver_id == driver_id,
                    DriverVehicleHistory.vehicle_id == vehicle_id,
                    DriverVehicleHistory.ended_at == None,  # noqa: E711,E712
                    DriverVehicleHistory.is_deleted == False,  # noqa: E712
                ).first()
            )
            vehicle = Vehicle.query.filter(
                Vehicle.id == vehicle_id,
                Vehicle.is_deleted == False,  # noqa: E712
            ).first()
        except Exception as exc:
            logger.warning(
                "offer vehicle lookup failed for %s: %s",
                ref,
                exc,
            )
            return None
        if vehicle is None:
            return None
        owned = (
            getattr(vehicle, "owner_type", None) == "driver"
            and getattr(vehicle, "owner_id", None) == driver_id
        )
        if associated is None and not owned:
            logger.info(
                "offer vehicle %s not associated with driver %s for %s; "
                "withholding vehicle details",
                vehicle_id,
                driver_id,
                ref,
            )
            return None
        return {
            "license_plate": vehicle.license_plate,
            "make": vehicle.make,
            "model": vehicle.model,
            "vehicle_class": _enum_value(
                getattr(vehicle, "vehicle_class", None)
            ),
        }

    @classmethod
    def count_driver_offers(cls, driver_id: int) -> int:
        try:
            return int(redis_client.scard(cls._driver_key(driver_id)) or 0)
        except Exception:
            return 0

    # ------------------------------------------------------------------ #
    # Accept (atomic Lua CAS) and decline
    # ------------------------------------------------------------------ #
    @classmethod
    def accept_offer(cls, booking_ref: str, driver_id: int) -> Dict[str, Any]:
        """Atomically accept an offer. On success, the caller MUST then run
        ``AssignmentService.claim`` -- the offer is only a pace gate.

        Raises ``DispatchClaimError`` with kind ``offer_expired`` /
        ``offer_conflict`` when the offer is gone or already accepted, and
        ``OfferUnavailableError`` when Redis fails.
        """
        key = cls._offer_key(booking_ref)
        dkey = cls._driver_key(driver_id)
        ikey = cls._index_key(booking_ref)
        try:
            accepted = redis_client.eval(
                _ACCEPT_SCRIPT,
                3,
                key,
                dkey,
                ikey,
                _to_str(driver_id),
                OFFER_STATUS_OFFERED,
                OFFER_STATUS_ACCEPTED,
                booking_ref,
            )
        except OfferUnavailableError:
            raise
        except Exception as exc:
            raise OfferUnavailableError(f"offer store unavailable: {exc}") from exc

        if accepted is not None and int(accepted) == 1:
            return {
                "booking_reference": booking_ref,
                "driver_id": driver_id,
                "accepted": True,
            }

        status = None
        try:
            raw_status = redis_client.hget(key, "status")
            status = _to_str(raw_status) if raw_status else None
        except Exception:
            status = None

        if status is None:
            raise DispatchClaimError(
                "offer_expired",
                "offer has expired or no longer exists",
                booking_ref=booking_ref,
            )
        raise DispatchClaimError(
            "offer_conflict",
            "offer is not in an acceptable state (already accepted or withdrawn)",
            booking_ref=booking_ref,
        )

    @classmethod
    def decline_offer(cls, booking_ref: str, driver_id: int) -> bool:
        """Withdraw an offer. Non-authoritative; safe in any state."""
        key = cls._offer_key(booking_ref)
        dkey = cls._driver_key(driver_id)
        ikey = cls._index_key(booking_ref)
        try:
            result = redis_client.eval(
                _DECLINE_SCRIPT,
                3,
                key,
                dkey,
                ikey,
                _to_str(driver_id),
                booking_ref,
            )
        except Exception as exc:
            logger.warning("offer decline failed (Redis) for %s: %s", booking_ref, exc)
            return False
        return result is not None and int(result) == 1

    @classmethod
    def cleanup_offer(cls, booking_ref: str, driver_id: Optional[int] = None) -> None:
        """Best-effort removal of an offer from all transient structures.
        Used after a failed claim or on cancellation/release."""
        try:
            key = cls._offer_key(booking_ref)
            data = redis_client.hgetall(key)
            owner_driver = (
                _to_str(data.get("driver_id")) if data and data.get("driver_id") else None
            )
            actual_driver = (
                _to_str(driver_id) if driver_id is not None else owner_driver
            )
            redis_client.srem(cls._index_key(booking_ref), actual_driver)
            if actual_driver:
                redis_client.srem(cls._driver_key(int(actual_driver)), booking_ref)
            redis_client.delete(key)
        except Exception as exc:
            logger.warning("offer cleanup failed (Redis) for %s: %s", booking_ref, exc)

    # ------------------------------------------------------------------ #
    # Expiry sweep (defensive; Redis TTL is the primary expiry mechanism)
    # ------------------------------------------------------------------ #
    @classmethod
    def sweep_expired(cls) -> int:
        """Best-effort scan that prunes stale drivers from booking offer
        indices. Returns the number of indices inspected. Exists for cron
        hygiene; a Redis TTL already expires the offer hash itself."""
        cleared = 0
        try:
            refs = redis_client.keys(f"{cls.PREFIX_INDEX}:*")
            for ref_key in refs or []:
                booking_ref = _to_str(ref_key).replace(f"{cls.PREFIX_INDEX}:booking:", "")
                if not booking_ref:
                    continue
                if cls.get_offer(booking_ref) is None:
                    redis_client.delete(ref_key)
                    cleared += 1
        except Exception as exc:
            logger.warning("offer sweep failed (Redis): %s", exc)
        return cleared


def get_offer_service():
    """Service-locator helper consistent with the transport module pattern."""
    return OfferService