# app/transport/api/ride_options_routes.py
"""Pre-confirmation fare quotes by vehicle class.

This endpoint must not query live driver/vehicle supply or initiate matching.
It returns short-lived signed fare quotes from the canonical fare engine;
the rider must confirm the exact quote and payment method before a request
is persisted and driver matching begins. Distance uses the GEO straight-line
planner; no road-distance claim is made.
"""
import logging

from flask import request
from flask_login import current_user
from flask_restful import Resource

from app.extensions import limiter
from app.transport.models import Currency, VehicleClass
from app.transport.services import fare_service
from datetime import datetime

from app.transport.services.fare_quote_service import issue_fare_quote, money_amount

logger = logging.getLogger(__name__)

_DISPLAY_NAMES = {
    VehicleClass.ECONOMY: "Economy",
    VehicleClass.COMFORT: "Comfort",
    VehicleClass.PREMIUM: "Premium",
    VehicleClass.LUXURY: "Luxury",
    VehicleClass.VAN:     "Van",
    VehicleClass.BUS:     "Bus",
}


def _rate_limit_key():
    """Per-caller rate-limit key shared by the public estimate endpoints.

    Authenticated callers are keyed by user id; anonymous callers by IP.
    Server-side limiter key only — never rendered or exposed.
    """
    if current_user.is_authenticated:
        return f"user:{current_user.id}"
    return f"ip:{request.remote_addr}"


class RideOptionsResource(Resource):
    """POST /api/transport/ride-options

    Anonymous-allowed so riders can see prices before signing in. The
    booking action still goes through transport.book_transport (auth +
    KYC + rate limit unchanged).
    """

    method_decorators = [
        limiter.limit("30 per minute", key_func=_rate_limit_key),
    ]

    def post(self):
        data = request.get_json(silent=True) or {}
        service_type = data.get("service_type") or "on_demand"

        currency = str(data.get("currency") or "USD").upper()
        try:
            Currency(currency)
        except ValueError:
            return {"success": False,
                    "error": f"Unknown currency: {currency}"}, 400

        # UI-LOC-02A: booking-bound quote inputs must carry resolved
        # coordinates. Validate RAW values with the canonical validator
        # (no float() pre-conversion — that launders bool/nan/inf).
        # Only after validation converts to float for distance/fare.
        from app.core.validators import validate_coordinates
        pickup_lat = data.get("pickup_latitude")
        pickup_lng = data.get("pickup_longitude")
        dropoff_lat = data.get("dropoff_latitude")
        dropoff_lng = data.get("dropoff_longitude")

        # All four coordinate fields must be present and numeric
        coord_fields = {
            "pickup_latitude": pickup_lat,
            "pickup_longitude": pickup_lng,
            "dropoff_latitude": dropoff_lat,
            "dropoff_longitude": dropoff_lng,
        }
        for name, value in coord_fields.items():
            if value is None or (isinstance(value, str) and value == ""):
                return {"success": False, "error": f"Missing coordinate: {name}"}, 400
            # Canonical verdict on the RAW value, paired with a known-valid
            # peer (0.0 is in range on both axes), so any rejection is
            # attributable to `value` alone. No float() pre-conversion here.
            try:
                if name.endswith("latitude"):
                    validate_coordinates(value, 0)
                else:
                    validate_coordinates(0, value)
            except Exception:
                # Message granularity only (not a second verdict): the
                # rejection above is authoritative. Non-numeric (incl. bool)
                # keeps the historic "Invalid coordinate" text; numeric but
                # rejected (range/non-finite) keeps axis-specific text.
                if isinstance(value, bool):
                    return {"success": False, "error": f"Invalid coordinate: {name}"}, 400
                try:
                    float(value)
                except (TypeError, ValueError):
                    return {"success": False, "error": f"Invalid coordinate: {name}"}, 400
                if name.endswith("latitude"):
                    return {"success": False, "error": f"Invalid latitude: {name}"}, 400
                return {"success": False, "error": f"Invalid longitude: {name}"}, 400

        # Fare discovery is quote-only: do not query online drivers, vehicles,
        # availability, or ETA before the rider accepts an exact quote.
        # Every supported class can be priced even when no driver is online.
        distance_km = _straight_line_km(data)
        if distance_km is None:
            return {"success": False, "error": "Invalid coordinates for distance calculation"}, 400
        distance_basis = "straight_line_planner"
        quote_at = datetime.now().replace(microsecond=0)
        pickup = {"latitude": float(pickup_lat), "longitude": float(pickup_lng)}
        dropoff = {"latitude": float(dropoff_lat), "longitude": float(dropoff_lng)}

        # The fare engine currently denominates transport quotes in its own
        # currency. Never label a USD amount as UGX/KES/TZS or imply FX.
        options = []
        for vc in VehicleClass:
            vc_value = str(getattr(vc, "value", vc)).lower()
            try:
                estimate = fare_service.calculate_estimate(
                    service_type=service_type,
                    vehicle_class=vc_value,
                    distance_km=distance_km,
                    at=quote_at,
                )
                quote_currency = str(estimate.get("currency") or "USD").upper()
                if quote_currency != currency:
                    return {
                        "success": False,
                        "error": ("Transport fares are currently quoted in %s. "
                                  "No automatic currency conversion is applied." % quote_currency),
                    }, 400
                fare_total = float(money_amount(estimate["total"]))
                quote_token = issue_fare_quote(
                    service_type=service_type,
                    vehicle_class=vc_value,
                    currency=quote_currency,
                    amount=fare_total,
                    fare_version=estimate.get("version"),
                    pickup=pickup,
                    dropoff=dropoff,
                    distance_km=distance_km,
                    quoted_at=quote_at,
                )
            except Exception as exc:
                logger.warning("Ride-option fare failed for %s: %s", vc_value, exc)
                continue

            options.append({
                "vehicle_class": vc_value,
                "display_name": _DISPLAY_NAMES.get(vc, vc_value.title()),
                "fare_total": fare_total,
                "fare_breakdown": estimate["breakdown"],
                "fare_version": estimate["version"],
                "currency": quote_currency,
                "quote_token": quote_token,
            })

        options.sort(key=lambda o: o["fare_total"])

        return {
            "success": True,
            "data": {
                "service_type":   service_type,
                "currency":       currency,
                "distance_km":    float(distance_km) if distance_km is not None else None,
                "distance_basis": distance_basis,
                "options":        options,
                "note": (
                    "Availability is live (online drivers with a current "
                    "vehicle, not engaged elsewhere). Fares come from the "
                    "canonical fare engine. ETA is a straight-line "
                    "planning estimate, not road routing."
                ),
            },
        }, 200


# ----------------------------------------------------------------- helpers

def _point(data, prefix):
    try:
        return (float(data[f"{prefix}_latitude"]),
                float(data[f"{prefix}_longitude"]))
    except (KeyError, TypeError, ValueError):
        return None


def _valid_coords(lat, lng):
    return (-90.0 <= lat <= 90.0) and (-180.0 <= lng <= 180.0)


def _straight_line_km(data):
    try:
        from app.geo.interfaces import GeoPoint
        from app.geo.services import straight_line_distance_m
        a, b = _point(data, "pickup"), _point(data, "dropoff")
        if not a or not b:
            return None
        if not (_valid_coords(a[0], a[1]) and _valid_coords(b[0], b[1])):
            return None
        return straight_line_distance_m(
            GeoPoint(a[0], a[1]), GeoPoint(b[0], b[1]),
        ) / 1000.0
    except Exception:
        return None
