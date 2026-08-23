"""
Shared attendee account management.

Used by both EventService and EventPaymentService so third-party and group
registration paths share one source of truth for attendee account resolution.

Account creation is OPTIONAL.  A guest may be registered for an event without
owning an AFCON360 account.  Callers that only need to link an existing account
should use ``find_attendee_user_id()``.  ``find_or_create_attendee_user()`` is
the unified resolver; by default it will NOT create an account
(``create_guest_account=False``).  Pass ``create_guest_account=True`` only when
an account is genuinely required (e.g. wallet top-up or other account-linked
services explicitly requested by the organizer).
"""
from typing import Optional, Tuple

import logging
import secrets

from app.extensions import db

logger = logging.getLogger(__name__)


def find_attendee_user_id(
    email: str,
    name: str = None,
    phone: str = None,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Resolve an existing attendee user id by email without creating an account.

    Returns:
        (user_id, None) if a matching user exists
        (None, None) if no account exists (this is not an error)
        (None, error_message) only on an unexpected lookup failure
    """
    from app.identity.models.user import User

    if not email:
        return None, None

    email = email.strip().lower()
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        logger.debug("Found existing user %s for email %s", existing_user.id, email)
        return existing_user.id, None
    return None, None


def create_attendee_user(
    email: str,
    name: str = None,
    phone: str = None,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Create a new AFCON360 guest account for an attendee.

    Returns:
        (user_id, None) on success
        (None, error_message) on failure
    """
    from app.auth.services import register_user
    from app.identity.models.user import User
    from app.profile.models import get_profile_by_user

    if not email:
        return None, "Email is required to create an attendee account"

    email = email.strip().lower()
    name = name.strip() if name else None

    temp_username = f"guest_{secrets.token_hex(8)}"
    temp_password = secrets.token_urlsafe(16)

    try:
        user = register_user(
            username=temp_username,
            password=temp_password,
            email=email,
            full_name=name,
        )

        user.is_verified = False
        user.is_active = True
        db.session.commit()

        profile = get_profile_by_user(user.public_id)
        if profile:
            if name:
                profile.full_name = name
                profile.display_name = name
            if phone:
                profile.phone_number = phone
            db.session.commit()

        logger.info("Created guest account for %s (user_id=%s)", email, user.id)
        return user.id, None

    except Exception as e:
        db.session.rollback()
        logger.error("Failed to create attendee user for %s: %s", email, e)
        return None, f"Could not create attendee account: {str(e)}"


def find_or_create_attendee_user(
    email: str,
    name: str,
    phone: str = None,
    create_guest_account: bool = False,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Resolve an existing attendee account or optionally create one.

    By default this is account-optional: if no account exists the caller gets
    ``(None, None)`` and should proceed without forcing account creation.  Pass
    ``create_guest_account=True`` only when an account is genuinely required
    (e.g. wallet top-up or other account-linked services).

    Returns:
        (user_id, None) on success (existing or newly created)
        (None, None) when no account exists and creation was not requested
        (None, error_message) on a creation failure
    """
    user_id, error = find_attendee_user_id(email, name, phone)
    if user_id is not None:
        return user_id, None
    if not create_guest_account:
        return None, None
    return create_attendee_user(email, name, phone)
