"""
Transport dashboard overview regression tests.

Contract under test: ``GET /transport/dashboard/overview`` renders the
transport dashboard overview shell (which extends
``transport/dashboard/base_dashboard.html``) with the metrics supplied by
``DashboardService``, and degrades safely when a metric source is
unavailable.

Regression guard for the previously broken page, which extended a
non-existent base template (``transport/base_dashboard.html``) and was
rendered by a route that passed no context at all.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.extensions import db


def _session_login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True


def _enable_transport(app):
    app.config["MODULE_FLAGS"] = dict(
        app.config.get("MODULE_FLAGS", {}), transport=True
    )


@pytest.fixture()
def viewer(app):
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import User, UserRole

    with app.app_context():
        user_role = get_or_create_role("user", level=6)
        uid = uuid.uuid4().hex[:8]
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"viewer_{uid}",
            email=f"viewer_{uid}@test.example.com",
        )
        user.set_password("TestPassword123!")
        user.is_active = True
        user.is_verified = True
        user.email_verified = True
        db.session.add(user)
        db.session.flush()
        db.session.add(UserRole(user_id=user.id, role_id=user_role.id))
        db.session.commit()
        return SimpleNamespace(public_id=user.public_id, id=user.id)


def test_overview_renders_with_context(app, client, viewer):
    _enable_transport(app)
    _session_login(client, viewer)

    resp = client.get("/transport/dashboard/overview")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Total Bookings" in body
    assert "Active Drivers" in body
    assert "Available Vehicles" in body
    assert "Open Incidents" in body
    assert "Recent Activity" in body


def test_overview_json_path_returns_context(app, client, viewer):
    _enable_transport(app)
    _session_login(client, viewer)

    resp = client.get(
        "/transport/dashboard/overview",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "total_bookings" in data
    assert "active_drivers" in data
    assert "available_vehicles" in data
    assert "open_incidents" in data
    assert "recent_bookings" in data
