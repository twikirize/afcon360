# app/events/permissions.py
"""
Event Permissions - Role-based access control for all event actions.

ROLE HIERARCHY (highest → lowest)
───────────────────────────────────────────────────────────────────
  owner        Platform owner.  Unrestricted.
  super_admin  Platform super-admin.  All moderation + hard-delete.
  admin        Platform admin.  Approve / reject / suspend / unsuspend.
               Cannot hard-delete (→ DELETED) or takedown.
  event_manager Platform-level event manager.  Approve / reject / publish.
               Cannot suspend, takedown, or hard-delete.
  org_owner    Owner of an organisation.  Full control over org events.
  org_admin    Admin of an organisation.  Manage their org's events.
  organiser    The event's own organiser_id.  Self-service only.
  co_organizer Event-level staff role.  Edit + attendee management.
  steward      Event-level staff role.  Check-in only.
  volunteer    Event-level staff role.  Check-in only.

MODERATION MATRIX
───────────────────────────────────────────────────────────────────
  Action           owner  super  admin  evt_mgr  org*  organiser
  ─────────────────────────────────────────────────────────────────
  approve            ✅     ✅     ✅      ✅      ❌       ❌
  reject             ✅     ✅     ✅      ✅      ❌       ❌
  publish            ✅     ✅     ✅      ✅      ❌       ❌
  suspend            ✅     ✅     ✅      ❌      ❌       ❌
  unsuspend          ✅     ✅     ✅      ❌      ❌       ❌
  takedown           ✅     ✅     ❌      ❌      ❌       ❌
  hard-delete(→DEL)  ✅     ✅     ❌      ❌      ❌       ❌
  pause              ✅     ✅     ✅      ✅      ✅       ✅ (own)
  resume             ✅     ✅     ✅      ✅      ✅       ✅ (own)
  cancel             ✅     ✅     ✅      ✅      ✅       ✅ (own)
  soft-delete(→ARC)  ✅     ✅     ✅      ✅      ✅       ✅ (own)
  edit               ✅     ✅     ✅      ✅      ✅       ✅ (own)

  * org_owner / org_admin - only for events owned by their organisation
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Tuple

from flask_login import current_user

from app.extensions import db
from app.auth.helpers import (
    has_global_role,
    has_org_role,
    has_global_permission,
    has_org_permission,
)
from app.events.constants import EventStatus


# ============================================================================
# EVENT-LEVEL STAFF ACTION MAP
# ============================================================================

EVENT_STAFF_ACTION_MAP = {
    # Role name in EventRole.table        Actions permitted
    'co_organizer': {
        'view_coordination',
        'manage_coordination',
        'check_in',
    },
    'steward': {
        'check_in',
    },
    'volunteer': {
        'check_in',
    },
}

# ============================================================================
# EVENT GUEST OPERATIONS — GRANULAR PERMISSION MODEL
# ============================================================================
# Fine-grained permissions for the Event Guest Operations / assignment system.
# Grouped by capability per the Event Guest Operations permission model.
#
# Event staff (EventRole) are scoped by a permission bundle, never by a single
# catch-all flag.  Platform admins, event managers, the canonical event owner
# (individual or organisation) and org_owner/org_admin of the owning
# organisation receive EVERY permission below.  Event-level staff receive only
# the permissions present in their role bundle.
GUEST_OPERATIONS_PERMISSION_GROUPS = {
    'Guest Management': [
        'guest.view',
        'guest.create',
        'guest.edit',
        'guest.import',
        'guest.archive',
        'guest.link_account',
        'guest.merge',
    ],
    'Coordination / Assignment': [
        'assignment.view',
        'accommodation.assign',
        'accommodation.cancel',
        'accommodation.allocate_room',
        'transport.assign',
        'transport.cancel',
        'transport.plan',
        'tourism.assign',
        'tourism.cancel',
        'experience.assign',
    ],
    'Wallet / Allowance': [
        'wallet.view',
        'allowance.create',
        'allowance.adjust',
        'wallet.authorise_spend',
        'financial.approve',
        'financial.view',
    ],
    'Guest Journey': [
        'journey.view',
        'journey.manage',
        'journey.override',
        'exception.resolve',
        'coverage.view',
    ],
    'Groups / Delegations': [
        'group.view',
        'group.create',
        'group.edit',
        'group.bulk_assign',
        'group.vip_manage',
    ],
    'Communication': [
        'notify.guest',
        'notify.bulk',
        'message.view',
    ],
    'Audit / Compliance': [
        'audit.view',
        'audit.export',
    ],
    'Check-in': [
        'check_in',
    ],
}

ALL_GUEST_OPERATIONS_PERMISSIONS = {
    perm for perms in GUEST_OPERATIONS_PERMISSION_GROUPS.values() for perm in perms
}

# Permissions that mutate event guest state.  Used by can_manage_coordination
# and by capability-aware helpers to recognise a "manager".
MUTATION_PERMISSIONS = {
    'guest.create', 'guest.edit', 'guest.import', 'guest.archive',
    'guest.link_account', 'guest.merge',
    'accommodation.assign', 'accommodation.cancel', 'accommodation.allocate_room',
    'transport.assign', 'transport.cancel', 'transport.plan',
    'tourism.assign', 'tourism.cancel', 'experience.assign',
    'allowance.create', 'allowance.adjust', 'wallet.authorise_spend',
    'financial.approve',
    'journey.manage', 'journey.override', 'exception.resolve',
    'group.create', 'group.edit', 'group.bulk_assign', 'group.vip_manage',
    'notify.guest', 'notify.bulk',
    'audit.export',
}

# Default permission bundles for event staff roles.  A concrete EventRole may
# override these via its JSON `permissions` column; otherwise this map supplies
# the default for the role name.  co_organizer / steward / volunteer remain
# backward compatible with the legacy EVENT_STAFF_ACTION_MAP behaviour.
EVENT_STAFF_ROLE_PERMISSIONS = {
    # Legacy broad coordinator.
    'co_organizer': {
        'guest.view', 'guest.create', 'guest.edit', 'guest.import',
        'guest.archive', 'guest.link_account', 'guest.merge',
        'assignment.view',
        'accommodation.assign', 'accommodation.cancel', 'accommodation.allocate_room',
        'transport.assign', 'transport.cancel', 'transport.plan',
        'tourism.assign', 'tourism.cancel',
        'journey.view', 'journey.manage', 'journey.override',
        'exception.resolve', 'coverage.view',
        'group.view', 'group.create', 'group.edit', 'group.bulk_assign', 'group.vip_manage',
        'notify.guest', 'notify.bulk', 'message.view',
        'audit.view', 'check_in',
    },
    'steward': {'check_in', 'guest.view', 'assignment.view', 'journey.view'},
    'volunteer': {'check_in', 'guest.view', 'assignment.view', 'journey.view'},

    # Event Operations Manager — day-to-day event operator.
    'operations_manager': {
        'guest.view', 'guest.create', 'guest.edit', 'guest.import',
        'guest.archive', 'guest.link_account', 'guest.merge',
        'assignment.view',
        'accommodation.assign', 'accommodation.cancel', 'accommodation.allocate_room',
        'transport.assign', 'transport.cancel', 'transport.plan',
        'tourism.assign', 'tourism.cancel',
        'journey.view', 'journey.manage', 'journey.override',
        'exception.resolve', 'coverage.view',
        'group.view', 'group.create', 'group.edit', 'group.bulk_assign', 'group.vip_manage',
        'notify.guest', 'notify.bulk', 'message.view',
        'wallet.view', 'allowance.create', 'allowance.adjust',
        'wallet.authorise_spend', 'financial.view',
        'audit.view', 'check_in',
    },

    # Accommodation Coordinator — accommodation only.
    'accommodation_coordinator': {
        'guest.view', 'assignment.view',
        'accommodation.assign', 'accommodation.cancel', 'accommodation.allocate_room',
        'journey.view', 'coverage.view', 'check_in',
    },

    # Transport Coordinator — transport only.
    'transport_coordinator': {
        'guest.view', 'assignment.view',
        'transport.assign', 'transport.cancel', 'transport.plan',
        'journey.view', 'coverage.view', 'check_in',
    },

    # Guest Services / Hospitality Coordinator.
    'guest_services_coordinator': {
        'guest.view', 'guest.create', 'guest.edit', 'guest.link_account',
        'assignment.view',
        'journey.view', 'journey.manage',
        'tourism.assign', 'tourism.cancel',
        'notify.guest', 'message.view', 'check_in',
    },

    # Finance Manager / Budget Controller.
    'finance_manager': {
        'guest.view', 'assignment.view',
        'wallet.view', 'allowance.create', 'allowance.adjust',
        'wallet.authorise_spend', 'financial.approve', 'financial.view',
        'journey.view', 'audit.view',
    },

    # Check-in / Door Staff.
    'checkin_staff': {
        'guest.view', 'assignment.view', 'journey.view', 'check_in',
    },

    # Auditor / Compliance Viewer — read only.
    'auditor': {
        'guest.view', 'assignment.view', 'journey.view', 'coverage.view',
        'audit.view', 'audit.export',
    },

    # Delegation Lead / Group Coordinator — scoped to their group.
    'delegation_lead': {
        'guest.view', 'assignment.view',
        'group.view', 'group.edit', 'group.bulk_assign',
        'accommodation.assign', 'transport.assign', 'tourism.assign',
        'notify.guest', 'message.view', 'journey.view', 'check_in',
    },
}

# Human-readable explanations for every permission key used by event staff
# roles.  Surfaced in the staff management UI so the organizer can read, at a
# glance, what each role/permission actually allows (the "treasure map").
PERMISSION_DESCRIPTIONS = {
    'guest.view': 'View the guest / attendee list',
    'guest.create': 'Register new guests manually',
    'guest.edit': 'Edit guest details',
    'guest.import': 'Bulk-import guests',
    'guest.archive': 'Archive guest records',
    'guest.link_account': 'Link a guest to a user account',
    'guest.merge': 'Merge duplicate guest records',
    'assignment.view': 'View accommodation / transport assignments',
    'accommodation.assign': 'Assign accommodation to guests',
    'accommodation.cancel': 'Cancel accommodation assignments',
    'accommodation.allocate_room': 'Allocate specific rooms',
    'transport.assign': 'Assign transport to guests',
    'transport.cancel': 'Cancel transport assignments',
    'transport.plan': 'Plan transport logistics',
    'tourism.assign': 'Assign tourism experiences',
    'tourism.cancel': 'Cancel tourism assignments',
    'journey.view': 'View guest journeys / movement',
    'journey.manage': 'Manage guest journeys',
    'journey.override': 'Override journey records',
    'exception.resolve': 'Resolve guest exceptions',
    'coverage.view': 'View coverage / rosters',
    'group.view': 'View guest groups',
    'group.create': 'Create guest groups',
    'group.edit': 'Edit guest groups',
    'group.bulk_assign': 'Bulk-assign guests to groups',
    'group.vip_manage': 'Manage VIP groups',
    'notify.guest': 'Send notifications to guests',
    'notify.bulk': 'Send bulk notifications',
    'message.view': 'View and send messages / announcements',
    'audit.view': 'View audit logs',
    'audit.export': 'Export audit logs',
    'check_in': 'Check guests in at the door (scanner)',
    'wallet.view': 'View financial wallet info',
    'allowance.create': 'Create spending allowances',
    'allowance.adjust': 'Adjust allowances',
    'wallet.authorise_spend': 'Authorise spending',
    'financial.view': 'View financial reports',
    'financial.approve': 'Approve financial transactions',
}

# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _has_event_staff_permission(user, event, action: str) -> bool:
    """Return True if the user holds an event staff role granting ``action``.

    Adding a new event staff role later does not require editing every
    permission function.  Add the role to `EVENT_STAFF_ACTION_MAP` after
    making it available in the `EventRole` role reference data.
    """
    roles = resolve_user_roles(user, event)
    for role in roles:
        allowed_actions = EVENT_STAFF_ACTION_MAP.get(role)
        if allowed_actions and action in allowed_actions:
            return True
    return False


def _resolve_event_org_id(event) -> int | None:
    """Return the organisation id from either a model instance or a dict."""
    if hasattr(event, 'organization_id'):
        return event.organization_id
    if hasattr(event, 'get'):
        return event.get('organisation_id') or event.get('organization_id')
    return None


def _resolve_organiser_id(event) -> int | None:
    """Return the organiser user id from either a model instance or a dict."""
    import logging
    import warnings
    warnings.warn(
        'organizer_id fallback usage is DEPRECATED (Phase 4 Step 5)',
        DeprecationWarning,
        stacklevel=2,
    )
    logging.getLogger(__name__).warning(
        'LEGACY PERMISSION FALLBACK: _resolve_organiser_id called. Phase 4 Deprecation.'
    )
    if hasattr(event, 'organizer_id'):
        return event.organizer_id
    if hasattr(event, 'get'):
        return event.get('organizer_id')
    return None


def _resolve_status(event) -> EventStatus | None:
    """Return the EventStatus from either a model instance or a dict."""
    if hasattr(event, 'status'):
        s = event.status
        if isinstance(s, EventStatus):
            return s
        try:
            return EventStatus(str(s))
        except ValueError:
            return None
    if hasattr(event, 'get'):
        s = event.get('status')
        if isinstance(s, EventStatus):
            return s
        try:
            return EventStatus(str(s))
        except ValueError:
            return None
    return None


def _is_event_owner(user, event) -> bool:
    """Return whether ``user`` is the canonical owner of ``event``.

    ``organizer_id`` is consulted only for records that do not expose an
    explicit current owner.  This preserves legacy-record compatibility
    without allowing a stale organizer value to override a transfer.
    """
    if hasattr(event, 'current_owner_type'):
        owner_type = event.current_owner_type
        owner_id = event.current_owner_id
    elif hasattr(event, 'get'):
        owner_type = event.get('current_owner_type')
        owner_id = event.get('current_owner_id')
    else:
        owner_type = owner_id = None

    owner_type_value = getattr(owner_type, 'value', owner_type)
    if owner_type_value == 'individual' and owner_id == user.id:
        return True

    if owner_type is not None or owner_id is not None:
        return False

    if _resolve_organiser_id(event) == user.id:
        return True
    return False


def _is_org_member_of_event(user, event, *org_roles) -> bool:
    """True if user holds one of org_roles inside the event's owning org."""
    org_id = _resolve_event_org_id(event)
    if not org_id:
        return False
    return has_org_role(user, org_id, *org_roles)


# ============================================================================
# EVENT GUEST OPERATIONS — PERMISSION RESOLUTION
# ============================================================================

def _is_coordination_authority(user, event) -> bool:
    """True for platform/event authorities that hold EVERY guest operation permission.

    Mirrors the authority contract used by can_view_coordination /
    can_manage_coordination: system admins, event managers, moderators, the
    canonical event owner, and org_owner/org_admin of the owning organisation.
    """
    if not user or not user.is_authenticated:
        return False
    if is_system_admin(user) or is_event_manager(user) or is_moderator(user):
        return True
    if event:
        if _is_event_owner(user, event):
            return True
        if _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
            return True
    return False


def _resolve_user_event_permissions(user, event) -> set:
    """Return the full set of guest-operation permissions a user holds for event.

    Authorities receive every permission.  Event staff receive the union of
    their EventRole.permissions (JSON) and the role's default bundle.
    """
    if _is_coordination_authority(user, event):
        return set(ALL_GUEST_OPERATIONS_PERMISSIONS)

    perms: set = set()
    if event is None or not getattr(user, 'id', None):
        return perms

    event_id = getattr(event, 'id', None) or (
        event.get('id') if hasattr(event, 'get') else None
    )
    if not event_id:
        return perms

    from app.events.models import EventRole

    staff_roles = EventRole.query.filter_by(
        event_id=event_id, user_id=user.id, is_active=True
    ).all()
    for role in staff_roles:
        role_perms = role.permissions
        if isinstance(role_perms, (list, tuple, set)) and role_perms:
            perms.update(str(p) for p in role_perms)
        else:
            perms.update(EVENT_STAFF_ROLE_PERMISSIONS.get(role.role, set()))
    return perms


def has_guest_operation_permission(user, event, permission: str) -> Tuple[bool, str]:
    """Authorize a single granular guest-operation permission."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'
    perms = _resolve_user_event_permissions(user, event)
    if permission in perms:
        return True, ''
    return False, 'Not authorized for this event guest operation'


def get_event_guest_permissions(user, event) -> dict:
    """Return a granular permission map for templates / API consumers.

    Every permission in GUEST_OPERATIONS_PERMISSION_GROUPS is present as a
    boolean key, so the UI can show/hide actions without re-implementing the
    authority logic.  Safe to pass directly into Jinja2 templates.
    """
    if not user or not user.is_authenticated:
        return {perm: False for perm in ALL_GUEST_OPERATIONS_PERMISSIONS}
    perms = _resolve_user_event_permissions(user, event)
    return {perm: (perm in perms) for perm in ALL_GUEST_OPERATIONS_PERMISSIONS}


# ============================================================================
# PLATFORM-LEVEL ROLE CHECKS
# ============================================================================

def is_system_admin(user) -> bool:
    """
    True for owner, super_admin, and admin.
    These three roles have full platform-wide event visibility.
    Note: not all of them can hard-delete - use is_super_admin() for that.
    """
    if not user or not user.is_authenticated:
        return False
    return has_global_role(user, 'owner', 'super_admin', 'admin')


def is_moderator(user) -> bool:
    """
    True for moderator role.
    """
    if not user or not user.is_authenticated:
        return False
    return has_global_role(user, 'moderator')


def is_super_admin(user) -> bool:
    """
    True only for owner and super_admin.
    Required for hard-delete (→ DELETED) and policy takedown.
    """
    if not user or not user.is_authenticated:
        return False
    return has_global_role(user, 'owner', 'super_admin')


def is_event_manager(user) -> bool:
    """True if user has the events.manage permission (event_manager role and above)."""
    if not user or not user.is_authenticated:
        return False
    return has_global_permission(user, 'events.manage')


def is_organization_admin(user, organisation_id: int = None) -> bool:
    """
    True if user is a system admin OR an org_owner / org_admin of
    the given organisation (or any organisation if none specified).
    """
    if not user or not user.is_authenticated:
        return False
    if is_system_admin(user):
        return True
    if organisation_id:
        return has_org_role(user, organisation_id, 'org_owner', 'org_admin')
    if hasattr(user, 'organisations'):
        for membership in user.organisations:
            if has_org_role(user, membership.organisation_id, 'org_owner', 'org_admin'):
                return True
    return False


# ============================================================================
# CONTEXTUAL ROLE RESOLVER
# ============================================================================

def resolve_user_roles(user, event) -> set[str]:
    """
    Build the complete set of roles this user holds in the context of
    this specific event.  Used by check_transition_permission and the
    permission functions below.

    Returned role strings match TRANSITION_ROLES keys in constants.py.
    """
    roles: set[str] = set()

    if not user or not user.is_authenticated:
        return roles

    active_context = None
    try:
        from flask import has_request_context
        if has_request_context():
            from app.auth.context import get_active_context
            active_context = get_active_context(user)
    except ImportError:
        pass

    ctx_type = active_context.type.value if active_context else None
    ctx_id = active_context.id if active_context else None

    # Platform roles (order matters - most powerful first)
    if ctx_type is None or ctx_type == "platform":
        if has_global_role(user, 'owner'):
            roles.add('owner')
        if has_global_role(user, 'super_admin'):
            roles.add('super_admin')
        if has_global_role(user, 'admin'):
            roles.add('admin')
        if has_global_role(user, 'event_manager'):
            roles.add('event_manager')

    if event:
        # Organiser of this specific event
        if ctx_type is None or ctx_type == "personal":
            if _is_event_owner(user, event):
                roles.add('organiser')

        # Org-level roles for the event's owning organisation
        org_id = _resolve_event_org_id(event)
        if org_id:
            allow_org = True
            if ctx_type == "organisation":
                from app.identity.models.organisation import Organisation
                org = Organisation.query.get(org_id)
                if not org or org.org_id != ctx_id:
                    allow_org = False
            elif ctx_type is not None:
                # Strict Context Boundary: If acting personally or on another platform,
                # you do not implicitly get your org permissions here.
                allow_org = False

            if allow_org:
                if has_org_role(user, org_id, 'org_owner'):
                    roles.add('org_owner')
                if has_org_role(user, org_id, 'org_admin'):
                    roles.add('org_admin')

        # Event-level staff roles
        event_id = getattr(event, 'id', None) or (
            event.get('id') if hasattr(event, 'get') else None
        )
        if event_id:
            from app.events.models import EventRole
            staff = EventRole.query.filter_by(
                event_id=event_id,
                user_id=user.id,
                is_active=True,
            ).first()
            if staff:
                allow_staff = True
                if staff.organisation_id:
                    if ctx_type == "organisation":
                        from app.identity.models.organisation import Organisation
                        org = Organisation.query.get(staff.organisation_id)
                        if not org or org.org_id != ctx_id:
                            allow_staff = False
                    else:
                        allow_staff = False
                if allow_staff:
                    roles.add(staff.role)   # e.g. 'co_organizer', 'steward'

    return roles


# ============================================================================
# MODERATION PERMISSION CHECKS
# These are the authoritative checks routes and services should call.
# Each returns (bool, error_str) so callers can pass the message to the UI.
# ============================================================================

def can_manage_event(user, event) -> Tuple[bool, str]:
    """Edit, create, update - organiser and above."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if is_system_admin(user):
        return True, ''
    if is_event_manager(user):
        return True, ''
    if is_moderator(user):
        return True, ''

    if event:
        if _is_event_owner(user, event):
            return True, ''
        if _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
            return True, ''

    return False, 'Not authorized to manage this event'


def can_approve_event_transfer(user, transfer_request) -> Tuple[bool, str]:
    """Authorize approval against the requested transfer target."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if (
        has_global_permission(user, 'events.manage')
        or has_global_permission(user, 'events.approve')
    ):
        return True, ''

    if transfer_request.to_user_id is not None:
        if user.id == transfer_request.to_user_id:
            return True, ''
        return False, 'Only the requested individual owner can approve this transfer'

    if transfer_request.to_organization_id is not None:
        if has_org_role(user, transfer_request.to_organization_id, 'org_owner', 'org_admin'):
            return True, ''
        return False, 'Only an authorized target organization member can approve this transfer'

    return False, 'Transfer request has no valid approval target'


def can_view_coordination(user, event) -> Tuple[bool, str]:
    """View confirmed attendees and live coordination state.

    Maps to the granular ``assignment.view`` / ``guest.view`` permissions while
    preserving authority behaviour for platform/event owners and managers.
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if is_event_manager(user) or is_system_admin(user) or is_moderator(user):
        return True, ''

    if event and (
        _is_event_owner(user, event)
        or _is_org_member_of_event(user, event, 'org_owner', 'org_admin')
    ):
        return True, ''

    ok, _ = has_guest_operation_permission(user, event, 'assignment.view')
    if ok:
        return True, ''
    ok, _ = has_guest_operation_permission(user, event, 'guest.view')
    if ok:
        return True, ''

    return False, 'Not authorized to view event coordination'


def can_manage_coordination(user, event) -> Tuple[bool, str]:
    """Authorize coordination mutations broadly.

    True for authorities, or for any staff member holding at least one mutation
    permission.  Prefer the capability-specific helpers (can_assign_accommodation,
    can_assign_transport, can_cancel_assignment) for fine-grained control.
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'
    if is_event_manager(user) or is_system_admin(user) or is_moderator(user):
        return True, ''
    if event and (
        _is_event_owner(user, event)
        or _is_org_member_of_event(user, event, 'org_owner', 'org_admin')
    ):
        return True, ''
    perms = _resolve_user_event_permissions(user, event)
    if perms & MUTATION_PERMISSIONS:
        return True, ''
    return False, 'Not authorized to manage event coordination'


def can_assign_accommodation(user, event) -> Tuple[bool, str]:
    return has_guest_operation_permission(user, event, 'accommodation.assign')


def can_assign_transport(user, event) -> Tuple[bool, str]:
    return has_guest_operation_permission(user, event, 'transport.assign')


def can_cancel_assignment(user, event, capability: str = None) -> Tuple[bool, str]:
    """Cancel an assignment capability.

    ``capability`` may be 'accommodation' or 'transport'; when omitted any
    cancellation permission is accepted (broad authority / manager).
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'
    if capability == 'accommodation':
        return has_guest_operation_permission(user, event, 'accommodation.cancel')
    if capability == 'transport':
        return has_guest_operation_permission(user, event, 'transport.cancel')
    acc_ok, _ = has_guest_operation_permission(user, event, 'accommodation.cancel')
    trn_ok, _ = has_guest_operation_permission(user, event, 'transport.cancel')
    if acc_ok or trn_ok:
        return True, ''
    return False, 'Not authorized to cancel assignments'


# ============================================================================
# EVENT GUEST OPERATIONS — GRANULAR CONVENIENCE HELPERS
# Each maps to exactly one permission in GUEST_OPERATIONS_PERMISSION_GROUPS.
# Authorities (platform/event owners, managers) receive every permission via
# _resolve_user_event_permissions, so these return True for them automatically.
# ============================================================================

def _guest_op(user, event, permission: str) -> Tuple[bool, str]:
    return has_guest_operation_permission(user, event, permission)


def can_view_guests(user, event):
    return _guest_op(user, event, 'guest.view')


def can_create_guest(user, event):
    return _guest_op(user, event, 'guest.create')


def can_edit_guest(user, event):
    return _guest_op(user, event, 'guest.edit')


def can_import_guests(user, event):
    return _guest_op(user, event, 'guest.import')


def can_archive_guest(user, event):
    return _guest_op(user, event, 'guest.archive')


def can_link_guest_account(user, event):
    return _guest_op(user, event, 'guest.link_account')


def can_merge_guest(user, event):
    return _guest_op(user, event, 'guest.merge')


def can_view_assignment(user, event):
    return _guest_op(user, event, 'assignment.view')


def can_allocate_room(user, event):
    return _guest_op(user, event, 'accommodation.allocate_room')


def can_plan_transport(user, event):
    return _guest_op(user, event, 'transport.plan')


def can_assign_tourism(user, event):
    return _guest_op(user, event, 'tourism.assign')


def can_cancel_tourism(user, event):
    return _guest_op(user, event, 'tourism.cancel')


def can_assign_experience(user, event):
    return _guest_op(user, event, 'experience.assign')


def can_view_wallet(user, event):
    return _guest_op(user, event, 'wallet.view')


def can_create_allowance(user, event):
    return _guest_op(user, event, 'allowance.create')


def can_adjust_allowance(user, event):
    return _guest_op(user, event, 'allowance.adjust')


def can_authorise_spend(user, event):
    return _guest_op(user, event, 'wallet.authorise_spend')


def can_approve_financial(user, event):
    return _guest_op(user, event, 'financial.approve')


def can_view_financial(user, event):
    return _guest_op(user, event, 'financial.view')


def can_view_journey(user, event):
    return _guest_op(user, event, 'journey.view')


def can_manage_journey(user, event):
    return _guest_op(user, event, 'journey.manage')


def can_override_journey(user, event):
    return _guest_op(user, event, 'journey.override')


def can_resolve_exception(user, event):
    return _guest_op(user, event, 'exception.resolve')


def can_view_coverage(user, event):
    return _guest_op(user, event, 'coverage.view')


def can_view_group(user, event):
    return _guest_op(user, event, 'group.view')


def can_create_group(user, event):
    return _guest_op(user, event, 'group.create')


def can_edit_group(user, event):
    return _guest_op(user, event, 'group.edit')


def can_bulk_assign_group(user, event):
    return _guest_op(user, event, 'group.bulk_assign')


def can_manage_vip(user, event):
    return _guest_op(user, event, 'group.vip_manage')


def can_notify_guest(user, event):
    return _guest_op(user, event, 'notify.guest')


def can_notify_bulk(user, event):
    return _guest_op(user, event, 'notify.bulk')


def can_view_messages(user, event):
    return _guest_op(user, event, 'message.view')


def can_view_audit(user, event):
    return _guest_op(user, event, 'audit.view')


def can_export_audit(user, event):
    return _guest_op(user, event, 'audit.export')


def can_approve_event(user, event) -> Tuple[bool, str]:
    """Approve PENDING_APPROVAL → APPROVED.  event_manager and above."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if not has_global_permission(user, 'events.approve'):
        return False, 'You do not have permission to approve events'

    status = _resolve_status(event)
    if status and status != EventStatus.PENDING_APPROVAL:
        return False, f"Event must be pending approval (current: {status.value})"

    return True, ''


def can_reject_event(user, event) -> Tuple[bool, str]:
    """Reject PENDING_APPROVAL → REJECTED.  event_manager and above."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if not has_global_permission(user, 'events.approve'):
        return False, 'Only event managers and above can reject events'

    status = _resolve_status(event)
    if status and status != EventStatus.PENDING_APPROVAL:
        return False, f"Event must be pending approval (current: {status.value})"

    return True, ''


def can_publish_event(user, event) -> Tuple[bool, str]:
    """Publish APPROVED → PUBLISHED.  event_manager and above."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if not is_event_manager(user):
        return False, 'Only event managers and above can publish events'

    status = _resolve_status(event)
    if status and status != EventStatus.APPROVED:
        return False, f"Event must be approved before publishing (current: {status.value})"

    return True, ''


def can_suspend_event(user, event) -> Tuple[bool, str]:
    """
    Suspend PUBLISHED → SUSPENDED.  admin and above only.
    event_manager cannot suspend - suspension is an enforcement action.
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if not is_system_admin(user):
        return False, 'Only admins and above can suspend events'

    status = _resolve_status(event)
    if status and status != EventStatus.PUBLISHED:
        return False, f"Only published events can be suspended (current: {status.value})"

    return True, ''


def can_unsuspend_event(user, event) -> Tuple[bool, str]:
    """Restore SUSPENDED → PUBLISHED.  admin and above only."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if not is_system_admin(user):
        return False, 'Only admins and above can unsuspend events'

    status = _resolve_status(event)
    if status and status != EventStatus.SUSPENDED:
        return False, f"Event is not suspended (current: {status.value})"

    return True, ''


def can_takedown_event(user, event) -> Tuple[bool, str]:
    """
    Policy takedown → DELETED.  super_admin / owner only.
    This is irreversible from the organiser's perspective.
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if not is_super_admin(user):
        return False, 'Only super admins and owners can take down events'

    return True, ''


def can_pause_event(user, event) -> Tuple[bool, str]:
    """Pause PUBLISHED → PAUSED.  organiser and above."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if is_system_admin(user) or is_event_manager(user):
        return True, ''

    if event and _is_event_owner(user, event):
        return True, ''

    if event and _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
        return True, ''

    status = _resolve_status(event)
    if status and status != EventStatus.PUBLISHED:
        return False, f"Only published events can be paused (current: {status.value})"

    return False, 'Not authorized to pause this event'


def can_resume_event(user, event) -> Tuple[bool, str]:
    """Resume PAUSED → PUBLISHED.  organiser and above."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if is_system_admin(user) or is_event_manager(user):
        return True, ''

    if event and _is_event_owner(user, event):
        return True, ''

    if event and _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
        return True, ''

    status = _resolve_status(event)
    if status and status != EventStatus.PAUSED:
        return False, f"Event is not paused (current: {status.value})"

    return False, 'Not authorized to resume this event'


def can_cancel_event(user, event) -> Tuple[bool, str]:
    """Cancel → CANCELLED.  organiser and above."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if is_system_admin(user) or is_event_manager(user):
        return True, ''

    if event and _is_event_owner(user, event):
        return True, ''

    if event and _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
        return True, ''

    return False, 'Not authorized to cancel this event'


def can_soft_delete_event(user, event) -> Tuple[bool, str]:
    """
    Organiser soft-delete → ARCHIVED.
    Organisers reach ARCHIVED only - never DELETED.
    Admins can also archive via this path.
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if is_system_admin(user) or is_event_manager(user):
        return True, ''

    if event and _is_event_owner(user, event):
        return True, ''

    if event and _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
        return True, ''

    return False, 'Not authorized to delete this event'


def can_hard_delete_event(user, event) -> Tuple[bool, str]:
    """
    Admin hard-delete → DELETED.  super_admin / owner only.
    The event is never physically removed - just set to terminal DELETED status.
    Organisers can NEVER reach this state directly.
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if not is_super_admin(user):
        return False, 'Only super admins and owners can permanently remove events'

    return True, ''


def can_delete_event(user, event) -> Tuple[bool, str]:
    """
    Unified delete dispatcher:
      super_admin / owner  →  hard-delete allowed (→ DELETED)
      everyone else        →  soft-delete only    (→ ARCHIVED)

    Returns (allowed, error).  Callers should inspect the user's role to
    decide which target status to use:
        EventStatus.DELETED  if is_super_admin(user)
        EventStatus.ARCHIVED otherwise
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    # Super admins can hard-delete from any non-terminal state
    if is_super_admin(user):
        return True, ''

    # Platform admins can soft-delete from any non-terminal state
    if is_system_admin(user):
        return True, ''

    # event_manager and above can soft-delete
    if is_event_manager(user):
        return True, ''

    if event:
        # Organiser can soft-delete their own event
        if _is_event_owner(user, event):
            return True, ''

        # Org admin can soft-delete their org's event
        if _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
            return True, ''

        # Original creator 24-hour grace period
        original_creator_id = getattr(event, 'original_creator_id', None)
        if original_creator_id and original_creator_id == user.id:
            created_at = getattr(event, 'created_at', None)
            if created_at and datetime.now(timezone.utc) - created_at < timedelta(hours=24):
                return True, ''

    return False, 'Not authorized to delete this event'


# ============================================================================
# ANALYTICS & CHECK-IN
# ============================================================================

def can_view_analytics(user, event) -> Tuple[bool, str]:
    """Analytics: event_manager, org admins, finance managers, organiser."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if has_global_permission(user, 'events.analytics'):
        return True, ''

    if event:
        if _is_event_owner(user, event):
            return True, ''
        org_id = _resolve_event_org_id(event)
        if org_id and has_org_permission(user, org_id, 'org.events.analytics'):
            return True, ''
        if _is_org_member_of_event(user, event,
                                    'org_owner', 'org_admin', 'finance_manager'):
            return True, ''

    return False, 'Not authorized to view analytics'


def can_check_in(user, event) -> Tuple[bool, str]:
    """Check-in: event_manager, org admins, organiser, steward, volunteer."""
    if not user or not user.is_authenticated:
        return False, 'Not authorized to check in attendees'

    if has_global_permission(user, 'events.checkin'):
        return True, ''

    if event:
        if _is_event_owner(user, event):
            return True, ''
        if _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
            return True, ''
        ok, _ = has_guest_operation_permission(user, event, 'check_in')
        if ok:
            return True, ''

    return False, 'Not authorized to check in attendees'


# ============================================================================
# UNIFIED ACTION DISPATCHER
# Routes should prefer calling the specific can_X functions above.
# require_event_permission exists for backward compatibility with routes
# that dispatch via a string action name.
# ============================================================================

_ACTION_DISPATCH = {
    'approve':     can_approve_event,
    'reject':      can_reject_event,
    'publish':     can_publish_event,
    'suspend':     can_suspend_event,
    'unsuspend':   can_unsuspend_event,
    'reactivate':  can_unsuspend_event,   # alias
    'takedown':    can_takedown_event,
    'pause':       can_pause_event,
    'resume':      can_resume_event,
    'cancel':      can_cancel_event,
    'delete':      can_delete_event,
    'hard_delete': can_hard_delete_event,
    'archive':     can_soft_delete_event,
    'edit':        can_manage_event,
    'manage':      can_manage_event,
    'analytics':   can_view_analytics,
    'check_in':    can_check_in,
}


def require_event_permission(user, event, action: str) -> Tuple[bool, str]:
    """
    Dispatch permission check by action name.

    Usage:
        ok, err = require_event_permission(current_user, event, 'approve')
        if not ok:
            return jsonify({'error': err}), 403

    Returns (True, '') or (False, human-readable error string).
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    fn = _ACTION_DISPATCH.get(action)
    if fn is None:
        # Unknown action - fail secure
        return False, f"Unknown action '{action}'"

    return fn(user, event)


# ============================================================================
# CENTRALIZED ROUTE GATE
# The single, context-independent event-ownership security gate that every
# event route must route through.  Authorization is decided ONLY against the
# database (event owner OR platform system admin).  Operating-context switching
# is intentionally NOT consulted here - context is a workspace lens, never the
# lock.  Centralizing the decision prevents the IDOR risk of an ad-hoc check
# being forgotten on a single route.
# ============================================================================

def enforce_event_owner(
    event_model,
    user=None,
    *,
    redirect_endpoint: str = 'events.my_events',
    redirect_kwargs: dict = None,
    flash_message: str = 'Unauthorized access',
):
    """Context-independent event-ownership gate for route handlers.

    Returns a Flask response to return immediately on failure, or ``None`` when
    the user is authorized (event owner OR platform system admin).

    Failure response shape:
      * JSON / API requests  -> 403 JSON (``{'success': False, 'error': ...}``)
      * HTML requests        -> flash + redirect

    Usage::

        resp = enforce_event_owner(event_model)
        if resp:
            return resp
    """
    from flask import flash, redirect, request, url_for, jsonify
    from flask_login import current_user

    user = user or current_user
    authorized = bool(
        event_model
        and (is_system_admin(user) or _is_event_owner(user, event_model))
    )
    if authorized:
        return None

    if (
        request.is_json
        or request.path.startswith('/api/')
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    ):
        return jsonify({'success': False, 'error': flash_message}), 403

    flash(flash_message, 'danger')
    return redirect(url_for(redirect_endpoint, **(redirect_kwargs or {})))


# ============================================================================
# CONVENIENCE WRAPPERS  (bool-only, for templates and legacy callers)
# ============================================================================

def can_check_in_attendees(user, event) -> bool:
    ok, _ = can_check_in(user, event)
    return ok


def can_view_event_stats(user, event) -> bool:
    ok, _ = can_view_analytics(user, event)
    return ok


# ============================================================================
# FULL PERMISSION MAP  (for template context / API responses)
# ============================================================================

def can_manage_registration(user, registration, event=None) -> bool:
    """
    True if user may view/cancel/modify this registration.

    Permissions hierarchy:
    1. System admin → always True
    2. Canonical event owner → True for any registration in their event
    3. The attendee themselves → True for their own registration
    4. The person who booked it → True for registrations they paid for

    Returns False for anonymous users.
    """
    if not user or not user.is_authenticated:
        return False

    # System admin can manage anything
    if is_system_admin(user):
        return True

    # Canonical event owner can manage all registrations for their event
    if event:
        if _is_event_owner(user, event):
            return True
    elif registration and hasattr(registration, 'event'):
        event = registration.event
        if _is_event_owner(user, event):
            return True

    # Attendee or booker
    return (
        registration.user_id == user.id
        or registration.booked_by_user_id == user.id
    )


def get_user_event_permissions(user, event_slug: str) -> dict:
    """
    Return a complete permission map for a user on a specific event.
    Safe to pass directly to Jinja2 templates.
    """
    from app.events.services import EventService

    base = {
        'can_view':          True,
        'can_edit':          False,
        'can_delete':        False,
        'can_hard_delete':   False,
        'can_approve':       False,
        'can_reject':        False,
        'can_publish':       False,
        'can_suspend':       False,
        'can_unsuspend':     False,
        'can_takedown':      False,
        'can_pause':         False,
        'can_resume':        False,
        'can_cancel':        False,
        'can_manage_staff':  False,
        'can_view_attendees': False,
        'can_check_in':      False,
        'can_view_analytics': False,
        'role':              None,
    }

    if not user or not user.is_authenticated:
        return base

    event_model = EventService.get_event_model(event_slug)
    if not event_model:
        return base

    roles = resolve_user_roles(user, event_model)

    def _ok(fn):
        ok, _ = fn(user, event_model)
        return ok

    base.update({
        'can_edit':           _ok(can_manage_event),
        'can_delete':         _ok(can_delete_event),
        'can_hard_delete':    _ok(can_hard_delete_event),
        'can_approve':        _ok(can_approve_event),
        'can_reject':         _ok(can_reject_event),
        'can_publish':        _ok(can_publish_event),
        'can_suspend':        _ok(can_suspend_event),
        'can_unsuspend':      _ok(can_unsuspend_event),
        'can_takedown':       _ok(can_takedown_event),
        'can_pause':          _ok(can_pause_event),
        'can_resume':         _ok(can_resume_event),
        'can_cancel':         _ok(can_cancel_event),
        'can_manage_staff':   _ok(can_manage_event),
        'can_view_attendees': _ok(can_manage_event),
        'can_check_in':       _ok(can_check_in),
        'can_view_analytics': _ok(can_view_analytics),
        # Most specific role label for display purposes
        'role': (
            'system_admin'  if is_system_admin(user)  else
            'event_manager' if is_event_manager(user) else
            'org_admin'     if 'org_admin'  in roles  else
            'org_owner'     if 'org_owner'  in roles  else
            'co_organizer'  if 'co_organizer' in roles else
            'organiser'     if 'organiser'  in roles  else
            'steward'       if 'steward'    in roles  else
            'volunteer'     if 'volunteer'  in roles  else
            None
        ),
    })

    return base