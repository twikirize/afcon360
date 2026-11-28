# app/transport/api/ride_options_routes.py
"""Pre-confirmation fare quotes by vehicle class.

This endpoint must not query live driver/vehicle supply or initiate matching.
It returns short-lived signed fare quotes from the canonical fare engine;
the rider must confirm the exact quote and payment method before a request
is persisted and driver matching begins. Every quote uses a resolved GEO road
route; straight-line distance is never used as a fare substitute.
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

        # The rider's Wallet currency is a presentation preference only.
        # The signed fare quote and eventual Wallet invoice stay denominated
        # in the fare table's authoritative currency (currently USD).
        preferred_currency = currency
        if current_user.is_authenticated:
            try:
                from app.wallet.services.home_currency_service import get_user_home_currency
                preferred_currency = get_user_home_currency(current_user)
            except Exception:
                logger.warning("Could not resolve rider home currency; retaining fare currency")

        # Fare discovery remains quote-only: no live supply lookup, driver
        # matching, or ETA estimation. The GEO provider supplies one authoritative
        # driving route, and its exact distance/duration are signed into every
        # vehicle-class quote returned below.
        quote_at = datetime.now().replace(microsecond=0)
        pickup = {"latitude": float(pickup_lat), "longitude": float(pickup_lng)}
        dropoff = {"latitude": float(dropoff_lat), "longitude": float(dropoff_lng)}
        from app.transport.services.road_distance_service import measure_road_route
        from app.utils.exceptions import ServiceUnavailableError
        try:
            route = measure_road_route(pickup, dropoff)
        except ServiceUnavailableError as exc:
            return {
                "success": False,
                "code": "ROUTING_UNAVAILABLE",
                "error": exc.message,
            }, 503

        distance_km = route["distance_km"]
        distance_basis = route["distance_basis"]

        # The fare engine currently denominates transport quotes in its own
        # currency. A separate Wallet-currency amount is display-only.
        from app.wallet.services.display_fx_service import build_display_amount
        options = []
        active_tables, _, _ = fare_service.resolve_tables(at=quote_at)
        explicitly_priced_classes = set(
            (active_tables.get("class_multipliers") or {}).keys()
        )
        for vc in VehicleClass:
            vc_value = str(getattr(vc, "value", vc)).lower()
            # Do not publish a quote for a vehicle class that has no
            # explicit price multiplier. The fare engine's fallback to the
            # default class is useful for legacy inputs, but would mislead a
            # rider comparing vehicle classes.
            if vc_value not in explicitly_priced_classes:
                continue
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
                    route_duration_s=route["duration_s"],
                    route_provider=route["provider"],
                    quoted_at=quote_at,
                )
            except Exception as exc:
                logger.warning("Ride-option fare failed for %s: %s", vc_value, exc)
                continue

            display_fields = build_display_amount(
                fare_total, quote_currency, preferred_currency
            )
            options.append({
                "vehicle_class": vc_value,
                "display_name": _DISPLAY_NAMES.get(vc, vc_value.title()),
                # fare_total/currency remain the signed, authoritative values.
                "fare_total": fare_total,
                "fare_breakdown": estimate["breakdown"],
                "fare_version": estimate["version"],
                "currency": quote_currency,
                # display_* are non-authoritative, indicative UI fields only.
                **display_fields,
                "quote_token": quote_token,
            })

        options.sort(key=lambda o: o["fare_total"])

        return {
            "success": True,
            "data": {
                "service_type":   service_type,
                "currency":       (options[0]["currency"] if options else currency),
                "home_currency":  preferred_currency,
                "display_currency": (options[0]["display_currency"] if options else currency),
                "distance_km":    float(distance_km),
                "distance_basis": distance_basis,
                "duration_s":     route["duration_s"],
                "duration_minutes": route["duration_minutes"],
                "route_provider": route["provider"],
                "route_geometry": route["geometry"],
                "options":        options,
                "note": (
                    "Fare estimate only. This endpoint does not query driver "
                    "or vehicle availability and does not contact drivers. "
                    "Matching starts only after the rider confirms the quoted "
                    "amount and selects an available payment method. Any "
                    "home-currency amount is an indicative display estimate; "
                    "the signed quote and Wallet invoice remain in the fare currency."
                ),
            },
        }, 200


