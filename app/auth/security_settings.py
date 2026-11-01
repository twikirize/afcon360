"""Durable owner MFA policy helpers.

The database setting is authoritative when present. The environment value is
an emergency minimum: setting it to true cannot be weakened from the UI.
"""

from flask import current_app

from app.extensions import db
from app.models.system_config import SystemConfig


class OwnerMFAEnrollmentRequired(ValueError):
    """Raised when active owner accounts are not yet enrolled in MFA."""


def get_owner_mfa_required() -> bool:
    """Resolve the owner MFA policy consistently across workers and restarts."""
    environment_requires_mfa = bool(
        current_app.config.get("REQUIRE_OWNER_MFA", False)
    )
    try:
        persisted = SystemConfig.get("REQUIRE_OWNER_MFA", False)
    except Exception:
        # A missing/unavailable settings table must not poison the shared
        # SQLAlchemy session. The environment setting remains the fallback.
        db.session.rollback()
        current_app.logger.exception(
            "owner_mfa_policy_read_failed; using environment policy"
        )
        return environment_requires_mfa

    return environment_requires_mfa or bool(persisted)


def set_owner_mfa_required(*, required: bool, updated_by: int) -> None:
    """Persist the owner MFA policy, refusing unsafe enablement.

    Every active owner must already have MFA enrolled before enforcement can
    be switched on. This prevents an administrator from locking all owners
    out of the platform by enabling the policy prematurely.
    """
    if required:
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role

        unenrolled_count = (
            db.session.query(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(
                Role.name == "owner",
                User.is_active.is_(True),
                User.mfa_enabled.is_(False),
            )
            .distinct()
            .count()
        )
        if unenrolled_count:
            raise OwnerMFAEnrollmentRequired(
                f"Cannot require owner MFA yet: {unenrolled_count} active "
                "owner account(s) still need to enrol and verify MFA."
            )

    SystemConfig.set(
        "REQUIRE_OWNER_MFA",
        bool(required),
        value_type="bool",
        category="security",
        description="Require verified multi-factor authentication for all owner logins.",
        updated_by=updated_by,
        commit=False,
    )
