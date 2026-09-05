"""
Standalone (no pytest-flask autouse) confirmation that flask.g IS properly
isolated between sequential test-client requests in Flask 3.1.2 + Flask-Login.

This bypasses pytest-flask's _push_request_context autouse fixture entirely,
proving the production Flask/Flask-Login machinery is correct.
"""
import os
import sys
import json

sys.path.insert(0, os.getcwd())
os.environ.setdefault("FLASK_ENV", "testing")

from flask import g
from flask.globals import _cv_app
from app import create_app
import inspect


def main():
    app = create_app()
    app.config["TESTING"] = True

    @app.route("/g1")
    def g1():
        actual_g = g._get_current_object()
        app_ctx = _cv_app.get(None)
        return json.dumps({
            "g_id": id(actual_g),
            "app_ctx_id": id(app_ctx) if app_ctx else None,
        })

    @app.route("/g2")
    def g2():
        actual_g = g._get_current_object()
        app_ctx = _cv_app.get(None)
        return json.dumps({
            "g_id": id(actual_g),
            "app_ctx_id": id(app_ctx) if app_ctx else None,
        })

    # NOTE: no app.app_context() is pushed here at all.
    print(f"Before any request: app_context_active={_cv_app.get(None) is not None}")

    client = app.test_client()
    d1 = json.loads(client.get("/g1").data)
    print(f"req1: g_id={d1['g_id']} app_ctx_id={d1['app_ctx_id']}")
    btw = _cv_app.get(None)
    print(f"between: app_ctx_active={btw is not None}")
    d2 = json.loads(client.get("/g2").data)
    print(f"req2: g_id={d2['g_id']} app_ctx_id={d2['app_ctx_id']}")

    isolated = d1["g_id"] != d2["g_id"] and d1["app_ctx_id"] != d2["app_ctx_id"]
    if isolated:
        print("RESULT: g IS properly isolated between requests.")
    else:
        print("RESULT: g NOT isolated (but nothing pushed an app context!).")
    return 0 if isolated else 1


if __name__ == "__main__":
    sys.exit(main())
