# app/transport/api/route_routes.py
"""
AFCON360 Transport — Scheduled Routes REST API
Manages fixed shuttle routes: stadium transfers, airport runs,
hotel circuits. Handles capacity, scheduling, and live assignment.
"""
from flask import request
from flask_restful import Resource
from app.extensions import db
from app.transport.models import (
    ScheduledRoute, DriverProfile, Vehicle, Booking, BookingStatus
)
from app.admin.routes import admin_required
from app.transport.utils.helpers import paginate, filter_query, sort_query
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

ROUTE_SORT_FIELDS = [
    "created_at", "updated_at", "next_departure",
    "route_type", "is_active", "available_seats", "price_per_seat"
]


def _route_or_404(route_id):
    return ScheduledRoute.query.filter_by(
        id=route_id, is_deleted=False
    ).first_or_404()


# ===========================================================================
# Scheduled Route List
# ===========================================================================

class ScheduledRouteListResource(Resource):
    """GET /api/transport/routes  — list with filters/sort/pagination
       POST /api/transport/routes — create a new scheduled route
    """

    def get(self):
        """List scheduled routes with filtering, sorting, and pagination"""
        query = ScheduledRoute.query.filter_by(is_deleted=False)

        filters = {
            "route_type":   request.args.get("route_type"),
            "primary_zone": request.args.get("zone"),
            "is_active":    request.args.get("is_active", type=bool),
            "is_cancelled": request.args.get("is_cancelled", type=bool),
            "is_free":      request.args.get("is_free", type=bool),
            "provider_type": request.args.get("provider_type"),
        }
        query = filter_query(query, ScheduledRoute, filters)

        # Seats available filter
        min_seats = request.args.get("min_seats", type=int)
        if min_seats:
            query = query.filter(ScheduledRoute.available_seats >= min_seats)

        # Departure window
        depart_from = request.args.get("depart_from")
        depart_to = request.args.get("depart_to")
        if depart_from:
            query = query.filter(ScheduledRoute.next_departure >= depart_from)
        if depart_to:
            query = query.filter(ScheduledRoute.next_departure <= depart_to)

        # Provider filter
        provider_id = request.args.get("provider_id", type=int)
        if provider_id:
            query = query.filter(ScheduledRoute.provider_id == provider_id)

        query = sort_query(query, ScheduledRoute, ROUTE_SORT_FIELDS)
        result = paginate(query)

        return {
            "success": True,
            "data": {
                "items": [r.to_dict() for r in result["items"]],
                "total":    result["total"],
                "page":     result["page"],
                "per_page": result["per_page"],
                "pages":    result["pages"],
                "has_next": result["has_next"],
                "has_prev": result["has_prev"],
            },
        }

    @admin_required
    def post(self):
        """Create a new scheduled route"""
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        required = [
            "provider_type", "provider_id", "name",
            "route_type", "route_code", "schedule_pattern",
            "stops", "vehicle_capacity"
        ]
        missing = [f for f in required if f not in data]
        if missing:
            return {"success": False, "error": f"Missing fields: {missing}"}, 400

        # Duplicate route code check
        existing = ScheduledRoute.query.filter_by(
            route_code=data["route_code"], is_deleted=False
        ).first()
        if existing:
            return {"success": False, "error": f"Route code {data['route_code']} already exists"}, 409

        try:
            route = ScheduledRoute(
                provider_type=data["provider_type"],
                provider_id=data["provider_id"],
                name=data["name"],
                route_type=data["route_type"],
                route_code=data["route_code"],
                schedule_pattern=data["schedule_pattern"],
                stops=data["stops"],
                vehicle_capacity=data["vehicle_capacity"],
            )
            # Optional fields
            for field in [
                "description", "duration_minutes", "path_coordinates",
                "primary_zone", "price_per_seat", "is_free",
                "timezone", "next_departure"
            ]:
                if field in data:
                    setattr(route, field, data[field])

            # Init available seats
            route.available_seats = route.vehicle_capacity
            route.booked_seats = 0

            db.session.add(route)
            db.session.commit()
            logger.info(f"Route created: code={route.route_code}, id={route.id}")
            return {"success": True, "data": route.to_dict()}, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating route: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Scheduled Route Detail
# ===========================================================================

class ScheduledRouteDetailResource(Resource):
    """GET/PUT/DELETE /api/transport/routes/<route_id>"""

    def get(self, route_id):
        """Get route detail with live capacity and current assignment"""
        route = _route_or_404(route_id)

        # Refresh availability
        route.update_availability()

        # Current bookings for this route
        active_bookings = Booking.query.filter(
            Booking.assigned_route_id == route_id,
            Booking.is_deleted == False,
            Booking.status.in_([
                BookingStatus.CONFIRMED,
                BookingStatus.ASSIGNED,
                BookingStatus.IN_PROGRESS,
            ])
        ).count()

        return {
            "success": True,
            "data": {
                "route": route.to_dict(),
                "capacity": {
                    "total": route.vehicle_capacity,
                    "booked": route.booked_seats,
                    "available": route.available_seats,
                    "is_full": route.is_full,
                    "active_bookings": active_bookings,
                },
                "current_driver": (
                    DriverProfile.query.get(route.current_driver_id)
                    .to_dict(exclude=["license_number_encrypted"])
                    if route.current_driver_id else None
                ),
                "current_vehicle": (
                    Vehicle.query.get(route.current_vehicle_id).to_dict()
                    if route.current_vehicle_id else None
                ),
            },
        }

    @admin_required
    def put(self, route_id):
        """Update route details"""
        route = _route_or_404(route_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        updatable = [
            "name", "description", "schedule_pattern", "stops",
            "path_coordinates", "primary_zone", "timezone",
            "duration_minutes", "vehicle_capacity",
            "price_per_seat", "is_free",
            "is_active", "is_cancelled", "cancellation_reason",
            "next_departure", "route_metadata",
        ]
        for field in updatable:
            if field in data:
                setattr(route, field, data[field])

        # Recalculate if capacity changed
        if "vehicle_capacity" in data:
            route.update_availability()

        try:
            db.session.commit()
            logger.info(f"Route {route_id} updated")
            return {"success": True, "data": route.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating route {route_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500

    @admin_required
    def delete(self, route_id):
        """Cancel and soft-delete a scheduled route"""
        route = _route_or_404(route_id)

        # Block deletion if active bookings exist
        active = Booking.query.filter(
            Booking.assigned_route_id == route_id,
            Booking.is_deleted == False,
            Booking.status.in_([
                BookingStatus.CONFIRMED,
                BookingStatus.ASSIGNED,
                BookingStatus.IN_PROGRESS,
            ])
        ).count()

        if active:
            return {
                "success": False,
                "error": f"Cannot delete route with {active} active booking(s). Cancel them first.",
                "active_bookings": active,
            }, 409

        route.is_deleted = True
        route.deleted_at = datetime.now(timezone.utc)
        route.is_active = False
        route.is_cancelled = True
        route.cancellation_reason = "Route deleted by admin"

        try:
            db.session.commit()
            logger.info(f"Route {route_id} deleted")
            return {"success": True, "message": "Route cancelled and deleted"}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting route {route_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Route Assignment (Driver + Vehicle)
# ===========================================================================

class ScheduledRouteAssignmentResource(Resource):
    """POST /api/transport/routes/<route_id>/assign"""

    @admin_required
    def post(self, route_id):
        """
        Assign a driver and/or vehicle to a scheduled route.
        Validates availability before assigning.
        """
        route = _route_or_404(route_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        driver_id = data.get("driver_id")
        vehicle_id = data.get("vehicle_id")

        if not driver_id and not vehicle_id:
            return {"success": False, "error": "driver_id or vehicle_id required"}, 400

        if driver_id:
            driver = DriverProfile.query.filter_by(
                id=driver_id, is_deleted=False, is_available=True
            ).first()
            if not driver:
                return {
                    "success": False,
                    "error": f"Driver {driver_id} not found or unavailable"
                }, 404
            route.current_driver_id = driver_id

        if vehicle_id:
            vehicle = Vehicle.query.filter_by(
                id=vehicle_id, is_deleted=False, is_available=True
            ).first()
            if not vehicle:
                return {
                    "success": False,
                    "error": f"Vehicle {vehicle_id} not found or unavailable"
                }, 404

            # Validate vehicle has enough capacity for the route
            if vehicle.passenger_capacity < route.vehicle_capacity:
                return {
                    "success": False,
                    "error": (
                        f"Vehicle capacity ({vehicle.passenger_capacity}) is less than "
                        f"route capacity ({route.vehicle_capacity})"
                    ),
                }, 422
            route.current_vehicle_id = vehicle_id

        try:
            db.session.commit()
            logger.info(
                f"Route {route_id} assigned: driver={driver_id}, vehicle={vehicle_id}"
            )
            return {
                "success": True,
                "data": {
                    "route_id": route_id,
                    "current_driver_id": route.current_driver_id,
                    "current_vehicle_id": route.current_vehicle_id,
                },
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning route {route_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500