from types import SimpleNamespace
from pathlib import Path

import pytest
from flask import Flask, session

from app.auth import routes as auth_routes
from app.auth.context import (
    ContextDescriptor,
    ContextSwitchError,
    ContextType,
    get_active_context,
    get_available_contexts,
    switch_context,
)


def _user():
    org = SimpleNamespace(
        id=101,
        org_id="org-abc",
        legal_name="ABC Hotel",
        is_active=True,
        is_deleted=False,
        lifecycle_state="approved",
    )
    org_role = SimpleNamespace(id=201, name="org_owner", is_deleted=False, is_active=True)
    membership = SimpleNamespace(
        id=301,
        organisation_id=org.id,
        organisation=org,
        is_active=True,
        is_deleted=False,
        roles=[SimpleNamespace(id=401, role=org_role, is_deleted=False)],
    )
    event = SimpleNamespace(
        id=501,
        public_id="event-xyz",
        name="AFCON Fan Festival",
        status="published",
        is_deleted=False,
    )
    event_role = SimpleNamespace(
        id=601,
        event=event,
        role="organiser",
        is_active=True,
        is_deleted=False,
    )
    driver = SimpleNamespace(
        id=701,
        driver_code="DRV-001",
        verification_tier="platform_verified",
        compliance_status="approved",
        is_deleted=False,
    )
    roles = [
        SimpleNamespace(id=801, role=SimpleNamespace(id=901, name="admin", scope="global"), is_deleted=False),
        SimpleNamespace(id=802, role=SimpleNamespace(id=902, name="event_manager", scope="global"), is_deleted=False),
    ]
    return SimpleNamespace(
        id=1,
        public_id="user-123",
        is_authenticated=True,
        is_active=True,
        is_deleted=False,
        roles=roles,
        organisations=[membership],
        event_roles=[event_role],
        driver_profile=driver,
    )


@pytest.fixture
def request_context():
    app = Flask("auth-context-tests")
    app.secret_key = "context-test-secret"
    for endpoint, rule in (
        ("user.dashboard", "/user/dashboard"),
        ("org.org_dashboard", "/org/<org_id>/dashboard"),
        ("events.organizer_dashboard", "/events/organizer/dashboard/<identifier>"),
        ("transport.dashboard_overview", "/transport/dashboard/overview"),
        ("transport.driver_dashboard", "/transport/driver-dashboard"),
        ("accommodation.host_dashboard", "/accommodation/host/dashboard"),
        ("admin.super_dashboard", "/admin/super"),
        ("admin.owner.dashboard", "/admin/owner/dashboard"),
    ):
        app.add_url_rule(rule, endpoint=endpoint, view_func=lambda: "")
    with app.test_request_context("/"):
        yield


def test_available_contexts_normalize_existing_assignments(request_context):
    contexts = get_available_contexts(_user())

    assert contexts[0].type is ContextType.PERSONAL
    assert {context.role for context in contexts if context.type is ContextType.PLATFORM} == {
        "admin",
        "event_manager",
    }
    assert any(
        context.type is ContextType.ORGANISATION
        and context.public_id == "org-abc"
        and context.role == "org_owner"
        for context in contexts
    )
    assert any(
        context.type is ContextType.EVENT
        and context.public_id == "event-xyz"
        and context.role == "organiser"
        for context in contexts
    )
    assert any(context.type is ContextType.DRIVER for context in contexts)
    assert all("permission_lookup_metadata" not in context.to_dict() for context in contexts)
    assert all(context.to_dict()["public_id"] != 101 for context in contexts)


def test_organisation_context_uses_public_workspace_identifier(request_context):
    organisation_context = next(
        context
        for context in get_available_contexts(_user())
        if context.type is ContextType.ORGANISATION
    )

    assert organisation_context.workspace_url == "/org/org-abc/dashboard"
    assert "101" not in organisation_context.workspace_url


def test_context_workspace_urls_target_registered_dashboards(request_context):
    contexts = get_available_contexts(_user())

    urls = {(context.type, context.role): context.workspace_url for context in contexts}

    assert urls[(ContextType.ORGANISATION, "org_owner")] == "/org/org-abc/dashboard"
    assert urls[(ContextType.EVENT, "organiser")] == "/events/organizer/dashboard/event-xyz"
    assert urls[(ContextType.DRIVER, "driver")] == "/transport/driver-dashboard"
    assert urls[(ContextType.PLATFORM, "admin")] == "/admin/super"


def test_baseline_user_and_fan_assignments_are_not_platform_contexts(request_context):
    user = _user()
    user.roles.extend(
        [
            SimpleNamespace(id=803, role=SimpleNamespace(id=903, name="user", scope="global"), is_deleted=False),
            SimpleNamespace(id=804, role=SimpleNamespace(id=904, name="fan", scope="global"), is_deleted=False),
        ]
    )

    platform_roles = {
        context.role for context in get_available_contexts(user) if context.type is ContextType.PLATFORM
    }

    assert "user" not in platform_roles
    assert "fan" not in platform_roles


def test_owner_platform_context_targets_owner_workspace(request_context):
    user = _user()
    user.roles = [
        SimpleNamespace(id=805, role=SimpleNamespace(id=905, name="owner", scope="global"), is_deleted=False),
    ]

    owner_context = next(
        context
        for context in get_available_contexts(user)
        if context.type is ContextType.PLATFORM
    )

    assert owner_context.role == "owner"
    assert owner_context.workspace_url == "/admin/owner/dashboard"


def test_switch_preserves_identity_and_writes_only_selection(request_context):
    user = _user()
    descriptor = switch_context(
        user,
        {"type": "organisation", "id": "org-abc", "role": "org_owner"},
    )

    assert descriptor.type is ContextType.ORGANISATION
    assert descriptor.public_id == "org-abc"
    assert user.public_id == "user-123"
    assert dict(session) == {
        "active_context_type": "organisation",
        "active_context_id": "org-abc",
        "active_role": "org_owner",
    }


def test_revoked_selection_falls_back_to_personal(request_context):
    user = _user()
    switch_context(user, {"type": "event", "id": "event-xyz", "role": "organiser"})
    user.event_roles[0].is_active = False

    active = get_active_context(user)

    assert active.type is ContextType.PERSONAL
    assert "active_context_type" not in session
    assert user.public_id == "user-123"


def test_unassigned_or_forged_context_is_rejected(request_context):
    user = _user()

    with pytest.raises(ContextSwitchError):
        switch_context(user, {"type": "organisation", "id": "org-other", "role": "org_owner"})

    with pytest.raises(ContextSwitchError):
        switch_context(user, {"type": "event", "id": "event-xyz", "role": "admin"})

    with pytest.raises(ContextSwitchError):
        switch_context(user, {"type": "unsupported", "id": "anything"})


def test_switch_endpoint_audits_success_and_preserves_principal(monkeypatch):
    app = Flask("switch-endpoint-tests")
    app.secret_key = "endpoint-test-secret"
    user = _user()
    previous = ContextDescriptor(ContextType.PERSONAL, None, "Personal", "user")
    selected = ContextDescriptor(
        ContextType.ORGANISATION,
        "org-abc",
        "ABC Hotel — Org Owner",
        "org_owner",
        "/org/org-abc",
    )
    audit_calls = []

    monkeypatch.setattr(auth_routes, "current_user", user)
    monkeypatch.setattr(
        "app.auth.context.get_active_context",
        lambda _user: previous,
    )
    monkeypatch.setattr(
        "app.auth.context.switch_context",
        lambda _user, _requested: selected,
    )
    monkeypatch.setattr(
        "app.audit.forensic_audit.ForensicAuditService.log_attempt",
        lambda **kwargs: audit_calls.append(("attempt", kwargs)) or "audit-1",
    )
    monkeypatch.setattr(
        "app.audit.forensic_audit.ForensicAuditService.log_completion",
        lambda *args, **kwargs: audit_calls.append(("completion", args, kwargs)) or True,
    )

    with app.test_request_context(
        "/switch-context",
        method="POST",
        json={
            "type": "organisation",
            "id": "org-abc",
            "role": "org_owner",
            "next": "/user/dashboard",
        },
    ):
        response = auth_routes.switch_context.__wrapped__()

    assert response.status_code == 200
    assert response.get_json()["redirect"] == "/org/org-abc"
    assert user.public_id == "user-123"
    assert [call[0] for call in audit_calls] == ["attempt", "completion"]


def test_switch_endpoint_blocks_invalid_context_and_route_is_post_only(monkeypatch):
    app = Flask("switch-endpoint-negative-tests")
    app.secret_key = "endpoint-negative-secret"
    user = _user()
    blocked = []

    monkeypatch.setattr(auth_routes, "current_user", user)
    monkeypatch.setattr(
        "app.auth.context.get_active_context",
        lambda _user: ContextDescriptor(ContextType.PERSONAL, None, "Personal", "user"),
    )

    def reject(_user, _requested):
        raise ContextSwitchError("not assigned")

    monkeypatch.setattr("app.auth.context.switch_context", reject)
    monkeypatch.setattr(
        "app.audit.forensic_audit.ForensicAuditService.log_attempt",
        lambda **kwargs: "audit-2",
    )
    monkeypatch.setattr(
        "app.audit.forensic_audit.ForensicAuditService.log_blocked",
        lambda **kwargs: blocked.append(kwargs) or "blocked-1",
    )

    with app.test_request_context(
        "/switch-context",
        method="POST",
        json={"type": "organisation", "id": "org-other", "role": "org_owner"},
    ):
        response = app.make_response(auth_routes.switch_context.__wrapped__())

    assert response.status_code == 400
    assert response.get_json()["success"] is False
    assert blocked and blocked[0]["entity_id"] == "org-other"
    assert "current_user.id" not in str(blocked[0])

    app.register_blueprint(auth_routes.auth_bp)
    rules = [rule for rule in app.url_map.iter_rules() if "switch-context" in rule.rule]
    assert rules and all(rule.methods == {"POST", "OPTIONS"} for rule in rules)


def test_shell_template_uses_canonical_context_contract():
    root = Path(__file__).resolve().parents[1]
    shell = (root / "templates" / "user" / "base_user_dashboard.html").read_text(encoding="utf-8")

    assert "available_contexts" in shell
    assert "active_context" in shell
    assert "role_dashboard_links" not in shell
    assert 'style=' not in shell
    assert '<script>' not in shell
    assert 'dashboard-shell.js' in shell


def test_dashboard_shell_is_inside_parent_content_block():
    root = Path(__file__).resolve().parents[1]
    shell = (root / "templates" / "user" / "base_user_dashboard.html").read_text(encoding="utf-8")

    content_start = shell.index("{% block content %}")
    shell_start = shell.index('id="mobileOverlay"')
    content_end = shell.index("{% endblock %}", shell_start)

    assert content_start < shell_start < content_end
