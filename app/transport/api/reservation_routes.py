"""Reservation REST resources; lifecycle decisions remain in the service."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import abort, request
from flask_login import current_user, login_required
from flask_restful import Resource
from sqlalchemy import and_, or_

from app.extensions import db
from app.transport.models import TransportReservation
from app.transport.services.reservation_service import TransportReservationService
from app.utils.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError


def _reservation_data(reservation):
    """External contract: references and domain facts only, never internal IDs."""
    return {
        "reservation_reference": reservation.reservation_reference,
        "offering_code": reservation.offering_code,
        "window_start": reservation.window_start.isoformat(),
        "window_end": reservation.window_end.isoformat(),
        "required_quantity": reservation.required_quantity,
        "mode": reservation.mode,
        "state": reservation.state,
        "obligation_state": reservation.obligation_state,
        "payment_method": reservation.payment_method,
        "payment_timing": reservation.payment_timing,
        "deposit_required": reservation.deposit_required,
        "deposit_amount": str(reservation.deposit_amount) if reservation.deposit_amount is not None else None,
        "deposit_currency": reservation.deposit_currency,
        "deposit_due_at": reservation.deposit_due_at.isoformat() if reservation.deposit_due_at else None,
        "required_total_amount": str(reservation.required_total_amount) if reservation.required_total_amount is not None else None,
        "amount_received": str(reservation.amount_received or 0),
    }


def _parse_datetime(value, field):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"{field} must be timezone-aware")
    return parsed


def _error_response(exc):
    if isinstance(exc, PermissionError):
        return {"success": False, "error": str(exc)}, 403
    if isinstance(exc, NotFoundError):
        return {"success": False, "error": str(exc)}, 404
    if isinstance(exc, ConflictError):
        return {"success": False, "error": str(exc)}, 409
    return {"success": False, "error": str(exc)}, 400


class ReservationListResource(Resource):
    @login_required
    def get(self):
        # Owners can list their own rows. Organisation rows are filtered in SQL
        # through Identity's active-membership relationship, never in Python.
        from app.identity.models.organisation_member import (
            OrganisationMember, OrgMemberPermission, OrgRolePermission, OrgUserRole,
        )
        from app.identity.models.roles_permission import Permission
        member = db.session.query(OrganisationMember.id).filter(
            OrganisationMember.user_id == current_user.id,
            OrganisationMember.organisation_id == TransportReservation.on_behalf_of_organisation_id,
            OrganisationMember.is_active.is_(True),
            OrganisationMember.is_deleted.is_(False),
        ).correlate(TransportReservation)
        permission = Permission.name == "org.manage_transport"
        direct_grant = db.session.query(OrgMemberPermission.id).join(
            Permission, Permission.id == OrgMemberPermission.permission_id
        ).filter(OrgMemberPermission.member_id == OrganisationMember.id,
                 OrgMemberPermission.granted.is_(True), permission).correlate(OrganisationMember).exists()
        role_grant = db.session.query(OrgUserRole.id).join(
            OrgRolePermission, OrgRolePermission.org_role_id == OrgUserRole.role_id
        ).join(Permission, Permission.id == OrgRolePermission.permission_id).filter(
            OrgUserRole.organisation_member_id == OrganisationMember.id, permission
        ).correlate(OrganisationMember).exists()
        direct_deny = db.session.query(OrgMemberPermission.id).join(
            Permission, Permission.id == OrgMemberPermission.permission_id
        ).filter(OrgMemberPermission.member_id == OrganisationMember.id,
                 OrgMemberPermission.granted.is_(False), permission).correlate(OrganisationMember).exists()
        organisation_access = member.filter(or_(direct_grant, role_grant), ~direct_deny).exists()
        query = TransportReservation.query.filter(
            TransportReservation.is_deleted.is_(False),
            or_(TransportReservation.reserving_user_id == current_user.id, organisation_access),
        ).order_by(TransportReservation.created_at.desc())
        return {"success": True, "data": {"items": [_reservation_data(row) for row in query.all()]}}

    @login_required
    def post(self):
        data = request.get_json(silent=True) or {}
        required = ("offering_code", "provider_type", "provider_id", "window_start", "window_end",
                    "required_quantity", "mode", "payment_timing")
        missing = [name for name in required if name not in data]
        if missing:
            return {"success": False, "error": f"Missing fields: {missing}"}, 400
        idempotency_key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
        if not idempotency_key:
            return {"success": False, "error": "Idempotency-Key is required"}, 400
        try:
            estimate = data.get("estimated_value")
            reservation = TransportReservationService.create_reservation(
                actor=current_user, offering_code=data["offering_code"], provider_type=data["provider_type"],
                provider_id=int(data["provider_id"]), window_start=_parse_datetime(data["window_start"], "window_start"),
                window_end=_parse_datetime(data["window_end"], "window_end"), required_quantity=int(data["required_quantity"]),
                mode=data["mode"], idempotency_key=idempotency_key, payment_method=data.get("payment_method"),
                payment_timing=data.get("payment_timing"), commercial_policy_ref=data.get("commercial_policy_ref"),
                on_behalf_of_organisation_id=data.get("on_behalf_of_organisation_id"),
                event_id=data.get("event_id"), context_source=data.get("context_source"), context_ref=data.get("context_ref"),
                specific_vehicle_ids=data.get("specific_vehicle_ids"),
                estimated_value=Decimal(str(estimate)) if estimate is not None else None,
            )
            return {"success": True, "data": _reservation_data(reservation)}, 201
        except (ValidationError, PermissionError, NotFoundError, ConflictError, ValueError, InvalidOperation) as exc:
            return _error_response(exc)


class ReservationDetailResource(Resource):
    @login_required
    def get(self, reservation_reference):
        reservation = TransportReservation.query.filter_by(
            reservation_reference=reservation_reference, is_deleted=False
        ).first()
        if reservation is None:
            abort(404)
        if not TransportReservationService.actor_can_access_reservation(actor=current_user, reservation=reservation):
            abort(403)
        return {"success": True, "data": _reservation_data(reservation)}


class ReservationCancelResource(Resource):
    @login_required
    def post(self, reservation_reference):
        reservation = TransportReservation.query.filter_by(
            reservation_reference=reservation_reference, is_deleted=False
        ).first()
        if reservation is None:
            abort(404)
        try:
            result = TransportReservationService.cancel_reservation(
                reservation_id=reservation.id, actor=current_user,
                reason=(request.get_json(silent=True) or {}).get("reason"),
            )
            return {"success": True, "data": _reservation_data(result)}
        except (PermissionError, ConflictError, ValidationError) as exc:
            return _error_response(exc)
