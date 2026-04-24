# app/events/permissions.py
"""
Event Permissions - Role-based access control for events
Handles System Admin, Organization Admin, and Event Organizer permissions
"""

from typing import Tuple
from flask_login import current_user
from app.extensions import db
from app.auth.helpers import has_global_role, has_org_role, is_system_admin as auth_is_system_admin
from app.events.constants import EventStatus

def is_system_admin(user) -> bool:
    """
    Check if user is a System Admin (Super Admin)
    System Admins can manage ALL events platform-wide
    Only owner and super_admin have full admin privileges
    """
    if not user or not user.is_authenticated:
        return False
    # Only owner and super_admin have full admin privileges
    return has_global_role(user, 'owner', 'super_admin')


def is_organization_admin(user, organisation_id: int = None) -> bool:
    """
    Check if user is an Organization Admin
    Organization Admins can manage events for their organization
    """
    if not user or not user.is_authenticated:
        return False

    # System admin counts as organization admin too
    if is_system_admin(user):
        return True

    # If specific org ID provided, check if user is admin of that org
    if organisation_id:
        return has_org_role(user, organisation_id, "org_owner", "org_admin")

    # Otherwise check if user is admin of ANY organization
    # We need to get user's organizations - assuming user.organisations exists
    if hasattr(user, 'organisations'):
        for membership in user.organisations:
            if has_org_role(user, membership.organisation_id, "org_owner", "org_admin"):
                return True

    return False


def is_event_organizer(user, event) -> bool:
    """
    Check if user is the direct organizer of a specific event
    """
    if not user or not user.is_authenticated or not event:
        return False

    # System admin can manage any event
    if is_system_admin(user):
        return True

    # Check if user is the event's organizer
    if event.get('organizer_id') == user.id:
        return True

    # Check if user is organization admin for the event's organization
    if event.get('organisation_id'):
        return is_organization_admin(user, event.get('organisation_id'))

    return False


def can_manage_event(user, event) -> Tuple[bool, str]:
    """
    Check if user can manage an event (create, edit, delete)
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    # Level 1-3: Global admins can manage ANY event
    if has_global_role(user, 'owner', 'super_admin', 'admin'):
        return True, ''

    # Level 8: event_manager can manage events
    if has_global_role(user, 'event_manager'):
        return True, ''

    # Check if user is event owner (individual)
    # Assuming event has is_owned_by_user method or similar
    # For compatibility, check event.get('organizer_id')
    if event and hasattr(event, 'is_owned_by_user'):
        if event.is_owned_by_user(user.id):
            return True, ''
    elif event and hasattr(event, 'get'):
        if event.get('organizer_id') == user.id:
            return True, ''

    # Check if user is org admin of owning organization
    # For compatibility, check event.get('organisation_id')
    org_id = None
    if event and hasattr(event, 'current_owner_id'):
        org_id = event.current_owner_id
    elif event and hasattr(event, 'get'):
        org_id = event.get('organisation_id')

    if org_id:
        if has_org_role(user, org_id, 'org_owner', 'org_admin'):
            return True, ''

    return False, 'Not authorized'


def can_approve_event(user, event) -> Tuple[bool, str]:
    '''Only event_manager, admin, super_admin, owner can approve'''
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'
    if has_global_role(user, 'owner', 'super_admin', 'admin', 'event_manager'):
        return True, ''
    return False, 'Only event managers can approve events'

def can_delete_event(user, event) -> Tuple[bool, str]:
    '''Delete requires owner, super_admin, admin, or original creator within 24h'''
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if has_global_role(user, 'owner', 'super_admin', 'admin'):
        return True, ''

    # Check if user is event owner
    if event and hasattr(event, 'is_owned_by_user'):
        if event.is_owned_by_user(user.id):
            return True, ''
    elif event and hasattr(event, 'get'):
        if event.get('organizer_id') == user.id:
            return True, ''

    # Original creator grace period
    # Check if event has original_creator_id and created_at
    if event and hasattr(event, 'original_creator_id') and event.original_creator_id == user.id:
        if hasattr(event, 'created_at') and event.created_at:
            from datetime import datetime, timedelta
            if datetime.utcnow() - event.created_at < timedelta(hours=24):
                return True, ''

    return False, 'Not authorized to delete'

def can_view_analytics(user, event) -> Tuple[bool, str]:
    '''Analytics access: global admins, event_manager, org admins, finance managers'''
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if has_global_role(user, 'owner', 'super_admin', 'admin', 'event_manager'):
        return True, ''

    # Check if user is event owner
    if event and hasattr(event, 'is_owned_by_user'):
        if event.is_owned_by_user(user.id):
            return True, ''
    elif event and hasattr(event, 'get'):
        if event.get('organizer_id') == user.id:
            return True, ''

    # Check if user is org admin or finance manager
    org_id = None
    if event and hasattr(event, 'current_owner_id'):
        org_id = event.current_owner_id
    elif event and hasattr(event, 'get'):
        org_id = event.get('organisation_id')

    if org_id:
        if has_org_role(user, org_id, 'org_owner', 'org_admin', 'finance_manager'):
            return True, ''

    return False, 'Not authorized to view analytics'

def can_check_in(user, event) -> Tuple[bool, str]:
    '''Check-in access: global admins, event_manager, org admins, stewards'''
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'

    if has_global_role(user, 'owner', 'super_admin', 'admin', 'event_manager'):
        return True, ''

    # Check if user is event owner
    if event and hasattr(event, 'is_owned_by_user'):
        if event.is_owned_by_user(user.id):
            return True, ''
    elif event and hasattr(event, 'get'):
        if event.get('organizer_id') == user.id:
            return True, ''

    # Check if user is org admin
    org_id = None
    if event and hasattr(event, 'current_owner_id'):
        org_id = event.current_owner_id
    elif event and hasattr(event, 'get'):
        org_id = event.get('organisation_id')

    if org_id:
        if has_org_role(user, org_id, 'org_owner', 'org_admin'):
            return True, ''

    # Check event-specific staff role
    from app.events.models import EventRole
    if event and hasattr(event, 'id'):
        staff = EventRole.query.filter_by(event_id=event.id, user_id=user.id, is_active=True).first()
        if staff and staff.role in ['steward', 'co_organizer']:
            return True, ''

    return False, 'Not authorized to check in attendees'


def require_event_permission(user, event, action: str) -> Tuple[bool, str]:
    """
    Check if user has permission to perform an action on an event.
    Returns: (has_permission, error_message)
    
    Actions: view, edit, delete, approve, reject, suspend, reactivate, pause, resume
    """
    if not user or not user.is_authenticated:
        return False, 'Not authenticated'
    
    # System admins can do anything
    if is_system_admin(user):
        return True, ''
    
    # Define allowed state transitions
    ALLOWED_TRANSITIONS = {
        'approve': [EventStatus.PENDING_APPROVAL],
        'reject': [EventStatus.PENDING_APPROVAL],
        'suspend': [EventStatus.LIVE],
        'reactivate': [EventStatus.SUSPENDED, EventStatus.PAUSED],
        'pause': [EventStatus.LIVE],
        'resume': [EventStatus.PAUSED],
        'delete': [EventStatus.DRAFT, EventStatus.REJECTED, EventStatus.CANCELLED, EventStatus.ARCHIVED],
    }
    
    # Check if action requires specific status
    if action in ALLOWED_TRANSITIONS:
        if event.status not in ALLOWED_TRANSITIONS[action]:
            return False, f'Cannot {action} event with status {event.status.value}'
    
    # Check ownership for certain actions
    if action in ['edit', 'delete', 'pause', 'resume']:
        # Event organizers can edit/delete their own events
        if event.organizer_id == user.id:
            return True, ''
        
        # Organization admins can manage their organization's events
        if event.organisation_id and is_organization_admin(user, event.organisation_id):
            return True, ''
        
        return False, 'Not authorized'
    
    # For approve/reject/suspend/reactivate, need event_manager or higher
    if action in ['approve', 'reject', 'suspend', 'reactivate']:
        if has_global_role(user, 'event_manager', 'admin', 'super_admin', 'owner'):
            return True, ''
        return False, 'Only event managers and above can perform this action'
    
    # Default: check if user can manage the event
    return can_manage_event(user, event)

def can_check_in_attendees(user, event) -> bool:
    """
    Check if user can check in attendees (Stewards, Volunteers)
    """
    # Use the new can_check_in function
    can_check, _ = can_check_in(user, event)
    return can_check


def can_view_event_stats(user, event) -> bool:
    """
    Check if user can view event statistics
    """
    if not user or not user.is_authenticated:
        return False

    # System admin, event organizer, and organization admin can view stats
    # Use can_manage_event but only check the boolean part
    can_manage, _ = can_manage_event(user, event)
    return can_manage


def get_user_event_permissions(user, event_slug: str) -> dict:
    """
    Get all permissions for a user on a specific event
    Returns a dict of boolean permissions
    """
    from app.events.services import EventService

    event = EventService.get_event(event_slug)
    if not event:
        return {
            'can_view': False,
            'can_edit': False,
            'can_delete': False,
            'can_manage_staff': False,
            'can_view_attendees': False,
            'can_check_in': False,
            'can_approve': False,
            'role': None
        }

    event_model = EventService.get_event_model(event_slug)

    permissions = {
        'can_view': True,  # Anyone can view event landing page
        'can_edit': False,
        'can_delete': False,
        'can_manage_staff': False,
        'can_view_attendees': False,
        'can_check_in': False,
        'can_approve': can_approve_event(current_user, event)[0] if current_user.is_authenticated else False,
        'role': None
    }

    if not current_user.is_authenticated:
        return permissions

    # System admin has all permissions
    if is_system_admin(current_user):
        permissions.update({
            'can_edit': True,
            'can_delete': True,
            'can_manage_staff': True,
            'can_view_attendees': True,
            'can_check_in': True,
            'role': 'system_admin'
        })
        return permissions

    # Check if user is event organizer
    if event.get('organizer_id') == current_user.id:
        permissions.update({
            'can_edit': True,
            'can_delete': True,
            'can_manage_staff': True,
            'can_view_attendees': True,
            'can_check_in': True,
            'role': 'organizer'
        })
        return permissions

    # Check if user is organization admin
    if event.get('organisation_id') and is_organization_admin(current_user, event.get('organisation_id')):
        permissions.update({
            'can_edit': True,
            'can_delete': True,
            'can_manage_staff': True,
            'can_view_attendees': True,
            'can_check_in': True,
            'role': 'org_admin'
        })
        return permissions

    # Check for event-specific roles
    if event_model:
        from app.events.models import EventRole
        role = EventRole.query.filter_by(
            event_id=event_model.id,
            user_id=current_user.id,
            is_active=True
        ).first()

        if role:
            permissions['role'] = role.role
            if role.role in ['co_organizer', 'steward']:
                permissions.update({
                    'can_edit': role.role == 'co_organizer',
                    'can_view_attendees': True,
                    'can_check_in': role.role in ['steward', 'volunteer'],
                })

    return permissions
