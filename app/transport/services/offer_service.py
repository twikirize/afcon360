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
        """All live (status=offered) offers for a driver."""
        try:
            refs = redis_client.smembers(cls._driver_key(driver_id))
        except Exception:
            return []
        offers: List[Dict[str, Any]] = []
        for ref in refs or []:
            offer = cls.get_offer(_to_str(ref), driver_id=driver_id)
            if offer and offer.get("status") == OFFER_STATUS_OFFERED:
                offers.append(offer)
        return offers

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