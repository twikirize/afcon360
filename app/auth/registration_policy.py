"""
Registration and email validation helpers shared by the auth routes.

Centralises the question "is email verification required right now?" so the
owner's toggle at ``/admin/owner/settings/auth`` is respected everywhere
instead of each call site reading a different config key.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def email_verification_required() -> bool:
    """
    Return whether new accounts must verify their email via OTP.

    Resolution order:

    1. ``AuthConfiguration.email_verification_required`` - the owner-managed
       toggle on the Auth Settings page. This is the source of truth.
    2. ``REQUIRE_EMAIL_VERIFICATION`` in Flask config - fallback used when the
       settings row is unreachable (e.g. before migrations have run).

    Never raises: any database problem degrades to the config value so signup
    keeps working.
    """
    try:
        from app.extensions import db
        from app.auth.config_model import AuthConfiguration

        # Always read the live row - never a session-cached copy - so a toggle
        # flipped in the owner settings page takes effect on the very next
        # registration request (no app restart, no cache expiry needed).
        existing = db.session.get(AuthConfiguration, 1)
        if existing is not None:
            db.session.expire(existing)
            return bool(existing.email_verification_required)

        config = AuthConfiguration.get_config()
        if config is not None:
            return bool(config.email_verification_required)
    except Exception as e:
        logger.debug("Could not read AuthConfiguration, falling back to app config: %s", e)

    try:
        from flask import current_app
        if current_app:
            return bool(current_app.config.get("REQUIRE_EMAIL_VERIFICATION", False))
    except Exception:
        pass

    return False


def email_password_signup_allowed() -> bool:
    """Whether classic email + password signup is currently permitted."""
    try:
        from app.auth.config_model import AuthConfiguration

        config = AuthConfiguration.get_config()
        if config is not None:
            return bool(config.allow_email_password_signup)
    except Exception as e:
        logger.debug("Could not read AuthConfiguration signup flag: %s", e)
    return True
