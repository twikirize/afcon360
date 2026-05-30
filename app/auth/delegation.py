# app/auth/delegation.py
"""
Role-based delegation system for AFCON360

Implements cascading permissions:
- Owner → Super Admin → Admin → User
- Configurable delegation rules
- Audit trail for all delegation actions
- Time-limited delegations
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

from app.extensions import db
from app.audit.comprehensive_audit import AuditService


class DelegationScope(str, Enum):
    """Types of delegation scopes"""
    PAYMENT_GATEWAYS = 'payment_gateways'
    WALLET_MANAGEMENT = 'wallet_management'
    USER_MANAGEMENT = 'user_management'
    COMPLIANCE_ACCESS = 'compliance_access'
    FINANCIAL_CONTROLLER = 'financial_controller'
    REGULATOR_ACCESS = 'regulator_access'
    SYSTEM_SETTINGS = 'system_settings'


class DelegationRule:
    """Represents a delegation rule"""
    
    def __init__(self, delegator_role: str, delegatee_role: str, 
                 allowed_scopes: List[DelegationScope], 
                 max_duration_hours: int = 24,
                 requires_approval: bool = False):
        self.delegator_role = delegator_role
        self.delegatee_role = delegatee_role
        self.allowed_scopes = allowed_scopes
        self.max_duration_hours = max_duration_hours
        self.requires_approval = requires_approval


class DelegationService:
    """Service for managing role-based delegations"""
    
    # Define delegation rules
    DELEGATION_RULES = {
        # Owner can delegate to Super Admin
        ('owner', 'super_admin'): DelegationRule(
            delegator_role='owner',
            delegatee_role='super_admin',
            allowed_scopes=[
                DelegationScope.PAYMENT_GATEWAYS,
                DelegationScope.WALLET_MANAGEMENT,
                DelegationScope.USER_MANAGEMENT,
                DelegationScope.COMPLIANCE_ACCESS,
                DelegationScope.FINANCIAL_CONTROLLER,
                DelegationScope.REGULATOR_ACCESS,
                DelegationScope.SYSTEM_SETTINGS
            ],
            max_duration_hours=168,  # 7 days
            requires_approval=False
        ),
        
        # Super Admin can delegate to Admin
        ('super_admin', 'admin'): DelegationRule(
            delegator_role='super_admin',
            delegatee_role='admin',
            allowed_scopes=[
                DelegationScope.PAYMENT_GATEWAYS,
                DelegationScope.WALLET_MANAGEMENT,
                DelegationScope.COMPLIANCE_ACCESS,
                DelegationScope.FINANCIAL_CONTROLLER
            ],
            max_duration_hours=72,  # 3 days
            requires_approval=True
        ),
        
        # Admin can delegate to User (limited)
        ('admin', 'user'): DelegationRule(
            delegator_role='admin',
            delegatee_role='user',
            allowed_scopes=[
                DelegationScope.WALLET_MANAGEMENT
            ],
            max_duration_hours=24,  # 1 day
            requires_approval=True
        )
    }
    
    def __init__(self):
        self.active_delegations = {}
    
    def can_delegate(self, delegator_role: str, delegatee_role: str, 
                   scope: DelegationScope) -> Dict[str, Any]:
        """
        Check if delegation is allowed
        
        Args:
            delegator_role: Role of person delegating
            delegatee_role: Role of person receiving delegation
            scope: Specific permission scope being delegated
            
        Returns:
            Dict with delegation permission details
        """
        rule_key = (delegator_role, delegatee_role)
        rule = self.DELEGATION_RULES.get(rule_key)
        
        if not rule:
            return {
                'allowed': False,
                'error': f'No delegation rule for {delegator_role} → {delegatee_role}',
                'requires_approval': False,
                'max_duration_hours': 0
            }
        
        if scope not in rule.allowed_scopes:
            return {
                'allowed': False,
                'error': f'Scope {scope} not allowed for {delegator_role} → {delegatee_role}',
                'requires_approval': rule.requires_approval,
                'max_duration_hours': rule.max_duration_hours
            }
        
        return {
            'allowed': True,
            'error': None,
            'requires_approval': rule.requires_approval,
            'max_duration_hours': rule.max_duration_hours
        }
    
    def create_delegation(self, delegator_id: int, delegatee_id: int,
                       delegator_role: str, delegatee_role: str,
                       scopes: List[DelegationScope], duration_hours: int,
                       reason: str, approved_by: Optional[int] = None) -> Dict[str, Any]:
        """
        Create a new delegation
        
        Args:
            delegator_id: User ID of delegator
            delegatee_id: User ID of delegatee
            delegator_role: Role of delegator
            delegatee_role: Role of delegatee
            scopes: List of scopes to delegate
            duration_hours: Duration in hours
            reason: Reason for delegation
            approved_by: User ID who approved (if required)
            
        Returns:
            Dict with delegation result
        """
        try:
            # Check delegation rules
            for scope in scopes:
                permission = self.can_delegate(delegator_role, delegatee_role, scope)
                if not permission['allowed']:
                    return {
                        'success': False,
                        'error': f"Cannot delegate scope {scope}: {permission['error']}"
                    }
            
            # Check duration
            rule_key = (delegator_role, delegatee_role)
            rule = self.DELEGATION_RULES[rule_key]
            
            if duration_hours > rule.max_duration_hours:
                return {
                    'success': False,
                    'error': f"Duration exceeds maximum of {rule.max_duration_hours} hours"
                }
            
            # Check if approval is required
            if rule.requires_approval and not approved_by:
                return {
                    'success': False,
                    'error': 'This delegation requires approval',
                    'requires_approval': True
                }
            
            # Create delegation record
            delegation_id = f"DEL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            expires_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
            
            delegation = {
                'delegation_id': delegation_id,
                'delegator_id': delegator_id,
                'delegatee_id': delegatee_id,
                'delegator_role': delegator_role,
                'delegatee_role': delegatee_role,
                'scopes': [scope.value for scope in scopes],
                'created_at': datetime.now(timezone.utc).isoformat(),
                'expires_at': expires_at.isoformat(),
                'duration_hours': duration_hours,
                'reason': reason,
                'approved_by': approved_by,
                'is_active': True
            }
            
            # Store delegation (simplified - would use proper database)
            self.active_delegations[delegation_id] = delegation
            
            # Log delegation creation
            AuditService.compliance(
                action="delegation_created",
                delegation_id=delegation_id,
                delegator_id=delegator_id,
                delegatee_id=delegatee_id,
                scopes=[scope.value for scope in scopes],
                expires_at=expires_at.isoformat(),
                reason=reason,
                approved_by=approved_by,
                metadata={
                    "delegator_role": delegator_role,
                    "delegatee_role": delegatee_role,
                    "requires_approval": rule.requires_approval
                }
            )
            
            return {
                'success': True,
                'delegation_id': delegation_id,
                'expires_at': expires_at.isoformat(),
                'scopes': [scope.value for scope in scopes]
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to create delegation: {str(e)}'
            }
    
    def revoke_delegation(self, delegation_id: str, revoked_by: int, reason: str) -> Dict[str, Any]:
        """
        Revoke an active delegation
        
        Args:
            delegation_id: ID of delegation to revoke
            revoked_by: User ID revoking delegation
            reason: Reason for revocation
            
        Returns:
            Dict with revocation result
        """
        try:
            delegation = self.active_delegations.get(delegation_id)
            
            if not delegation:
                return {
                    'success': False,
                    'error': 'Delegation not found'
                }
            
            if not delegation['is_active']:
                return {
                    'success': False,
                    'error': 'Delegation already revoked'
                }
            
            # Mark as revoked
            delegation['is_active'] = False
            delegation['revoked_at'] = datetime.now(timezone.utc).isoformat()
            delegation['revoked_by'] = revoked_by
            delegation['revocation_reason'] = reason
            
            # Log revocation
            AuditService.compliance(
                action="delegation_revoked",
                delegation_id=delegation_id,
                revoked_by=revoked_by,
                reason=reason,
                metadata={
                    "original_delegator": delegation['delegator_id'],
                    "original_delegatee": delegation['delegatee_id'],
                    "scopes": delegation['scopes']
                }
            )
            
            return {
                'success': True,
                'message': 'Delegation revoked successfully'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to revoke delegation: {str(e)}'
            }
    
    def get_active_delegations(self, user_id: int = None) -> List[Dict[str, Any]]:
        """
        Get active delegations
        
        Args:
            user_id: Filter by specific user ID (optional)
            
        Returns:
            List of active delegations
        """
        delegations = []
        
        for delegation_id, delegation in self.active_delegations.items():
            if delegation['is_active']:
                if user_id is None or delegation['delegatee_id'] == user_id:
                    # Check if expired
                    expires_at = datetime.fromisoformat(delegation['expires_at'])
                    if expires_at > datetime.now(timezone.utc):
                        delegations.append(delegation)
                    else:
                        # Auto-expire
                        delegation['is_active'] = False
                        delegation['expired_at'] = datetime.now(timezone.utc).isoformat()
        
        return delegations
    
    def check_delegation_permission(self, user_id: int, required_scope: DelegationScope) -> bool:
        """
        Check if user has permission through delegation
        
        Args:
            user_id: User ID to check
            required_scope: Required permission scope
            
        Returns:
            Boolean indicating if permission is granted
        """
        user_delegations = self.get_active_delegations(user_id)
        
        for delegation in user_delegations:
            if required_scope.value in delegation['scopes']:
                # Check if delegation is still valid
                expires_at = datetime.fromisoformat(delegation['expires_at'])
                if expires_at > datetime.now(timezone.utc):
                    return True
        
        return False
    
    def get_delegation_rules(self) -> Dict[str, Any]:
        """
        Get all delegation rules for display
        
        Returns:
            Dict of delegation rules
        """
        rules = {}
        
        for (delegator, delegatee), rule in self.DELEGATION_RULES.items():
            rules[f"{delegator}_to_{delegatee}"] = {
                'delegator_role': delegator,
                'delegatee_role': delegatee,
                'allowed_scopes': [scope.value for scope in rule.allowed_scopes],
                'max_duration_hours': rule.max_duration_hours,
                'requires_approval': rule.requires_approval
            }
        
        return rules
    
    def cleanup_expired_delegations(self) -> int:
        """
        Clean up expired delegations
        
        Returns:
            Number of delegations cleaned up
        """
        cleaned_count = 0
        current_time = datetime.now(timezone.utc)
        
        for delegation_id, delegation in self.active_delegations.items():
            if delegation['is_active']:
                expires_at = datetime.fromisoformat(delegation['expires_at'])
                if expires_at <= current_time:
                    delegation['is_active'] = False
                    delegation['expired_at'] = current_time.isoformat()
                    cleaned_count += 1
                    
                    # Log expiration
                    AuditService.compliance(
                        action="delegation_expired",
                        delegation_id=delegation_id,
                        expired_at=current_time.isoformat(),
                        metadata={
                            "original_delegator": delegation['delegator_id'],
                            "original_delegatee": delegation['delegatee_id'],
                            "scopes": delegation['scopes']
                        }
                    )
        
        return cleaned_count
