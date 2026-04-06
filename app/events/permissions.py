# app/events/permissions.py
"""
Event Permissions - Role-based access control for events
Handles System Admin, Organization Admin, and Event Organizer permissions
"""

from flask_login import current_user
from app.extensions import db


def is_system_admin(user) -> bool:
    """
    Check if user is a System Admin (Super Admin)
    System Admins can manage ALL events platform-wide
    """
    if not user or not user.is_authenticated:
        return False
    return user.is_super_admin() if hasattr(user, 'is_super_admin') else False


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
        return user.has_org_role(organisation_id, "org_owner", "org_admin")

    # Otherwise check if user is admin of ANY organization
    for membership in user.organisations:
        if user.has_org_role(membership.organisation_id, "org_owner", "org_admin"):
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


def can_manage_event(user, event) -> bool:
    """
    Check if user can manage an event (create, edit, delete)
    """
    if not user or not user.is_authenticated:
        return False

    # System admin can manage any event
    if is_system_admin(user):
        return True

    # Event organizer can manage their own events
    if event and event.get('organizer_id') == user.id:
        return True

    # Organization admin can manage events for their org
    if event and event.get('organisation_id'):
        return is_organization_admin(user, event.get('organisation_id'))

    return False


def can_view_event_stats(user, event) -> bool:
    """
    Check if user can view event statistics
    """
    if not user or not user.is_authenticated:
        return False

    # System admin, event organizer, and organization admin can view stats
    return can_manage_event(user, event)


def can_check_in_attendees(user, event) -> bool:
    """
    Check if user can check in attendees (Stewards, Volunteers)
    """
    if not user or not user.is_authenticated:
        return False

    # System admin and event organizer can check in
    if can_manage_event(user, event):
        return True

    # Check for event-specific roles
    from app.events.models import EventRole
    if event and event.get('event_id'):
        role = EventRole.query.filter_by(
            event_id=event.get('event_id'),
            user_id=user.id,
            is_active=True
        ).first()
        if role and role.role in ['steward', 'volunteer']:
            return True

    return False


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
        'can_approve': is_system_admin(current_user),  # Only system admin can approve events
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