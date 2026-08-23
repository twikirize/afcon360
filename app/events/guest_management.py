# app/events/guest_management.py
"""
Event Guest Operations — Guest Management, Journey, and Communication.

Implements the account-independent guest lifecycle described in the Event
Guest Operations permission model:

    Guest (EventGuest)  ->  Registration  ->  Assignment  ->  Journey
                                    |
                                    +-- notify / archive / link / merge

Design invariants honoured here:
  * The guest is identified primarily by ``EventGuest`` / ``EventRegistration``,
    NOT by ``User``.  A guest does NOT need an AFCON360 account.
  * Every mutating action is gated by a granular permission from
    ``app.events.permissions`` (guest.create, guest.edit, guest.archive,
    guest.import, guest.link_account, guest.merge, journey.view,
    notify.guest, notify.bulk).
  * This module only orchestrates; it does not own accommodation, transport,
    or wallet records.
  * No new schema is introduced — everything uses the existing EventGuest /
    EventRegistration / EventAssignment models.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Tuple

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.events.models import (
    Event, EventGuest, EventRegistration, EventGroup, EventGroupMember,
)
from app.events.assignment import _event_for_ref
from app.events.permissions import (
    has_guest_operation_permission,
    can_create_guest,
    can_edit_guest,
    can_archive_guest,
    can_import_guests,
    can_link_guest_account,
    can_merge_guest,
    can_view_journey,
    can_notify_guest,
    can_notify_bulk,
    can_create_group,
    can_view_group,
    can_edit_group,
    can_bulk_assign_group,
    can_manage_vip,
)
from app.events.guest_coordination_service import (
    GuestCoordinationService,
    CoordinationError,
)
from app.events.attendee_accounts import find_or_create_attendee_user

guest_management_bp = Blueprint('event_guest_management', __name__)


@guest_management_bp.errorhandler(CoordinationError)
def _handle_coordination_error(error: CoordinationError):
    """Return coordination failures as JSON rather than a 500."""
    return jsonify({'success': False, 'code': error.code, 'error': error.message}), 400


# ============================================================================
# AUDIT HELPER
# ============================================================================

def _audit(event, actor, action: str, guest_ref: str, *, status: str, detail=None) -> None:
    """Best-effort forensic audit for guest-management actions."""
    try:
        from app.audit.forensic_audit import ForensicAuditService

        entity_id = f"{event.public_id}:guest:{guest_ref}"
        audit_id = ForensicAuditService.log_attempt(
            entity_type="event_guest",
            entity_id=entity_id,
            action=action,
            user_id=None,
            details={
                "event_ref": str(event.public_id),
                "guest_ref": guest_ref,
                "actor_ref": getattr(actor, "public_id", None),
                "detail": detail,
            },
            correlation_id=entity_id,
        )
        if status == "completed":
            ForensicAuditService.log_completion(
                audit_id=audit_id,
                result_details={"event_ref": str(event.public_id), "guest_ref": guest_ref},
            )
    except Exception:  # pragma: no cover - audit must never break the request
        current_app.logger.exception("guest management audit failed")


def _require(event, permission: str) -> Tuple[bool, str]:
    """Return (True, '') if the current user holds the granular permission."""
    return has_guest_operation_permission(current_user, event, permission)


def _resolve_guest(event, guest_ref: str) -> EventGuest:
    """Resolve a non-deleted EventGuest by guest_ref (account-independent)."""
    guest = EventGuest.query.filter_by(
        guest_ref=str(guest_ref), is_deleted=False
    ).first()
    if guest is None:
        raise CoordinationError("GUEST_NOT_FOUND", "Guest not found for this event")
    return guest


def _event_registration_for_guest(event, guest: EventGuest) -> EventRegistration | None:
    """Find the event-scoped registration that links this guest."""
    registration = EventRegistration.query.filter_by(
        event_id=event.id, guest_id=guest.id, is_deleted=False
    ).first()
    if registration is None:
        registration = EventRegistration.query.filter_by(
            event_id=event.id, email=guest.email, is_deleted=False
        ).first()
    return registration


# ============================================================================
# GUEST MANAGEMENT
# ============================================================================

@guest_management_bp.route('/<event_ref>/guests', methods=['POST'])
@login_required
def create_guest(event_ref):
    """Create a manual guest record (account-independent identity)."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'guest.create')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GUEST_FORBIDDEN', 'error': message}), 403

    data = request.get_json(silent=True) or {}
    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip()
    if not full_name or not email:
        return jsonify({'success': False, 'code': 'INVALID_GUEST',
                        'error': 'full_name and email are required'}), 400

    guest = EventGuest(
        full_name=full_name,
        email=email,
        phone=(data.get('phone') or '').strip() or None,
        nationality=(data.get('nationality') or '').strip() or None,
    )
    db.session.add(guest)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'GUEST_CREATE_FAILED',
                        'error': str(exc)}), 400

    _audit(event, current_user, 'guest_create', guest.guest_ref, status='completed')
    return jsonify({
        'success': True,
        'guest_ref': guest.guest_ref,
        'full_name': guest.full_name,
        'email': guest.email,
    }), 201


@guest_management_bp.route('/<event_ref>/guests/<guest_ref>', methods=['PUT'])
@login_required
def edit_guest(event_ref, guest_ref):
    """Update guest contact / identity details."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'guest.edit')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GUEST_FORBIDDEN', 'error': message}), 403

    guest = _resolve_guest(event, guest_ref)
    data = request.get_json(silent=True) or {}
    changed = {}
    for field in ('full_name', 'email', 'phone', 'nationality'):
        value = data.get(field)
        if value is not None:
            value = str(value).strip()
            if field in ('phone', 'nationality') and value == '':
                value = None
            if getattr(guest, field) != value:
                setattr(guest, field, value)
                changed[field] = value
    if not changed:
        return jsonify({'success': True, 'guest_ref': guest.guest_ref, 'changed': False})
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'GUEST_EDIT_FAILED',
                        'error': str(exc)}), 400

    _audit(event, current_user, 'guest_edit', guest.guest_ref,
           status='completed', detail=changed)
    return jsonify({'success': True, 'guest_ref': guest.guest_ref, 'changed': True})


@guest_management_bp.route('/<event_ref>/guests/<guest_ref>/archive', methods=['POST'])
@login_required
def archive_guest(event_ref, guest_ref):
    """Archive (soft-delete) a guest from the active list."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'guest.archive')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GUEST_FORBIDDEN', 'error': message}), 403

    guest = _resolve_guest(event, guest_ref)
    if guest.is_deleted:
        return jsonify({'success': True, 'guest_ref': guest.guest_ref, 'archived': False})
    guest.is_deleted = True
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'GUEST_ARCHIVE_FAILED',
                        'error': str(exc)}), 400

    _audit(event, current_user, 'guest_archive', guest.guest_ref, status='completed')
    return jsonify({'success': True, 'guest_ref': guest.guest_ref, 'archived': True})


@guest_management_bp.route('/<event_ref>/guests/import', methods=['POST'])
@login_required
def import_guests(event_ref):
    """Bulk import guests from a CSV payload.

    Accepted JSON body:
        {"csv": "full_name,email,phone,nationality\\nAlice,alice@x.com,..."}
    or multipart file upload with key ``file``.
    """
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'guest.import')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GUEST_FORBIDDEN', 'error': message}), 403

    csv_text = ''
    if request.is_json:
        csv_text = (request.get_json(silent=True) or {}).get('csv', '') or ''
    if not csv_text and 'file' in request.files:
        csv_text = request.files['file'].stream.read().decode('utf-8', 'ignore')
    if not csv_text:
        return jsonify({'success': False, 'code': 'INVALID_IMPORT',
                        'error': 'No CSV data provided'}), 400

    reader = csv.DictReader(io.StringIO(csv_text))
    succeeded = 0
    failed = 0
    errors = []
    for index, row in enumerate(reader, start=2):
        full_name = (row.get('full_name') or '').strip()
        email = (row.get('email') or '').strip()
        if not full_name or not email:
            failed += 1
            errors.append({'row': index, 'error': 'full_name and email required'})
            continue
        guest = EventGuest(
            full_name=full_name,
            email=email,
            phone=(row.get('phone') or '').strip() or None,
            nationality=(row.get('nationality') or '').strip() or None,
        )
        db.session.add(guest)
        succeeded += 1
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'GUEST_IMPORT_FAILED',
                        'error': str(exc)}), 400

    _audit(event, current_user, 'guest_import', 'bulk',
           status='completed', detail={'succeeded': succeeded, 'failed': failed})
    return jsonify({
        'success': True,
        'succeeded': succeeded,
        'failed': failed,
        'errors': errors[:20],
    }), 200 if failed == 0 else 207


@guest_management_bp.route('/<event_ref>/guests/<guest_ref>/link', methods=['POST'])
@login_required
def link_guest_account(event_ref, guest_ref):
    """Link a guest to an AFCON360 account (existing or newly created)."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'guest.link_account')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GUEST_FORBIDDEN', 'error': message}), 403

    guest = _resolve_guest(event, guest_ref)
    data = request.get_json(silent=True) or {}
    create_account = bool(data.get('create_account', False))
    email = (data.get('email') or guest.email or '').strip()

    user_id, error = find_or_create_attendee_user(
        email=email,
        name=guest.full_name,
        phone=guest.phone,
        create_guest_account=create_account,
    )
    if user_id is None:
        return jsonify({'success': False, 'code': 'GUEST_LINK_FAILED',
                        'error': error or 'No account found and creation not requested'}), 400

    guest.user_id = user_id
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'GUEST_LINK_FAILED',
                        'error': str(exc)}), 400

    _audit(event, current_user, 'guest_link', guest.guest_ref,
           status='completed', detail={'user_id': user_id})
    return jsonify({'success': True, 'guest_ref': guest.guest_ref, 'user_id': user_id})


@guest_management_bp.route('/<event_ref>/guests/<guest_ref>/merge', methods=['POST'])
@login_required
def merge_guest(event_ref, guest_ref):
    """Merge a no-account guest into an existing user account."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'guest.merge')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GUEST_FORBIDDEN', 'error': message}), 403

    guest = _resolve_guest(event, guest_ref)
    data = request.get_json(silent=True) or {}
    target_user_id = data.get('target_user_id')
    target_email = (data.get('target_email') or '').strip()

    if not target_user_id and not target_email:
        return jsonify({'success': False, 'code': 'INVALID_MERGE',
                        'error': 'target_user_id or target_email is required'}), 400

    from app.identity.models.user import User  # local import to avoid cycle at module load

    target = None
    if target_user_id:
        target = db.session.get(User, int(target_user_id))
    elif target_email:
        target = User.query.filter_by(email=target_email, is_deleted=False).first()
    if target is None:
        return jsonify({'success': False, 'code': 'TARGET_USER_NOT_FOUND',
                        'error': 'Target user account not found'}), 404

    guest.user_id = target.id
    # Re-point any event-scoped registrations that referenced this guest.
    EventRegistration.query.filter_by(guest_id=guest.id).update(
        {'user_id': target.id, 'attendee_user_id': target.id}
    )
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'GUEST_MERGE_FAILED',
                        'error': str(exc)}), 400

    _audit(event, current_user, 'guest_merge', guest.guest_ref,
           status='completed', detail={'user_id': target.id})
    return jsonify({'success': True, 'guest_ref': guest.guest_ref, 'user_id': target.id})


# ============================================================================
# GUEST JOURNEY
# ============================================================================

@guest_management_bp.route('/<event_ref>/guests/<guest_ref>/journey', methods=['GET'])
@login_required
def guest_journey(event_ref, guest_ref):
    """Aggregated, provider-agnostic journey view for one guest."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'journey.view')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GUEST_FORBIDDEN', 'error': message}), 403

    guest = _resolve_guest(event, guest_ref)
    registration = _event_registration_for_guest(event, guest)
    if registration is None:
        return jsonify({
            'success': True,
            'guest_ref': guest.guest_ref,
            'full_name': guest.full_name,
            'email': guest.email,
            'registration': None,
            'capabilities': {
                'accommodation': {'available': False, 'status': 'unregistered'},
                'transport': {'available': False, 'status': 'unregistered'},
            },
            'exceptions': [],
        })

    try:
        journey = GuestCoordinationService.guest_journey(
            event, current_user, registration.registration_ref
        )
    except CoordinationError as error:
        return jsonify({'success': False, 'code': error.code, 'error': error.message}), 403
    return jsonify({'success': True, **journey})


# ============================================================================
# COMMUNICATION
# ============================================================================

def _send_guest_notification(guest: EventGuest, title: str, message: str) -> dict:
    """Best-effort multi-channel delivery; returns a per-guest result dict."""
    from app.notifications.services import NotificationService

    channels = ['email']
    if guest.user_id:
        channels.append('in_app')
    try:
        NotificationService.send(
            user_id=guest.user_id,
            notification_type='system_alert',
            title=title,
            message=message,
            channels=channels,
            email=guest.email,
            module='events',
        )
        return {'guest_ref': guest.guest_ref, 'success': True}
    except Exception as exc:  # pragma: no cover - delivery is best effort
        current_app.logger.warning("guest notify failed for %s: %s", guest.guest_ref, exc)
        return {'guest_ref': guest.guest_ref, 'success': False, 'error': str(exc)}


@guest_management_bp.route('/<event_ref>/guests/<guest_ref>/notify', methods=['POST'])
@login_required
def notify_guest(event_ref, guest_ref):
    """Send an individual guest notification / email."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'notify.guest')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GUEST_FORBIDDEN', 'error': message}), 403

    guest = _resolve_guest(event, guest_ref)
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or 'Event notification').strip()
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'success': False, 'code': 'INVALID_NOTIFY',
                        'error': 'message is required'}), 400

    result = _send_guest_notification(guest, title, message)
    _audit(event, current_user, 'guest_notify', guest.guest_ref, status='completed')
    status = 200 if result['success'] else 207
    return jsonify({'success': result['success'], 'result': result}), status


@guest_management_bp.route('/<event_ref>/guests/notify', methods=['POST'])
@login_required
def notify_bulk(event_ref):
    """Bulk notify a set of guests (by guest_ref list or event-wide)."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'notify.bulk')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GUEST_FORBIDDEN', 'error': message}), 403

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or 'Event notification').strip()
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'success': False, 'code': 'INVALID_NOTIFY',
                        'error': 'message is required'}), 400

    guest_refs = data.get('guest_refs') or []
    if guest_refs:
        guests = EventGuest.query.filter(
            EventGuest.guest_ref.in_([str(r) for r in guest_refs]),
            EventGuest.is_deleted.is_(False),
        ).all()
    else:
        # Event-wide broadcast to every guest linked to this event.
        reg_subq = db.session.query(EventRegistration.guest_id).filter(
            EventRegistration.event_id == event.id,
            EventRegistration.is_deleted.is_(False),
        )
        guests = EventGuest.query.filter(
            EventGuest.id.in_(reg_subq), EventGuest.is_deleted.is_(False)
        ).all()

    results = [_send_guest_notification(guest, title, message) for guest in guests]
    succeeded = sum(1 for r in results if r['success'])
    _audit(event, current_user, 'guest_notify_bulk', 'bulk',
           status='completed', detail={'succeeded': succeeded, 'total': len(results)})
    return jsonify({
        'success': succeeded == len(results) and len(results) > 0,
        'succeeded': succeeded,
        'failed': len(results) - succeeded,
        'results': results[:50],
    }), 200 if (succeeded == len(results) and results) else 207


# ============================================================================
# EVENT GROUPS / DELEGATIONS
# ============================================================================
# Groups are scoped collections of attendees used for coordination (e.g. a
# national delegation or a VIP party).  They never grant attendees any
# organiser authority.  Every mutation is gated by a granular permission and
# emits a forensic audit fact.  Membership is recorded in EventGroupMember.

def _audit_group(event, actor, action: str, group_ref: str, *, status: str, detail=None) -> None:
    """Best-effort forensic audit for event-group actions."""
    try:
        from app.audit.forensic_audit import ForensicAuditService

        entity_id = f"{event.public_id}:group:{group_ref}"
        audit_id = ForensicAuditService.log_attempt(
            entity_type="event_group",
            entity_id=entity_id,
            action=action,
            user_id=None,
            details={
                "event_ref": str(event.public_id),
                "group_ref": group_ref,
                "actor_ref": getattr(actor, "public_id", None),
                "detail": detail,
            },
            correlation_id=entity_id,
        )
        if status == "completed":
            ForensicAuditService.log_completion(
                audit_id=audit_id,
                result_details={"event_ref": str(event.public_id), "group_ref": group_ref},
            )
    except Exception:  # pragma: no cover - audit must never break the request
        current_app.logger.exception("event group audit failed")


def _resolve_group(event, group_ref: str) -> EventGroup:
    """Resolve a non-deleted EventGroup by int id or public_id."""
    ref = str(group_ref).strip()
    query = EventGroup.query.filter_by(event_id=event.id, is_deleted=False)
    group = query.filter_by(public_id=ref).first()
    if group is None and ref.isdigit():
        group = query.filter_by(id=int(ref)).first()
    if group is None:
        raise CoordinationError("GROUP_NOT_FOUND", "Group not found for this event")
    return group


def _resolve_member(group: EventGroup, member_id: str) -> EventGroupMember:
    """Resolve an EventGroupMember by its int id within this group."""
    try:
        member_id_int = int(member_id)
    except (TypeError, ValueError):
        raise CoordinationError("GROUP_MEMBER_NOT_FOUND", "Member not found in this group")
    member = EventGroupMember.query.filter_by(
        group_id=group.id, id=member_id_int
    ).first()
    if member is None:
        raise CoordinationError("GROUP_MEMBER_NOT_FOUND", "Member not found in this group")
    return member


def _resolve_registration(event, registration_ref: str) -> EventRegistration:
    """Resolve an EventRegistration by registration_ref for this event."""
    ref = str(registration_ref).strip()
    registration = EventRegistration.query.filter_by(
        event_id=event.id, is_deleted=False, registration_ref=ref
    ).first()
    if registration is None:
        raise CoordinationError("REGISTRATION_NOT_FOUND", "Registration not found for this event")
    return registration


def _group_summary(group: EventGroup) -> dict:
    """Serialise a group without exposing internal ids."""
    return {
        'public_id': group.public_id,
        'id': group.id,
        'name': group.name,
        'description': group.description,
        'group_type': group.group_type,
        'created_by_id': group.created_by_id,
        'member_count': EventGroupMember.query.filter_by(
            group_id=group.id, is_deleted=False
        ).count(),
    }


def _member_summary(member: EventGroupMember) -> dict:
    """Serialise a group member without exposing internal ids."""
    registration_ref = None
    guest_ref = None
    if member.registration is not None:
        registration_ref = member.registration.registration_ref
    if member.guest is not None:
        guest_ref = member.guest.guest_ref
    return {
        'member_id': member.id,
        'registration_ref': registration_ref,
        'guest_ref': guest_ref,
        'is_vip': member.is_vip,
        'added_by_id': member.added_by_id,
    }


@guest_management_bp.route('/<event_ref>/groups', methods=['POST'])
@login_required
def create_group(event_ref):
    """Create a new event group / delegation."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'group.create')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GROUP_FORBIDDEN', 'error': message}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'code': 'INVALID_GROUP',
                        'error': 'name is required'}), 400

    group = EventGroup(
        event_id=event.id,
        name=name,
        description=(data.get('description') or '').strip() or None,
        group_type=(data.get('group_type') or 'delegation').strip() or 'delegation',
        created_by_id=current_user.id,
    )
    db.session.add(group)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'GROUP_CREATE_FAILED',
                        'error': str(exc)}), 400

    _audit_group(event, current_user, 'group_create', group.public_id, status='completed')
    return jsonify({
        'success': True,
        'public_id': group.public_id,
        'id': group.id,
        'name': group.name,
        'group_type': group.group_type,
    }), 201


@guest_management_bp.route('/<event_ref>/groups', methods=['GET'])
@login_required
def list_groups(event_ref):
    """List all groups for an event."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'group.view')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GROUP_FORBIDDEN', 'error': message}), 403

    groups = EventGroup.query.filter_by(
        event_id=event.id, is_deleted=False
    ).order_by(EventGroup.name).all()
    return jsonify({'success': True, 'groups': [_group_summary(g) for g in groups]})


@guest_management_bp.route('/<event_ref>/groups/<group_ref>', methods=['GET'])
@login_required
def get_group(event_ref, group_ref):
    """Get a group and its members."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'group.view')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GROUP_FORBIDDEN', 'error': message}), 403

    group = _resolve_group(event, group_ref)
    members = EventGroupMember.query.filter_by(
        group_id=group.id, is_deleted=False
    ).order_by(EventGroupMember.id).all()
    payload = _group_summary(group)
    payload['members'] = [_member_summary(m) for m in members]
    return jsonify({'success': True, **payload})


@guest_management_bp.route('/<event_ref>/groups/<group_ref>', methods=['PUT'])
@login_required
def edit_group(event_ref, group_ref):
    """Rename / re-describe a group."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'group.edit')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GROUP_FORBIDDEN', 'error': message}), 403

    group = _resolve_group(event, group_ref)
    data = request.get_json(silent=True) or {}
    changed = {}
    for field in ('name', 'description', 'group_type'):
        value = data.get(field)
        if value is not None:
            value = str(value).strip()
            if field == 'description' and value == '':
                value = None
            if field == 'group_type' and value == '':
                value = 'delegation'
            if getattr(group, field) != value:
                setattr(group, field, value)
                changed[field] = value
    if not changed:
        return jsonify({'success': True, 'public_id': group.public_id, 'changed': False})
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'GROUP_EDIT_FAILED',
                        'error': str(exc)}), 400

    _audit_group(event, current_user, 'group_edit', group.public_id,
                 status='completed', detail=changed)
    return jsonify({'success': True, 'public_id': group.public_id, 'changed': True})


@guest_management_bp.route('/<event_ref>/groups/<group_ref>', methods=['DELETE'])
@login_required
def delete_group(event_ref, group_ref):
    """Soft-delete a group (members are cascade-soft-deleted via is_deleted)."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'group.edit')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GROUP_FORBIDDEN', 'error': message}), 403

    group = _resolve_group(event, group_ref)
    if group.is_deleted:
        return jsonify({'success': True, 'public_id': group.public_id, 'deleted': False})
    try:
        EventGroupMember.query.filter_by(group_id=group.id).update({'is_deleted': True})
        group.is_deleted = True
        group.deleted_at = datetime.now(timezone.utc)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'GROUP_DELETE_FAILED',
                        'error': str(exc)}), 400

    _audit_group(event, current_user, 'group_delete', group.public_id, status='completed')
    return jsonify({'success': True, 'public_id': group.public_id, 'deleted': True})


@guest_management_bp.route('/<event_ref>/groups/<group_ref>/members', methods=['POST'])
@login_required
def add_group_member(event_ref, group_ref):
    """Add a member to a group by registration_ref or guest_ref (deduped)."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'group.edit')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GROUP_FORBIDDEN', 'error': message}), 403

    group = _resolve_group(event, group_ref)
    data = request.get_json(silent=True) or {}
    registration_ref = (data.get('registration_ref') or '').strip()
    guest_ref = (data.get('guest_ref') or '').strip()
    if not registration_ref and not guest_ref:
        return jsonify({'success': False, 'code': 'INVALID_MEMBER',
                        'error': 'registration_ref or guest_ref is required'}), 400

    registration = None
    guest = None
    if registration_ref:
        registration = _resolve_registration(event, registration_ref)
        guest = registration.guest
    else:
        guest = _resolve_guest(event, guest_ref)

    existing = EventGroupMember.query.filter_by(group_id=group.id)
    if registration is not None:
        existing = existing.filter_by(registration_id=registration.id)
    else:
        existing = existing.filter_by(guest_id=guest.id)
    existing = existing.first()
    if existing is not None:
        if existing.is_deleted:
            existing.is_deleted = False
            existing.deleted_at = None
            existing.is_vip = bool(data.get('is_vip', False))
            existing.added_by_id = current_user.id
            try:
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                return jsonify({'success': False, 'code': 'MEMBER_ADD_FAILED',
                                'error': str(exc)}), 400
            _audit_group(event, current_user, 'group_member_add', group.public_id,
                         status='completed', detail={'member_id': existing.id, 'reactivated': True})
            return jsonify({'success': True, 'member_id': existing.id,
                            'is_vip': existing.is_vip, 'reactivated': True}), 200
        return jsonify({'success': False, 'code': 'MEMBER_EXISTS',
                        'error': 'Member already in group'}), 409

    is_vip = bool(data.get('is_vip', False))
    member = EventGroupMember(
        group_id=group.id,
        registration_id=registration.id if registration else None,
        guest_id=guest.id if guest else None,
        is_vip=is_vip,
        added_by_id=current_user.id,
    )
    db.session.add(member)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'MEMBER_ADD_FAILED',
                        'error': str(exc)}), 400

    _audit_group(event, current_user, 'group_member_add', group.public_id,
                 status='completed', detail={'member_id': member.id})
    return jsonify({'success': True, 'member_id': member.id,
                    'is_vip': member.is_vip}), 201


@guest_management_bp.route('/<event_ref>/groups/<group_ref>/members/<member_id>', methods=['DELETE'])
@login_required
def remove_group_member(event_ref, group_ref, member_id):
    """Remove a member from a group (soft-delete the membership)."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'group.edit')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GROUP_FORBIDDEN', 'error': message}), 403

    group = _resolve_group(event, group_ref)
    member = _resolve_member(group, member_id)
    if member.is_deleted:
        return jsonify({'success': True, 'member_id': member.id, 'removed': False})
    member.is_deleted = True
    member.deleted_at = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'MEMBER_REMOVE_FAILED',
                        'error': str(exc)}), 400

    _audit_group(event, current_user, 'group_member_remove', group.public_id,
                 status='completed', detail={'member_id': member.id})
    return jsonify({'success': True, 'member_id': member.id, 'removed': True})


@guest_management_bp.route('/<event_ref>/groups/<group_ref>/bulk-assign', methods=['POST'])
@login_required
def group_bulk_assign(event_ref, group_ref):
    """Bulk-assign every member with a linked registration to a booking.

    Body: {"capability": "accommodation"|"transport", "booking_ref": "..."}.
    Delegates to GuestCoordinationService so accommodation/transport inventory
    and eligibility decisions remain owned by those modules.  Returns a
    per-item result list; HTTP 207 when any item fails.
    """
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'group.bulk_assign')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GROUP_FORBIDDEN', 'error': message}), 403

    group = _resolve_group(event, group_ref)
    data = request.get_json(silent=True) or {}
    capability = (data.get('capability') or '').strip()
    booking_ref = (data.get('booking_ref') or '').strip()
    if capability not in ('accommodation', 'transport'):
        return jsonify({'success': False, 'code': 'INVALID_CAPABILITY',
                        'error': "capability must be 'accommodation' or 'transport'"}), 400
    if not booking_ref:
        return jsonify({'success': False, 'code': 'INVALID_BOOKING',
                        'error': 'booking_ref is required'}), 400

    results = []
    for member in group.members:
        if member.is_deleted:
            continue
        if member.registration_id is None or member.registration is None:
            results.append({'member_id': member.id, 'success': False,
                            'code': 'NO_REGISTRATION',
                            'error': 'Member has no linked registration'})
            continue
        registration_ref = member.registration.registration_ref
        try:
            if capability == 'accommodation':
                GuestCoordinationService.assign_accommodation(
                    event, current_user, registration_ref, booking_ref
                )
            else:
                GuestCoordinationService.assign_transport(
                    event, current_user, registration_ref, booking_ref
                )
            results.append({'member_id': member.id, 'registration_ref': registration_ref,
                            'success': True})
        except CoordinationError as error:
            results.append({'member_id': member.id, 'registration_ref': registration_ref,
                            'success': False, 'code': error.code, 'error': error.message})

    succeeded = sum(1 for r in results if r['success'])
    status = 200 if (results and succeeded == len(results)) else 207
    _audit_group(event, current_user, 'group_bulk_assign', group.public_id,
                 status='completed',
                 detail={'capability': capability, 'succeeded': succeeded,
                         'total': len(results)})
    return jsonify({
        'success': succeeded == len(results) and len(results) > 0,
        'capability': capability,
        'succeeded': succeeded,
        'failed': len(results) - succeeded,
        'results': results,
    }), status


@guest_management_bp.route('/<event_ref>/groups/<group_ref>/vip', methods=['POST'])
@login_required
def group_manage_vip(event_ref, group_ref):
    """Set the is_vip flag for a list of member ids or all members."""
    event = _event_for_ref(event_ref)
    allowed, message = _require(event, 'group.vip_manage')
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_GROUP_FORBIDDEN', 'error': message}), 403

    group = _resolve_group(event, group_ref)
    data = request.get_json(silent=True) or {}
    is_vip = bool(data.get('is_vip', True))
    member_ids = data.get('member_ids') or []
    apply_all = bool(data.get('all', False))
    if not apply_all and not member_ids:
        return jsonify({'success': False, 'code': 'INVALID_VIP',
                        'error': 'member_ids or all is required'}), 400

    members = []
    if apply_all:
        members = [m for m in group.members if not m.is_deleted]
    else:
        seen = set()
        for mid in member_ids:
            try:
                member = _resolve_member(group, mid)
            except CoordinationError:
                continue
            if member.id in seen:
                continue
            seen.add(member.id)
            members.append(member)

    updated = 0
    for member in members:
        if member.is_vip != is_vip:
            member.is_vip = is_vip
            updated += 1
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'code': 'VIP_UPDATE_FAILED',
                        'error': str(exc)}), 400

    _audit_group(event, current_user, 'group_vip', group.public_id,
                 status='completed', detail={'is_vip': is_vip, 'count': updated})
    return jsonify({'success': True, 'updated': updated})
