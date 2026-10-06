"""UI-20: Content-Security-Policy enforcement proofs.

Node-owned additive tests. UI-20 owns technical CSP / browser-console hygiene
only. It asserts the policy the application actually DELIVERS, so the
2026-10-03 CSP-ENFORCEMENT-01 regression class (an EMPTY enforcement header
that silently disabled the whole policy) cannot recur unguarded.

Why these assertions exist
--------------------------
Before UI-20 there was NO automated coverage of the CSP response header
(`grep -r "Content-Security-Policy" tests/` matched nothing). The
CSP-ENFORCEMENT-01 defect shipped, was found by hand in a browser, was fixed,
and shipped again with no test to hold it. That is the hygiene debt UI-20
closes.

Browser-proven enforcement semantics these tests encode
--------------------------------------------------------
Verified in Chrome against the live enforced policy
(`script-src 'self' 'nonce-X' https://cdn.jsdelivr.net`):

  R1  external <script src=allowed-host>  -> ALLOWED even with NO nonce
  R2  inline <script> (no src)            -> BLOCKED unless it carries the
                                              matching nonce
  R3  inline event-handler attribute      -> BLOCKED always (no
                                              'unsafe-inline', and hashes do
                                              not apply without
                                              'unsafe-hashes')

R1 is why a non-nonced EXTERNAL script is a hygiene inconsistency, not an
enforced violation. R2/R3 are the enforced-violation classes. Template-side
remediation of R2/R3 is a separate multi-workstream migration and is explicitly
OUT of UI-20 scope; see docs/transport/nodes/UI-20-evidence.md.
"""

import re

import pytest

# ---------------------------------------------------------------------------
# Paths exercised. All are anonymously reachable, so these proofs need no
# fixtures beyond the session app/client and no domain data.
# ---------------------------------------------------------------------------
PATHS = ("/login", "/", "/events/", "/register")

ENFORCE_HEADER = "Content-Security-Policy"
REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only"

# Nonce source expressions are `secrets.token_urlsafe(16)` -> 22 chars of
# URL-safe base64. The floor is deliberately loose; it exists to catch a
# truncated / hardcoded / empty nonce, not to re-specify the generator.
MIN_NONCE_LEN = 16
NONCE_RE = re.compile(r"'nonce-([^']+)'")


def _directives(policy):
    """Parse a CSP into {directive_name: [source expressions]}."""
    out = {}
    for raw in policy.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split()
        out[parts[0]] = parts[1:]
    return out


def _enforce(client, path):
    resp = client.get(path, follow_redirects=False)
    return resp, resp.headers.get(ENFORCE_HEADER)


def _nonce(policy, where=""):
    """Extract the nonce source expression value, failing loudly if absent."""
    m = NONCE_RE.search(policy)
    assert m is not None, f"{where}: no 'nonce-...' source expression in {policy!r}"
    return m.group(1)


# ---------------------------------------------------------------------------
# 1. The header exists and carries a real policy
#    (direct regression guard for CSP-ENFORCEMENT-01)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", PATHS)
def test_enforcement_header_is_present_and_non_empty(client, path):
    """An ABSENT or EMPTY Content-Security-Policy parses to an empty policy
    set, i.e. nothing is enforced while looking configured. That exact
    failure shipped on 2026-10-03 with no test to catch it."""
    resp, csp = _enforce(client, path)
    assert resp.status_code in (200, 301, 302, 308), (
        f"{path} unexpected status {resp.status_code}; CSP assertions skipped"
    )
    assert csp is not None, f"{path}: {ENFORCE_HEADER} header ABSENT"
    assert csp.strip(), f"{path}: {ENFORCE_HEADER} present but EMPTY (nothing enforced)"
    assert "default-src" in csp, f"{path}: no default-src in enforced policy"


@pytest.mark.parametrize("path", PATHS)
def test_enforced_policy_has_no_malformed_directive(client, path):
    """Every interior ';' segment must be a real `name sources...` directive.

    Guards the operator-precedence defect class that produced the empty
    enforcement header on 2026-10-03: a half-assembled policy that still
    *looks* configured. A single TRAILING ';' is valid CSP (the parser skips
    empty directives) so it is tolerated here and recorded as a cosmetic
    finding rather than failed as a defect."""
    _, csp = _enforce(client, path)
    assert csp is not None
    segments = csp.split(";")
    # Tolerate exactly one trailing separator; anything else is malformation.
    if segments and not segments[-1].strip():
        segments = segments[:-1]
    for seg in segments:
        assert seg.strip(), (
            f"{path}: interior empty directive segment in {csp!r}"
        )
    parsed = _directives(csp)
    assert parsed, f"{path}: policy parsed to zero directives"
    for name, sources in parsed.items():
        assert name, f"{path}: directive with empty name"
        if name not in ("report-to", "report-uri"):
            assert sources, f"{path}: directive {name!r} has no source expressions"


def test_enforced_policy_trailing_separator_is_at_most_one(client):
    """Cosmetic drift guard on the policy assembly in
    app/__init__.py::after_request_pipeline. Currently the enforced policy ends
    'base-uri \'self\'; ' with one trailing separator because
    `upgrade_directive` is empty when SystemConfig.CSP_UPGRADE_INSECURE is
    false. Harmless (CSP parsing skips empty directives) but recorded so the
    shape of the header is not left to drift unnoticed."""
    _, csp = _enforce(client, "/")
    body = csp.rstrip(";")
    assert len(csp) - len(body) <= 1, (
        f"enforced policy ends with multiple separators: ...{csp[-40:]!r}"
    )


# ---------------------------------------------------------------------------
# 2. script-src must not be weakened
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("banned", [
    "'unsafe-inline'",   # would re-enable R2 and R3 entirely
    "'unsafe-eval'",     # would re-enable string-to-code execution
    "'unsafe-hashes'",   # would make hashes apply to R3 inline handlers
])
def test_script_src_contains_no_unsafe_weakening(client, path, banned):
    _, csp = _enforce(client, path)
    script_src = _directives(csp)["script-src"]
    assert banned not in script_src, (
        f"{path}: script-src weakened by {banned}: {' '.join(script_src)}"
    )


def test_script_src_always_carries_a_nonce_expression(client):
    """script-src must offer a nonce path, otherwise no inline script on any
    page could ever execute and every nonced template is dead markup."""
    for path in PATHS:
        _, csp = _enforce(client, path)
        script_src = _directives(csp)["script-src"]
        assert any(s.startswith("'nonce-") for s in script_src), (
            f"{path}: script-src has no nonce source expression"
        )


# ---------------------------------------------------------------------------
# 3. Nonce generation and propagation
# ---------------------------------------------------------------------------

def test_nonce_is_generated_fresh_for_every_request(client):
    """A reused nonce would let one page's script authorise another's."""
    nonces = []
    for _ in range(5):
        _, csp = _enforce(client, "/login")
        nonces.append(_nonce(csp, "/login"))
    assert len(set(nonces)) == len(nonces), f"nonce reused across requests: {nonces}"


def test_nonce_is_non_trivial(client):
    for path in PATHS:
        _, csp = _enforce(client, path)
        nonce = _nonce(csp, path)
        assert len(nonce) >= MIN_NONCE_LEN, (
            f"{path}: nonce too short ({len(nonce)} chars): {nonce!r}"
        )


def test_nonce_in_header_equals_nonce_rendered_into_body(client):
    """The load-bearing propagation invariant.

    `inject_csp_nonce` (context processor) and `set_csp_nonce` (before_request)
    are two separate registrations. If they ever diverge, the header advertises
    a nonce that no markup carries, and every inline script is silently blocked
    (R2) while the policy still looks correct in the header. This is the exact
    failure the browser probe on /login and /register observed."""
    for path in PATHS:
        resp, csp = _enforce(client, path)
        if resp.status_code != 200:
            continue
        body = resp.get_data(as_text=True)
        rendered = set(re.findall(r'nonce="([^"]+)"', body))
        if not rendered:
            # Page genuinely renders no nonced markup; nothing to correlate.
            continue
        header_nonce = _nonce(csp, path)
        assert header_nonce in rendered, (
            f"{path}: header nonce {header_nonce!r} not present in rendered "
            f"body nonces {sorted(rendered)}"
        )


# ---------------------------------------------------------------------------
# 4. Report-only policy is the staged-migration instrument, and must stay
#    strictly stricter than enforcement on style-src
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", PATHS)
def test_report_only_policy_is_present_and_stricter_on_style_src(client, path):
    """Report-only exists to observe inline styles before 'unsafe-inline' is
    dropped from the enforced style-src. If report-only ever gains
    'unsafe-inline' it stops measuring anything and the migration signal dies."""
    resp = client.get(path, follow_redirects=False)
    ro = resp.headers.get(REPORT_ONLY_HEADER)
    assert ro is not None, f"{path}: {REPORT_ONLY_HEADER} ABSENT"
    csp = resp.headers.get(ENFORCE_HEADER)
    enforce_style = _directives(csp)["style-src"]
    report_style = _directives(ro)["style-src"]
    assert "'unsafe-inline'" in enforce_style, (
        f"{path}: enforced style-src no longer permits inline styles; "
        "the staged migration in app/Documentation/CSP_POLICY.md has landed "
        "and this test needs updating with it"
    )
    assert "'unsafe-inline'" not in report_style, (
        f"{path}: report-only style-src permits inline styles, so it can no "
        "longer observe the inline-style debt it exists to measure"
    )


@pytest.mark.parametrize("path", PATHS)
def test_reporting_directives_and_endpoints_agree(client, path):
    """A report-only policy pointing at a group the app never declares, or at
    an endpoint that does not exist, silently discards every violation."""
    resp = client.get(path, follow_redirects=False)
    ro = _directives(resp.headers[REPORT_ONLY_HEADER])
    assert "report-to" in ro or "report-uri" in ro, (
        f"{path}: report-only policy declares no reporting directive"
    )
    report_to = resp.headers.get("Report-To")
    reporting_endpoints = resp.headers.get("Reporting-Endpoints")
    assert report_to and "csp-endpoint" in report_to, (
        f"{path}: Report-To header missing or does not name csp-endpoint"
    )
    assert reporting_endpoints and "csp-report" in reporting_endpoints, (
        f"{path}: Reporting-Endpoints header missing or does not name /csp-report"
    )


# ---------------------------------------------------------------------------
# 5. Baseline hardening directives
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", PATHS)
def test_baseline_hardening_directives_present(client, path):
    _, csp = _enforce(client, path)
    d = _directives(csp)
    assert d["object-src"] == ["'none'"], f"{path}: object-src not 'none'"
    assert d["frame-ancestors"] == ["'none'"], f"{path}: frame-ancestors not 'none'"
    assert d["base-uri"] == ["'self'"], f"{path}: base-uri not 'self'"
    assert d["form-action"] == ["'self'"], f"{path}: form-action not 'self'"


@pytest.mark.parametrize("path", PATHS)
def test_companion_security_headers_present(client, path):
    resp, _ = _enforce(client, path)
    h = resp.headers
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    # geolocation=(self) is a deliberate, documented driver-console dependency.
    assert "geolocation=(self)" in (h.get("Permissions-Policy") or "")
    assert h.get("Cross-Origin-Opener-Policy") == "same-origin"
    assert h.get("Cross-Origin-Resource-Policy") == "same-origin"
    assert h.get("X-Permitted-Cross-Domain-Policies") == "none"


# ---------------------------------------------------------------------------
# 6. Legitimate external origins are an explicit, drift-guarded allowlist
# ---------------------------------------------------------------------------

# Mirrors app/__init__.py::after_request_pipeline. Changing the allowlist is a
# security decision: update this table AND app/Documentation/CSP_POLICY.md in
# the same node, never one alone.
EXPECTED_ALLOWLIST = {
    "script-src": {"'self'", "https://cdn.jsdelivr.net"},
    "style-src": {
        "'self'", "'unsafe-inline'", "https://fonts.googleapis.com",
        "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com",
        "https://use.fontawesome.com",
    },
    "font-src": {
        "'self'", "https://fonts.gstatic.com", "https://cdnjs.cloudflare.com",
        "https://use.fontawesome.com", "https://cdn.jsdelivr.net",
    },
    "img-src": {"'self'", "data:", "https:"},
    "connect-src": {"'self'", "https://cdn.jsdelivr.net"},
}


def test_third_party_origin_allowlist_has_not_drifted(client):
    """Silent allowlist growth is how a supply-chain origin becomes trusted.
    The nonce source expression is filtered out; everything else must match
    exactly."""
    _, csp = _enforce(client, "/")
    d = _directives(csp)
    for directive, expected in EXPECTED_ALLOWLIST.items():
        actual = {s for s in d[directive] if not s.startswith("'nonce-")}
        assert actual == expected, (
            f"{directive} allowlist drift.\n  expected: {sorted(expected)}\n"
            f"  actual:   {sorted(actual)}\n  extra:    {sorted(actual - expected)}\n"
            f"  missing:  {sorted(expected - actual)}"
        )


def test_upgrade_insecure_requests_is_conditional_and_consistent(client):
    """`should_upgrade_insecure()` reads SystemConfig.CSP_UPGRADE_INSECURE and
    DB-fails closed to False. Both policies must make the SAME decision, and
    when enabled it must be the LAST directive so it is not silently dropped
    by a trailing-concatenation mistake."""
    resp = client.get("/", follow_redirects=False)
    enforce = resp.headers[ENFORCE_HEADER]
    report_only = resp.headers[REPORT_ONLY_HEADER]

    enforce_has = "upgrade-insecure-requests" in enforce
    report_has = "upgrade-insecure-requests" in report_only
    assert enforce_has == report_has, (
        "enforced and report-only policies disagree on upgrade-insecure-requests"
    )

    if enforce_has:
        enforce_dirs = [s.strip().split()[0] for s in enforce.split(";") if s.strip()]
        assert enforce_dirs[-1] == "upgrade-insecure-requests", (
            f"upgrade-insecure-requests is not the final directive: {enforce_dirs}"
        )


# ---------------------------------------------------------------------------
# 7. /csp-report collector must accept reports (it is the only place violations
#    are recorded server-side)
# ---------------------------------------------------------------------------

def test_csp_report_endpoint_accepts_and_swallows_a_report(app):
    """/csp-report is POST-only. A 405 or 500 here means browser reports are
    being dropped and the whole report-only instrument is inert."""
    with app.test_client() as c:
        resp = c.post(
            "/csp-report",
            json={
                "csp-report": {
                    "document-uri": "http://127.0.0.1/login",
                    "violated-directive": "script-src-elem",
                    "blocked-uri": "inline",
                }
            },
        )
    assert resp.status_code == 204, (
        f"/csp-report returned {resp.status_code}; browser violation reports "
        "are being dropped"
    )


# ---------------------------------------------------------------------------
# 8. Source-level invariant for the ONE template UI-20 is allowed to police
#    end-to-end: the shell that every page inherits.
#    Kept to a precise, non-brittle assertion. Repo-wide R2/R3 remediation is
#    a separate migration (see evidence file) and is not asserted here.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "KNOWN DEFECT, tracked not fixed by UI-20. templates/base.html carries "
        "9 inline onclick handlers (L127, L334, L335, L342, L348, L634, L635, "
        "L639, L642). Under the enforced policy these are blocked "
        "(browser-proven by UI-20), so the controls are dead -- notably the "
        "module-disabled warnings, where event.preventDefault() never runs and "
        "the link navigates instead of warning. UI-20 does not fix it: "
        "base.html is a shared shell inherited by every page (repo-wide blast "
        "radius = broad refactor, forbidden as a minimal change), it is dirty "
        "from another workstream, and AGENTS.md S28 module-toggle behaviour is "
        "explicitly outside UI-20 scope. Remediation belongs to a dedicated "
        "CSP-migration node. See docs/transport/nodes/UI-20-evidence.md."
    ),
    strict=False,
)
def test_base_template_carries_no_inline_event_handlers():
    """Tripwire for the shared shell. templates/base.html is inherited by every
    page, so an inline handler there is the highest-leverage R3 site in the
    repo. Expected to xfail today; flips to XPASS when the migration lands."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    base = (root / "templates" / "base.html").read_text(encoding="utf-8")
    offenders = re.findall(r"\s(on[a-zA-Z]+)\s*=\s*[\"']", base)
    offenders = [o for o in offenders if o.lower() not in ("once", "only")]
    assert not offenders, (
        f"templates/base.html carries inline event handler(s) "
        f"{sorted(set(offenders))}; under the enforced policy these are blocked "
        "(browser-proven) and the controls are dead"
    )