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
        
        # Get permissions for user's role
        role_permissions = get_role_permissions(membership.role)
        
        return permission in role_permissions
    
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
        
        return set(get_role_permissions(membership.role))
    
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
        
        return membership.role
    
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
        """Get list of modules user can access in organization"""
        if not OrganizationPermissionService.is_member(user, organization):
            return []
        
        modules = organization.get_active_modules()
        accessible_modules = []
        
        # Check module-specific permissions
        if 'events' in modules and OrganizationPermissionService.can_create_events(user, organization):
            accessible_modules.append('events')
        
        if 'accommodation' in modules and OrganizationPermissionService.can_manage_accommodation(user, organization):
            accessible_modules.append('accommodation')
        
        if 'transport' in modules and OrganizationPermissionService.can_manage_transport(user, organization):
            accessible_modules.append('transport')
        
        if 'wallet' in modules and OrganizationPermissionService.can_manage_wallet(user, organization):
            accessible_modules.append('wallet')
        
        if 'tourism' in modules and OrganizationPermissionService.can_manage_tourism(user, organization):
            accessible_modules.append('tourism')
        
        # Always add basic modules for managers and above
        if OrganizationPermissionService.is_manager(user, organization):
            if 'staff' not in accessible_modules:
                accessible_modules.append('staff')
            if 'reports' not in accessible_modules:
                accessible_modules.append('reports')
        
        # Add settings for admins and owners
        if OrganizationPermissionService.is_admin(user, organization):
            if 'settings' not in accessible_modules:
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
        """Get organization role hierarchy"""
        hierarchy = {
            'executive': [],
            'management': [],
            'staff': [],
            'support': []
        }
        
        members = OrganisationMember.query.filter_by(
            organisation_id=organization.id,
            is_active=True,
            is_deleted=False
        ).all()
        
        for member in members:
            user_info = {
                'user_id': member.user_id,
                'username': member.user.username,
                'email': member.user.email,
                'role': member.role.value,
                'joined_at': member.created_at
            }
            
            if member.role in [OrganizationRole.ORG_OWNER, OrganizationRole.ORG_ADMIN]:
                hierarchy['executive'].append(user_info)
            elif member.role in [OrganizationRole.ORG_MANAGER, OrganizationRole.OPERATIONS_MANAGER, 
                                OrganizationRole.FINANCE_MANAGER, OrganizationRole.HR_MANAGER, 
                                OrganizationRole.MARKETING_MANAGER]:
                hierarchy['management'].append(user_info)
            elif member.role in [OrganizationRole.STAFF_MEMBER, OrganizationRole.AGENT, 
                                OrganizationRole.REPRESENTATIVE, OrganizationRole.EVENT_MANAGER,
                                OrganizationRole.TRANSPORT_MANAGER, OrganizationRole.ACCOMMODATION_MANAGER,
                                OrganizationRole.TOURISM_MANAGER]:
                hierarchy['staff'].append(user_info)
            else:
                hierarchy['support'].append(user_info)
        
        return hierarchy
    
    @staticmethod
    def validate_role_assignment(organization: Organisation, role: OrganizationRole) -> tuple[bool, str]:
        """Validate if role can be assigned to organization type"""
        available_roles = get_available_roles(organization.business_category)
        
        if role not in available_roles:
            return False, f"Role '{role.value}' is not available for {organization.business_category.value} organizations"
        
        return True, ""
