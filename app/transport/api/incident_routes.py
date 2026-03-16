# app/transport/api/incident_routes.py
"""
AFCON360 Transport — Incident REST API
Full incident lifecycle: report, investigate, assign, follow-up, resolve.
Critical incidents trigger alerts visible on the admin dashboard.
"""
from flask import request
from flask_restful import Resource
from app.extensions import db
from app.transport.models import TransportIncident, IncidentSeverity
from app.admin.routes import admin_required
from app.transport.utils.helpers import paginate, filter_query, sort_query
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

INCIDENT_SORT_FIELDS = [
    "created_at", "occurred_at", "severity", "status", "priority"
]

VALID_STATUSES = [
    "reported", "under_investigation", "action_taken", "resolved", "closed"
]


def _incident_or_404(incident_id):
    return TransportIncident.query.filter_by(
        id=incident_id, is_deleted=False
    ).first_or_404()


# ===========================================================================
# Incident List
# ===========================================================================

class IncidentListResource(Resource):
    """GET /api/transport/incidents  — list with filters/sort/pagination
       POST /api/transport/incidents — report a new incident
    """

    def get(self):
        """List incidents with filtering, sorting, and pagination"""
        query = TransportIncident.query.filter_by(is_deleted=False)

        filters = {
            "severity":          request.args.get("severity"),
            "status":            request.args.get("status"),
            "incident_type":     request.args.get("incident_type"),
            "incident_category": request.args.get("incident_category"),
            "reported_by":       request.args.get("reported_by"),
            "priority":          request.args.get("priority"),
        }
        query = filter_query(query, TransportIncident, filters)

        # Related entity filters
        booking_id = request.args.get("booking_id", type=int)
        driver_id = request.args.get("driver_id", type=int)
        vehicle_id = request.args.get("vehicle_id", type=int)
        assigned_to = request.args.get("assigned_to", type=int)

        if booking_id:
            query = query.filter(TransportIncident.booking_id == booking_id)
        if driver_id:
            query = query.filter(TransportIncident.driver_id == driver_id)
        if vehicle_id:
            query = query.filter(TransportIncident.vehicle_id == vehicle_id)
        if assigned_to:
            query = query.filter(TransportIncident.assigned_to == assigned_to)

        # Date range
        from_date = request.args.get("from_date")
        to_date = request.args.get("to_date")
        if from_date:
            query = query.filter(TransportIncident.occurred_at >= from_date)
        if to_date:
            query = query.filter(TransportIncident.occurred_at <= to_date)

        # Unresolved only flag
        if request.args.get("unresolved_only", type=bool):
            query = query.filter(
                TransportIncident.status.notin_(["resolved", "closed"])
            )

        query = sort_query(query, TransportIncident, INCIDENT_SORT_FIELDS)
        result = paginate(query)

        return {
            "success": True,
            "data": {
                "items": [i.to_dict() for i in result["items"]],
                "total":    result["total"],
                "page":     result["page"],
                "per_page": result["per_page"],
                "pages":    result["pages"],
                "has_next": result["has_next"],
                "has_prev": result["has_prev"],
            },
        }

    def post(self):
        """Report a new incident — open to drivers and users, not just admin"""
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        required = [
            "incident_type", "severity", "title",
            "description", "occurred_at", "reported_by", "reported_via"
        ]
        missing = [f for f in required if f not in data]
        if missing:
            return {"success": False, "error": f"Missing fields: {missing}"}, 400

        # Validate severity
        try:
            IncidentSeverity(data["severity"])
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid severity. Choose from: {[s.value for s in IncidentSeverity]}"
            }, 400

        try:
            incident = TransportIncident(
                incident_type=data["incident_type"],
                severity=data["severity"],
                title=data["title"],
                description=data["description"],
                occurred_at=data["occurred_at"],
                reported_by=data["reported_by"],
                reported_via=data["reported_via"],
                reported_by_id=data.get("reported_by_id"),
                incident_category=data.get("incident_category"),
                booking_id=data.get("booking_id"),
                user_id=data.get("user_id"),
                driver_id=data.get("driver_id"),
                vehicle_id=data.get("vehicle_id"),
                location=data.get("location"),
                photos=data.get("photos", []),
                videos=data.get("videos", []),
                status="reported",
                # Auto-escalate critical/high to high priority
                priority=(
                    "high"
                    if data["severity"] in [
                        IncidentSeverity.CRITICAL.value,
                        IncidentSeverity.HIGH.value
                    ]
                    else "medium"
                ),
            )
            incident.generate_reference()
            db.session.add(incident)
            db.session.commit()

            logger.warning(
                f"Incident reported: ref={incident.incident_reference}, "
                f"severity={incident.severity}, type={incident.incident_type}"
            )
            return {"success": True, "data": incident.to_dict()}, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error reporting incident: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Incident Detail
# ===========================================================================

class IncidentDetailResource(Resource):
    """GET/PUT /api/transport/incidents/<incident_id>"""

    def get(self, incident_id):
        """Get full incident detail"""
        incident = _incident_or_404(incident_id)
        return {"success": True, "data": incident.to_dict()}

    @admin_required
    def put(self, incident_id):
        """Update investigation notes, findings, and resolution details"""
        incident = _incident_or_404(incident_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        updatable = [
            "priority", "investigation_notes", "investigation_findings",
            "root_cause", "actions_taken", "preventive_measures",
            "financial_impact", "reputation_impact", "safety_impact",
            "requires_follow_up", "follow_up_date", "follow_up_notes",
            "reported_to_authorities", "authority_report_details",
            "insurance_claimed", "insurance_claim_details",
        ]
        for field in updatable:
            if field in data:
                setattr(incident, field, data[field])

        try:
            db.session.commit()
            logger.info(f"Incident {incident_id} updated")
            return {"success": True, "data": incident.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating incident {incident_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Incident Assignment
# ===========================================================================

class IncidentAssignmentResource(Resource):
    """POST /api/transport/incidents/<incident_id>/assign"""

    @admin_required
    def post(self, incident_id):
        """Assign incident to an admin/investigator and update status"""
        incident = _incident_or_404(incident_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        assigned_to = data.get("assigned_to")
        if not assigned_to:
            return {"success": False, "error": "assigned_to (user_id) required"}, 400

        incident.assigned_to = assigned_to
        incident.status = "under_investigation"

        try:
            db.session.commit()
            logger.info(f"Incident {incident_id} assigned to user {assigned_to}")
            return {"success": True, "data": incident.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning incident {incident_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Incident Follow-Up / Resolution
# ===========================================================================

class IncidentFollowUpResource(Resource):
    """POST /api/transport/incidents/<incident_id>/followup"""

    @admin_required
    def post(self, incident_id):
        """
        Record a follow-up action or resolve/close the incident.
        action: follow_up | resolve | close
        """
        incident = _incident_or_404(incident_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        action = data.get("action")
        now = datetime.now(timezone.utc)

        if action == "follow_up":
            incident.follow_up_notes = data.get("notes", "")
            incident.follow_up_date = data.get("next_follow_up_date")
            incident.status = "action_taken"

        elif action == "resolve":
            if not data.get("resolution"):
                return {"success": False, "error": "resolution details required"}, 400
            incident.resolution = data.get("resolution")
            incident.resolution_details = data.get("resolution_details")
            incident.resolved_at = now
            incident.resolved_by = data.get("resolved_by")
            incident.status = "resolved"
            incident.requires_follow_up = False

        elif action == "close":
            if incident.status != "resolved":
                return {
                    "success": False,
                    "error": "Incident must be resolved before closing",
                }, 422
            incident.status = "closed"

        else:
            return {
                "success": False,
                "error": f"Unknown action: {action}. Use follow_up, resolve, or close"
            }, 400

        try:
            db.session.commit()
            logger.info(f"Incident {incident_id} follow-up: action={action}")
            return {"success": True, "data": incident.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error on incident {incident_id} follow-up: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500