"""CSP strict-flag regression guard (node-owned, additive).

Asserts the two Content-Security-Policy shapes served by
app/__init__.py::after_request_pipeline under CSP_STRICT_ENFORCE=false/true,
and that the report-only header always carries the strict policy.

Does not modify tests/test_ui_20_csp.py. Uses only the shared session
app/client fixtures; the SystemConfig row it writes is cleaned up by the
conftest row-tracking isolation, and the worker flag cache is reset after
each test so no state leaks between tests.
"""

import pytest

from app import is_csp_strict_enforce, refresh_csp_strict_cache
from app.models.system_config import SystemConfig
from app.extensions import db

ENFORCE_HEADER = "Content-Security-Policy"
REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only"


def _directives(policy):
    out = {}
    for raw in policy.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split()
        out[parts[0]] = parts[1:]
    return out


@pytest.fixture()
def strict_flag(app):
    """Save the stored flag, yield a setter, then restore + refresh cache."""
    with app.app_context():
        prior = SystemConfig.query.filter_by(key="CSP_STRICT_ENFORCE").first()
        prior_value = prior.value if prior is not None else None
    try:
        yield prior_value
    finally:
        with app.app_context():
            if prior_value is None:
                row = SystemConfig.query.filter_by(key="CSP_STRICT_ENFORCE").first()
                if row is not None:
                    db.session.delete(row)
                    db.session.commit()
            else:
                SystemConfig.set(
                    "CSP_STRICT_ENFORCE",
                    prior_value,
                    value_type="bool",
                    category="security",
                    commit=True,
                )
            refresh_csp_strict_cache()


def _set_flag(app, enabled):
    with app.app_context():
        SystemConfig.set(
            "CSP_STRICT_ENFORCE",
            bool(enabled),
            value_type="bool",
            category="security",
            description="Enforce strict CSP (element-level inline requires nonce)",
            commit=True,
        )
    refresh_csp_strict_cache()


def test_flag_resolves_to_false_when_not_set_anywhere(app, strict_flag):
    """Default-off proof: no row, no override -> False (fails closed)."""
    with app.app_context():
        row = SystemConfig.query.filter_by(key="CSP_STRICT_ENFORCE").first()
        if row is not None:
            db.session.delete(row)
            db.session.commit()
    refresh_csp_strict_cache()
    assert is_csp_strict_enforce() is False


def test_permissive_policy_served_when_flag_off(app, client, strict_flag):
    _set_flag(app, False)
    assert is_csp_strict_enforce() is False
    csp = client.get("/", follow_redirects=False).headers.get(ENFORCE_HEADER)
    d = _directives(csp)
    # Permissive keeps element-level style inline allowed ...
    assert "'unsafe-inline'" in d["style-src"]
    assert "style-src-elem" not in d
    # ... while attribute-level inline is explicitly allowed ...
    assert "'unsafe-inline'" in d["script-src-attr"]
    assert "'unsafe-inline'" in d["style-src-attr"]
    # ... and script-src itself is never weakened.
    assert "'unsafe-inline'" not in d["script-src"]


def test_strict_policy_served_when_flag_on(app, client, strict_flag):
    _set_flag(app, True)
    assert is_csp_strict_enforce() is True
    csp = client.get("/", follow_redirects=False).headers.get(ENFORCE_HEADER)
    d = _directives(csp)
    # Strict moves styles to style-src-elem with a nonce path ...
    assert "style-src" not in d
    elem = d["style-src-elem"]
    assert "'unsafe-inline'" not in elem
    assert any(s.startswith("'nonce-") and len(s) > len("'nonce-'") for s in elem)
    # ... while attribute-level inline stays allowed in both modes ...
    assert "'unsafe-inline'" in d["script-src-attr"]
    assert "'unsafe-inline'" in d["style-src-attr"]
    # ... and script-src itself is never weakened.
    assert "'unsafe-inline'" not in d["script-src"]


def test_report_only_always_carries_strict_policy(app, client, strict_flag):
    """Report-only is the always-on violation instrument, independent of
    the flag: style-src-elem with nonce, both *-attr allowed, and the
    reporting directives present — in both modes."""
    for enabled in (False, True):
        _set_flag(app, enabled)
        ro = client.get("/", follow_redirects=False).headers.get(REPORT_ONLY_HEADER)
        assert ro is not None
        d = _directives(ro)
        assert "style-src" not in d
        elem = d["style-src-elem"]
        assert any(s.startswith("'nonce-") and len(s) > len("'nonce-'") for s in elem)
        assert "'unsafe-inline'" in d["script-src-attr"]
        assert "'unsafe-inline'" in d["style-src-attr"]
        assert "report-uri" in d or "report-to" in d
