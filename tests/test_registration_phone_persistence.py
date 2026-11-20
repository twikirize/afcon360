"""Regression tests for preserving signup phone data across account creation."""

import uuid
from werkzeug.security import generate_password_hash

from app.auth.pending_registration import _create_verified_user
from app.auth.services import register_user
from app.profile.models import get_profile_by_user


def _unique_identity():
    suffix = uuid.uuid4().hex[:10]
    return {
        "username": f"phone_signup_{suffix}",
        "email": f"phone_signup_{suffix}@example.com",
        "phone": f"+2567{uuid.uuid4().int % 10**8:08d}",
    }


def test_direct_registration_persists_phone_as_unverified_contact(db_session):
    identity = _unique_identity()

    user = register_user(
        username=identity["username"],
        password="StrongTestPassword123!",
        email=identity["email"],
        phone=identity["phone"],
    )
    profile = get_profile_by_user(user.public_id)

    assert user.phone == identity["phone"]
    assert profile.phone_number == identity["phone"]
    assert user.phone_verified is False
    assert user.phone_verified_at is None
    assert profile.phone_verified is False


def test_pending_email_signup_persists_phone_without_marking_it_verified(db_session):
    identity = _unique_identity()
    payload = {
        **identity,
        "password_hash": generate_password_hash("StrongTestPassword123!"),
        "full_name": "Pending Signup Test",
        "resolved_channel": "email",
    }

    user, already_existed = _create_verified_user(
        payload,
        ip="127.0.0.1",
        user_agent="pytest",
    )
    profile = get_profile_by_user(user.public_id)

    assert already_existed is False
    assert user.phone == identity["phone"]
    assert profile.phone_number == identity["phone"]
    assert user.email_verified is True
    assert user.phone_verified is False
    assert user.phone_verified_at is None
    assert profile.phone_verified is False
