"""
Profile Change Request Service - Role-based approval workflow for immutable field changes.

Only Owner and Super Admin have full approval privileges.
Compliance Officer has limited approval power for compliance-level changes.
All other roles are read-only for change requests.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from flask import current_app
from flask_login import current_user
from sqlalchemy import or_
from app.extensions import db
from app.profile.models import ProfileChangeRequest, UserProfile
from app.auth.roles import ROLE_OWNER, ROLE_SUPER_ADMIN, ROLE_COMPLIANCE_OFFICER


class ProfileChangeRequestService:
    """Service for managing profile change requests with role-based approval."""

    @classmethod
    def _user_has_approval_power(cls, user, level: str) -> bool:
        """
        Check if user has approval power at a specific level.

        Only Owner and Super Admin have full approval power.
        Compliance Officer has limited approval power.
        """
        role_names = user.role_names if hasattr(user, "role_names") else []

        # Owner has ALL approval power
        if user.is_app_owner() or ROLE_OWNER in role_names:
            return True

        # Super Admin has all approval power EXCEPT owner-level
        if ROLE_SUPER_ADMIN in role_names:
            if level == "owner":
                return False
            return True

        # Compliance Officer can only approve compliance-level
        if ROLE_COMPLIANCE_OFFICER in role_names:
            if level == "compliance":
                return True
            return False

        # Everyone else has NO approval power
        return False

    @classmethod
    def create_request(
        cls,
        profile: UserProfile,
        field_name: str,
        old_value: str,
        requested_value: str,
        requested_by: int,
        reason: str = None,
        require_admin_approval: bool = False,
        require_compliance_approval: bool = False,
        require_super_admin_approval: bool = False,
        require_owner_approval: bool = False,
    ) -> ProfileChangeRequest:
        """
        Create a new profile change request.

        Args:
            profile: The UserProfile being modified
            field_name: The field being changed
            old_value: The current value
            requested_value: The requested new value
            requested_by: User ID of the requester
            reason: Reason for the change
            require_admin_approval: Whether admin approval is required
            require_compliance_approval: Whether compliance approval is required
            require_super_admin_approval: Whether super admin approval is required
            require_owner_approval: Whether owner approval is required

        Returns:
            The created ProfileChangeRequest
        """
        request = ProfileChangeRequest(
            user_profile_id=profile.id,
            field_name=field_name,
            old_value=old_value,
            requested_value=requested_value,
            requested_by_user_id=requested_by,
            reason=reason,
            requires_admin_approval=require_admin_approval,
            requires_compliance_approval=require_compliance_approval,
            requires_super_admin_approval=require_super_admin_approval,
            requires_owner_approval=require_owner_approval,
        )
        db.session.add(request)
        db.session.commit()

        current_app.logger.info(
            f"Profile change request created: profile={profile.id}, "
            f"field={field_name}, requested_by={requested_by}"
        )

        return request

    @classmethod
    def get_pending_requests(cls) -> List[ProfileChangeRequest]:
        """Get all pending change requests."""
        return (
            ProfileChangeRequest.query.filter_by(status="pending")
            .order_by(ProfileChangeRequest.created_at.desc())
            .all()
        )

    @classmethod
    def get_requests_for_user(cls, user_id: int) -> List[ProfileChangeRequest]:
        """Get all change requests for a specific user profile."""
        return (
            ProfileChangeRequest.query.filter_by(
                requested_by_user_id=user_id,
            )
            .order_by(ProfileChangeRequest.created_at.desc())
            .all()
        )

    @classmethod
    def approve_request(
        cls,
        request_id: int,
        approver_id: int,
        approval_level: str,
        notes: Optional[str] = None,
    ) -> ProfileChangeRequest:
        """
        Approve a change request at a specific level.

        Args:
            request_id: The ID of the change request
            approver_id: The ID of the user approving
            approval_level: The level of approval (admin, compliance, super_admin, owner)
            notes: Optional notes about the approval

        Returns:
            The updated ProfileChangeRequest

        Raises:
            ValueError: If request not found or already processed
            PermissionError: If user lacks approval power at this level
        """
        request = db.session.get(ProfileChangeRequest, request_id)
        if not request:
            raise ValueError("Request not found")

        if request.status in ["approved", "applied", "rejected", "expired"]:
            raise ValueError(f"Cannot approve: request status is '{request.status}'")

        approver = db.session.get(type(request).__table__.columns, approver_id)
        from app.identity.models.user import User
        approver = db.session.get(User, approver_id)
        if not approver:
            raise ValueError("Approver not found")

        # Check if user has approval power at this level
        if not cls._user_has_approval_power(approver, approval_level):
            raise PermissionError(
                f"User does not have {approval_level} approval privileges. "
                f"Only Owner and Super Admin can approve changes."
            )

        # Validate approval level matches request requirements
        if approval_level == "admin":
            if not request.requires_admin_approval:
                raise ValueError("This request does not require admin approval")
            request.admin_approved = True
            request.admin_approved_by = approver_id
            request.admin_approved_at = datetime.now(timezone.utc)
            request.admin_approval_notes = notes

        elif approval_level == "compliance":
            if not request.requires_compliance_approval:
                raise ValueError("This request does not require compliance approval")
            if not cls._user_has_approval_power(approver, "compliance"):
                raise PermissionError("Only Compliance Officer can approve compliance-level changes")
            request.compliance_approved = True
            request.compliance_approved_by = approver_id
            request.compliance_approved_at = datetime.now(timezone.utc)
            request.compliance_approval_notes = notes

        elif approval_level == "super_admin":
            if not request.requires_super_admin_approval:
                raise ValueError("This request does not require super admin approval")
            if not cls._user_has_approval_power(approver, "super_admin"):
                raise PermissionError("Only Super Admin can approve super admin-level changes")
            request.super_admin_approved = True
            request.super_admin_approved_by = approver_id
            request.super_admin_approved_at = datetime.now(timezone.utc)
            request.super_admin_approval_notes = notes

        elif approval_level == "owner":
            if not request.requires_owner_approval:
                raise ValueError("This request does not require owner approval")
            if not cls._user_has_approval_power(approver, "owner"):
                raise PermissionError("Only Owner can approve owner-level changes")
            request.owner_approved = True
            request.owner_approved_by = approver_id
            request.owner_approved_at = datetime.now(timezone.utc)
            request.owner_approval_notes = notes

        else:
            raise ValueError(f"Unknown approval level: {approval_level}")

        request.add_audit_trail_entry(f"{approval_level}_approved", approver_id, notes)

        # Check if fully approved
        if request.is_fully_approved():
            request.status = "approved"
            request.approved_at = datetime.now(timezone.utc)
            request.add_audit_trail_entry("fully_approved", approver_id)

            # Apply the change
            cls._apply_change(request, approver_id)

        db.session.commit()
        return request

    @classmethod
    def reject_request(
        cls,
        request_id: int,
        rejector_id: int,
        reason: str,
    ) -> ProfileChangeRequest:
        """
        Reject a change request.

        Args:
            request_id: The ID of the change request
            rejector_id: The ID of the user rejecting
            reason: The reason for rejection

        Returns:
            The updated ProfileChangeRequest
        """
        request = db.session.get(ProfileChangeRequest, request_id)
        if not request:
            raise ValueError("Request not found")

        if request.status in ["approved", "applied", "rejected", "expired"]:
            raise ValueError(f"Cannot reject: request status is '{request.status}'")

        rejector = db.session.get(type(request).__table__.columns, rejector_id)
        from app.identity.models.user import User
        rejector = db.session.get(User, rejector_id)
        if not rejector:
            raise ValueError("Rejector not found")

        request.status = "rejected"
        request.rejected_at = datetime.now(timezone.utc)
        request.rejected_by = rejector_id
        request.rejection_reason = reason
        request.add_audit_trail_entry("rejected", rejector_id, reason)

        db.session.commit()
        return request

    @classmethod
    def _apply_change(cls, request: ProfileChangeRequest, applied_by: int):
        """
        Apply the approved change to the profile.

        This is called automatically when all required approvals are obtained.
        """
        profile = db.session.get(UserProfile, request.user_profile_id)
        if not profile:
            current_app.logger.error(
                f"Profile not found for change request {request.id}"
            )
            return

        # Check if the field is still immutable
        from app.profile.models import IMMUTABLE_AFTER_VERIFICATION
        if profile.verification_status == "verified" and request.field_name in IMMUTABLE_AFTER_VERIFICATION:
            # Allow the change since it was properly approved
            pass

        # Apply the change
        setattr(profile, request.field_name, request.requested_value)
        request.applied_at = datetime.now(timezone.utc)
        request.applied_by = applied_by
        request.status = "applied"
        request.add_audit_trail_entry("change_applied", applied_by)

        current_app.logger.info(
            f"Profile change applied: profile={profile.id}, "
            f"field={request.field_name}, old={request.old_value}, "
            f"new={request.requested_value}, applied_by={applied_by}"
        )

    @classmethod
    def get_approval_status(cls, request_id: int) -> Dict[str, Any]:
        """
        Get the approval status of a change request.

        Returns a dict with the status of each approval level.
        """
        request = db.session.get(ProfileChangeRequest, request_id)
        if not request:
            raise ValueError("Request not found")

        return {
            "request_id": request.id,
            "field_name": request.field_name,
            "status": request.status,
            "requires_admin_approval": request.requires_admin_approval,
            "admin_approved": request.admin_approved,
            "admin_approved_by": request.admin_approved_by,
            "admin_approved_at": request.admin_approved_at.isoformat() if request.admin_approved_at else None,
            "requires_compliance_approval": request.requires_compliance_approval,
            "compliance_approved": request.compliance_approved,
            "compliance_approved_by": request.compliance_approved_by,
            "compliance_approved_at": request.compliance_approved_at.isoformat() if request.compliance_approved_at else None,
            "requires_super_admin_approval": request.requires_super_admin_approval,
            "super_admin_approved": request.super_admin_approved,
            "super_admin_approved_by": request.super_admin_approved_by,
            "super_admin_approved_at": request.super_admin_approved_at.isoformat() if request.super_admin_approved_at else None,
            "requires_owner_approval": request.requires_owner_approval,
            "owner_approved": request.owner_approved,
            "owner_approved_by": request.owner_approved_by,
            "owner_approved_at": request.owner_approved_at.isoformat() if request.owner_approved_at else None,
            "is_fully_approved": request.is_fully_approved(),
            "audit_trail": request.audit_trail or [],
        }
