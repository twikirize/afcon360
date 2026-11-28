"""Short-lived signed road-distance fare quotes.

A quote is a server-priced offer bound to resolved pickup/dropoff coordinates,
the GEO routing provider's road distance and duration, fare version, class and
currency. A booking must consume these exact signed facts rather than routing
again or trusting client-supplied distance.
"""
import math
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.utils.exceptions import ValidationError

QUOTE_SALT = "transport-fare-quote-v2"
DEFAULT_QUOTE_MAX_AGE_SECONDS = 15 * 60
_CENT = Decimal("0.01")


def money_amount(value: Any) -> Decimal:
    """Normalize a fare to the two decimals shown and accepted by the rider."""
    try:
        amount = Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(
            message="Invalid fare amount. Please request a new fare quote.",
            field="confirmed_fare_amount",
        ) from exc
    if not amount.is_finite() or amount <= 0:
        raise ValidationError(
            message="Invalid fare amount. Please request a new fare quote.",
            field="confirmed_fare_amount",
        )
    return amount


def _finite_nonnegative(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and number >= 0


def _serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY is required to sign transport fare quotes")
    return URLSafeTimedSerializer(secret, salt=QUOTE_SALT)


def _coords(location: Dict[str, Any]):
    try:
        lat = round(float(location["latitude"]), 7)
        lng = round(float(location["longitude"]), 7)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValidationError(
            message="Resolved pickup and destination coordinates are required.",
            field="pickup",
        ) from exc
    if not (math.isfinite(lat) and math.isfinite(lng)
            and -90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValidationError(
            message="Resolved pickup and destination coordinates are required.",
            field="pickup",
        )
    return [lat, lng]


def road_measurements_from_quote(quote: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and extract the signed road facts from a verified quote."""
    distance_km = quote.get("distance_km")
    duration_s = quote.get("route_duration_s")
    provider = quote.get("route_provider")
    if (quote.get("distance_basis") != "road_network"
            or not _finite_nonnegative(distance_km)
            or not _finite_nonnegative(duration_s)
            or not isinstance(provider, str)
            or not provider.strip()
            or provider.strip().lower() == "unresolved"):
        raise ValidationError(
            message="Your road-route fare quote is invalid. Please review the fare again.",
            field="fare_quote_token",
        )
    return {
        "distance_km": round(float(distance_km), 6),
        "route_duration_s": round(float(duration_s), 3),
        "route_provider": provider.strip()[:64],
    }


def issue_fare_quote(
    *,
    service_type: str,
    vehicle_class: str,
    currency: str,
    amount: Any,
    fare_version: Any,
    pickup: Dict[str, Any],
    dropoff: Dict[str, Any],
    distance_km: Any,
    route_duration_s: Any,
    route_provider: str,
    quoted_at: datetime,
) -> str:
    """Sign a fare offer and its authoritative GEO road measurements."""
    if not _finite_nonnegative(distance_km) or not _finite_nonnegative(route_duration_s):
        raise ValidationError(
            message="A resolved road route is required before quoting a fare.",
            field="pickup",
        )
    if (not isinstance(route_provider, str) or not route_provider.strip()
            or route_provider.strip().lower() == "unresolved"):
        raise ValidationError(
            message="A resolved road route is required before quoting a fare.",
            field="pickup",
        )
    distance = round(float(distance_km), 6)
    duration = round(float(route_duration_s), 3)
    payload = {
        "v": 2,
        "distance_basis": "road_network",
        "service_type": str(service_type or "on_demand").strip().lower(),
        "vehicle_class": str(vehicle_class or "").strip().lower(),
        "currency": str(currency or "").strip().upper(),
        "amount": format(money_amount(amount), ".2f"),
        "fare_version": str(fare_version or ""),
        "pickup": _coords(pickup),
        "dropoff": _coords(dropoff),
        "distance_km": distance,
        "route_duration_s": duration,
        "route_provider": route_provider.strip()[:64],
        "quoted_at": quoted_at.replace(microsecond=0).isoformat(),
    }
    if not payload["vehicle_class"] or not payload["currency"] or not payload["fare_version"]:
        raise ValidationError(
            message="The fare quote is incomplete. Please try again.",
            field="fare_quote_token",
        )
    return _serializer().dumps(payload)


def load_fare_quote(token: Any) -> Dict[str, Any]:
    """Verify quote authenticity and expiry before using any quoted field."""
    if not isinstance(token, str) or not token.strip():
        raise ValidationError(
            message="Please review and confirm a current fare before requesting a driver.",
            field="fare_quote_token",
        )
    max_age = int(current_app.config.get(
        "TRANSPORT_FARE_QUOTE_MAX_AGE_SECONDS",
        DEFAULT_QUOTE_MAX_AGE_SECONDS,
    ))
    try:
        payload = _serializer().loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise ValidationError(
            message="Your fare quote has expired. Please review the updated fare before continuing.",
            field="fare_quote_token",
        ) from exc
    except BadSignature as exc:
        raise ValidationError(
            message="Your fare quote could not be verified. Please review the fare again.",
            field="fare_quote_token",
        ) from exc
    if not isinstance(payload, dict) or payload.get("v") != 2:
        raise ValidationError(
            message="Your fare quote is invalid. Please review the fare again.",
            field="fare_quote_token",
        )
    road_measurements_from_quote(payload)
    return payload


def validate_fare_quote(
    quote: Dict[str, Any],
    *,
    service_type: str,
    vehicle_class: str,
    currency: str,
    pickup: Dict[str, Any],
    dropoff: Dict[str, Any],
    distance_km: Any,
    route_duration_s: Any,
    route_provider: str,
    fare_version: Any,
    server_amount: Any,
    confirmed_amount: Any,
) -> Decimal:
    """Require the accepted amount, trip and road-route facts to match."""
    accepted = money_amount(confirmed_amount)
    quoted = money_amount(quote.get("amount"))
    current = money_amount(server_amount)
    if not _finite_nonnegative(distance_km) or not _finite_nonnegative(route_duration_s):
        raise ValidationError(
            message="The route could not be verified. Please request a new fare.",
            field="pickup",
        )
    measured_distance = round(float(distance_km), 6)
    measured_duration = round(float(route_duration_s), 3)
    route_facts = road_measurements_from_quote(quote)

    matches = (
        quote.get("distance_basis") == "road_network"
        and quote.get("service_type") == str(service_type or "on_demand").strip().lower()
        and quote.get("vehicle_class") == str(vehicle_class or "").strip().lower()
        and quote.get("currency") == str(currency or "").strip().upper()
        and quote.get("pickup") == _coords(pickup)
        and quote.get("dropoff") == _coords(dropoff)
        and route_facts["distance_km"] == measured_distance
        and route_facts["route_duration_s"] == measured_duration
        and route_facts["route_provider"] == str(route_provider or "").strip()[:64]
        and quote.get("fare_version") == str(fare_version or "")
        and accepted == quoted == current
    )
    if not matches:
        raise ValidationError(
            message="The fare or trip details have changed. Please review the current fare and confirm again.",
            field="confirmed_fare_amount",
        )
    return accepted
