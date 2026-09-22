"""AFCON360 GEO control-plane integration tests.

Proves the existing module-toggle architecture governs GEO end to end:
  Owner/Super Admin surfaces -> ModuleToggleService -> SystemConfig (DB)
  -> per-request refresh -> module_enabled('geo') -> guarded GEO routes.

DB hygiene: every mutating test snapshots SystemConfig MODULE_FLAGS and
restores it in `finally` (mirrors tests/test_module_integration.py), so the
shared test database is never dirtied.
"""

import json
import re
from contextlib import contextmanager

import pytest


@contextmanager
def preserved_module_flags(app):
    """Snapshot + restore persisted MODULE_FLAGS around a test."""
    from app.models.system_config import SystemConfig
    from app.utils.module_toggle_service import ModuleToggleService
    with app.app_context():
        row_present = (
            SystemConfig.query.filter_by(key=ModuleToggleService.SETTINGS_KEY).first()
            is not None
        )
        previous = ModuleToggleService._fetch_stored_flags()
    try:
        yield previous
    finally:
        with app.app_context():
            from app.extensions import db
            if row_present:
                SystemConfig.set(
                    ModuleToggleService.SETTINGS_KEY,
                    json.dumps(previous),
                    value_type='json',
                    description='Module flags',
                    commit=True,
                )
            else:
                row = SystemConfig.query.filter_by(
                    key=ModuleToggleService.SETTINGS_KEY
                ).first()
                if row is not None:
                    db.session.delete(row)
                    db.session.commit()
            ModuleToggleService.load_overrides_into_app()


def set_geo(app, enabled):
    from app.utils.module_toggle_service import ModuleToggleService
    with app.app_context():
        ModuleToggleService.set_flag('geo', enabled, updated_by=None)


# --- registry ----------------------------------------------------------

def test_geo_in_canonical_module_registry():
    from app.utils.module_guard import MODULE_REGISTRY
    assert 'geo' in MODULE_REGISTRY


def test_geo_flag_present_and_boolean(app):
    from app.utils.module_guard import module_enabled
    from app.utils.module_toggle_service import ModuleToggleService
    with app.app_context():
        assert 'geo' in ModuleToggleService.get_flags()
        assert isinstance(module_enabled('geo'), bool)


# --- runtime effect: ON -> OFF -> ON -----------------------------------

def test_geo_runtime_effect_on_off_on(app, admin_client):
    # Service-level state (ModuleToggleService reads merged config+DB flags).
    # Request-time module_enabled() is proven through the HTTP assertions
    # below, since the /geo/ guard and per-request refresh run in requests.
    from app.utils.module_toggle_service import ModuleToggleService
    with preserved_module_flags(app):
        set_geo(app, True)
        with app.app_context():
            assert ModuleToggleService.is_enabled('geo') is True
        assert admin_client.get('/geo/health').status_code == 200
        assert admin_client.get('/geo/').status_code == 200

        set_geo(app, False)
        with app.app_context():
            assert ModuleToggleService.is_enabled('geo') is False
        assert admin_client.get('/geo/').status_code == 404
        # liveness stays open per health-endpoint precedent
        assert admin_client.get('/geo/health').status_code == 200

        set_geo(app, True)
        with app.app_context():
            assert ModuleToggleService.is_enabled('geo') is True
        assert admin_client.get('/geo/').status_code == 200


def test_geo_overview_reports_truthful_status(app, admin_client):
    with preserved_module_flags(app):
        set_geo(app, True)
        response = admin_client.get('/geo/')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'GEO' in html
        assert 'Enabled' in html
        # stubs must report unavailable, never fabricated capability
        assert 'not configured' in html
        assert 'demand' not in html.lower()


def test_geo_toggle_preserves_neighbor_modules(app):
    from app.utils.module_toggle_service import ModuleToggleService
    with preserved_module_flags(app) as previous:
        before = {k: ModuleToggleService.get_flags().get(k)
                  for k in ('transport', 'accommodation', 'events', 'tourism', 'wallet')}
        set_geo(app, False)
        set_geo(app, True)
        with app.app_context():
            after = {k: ModuleToggleService.get_flags().get(k)
                     for k in before}
        assert before == after


# --- Owner control surface ----------------------------------------------

def test_owner_toggle_route_flips_geo(app, admin_client):
    from app.utils.module_toggle_service import ModuleToggleService
    with preserved_module_flags(app):
        set_geo(app, True)
        with app.test_request_context():
            from flask import url_for
            url = url_for('admin.owner.owner_toggle_module', module='geo')
        response = admin_client.post(url, follow_redirects=False)
        assert response.status_code in (302, 303)
        with app.app_context():
            assert ModuleToggleService.is_enabled('geo') is False
        # and back on through the same surface
        response = admin_client.post(url, follow_redirects=False)
        assert response.status_code in (302, 303)
        with app.app_context():
            assert ModuleToggleService.is_enabled('geo') is True


def test_owner_module_settings_lists_geo(app, admin_client):
    with app.test_request_context():
        from flask import url_for
        url = url_for('admin.owner.module_settings')
    response = admin_client.get(url)
    assert response.status_code == 200
    assert 'geo' in response.data.decode('utf-8').lower()


def test_owner_toggle_rejects_unknown_module(app, admin_client):
    with app.test_request_context():
        from flask import url_for
        url = url_for('admin.owner.owner_toggle_module',
                      module='not_a_real_module')
    response = admin_client.post(url, follow_redirects=False)
    assert response.status_code in (302, 303)


# --- Super Admin surface --------------------------------------------------

def test_module_api_status_includes_geo(app, admin_client):
    response = admin_client.get('/admin/api/modules/status')
    assert response.status_code == 200
    assert response.get_json().get('geo') in (True, False)


def test_health_modules_includes_geo(app, admin_client):
    response = admin_client.get('/api/health/modules')
    assert response.status_code == 200
    payload = response.get_json()
    assert 'geo' in payload['modules']


# --- authorization negatives ----------------------------------------------

def test_anonymous_cannot_toggle_geo(app, anonymous_client):
    from app.utils.module_toggle_service import ModuleToggleService
    with preserved_module_flags(app):
        set_geo(app, True)
        with app.test_request_context():
            from flask import url_for
            url = url_for('admin.owner.owner_toggle_module', module='geo')
        response = anonymous_client.post(url, follow_redirects=False)
        assert response.status_code in (302, 401, 403)
        with app.app_context():
            assert ModuleToggleService.is_enabled('geo') is True


def test_anonymous_cannot_use_module_api_toggle(app, anonymous_client):
    with preserved_module_flags(app):
        response = anonymous_client.post(
            '/admin/api/modules/toggle',
            json={'module': 'geo', 'enabled': False},
        )
        assert response.status_code in (302, 401, 403)


def test_standard_user_cannot_toggle_geo(app, authenticated_client):
    from app.utils.module_toggle_service import ModuleToggleService
    with preserved_module_flags(app):
        set_geo(app, True)
        with app.test_request_context():
            from flask import url_for
            url = url_for('admin.owner.owner_toggle_module', module='geo')
        response = authenticated_client.post(url, follow_redirects=False)
        assert response.status_code in (302, 401, 403)
        with app.app_context():
            assert ModuleToggleService.is_enabled('geo') is True


def test_geo_overview_requires_login(app, anonymous_client):
    with preserved_module_flags(app):
        set_geo(app, True)
        response = anonymous_client.get('/geo/', follow_redirects=False)
        assert response.status_code in (302, 401)


# --- /geo/health UX page (privileged) + /geo/api/health JSON (tooling) ----

def test_geo_health_ux_requires_login(app, anonymous_client):
    """Anonymous visitors get no human health page (redirect to login)."""
    with preserved_module_flags(app):
        set_geo(app, True)
        resp = anonymous_client.get('/geo/health', follow_redirects=False)
        assert resp.status_code in (302, 401)


def test_geo_health_ux_denied_for_standard_user(app, authenticated_client):
    """Standard (non-admin) users get 403 and never see provider internals."""
    with preserved_module_flags(app):
        set_geo(app, True)
        assert authenticated_client.get('/geo/health').status_code == 403


def test_geo_health_ux_allowed_for_admin(app, admin_client):
    """admin/owner/super_admin get the 200 HTML UX page."""
    with preserved_module_flags(app):
        set_geo(app, True)
        resp = admin_client.get('/geo/health')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'GEO' in html
        assert 'Platform Health' in html
        assert 'Valhalla' in html


def test_geo_health_ux_reflects_module_disabled(app, admin_client):
    """Privileged health page stays reachable when GEO is disabled so
    operators can see truthful status (health is not module-gated)."""
    with preserved_module_flags(app):
        set_geo(app, False)
        resp = admin_client.get('/geo/health')
        assert resp.status_code == 200
        assert 'Disabled' in resp.data.decode('utf-8')


def test_geo_health_json_retained_for_tooling(app, anonymous_client, admin_client):
    """Raw JSON liveness remains available and open for monitoring/CI."""
    with preserved_module_flags(app):
        set_geo(app, True)
        resp = anonymous_client.get('/geo/api/health')
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['module'] == 'geo'
        assert payload['status'] == 'ok'
        assert set(payload['adapters']) == {'valhalla', 'photon', 'tiles'}
        # authenticated admins see the same payload through the same endpoint
        assert admin_client.get('/geo/api/health').status_code == 200


# --- owner-controlled GEO permission gating ----------------------------------
# GEO view/manage permissions are seeded to the OWNER only. super_admin and
# admin must be granted access by the owner (or be denied). RolePermission
# rows created/removed here target only the admin/super_admin roles, which
# NEVER carry geo permissions at seed time, so the shared-DB isolation
# cleanup leaves no residue. It never mutates the OwnerRole.Period.

def _make_role_user(app, role_name):
    import uuid as _uuid

    from app.extensions import db
    from app.identity.models.user import User, UserRole
    from app.identity.models.roles_permission import Role

    with app.app_context():
        role = Role.query.filter_by(name=role_name, scope='global').first()
        assert role is not None, f"'{role_name}' role must be seeded"
        uid = str(_uuid.uuid4())[:8]
        user = User(
            username=f'{role_name}_{uid}',
            email=f'{role_name}_{uid}@test.example.com',
            is_verified=True,
            is_active=True,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.flush()
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
        db.session.commit()
        return user


def _login_as(client, user, app):
    from app.extensions import db
    with app.app_context():
        merged = db.session.merge(user)
        uid = str(merged.public_id)
        db.session.rollback()
    with client.session_transaction() as sess:
        sess['_user_id'] = uid
        sess['_fresh'] = True


def _set_geo_role_access(app, role_name, granted):
    from app.extensions import db
    from app.identity.models.roles_permission import (
        Permission,
        Role,
        assign_permission_to_role,
        remove_permission_from_role,
    )
    with app.app_context():
        role = Role.query.filter_by(name=role_name, scope='global').first()
        assert role is not None
        for perm_name in ('geo.view', 'geo.manage'):
            perm = Permission.query.filter_by(name=perm_name).first()
            assert perm is not None, f"'{perm_name}' permission must be seeded"
            if granted:
                assign_permission_to_role(role, perm)
            else:
                remove_permission_from_role(role, perm)
        db.session.commit()


def test_geo_permissions_seeded_owner_only(app):
    from app.identity.models.roles_permission import Permission, Role
    with app.app_context():
        geo_view = Permission.query.filter_by(name='geo.view').first()
        geo_manage = Permission.query.filter_by(name='geo.manage').first()
        assert geo_view is not None
        assert geo_manage is not None

        owner = Role.query.filter_by(name='owner', scope='global').first()
        super_admin = Role.query.filter_by(name='super_admin', scope='global').first()
        admin = Role.query.filter_by(name='admin', scope='global').first()
        assert owner.has_permission('geo.view')
        assert owner.has_permission('geo.manage')
        # default (no owner grant) = denied for super_admin and admin
        assert not super_admin.has_permission('geo.view')
        assert not admin.has_permission('geo.view')


def test_geo_denied_for_admin_without_toggle(app, client):
    with preserved_module_flags(app):
        set_geo(app, True)
        user = _make_role_user(app, 'admin')
        _login_as(client, user, app)
        assert client.get('/geo/').status_code == 403
        assert client.get('/geo/health').status_code == 403


def test_geo_denied_for_super_admin_without_toggle(app, client):
    with preserved_module_flags(app):
        set_geo(app, True)
        user = _make_role_user(app, 'super_admin')
        _login_as(client, user, app)
        assert client.get('/geo/').status_code == 403
        assert client.get('/geo/health').status_code == 403


def test_geo_allowed_for_admin_after_owner_grant(app, client):
    with preserved_module_flags(app):
        set_geo(app, True)
        _set_geo_role_access(app, 'admin', granted=True)
        user = _make_role_user(app, 'admin')
        _login_as(client, user, app)
        assert client.get('/geo/').status_code == 200
        assert client.get('/geo/health').status_code == 200
        html = client.get('/geo/health').data.decode('utf-8')
        assert 'Platform Health' in html


def test_geo_super_admin_respects_owner_grant_and_revoke(app, client):
    with preserved_module_flags(app):
        set_geo(app, True)
        user = _make_role_user(app, 'super_admin')
        _login_as(client, user, app)

        _set_geo_role_access(app, 'super_admin', granted=True)
        assert client.get('/geo/health').status_code == 200
        assert client.get('/geo/').status_code == 200

        # revocation takes effect immediately (permissions read from DB)
        _set_geo_role_access(app, 'super_admin', granted=False)
        assert client.get('/geo/health').status_code == 403
        assert client.get('/geo/').status_code == 403


def test_owner_geo_toggle_route_grants_and_revokes(app, admin_client):
    from app.identity.models.roles_permission import Role
    with preserved_module_flags(app):
        with app.test_request_context():
            from flask import url_for
            grant_url = url_for(
                'admin.owner.owner_toggle_geo_permission', role='admin')

        # grant
        assert admin_client.post(grant_url).status_code in (302, 303)
        with app.app_context():
            admin_role = Role.query.filter_by(name='admin', scope='global').first()
            assert admin_role.has_permission('geo.view')
            assert admin_role.has_permission('geo.manage')

        # revoke
        assert admin_client.post(grant_url).status_code in (302, 303)
        with app.app_context():
            admin_role = Role.query.filter_by(name='admin', scope='global').first()
            assert not admin_role.has_permission('geo.view')
            assert not admin_role.has_permission('geo.manage')


def test_owner_geo_toggle_rejects_unknown_role(app, admin_client):
    from app.identity.models.roles_permission import Role
    with app.test_request_context():
        from flask import url_for
        url = url_for('admin.owner.owner_toggle_geo_permission',
                      role='not_a_real_role')
    assert admin_client.post(url).status_code in (302, 303)
    with app.app_context():
        admin_role = Role.query.filter_by(name='admin', scope='global').first()
        assert not admin_role.has_permission('geo.view')


def test_geo_overview_denied_for_standard_user(app, authenticated_client):
    with preserved_module_flags(app):
        set_geo(app, True)
        assert authenticated_client.get('/geo/').status_code == 403


# --- public-identifier hygiene ---------------------------------------------

def test_geo_pages_expose_no_internal_ids(app, admin_client):
    with preserved_module_flags(app):
        set_geo(app, True)
        html = admin_client.get('/geo/').data.decode('utf-8')
        # Same-origin app links must not embed raw integer record IDs
        # (public slugs such as /events/afcon-2027 are allowed).
        assert not re.search(r'href="/[^"]*/\d+(?:[/?#]|")', html)
