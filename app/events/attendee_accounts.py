"""
Shared attendee account management.

Used by both EventService and EventPaymentService so third-party and group
registration paths share one source of truth for attendee account creation.
"""
from typing import Optional, Tuple

import logging
import secrets

from app.extensions import db

logger = logging.getLogger(__name__)


def find_or_create_attendee_user(
    email: str,
    name: str,
    phone: str = None
) -> Tuple[Optional[int], Optional[str]]:
    """
    Find an existing user by email or create a new guest account for an attendee.

    Returns:
        (user_id, None) on success
        (None, error_message) on failure
    """
    from app.auth.services import register_user
    from app.identity.models.user import User
    from app.profile.models import get_profile_by_user

    if not email:
        return None, "Email is required for third-party registration"

    email = email.strip().lower()
    name = name.strip() if name else None

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        logger.debug("Found existing user %s for email %s", existing_user.id, email)
        return existing_user.id, None

    temp_username = f"guest_{secrets.token_hex(8)}"
    temp_password = secrets.token_urlsafe(16)

    try:
        user = register_user(
            username=temp_username,
            password=temp_password,
            email=email,
            full_name=name
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
