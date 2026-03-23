# app/accommodation/services/identity_service.py
"""
Identity Service - Integration point with your existing identity system
This is the ONLY place that touches identity models directly.
Keeps accommodation module decoupled from identity implementation details.
"""

from typing import Dict, Optional, Tuple
from flask import current_app
from app.extensions import db
from app.identity.models.user import User
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember
from app.auth.policy import can
from app.auth.roles import assign_org_role
import logging

logger = logging.getLogger(__name__)


class AccommodationIdentityService:
    """
    Handles all identity-related queries for accommodation module.
    This creates a clean API boundary between modules.
    """

    @staticmethod
    def can_host(user: User) -> Tuple[bool, str]:
        """
        Check if a user can become a host (individual).

        Returns: (can_host, reason)
        """
        if not user:
            return False, "No user provided"

        if not user.is_active or user.is_deleted:
            return False, "Account is inactive or deleted"

        # Check KYC verification (using your existing method)
        if not user.is_fully_verified():
            return False, "Account not fully verified. Please complete KYC verification."

        # Check profile completion
        if not user.profile or not user.profile.profile_completed:
            return False, "Profile incomplete. Please complete your profile."

        return True, "OK"

    @staticmethod
    def can_org_host(organisation_id: int) -> Tuple[bool, str]:
        """
        Check if an organisation can host properties.

        Returns: (can_host, reason)
        """
        org = Organisation.query.get(organisation_id)
        if not org or org.is_deleted:
            return False, "Organisation not found or deleted"

        if not org.is_active:
            return False, "Organisation is inactive"

        if org.verification_status != "verified":
            return False, f"Organisation not verified. Status: {org.verification_status}"

        if not org.is_operational:
            return False, "Organisation is not operational. Please complete all requirements."

        # Check business category
        if org.business_category not in ['service_provider', 'merchant']:
            return False, "Organisation type not eligible for accommodation hosting"

        return True, "OK"

    @staticmethod
    def get_host_identity(user: User, org_id: Optional[int] = None) -> Dict:
        """
        Determine if user is acting as individual or organisation host.

        Returns: {
            'type': 'individual' or 'organisation',
            'id': host_id (user.id or org.id),
            'display_name': str,
            'member_role': str or None
        }
        """
        if org_id:
            # Check if user is authorized to act for this organisation
            member = OrganisationMember.query.filter_by(
                user_id=user.id,
                organisation_id=org_id,
                is_active=True,
                is_deleted=False
            ).first()

            if member:
                org = Organisation.query.get(org_id)
                # Check if member has transport/accommodation management permission
                if member.has_permission("org.accommodation.manage") or member.has_permission("org.transport.manage"):
                    return {
                        'type': 'organisation',
                        'id': org.id,
                        'display_name': org.legal_name,
                        # FIX 3: Old-style `X and Y or Z` ternary is fragile — it breaks if Y is
                        # falsy. The string 'admin' is always truthy here so it happened to work,
                        # but using a proper ternary is safer and clearer.
                        'member_role': 'admin' if member.has_permission("org.accommodation.manage") else 'member'
                    }

        # Default to individual host
        return {
            'type': 'individual',
            'id': user.id,
            'display_name': user.username or user.email,
            'member_role': None
        }

    @staticmethod
    def can_book(user: User) -> Tuple[bool, str]:
        """
        Check if user can book accommodation.

        Returns: (can_book, reason)
        """
        if not user or not user.is_active or user.is_deleted:
            return False, "Invalid account"

        # FIX 2: Was `and` — that requires BOTH conditions to be true to block a user,
        # meaning a user who is NOT fully verified but has kyc_level >= 1 would pass through.
        # Using `or` correctly blocks anyone who fails either check.
        if not user.is_fully_verified() or user.kyc_level < 1:
            return False, "Account not verified. Please complete basic KYC to book."

        # Check if user has wallet
        if not user.wallet:
            return False, "No wallet found. Please set up your wallet first."

        if user.wallet.balance <= 0:
            return False, "Insufficient wallet balance to book. Please add funds."

        return True, "OK"

    @staticmethod
    def can_manage_property(user: User, property_owner_user_id=None, property_owner_org_id=None) -> bool:
        """
        Check if user can manage a specific property.

        Returns: bool
        """
        # Super admin can manage everything
        if can(user, "accommodation.manage"):
            return True

        # Check if user is the individual owner
        if property_owner_user_id and user.id == property_owner_user_id:
            return True

        # Check if user is admin of owning organisation
        if property_owner_org_id:
            member = OrganisationMember.query.filter_by(
                user_id=user.id,
                organisation_id=property_owner_org_id,
                is_active=True
            ).first()

            if member and member.has_permission("org.accommodation.manage"):
                return True

        return False

    @staticmethod
    def assign_host_permissions(user: User, org_id: Optional[int] = None) -> bool:
        """
        Assign host permissions to a user or organisation admin.

        Returns: bool
        """
        try:
            if org_id:
                # Assign organisation role (use existing transport_manager role)
                assign_org_role(
                    user_id=user.id,
                    org_id=org_id,
                    role_name="transport_manager",  # Reuse existing role
                    assigned_by_id=user.id
                )
                logger.info(f"Assigned host permissions to user {user.id} for org {org_id}")
            else:
                # Individual hosts don't need a special role
                # They just need to meet verification requirements
                logger.info(f"User {user.id} is an individual host")

            # Audit log (use your existing AuditLog)
            from app.audit.user import AuditLog
            AuditLog.log(
                user_id=user.id,
                action="accommodation.host_role_assigned",
                resource_type="accommodation",
                meta={"org_id": org_id}
            )

            return True

        except Exception as e:
            logger.error(f"Failed to assign host permissions: {e}")
            return False

    @staticmethod
    def get_user_organisations(user: User) -> list:
        """
        Get all organisations a user belongs to with accommodation permissions.

        Returns: list of dicts with org details
        """
        orgs = []
        for member in user.organisations:
            if member.is_active and not member.is_deleted:
                if member.has_permission("org.accommodation.manage") or member.has_permission("org.accommodation.view"):
                    orgs.append({
                        'id': member.organisation.id,
                        'name': member.organisation.legal_name,
                        # FIX 3 applied here too — same old-style ternary pattern
                        'role': 'admin' if member.has_permission("org.accommodation.manage") else 'member'
                    })
        return orgs