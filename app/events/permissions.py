# app/events/permissions.py
"""
Event Permissions — Role-based access control for all event actions.

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

  * org_owner / org_admin — only for events owned by their organisation
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Tuple

from flask_login import current_user

from app.extensions import db
from app.auth.helpers import has_global_role, has_org_role, has_global_permission, has_org_permission
from app.auth.helpers import is_system_admin as auth_is_system_admin
from app.events.constants import EventStatus


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _resolve_event_org_id(event) -> int | None:
    """Return the organisation id from either a model instance or a dict."""
    if hasattr(event, 'organization_id'):
        return event.organization_id
    if hasattr(event, 'get'):
        return event.get('organisation_id') or event.get('organization_id')
    return None


def _resolve_organiser_id(event) -> int | None:
    """Return the organiser user id from either a model instance or a dict."""
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
    """True if this user is the current owner OR organiser of the event."""
    if _resolve_organiser_id(event) == user.id:
        return True
    if hasattr(event, 'is_owned_by_user') and event.is_owned_by_user(user.id):
        return True
    return False


def _is_org_member_of_event(user, event, *org_roles) -> bool:
    """True if user holds one of org_roles inside the event's owning org."""
    org_id = _resolve_event_org_id(event)
    if not org_id:
        return False
    return has_org_role(user, org_id, *org_roles)


# ============================================================================
# PLATFORM-LEVEL ROLE CHECKS
# ============================================================================

def is_system_admin(user) -> bool:
    """
    True for owner, super_admin, and admin.
    These three roles have full platform-wide event visibility.
    Note: not all of them can hard-delete — use is_super_admin() for that.
    """
    if not user or not user.is_authenticated:
        return False
    return has_global_role(user, 'owner', 'super_admin', 'admin')


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

    # Platform roles (order matters — most powerful first)
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
        if _is_event_owner(user, event):
            roles.add('organiser')

        # Org-level roles for the event's owning organisation
        org_id = _resolve_event_org_id(event)
        if org_id:
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
                roles.add(staff.role)   # e.g. 'co_organizer', 'steward'

    return roles


# ============================================================================
# MODERATION PERMISSION CHECKS
# These are the authoritative checks routes and services should call.
# Each returns (bool, error_str) so callers can pass the message to the UI.
# ============================================================================

def can_manage_event(user, event) -> Tuple[bool, str]:
    """Edit, create, update — organiser and above."""
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'
    if is_event_manager(user):
        return True, ''
    if event:
        if _is_event_owner(user, event):
            return True, ''
        if _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
            return True, ''
    return False, 'Not authorized to manage this event'


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
    if not is_event_manager(user):
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
    event_manager cannot suspend — suspension is an enforcement action.
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
    if is_event_manager(user):
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
    if is_event_manager(user):
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
    if is_event_manager(user):
        return True, ''
    if event and _is_event_owner(user, event):
        return True, ''
    if event and _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
        return True, ''
    return False, 'Not authorized to cancel this event'


def can_soft_delete_event(user, event) -> Tuple[bool, str]:
    """
    Organiser soft-delete → ARCHIVED.
    Organisers reach ARCHIVED only — never DELETED.
    Admins can also archive via this path.
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'
    if is_event_manager(user):
        return True, ''
    if event and _is_event_owner(user, event):
        return True, ''
    if event and _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
        return True, ''
    return False, 'Not authorized to delete this event'


def can_hard_delete_event(user, event) -> Tuple[bool, str]:
    """
    Admin hard-delete → DELETED.  super_admin / owner only.
    The event is never physically removed — just set to terminal DELETED status.
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

    # event_manager and admin can soft-delete (→ ARCHIVED)
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
            if created_at and datetime.utcnow() - created_at < timedelta(hours=24):
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
        return False, 'Not authenticated'
    if has_global_permission(user, 'events.checkin'):
        return True, ''
    if event:
        if _is_event_owner(user, event):
            return True, ''
        if _is_org_member_of_event(user, event, 'org_owner', 'org_admin'):
            return True, ''
        # Event-level staff
        roles = resolve_user_roles(user, event)
        if roles & {'steward', 'volunteer', 'co_organizer'}:
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
        # Unknown action — fail secure
        return False, f"Unknown action '{action}'"

    return fn(user, event)


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
