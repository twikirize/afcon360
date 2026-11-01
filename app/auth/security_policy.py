"""Central security policy readers.

Owner MFA is a system-wide policy. A persisted SystemConfig value takes
precedence over the bootstrap environment setting so all Gunicorn workers
observe the same policy without relying on process-local config mutation.
"""
import logging

from flask import current_app

logger = logging.getLogger(__name__)


def owner_mfa_required() -> bool:
    """Return the effective owner-MFA policy.

    The environment value is used only until an owner explicitly saves the
    setting. A database read failure in production fails closed: privileged
    logins must not silently downgrade to password-only authentication.
    """
    fallback = bool(current_app.config.get("REQUIRE_OWNER_MFA", False))
    try:
        from app.models.system_config import SystemConfig

        stored = SystemConfig.get("REQUIRE_OWNER_MFA", default=None)
        if stored is None:
            return fallback
        if isinstance(stored, str):
            return stored.strip().lower() in ("true", "1", "yes", "on")
        return bool(stored)
    except Exception:
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass

        app_env = str(current_app.config.get("APP_ENV", "")).strip().lower()
        flask_env = str(current_app.config.get("FLASK_ENV", "")).strip().lower()
        if app_env in ("prod", "production") or flask_env == "production":
            logger.critical(
                "Unable to read persisted owner MFA policy; failing closed for owner login",
                exc_info=True,
            )
            return True

        logger.exception("Unable to read owner MFA policy; using non-production bootstrap fallback")
        return fallback



def recent_owner_totp_proof(max_age_seconds: int = 300) -> bool:
    """Require a recent, actual TOTP proof for high-impact owner policy changes.

    Backup codes are valid for sign-in, but changing the platform-wide MFA
    requirement specifically requires a fresh authenticator-app code.
    """
    from datetime import datetime, timezone
    from flask import session

    if not session.get("mfa_verified") or session.get("mfa_verified_method") != "totp":
        return False

    raw = session.get("mfa_verified_at")
    if not isinstance(raw, str) or not raw:
        return False
    try:
        verified_at = datetime.fromisoformat(raw)
        if verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - verified_at).total_seconds()
        return 0 <= age <= max_age_seconds
    except (TypeError, ValueError, OverflowError):
        return False
