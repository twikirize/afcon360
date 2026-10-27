"""Regression tests for Socket.IO suppression in one-shot CLI processes.

These tests exercise command-line classification and the app-level switch
without starting the Flask server or connecting to PostgreSQL/Redis.
"""

import sys

import pytest

from app import _resolve_socketio_enabled
from app.realtime import is_bare_cli_invocation


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        pytest.param(
            ["alembic", "upgrade", "head"],
            True,
            id="direct-alembic",
        ),
        pytest.param(
            ["python", "-m", "alembic", "upgrade", "head"],
            True,
            id="python-module-alembic",
        ),
        pytest.param(
            ["python.exe", "-m", "alembic", "upgrade", "head"],
            True,
            id="windows-python-module-alembic",
        ),
        pytest.param(
            ["flask", "--app", "app", "db", "upgrade"],
            True,
            id="flask-db-upgrade",
        ),
        pytest.param(
            ["flask", "--app", "app", "db", "current"],
            True,
            id="flask-db-current",
        ),
        pytest.param(
            ["python", "-m", "flask", "--app", "app", "db", "upgrade"],
            True,
            id="python-module-flask-db-upgrade",
        ),
        pytest.param(
            ["python.exe", "flask.exe", "--app", "app", "db", "upgrade"],
            True,
            id="windows-flask-launcher",
        ),
        pytest.param(
            ["flask-script", "db", "upgrade"],
            True,
            id="flask-script-launcher",
        ),
        pytest.param(
            ["flask", "--app", "app", "run"],
            False,
            id="flask-run-is-a-server",
        ),
        pytest.param(
            ["flask", "--app", "app", "runserver"],
            False,
            id="flask-runserver-is-a-server",
        ),
        pytest.param(
            ["python", "-m", "flask", "--app", "app", "run"],
            False,
            id="python-module-flask-run-is-a-server",
        ),
        pytest.param(
            ["gunicorn", "app:create_app()"],
            False,
            id="gunicorn-is-a-server",
        ),
        pytest.param(
            ["uvicorn", "app:app"],
            False,
            id="uvicorn-is-a-server",
        ),
        pytest.param(
            ["python", "app.py"],
            False,
            id="python-app-script-is-not-flask-cli",
        ),
        pytest.param(
            ["python", "-c", "print('probe')"],
            False,
            id="python-one-off-script-is-not-flask-or-alembic",
        ),
    ],
)
def test_is_bare_cli_invocation_classifies_command_lines(
    monkeypatch, argv, expected
):
    monkeypatch.setattr(sys, "orig_argv", argv, raising=False)
    monkeypatch.setattr(sys, "argv", ["pytest"], raising=False)

    assert is_bare_cli_invocation() is expected


def test_is_bare_cli_invocation_falls_back_to_sys_argv(monkeypatch):
    monkeypatch.setattr(sys, "orig_argv", None, raising=False)
    monkeypatch.setattr(
        sys, "argv", ["flask", "--app", "app", "db", "upgrade"], raising=False
    )

    assert is_bare_cli_invocation() is True


def test_is_bare_cli_invocation_prefers_orig_argv_when_available(monkeypatch):
    monkeypatch.setattr(
        sys, "orig_argv", ["flask", "--app", "app", "run"], raising=False
    )
    monkeypatch.setattr(
        sys, "argv", ["flask", "--app", "app", "db", "upgrade"], raising=False
    )

    assert is_bare_cli_invocation() is False


class _AppContextMustNotBeEntered:
    """Fail if a test unexpectedly reaches the DB-backed settings fallback."""

    def app_context(self):
        raise AssertionError(
            "this branch should resolve Socket.IO without entering app context"
        )


def test_bare_cli_forces_socketio_off_even_when_environment_enables_it(
    monkeypatch,
):
    monkeypatch.setattr("app.realtime.is_bare_cli_invocation", lambda: True)
    monkeypatch.setenv("SOCKETIO_ENABLED", "true")

    assert _resolve_socketio_enabled(_AppContextMustNotBeEntered()) is False


@pytest.mark.parametrize(
    ("environment_value", "expected"),
    [
        pytest.param("true", True, id="explicit-true"),
        pytest.param("TRUE", True, id="case-insensitive-true"),
        pytest.param("1", True, id="numeric-true"),
        pytest.param("yes", True, id="yes-is-true"),
        pytest.param("on", True, id="on-is-true"),
        pytest.param("false", False, id="explicit-false"),
        pytest.param("FALSE", False, id="case-insensitive-false"),
        pytest.param("0", False, id="numeric-false"),
        pytest.param("no", False, id="no-is-false"),
        pytest.param("off", False, id="off-is-false"),
    ],
)
def test_non_cli_respects_socketio_environment_override_without_database(
    monkeypatch, environment_value, expected
):
    monkeypatch.setattr("app.realtime.is_bare_cli_invocation", lambda: False)
    monkeypatch.setenv("SOCKETIO_ENABLED", environment_value)

    actual = _resolve_socketio_enabled(_AppContextMustNotBeEntered())

    assert actual is expected
