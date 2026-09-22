# app/transport/api/vehicle_routes.py
"""
AFCON360 Transport - Vehicle REST API
Handles vehicle registration, verification, maintenance tracking,
and driver assignment management.
"""
from flask import request
from flask_restful import Resource
from app.extensions import db
from app.transport.models import (
    Vehicle, VehicleClass, DriverProfile, DriverVehicleHistory,
    VehicleMarketplaceListing, DriverVehicleApplication,
    ApplicationStatus, ContractStatus
)
from app.auth.decorators import admin_required
from flask_login import login_required, current_user
from app.transport.utils.helpers import paginate, filter_query, sort_query
from datetime import datetime, timezone
import logging
from app.identity.services.organization_permissions import OrganizationPermissionService
from app.identity.models.user import User
from app.identity.models.organisation import Organisation

logger = logging.getLogger(__name__)

VEHICLE_SORT_FIELDS = [
    "created_at", "updated_at", "year", "status",
    "vehicle_class", "passenger_capacity", "odometer_reading_km"
]


def _vehicle_or_404(vehicle_id):
    return Vehicle.query.filter_by(id=vehicle_id, is_deleted=False).first_or_404()


def _parse_utc_day_datetime(value, field_name):
    """Parse a maintenance/compliance date into an explicit timezone-aware UTC
    datetime.

    Accepts YYYY-MM-DD (stored as midnight UTC) or an ISO-8601 datetime
    (including a trailing Z or explicit offset; naive datetimes are assumed
    UTC to match the project convention).  Returns None for None/empty input
    and raises ValueError for anything malformed, so callers can return a
    controlled 400 instead of letting the DB session timezone interpret a raw
    string.
    """
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError(
            f"{field_name} must be a valid YYYY-MM-DD date or ISO-8601 datetime"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# ===========================================================================
# Vehicle List
# ===========================================================================

class VehicleListResource(Resource):
    """GET /api/transport/vehicles - list with filters/sort/pagination
       POST /api/transport/vehicles - register a new vehicle
    """

    @admin_required
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

    @admin_required
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

    @admin_required
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

        try:
            if event_type == "service":
                vehicle.last_service_date = now
                vehicle.last_service_km = data.get("odometer_km", vehicle.odometer_reading_km)
                vehicle.next_service_date = _parse_utc_day_datetime(
                    data.get("next_service_date"), "next_service_date"
                )
                vehicle.next_service_km = data.get("next_service_km")
                vehicle.maintenance_status = "ok"
                vehicle.odometer_reading_km = data.get("odometer_km", vehicle.odometer_reading_km)

            elif event_type == "inspection":
                vehicle.last_inspection_date = now
                vehicle.next_inspection_due = _parse_utc_day_datetime(
                    data.get("next_inspection_due"), "next_inspection_due"
                )
                vehicle.roadworthiness_certificate = data.get("certificate_number")
                vehicle.roadworthiness_expiry = _parse_utc_day_datetime(
                    data.get("roadworthiness_expiry"), "roadworthiness_expiry"
                )

            elif event_type == "insurance":
                vehicle.insurance_provider = data.get("provider")
                vehicle.insurance_policy_number = data.get("policy_number")
                vehicle.insurance_expiry = _parse_utc_day_datetime(
                    data.get("expiry"), "expiry"
                )
                vehicle.insurance_coverage_amount = data.get("coverage_amount")
                vehicle.insurance_verified = True

            elif event_type == "odometer":
                new_reading = data.get("odometer_km")
                if new_reading and new_reading < vehicle.odometer_reading_km:
                    return {"success": False, "error": "Odometer cannot decrease"}, 400
                vehicle.odometer_reading_km = new_reading

            else:
                return {"success": False, "error": f"Unknown event_type: {event_type}"}, 400
        except ValueError as ve:
            return {"success": False, "error": str(ve)}, 400

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
                    }
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


# ===========================================================================
# Vehicle Contract Request (Marketplace)
# ===========================================================================

class VehicleContractRequestResource(Resource):
    """POST /api/transport/vehicles/<vehicle_id>/request-contract"""

    @login_required
    def post(self, vehicle_id):
        """Request a contract to drive a vehicle from the marketplace.

        The acting driver is ALWAYS the authenticated ``current_user``. The
        optional ``driver_id`` request field is accepted for backward
        compatibility only and is NEVER trusted to impersonate another
        driver — the marketplace service is called with ``current_user.id``.
        The vehicle must be listed and the listing must be active + public.
        """
        from app.transport.models import VehicleMarketplaceListing
        from app.transport.services.marketplace_service import get_marketplace_service

        vehicle = _vehicle_or_404(vehicle_id)
        data = request.get_json(silent=True) or {}

        # Actor = authenticated user (client-supplied driver_id is ignored).
        driver = DriverProfile.query.filter_by(
            user_id=current_user.id, is_deleted=False
        ).first()
        if not driver:
            return {"success": False, "error": "Driver profile not found"}, 404

        # Check if driver already owns this vehicle
        if vehicle.owner_type == 'driver' and vehicle.owner_id == driver.id:
            return {"success": False, "error": "You already own this vehicle"}, 400

        # Check if vehicle is available
        if not vehicle.is_available or vehicle.is_reserved or vehicle.status != 'active':
            return {"success": False, "error": "Vehicle is not available for contract"}, 400

        # The vehicle must be listed on the marketplace (active + public).
        listing = get_marketplace_service().listing_for_vehicle(vehicle.id)
        if not listing:
            return {"success": False, "error": "Vehicle is not listed on the marketplace"}, 400

        try:
            application = get_marketplace_service().submit_application(
                current_user.id, listing.id, data
            )
        except ValueError as ve:
            db.session.rollback()
            return {"success": False, "error": str(ve)}, 400

        status_value = (
            application.status.value
            if hasattr(application.status, "value")
            else application.status
        )
        return {
            "success": True,
            "message": "Contract request sent to vehicle owner",
            "data": {
                "application_id": application.id,
                "status": status_value,
                "listing_id": application.listing_id,
            },
        }


# ===========================================================================
# Contract Acceptance (Marketplace)
# ===========================================================================

class ContractAcceptanceResource(Resource):
    """POST /api/transport/contracts/<contract_id>/accept"""

    @login_required
    def post(self, contract_id):
        """Driver accepts contract terms and activates the contract.
        
        This endpoint is called by the driver to accept a contract that
        was created after the owner approved their application.
        
        On acceptance, the contract is activated and a DriverVehicleHistory
        entry is created to establish the authoritative driver-vehicle
        relationship for Go-Live."""
        from app.transport.models import (VehicleContract, DriverProfile)
        from app.transport.services.marketplace_service import get_marketplace_service
         
        contract = VehicleContract.query.filter_by(
            id=contract_id, is_deleted=False
        ).first()
         
        if not contract:
            return {"success": False, "error": "Contract not found"}, 404
         
        # Verify the current user is the driver for this contract
        driver = DriverProfile.query.filter_by(
            user_id=current_user.id, is_deleted=False
        ).first()
        if not driver or contract.driver_id != driver.id:
            return {"success": False, "error": "You are not authorized to accept this contract"}, 403
         
        if contract.status != 'pending_signature':
            return {"success": False, "error": "Contract cannot be accepted in current state"}, 400
         
        marketplace_service = get_marketplace_service()
        success = marketplace_service.accept_contract_terms(contract_id, current_user.id)
         
        if not success:
            return {"success": False, "error": "Failed to accept contract"}, 400
         
        # Reload contract to get updated status
        contract = VehicleContract.query.filter_by(id=contract_id).first()
         
        return {
            "success": True,
            "message": "Contract accepted and activated",
            "data": {
                "contract_id": contract.id,
                "status": contract.status.value if hasattr(contract.status, 'value') else contract.status,
                "vehicle_id": contract.vehicle_id,
                "driver_id": contract.driver_id,
                "activated_at": contract.start_date.isoformat() if contract.start_date else None,
            }
        }

# ===========================================================================
# Marketplace Application Management (NEW)
# ===========================================================================

class MarketplaceApplicationListResource(Resource):
    """GET /api/transport/listings/<int:listing_id>/applications"""

    @login_required
    def get(self, listing_id):
        """Get all applications for a listing (owner only)"""
        from app.transport.services.marketplace_service import get_marketplace_service
        from app.identity.services.organization_permissions import OrganizationPermissionService
        
        # Verify ownership
        marketplace_service = get_marketplace_service()
        listing = marketplace_service.get_listing(listing_id)
        if not listing:
            return {"success": False, "error": "Listing not found"}, 404
        
        # Check ownership - canonical vehicle owner (driver/user/organisation)
        vehicle = listing.vehicle
        if vehicle.owner_type == 'driver':
            from app.transport.models import DriverProfile
            driver = DriverProfile.query.filter_by(
                user_id=current_user.id, is_deleted=False
            ).first()
            if not driver or vehicle.owner_id != driver.id:
                return {"success": False, "error": "Not authorized"}, 403
        elif vehicle.owner_type == 'user':
            if vehicle.owner_id != current_user.id:
                return {"success": False, "error": "Not authorized"}, 403
        elif vehicle.owner_type == 'organisation':
            organisation_user = db.session.get(User, current_user.id)
            if organisation_user:
                organisation = db.session.get(Organisation, vehicle.owner_id)
                if organisation:
                    if not OrganizationPermissionService.has_permission(
                        organisation_user, organisation, 'org.transport.manage'
                    ):
                        return {"success": False, "error": "Not authorized"}, 403
                else:
                    return {"success": False, "error": "Not authorized"}, 403
            else:
                return {"success": False, "error": "Not authorized"}, 403
        else:
            return {"success": False, "error": "Not authorized"}, 403
        
        # Get applications
        status = request.args.get('status')
        applications = marketplace_service.get_listing_applications(
            listing_id=listing_id,
            owner_id=listing.owner_id,
            status=status
        )
        
        return {
            "success": True,
            "data": {
                "applications": [app.to_dict() for app in applications],
                "count": len(applications)
            }
        }


class MarketplaceApplicationApproveResource(Resource):
    """POST /api/transport/applications/<int:application_id>/approve"""

    @login_required
    def post(self, application_id):
        """Approve an application and create a contract"""
        from app.transport.services.marketplace_service import get_marketplace_service
        from app.identity.services.organization_permissions import OrganizationPermissionService
        from app.transport.models import (DriverVehicleApplication, VehicleMarketplaceListing)
        from app.identity.models.user import User
        from app.identity.models.organisation import Organisation
        
        # Get application with listing for ownership check
        application = DriverVehicleApplication.query.join(VehicleMarketplaceListing).filter(
            DriverVehicleApplication.id == application_id,
            DriverVehicleApplication.is_deleted == False
        ).first()
        
        if not application:
            return {"success": False, "error": "Application not found"}, 404
        
        # Verify ownership of the listing (canonical vehicle owner)
        listing = application.listing
        vehicle = listing.vehicle
        if vehicle.owner_type == 'driver':
            from app.transport.models import DriverProfile
            driver = DriverProfile.query.filter_by(
                user_id=current_user.id, is_deleted=False
            ).first()
            if not driver or vehicle.owner_id != driver.id:
                return {"success": False, "error": "Not authorized"}, 403
        elif vehicle.owner_type == 'user':
            if vehicle.owner_id != current_user.id:
                return {"success": False, "error": "Not authorized"}, 403
        elif vehicle.owner_type == 'organisation':
            organisation_user = db.session.get(User, current_user.id)
            if organisation_user:
                organisation = db.session.get(Organisation, vehicle.owner_id)
                if organisation:
                    if not OrganizationPermissionService.has_permission(
                        organisation_user, organisation, 'org.transport.manage'
                    ):
                        return {"success": False, "error": "Not authorized"}, 403
                else:
                    return {"success": False, "error": "Not authorized"}, 403
            else:
                return {"success": False, "error": "Not authorized"}, 403
        else:
            return {"success": False, "error": "Not authorized"}, 403
        
        # Parse contract terms (optional)
        data = request.get_json(silent=True) or {}
        contract_terms = data.get('contract_terms')
        
        try:
            marketplace_service = get_marketplace_service()
            contract = marketplace_service.approve_application(
                application_id=application_id,
                owner_id=listing.owner_id,
                contract_terms=contract_terms
            )
            
            if not contract:
                return {"success": False, "error": "Failed to approve application"}, 400
            
            return {
                "success": True,
                "message": "Application approved and contract created",
                "data": {
                    "contract_id": contract.id,
                    "status": contract.status.value if hasattr(contract.status, 'value') else contract.status,
                    "application_id": application.id,
                    "listing_id": listing.id
                }
            }
        except ValueError as ve:
            return {"success": False, "error": str(ve)}, 400
        except Exception as e:
            return {"success": False, "error": str(e)}, 500


class MarketplaceApplicationRejectResource(Resource):
    """POST /api/transport/applications/<int:application_id>/reject"""

    @login_required
    def post(self, application_id):
        """Reject an application"""
        from app.transport.services.marketplace_service import get_marketplace_service
        from app.identity.services.organization_permissions import OrganizationPermissionService
        from app.transport.models import DriverVehicleApplication, VehicleMarketplaceListing
        from app.identity.models.user import User
        from app.identity.models.organisation import Organisation
        
        # Get application with listing for ownership check
        application = DriverVehicleApplication.query.join(VehicleMarketplaceListing).filter(
            DriverVehicleApplication.id == application_id,
            DriverVehicleApplication.is_deleted == False
        ).first()
        
        if not application:
            return {"success": False, "error": "Application not found"}, 404
        
        # Verify ownership of the listing (canonical vehicle owner)
        listing = application.listing
        vehicle = listing.vehicle
        if vehicle.owner_type == 'driver':
            from app.transport.models import DriverProfile
            driver = DriverProfile.query.filter_by(
                user_id=current_user.id, is_deleted=False
            ).first()
            if not driver or vehicle.owner_id != driver.id:
                return {"success": False, "error": "Not authorized"}, 403
        elif vehicle.owner_type == 'user':
            if vehicle.owner_id != current_user.id:
                return {"success": False, "error": "Not authorized"}, 403
        elif vehicle.owner_type == 'organisation':
            organisation_user = db.session.get(User, current_user.id)
            if organisation_user:
                organisation = db.session.get(Organisation, vehicle.owner_id)
                if organisation:
                    if not OrganizationPermissionService.has_permission(
                        organisation_user, organisation, 'org.transport.manage'
                    ):
                        return {"success": False, "error": "Not authorized"}, 403
                else:
                    return {"success": False, "error": "Not authorized"}, 403
            else:
                return {"success": False, "error": "Not authorized"}, 403
        else:
            return {"success": False, "error": "Not authorized"}, 403
        
        # Get reason
        data = request.get_json(silent=True) or {}
        reason = data.get('reason', 'No reason provided')
        
        try:
            marketplace_service = get_marketplace_service()
            success = marketplace_service.reject_application(
                application_id=application_id,
                owner_id=listing.owner_id,
                reason=reason
            )
            
            if not success:
                return {"success": False, "error": "Failed to reject application"}, 400
            
            return {
                "success": True,
                "message": "Application rejected",
                "data": {
                    "application_id": application.id,
                    "status": ApplicationStatus.REJECTED.value,
                    "reason": reason
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}, 500


class MarketplaceApplicationWithdrawResource(Resource):
    """POST /api/transport/applications/<int:application_id>/withdraw"""

    @login_required
    def post(self, application_id):
        """Withdraw an application (driver only)"""
        from app.transport.services.marketplace_service import get_marketplace_service
        from app.transport.models import DriverVehicleApplication, DriverProfile
        
        # Verify the current user is the driver for this application
        application = DriverVehicleApplication.query.join(DriverProfile).filter(
            DriverVehicleApplication.id == application_id,
            DriverProfile.user_id == current_user.id,
            DriverVehicleApplication.is_deleted == False
        ).first()
        
        if not application:
            return {"success": False, "error": "Application not found or not authorized"}, 404
        
        # Check if withdrawal is allowed
        if application.status not in [ApplicationStatus.PENDING, ApplicationStatus.UNDER_REVIEW]:
            return {"success": False, "error": "Cannot withdraw application in current status"}, 400
        
        try:
            marketplace_service = get_marketplace_service()
            success = marketplace_service.withdraw_application(
                application_id=application_id,
                driver_user_id=current_user.id
            )
            
            if not success:
                return {"success": False, "error": "Failed to withdraw application"}, 400
            
            return {
                "success": True,
                "message": "Application withdrawn",
                "data": {
                    "application_id": application.id,
                    "status": ApplicationStatus.WITHDRAWN.value
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}, 500