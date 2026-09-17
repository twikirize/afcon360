# tests/test_transport_drivers_admin_lock.py
"""Access control for the HTML driver-management surfaces.

Directive: `/transport/drivers` and every sub-page under it are for transport
admins only. Non-transport-admins must be denied; admin / super_admin / owner
must retain access. The self-service surfaces (`/become-driver`,
`/driver-dashboard`, `/driver/dashboard`) are intentionally NOT covered here —
they belong to the driver's own workspace and stay open to authenticated users.
"""
import uuid

import pytest

from app.extensions import db


DRIVER_ADMIN_PATHS = [
    "/transport/drivers",
    "/transport/drivers/new",
    "/transport/drivers/1",
    "/transport/drivers/1/edit",
    "/transport/drivers/1/location",
    "/transport/drivers/1/verification",
]


def _make_user(tag):
    from app.identity.models.user import User

    suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"drvlock_{tag}_{suffix}",
        email=f"drvlock_{tag}_{suffix}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.commit()
    return str(user.public_id), user.id


def _grant_admin(internal_id):
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import User, UserRole

    user = db.session.get(User, internal_id)
    role = get_or_create_role("admin", level=3)
    if not any(getattr(r, "role_id", None) == role.id for r in user.roles):
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
        db.session.commit()


def _login(client, public_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id


@pytest.mark.parametrize("path", DRIVER_ADMIN_PATHS)
def test_unauthenticated_driver_pages_are_denied(app, client, path):
    resp = client.get(path)
    assert resp.status_code in (302, 401, 403), (
        f"Unauthenticated GET {path} must be denied, got {resp.status_code}"
    )


@pytest.mark.parametrize("path", DRIVER_ADMIN_PATHS)
def test_non_admin_driver_pages_are_denied(app, client, path):
    with app.app_context():
        public_id, _ = _make_user("plain")
    _login(client, public_id)
    resp = client.get(path)
    assert resp.status_code in (302, 401, 403), (
        f"Non-admin GET {path} must be denied, got {resp.status_code}"
    )


@pytest.mark.parametrize("path", DRIVER_ADMIN_PATHS)
def test_admin_driver_pages_pass_auth_gate(app, client, path):
    with app.app_context():
        public_id, internal_id = _make_user("admin")
        _grant_admin(internal_id)
    _login(client, public_id)
    resp = client.get(path)
    # Admin must never be forbidden. An id-addressed path may legitimately
    # redirect back to the index when the seeded driver id does not exist;
    # what must NOT happen is a 401/403 or a bounce to the login page.
    assert resp.status_code != 403, resp.status_code
    if resp.status_code == 302:
        location = resp.headers.get("Location", "")
        assert "login" not in location, location

    # The primary named surface must render for an admin.
    if path == "/transport/drivers":
        assert resp.status_code == 200, resp.status_code
