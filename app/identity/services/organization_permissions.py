# app/identity/services/organization_permissions.py
"""
Organization-specific permission system
Handles role-based permissions for different organization types
"""

from typing import List, Dict, Set, Optional
from flask import current_app
from app.identity.models.organization_types import OrganizationType, OrganizationRole, get_role_permissions, get_available_roles
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember
from app.identity.models.user import User


class OrganizationPermissionService:
    """Service for managing organization permissions"""
    
    @staticmethod
    def has_permission(user: User, organization: Organisation, permission: str) -> bool:
        """Check if user has specific permission in organization"""
        # Get user's membership in organization
        membership = OrganisationMember.query.filter_by(
            user_id=user.id,
            organisation_id=organization.id,
            is_active=True,
            is_deleted=False
        ).first()
        
        if not membership:
            return False
        
        # New organisation memberships resolve permissions from OrgUserRole
        # assignments. Keep the legacy role fallback for older records.
        if hasattr(membership, 'has_permission'):
            return membership.has_permission(permission)
        role = getattr(membership, 'role', None)
        return permission in get_role_permissions(role) if role else False
    
    @staticmethod
    def has_any_permission(user: User, organization: Organisation, permissions: List[str]) -> bool:
        """Check if user has any of the specified permissions"""
        for permission in permissions:
            if OrganizationPermissionService.has_permission(user, organization, permission):
                return True
        return False
    
    @staticmethod
    def has_all_permissions(user: User, organization: Organisation, permissions: List[str]) -> bool:
        """Check if user has all of the specified permissions"""
        for permission in permissions:
            if not OrganizationPermissionService.has_permission(user, organization, permission):
                return False
        return True
    
    @staticmethod
    def get_user_permissions(user: User, organization: Organisation) -> Set[str]:
        """Get all permissions for user in organization"""
        membership = OrganisationMember.query.filter_by(
            user_id=user.id,
            organisation_id=organization.id,
            is_active=True,
            is_deleted=False
        ).first()
        
        if not membership:
            return set()
        
        if hasattr(membership, 'effective_permissions'):
            return set(membership.effective_permissions)
        role = getattr(membership, 'role', None)
        return set(get_role_permissions(role)) if role else set()
    
    @staticmethod
    def get_user_role(user: User, organization: Organisation) -> Optional[OrganizationRole]:
        """Get user's role in organization"""
        membership = OrganisationMember.query.filter_by(
            user_id=user.id,
            organisation_id=organization.id,
            is_active=True,
            is_deleted=False
        ).first()
        
        if not membership:
            return None
        
        legacy_role = getattr(membership, 'role', None)
        if legacy_role:
            return legacy_role
        for assigned_role in getattr(membership, 'roles', ()):
            role_name = getattr(getattr(assigned_role, 'role', None), 'name', None)
            if role_name:
                try:
                    return OrganizationRole(role_name)
                except ValueError:
                    continue
        return None
    
    @staticmethod
    def can_manage_staff(user: User, organization: Organisation) -> bool:
        """Check if user can manage organization staff"""
        return OrganizationPermissionService.has_permission(user, organization, 'org.manage_staff')
    
    @staticmethod
    def can_create_events(user: User, organization: Organisation) -> bool:
        """Check if user can create events"""
        if not organization.can_create_events():
            return False
        return OrganizationPermissionService.has_permission(user, organization, 'org.create_events')
    
    @staticmethod
    def can_manage_accommodation(user: User, organization: Organisation) -> bool:
        """Check if user can manage accommodation"""
        if not organization.can_manage_accommodation():
            return False
        return OrganizationPermissionService.has_permission(user, organization, 'org.manage_accommodation')
    
    @staticmethod
    def can_manage_transport(user: User, organization: Organisation) -> bool:
        """Check if user can manage transport"""
        if not organization.can_manage_transport():
            return False
        return OrganizationPermissionService.has_permission(user, organization, 'org.manage_transport')
    
    @staticmethod
    def can_manage_tourism(user: User, organization: Organisation) -> bool:
        """Check if user can manage tourism"""
        if not organization.can_manage_tourism():
            return False
        return OrganizationPermissionService.has_permission(user, organization, 'org.manage_tourism')
    
    @staticmethod
    def can_manage_wallet(user: User, organization: Organisation) -> bool:
        """Check if user can manage organization wallet"""
        return OrganizationPermissionService.has_permission(user, organization, 'org.manage_wallet')
    
    @staticmethod
    def can_view_reports(user: User, organization: Organisation) -> bool:
        """Check if user can view organization reports"""
        return OrganizationPermissionService.has_permission(user, organization, 'org.view_reports')
    
    @staticmethod
    def can_manage_settings(user: User, organization: Organisation) -> bool:
        """Check if user can manage organization settings"""
        return OrganizationPermissionService.has_permission(user, organization, 'org.manage_settings')
    
    @staticmethod
    def is_owner(user: User, organization: Organisation) -> bool:
        """Check if user is organization owner"""
        return OrganizationPermissionService.get_user_role(user, organization) == OrganizationRole.ORG_OWNER
    
    @staticmethod
    def is_admin(user: User, organization: Organisation) -> bool:
        """Check if user is organization admin"""
        role = OrganizationPermissionService.get_user_role(user, organization)
        return role in [OrganizationRole.ORG_OWNER, OrganizationRole.ORG_ADMIN]
    
    @staticmethod
    def is_manager(user: User, organization: Organisation) -> bool:
        """Check if user is organization manager"""
        role = OrganizationPermissionService.get_user_role(user, organization)
        return role in [
            OrganizationRole.ORG_OWNER, 
            OrganizationRole.ORG_ADMIN, 
            OrganizationRole.ORG_MANAGER
        ]
    
    @staticmethod
    def can_add_member(user: User, organization: Organisation, target_role: OrganizationRole) -> bool:
        """Check if user can add member with specific role"""
        user_role = OrganizationPermissionService.get_user_role(user, organization)
        
        # Owner can add any role
        if user_role == OrganizationRole.ORG_OWNER:
            return True
        
        # Admin can add roles below admin level
        if user_role == OrganizationRole.ORG_ADMIN:
            return target_role not in [OrganizationRole.ORG_OWNER, OrganizationRole.ORG_ADMIN]
        
        # Manager can add staff and below
        if user_role == OrganizationRole.ORG_MANAGER:
            return target_role in [OrganizationRole.STAFF_MEMBER, OrganizationRole.VIEWER, OrganizationRole.GUEST]
        
        return False
    
    @staticmethod
    def can_remove_member(user: User, organization: Organisation, target_user: User) -> bool:
        """Check if user can remove target member from organization"""
        user_role = OrganizationPermissionService.get_user_role(user, organization)
        target_role = OrganizationPermissionService.get_user_role(target_user, organization)
        
        # Cannot remove if not a member
        if not target_role:
            return False
        
        # Owner cannot be removed by anyone except themselves
        if target_role == OrganizationRole.ORG_OWNER:
            return user.id == target_user.id
        
        # Admin can remove non-owners
        if user_role == OrganizationRole.ORG_ADMIN:
            return target_role != OrganizationRole.ORG_OWNER
        
        # Manager can remove staff and below
        if user_role == OrganizationRole.ORG_MANAGER:
            return target_role in [OrganizationRole.STAFF_MEMBER, OrganizationRole.VIEWER, OrganizationRole.GUEST]
        
        return False
    
    @staticmethod
    def can_change_role(user: User, organization: Organisation, target_user: User, new_role: OrganizationRole) -> bool:
        """Check if user can change target member's role"""
        user_role = OrganizationPermissionService.get_user_role(user, organization)
        target_role = OrganizationPermissionService.get_user_role(target_user, organization)
        
        # Cannot change role if not a member
        if not target_role:
            return False
        
        # Cannot change owner role
        if target_role == OrganizationRole.ORG_OWNER or new_role == OrganizationRole.ORG_OWNER:
            return False
        
        # Admin can change roles below admin
        if user_role == OrganizationRole.ORG_ADMIN:
            return target_role != OrganizationRole.ORG_ADMIN and new_role != OrganizationRole.ORG_ADMIN
        
        # Manager can change staff roles
        if user_role == OrganizationRole.ORG_MANAGER:
            return (target_role in [OrganizationRole.STAFF_MEMBER, OrganizationRole.VIEWER, OrganizationRole.GUEST] and
                    new_role in [OrganizationRole.STAFF_MEMBER, OrganizationRole.VIEWER, OrganizationRole.GUEST])
        
        return False
    
    @staticmethod
    def get_available_roles_for_user(user: User, organization: Organisation) -> List[OrganizationRole]:
        """Get roles that user can assign in organization"""
        user_role = OrganizationPermissionService.get_user_role(user, organization)
        
        if not user_role:
            return []
        
        # Get all available roles for organization type
        all_roles = get_available_roles(organization.business_category)
        
        # Filter based on user's role
        assignable_roles = []
        
        if user_role == OrganizationRole.ORG_OWNER:
            # Owner can assign any role
            assignable_roles = all_roles
        elif user_role == OrganizationRole.ORG_ADMIN:
            # Admin can assign roles below admin
            assignable_roles = [role for role in all_roles if role != OrganizationRole.ORG_OWNER]
        elif user_role == OrganizationRole.ORG_MANAGER:
            # Manager can assign staff roles
            assignable_roles = [role for role in all_roles if role in [
                OrganizationRole.STAFF_MEMBER, OrganizationRole.VIEWER, OrganizationRole.GUEST
            ]]
        
        return assignable_roles
    
    @staticmethod
    def get_accessible_modules(user: User, organization: Organisation) -> List[str]:
        """Get list of modules user can access in organization.

        Derived from canonical ``org.*`` permissions only. Legacy
        ``org.manage_*`` gates are never consulted (they are not seeded).
        Modules with no canonical permission definition (events, tourism,
        wallet, reports) stay closed by design (fail-closed): a disabled or
        unspecified module must never be silently opened.
        """
        if not OrganizationPermissionService.is_member(user, organization):
            return []

        modules = organization.get_active_modules()
        accessible_modules = []

        # Org administration - canonical org.members.view
        if OrganizationPermissionService.has_permission(user, organization, 'org.members.view'):
            accessible_modules.append('staff')

        # Domain modules gated by their canonical manage permission
        if 'accommodation' in modules and OrganizationPermissionService.has_permission(
            user, organization, 'org.accommodation.manage'
        ):
            accessible_modules.append('accommodation')

        if 'transport' in modules and OrganizationPermissionService.has_permission(
            user, organization, 'org.transport.manage'
        ):
            accessible_modules.append('transport')

        # Settings - canonical org.settings.manage
        if OrganizationPermissionService.has_permission(user, organization, 'org.settings.manage'):
            accessible_modules.append('settings')

        return accessible_modules
    
    @staticmethod
    def is_member(user: User, organization: Organisation) -> bool:
        """Check if user is a member of organization"""
        membership = OrganisationMember.query.filter_by(
            user_id=user.id,
            organisation_id=organization.id,
            is_active=True,
            is_deleted=False
        ).first()
        
        return membership is not None
    
    @staticmethod
    def get_organization_hierarchy(organization: Organisation) -> Dict[str, List]:
        """Get organization role hierarchy from canonical role assignments.

        A canonical ``OrganisationMember`` never carries ``member.role`` -
        roles live on ``OrgUserRole`` → ``OrgRole``. This builder reads the
        canonical chain and never touches the legacy ``OrganizationRole``
        enum. Each row exposes:
            user_id/public_id/username/email     identity
            role          primary canonical role name (first assignment)
            roles         all canonical role names for the member
            role_label    display label for ``role``
            permissions   sorted canonical permission names
            is_owner      True when ``org_owner`` is assigned
            member        the OrganisationMember object (for lifecycle UI)
        """
        hierarchy = {
            'executive': [],
            'management': [],
            'staff': [],
            'support': []
        }

        bucket_by_role = {
            'org_owner': 'executive',
            'org_admin': 'executive',
            'finance_manager': 'management',
            'transport_manager': 'management',
            'hr_manager': 'management',
            'project_manager': 'management',
            'dispatcher': 'staff',
            'org_member': 'staff',
            'org_guest': 'support',
        }

        members = OrganisationMember.query.filter_by(
            organisation_id=organization.id,
            is_active=True,
            is_deleted=False
        ).all()

        for member in members:
            role_names = sorted({
                our.role.name for our in member.roles if our.role and our.role.name
            })
            primary_role = role_names[0] if role_names else 'org_member'
            permissions = sorted(member.effective_permissions)

            user_info = {
                'user_id': member.user_id,
                'public_id': getattr(member.user, 'public_id', None),
                'username': member.user.username,
                'email': member.user.email,
                'role': primary_role,
                'roles': role_names,
                'role_label': primary_role.replace('_', ' ').title(),
                'permissions': permissions,
                'is_owner': 'org_owner' in role_names,
                'member': member,
            }

            bucket = bucket_by_role.get(primary_role, 'staff')
            hierarchy[bucket].append(user_info)

        return hierarchy
    
    @staticmethod
    def validate_role_assignment(organization: Organisation, role: OrganizationRole) -> tuple[bool, str]:
        """Validate if role can be assigned to organization type"""
        available_roles = get_available_roles(organization.business_category)
        
        if role not in available_roles:
            return False, f"Role '{role.value}' is not available for {organization.business_category.value} organizations"
        
        return True, ""
