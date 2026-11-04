"""Shared, reauthenticated account deletion for native and web clients.

Account closure retains the identity tombstone and separately controlled
KYC/financial/audit evidence where retention is legally required. Direct
profile and sign-in identifiers, active sessions, API credentials, MFA and
transaction-PIN secrets are removed or invalidated.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from app.extensions import db

logger = logging.getLogger(__name__)


class AccountDeletionError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def request_account_deletion(
    *,
    user,
    password,
    confirmation: str,
    mfa_code: str = "",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Reauthenticate, revoke credentials, anonymize direct PII and audit.

    This service is shared by POST /api/mobile/v1/auth/account-deletion and
    the public web deletion resource /apps/delete-account. It deliberately
    uses a soft-deleted User tombstone so foreign keys for Wallet, bookings,
    KYC and audit records are not cascade-deleted.
    """
    if confirmation != "DELETE MY ACCOUNT":
        raise AccountDeletionError(
            "deletion_confirmation_invalid",
            'Type "DELETE MY ACCOUNT" exactly to confirm.',
            400,
        )
    if not isinstance(password, str) or not password or len(password) > 128:
        raise AccountDeletionError(
            "password_required",
            "Enter your current password to confirm account deletion.",
            400,
        )

    if user is None or not getattr(user, "is_active", False) or getattr(user, "is_deleted", False):
        raise AccountDeletionError(
            "account_inactive",
            "This account is already inactive or cannot be deleted from this session.",
            403,
        )
    if getattr(user, "is_app_owner", lambda: False)():
        raise AccountDeletionError(
            "owner_deletion_blocked",
            "The platform owner account cannot be deleted through self-service.",
            403,
        )
    if bool(getattr(user, "is_protected", False)):
        raise AccountDeletionError(
            "protected_account",
            "This protected account must be closed through AFCON360's authorized security process.",
            403,
        )

    try:
        if not user.verify_password(password):
            raise AccountDeletionError(
                "password_invalid",
                "The current password could not be verified.",
                401,
            )

        from app.identity.models.user import MFASecret
        active_mfa = MFASecret.query.filter_by(
            user_id=user.id,
            is_active=True,
        ).first()
        if active_mfa is not None and active_mfa.mfa_type != "totp":
            raise AccountDeletionError(
                "mfa_method_unsupported",
                "This account uses an MFA method that cannot currently be reverified in the self-service deletion flow. Update to an authenticator app or contact AFCON360 support.",
                422,
            )
        if getattr(user, "mfa_enabled", False) or active_mfa is not None:
            if active_mfa is None:
                raise AccountDeletionError(
                    "mfa_enrollment_unavailable",
                    "Your account requires MFA, but no active authenticator is available. Restore MFA through AFCON360 support before deleting this account.",
                    403,
                )
            if not mfa_code:
                raise AccountDeletionError(
                    "mfa_required",
                    "Enter your current authenticator or backup code.",
                    401,
                )
            from app.auth.routes import _verify_mfa_token
            if not _verify_mfa_token(
                user,
                mfa_code,
                backup_code=(len(mfa_code) == 8),
            ):
                raise AccountDeletionError(
                    "mfa_invalid",
                    "The authenticator code is invalid or expired.",
                    401,
                )
    except AccountDeletionError:
        raise
    except Exception as exc:
        db.session.rollback()
        logger.exception("Account deletion reauthentication failed")
        raise AccountDeletionError(
            "deletion_verification_unavailable",
            "AFCON360 could not verify this deletion request.",
            503,
        ) from exc

    from app.auth.sessions import (
        revoke_all_device_sessions_for_user,
        revoke_all_sessions_for_user,
    )
    from app.identity.models.user import (
        APIKey,
        MFASecret,
        Session as DeviceSession,
    )
    from sqlalchemy import func

    active_device_ids = [
        row.session_id
        for row in DeviceSession.query.filter_by(
            user_id=user.id,
            revoked_at=None,
        ).all()
    ]
    public_id = str(user.public_id)
    try:
        # Database revocation is authoritative. All sessions, not only the
        # current device, must stop authenticating before profile scrubbing.
        revoke_all_device_sessions_for_user(
            user.id,
            reason="account_deletion",
        )
        revoke_all_sessions_for_user(public_id)

        # Clean the corresponding opaque token keys in Redis where possible.
        # Even if Redis is temporarily unavailable, request authentication also
        # checks the revoked Identity and ServerSession rows and fails closed.
        try:
            from app.auth.mobile_tokens import mark_mobile_session_revoked
            for session_id in active_device_ids:
                try:
                    mark_mobile_session_revoked(session_id)
                except Exception:
                    logger.warning(
                        "Redis token cleanup deferred for deleted-account device session",
                        exc_info=True,
                    )
        except Exception:
            logger.warning(
                "Mobile Redis token cleanup is unavailable during account deletion",
                exc_info=True,
            )

        user.is_deleted = True
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        user.email = f"deleted_{public_id}@deleted.local"
        user.username = f"deleted_{public_id}"
        user.email_verified = False
        user.phone_verified = False
        user.mfa_enabled = False
        user.security_question = None
        user.security_answer_hash = None
        user.recovery_code = None
        user.transaction_pin_hash = None
        user.transaction_pin_failed_attempts = 0
        user.transaction_pin_locked_until = None
        user.is_agent = False
        if hasattr(user, "phone"):
            user.phone = None
        if hasattr(user, "agent_code"):
            user.agent_code = None
        if hasattr(user, "email_verify_nonce"):
            user.email_verify_nonce = None
        if hasattr(user, "password_hash"):
            user.set_password(secrets.token_urlsafe(64))

        # General personal profile is not the legal KYC archive. Remove direct
        # identifiers and user-facing content from it; retain verification
        # workflow metadata and separately governed KYC evidence for the
        # approved statutory retention periods.
        from app.profile.models import get_profile_by_user
        profile = get_profile_by_user(user)
        if profile is not None:
            profile.is_deleted = True
            profile.deleted_at = datetime.now(timezone.utc)
            profile.full_name = "Deleted account"
            profile.display_name = "Deleted account"
            profile.date_of_birth = None
            profile.gender = None
            profile.nationality = None
            profile.address = None
            profile.city = None
            profile.country = None
            profile.phone_number = None
            profile.email = None
            profile.email_verified = False
            profile.phone_verified = False
            profile.fan_team = None
            profile.avatar_url = None
            profile.bio = None
            profile.id_type = None
            profile.id_number = None
            profile.id_document_url = None
            profile.id_document_mime = None
            profile.id_document_size = None
            profile.rejected_reason = None

        # Erase active authenticator and backup-code material, not just flags.
        for secret in MFASecret.query.filter_by(
            user_id=user.id,
            is_active=True,
        ).all():
            secret.is_active = False
            secret.secret = "revoked"
            secret.backup_codes = None
            secret.device_name = None
            secret.last_used = None

        # Revoke user-owned API keys regardless of owner_type case convention.
        user_api_keys = APIKey.query.filter(
            APIKey.owner_id == user.id,
            func.lower(APIKey.owner_type) == "user",
            APIKey.revoked_at.is_(None),
        ).all()
        revoked_at = datetime.now(timezone.utc)
        for api_key in user_api_keys:
            api_key.revoked_at = revoked_at

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception("Account deletion persistence failed")
        raise AccountDeletionError(
            "account_deletion_failed",
            "AFCON360 could not complete the account deletion request. Please contact support.",
            503,
        ) from exc

    # Audit delivery happens after the commit; an audit-sink outage must not
    # tell the user that a completed account deletion failed.
    try:
        from app.audit.comprehensive_audit import AuditService
        AuditService.security(
            event_type="account_deletion_requested",
            severity="WARNING",
            description=f"User {public_id} requested account deletion",
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data={
                "client_surface": "mobile_or_web",
                "active_device_sessions_revoked": len(active_device_ids),
                "api_keys_revoked": len(user_api_keys),
                "profile_anonymized": profile is not None,
                "legal_evidence_retained": True,
            },
        )
    except Exception:
        logger.exception("Account deletion completed but audit event delivery failed")

    return {
        "status": "anonymized",
        "message": (
            "Your AFCON360 sign-in has been disabled and direct profile identifiers "
            "anonymized. KYC, Wallet, booking, safety and audit records required "
            "for legal, financial or dispute-resolution obligations may be retained."
        ),
    }
