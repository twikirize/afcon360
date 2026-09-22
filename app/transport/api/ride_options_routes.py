# app/transport/api/ride_options_routes.py
"""Ride options — live available vehicles by class, priced by the
canonical fare engine (hailing node).

Availability comes from ``availability_service`` (the single source of
truth for "available right now"). Pricing comes from FareService.
Distance comes from GEO's straight-line planner. Nothing in this module
invents availability, price, or distance.
"""
import logging

from flask import request
from flask_restful import Resource

from app.transport.models import Currency, VehicleClass
from app.transport.services import fare_service
from app.transport.services.availability_service import (
    available_by_class,
    nearest_eta_minutes_for_class,
)

logger = logging.getLogger(__name__)

_DISPLAY_NAMES = {
    VehicleClass.ECONOMY: "Economy",
    VehicleClass.COMFORT: "Comfort",
    VehicleClass.PREMIUM: "Premium",
    VehicleClass.LUXURY: "Luxury",
    VehicleClass.VAN:     "Van",
    VehicleClass.BUS:     "Bus",
}


class RideOptionsResource(Resource):
    """POST /api/transport/ride-options

    Anonymous-allowed so riders can see prices before signing in. The
    booking action still goes through transport.book_transport (auth +
    KYC + rate limit unchanged).
    """

    def post(self):
        data = request.get_json(silent=True) or {}
        service_type = data.get("service_type") or "on_demand"

        currency = str(data.get("currency") or "USD").upper()
        try:
            Currency(currency)
        except ValueError:
            return {"success": False,
                    "error": f"Unknown currency: {currency}"}, 400

        # Distance basis (same rules as fare estimate): caller-supplied
        # estimate wins, then straight-line from supplied pins, then the
        # engine's planning default.
        distance_km = data.get("estimated_distance_km")
        distance_basis = "planning_default"
        if distance_km is None:
            sl = _straight_line_km(data)
            if sl is not None:
                distance_km = sl
                distance_basis = "straight_line_planner"

        pickup = _point(data, "pickup")

        # Real availability — from the availability service, not a raw
        # Vehicle query.
        rows = available_by_class()

        options = []
        for row in rows:
            vc_raw = row["vehicle_class"]
            vc = vc_raw if isinstance(vc_raw, VehicleClass) else VehicleClass(vc_raw)

            try:
                estimate = fare_service.calculate_estimate(
                    service_type=service_type,
                    vehicle_class=vc.value,
                    distance_km=distance_km,
                )
            except Exception as exc:
                logger.warning("Ride-option fare failed for %s: %s", vc, exc)
                continue

            eta_minutes = nearest_eta_minutes_for_class(vc.value, pickup)

            options.append({
                "vehicle_class":   vc.value,
                "display_name":    _DISPLAY_NAMES.get(vc, vc.value.title()),
                "available_count": row["available_count"],
                "capacity":        row["capacity"],
                "luggage":         row["luggage"],
                "fare_total":      float(estimate["total"]),
                "fare_breakdown":  estimate["breakdown"],
                "fare_version":    estimate["version"],
                "currency":        currency,
                "eta_minutes":     eta_minutes,
                "eta_basis":       ("straight_line_planner"
                                    if eta_minutes is not None else None),
            })

        options.sort(key=lambda o: o["fare_total"])

        # Truthful distance reporting when the planning default priced
        # the options.
        if distance_km is None and options:
            distance_km = options[0]["fare_breakdown"].get("distance_km")

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
