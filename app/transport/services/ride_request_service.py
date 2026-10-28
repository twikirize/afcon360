"""BOOKING-LIFECYCLE-REQUEST-CREATE (Stage 3B, Phase 2A).

Pre-Booking request creation for rider on-demand hailing: validate,
build canonical location snapshots, price via the canonical fare engine,
and atomically persist one RideRequest plus its initial SearchCycle.

What this module NEVER does: create a Booking, generate or expose a
Booking reference, dispatch an offer, or assign a driver/vehicle.

Re-use, not duplication:
  * input shape validation — app.utils.validators.validate_booking_request
  * location truth — location_snapshot.build_canonical_location_snapshot
    (with SOURCE_METHOD_PAIRS + geo geocode evidence, same as BookingService)
  * fare truth — fare_service.calculate_estimate over the measured
    straight-line distance (booking_service._measured_distance_km)
  * matching window — MatchingService._matching_window_seconds
  * storage labels — app/utils/enums.py Python str-Enums (UPPERCASE
    names, lowercase values: ServiceType.ON_DEMAND.value == 'on_demand');
    rider surface and storage share the lowercase spelling.
  * fare denomination — the estimate's own currency (authoritative);
    the rider's requested code is preserved as a payment preference in
    metadata, never converted, never relabeled (Transport/Wallet
    boundary: conversion and execution belong to Wallet's later node).
No second fare path. No second location-validation path.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
# NOTE (Phase 2A, transitional): RideRequest/SearchCycle are imported
# lazily inside create_request — same deferred-import precedent as
# offer_service's deferred db import — so this module loads and verifies
# in isolation while the concurrent enum-centralization work lands.
# Identical at call time; no behavior difference once the tree is stable.
from app.utils.enums import Currency, ServiceType
from app.transport.services.location_snapshot import (
    SOURCE_METHOD_PAIRS,
    build_canonical_location_snapshot,
)
from app.transport.services.fare_quote_service import (
    load_fare_quote,
    money_amount,
    validate_fare_quote,
)
from app.utils.exceptions import ServiceUnavailableError, ValidationError
from app.utils.validators import validate_booking_request

logger = logging.getLogger(__name__)


class IdempotencyConflictError(ValidationError):
    """Same owner + key, materially different trip requirements.

    The original request is left untouched; the caller must use a fresh
    idempotency key for a different trip. Subclasses ValidationError so
    generic handlers keep working; the API layer maps it to 409.
    """


def _trip_hash(service_type: str, vehicle_class: str, passenger_count: int,
               pickup: Dict[str, Any], dropoff: Dict[str, Any],
               payment_method: Optional[str], currency_code: Optional[str],
               pickup_time_fp: str, requested_currency: Optional[str]) -> str:
    """Stable fingerprint of the trip requirements a key was first used for.

    Coordinates are rounded to 6dp so float-encoding noise does not split
    identical trips; snapshots themselves are stored verbatim.
    pickup_time_fp is "immediate" when the rider omitted pickup_time
    (immediate intent — stable across retries, never wall-clock),
    "naive-local:<wall-clock ISO>" for naive explicits (deterministic,
    never worker-local-converted), else the aware instant normalized
    to UTC ISO.
    requested_currency is the rider's preserved payment preference (None
    when absent); like pickup_time, an explicit difference conflicts.
    """
    def _coords(loc: Dict[str, Any]):
        return [round(float(loc["latitude"]), 6), round(float(loc["longitude"]), 6)]

    canonical = {
        "service_type": service_type,
        "vehicle_class": vehicle_class,
        "passenger_count": int(passenger_count),
        "pickup": _coords(pickup),
        "dropoff": _coords(dropoff),
        "payment_method": payment_method,
        "currency_code": currency_code,
        "pickup_time": pickup_time_fp,
        "requested_currency": requested_currency,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()


def _search_geocode_evidence(raw: Any, field: str):
    """Provider evidence for a 'search' source claim (same rule as BookingService).

    The only truthful backing is the provider result echoed back in
    <endpoint>_geocode. gps/map/absent markers carry no evidence.
    """
    from app.geo.services import geocode_result_from_candidate

    missing = "%s 'search' requires %s provider evidence" % (field, field.replace("_source", "_geocode"))
    candidate = None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValidationError(message=missing, field=field)
        try:
            candidate = json.loads(text)
        except ValueError as exc:
            raise ValidationError(message=missing, field=field) from exc
    elif isinstance(raw, dict):
        candidate = raw
    else:
        raise ValidationError(message=missing, field=field)
    if not isinstance(candidate, dict):
        raise ValidationError(message=missing, field=field)
    try:
        return geocode_result_from_candidate(candidate)
    except ValidationError as exc:
        raise ValidationError(message="%s (%s)" % (missing, exc.message),
                              field=field) from exc


def _resolve_snapshot(payload: Dict[str, Any], endpoint: str) -> Dict[str, Any]:
    """Canonical snapshot for one endpoint; canonical builder owns the verdict."""
    raw = payload.get(endpoint)
    if not isinstance(raw, dict):
        raise ValidationError(
            message="%s must be an object with latitude/longitude" % endpoint,
            field=endpoint,
        )
    lat, lng = raw.get("latitude"), raw.get("longitude")
    if lat is None or lng is None:
        raise ValidationError(
            message="%s must include both 'latitude' and 'longitude'" % endpoint,
            field=endpoint,
        )

    source = payload.get("%s_source" % endpoint)
    method = None
    if source is not None:
        if isinstance(source, str):
            source = source.strip()
        if source:
            method = SOURCE_METHOD_PAIRS.get(source)
            if method is None:
                raise ValidationError(
                    message="%s_source must be one of %s"
                            % (endpoint, sorted(SOURCE_METHOD_PAIRS)),
                    field="%s_source" % endpoint,
                )
        else:
            source = None

    geocode_result = (_search_geocode_evidence(payload.get("%s_geocode" % endpoint),
                                               "%s_source" % endpoint)
                      if source == "search" else None)

    location_payload = dict(raw)
    try:
        return build_canonical_location_snapshot(
            location_payload=location_payload,
            geocode_result=geocode_result,
            explicit_address=(raw.get("address")
                              if isinstance(raw.get("address"), str) else None),
            source=source,
            resolution_method=method,
        )
    except ValueError as exc:
        raise ValidationError(message=str(exc), field=endpoint) from exc


def serialize_request(ride_request: "RideRequest", cycle: "SearchCycle") -> Dict[str, Any]:
    """Rider-safe serialization: opaque public id only, never internal PKs."""
    meta = ride_request.request_metadata or {}
    fare = meta.get("fare_estimate") or {}
    return {
        "request_id": ride_request.public_id,
        "status": ride_request.status,
        "cycle": {
            "number": cycle.cycle_number,
            "status": cycle.status,
            "started_at": cycle.started_at.isoformat() if cycle.started_at else None,
            "deadline": cycle.deadline.isoformat() if cycle.deadline else None,
        },
        # Rider surface keeps the lowercase API spelling under any
        # storage representation (member or plain string).
        "service_type": str(getattr(ride_request.service_type, "value",
                                    ride_request.service_type) or "").lower(),
        "vehicle_class": ride_request.vehicle_class,
        "passenger_count": ride_request.passenger_count,
        "pickup_time": (ride_request.requested_pickup_time.isoformat()
                        if ride_request.requested_pickup_time else None),
        "fare_estimate": {
            "amount": fare.get("amount"),
            "currency": fare.get("currency"),
        },
        "payment_method": ride_request.payment_method,
        "created_at": (ride_request.created_at.isoformat()
                       if ride_request.created_at else None),
    }


class RideRequestService:
    """Creation authority for pre-Booking ride requests (Phase 2A)."""

    @staticmethod
    def create_request(owner_user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate, snapshot, price, and atomically persist request + cycle 1.

        Returns {"request": RideRequest, "cycle": SearchCycle, "replayed": bool}.
        Raises ValidationError (bad input), IdempotencyConflictError (key
        reused for a different trip), ServiceUnavailableError (storage failure).
        Creates zero Booking rows by construction — this module never
        imports the Booking writer path.
        """
        data = payload or {}
        request_received_at = datetime.now(timezone.utc)

        key = (data.get("idempotency_key") or "").strip() or None
        if not key:
            raise ValidationError(message="idempotency_key is required",
                                  field="idempotency_key")

        # Shared input validation (same authority as Booking creation).
        validation_view = {
            "pickup_location": data.get("pickup"),
            "dropoff_location": data.get("dropoff"),
            "pickup_time": (
                data.get("pickup_time")
                if str(data.get("booking_mode") or "instant").strip().lower() == "scheduled"
                else request_received_at.isoformat()
            ) or request_received_at.isoformat(),
            "service_type": data.get("service_type"),
            "passenger_count": data.get("passenger_count", 1),
            "vehicle_class": data.get("vehicle_class", "comfort"),
        }
        is_valid, errors = validate_booking_request(validation_view)
        if not is_valid:
            raise ValidationError(message="; ".join(errors) or "Invalid request")

        # Value authority is the centralized Python enum (lowercase
        # values); the shared validator above already owns the input
        # spelling.
        service_key = str(data.get("service_type") or "").lower()
        try:
            service_type = ServiceType(service_key)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValidationError(message="Invalid service_type",
                                  field="service_type") from exc

        vehicle_class = str(data.get("vehicle_class") or "comfort").lower()
        try:
            passenger_count = int(data.get("passenger_count") or 1)
        except (TypeError, ValueError) as exc:
            raise ValidationError(message="passenger_count must be a valid number",
                                  field="passenger_count") from exc

        pickup_snapshot = _resolve_snapshot(data, "pickup")
        dropoff_snapshot = _resolve_snapshot(data, "dropoff")

        # Canonical fare engine over the measured straight-line distance —
        # the same basis BookingService uses (no second fare path).
        from app.transport.services.booking_service import _measured_distance_km
        from app.transport.services.fare_service import calculate_estimate

        measured_km = _measured_distance_km(pickup_snapshot, dropoff_snapshot)
        if measured_km is None:
            raise ValidationError(
                message="Resolved coordinates required for fare calculation",
                field="pickup",
            )
        # Only a current, signed quote can cross the commitment boundary.
        # Reuse the quote's issue time so a change of hour/table version
        # during the review step cannot silently change the shown amount.
        fare_quote = load_fare_quote(data.get("fare_quote_token"))
        try:
            quoted_at = datetime.fromisoformat(str(fare_quote.get("quoted_at")))
            if quoted_at.tzinfo is not None:
                raise ValueError("quoted_at must be the signed local reference time")
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                message="Your fare quote is invalid. Please review the fare again.",
                field="fare_quote_token",
            ) from exc

        estimate = calculate_estimate(
            service_type=service_key,
            vehicle_class=vehicle_class,
            distance_km=measured_km,
            at=quoted_at,
        )

        # Denomination authority is the fare estimate itself: the stored
        # amount is estimate-denominated, so its code must be too. The
        # rider's requested code is a payment preference for later Wallet
        # integration — validated, preserved in metadata as requested,
        # never converted and never presented as the amount's denomination.
        # (Legacy Booking stores payload currency beside an estimate amount;
        # this service does not repeat that relabeling.)
        currency_code = str(estimate.get("currency") or "USD").upper()
        if currency_code not in {m.value for m in Currency}:
            raise ServiceUnavailableError("Fare service returned an unknown currency")
        requested_currency = (str(data.get("currency")).upper()
                              if data.get("currency") else None)
        if (requested_currency is not None
                and requested_currency not in {m.value for m in Currency}):
            raise ValidationError(message="Invalid currency code",
                                  field="currency")

        raw_payment_method = data.get("payment_method")
        payment_method = (
            str(raw_payment_method).strip().lower()
            if raw_payment_method is not None else ""
        )
        if not payment_method:
            raise ValidationError(
                message="Choose a payment method before requesting the ride",
                field="payment_method",
            )
        from app.transport.services.payment_methods import (
            get_available_transport_payment_methods,
        )
        offered = {
            str(m.get("code") or "").strip().lower()
            for m in get_available_transport_payment_methods(owner_user_id)
        }
        if payment_method not in offered:
            raise ValidationError(
                message="payment_method must be one of: %s" % sorted(offered),
                field="payment_method",
            )

        accepted_fare_amount = validate_fare_quote(
            fare_quote,
            service_type=service_key,
            vehicle_class=vehicle_class,
            currency=currency_code,
            pickup=pickup_snapshot,
            dropoff=dropoff_snapshot,
            distance_km=measured_km,
            fare_version=estimate.get("version"),
            server_amount=estimate["total"],
            confirmed_amount=data.get("confirmed_fare_amount"),
        )

        booking_mode = str(data.get("booking_mode") or "instant").strip().lower()
        if booking_mode not in ("instant", "scheduled"):
            raise ValidationError(
                message="booking_mode must be 'instant' or 'scheduled'",
                field="booking_mode",
            )

        # Instant requests use the server's request-received clock. Never let
        # a stale/future datetime left in a browser form turn an on-demand
        # ride into a scheduled trip or fail a future-time constraint.
        raw_time = data.get("pickup_time") if booking_mode == "scheduled" else None
        if booking_mode == "scheduled" and not raw_time:
            raise ValidationError(
                message="Scheduled pickups require an explicit pickup_time",
                field="pickup_time",
            )
        try:
            if booking_mode == "instant":
                requested_at = request_received_at
                raw_was_naive = False
            else:
                requested_at = datetime.fromisoformat(str(raw_time))
                # Match the legacy booking service contract: naive form values
                # are interpreted in the configured application zone.
                if requested_at.tzinfo is None:
                    raw_was_naive = True
                    app_tz_name = current_app.config.get("APP_TZ", "Africa/Nairobi")
                    requested_at = requested_at.replace(tzinfo=ZoneInfo(app_tz_name))
                else:
                    raw_was_naive = False
                minimum_lead = request_received_at + timedelta(minutes=15)
                if requested_at < minimum_lead:
                    raise ValidationError(
                        message=(
                            "Scheduled pickups must be at least 15 minutes from now. "
                            "For an immediate ride, choose 'Now'."
                        ),
                        field="pickup_time",
                    )
        except (ValueError, TypeError) as exc:
            raise ValidationError(
                message="pickup_time must be a valid datetime",
                field="pickup_time",
            ) from exc

        # Fingerprint the server clock for instant intent (so retries do not
        # conflict because transport latency changed the timestamp); scheduled
        # trips fingerprint their explicitly validated requested time.
        if booking_mode == "instant":
            pickup_time_fp = "immediate"
        elif raw_was_naive:
            pickup_time_fp = "naive-local:%s" % requested_at.replace(tzinfo=None).isoformat()
        else:
            pickup_time_fp = requested_at.astimezone(timezone.utc).isoformat()
        trip_hash = _trip_hash(service_type.value, vehicle_class,
                               passenger_count, pickup_snapshot,
                               dropoff_snapshot, payment_method, currency_code,
                               pickup_time_fp, requested_currency)

        # Deferred model import (see module note): resolves at call time.
        from app.transport.models import RideRequest, SearchCycle

        # Idempotent replay: same owner + key + equivalent trip wins as-is;
        # same key + different trip is a controlled conflict, no mutation.
        existing = RideRequest.query.filter_by(
            user_id=owner_user_id, idempotency_key=key, is_deleted=False).first()
        if existing is not None:
            stored_hash = (existing.request_metadata or {}).get("trip_hash")
            if stored_hash != trip_hash:
                raise IdempotencyConflictError(
                    message="idempotency_key was already used for a different trip",
                    field="idempotency_key",
                )
            first_cycle = SearchCycle.query.filter_by(
                ride_request_id=existing.id, cycle_number=1,
                is_deleted=False).first()
            return {"request": existing, "cycle": first_cycle, "replayed": True}

        from app.transport.services.matching_service import MatchingService

        now = datetime.now(timezone.utc)
        window = MatchingService._matching_window_seconds()
        try:
            ride_request = RideRequest(
                user_id=owner_user_id,
                idempotency_key=key,
                pickup_location=pickup_snapshot,
                dropoff_location=dropoff_snapshot,
                requested_pickup_time=requested_at,
                service_type=service_type,
                vehicle_class=vehicle_class,
                passenger_count=passenger_count,
                fare_estimate_amount=accepted_fare_amount,
                currency_code=currency_code,
                payment_method=payment_method,
                status="searching",
                request_metadata={
                    "trip_hash": trip_hash,
                    "fare_version": estimate.get("version"),
                    "fare_effective_from": estimate.get("effective_from"),
                    "fare_estimate": {
                        "amount": float(accepted_fare_amount),
                        "currency": estimate.get("currency"),
                    },
                    "requested_currency": requested_currency,
                    "distance_km": float(measured_km),
                    "distance_basis": "straight_line_planner",
                    "created_via": "ride_request_api",
                    "created_at": now.isoformat(),
                    "booking_mode": booking_mode,
                    "payment_timing": "pay_on_completion",
                },
            )
            db.session.add(ride_request)
            db.session.flush()
            cycle = SearchCycle(
                ride_request_id=ride_request.id,
                cycle_number=1,
                cycle_key="%s:1" % key,
                status="searching",
                started_at=now,
                deadline=now + timedelta(seconds=window),
            )
            db.session.add(cycle)
            db.session.flush()
            db.session.commit()
        except IntegrityError:
            # Concurrent same-key race: the winner's row exists — resolve
            # to it (replay) or report the conflict, never a duplicate.
            db.session.rollback()
            winner = RideRequest.query.filter_by(
                user_id=owner_user_id, idempotency_key=key,
                is_deleted=False).first()
            if winner is not None:
                if (winner.request_metadata or {}).get("trip_hash") != trip_hash:
                    raise IdempotencyConflictError(
                        message="idempotency_key was already used for a different trip",
                        field="idempotency_key",
                    )
                first_cycle = SearchCycle.query.filter_by(
                    ride_request_id=winner.id, cycle_number=1,
                    is_deleted=False).first()
                return {"request": winner, "cycle": first_cycle, "replayed": True}
            logger.error("IntegrityError with no winner row", exc_info=True)
            raise ServiceUnavailableError("Request service temporarily unavailable")
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Database error creating ride request: %s", exc, exc_info=True)
            raise ServiceUnavailableError("Request service temporarily unavailable")

        logger.info("RideRequest created: owner=%s public_id=%s",
                    owner_user_id, ride_request.public_id)
        return {"request": ride_request, "cycle": cycle, "replayed": False}


def get_ride_request_service():
    """Service-locator helper consistent with the transport module pattern."""
    return RideRequestService
