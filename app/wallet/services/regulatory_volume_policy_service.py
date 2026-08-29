"""
app/wallet/services/regulatory_volume_policy_service.py
Regulatory Volume Policy Management Service

Handles policy change requests, dual authorization, and audit logging.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from flask import current_app, request
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.wallet.models.regulatory_volume import (
    RegulatoryVolumePolicy,
    RegulatoryVolumePolicyChangeRequest,
    WindowMode,
)
from app.audit.forensic_audit import ForensicAuditService


class RegulatoryVolumePolicyService:
    """
    Service for managing regulatory volume calculation policies.
    
    Implements dual-authorization workflow for policy changes:
    - Owner/super_admin can request changes
    - Different owner/super_admin must approve
    - All changes are audit-logged with effective dates
    """
    
    # Roles authorized to manage regulatory volume policy
    AUTHORIZED_ROLES = {'owner', 'super_admin'}
    
    @classmethod
    def _require_authorization(cls) -> bool:
        """Check if current user has authorization to manage regulatory volume policy."""
        if not current_user or not current_user.is_authenticated:
            return False
        return any(current_user.has_role(role) for role in cls.AUTHORIZED_ROLES)
    
    @classmethod
    def get_current_policy(cls) -> Optional[RegulatoryVolumePolicy]:
        """Get the currently active regulatory volume policy."""
        return RegulatoryVolumePolicy.get_active_or_default()
    
    @classmethod
    def get_policy_status(cls) -> Dict[str, Any]:
        """Get comprehensive policy status for display."""
        policy = cls.get_current_policy()
        pending_request = RegulatoryVolumePolicyChangeRequest.query.filter_by(
            status=RegulatoryVolumePolicyChangeRequest.Status.PENDING
        ).order_by(RegulatoryVolumePolicyChangeRequest.requested_at.desc()).first()
        
        return {
            "active_policy": policy.to_dict() if policy else None,
            "pending_request": pending_request.to_dict() if pending_request else None,
            "can_request": cls._require_authorization(),
            "can_approve": cls._require_authorization() and (
                pending_request is not None and 
                pending_request.can_approve(current_user.id)
            ),
        }
    
    @classmethod
    def request_policy_change(
        cls,
        daily_mode: WindowMode,
        monthly_mode: WindowMode,
        tz: str = 'Africa/Kampala',
        effective_from: Optional[datetime] = None,
        reason: str = ''
    ) -> RegulatoryVolumePolicyChangeRequest:
        """
        Create a new policy change request.
        
        Requires owner/super_admin role.
        Does NOT activate the policy - requires separate approval.
        """
        if not cls._require_authorization():
            raise PermissionError("Only owner or super_admin can request regulatory volume policy changes")
        
        # Validate timezone
        import pytz
        if tz not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {tz}")
        
        # Create the change request
        change_request = RegulatoryVolumePolicyChangeRequest(
            proposed_daily_mode=daily_mode,
            proposed_monthly_mode=monthly_mode,
            proposed_timezone=tz,
            proposed_effective_from=effective_from or datetime.now(timezone.utc),
            requested_by=current_user.id,
            reason=reason,
            ip_address=request.remote_addr if request else None,
            user_agent=request.user_agent.string if request and request.user_agent else None,
        )
        
        db.session.add(change_request)
        db.session.commit()
        
        # Audit log the request
        ForensicAuditService.log_action(
            action='regulatory_volume_policy_change_requested',
            user_id=current_user.id,
            resource_type='regulatory_volume_policy',
            resource_id=str(change_request.id),
            details={
                'proposed_daily_mode': daily_mode.value,
                'proposed_monthly_mode': monthly_mode.value,
                'proposed_timezone': tz,
                'proposed_effective_from': change_request.proposed_effective_from.isoformat(),
                'reason': reason,
            },
            ip_address=request.remote_addr if request else None,
        )
        
        return change_request
    
    @classmethod
    def approve_policy_change(
        cls,
        change_request_id: int,
        reason: str = ''
    ) -> RegulatoryVolumePolicy:
        """
        Approve a pending policy change request.
        
        Requires owner/super_admin role AND must not be the requester.
        Creates new active policy with effective date.
        """
        if not cls._require_authorization():
            raise PermissionError("Only owner or super_admin can approve regulatory volume policy changes")
        
        change_request = db.session.get(RegulatoryVolumePolicyChangeRequest, change_request_id)
        if not change_request:
            raise ValueError(f"Change request {change_request_id} not found")
        
        if change_request.status != RegulatoryVolumePolicyChangeRequest.Status.PENDING:
            raise ValueError(f"Change request is not pending (status: {change_request.status.value})")
        
        if not change_request.can_approve(current_user.id):
            raise PermissionError("Requester cannot approve their own policy change")
        
        # Get current active policy to deactivate
        current_policy = RegulatoryVolumePolicy.get_active()
        
        # Create new active policy
        new_policy = RegulatoryVolumePolicy(
            daily_window_mode=change_request.proposed_daily_mode,
            monthly_window_mode=change_request.proposed_monthly_mode,
            timezone=change_request.proposed_timezone,
            is_active=True,
            effective_from=change_request.proposed_effective_from,
            requested_by=change_request.requested_by,
            requested_at=change_request.requested_at,
            approved_by=current_user.id,
            approved_at=datetime.now(timezone.utc),
            reason=reason or change_request.reason,
            previous_policy_id=current_policy.id if current_policy else None,
        )
        
        # Deactivate current policy if exists
        if current_policy:
            current_policy.is_active = False
            current_policy.effective_until = change_request.proposed_effective_from
            # If the new policy is effective immediately, deactivate now
            if change_request.proposed_effective_from <= datetime.now(timezone.utc):
                current_policy.is_active = False
        
        # Update change request
        change_request.status = RegulatoryVolumePolicyChangeRequest.Status.APPROVED
        change_request.approved_by = current_user.id
        change_request.approved_at = datetime.now(timezone.utc)
        change_request.resulting_policy_id = new_policy.id
        
        db.session.add(new_policy)
        db.session.commit()
        
        # Audit log the approval
        ForensicAuditService.log_action(
            action='regulatory_volume_policy_change_approved',
            user_id=current_user.id,
            resource_type='regulatory_volume_policy',
            resource_id=str(new_policy.id),
            details={
                'change_request_id': change_request_id,
                'old_policy_id': current_policy.id if current_policy else None,
                'new_daily_mode': new_policy.daily_window_mode.value,
                'new_monthly_mode': new_policy.monthly_window_mode.value,
                'new_timezone': new_policy.timezone,
                'effective_from': new_policy.effective_from.isoformat(),
                'reason': reason,
            },
            ip_address=request.remote_addr if request else None,
        )
        
        return new_policy
    
    @classmethod
    def reject_policy_change(
        cls,
        change_request_id: int,
        rejection_reason: str
    ) -> RegulatoryVolumePolicyChangeRequest:
        """
        Reject a pending policy change request.
        
        Requires owner/super_admin role AND must not be the requester.
        """
        if not cls._require_authorization():
            raise PermissionError("Only owner or super_admin can reject regulatory volume policy changes")
        
        change_request = db.session.get(RegulatoryVolumePolicyChangeRequest, change_request_id)
        if not change_request:
            raise ValueError(f"Change request {change_request_id} not found")
        
        if change_request.status != RegulatoryVolumePolicyChangeRequest.Status.PENDING:
            raise ValueError(f"Change request is not pending (status: {change_request.status.value})")
        
        if not change_request.can_reject(current_user.id):
            raise PermissionError("Requester cannot reject their own policy change")
        
        change_request.status = RegulatoryVolumePolicyChangeRequest.Status.REJECTED
        change_request.rejected_by = current_user.id
        change_request.rejected_at = datetime.now(timezone.utc)
        change_request.rejection_reason = rejection_reason
        
        db.session.commit()
        
        # Audit log the rejection
        ForensicAuditService.log_action(
            action='regulatory_volume_policy_change_rejected',
            user_id=current_user.id,
            resource_type='regulatory_volume_policy_change',
            resource_id=str(change_request_id),
            details={
                'rejection_reason': rejection_reason,
                'original_request': change_request.to_dict(),
            },
            ip_address=request.remote_addr if request else None,
        )
        
        return change_request
    
    @classmethod
    def get_change_history(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """Get history of policy change requests."""
        changes = RegulatoryVolumePolicyChangeRequest.query.order_by(
            RegulatoryVolumePolicyChangeRequest.requested_at.desc()
        ).limit(limit).all()
        
        return [c.to_dict() for c in changes]
    
    @classmethod
    def get_policies_history(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """Get history of active policies."""
        policies = RegulatoryVolumePolicy.query.order_by(
            RegulatoryVolumePolicy.effective_from.desc()
        ).limit(limit).all()
        
        return [p.to_dict() for p in policies]


__all__ = ['RegulatoryVolumePolicyService']