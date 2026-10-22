"""Runtime control for the Socket.IO transport.

Socket.IO is optional at runtime. It must never be initialised for one-shot
CLI/Alembic processes (there are no connected browser clients), and the owner
can disable it persistently with the ``SOCKETIO_ENABLED`` SystemConfig row.
"""

import os
import sys
from pathlib import Path


def is_bare_cli_invocation() -> bool:
    """True for one-shot Flask/Alembic CLI commands.

    False for flask run, gunicorn, uvicorn, python app.py, or any WSGI server.
    A one-shot command has zero connected Socket.IO clients, so starting the
    Redis message queue and emitting to it is pointless (and can block/retry
    indefinitely when Redis is unreachable).
    """
    orig = [str(arg) for arg in (getattr(sys, "orig_argv", None) or sys.argv)]
    if not orig:
        return False

    def _stem(path: str) -> str:
        return Path(path).stem.lower()

    first = _stem(orig[0])

    # Direct Alembic invocations: alembic ... / python -m alembic ...
    if first == "alembic":
        return True
    if first.startswith("python") and len(orig) > 1:
        if _stem(orig[1]) == "alembic":
            return True
        if len(orig) > 2 and orig[1] == "-m" and orig[2] == "alembic":
            return True

    # Flask CLI invocations.
    args = []
    if first in ("flask", "flask-script"):
        args = orig[1:]
    elif first.startswith("python") and len(orig) > 1:
        # Windows console-script launchers pass [python.exe, flask.exe, ...].
        if _stem(orig[1]) in ("flask", "flask-script"):
            args = orig[2:]
        elif len(orig) > 2 and orig[1] == "-m" and orig[2] in ("flask", "flask-script"):
            args = orig[3:]
        else:
            return False
    else:
        return False

    # Skip Flask global options so e.g. `flask --app app run` still counts as run.
    value_options = {"-A", "--app", "-e", "--env-file"}
    index = 0
    while index < len(args):
        token = args[index]
        if token in value_options:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break

    subcmd = args[index] if index < len(args) else ""
    return subcmd not in ("run", "runserver")


def socketio_enabled() -> bool:
    """Effective Socket.IO allow-flag for the current app (or process env)."""
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            return bool(current_app.config.get("SOCKETIO_ENABLED", True))
    except Exception:
        pass
    return os.getenv("SOCKETIO_ENABLED", "true").strip().lower() not in (
        "false",
        "0",
        "no",
        "off",
    )


def socketio_server_ready() -> bool:
    """True when the Flask-SocketIO server was actually initialised."""
    try:
        from app.extensions import socketio

        return getattr(socketio, "server", None) is not None
    except Exception:
        return False
