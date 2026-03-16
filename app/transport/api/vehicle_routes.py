# app/transport/api/vehicle_routes.py
"""
AFCON360 Transport — Vehicle REST API
Handles vehicle registration, verification, maintenance tracking,
and driver assignment management.
"""
from flask import request
from flask_restful import Resource
from app.extensions import db
from app.transport.models import (
    Vehicle, VehicleClass, DriverProfile, DriverVehicleHistory
)
from app.admin.routes import admin_required
from app.transport.utils.helpers import paginate, filter_query, sort_query
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

VEHICLE_SORT_FIELDS = [
    "created_at", "updated_at", "year", "status",
    "vehicle_class", "passenger_capacity", "odometer_reading_km"
]


def _vehicle_or_404(vehicle_id):
    return Vehicle.query.filter_by(id=vehicle_id, is_deleted=False).first_or_404()


# ===========================================================================
# Vehicle List
# ===========================================================================

class VehicleListResource(Resource):
    """GET /api/transport/vehicles — list with filters/sort/pagination
       POST /api/transport/vehicles — register a new vehicle
    """

    def get(self):
        """List vehicles with filtering, sorting, and pagination"""
        query = Vehicle.query.filter_by(is_deleted=False)

        filters = {
            "vehicle_class":   request.args.get("vehicle_class"),
            "status":          request.args.get("status"),
            "owner_type":      request.args.get("owner_type"),
            "is_available":    request.args.get("is_available", type=bool),
            "is_trackable":    request.args.get("is_trackable", type=bool),
            "maintenance_status": request.args.get("maintenance_status"),
            "passenger_capacity__gte": request.args.get("min_capacity", type=int),
        }
        query = filter_query(query, Vehicle, filters)

        # Owner filter
        owner_id = request.args.get("owner_id", type=int)
        if owner_id:
            query = query.filter(Vehicle.owner_id == owner_id)

        # Insurance expiry warning (expiring within N days)
        expiring_days = request.args.get("insurance_expiring_days", type=int)
        if expiring_days:
            cutoff = datetime.now(timezone.utc) + __import__("datetime").timedelta(days=expiring_days)
            query = query.filter(
                Vehicle.insurance_expiry.isnot(None),
                Vehicle.insurance_expiry <= cutoff,
            )

        # Search on plate or make/model
        search = request.args.get("search")
        if search:
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    Vehicle.license_plate.ilike(f"%{search}%"),
                    Vehicle.make.ilike(f"%{search}%"),
                    Vehicle.model.ilike(f"%{search}%"),
                    Vehicle.registration_number.ilike(f"%{search}%"),
                )
            )

        query = sort_query(query, Vehicle, VEHICLE_SORT_FIELDS)
        result = paginate(query)

        return {
            "success": True,
            "data": {
                "items": [v.to_dict() for v in result["items"]],
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
        """Register a new vehicle"""
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        required = [
            "owner_type", "owner_id", "license_plate",
            "make", "model", "year", "vehicle_type",
            "vehicle_class", "passenger_capacity"
        ]
        missing = [f for f in required if f not in data]
        if missing:
            return {"success": False, "error": f"Missing fields: {missing}"}, 400

        # Duplicate plate check
        existing = Vehicle.query.filter_by(
            license_plate=data["license_plate"], is_deleted=False
        ).first()
        if existing:
            return {"success": False, "error": "License plate already registered"}, 409

        try:
            vehicle = Vehicle(**{k: data[k] for k in required})
            # Optional fields
            for field in ["color", "vin_number", "registration_number", "features",
                          "safety_features", "accessibility_features", "photo_urls"]:
                if field in data:
                    setattr(vehicle, field, data[field])

            vehicle.generate_qr_code()
            db.session.add(vehicle)
            db.session.commit()
            logger.info(f"Vehicle registered: plate={vehicle.license_plate}, id={vehicle.id}")
            return {"success": True, "data": vehicle.to_dict()}, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error registering vehicle: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Vehicle Detail
# ===========================================================================

class VehicleDetailResource(Resource):
    """GET/PUT/DELETE /api/transport/vehicles/<vehicle_id>"""

    def get(self, vehicle_id):
        """Get full vehicle detail including current driver and booking"""
        vehicle = _vehicle_or_404(vehicle_id)

        return {
            "success": True,
            "data": {
                "vehicle": vehicle.to_dict(),
                "current_driver": (
                    vehicle.current_driver.to_dict(
                        exclude=["license_number_encrypted"]
                    ) if vehicle.current_driver else None
                ),
                "current_booking": (
                    vehicle.current_booking.to_dict()
                    if vehicle.current_booking else None
                ),
                "current_assignment": (
                    vehicle.current_assignment.to_dict()
                    if vehicle.current_assignment else None
                ),
                "recent_drivers": [
                    {
                        "driver_id": h.driver_id,
                        "started_at": h.started_at.isoformat(),
                        "ended_at": h.ended_at.isoformat() if h.ended_at else None,
                        "assignment_reason": h.assignment_reason,
                    }
                    for h in vehicle.driving_history[:5]
                ],
            },
        }

    @admin_required
    def put(self, vehicle_id):
        """Update vehicle details"""
        vehicle = _vehicle_or_404(vehicle_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        updatable = [
            "color", "features", "accessibility_features", "safety_features",
            "passenger_capacity", "max_passenger_capacity", "luggage_capacity",
            "is_available", "is_trackable", "tracking_device_id",
            "status", "maintenance_status", "photo_urls", "document_urls",
        ]
        for field in updatable:
            if field in data:
                setattr(vehicle, field, data[field])

        try:
            db.session.commit()
            logger.info(f"Vehicle {vehicle_id} updated")
            return {"success": True, "data": vehicle.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating vehicle {vehicle_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500

    @admin_required
    def delete(self, vehicle_id):
        """Soft delete vehicle"""
        vehicle = _vehicle_or_404(vehicle_id)

        # Cannot delete if currently on an active booking
        if vehicle.current_booking:
            return {
                "success": False,
                "error": "Cannot delete vehicle with an active booking",
            }, 409

        vehicle.is_deleted = True
        vehicle.deleted_at = datetime.now(timezone.utc)
        vehicle.is_available = False
        vehicle.status = "deleted"

        try:
            db.session.commit()
            logger.info(f"Vehicle {vehicle_id} soft-deleted")
            return {"success": True, "message": "Vehicle deleted"}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting vehicle {vehicle_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Vehicle Maintenance
# ===========================================================================

class VehicleMaintenanceResource(Resource):
    """GET/POST /api/transport/vehicles/<vehicle_id>/maintenance"""

    def get(self, vehicle_id):
        """Get maintenance status and schedule"""
        vehicle = _vehicle_or_404(vehicle_id)

        now = datetime.now(timezone.utc)
        service_due = (
            vehicle.next_service_date and vehicle.next_service_date <= now
        )
        inspection_due = (
            vehicle.next_inspection_due and vehicle.next_inspection_due <= now
        )
        insurance_expired = (
            vehicle.insurance_expiry and vehicle.insurance_expiry <= now
        )

        return {
            "success": True,
            "data": {
                "vehicle_id": vehicle_id,
                "maintenance_status": vehicle.maintenance_status,
                "odometer_km": vehicle.odometer_reading_km,
                "service": {
                    "last_service_date": (
                        vehicle.last_service_date.isoformat()
                        if vehicle.last_service_date else None
                    ),
                    "last_service_km": vehicle.last_service_km,
                    "next_service_date": (
                        vehicle.next_service_date.isoformat()
                        if vehicle.next_service_date else None
                    ),
                    "next_service_km": vehicle.next_service_km,
                    "service_due": service_due,
                },
                "inspection": {
                    "last_inspection_date": (
                        vehicle.last_inspection_date.isoformat()
                        if vehicle.last_inspection_date else None
                    ),
                    "next_inspection_due": (
                        vehicle.next_inspection_due.isoformat()
                        if vehicle.next_inspection_due else None
                    ),
                    "inspection_due": inspection_due,
                    "roadworthiness_certificate": vehicle.roadworthiness_certificate,
                    "roadworthiness_expiry": (
                        vehicle.roadworthiness_expiry.isoformat()
                        if vehicle.roadworthiness_expiry else None
                    ),
                },
                "insurance": {
                    "provider": vehicle.insurance_provider,
                    "policy_number": vehicle.insurance_policy_number,
                    "verified": vehicle.insurance_verified,
                    "expiry": (
                        vehicle.insurance_expiry.isoformat()
                        if vehicle.insurance_expiry else None
                    ),
                    "expired": insurance_expired,
                    "coverage_amount": float(vehicle.insurance_coverage_amount or 0),
                },
                "alerts": [
                    a for a in [
                        "service_due" if service_due else None,
                        "inspection_due" if inspection_due else None,
                        "insurance_expired" if insurance_expired else None,
                    ] if a
                ],
            },
        }

    @admin_required
    def post(self, vehicle_id):
        """Record a maintenance event (service, inspection, or insurance update)"""
        vehicle = _vehicle_or_404(vehicle_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        event_type = data.get("event_type")
        now = datetime.now(timezone.utc)

        if event_type == "service":
            vehicle.last_service_date = now
            vehicle.last_service_km = data.get("odometer_km", vehicle.odometer_reading_km)
            vehicle.next_service_date = data.get("next_service_date")
            vehicle.next_service_km = data.get("next_service_km")
            vehicle.maintenance_status = "ok"
            vehicle.odometer_reading_km = data.get("odometer_km", vehicle.odometer_reading_km)

        elif event_type == "inspection":
            vehicle.last_inspection_date = now
            vehicle.next_inspection_due = data.get("next_inspection_due")
            vehicle.roadworthiness_certificate = data.get("certificate_number")
            vehicle.roadworthiness_expiry = data.get("roadworthiness_expiry")

        elif event_type == "insurance":
            vehicle.insurance_provider = data.get("provider")
            vehicle.insurance_policy_number = data.get("policy_number")
            vehicle.insurance_expiry = data.get("expiry")
            vehicle.insurance_coverage_amount = data.get("coverage_amount")
            vehicle.insurance_verified = True

        elif event_type == "odometer":
            new_reading = data.get("odometer_km")
            if new_reading and new_reading < vehicle.odometer_reading_km:
                return {"success": False, "error": "Odometer cannot decrease"}, 400
            vehicle.odometer_reading_km = new_reading

        else:
            return {"success": False, "error": f"Unknown event_type: {event_type}"}, 400

        try:
            db.session.commit()
            logger.info(f"Vehicle {vehicle_id} maintenance updated: event={event_type}")
            return {"success": True, "data": vehicle.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error recording maintenance for vehicle {vehicle_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Vehicle Assignment
# ===========================================================================

class VehicleAssignmentResource(Resource):
    """POST /api/transport/vehicles/<vehicle_id>/assign"""

    @admin_required
    def post(self, vehicle_id):
        """
        Assign or unassign a driver to/from a vehicle.
        Uses DriverVehicleHistory for a full audit trail.
        """
        vehicle = _vehicle_or_404(vehicle_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        action = data.get("action", "assign")  # assign | unassign

        if action == "assign":
            driver_id = data.get("driver_id")
            if not driver_id:
                return {"success": False, "error": "driver_id required for assign"}, 400

            driver = DriverProfile.query.filter_by(
                id=driver_id, is_deleted=False
            ).first()
            if not driver:
                return {"success": False, "error": f"Driver {driver_id} not found"}, 404

            try:
                from app.transport.models import assign_driver_to_vehicle
                assignment = assign_driver_to_vehicle(
                    driver=driver,
                    vehicle=vehicle,
                    reason=data.get("reason", "shift_start"),
                    notes=data.get("notes"),
                )
                db.session.commit()
                logger.info(f"Vehicle {vehicle_id} assigned to driver {driver_id}")
                return {
                    "success": True,
                    "data": {
                        "assignment_id": assignment.id,
                        "driver_id": driver_id,
                        "vehicle_id": vehicle_id,
                        "started_at": assignment.started_at.isoformat(),
                    },
                }
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error assigning driver {driver_id} to vehicle {vehicle_id}: {e}", exc_info=True)
                return {"success": False, "error": str(e)}, 500

        elif action == "unassign":
            current = vehicle.current_assignment
            if not current:
                return {"success": False, "error": "Vehicle has no current driver assignment"}, 404

            current.ended_at = datetime.now(timezone.utc)
            current.notes = data.get("notes", "Manual unassignment")

            try:
                db.session.commit()
                logger.info(f"Vehicle {vehicle_id} unassigned from driver {current.driver_id}")
                return {"success": True, "message": "Driver unassigned from vehicle"}
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error unassigning vehicle {vehicle_id}: {e}", exc_info=True)
                return {"success": False, "error": str(e)}, 500

        else:
            return {"success": False, "error": f"Unknown action: {action}. Use assign or unassign"}, 400