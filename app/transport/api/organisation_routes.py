# app/transport/api/organisation_routes.py
"""
AFCON360 Transport — Organisation REST API
Manages transport organisations (hotel fleets, tour operators, transport companies)
including their driver rosters, fleet stats, and verification status.
"""
from flask import request
from flask_restful import Resource
from app.extensions import db
from app.transport.models import (
    OrganisationTransportProfile, DriverProfile, Vehicle, ComplianceStatus
)
from app.admin.routes import admin_required
from app.transport.utils.helpers import paginate, filter_query, sort_query
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

ORG_SORT_FIELDS = [
    "created_at", "updated_at", "compliance_status",
    "fleet_size", "average_rating", "total_bookings", "registration_type"
]


def _org_or_404(org_id):
    return OrganisationTransportProfile.query.filter_by(
        id=org_id, is_deleted=False
    ).first_or_404()


# ===========================================================================
# Organisation List
# ===========================================================================

class OrganisationListResource(Resource):
    """GET /api/transport/organisations  — list with filters/sort/pagination
       POST /api/transport/organisations — create a new organisation profile
    """

    def get(self):
        """List organisations with filtering, sorting, and pagination"""
        query = OrganisationTransportProfile.query.filter_by(is_deleted=False)

        filters = {
            "registration_type":  request.args.get("registration_type"),
            "compliance_status":  request.args.get("compliance_status"),
            "accepts_bookings":   request.args.get("accepts_bookings", type=bool),
            "is_suspended":       request.args.get("is_suspended", type=bool),
            "license_verified":   request.args.get("license_verified", type=bool),
            "insurance_verified": request.args.get("insurance_verified", type=bool),
        }
        query = filter_query(query, OrganisationTransportProfile, filters)

        # Capability filters
        capability = request.args.get("can_provide")
        capability_map = {
            "airport":  "can_provide_airport_transfers",
            "stadium":  "can_provide_stadium_shuttles",
            "hotel":    "can_provide_hotel_transfers",
            "tours":    "can_provide_city_tours",
            "on_demand": "can_provide_on_demand",
        }
        if capability and capability in capability_map:
            query = query.filter(
                getattr(OrganisationTransportProfile, capability_map[capability]) == True
            )

        query = sort_query(query, OrganisationTransportProfile, ORG_SORT_FIELDS)
        result = paginate(query)

        return {
            "success": True,
            "data": {
                "items": [o.to_dict() for o in result["items"]],
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
        """Register a new organisation transport profile"""
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        required = ["organisation_id", "registration_type"]
        missing = [f for f in required if f not in data]
        if missing:
            return {"success": False, "error": f"Missing fields: {missing}"}, 400

        # Prevent duplicate
        existing = OrganisationTransportProfile.query.filter_by(
            organisation_id=data["organisation_id"], is_deleted=False
        ).first()
        if existing:
            return {
                "success": False,
                "error": "Organisation already has a transport profile"
            }, 409

        try:
            profile = OrganisationTransportProfile(
                organisation_id=data["organisation_id"],
                registration_type=data["registration_type"],
            )
            optional = [
                "business_license_number", "tax_identification_number",
                "transport_manager_name", "transport_manager_phone",
                "transport_manager_email", "commission_rate",
                "can_provide_airport_transfers", "can_provide_stadium_shuttles",
                "can_provide_hotel_transfers", "can_provide_city_tours",
                "can_provide_on_demand", "operational_zones",
                "languages_supported", "service_hours",
            ]
            for field in optional:
                if field in data:
                    setattr(profile, field, data[field])

            db.session.add(profile)
            db.session.commit()
            logger.info(f"Organisation transport profile created: org_id={data['organisation_id']}")
            return {"success": True, "data": profile.to_dict()}, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating organisation profile: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Organisation Detail
# ===========================================================================

class OrganisationDetailResource(Resource):
    """GET/PUT /api/transport/organisations/<org_id>"""

    def get(self, org_id):
        """Get full organisation profile including fleet and driver summary"""
        org = _org_or_404(org_id)

        # Fleet summary
        fleet_vehicles = Vehicle.query.filter(
            Vehicle.owner_type == "organisation",
            Vehicle.owner_id == org.organisation_id,
            Vehicle.is_deleted == False,
        ).all()

        available_fleet = [v for v in fleet_vehicles if v.is_available]

        return {
            "success": True,
            "data": {
                "organisation": org.to_dict(),
                "fleet_summary": {
                    "total_vehicles": len(fleet_vehicles),
                    "available_vehicles": len(available_fleet),
                    "vehicle_classes": list({v.vehicle_class.value for v in fleet_vehicles}),
                },
                "driver_summary": {
                    "total_drivers": len(org.drivers),
                    "active_drivers": sum(
                        1 for d in org.drivers
                        if d.is_online and not d.is_deleted
                    ),
                },
                "contact": {
                    "manager_name": org.transport_manager_name,
                    "manager_phone": org.transport_manager_phone,
                    "manager_email": org.transport_manager_email,
                },
                "compliance": {
                    "status": org.compliance_status.value,
                    "license_verified": org.license_verified,
                    "insurance_verified": org.insurance_verified,
                    "insurance_expiry": (
                        org.insurance_expiry.isoformat()
                        if org.insurance_expiry else None
                    ),
                },
            },
        }

    @admin_required
    def put(self, org_id):
        """Update organisation transport profile"""
        org = _org_or_404(org_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        updatable = [
            "transport_manager_name", "transport_manager_phone",
            "transport_manager_email", "commission_rate",
            "payment_terms_days", "operational_zones",
            "languages_supported", "service_hours",
            "can_provide_airport_transfers", "can_provide_stadium_shuttles",
            "can_provide_hotel_transfers", "can_provide_city_tours",
            "can_provide_on_demand", "max_group_size",
            "accepts_bookings", "is_suspended",
        ]
        for field in updatable:
            if field in data:
                setattr(org, field, data[field])

        # Compliance update
        if "compliance_status" in data:
            try:
                org.compliance_status = ComplianceStatus(data["compliance_status"])
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid compliance_status: {data['compliance_status']}"
                }, 400

        if "license_verified" in data:
            org.license_verified = data["license_verified"]

        if "insurance_verified" in data:
            org.insurance_verified = data["insurance_verified"]
            if data["insurance_verified"] and "insurance_expiry" in data:
                org.insurance_expiry = data["insurance_expiry"]

        try:
            db.session.commit()
            logger.info(f"Organisation {org_id} updated")
            return {"success": True, "data": org.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating organisation {org_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Organisation Drivers
# ===========================================================================

class OrganisationDriversResource(Resource):
    """GET/POST/DELETE /api/transport/organisations/<org_id>/drivers"""

    def get(self, org_id):
        """List all drivers belonging to this organisation"""
        org = _org_or_404(org_id)

        # Allow filtering within the org's driver list
        status_filter = request.args.get("compliance_status")
        online_filter = request.args.get("is_online", type=bool)

        drivers = org.drivers
        if status_filter:
            drivers = [d for d in drivers if d.compliance_status.value == status_filter]
        if online_filter is not None:
            drivers = [d for d in drivers if d.is_online == online_filter]

        return {
            "success": True,
            "data": {
                "organisation_id": org_id,
                "total": len(drivers),
                "drivers": [
                    d.to_dict(exclude=["license_number_encrypted"])
                    for d in drivers
                ],
            },
        }

    @admin_required
    def post(self, org_id):
        """Add a driver to this organisation"""
        org = _org_or_404(org_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        driver_id = data.get("driver_id")
        if not driver_id:
            return {"success": False, "error": "driver_id required"}, 400

        driver = DriverProfile.query.filter_by(
            id=driver_id, is_deleted=False
        ).first()
        if not driver:
            return {"success": False, "error": f"Driver {driver_id} not found"}, 404

        # Check not already in org
        if driver in org.drivers:
            return {
                "success": False,
                "error": f"Driver {driver_id} is already in this organisation"
            }, 409

        try:
            # Insert directly into the association table
            db.engine.execute(
                "INSERT INTO organisation_drivers "
                "(organisation_id, driver_id, role, is_active, joined_at) "
                "VALUES (:org_id, :driver_id, :role, true, :now)",
                {
                    "org_id": org.id,
                    "driver_id": driver_id,
                    "role": data.get("role", "driver"),
                    "now": datetime.now(timezone.utc),
                }
            )
            db.session.commit()
            logger.info(f"Driver {driver_id} added to organisation {org_id}")
            return {
                "success": True,
                "message": f"Driver {driver_id} added to organisation {org_id}",
            }
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding driver {driver_id} to org {org_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500

    @admin_required
    def delete(self, org_id):
        """Remove a driver from this organisation"""
        org = _org_or_404(org_id)
        data = request.get_json()
        driver_id = data.get("driver_id") if data else None

        if not driver_id:
            return {"success": False, "error": "driver_id required in request body"}, 400

        try:
            db.engine.execute(
                "UPDATE organisation_drivers SET is_active = false, left_at = :now "
                "WHERE organisation_id = :org_id AND driver_id = :driver_id",
                {
                    "org_id": org.id,
                    "driver_id": driver_id,
                    "now": datetime.now(timezone.utc),
                }
            )
            db.session.commit()
            logger.info(f"Driver {driver_id} removed from organisation {org_id}")
            return {"success": True, "message": f"Driver {driver_id} removed"}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing driver {driver_id} from org {org_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500