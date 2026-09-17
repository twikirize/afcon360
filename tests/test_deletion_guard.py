"""Focused tests for the deletion-guard step-up gate.

Covers:
  - ``authorize_privileged_deletion`` requires owner/super_admin role,
    valid actor password, and a valid OTP for the PLATFORM OWNER's MFA.
  - Failed checks raise ``PermissionError`` and never set the GUC.
  - Success sets the transaction-scoped GUC ``app.guard.authorized_deletion``.

The DB trigger itself is applied by migration ``guard_delete_v1`` and is not
present in the test schema (created via ``db.create_all()``); these tests
verify the application-layer gate that the trigger relies on.
"""

import pyotp

import pytest

from app.auth.deletion_guard import (
    authorize_privileged_deletion,
    is_deletion_authorized,
    require_owner_otp,
    resolve_owner_user,
    verify_privileged_actor,
)
from app.identity.models.roles_permission import Role
from app.identity.models.user import MFASecret, User, UserRole


def _ensure_role(db_session, name):
    role = db_session.query(Role).filter_by(name=name, scope="global").first()
    if role is None:
        role = Role(name=name, scope="global")
        db_session.add(role)
        db_session.flush()
    return role


def _make_user(db_session, email, username, password="pass1234"):
    user = User(email=email, username=username)
    user.set_password(password)
    db_session.add(user)
    db_session.flush()
    return user


def _assign_role(db_session, user, role):
    db_session.add(UserRole(user_id=user.id, role_id=role.id))


def _enable_owner_mfa(db_session, owner, secret=pyotp.random_base32()):
    mfa = MFASecret(
        user_id=owner.id,
        mfa_type="totp",
        secret=secret,
        is_active=True,
    )
    db_session.add(mfa)
    db_session.flush()
    return mfa


def test_resolve_owner_user_returns_owner(db_session):
    owner_role = _ensure_role(db_session, "owner")
    other_role = _ensure_role(db_session, "support")
    owner = _make_user(db_session, "guard_owner@example.com", "guard_owner")
    _assign_role(db_session, owner, owner_role)
    other = _make_user(db_session, "guard_other@example.com", "guard_other")
    _assign_role(db_session, other, other_role)
    db_session.flush()

    resolved = resolve_owner_user(db_session)
    assert resolved is not None
    assert resolved.id == owner.id


def test_actor_must_be_owner_or_super_admin(db_session):
    owner_role = _ensure_role(db_session, "owner")
    support_role = _ensure_role(db_session, "support")
    _make_user(db_session, "guard_o1@example.com", "guard_o1")
    plain = _make_user(db_session, "guard_plain@example.com", "guard_plain")
    _assign_role(db_session, plain, support_role)
    db_session.flush()

    with pytest.raises(PermissionError, match="Only the owner or a super admin"):
        verify_privileged_actor(db_session, plain, "pass1234")
    assert is_deletion_authorized(db_session) is False


def test_wrong_password_denied(db_session):
    owner_role = _ensure_role(db_session, "owner")
    owner = _make_user(db_session, "guard_o2@example.com", "guard_o2")
    _assign_role(db_session, owner, owner_role)
    _enable_owner_mfa(db_session, owner)
    db_session.flush()

    with pytest.raises(PermissionError, match="Password verification failed"):
        verify_privileged_actor(db_session, owner, "not-the-password")

    with pytest.raises(PermissionError, match="Password verification failed"):
        authorize_privileged_deletion(db_session, actor=owner, password="bad", otp="123456")
    assert is_deletion_authorized(db_session) is False


def test_owner_otp_required_for_privileged_delete(db_session):
    owner_role = _ensure_role(db_session, "owner")
    super_admin_role = _ensure_role(db_session, "super_admin")
    owner = _make_user(db_session, "guard_o3@example.com", "guard_o3")
    _assign_role(db_session, owner, owner_role)
    secret = pyotp.random_base32()
    _enable_owner_mfa(db_session, owner, secret=secret)

    su = _make_user(db_session, "guard_su@example.com", "guard_su")
    _assign_role(db_session, su, super_admin_role)
    db_session.flush()

    valid_totp = pyotp.TOTP(secret).now()

    wrong_otp = "0" * 6
    with pytest.raises(PermissionError, match="invalid or expired"):
        authorize_privileged_deletion(
            db_session, actor=su, password="pass1234", otp=wrong_otp
        )
    assert is_deletion_authorized(db_session) is False

    with pytest.raises(PermissionError, match="MFA code"):
        authorize_privileged_deletion(db_session, actor=su, password="pass1234", otp="")

    label = authorize_privileged_deletion(
        db_session, actor=su, password="pass1234", otp=valid_totp
    )
    assert isinstance(label, str)
    assert is_deletion_authorized(db_session) is True


def test_owner_otp_must_be_owners_not_actors(db_session):
    """A super_admin's own TOTP must NOT authorize a privileged delete."""
    owner_role = _ensure_role(db_session, "owner")
    super_admin_role = _ensure_role(db_session, "super_admin")
    owner = _make_user(db_session, "guard_o4@example.com", "guard_o4")
    _assign_role(db_session, owner, owner_role)
    owner_secret = pyotp.random_base32()
    _enable_owner_mfa(db_session, owner, secret=owner_secret)

    su = _make_user(db_session, "guard_su2@example.com", "guard_su2")
    _assign_role(db_session, su, super_admin_role)
    su_secret = pyotp.random_base32()
    _enable_owner_mfa(db_session, su, secret=su_secret)
    db_session.flush()

    su_totp = pyotp.TOTP(su_secret).now()

    with pytest.raises(PermissionError, match="invalid or expired"):
        authorize_privileged_deletion(
            db_session, actor=su, password="pass1234", otp=su_totp
        )

    owner_totp = pyotp.TOTP(owner_secret).now()
    authorize_privileged_deletion(
        db_session, actor=su, password="pass1234", otp=owner_totp
    )
    assert is_deletion_authorized(db_session) is True


def test_no_owner_mfa_blocks_privileged_delete(db_session):
    owner_role = _ensure_role(db_session, "owner")
    super_admin_role = _ensure_role(db_session, "super_admin")
    owner = _make_user(db_session, "guard_o5@example.com", "guard_o5")
    _assign_role(db_session, owner, owner_role)

    su = _make_user(db_session, "guard_su3@example.com", "guard_su3")
    _assign_role(db_session, su, super_admin_role)
    db_session.flush()

    with pytest.raises(PermissionError, match="no active MFA"):
        require_owner_otp(db_session, "123456")
    assert is_deletion_authorized(db_session) is False