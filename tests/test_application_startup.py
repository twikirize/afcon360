"""Reliable application startup verification.

Regression check for the application factory: importing ``create_app`` and
calling it must succeed and produce a fully initialised Flask application.

This mirrors the project's canonical startup sanity check
(AGENTS.md §37: ``python -c "from app import create_app"``) but asserts the
factory result inside the pytest suite, using the same canonical test
configuration as ``tests/conftest.py``. It is a real, unmocked factory call —
no fake or stubbed startup.

Nothing mocked, no production behaviour changed, no schema/migration touched.
"""
from app import create_app
from app.config import TestingConfig


def test_create_app_initialises_application():
    """The application factory must import and build the app without raising."""
    app = create_app(config_object=TestingConfig)

    assert app is not None
    assert app.name == "app"
    assert app.config["TESTING"] is True

    # A factory-complete app has routed endpoints registered.
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/health/ping" in rules