# app/transport/api/driver_routes.py
from flask import request
from flask_restful import Resource
from app.extensions import db
from app.transport.models import DriverProfile, DriverVehicleHistory, Booking
from app.admin.routes import admin_required
from app.transport.utils.helpers import paginate, filter_query, sort_query
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, func
import logging

logger = logging.getLogger(__name__)

# Fields allowed for sorting — prevents arbitrary column injection
DRIVER_SORT_FIELDS = [
    "created_at", "updated_at", "average_rating",
    "reliability_score", "safety_score", "total_trips",
    "compliance_status", "verification_tier"
]


class DriverListResource(Resource):
    """GET/POST /api/transport/drivers"""

    def get(self):
        """List drivers with filtering, sorting, and pagination"""

        # ------------------------------------------------------------------
        # Build base query
        # ------------------------------------------------------------------
        query = DriverProfile.query.filter_by(is_deleted=False)

        # ------------------------------------------------------------------
        # Filter via helpers
        # ------------------------------------------------------------------
        filters = {
            "verification_tier":  request.args.get("verification_tier"),
            "compliance_status":  request.args.get("compliance_status"),
            "is_online":          request.args.get("is_online", type=bool),
            "is_available":       request.args.get("is_available", type=bool),
            "average_rating__gte": request.args.get("min_rating", type=float),
        }
        query = filter_query(query, DriverProfile, filters)

        # ------------------------------------------------------------------
        # Search (join required — handled separately from filter_query)
        # ------------------------------------------------------------------
        search = request.args.get("search")
        if search:
            from app.identity.models.user import User
            query = query.join(DriverProfile.user).filter(
                or_(
                    DriverProfile.driver_code.ilike(f"%{search}%"),
                    User.username.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                )
            )

        # ------------------------------------------------------------------
        # Sort via helpers
        # ------------------------------------------------------------------
        query = sort_query(query, DriverProfile, DRIVER_SORT_FIELDS)

        # ------------------------------------------------------------------
        # Paginate via helpers
        # ------------------------------------------------------------------
        result = paginate(query)

        return {
            "success": True,
            "data": {
                "items": [
                    d.to_dict(exclude=["license_number_encrypted"])
                    for d in result["items"]
                ],
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
        """Create new driver"""
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        try:
            driver = DriverProfile(
                user_id=data.get("user_id"),
                driver_code=data.get("driver_code"),
                license_number=data.get("license_number"),
                languages_spoken=data.get("languages_spoken", ["en"]),
                vehicle_classes=data.get("vehicle_classes", ["comfort"]),
                service_types=data.get("service_types", ["on_demand"]),
                max_passenger_capacity=data.get("max_passenger_capacity", 4),
                max_luggage_capacity=data.get("max_luggage_capacity", 2),
                commission_rate=data.get("commission_rate", 15.00),
            )
            db.session.add(driver)
            db.session.commit()
            logger.info(f"Driver created: driver_id={driver.id}")
            return {
                "success": True,
                "data": driver.to_dict(exclude=["license_number_encrypted"]),
            }, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating driver: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


class DriverDetailResource(Resource):
    """GET/PUT/DELETE /api/transport/drivers/<int:driver_id>"""

    def get(self, driver_id):
        """Get single driver with full detail"""
        driver = DriverProfile.query.get_or_404(driver_id)

        recent_trips = (
            Booking.query
            .filter_by(assigned_driver_id=driver_id, is_deleted=False)
            .order_by(Booking.created_at.desc())
            .limit(10)
            .all()
        )

        total_earnings = (
            db.session.query(func.sum(Booking.final_price))
            .filter(
                Booking.assigned_driver_id == driver_id,
                Booking.payment_status == "captured",
                Booking.is_deleted == False,
            )
            .scalar() or 0
        )

        return {
            "success": True,
            "data": {
                "driver": driver.to_dict(exclude=["license_number_encrypted"]),
                "current_assignment": (
                    driver.current_assignment.to_dict()
                    if driver.current_assignment else None
                ),
                "recent_trips": [t.to_dict() for t in recent_trips],
                "total_earnings": float(total_earnings),
                "vehicles": [v.to_dict() for v in driver.owned_vehicles],
            },
        }

    @admin_required
    def put(self, driver_id):
        """Update driver fields"""
        driver = DriverProfile.query.get_or_404(driver_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        updatable_fields = [
            "languages_spoken", "vehicle_classes", "service_types",
            "operational_zones", "preferred_zones",
            "max_passenger_capacity", "max_luggage_capacity",
            "commission_rate", "is_online", "is_available",
        ]
        for field in updatable_fields:
            if field in data:
                setattr(driver, field, data[field])

        try:
            db.session.commit()
            logger.info(f"Driver {driver_id} updated")
            return {
                "success": True,
                "data": driver.to_dict(exclude=["license_number_encrypted"]),
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating driver {driver_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500

    @admin_required
    def delete(self, driver_id):
        """Soft delete driver"""
        driver = DriverProfile.query.get_or_404(driver_id)
        driver.is_deleted = True
        driver.deleted_at = datetime.now(timezone.utc)
        driver.is_online = False
        driver.is_available = False

        try:
            db.session.commit()
            logger.info(f"Driver {driver_id} soft-deleted")
            return {"success": True, "message": "Driver deleted"}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting driver {driver_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


class DriverVerificationResource(Resource):
    """POST /api/transport/drivers/<int:driver_id>/verification"""

    @admin_required
    def post(self, driver_id):
        """Update driver verification status"""
        driver = DriverProfile.query.get_or_404(driver_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        action = data.get("action")

        if action == "verify_license":
            driver.license_verified = True
            driver.license_verified_at = datetime.now(timezone.utc)
            driver.license_verified_by = data.get("verified_by")

        elif action == "verify_police":
            driver.police_clearance_verified = True
            driver.police_clearance_date = datetime.now(timezone.utc)
            driver.background_check_reference = data.get("reference")

        elif action == "verify_tier":
            driver.verification_tier = data.get("tier")

        elif action == "update_compliance":
            driver.compliance_status = data.get("status")

        else:
            return {"success": False, "error": f"Unknown action: {action}"}, 400

        try:
            db.session.commit()
            logger.info(f"Driver {driver_id} verification updated: action={action}")
            return {
                "success": True,
                "data": driver.to_dict(exclude=["license_number_encrypted"]),
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating verification for driver {driver_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


class DriverLocationResource(Resource):
    """GET/POST /api/transport/drivers/<int:driver_id>/location"""

    def get(self, driver_id):
        """Get driver's last known location"""
        driver = DriverProfile.query.get_or_404(driver_id)
        return {
            "success": True,
            "data": {
                "last_location": driver.last_location,
                "location_updated_at": (
                    driver.location_updated_at.isoformat()
                    if driver.location_updated_at else None
                ),
                "is_online": driver.is_online,
                "last_seen_at": (
                    driver.last_seen_at.isoformat()
                    if driver.last_seen_at else None
                ),
            },
        }

    def post(self, driver_id):
        """Update driver location (mobile app)"""
        driver = DriverProfile.query.get_or_404(driver_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        latitude = data.get("latitude")
        longitude = data.get("longitude")
        accuracy = data.get("accuracy", 0.0)

        if latitude is None or longitude is None:
            return {"success": False, "error": "latitude and longitude are required"}, 400

        try:
            driver.update_location(latitude, longitude, accuracy)
            driver.last_seen_at = datetime.now(timezone.utc)
            db.session.commit()
            return {"success": True}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating location for driver {driver_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


class DriverHistoryResource(Resource):
    """GET /api/transport/drivers/<int:driver_id>/history"""

    def get(self, driver_id):
        """Get driver's vehicle assignment history"""
        DriverProfile.query.get_or_404(driver_id)  # 404 if driver doesn't exist

        days = min(request.args.get("days", 30, type=int), 365)  # cap at 1 year
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        history = (
            DriverVehicleHistory.query
            .filter(
                DriverVehicleHistory.driver_id == driver_id,
                DriverVehicleHistory.started_at >= cutoff,
            )
            .order_by(DriverVehicleHistory.started_at.desc())
            .all()
        )

        return {
            "success": True,
            "data": [
                {
                    "id": h.id,
                    "vehicle": {
                        "id": h.vehicle.id,
                        "license_plate": h.vehicle.license_plate,
                        "make": h.vehicle.make,
                        "model": h.vehicle.model,
                    } if h.vehicle else None,
                    "started_at": h.started_at.isoformat(),
                    "ended_at": h.ended_at.isoformat() if h.ended_at else None,
                    "assignment_reason": h.assignment_reason,
                    "notes": h.notes,
                    "was_breakdown": h.was_breakdown,
                }
                for h in history
            ],
        }