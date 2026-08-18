# app/auth/delegation.py
"""
Role-based delegation system for AFCON360

Implements cascading permissions:
- Owner → Super Admin → Admin → User
- Configurable delegation rules
- Audit trail for all delegation actions
- Time-limited delegations

CHANGE FROM PRIOR VERSION: delegations are now persisted via the `Delegation`
model (app/auth/models/delegation.py) instead of an in-memory class-level
dict. The dict was invisible across gunicorn workers and lost on every
restart — this file's public method signatures are unchanged so existing
callers (e.g. RegistrationPermissionService) work without modification.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum
import secrets

from app.extensions import db
from app.audit.comprehensive_audit import AuditService
from app.auth.models.delegation import Delegation


class DelegationScope(str, Enum):
    """Types of delegation scopes"""
    PAYMENT_GATEWAYS = 'payment_gateways'
    WALLET_MANAGEMENT = 'wallet_management'
    USER_MANAGEMENT = 'user_management'
    COMPLIANCE_ACCESS = 'compliance_access'
    FINANCIAL_CONTROLLER = 'financial_controller'
    REGULATOR_ACCESS = 'regulator_access'
    SYSTEM_SETTINGS = 'system_settings'
    ACCOMMODATION_REGISTRATION_MANAGEMENT = 'accommodation_registration_management'


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

    DELEGATION_RULES = {
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
            max_duration_hours=168,
            requires_approval=False
        ),
        ('super_admin', 'admin'): DelegationRule(
            delegator_role='super_admin',
            delegatee_role='admin',
            allowed_scopes=[
                DelegationScope.PAYMENT_GATEWAYS,
                DelegationScope.WALLET_MANAGEMENT,
                DelegationScope.COMPLIANCE_ACCESS,
                DelegationScope.FINANCIAL_CONTROLLER,
                DelegationScope.ACCOMMODATION_REGISTRATION_MANAGEMENT
            ],
            max_duration_hours=72,
            requires_approval=True
        ),
        ('admin', 'user'): DelegationRule(
            delegator_role='admin',
            delegatee_role='user',
            allowed_scopes=[
                DelegationScope.WALLET_MANAGEMENT,
                DelegationScope.ACCOMMODATION_REGISTRATION_MANAGEMENT
            ],
            max_duration_hours=24,
            requires_approval=True
        ),
        ('user', 'user'): DelegationRule(
            delegator_role='user',
            delegatee_role='user',
            allowed_scopes=[DelegationScope.ACCOMMODATION_REGISTRATION_MANAGEMENT],
            max_duration_hours=168,
            requires_approval=False
        )
    }

    def can_delegate(self, delegator_role: str, delegatee_role: str,
                      scope: DelegationScope) -> Dict[str, Any]:
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
        try:
            for scope in scopes:
                permission = self.can_delegate(delegator_role, delegatee_role, scope)
                if not permission['allowed']:
                    return {
                        'success': False,
                        'error': f"Cannot delegate scope {scope}: {permission['error']}"
                    }

            rule_key = (delegator_role, delegatee_role)
            rule = self.DELEGATION_RULES[rule_key]

            if duration_hours > rule.max_duration_hours:
                return {
                    'success': False,
                    'error': f"Duration exceeds maximum of {rule.max_duration_hours} hours"
                }

            if rule.requires_approval and not approved_by:
                return {
                    'success': False,
                    'error': 'This delegation requires approval',
                    'requires_approval': True
                }

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=duration_hours)
            reference = f"DEL-{now.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2).upper()}"

            delegation = Delegation(
                delegation_reference=reference,
                delegator_id=delegator_id,
                delegatee_id=delegatee_id,
                delegator_role=delegator_role,
                delegatee_role=delegatee_role,
                scopes=[scope.value for scope in scopes],
                reason=reason,
                duration_hours=duration_hours,
                requires_approval=rule.requires_approval,
                approved_by_user_id=approved_by,
                approved_at=now if approved_by else None,
                is_active=True,
                created_at=now,
                expires_at=expires_at,
            )
            db.session.add(delegation)
            db.session.commit()

            AuditService.compliance(
                action="delegation_created",
                delegation_id=reference,
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
                'delegation_id': reference,
                'expires_at': expires_at.isoformat(),
                'scopes': [scope.value for scope in scopes]
            }

        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': f'Failed to create delegation: {str(e)}'
            }

    def revoke_delegation(self, delegation_id: str, revoked_by: int, reason: str) -> Dict[str, Any]:
        delegation = Delegation.query.filter_by(delegation_reference=delegation_id).first()

        if not delegation:
            return {'success': False, 'error': 'Delegation not found'}

        if not delegation.is_active:
            return {'success': False, 'error': 'Delegation already revoked'}

        delegation.revoke(revoked_by, reason)
        db.session.commit()

        AuditService.compliance(
            action="delegation_revoked",
            delegation_id=delegation_id,
            revoked_by=revoked_by,
            reason=reason,
            metadata={
                "original_delegator": delegation.delegator_id,
                "original_delegatee": delegation.delegatee_id,
                "scopes": delegation.scopes,
            }
        )

        return {'success': True, 'message': 'Delegation revoked successfully'}

    def get_active_delegations(self, user_id: int = None) -> List[Dict[str, Any]]:
        query = Delegation.query.filter(Delegation.is_active.is_(True))
        if user_id is not None:
            query = query.filter(Delegation.delegatee_id == user_id)

        results = []
        now = datetime.now(timezone.utc)
        for delegation in query.all():
            expires_at = delegation.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > now:
                results.append({
                    'delegation_id': delegation.delegation_reference,
                    'delegator_id': delegation.delegator_id,
                    'delegatee_id': delegation.delegatee_id,
                    'delegator_role': delegation.delegator_role,
                    'delegatee_role': delegation.delegatee_role,
                    'scopes': delegation.scopes,
                    'created_at': delegation.created_at.isoformat(),
                    'expires_at': delegation.expires_at.isoformat(),
                    'duration_hours': delegation.duration_hours,
                    'reason': delegation.reason,
                    'approved_by': delegation.approved_by_user_id,
                    'is_active': delegation.is_active,
                })
            else:
                # Auto-expire lazily, same behavior as the prior in-memory version.
                delegation.is_active = False
        db.session.commit()
        return results

    def check_delegation_permission(self, user_id: int, required_scope: DelegationScope) -> bool:
        delegation = (
            Delegation.query
            .filter(
                Delegation.delegatee_id == user_id,
                Delegation.is_active.is_(True),
            )
            .filter(Delegation.expires_at > datetime.now(timezone.utc))
            .all()
        )
        for d in delegation:
            if d.has_scope(required_scope.value) and d.is_valid:
                return True
        return False

    def get_delegation_rules(self) -> Dict[str, Any]:
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
        now = datetime.now(timezone.utc)
        expired = Delegation.query.filter(
            Delegation.is_active.is_(True),
            Delegation.expires_at <= now,
        ).all()

        for delegation in expired:
            delegation.is_active = False
            AuditService.compliance(
                action="delegation_expired",
                delegation_id=delegation.delegation_reference,
                expired_at=now.isoformat(),
                metadata={
                    "original_delegator": delegation.delegator_id,
                    "original_delegatee": delegation.delegatee_id,
                    "scopes": delegation.scopes,
                }
            )
        db.session.commit()
        return len(expired)