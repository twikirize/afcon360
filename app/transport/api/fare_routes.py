# app/transport/api/fare_routes.py
"""AFCON360 Transport API - fare estimation (fare node).

POST /api/transport/fare/estimate: pre-submit estimate from the
CANONICAL fare engine (the same implementation that prices bookings
at creation). No JavaScript-side pricing, no duplicate formulas.

Inputs (JSON): service_type, vehicle_class, estimated_distance_km
(optional, planning default labelled in the response), plus optional
pickup_latitude/pickup_longitude/dropoff_latitude/dropoff_longitude:
when both endpoints are valid, distance derives from the GEO
straight-line planner (explicitly NOT road distance); otherwise the
planning default applies. Either way the response states which
distance basis was used.

Auth: login required (consistent with the booking flow that consumes
estimates). Riders can estimate; only the booking service persists.
"""

import logging

from flask import request
from flask_restful import Resource

from app.extensions import limiter
from app.transport.api.ride_options_routes import _rate_limit_key

logger = logging.getLogger(__name__)


class FareEstimateResource(Resource):
    """POST /api/transport/fare/estimate"""

    method_decorators = [
        limiter.limit("30 per minute", key_func=_rate_limit_key),
    ]

    # NOTE: no @login_required decorator here on purpose (see below).
    def post(self):
        from flask_login import current_user

        # Manual auth check (not just the decorator): the platform's
        # flask_restful error_router turns @login_required denials into
        # 500s (known defect, BACKLOG). This endpoint returns the
        # intended 401 itself instead of inheriting that failure.
        if not current_user.is_authenticated:
            return {"success": False,
                    "error": "Authentication required"}, 401
        from app.transport.services.fare_service import (
            DEFAULT_DISTANCE_KM,
            calculate_estimate,
        )

        data = request.get_json(silent=True) or {}
        service_type = data.get("service_type", "on_demand")
        vehicle_class = data.get("vehicle_class", "comfort")

        # Currency is echoed, never converted: the engine computes in
        # base-table units and performs no FX. Unknown codes are
        # rejected rather than silently priced.
        from app.transport.models import Currency
        currency = str(data.get("currency") or "USD").upper()
        try:
            Currency(currency)
        except ValueError:
            return {"success": False,
                    "error": f"Unknown currency: {currency}"}, 400

        distance_km = data.get("estimated_distance_km")
        distance_basis = "planning_default"
        if distance_km is None:
            coords = _straight_line_km(data)
            if coords is not None:
                distance_km = coords
                distance_basis = "straight_line_planner"

        try:
            estimate = calculate_estimate(
                service_type=service_type,
                vehicle_class=vehicle_class,
                distance_km=distance_km,
            )
        except Exception as exc:
            logger.warning("Fare estimate rejected: %s", exc)
            return {"success": False,
                    "error": "Invalid estimate parameters"}, 400

        return {
            "success": True,
            "data": {
                "currency": currency,
                "currency_note": ("Amounts follow the base fare tables; "
                                  "no FX conversion is performed."),
                "version": estimate["version"],
                "total": float(estimate["total"]),
                "breakdown": estimate["breakdown"],
                "inputs": estimate["inputs"],
                "distance_basis": distance_basis,
                "default_distance_km": float(DEFAULT_DISTANCE_KM),
                "note": ("Planning estimate from the canonical fare "
                         "engine; final fare follows authoritative trip "
                         "facts (tolls, waiting/cancellation rules, "
                         "promotions)."),
            },
        }, 200


def _straight_line_km(data):
    """GEO straight-line kilometres between supplied endpoints, or
    None when either endpoint is absent/invalid. Planning input only:
    explicitly not road distance, ETA, or fare distance."""
    try:
        from app.geo.interfaces import GeoPoint
        from app.geo.services import straight_line_distance_m
        origin = GeoPoint(float(data["pickup_latitude"]),
                          float(data["pickup_longitude"]))
        destination = GeoPoint(float(data["dropoff_latitude"]),
                               float(data["dropoff_longitude"]))
    except (KeyError, TypeError, ValueError):
        return None
    try:
        from app.core.validators import validate_coordinates
        validate_coordinates(origin.latitude, origin.longitude)
        validate_coordinates(destination.latitude, destination.longitude)
    except Exception:
        return None
    return straight_line_distance_m(origin, destination) / 1000.0


class FareConfigResource(Resource):
    """GET/PUT /api/transport/fare/config — governed fare tables.

    Both methods require the ``transport.settings`` permission: the
    platform owner holds it unconditionally; a super-admin (or any
    role) holds it only through explicit delegation; everyone else
    is denied. Reads expose the active version plus audit trail;
    writes validate completeness, assign the next version, and persist
    through the TransportSetting audit trail (old/new/at/by) with
    cache invalidation. No admin UI is built in this node; the
    contract is API-proven and browser-proven via authenticated calls.
    """

    @staticmethod
    def _guard():
        from flask_login import current_user
        from app.auth.policy import can_configure_transport
        if not current_user.is_authenticated:
            return {"success": False,
                    "error": "Authentication required"}, 401
        if not can_configure_transport(current_user):
            return {"success": False,
                    "error": "transport.settings permission required"}, 403
        return None

    def get(self):
        denied = self._guard()
        if denied is not None:
            return denied
        from app.transport.services.fare_service import read_configuration
        try:
            config = read_configuration()
        except Exception as exc:
            logger.warning("Fare configuration read failed: %s", exc)
            return {"success": False,
                    "error": "Configuration unavailable"}, 503
        return {"success": True, "data": config}, 200

    def put(self):
        denied = self._guard()
        if denied is not None:
            return denied
        from flask_login import current_user
        from app.transport.services.fare_service import update_fare_tables

        data = request.get_json(silent=True) or {}
        if "tables" not in data:
            return {"success": False,
                    "error": "tables object required"}, 400
        try:
            result = update_fare_tables(
                data["tables"],
                actor_user_id=int(current_user.id),
                effective_from=data.get("effective_from"),
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 400
        except Exception as exc:
            logger.warning("Fare configuration write failed: %s", exc)
            return {"success": False,
                    "error": "Configuration write failed"}, 500
        return {"success": True, "data": result}, 200
