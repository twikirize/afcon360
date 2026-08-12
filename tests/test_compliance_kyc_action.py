"""Regression tests for the compliance KYC action route aliases."""

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from app.admin import admin_bp
from app.admin.compliance import routes as compliance_routes
from app.kyc.models import KycRecord


def test_kyc_action_route_arguments_match_handler_signature():
    """Both KYC action aliases must dispatch their route keyword safely."""
    test_app = Flask(__name__)
    test_app.register_blueprint(admin_bp)

    handler_signatures = {
        endpoint: inspect.signature(view)
        for endpoint, view in test_app.view_functions.items()
        if endpoint in {"admin.compliance.kyc_action", "admin.compliance.kyc_action_uuid"}
    }

    assert set(handler_signatures) == {
        "admin.compliance.kyc_action",
        "admin.compliance.kyc_action_uuid",
    }

    for rule in test_app.url_map.iter_rules():
        if rule.endpoint not in handler_signatures:
            continue
        parameters = handler_signatures[rule.endpoint].parameters
        assert rule.arguments <= parameters.keys(), (
            f"{rule.endpoint} passes {rule.arguments}, "
            f"but the handler accepts {set(parameters)}"
        )


def test_legacy_kyc_action_form_dispatches_with_kyc_id():
    """The form-generated legacy keyword must reach the action handler."""
    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"
    test_app.register_blueprint(admin_bp)

    record = SimpleNamespace(id=5)
    query = MagicMock()
    query.get.return_value = record

    handler = test_app.view_functions["admin.compliance.kyc_action"]
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__

    with test_app.test_request_context(
        "/admin/compliance/kyc/5/action",
        method="POST",
        data={"action": "noop"},
    ), patch.object(compliance_routes.KycRecord, "query", query):
        response = handler(kyc_id=5)

    assert response.status_code == 302