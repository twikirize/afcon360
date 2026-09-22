"""Phase D3-A — Canonical Transport Admin foundation (Overview).

Contract under test
-------------------
``GET /admin/transport-admin`` is the canonical Platform Transport Admin entry
(D2 §15.2 / §15.3). It must:

- render **200** for any actor holding ``transport.view`` (``transport_admin``
  role, plus the preserved ``admin``/``owner`` broader authority);
- deny ordinary users;
- feed the Overview **exclusively** from the existing
  ``DashboardService.get_admin_dashboard_context()`` (no business logic in the
  route, no dependency on the non-canonical dynamic ``TransportPermission``
  table);
- never self-redirect (legacy ``/transport/admin/dashboard`` loop defect);
- leave the Driver Workspace and Organisation Transport scopes untouched;
- ship the ``datetimeformat`` template filter (D2 §15.12, D3-A prerequisite)
  so Transport templates stop failing to compile.
"""
import inspect
import uuid

import pytest

from app.extensions import db

TRANSPORT_ADMIN = "transport_admin"
ENTRY = "/admin/transport-admin"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(tag, role_names=()):
    """Create a committed user holding the named global roles."""
    from app.identity.models.roles_permission import Role
    from app.identity.models.user import User, UserRole

    uid = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"ca_{tag}_{uid}",
        email=f"ca_{tag}_{uid}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.flush()

    for name in role_names:
        role = Role.query.filter_by(name=name, scope="global").first()
        assert role is not None, f"global role {name!r} must be seeded"
        db.session.add(UserRole(user_id=user.id, role_id=role.id))

    db.session.commit()
    return user.public_id


def _make_driver(app, tag):
    """Create a user with a live PENDING DriverProfile (driver workspace)."""
    from app.identity.models.roles_permission import Role
    from app.identity.models.user import User, UserRole
    from app.transport.models import (
        ComplianceStatus,
        DriverProfile,
        VerificationTier,
    )

    uid = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"cadrv_{tag}_{uid}",
        email=f"cadrv_{tag}_{uid}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.flush()

    user_role = Role.query.filter_by(name="user", scope="global").first()
    if user_role is not None:
        db.session.add(UserRole(user_id=user.id, role_id=user_role.id))

    db.session.add(
        DriverProfile(
            user_id=user.id,
            driver_code=f"CA-{uid[:6].upper()}",
            verification_tier=VerificationTier.PENDING,
            compliance_status=ComplianceStatus.PENDING_REVIEW,
            is_active=True,
            is_online=False,
            is_available=False,
            max_passenger_capacity=4,
            vehicle_classes=["comfort"],
        )
    )
    db.session.commit()

    driver = DriverProfile.query.filter_by(user_id=user.id, is_deleted=False).first()
    assert driver is not None, "DriverProfile must exist"
    return user.public_id, driver.driver_code


def _login(client, public_id, *, context_type=None, context_role=None):
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id
        sess["_fresh"] = True
        if context_type:
            sess["active_context_type"] = context_type
            sess["active_context_id"] = public_id
            sess["active_role"] = context_role


def _platform_login(client, public_id, role):
    _login(client, public_id, context_type="platform", context_role=role)


def _clear_cache():
    try:
        from app.extensions import cache

        cache.clear()
    except Exception:
        pass


def _get(client, url):
    _clear_cache()
    return client.get(url)


def _assert_denied(resp):
    """Denial = hard 403 OR redirect to ``/`` — never a login bounce."""
    if resp.status_code == 403:
        return
    assert resp.status_code == 302, (resp.status_code, resp.headers.get("Location"))
    location = resp.headers.get("Location", "")
    assert "login" not in location, location
    assert location.rstrip("/") in ("", "http:", "https:"), location


# ---------------------------------------------------------------------------
# A. Canonical entry renders for transport_admin and platform admins
# ---------------------------------------------------------------------------

class TestCanonicalEntryRenders:
    def test_transport_admin_gets_200_canonical_overview(self, app, client):
        with app.app_context():
            public_id = _make_user("ta", [TRANSPORT_ADMIN])
        _platform_login(client, public_id, TRANSPORT_ADMIN)

        resp = _get(client, ENTRY)
        assert resp.status_code == 200, resp.status_code
        body = resp.get_data(as_text=True)
        assert "Transport Admin" in body
        assert "Overview" in body
        assert "Total Bookings" in body
        assert "Active Drivers" in body
        assert "Available Vehicles" in body
        assert "Today's Completed Revenue" in body
        assert "Recent Activity" in body

    def test_canonical_entry_never_self_redirects(self, app, client):
        with app.app_context():
            public_id = _make_user("ta_loop", [TRANSPORT_ADMIN])
        _platform_login(client, public_id, TRANSPORT_ADMIN)

        resp = _get(client, ENTRY)
        # Legacy self-redirect defect must never return a redirect to the same URL.
        assert resp.status_code != 302, resp.headers.get("Location")
        assert resp.headers.get("Location", "").rstrip("/") != ENTRY.rstrip("/")

    def test_canonical_shell_has_no_legacy_dead_links(self, app, client):
        """D3-A §8 — the canonical shell must not link to non-implemented legacy
        endpoints (the broken ``/transport/admin/*`` family)."""
        with app.app_context():
            public_id = _make_user("ta_links", [TRANSPORT_ADMIN])
        _platform_login(client, public_id, TRANSPORT_ADMIN)

        body = _get(client, ENTRY).get_data(as_text=True)
        assert 'href="/transport/admin' not in body
        assert "transport_admin.admin_dashboard" not in body

    def test_platform_admin_preserved(self, app, client):
        with app.app_context():
            public_id = _make_user("adm", ["admin"])
        _platform_login(client, public_id, "admin")
        assert _get(client, ENTRY).status_code == 200

    def test_owner_preserved(self, app, client):
        with app.app_context():
            public_id = _make_user("own", ["owner"])
        _platform_login(client, public_id, "owner")
        assert _get(client, ENTRY).status_code == 200


# ---------------------------------------------------------------------------
# B. Denials
# ---------------------------------------------------------------------------

class TestDenials:
    def test_ordinary_user_denied(self, app, client):
        with app.app_context():
            public_id = _make_user("plain", ["user"])
        _platform_login(client, public_id, "user")
        _assert_denied(_get(client, ENTRY))

    def test_driver_denied(self, app, client):
        with app.app_context():
            public_id, driver_code = _make_driver(app, "deny")
        _login(client, public_id, context_type="driver", context_role="driver")
        with client.session_transaction() as sess:
            sess["active_context_id"] = driver_code
        _assert_denied(_get(client, ENTRY))


# ---------------------------------------------------------------------------
# C. Driver workspace separation
# ---------------------------------------------------------------------------

class TestDriverWorkspaceSeparation:
    def test_driver_workspace_unchanged(self, app, client):
        with app.app_context():
            public_id, driver_code = _make_driver(app, "ws")
        _login(client, public_id, context_type="driver", context_role="driver")
        with client.session_transaction() as sess:
            sess["active_context_id"] = driver_code

        resp = _get(client, "/transport/driver-dashboard")
        assert resp.status_code == 200, resp.status_code


# ---------------------------------------------------------------------------
# D. Overview data source — DashboardService only
# ---------------------------------------------------------------------------

class TestOverviewDataSource:
    def test_route_does_not_depend_on_transport_permissions_table(self, app):
        """The canonical Overview must not import or read
        ``app.core.transport_permissions`` (non-canonical; absent from the test
        DB bootstrap — D2 §15.12 PHASE-D2-4)."""
        from app.admin.route_modules.transport_admin import transport_admin_dashboard

        unwrapped = inspect.unwrap(transport_admin_dashboard)
        with open(unwrapped.__code__.co_filename, encoding="utf-8") as fh:
            text = fh.read()
        assert "transport_permissions import" not in text
        assert "TransportPermission" not in text

    def test_datetimeformat_filter_registered_and_safe(self, app):
        fil = app.jinja_env.filters.get("datetimeformat")
        assert fil is not None, "datetimeformat template filter must be registered"
        from datetime import datetime, timezone

        rendered = fil(datetime(2026, 9, 18, 7, 30, tzinfo=timezone.utc))
        assert isinstance(rendered, str) and "2026" in rendered
        assert fil(None) == ""

    def test_service_module_enabled_key_must_not_shadow_template_helper(self, app):
        """DashboardService returns a ``module_enabled`` boolean (service
        contract). The canonical route must strip it before render so the
        global ``module_enabled()`` helper used by ``base.html`` stays
        callable — otherwise ``{% if module_enabled('wallet') %}`` fails with
        "'bool' object is not callable"."""
        from app.transport.services.dashboard_service import get_dashboard_service

        with app.app_context():
            context = get_dashboard_service().get_admin_dashboard_context()
            assert isinstance(context.get("module_enabled"), bool)
        assert not isinstance(app.jinja_env.globals.get("module_enabled"), bool)

        import inspect
        from app.admin.route_modules.transport_admin import transport_admin_dashboard

        unwrapped = inspect.unwrap(transport_admin_dashboard)
        with open(unwrapped.__code__.co_filename, encoding="utf-8") as fh:
            text = fh.read()
        assert 'context.pop("module_enabled", None)' in text