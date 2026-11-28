# app/transport/api/fare_routes.py
"""AFCON360 Transport API - fare estimation (fare node).

POST /api/transport/fare/estimate: pre-submit estimate from the
CANONICAL fare engine (the same implementation that prices bookings
at creation). No JavaScript-side pricing, no duplicate formulas.

Inputs (JSON): service_type, vehicle_class, estimated_distance_km
(optional, planning default labelled in the response), plus optional
pickup_latitude/pickup_longitude/dropoff_latitude/dropoff_longitude:
when both endpoints are supplied, distance is resolved from the GEO road
routing provider. Explicit distance-only input remains labelled as a
planning input and is never used to create a booking.

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
        distance_basis = "explicit_planning_input" if distance_km is not None else "planning_default"
        route = None
        coordinate_keys = (
            "pickup_latitude", "pickup_longitude",
            "dropoff_latitude", "dropoff_longitude",
        )
        supplied_coordinates = any(
            data.get(key) not in (None, "") for key in coordinate_keys
        )
        if distance_km is None and supplied_coordinates:
            if any(data.get(key) in (None, "") for key in coordinate_keys):
                return {"success": False, "error": "All four resolved route coordinates are required."}, 400
            from app.transport.services.road_distance_service import measure_road_route
            from app.utils.exceptions import ServiceUnavailableError, ValidationError
            try:
                route = measure_road_route(
                    {
                        "latitude": data.get("pickup_latitude"),
                        "longitude": data.get("pickup_longitude"),
                    },
                    {
                        "latitude": data.get("dropoff_latitude"),
                        "longitude": data.get("dropoff_longitude"),
                    },
                )
            except ValidationError as exc:
                return {"success": False, "error": exc.message}, 400
            except ServiceUnavailableError as exc:
                return {
                    "success": False,
                    "code": "ROUTING_UNAVAILABLE",
                    "error": exc.message,
                }, 503
            distance_km = route["distance_km"]
            distance_basis = "road_network"

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
                "duration_s": route["duration_s"] if route else None,
                "duration_minutes": route["duration_minutes"] if route else None,
                "route_provider": route["provider"] if route else None,
                "default_distance_km": float(DEFAULT_DISTANCE_KM),
                "note": ("Planning estimate from the canonical fare "
                         "engine; final fare follows authoritative trip "
                         "facts (tolls, waiting/cancellation rules, "
                         "promotions)."),
            },
        }, 200


class FareConfigResource(Resource):
    """GET/PUT /api/transport/fare/config — governed fare tables.

    Both methods require the ``owner`` or ``super_admin`` global role.
    The platform owner holds this unconditionally; super_admin is
    explicitly granted. Transport admins and other roles are denied.
    Reads expose the active version plus audit trail;
    writes validate completeness, assign the next version, and persist
    through the TransportSetting audit trail (old/new/at/by) with
    cache invalidation. UI available on Owner/Super Admin settings page.
    """

    @staticmethod
    def _guard():
        from flask_login import current_user
        if not current_user.is_authenticated:
            return {"success": False,
                    "error": "Authentication required"}, 401
        # The platform owner is authoritative. A super admin must also
        # hold the specific fare-settings delegation; the broad super_admin
        # role alone must not silently grant financial configuration access.
        is_owner = False
        is_super = False
        if hasattr(current_user, "has_global_role"):
            try:
                is_owner = current_user.has_global_role("owner")
                is_super = current_user.has_global_role("super_admin")
            except Exception:
                pass
        delegated = False
        if is_super and not is_owner:
            from app.auth.helpers import has_global_permission
            delegated = has_global_permission(current_user, "transport.settings")
        if not (is_owner or delegated):
            return {
                "success": False,
                "error": "Owner or delegated Super Admin role required",
            }, 403
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
