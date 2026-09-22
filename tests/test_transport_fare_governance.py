"""Transport fare governance + configuration (governance node).

Proves the operating model: owner configures (unconditional),
explicitly delegated roles configure (DB-resolved permission),
everyone else is denied; versions/audit/history persist; the
canonical engine, preview, and final all consume the active
configuration; historical versions stay explainable.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.transport.services.fare_service import (
    FARE_SETTINGS_KEY,
    calculate_estimate,
    calculate_final,
    read_configuration,
    resolve_tables,
    tables_version_at,
    update_fare_tables,
)


def _tables(base=10.0):
    return {
        "base_fares": {"on_demand": base, "airport_transfer": 25.0,
                       "stadium_shuttle": 15.0, "hotel_transfer": 20.0,
                       "city_tour": 30.0},
        "distance_rate_per_km": 2.5,
        "class_multipliers": {"economy": 1.0, "comfort": 1.2,
                              "premium": 1.5, "van": 1.8, "luxury": 2.0},
        "minimum_fare": 5.0,
        "peak": {"hours": [[7, 10], [17, 20]], "multiplier": 1.3},
    }


def _user(app, username, role_name=None):
    from app.extensions import db
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import User, UserRole
    with app.app_context():
        user = User(username=username, email=f"{username}@test.example.com",
                    is_active=True, is_verified=True, email_verified=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        if role_name:
            db.session.add(UserRole(
                user_id=user.id,
                role_id=get_or_create_role(role_name).id))
        db.session.commit()
        return user.id


def _login(app, client, user_id):
    from tests.conftest import _login_client
    from app.identity.models.user import User
    with app.app_context():
        from app.extensions import db
        _login_client(client, db.session.get(User, user_id))
    return client


def _grant(app, role_name):
    from app.identity.models.roles_permission import (
        assign_permission_to_role, get_or_create_permission,
        get_or_create_role)
    with app.app_context():
        role = get_or_create_role(role_name)
        perm = get_or_create_permission("transport.settings")
        assign_permission_to_role(role, perm)


def _config_url():
    return "/api/transport/fare/config"


@pytest.fixture(autouse=True)
def _clean_fare_config(app):
    """Isolation: fare config rows must not leak into other suites
    (the engine suite pins audited defaults)."""
    yield
    from app.extensions import cache, db
    from app.transport.models import TransportSetting
    from app.transport.services.fare_service import FARE_SETTINGS_KEY
    with app.app_context():
        TransportSetting.query.filter_by(key=FARE_SETTINGS_KEY).delete()
        db.session.commit()
    try:
        cache.delete(f"transport:setting:{FARE_SETTINGS_KEY}")
    except Exception:
        pass


# --- authorization matrix ----------------------------------------------------------

def test_owner_can_write_and_read(app, client):
    owner = _user(app, f"fgo_{uuid.uuid4().hex[:6]}", "owner")
    _login(app, client, owner)
    resp = client.put(_config_url(), json={"tables": _tables()})
    assert resp.status_code == 200, resp.data.decode("utf-8")[:300]
    assert resp.get_json()["data"]["version"] >= 1
    assert client.get(_config_url()).status_code == 200


def test_delegated_super_admin_allowed(app, client):
    _grant(app, "super_admin")
    sud = _user(app, f"fgs_{uuid.uuid4().hex[:6]}", "super_admin")
    _login(app, client, sud)
    assert client.put(_config_url(),
                      json={"tables": _tables()}).status_code == 200
    assert client.get(_config_url()).status_code == 200


def test_nondelegated_super_admin_denied(app, client):
    from app.identity.models.roles_permission import (
        assign_permission_to_role, get_or_create_permission,
        get_or_create_role, remove_permission_from_role)
    # Ensure the delegation used above cannot leak across tests.
    with app.app_context():
        role = get_or_create_role("super_admin")
        perm = get_or_create_permission("transport.settings")
        try:
            remove_permission_from_role(role, perm)
        except Exception:
            pass
    sud = _user(app, f"fgn_{uuid.uuid4().hex[:6]}", "super_admin")
    _login(app, client, sud)
    assert client.put(_config_url(),
                      json={"tables": _tables()}).status_code == 403
    assert client.get(_config_url()).status_code == 403


def test_ordinary_admin_denied(app, client):
    admin = _user(app, f"fga_{uuid.uuid4().hex[:6]}", "admin")
    _login(app, client, admin)
    assert client.put(_config_url(),
                      json={"tables": _tables()}).status_code == 403
    assert client.get(_config_url()).status_code == 403


def test_plain_user_denied(app, authenticated_client):
    assert authenticated_client.put(
        _config_url(), json={"tables": _tables()},
        follow_redirects=False).status_code == 403
    assert authenticated_client.get(
        _config_url(), follow_redirects=False).status_code == 403


def test_anonymous_denied(app, anonymous_client):
    assert anonymous_client.put(
        _config_url(), json={"tables": _tables()},
        follow_redirects=False).status_code in (302, 401)
    assert anonymous_client.get(
        _config_url(), follow_redirects=False).status_code in (302, 401)


def test_config_validation_rejects(app, client):
    owner = _user(app, f"fgv_{uuid.uuid4().hex[:6]}", "owner")
    _login(app, client, owner)
    bad = _tables()
    del bad["base_fares"]
    assert client.put(_config_url(), json={"tables": bad}).status_code == 400
    bad2 = _tables()
    bad2["distance_rate_per_km"] = -1
    assert client.put(_config_url(), json={"tables": bad2}).status_code == 400
    assert client.put(_config_url(), json={}).status_code == 400
    assert client.put(
        _config_url(),
        json={"tables": _tables(), "effective_from": "not-a-time"}
    ).status_code == 400


# --- versions, history, effective dates ----------------------------------------------

def test_versions_increment_and_history_preserved(app):
    owner = _user(app, f"fgh_{uuid.uuid4().hex[:6]}", "owner")
    with app.app_context():
        first = update_fare_tables(_tables(base=10.0), actor_user_id=owner)
        second = update_fare_tables(_tables(base=99.0), actor_user_id=owner)
    assert second["version"] == first["version"] + 1
    with app.app_context():
        config = read_configuration()
    assert config["version"] == second["version"]
    versions = [h["version"] for h in config["history"]]
    assert first["version"] in versions
    assert all("changed_at" in h for h in config["history"])
    assert all("user_id" not in str(h) for h in config["history"])


def test_effective_dates_stage_without_activating(app):
    owner = _user(app, f"fge_{uuid.uuid4().hex[:6]}", "owner")
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    with app.app_context():
        before_tables, before_version, _ = resolve_tables()
        staged = update_fare_tables(_tables(base=77.0), actor_user_id=owner,
                                    effective_from=future)
        live_tables, live_version, _ = resolve_tables()
        future_version = tables_version_at(
            datetime.now(timezone.utc) + timedelta(days=3))
    assert live_tables == before_tables  # staged, not active
    assert live_version == before_version
    assert future_version == staged["version"]
    assert staged["effective_from"] == future


def test_historical_reproducibility(app):
    owner = _user(app, f"fgr_{uuid.uuid4().hex[:6]}", "owner")
    past = datetime.now(timezone.utc) - timedelta(days=3)
    with app.app_context():
        update_fare_tables(_tables(base=11.0), actor_user_id=owner,
                           effective_from=past.isoformat())
        update_fare_tables(_tables(base=22.0), actor_user_id=owner)
        old_version = tables_version_at(past + timedelta(hours=1))
        old_tables, _, _ = resolve_tables(at=past + timedelta(hours=1))
    assert old_tables["base_fares"]["on_demand"] == 11.0
    assert old_version >= 1


# --- engine consumption -----------------------------------------------------------------

def test_engine_and_preview_consume_active_config(app, client):
    owner = _user(app, f"fgc_{uuid.uuid4().hex[:6]}", "owner")
    with app.app_context():
        update_fare_tables(_tables(base=40.0), actor_user_id=owner,
                           effective_from="2020-01-01T00:00:00+00:00")
        out = calculate_estimate(service_type="on_demand",
                                 vehicle_class="economy", distance_km=0,
                                 at=datetime(2026, 3, 10, 14, 0, 0))
    assert out["total"] == Decimal("40.00")
    assert out["version"] >= 1
    _login(app, client, owner)
    resp = client.post("/api/transport/fare/estimate",
                       json={"service_type": "on_demand"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["version"] == out["version"]


def test_final_follows_configured_minimum(app):
    from decimal import Decimal
    owner = _user(app, f"fgm_{uuid.uuid4().hex[:6]}", "owner")
    with app.app_context():
        tables = _tables()
        tables["minimum_fare"] = 9.0
        update_fare_tables(tables, actor_user_id=owner)
        assert calculate_final(Decimal("1.00")) == Decimal("9.00")


def test_cache_invalidation_on_write(app, client):
    owner = _user(app, f"fgw_{uuid.uuid4().hex[:6]}", "owner")
    _login(app, client, owner)
    client.put(_config_url(), json={"tables": _tables(base=13.0)})
    first = client.get(_config_url()).get_json()["data"]["version"]
    client.put(_config_url(), json={"tables": _tables(base=14.0)})
    second = client.get(_config_url()).get_json()["data"]["version"]
    assert second == first + 1  # no stale read past the write


def test_no_internal_ids_in_config_payloads(app, client):
    owner = _user(app, f"fgi_{uuid.uuid4().hex[:6]}", "owner")
    _login(app, client, owner)
    client.put(_config_url(), json={"tables": _tables()})
    blob = json.dumps(client.get(_config_url()).get_json())
    assert '"id":' not in blob and "user_id" not in blob
