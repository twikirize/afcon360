# app/auth/deletion_guard.py
"""
Hard guards against unauthorized deletion of protected identity rows.

Layers:
  1. DB trigger (requires migration) — blocks DELETE from user_roles / users
     unless a PostgreSQL session GUC ``app.guard.authorized_deletion`` is set.
  2. App-level enforcement — the functions below set/clear that GUC and
     enforce authorization before allowing calls into the ORM delete path.

Usage (inside an authorized transaction)::

    from app.auth.deletion_guard import guard_user_roles_deletion, authorize_deletion

    with db_transaction("Revoke role"):
        authorize_deletion(db.session)          # SET LOCAL app.guard.authorized_deletion = 'true'
        db.session.delete(user_role)            # trigger sees the GUC → allows the DELETE
        # commit clears the GUC (SET LOCAL is transaction-scoped)

Quick public API:
    authorize_deletion(session)          — set the GUC for the current transaction
    guard_user_roles_deletion(session)   — context-managed: authorize + return a token
                                            (used by callers that want a bounded scope)
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, scoped_session

log = logging.getLogger(__name__)

# The PostgreSQL session GUC that the trigger checks.
_GU_PARM = "app.guard.authorized_deletion"

def authorize_deletion(
    session: Session | scoped_session,
    *,
    actor: Optional[str] = None,
) -> None:
    """
    Set the transaction-scoped PostgreSQL GUC that unblocks the
    ``trg_guard_user_roles_delete`` / ``trg_guard_users_delete`` triggers.

    MUST be called inside an active transaction.  ``SET LOCAL`` is
    transaction-scoped, so the flag auto-clears on commit/rollback.

    The trigger compares the flag against the literal ``'true'``; the actor
    label (if provided) is carried in a separate GUC purely for query-time
    debugging and is never read by the trigger.

    Args:
        session: Active SQLAlchemy session.
        actor:   Optional label for audit (e.g. ``f"user:{user_id}"``).
    """
    session.execute(text(f"SET LOCAL {_GU_PARM} = 'true'"))
    if actor:
        session.execute(
            text("SET LOCAL app.guard.authorized_by = :actor"),
            {"actor": actor},
        )


def is_deletion_authorized(session: Session | scoped_session) -> bool:
    """
    Read the current transaction's GUC value (useful for tests / dry-runs).
    """
    row = session.execute(text(f"SELECT current_setting('{_GU_PARM}', true)")).scalar()
    return bool(row and row != "")


# ---------------------------------------------------------------------------
# Privileged step-up gate
# ---------------------------------------------------------------------------

def resolve_owner_user(session: Session | scoped_session) -> Optional[Any]:
    """
    Resolve the platform owner account (the user holding the global ``owner``
    role).  Returns ``None`` if no owner role assignment exists.
    """
    from app.identity.models.roles_permission import Role
    from app.identity.models.user import User, UserRole

    owner_role = (
        session.query(Role)
        .filter(Role.name == "owner", Role.scope == "global")
        .first()
    )
    if owner_role is None:
        return None
    ur = (
        session.query(UserRole)
        .filter(UserRole.role_id == owner_role.id)
        .first()
    )
    if ur is None:
        return None
    return session.get(User, ur.user_id)


def require_owner_otp(session: Session | scoped_session, otp: str) -> None:
    """
    Verify that ``otp`` is a valid TOTP code (or backup code) for the
    **platform owner's** active MFA secret.

    The owner is resolved by role, not by caller identity, so a super_admin
    stepping up to authorize a deletion must present the OWNER's current OTP —
    never their own.
    """
    if not otp:
        raise PermissionError(
            "This sensitive action requires the platform owner's MFA code."
        )

    from datetime import datetime, timezone

    from app.identity.models.user import MFASecret

    owner = resolve_owner_user(session)
    if owner is None:
        raise PermissionError(
            "No platform owner role found — cannot authorize privileged deletion."
        )

    mfa_secret = (
        session.query(MFASecret)
        .filter(MFASecret.user_id == owner.id, MFASecret.is_active.is_(True))
        .first()
    )
    if mfa_secret is None:
        raise PermissionError(
            "Platform owner has no active MFA secret — cannot authorize "
            "privileged deletion. Enable MFA on the owner account first."
        )

    import pyotp

    token = otp.strip()
    valid = False
    mfa_type = str(mfa_secret.mfa_type or "")
    if mfa_type == "totp":
        if len(token) == 8:
            valid = mfa_secret.verify_backup_code(token.upper())
        else:
            try:
                valid = pyotp.TOTP(str(mfa_secret.secret) or "").verify(token, valid_window=1)
            except Exception:
                valid = False
    elif len(token) == 8 and mfa_type in ("sms", "webauthn"):
        valid = mfa_secret.verify_backup_code(token.upper())

    if valid:
        mfa_secret.last_used = datetime.now(timezone.utc)
        session.flush()
        return

    raise PermissionError(
        "Owner MFA code invalid or expired — privileged deletion not authorized."
    )


def verify_privileged_actor(
    session: Session | scoped_session,
    actor: Optional[Any],
    password: str,
) -> None:
    """
    Verify that ``actor`` may step up for a privileged deletion: the actor
    must hold the ``owner`` or ``super_admin`` role and present a valid
    password.
    """
    if actor is None:
        raise PermissionError("Not authenticated — cannot authorize deletion.")
    if not actor.has_global_role("owner", "super_admin"):
        raise PermissionError(
            "Only the owner or a super admin may authorize privileged deletions."
        )
    if not actor.verify_password(password):
        raise PermissionError("Password verification failed — deletion denied.")


def authorize_privileged_deletion(
    session: Session | scoped_session,
    *,
    actor: Optional[Any],
    password: str,
    otp: str,
) -> str:
    """
    Single entry point for the *key-or-PIN* step-up required before any
    privileged delete/revoke:

    1. actor is owner OR super_admin,
    2. actor's own password is valid,
    3. the OTP is an active TOTP for the PLATFORM OWNER's account.

    On success sets the transaction-scoped GUC (so the trigger allows the
    DELETE) and returns an actor label for audit logging.

    Raises ``PermissionError`` with the deny reason on any failed check.
    """
    verify_privileged_actor(session, actor, password)
    require_owner_otp(session, otp)

    if actor is None:
        raise PermissionError("Not authenticated — cannot authorize deletion.")
    actor_label = f"user:{actor.id}:owner_otp_verified"
    authorize_deletion(session, actor=actor_label)
    return actor_label


def authorize_privileged_deletion_from_form(
    session: Session | scoped_session,
    *,
    actor: Optional[Any],
) -> str:
    """
    Convenience for route handlers: read the step-up credentials from the
    current POST form (``delete_password`` + ``delete_otp``) and run the full
    privileged step-up.

    Raises ``PermissionError`` on any failed check, exactly like
    :func:`authorize_privileged_deletion`.
    """
    from flask import request

    password = (request.form.get("delete_password") or "").strip()
    otp = (request.form.get("delete_otp") or "").strip()
    return authorize_privileged_deletion(
        session, actor=actor, password=password, otp=otp
    )


@contextmanager
def guard_user_roles_deletion(
    session: Session | scoped_session,
    *,
    actor: Optional[str] = None,
):
    """
    Context manager: authorize deletion for the block, yield, then
    log.  Rolls back the authorization if the caller raises.

    Usage::

        with guard_user_roles_deletion(db.session, actor="user:1"):
            db.session.delete(ur)
    """
    authorize_deletion(session, actor=actor)
    try:
        yield
        log.info("Authorized deletion committed (actor=%s)", actor)
    except Exception:
        log.warning("Authorized deletion rolled back (actor=%s)", actor)
        raise
