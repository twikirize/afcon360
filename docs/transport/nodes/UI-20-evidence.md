# UI-20: CSP / CONSOLE TECHNICAL HYGIENE — EVIDENCE

## STATUS: PASS — panel-confirmed, node CLOSED

> **Gate history (read in order, not overwritten):**
> 1. Agent submission: `IMPLEMENTATION PASS / EVIDENCE GATE HOLD`
> 2. Panel review (DeepSeek + human): **PASS** — "no implementation defect, no
>    evidence defect, no UI-LOC-0B overlap, and no migration impact."
> 3. Human declared UI-20 **formally CLOSED**, 2026-10-05.
>
> The agent did not and cannot set the gate; the panel did. This header now
> records the panel's decision, it does not replace the agent's original claim.

NODE: UI-20
PARALLEL WORKSTREAM IN FLIGHT: UI-LOC-0B (concurrent agent)
UPSTREAM: UI-LOC-02A (formally CLOSED / PASS)
BRANCH: main
DATE: 2026-10-05
RUNTIME USED FOR PROOF: `http://127.0.0.1:5599` (throwaway probe server, `create_app(TestingConfig)`, TEST database only)

---

## 1. SCOPE AND GUARANTEE

**Guarantee in one sentence:** the Content-Security-Policy the application
actually delivers is correct, enforced, and now *guarded by automated tests*,
and the browser-console noise on the inspected surfaces is classified into real
CSP defects versus by-design migration signal versus unrelated noise.

UI-20 owns technical CSP / browser-console hygiene only. It did not touch
pickup/destination UX, GPS, map targeting or interaction state, location labels,
chips, disabled rider controls, booking UX, search/autocomplete, Photon /
provider code, canonical location architecture, routing, fare logic, matching,
tracking, wallet, or migrations.

**Node contract:** no `docs/transport/nodes/UI-20-contract.md` exists in the
repository. This node was executed against the human's written UI-20 directive
as the task contract. Recorded here so the panel can decide whether a formal
`-contract.md` should be back-filled. **Not verified:** that the directive is
formally registered as the node contract.

---

## 2. UNDERSTAND — where CSP actually comes from

There is no Flask-Talisman / Flask-CSP extension. CSP is assembled by hand in a
single place.

| Concern | Location | Lines |
|---------|----------|-------|
| Enforcement + report-only policy assembly | `app/__init__.py::create_app.after_request_pipeline` | 455–510 |
| `upgrade-insecure-requests` gate | `app/__init__.py::should_upgrade_insecure` | 129–138 |
| Nonce generation | `app/__init__.py::set_csp_nonce` (`@app.before_request`) | 2083–2088 |
| Nonce injection into templates | `app/__init__.py::inject_csp_nonce` (`@app.context_processor`) | 2090–2098 |
| Violation collector | `app/__init__.py::csp_report` (`POST /csp-report`) | 2100–2111 |
| Stated policy documentation | `app/Documentation/CSP_POLICY.md` | (pre-existing, drifted) |

`g.csp_nonce = secrets.token_urlsafe(16)` per request; exposed to Jinja as
`{{ csp_nonce }}`.

---

## 3. THE EXACT POLICY DELIVERED (browser-proven + runtime-proven)

Captured from a live response to `GET http://127.0.0.1:5599/login`:

```text
default-src 'self';
script-src 'self' 'nonce-unVshbNZdVGjTCGUV1yaUQ' https://cdn.jsdelivr.net;
style-src  'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://use.fontawesome.com;
img-src    'self' data: https:;
font-src   'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com https://use.fontawesome.com https://cdn.jsdelivr.net;
connect-src 'self' https://cdn.jsdelivr.net;
object-src 'none';
frame-ancestors 'none';
form-action 'self';
base-uri 'self';
```

Report-only (same, except `style-src` drops `'unsafe-inline'`, plus
`report-to csp-endpoint; report-uri /csp-report`).

Verified properties:

- Enforcement header **present and non-empty** (519 chars). CSP-ENFORCEMENT-01
  (empty enforcement header) is confirmed resolved.
- `unsafe-inline` **absent from `script-src`** — no script weakening.
- Nonce **unique per request**: 4 requests → 4 distinct nonces
  (`rst55IKOewGKru8c9zJjig`, `hSdIjygdzRhwvIWTnmZ9Pg`, `3s8G1s7IwqIYFMKhho5LEw`, `pKF3uIw2UfpDFjMBOxfjFA`).
- Nonce in header **equals** nonce rendered into the body (`GET /` →
  `hSdIjygdzRhwvIWTnmZ9Pg` present as `nonce=` in the HTML).
- `upgrade-insecure-requests` **absent** (SystemConfig `CSP_UPGRADE_INSECURE`
  not `'true'`; the lookup fails closed to `False`) — and consistent between
  the two policies.
- Companion headers present: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy: geolocation=(self), microphone=(), camera=(), payment=()`,
  `Cross-Origin-Opener-Policy: same-origin`,
  `Cross-Origin-Resource-Policy: same-origin`,
  `X-Permitted-Cross-Domain-Policies: none`.

---

## 4. TRACE — the mechanism behind every reported violation

This is the load-bearing part of the node. The initial source hypothesis was
wrong and was corrected by browser experiment.

**Hypothesis (rejected):** "a nonce present in `script-src` causes host sources
to be ignored, therefore every `<script>` lacking a `nonce` attribute is
blocked."

**Experiment (Chrome, live enforced policy):**

1. `GET /` — `static/js/feed/feed.js` has **no** `nonce` attribute, yet it
   loaded and executed with **no** CSP violation. `window.bootstrap` is an
   object and `theme-manager.js` ran (`body.class=light-mode`) on `/login`,
   where neither script carries a nonce.
2. `GET /login` — the inline `<script>` at `:483` has **no** `nonce` and **was
   blocked**.
3. Inline-handler probe on a live page: an element given
   `setAttribute('onclick', ...)` did **not** fire; the same logic bound with
   `addEventListener` **did** fire.

**Corrected, browser-proven enforcement semantics:**

| # | Construct | Result |
|---|-----------|--------|
| R1 | External `<script src>` from an allowed origin, no `nonce` | **ALLOWED**, executes |
| R2 | Inline `<script>` with no `src` and no `nonce` | **BLOCKED** |
| R3 | Inline event-handler attribute (`onclick=`, …) | **BLOCKED**, always |

R1 is the correction that matters for triage: a non-nonced *external* script is
a consistency defect, **not** an enforced-policy violation. R2 and R3 are the
enforced-violation classes.

### Console classification (required by the brief)

| Observation | Class | Verdict |
|---|---|---|
| `Executing inline script violates ... 'script-src ...'` (ERROR, blocked) | **CSP violation** | Real defect — R2 |
| `Applying inline style violates ... 'style-src ...' ... report-only` (INFO) | **By-design migration signal** | Not a defect. Report-only `style-src` intentionally omits `'unsafe-inline'` |
| `Failed to load resource: 404 (favicon.ico)` | **Third-party/asset noise** | Not CSP. `static/favicon.ico` does not exist and no route serves it |
| `[DOM] Input elements should have autocomplete attributes` (VERBOSE) | **Browser authoring hint** | Not a defect |
| `[LOG] Theme Manager initialized with manual save mode` | **Application log** | Not a defect |

---

## 5. PROVE — findings

### F1 — R2 dead JavaScript, browser-proven on three surfaces

| Page | Blocked inline scripts | Source |
|------|-----------------------|--------|
| `/login` | 1 (`:483`) | `templates/login.html:503` |
| `/register` | 2 (`:297`, `:336`) | `templates/register.html:110,149` |
| `/events/` | 1 (`:968`) | events hub template |

Console evidence, `/login`:

```text
[ERROR] Executing inline script violates the following Content Security Policy
directive 'script-src 'self' 'nonce-FzcHcJDlbzq9Gs5UANzCmQ' https://cdn.jsdelivr.net'.
Either the 'unsafe-inline' keyword, a hash ('sha256-DMolmxA0+LomqYaFx5viFfjS41t3D2kZ78lEbmzC710='),
or a nonce ('nonce-...') is required to enable inline execution. The action has been blocked.
@ http://127.0.0.1:5599/login:483
```

Source-scan ↔ runtime correlation is exact: the two inline scripts counted in
`templates/register.html` are the two blocked at runtime.

### F2 — concrete user-facing consequence, browser-proven

`templates/login.html` renders a password-visibility toggle button
(`#togglePassword`, added by a concurrent auth workstream). Its handler lives
in the R2-blocked inline script, so the control is visible and clickable and
does nothing:

```json
{ "typeBeforeClick": "password", "typeAfterClick": "password",
  "toggleWorks": false,
  "verdict": "toggle handler DEAD -> inline script was CSP-blocked" }
```

**Not fixed by UI-20** — `templates/login.html` is already dirty from a
concurrent agent's auth workstream (see §7).

### F3 — R3 dead controls in the shared shells (mechanism browser-proven, presence source-proven)

| File | Line | Handler |
|------|------|---------|
| `templates/base.html` | 127 | `onclick="showImpersonationRestrictions()"` |
| `templates/base.html` | 334, 335, 342, 348, 634, 635, 639, 642 | `onclick="event.preventDefault(); flash(...)"` module-disabled guards |
| `templates/transport/base.html` | 120 | `onclick="toggleSidebar()"` |
| `templates/transport/base.html` | 166 | `onclick="this.parentElement.remove()"` |
| `templates/transport/driver/base.html` | 177 | `onclick="this.parentElement.remove()"` |
| `templates/transport/driver/driver_dashboard.html` | 1382 | `onclick="this.parentElement.remove()"` |

Behavioural consequence worth flagging to the panel: the module-disabled guards
rely on `event.preventDefault()`. Under a blocked handler that call never runs,
so a "disabled" module link **navigates instead of warning**. This interacts
with `AGENTS.md §28` module-toggle behaviour, which is explicitly outside
UI-20 scope.

**Honest scoping of this finding:** the R3 *mechanism* is browser-proven (synthetic
probe). Per-page runtime capture was **not** obtained for these specific
elements because they sit behind authentication. The four shell templates are
all already dirty from other workstreams, so UI-20 did not edit them.

### F4 — systemic R2/R3 debt (source-proven lower bound, NOT fixed)

Static scan of 609 templates under `templates/**` (HTML comments stripped):

| Class | Count | Files affected |
|-------|-------|----------------|
| R2 inline `<script>` without nonce | 158 | 152 |
| R3 inline event-handler attributes | 665 | 154 |
| R1 external `<script>` without nonce (hygiene only) | 94 | 62 |
| Inline `<script>` correctly nonced | 26 | — |

**The R3 figure is a lower bound and is disclosed as such.** The scanner cannot
see handlers emitted inside Jinja conditionals that span tag boundaries;
`templates/base.html` actually carries **9** handlers while the scan reports 1.
Under-counting is in the safe direction for a "do not touch" decision, and is
recorded so no future agent treats 665 as exact.

Worst R2 files (all outside UI-20 ownership): `templates/events/attendee/registerO.html` (3),
`templates/owner/settings.html` (2), `templates/super_admin_dashboard.html` (2),
`templates/transport/dashboard/base_dashboard.html` (2), `templates/register.html` (2).

**UI-20 does not fix this.** It spans rider, admin, owner, wallet, events and
accommodation templates; it needs its own contract, per-domain ownership and
per-page browser re-proof. Remediating it inside UI-20 would be exactly the
"broad refactor" the brief forbids.

### F5 — zero automated coverage of the policy (the real hygiene debt, FIXED)

Before UI-20, `grep -r "Content-Security-Policy" tests/` returned **nothing**,
and `grep` for `X-Frame-Options|Permissions-Policy|Strict-Transport|security_header`
across the whole test tree matched **no file at all**. The CSP-ENFORCEMENT-01
regression shipped, was found by hand in a browser, was fixed — and shipped
again with nothing to hold it.

### F6 — documentation drift (source-proven, FIXED)

`app/Documentation/CSP_POLICY.md` did not describe the delivered policy:

| Documented | Actually delivered |
|---|---|
| `script-src 'self' 'nonce-…'` | `+ https://cdn.jsdelivr.net` |
| `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com` | `+ jsdelivr, cdnjs.cloudflare.com, use.fontawesome.com` |
| `font-src 'self' https://fonts.gstatic.com` | `+ cdnjs, fontawesome, jsdelivr` |
| `connect-src 'self'` | `+ https://cdn.jsdelivr.net` |
| `upgrade-insecure-requests;` (unconditional) | conditional on `SystemConfig.CSP_UPGRADE_INSECURE` |

Plus a **stale function reference** (Operating System §6, stale legacy state):
line 133 named `app/__init__.py::apply_security_headers` as the policy owner.
Verified that function **does not exist**; the real owner is
`after_request_pipeline`.

---

## 6. MINIMAL CHANGE — what UI-20 changed

Exactly **two files**. No runtime code was touched.

| File | Change | Runtime impact |
|------|--------|----------------|
| `tests/test_ui_20_csp.py` | **NEW** — 45 test cases guarding the delivered policy | none |
| `app/Documentation/CSP_POLICY.md` | `+106 −22` — reconciled to the delivered policy; added enforcement-semantics, automated-enforcement and known-debt sections; corrected the stale function reference | none |

`app/Documentation/CSP_POLICY.md` was **clean** in `git status` before UI-20
touched it; `tests/test_ui_20_csp.py` is new. No already-dirty file was
modified by this node.

### What the tests assert

Header integrity: present, non-empty, no interior empty directive, real
baseline directives (`object-src 'none'`, `frame-ancestors 'none'`,
`base-uri 'self'`, `form-action 'self'`).

Script hardening: no `'unsafe-inline'`, no `'unsafe-eval'`, no
`'unsafe-hashes'` in `script-src`; a nonce path is always offered.

Nonce: non-trivial, unique across 5 consecutive requests, and **identical in
the header and the rendered body** — the propagation invariant between the
`before_request` generator and the `context_processor` injector. Divergence
there silently blocks every inline script while the header still looks correct.

Report-only: present, **strictly stricter than enforcement on `style-src`**,
and its reporting directives agree with `Report-To` / `Reporting-Endpoints`.

Allowlist: `EXPECTED_ALLOWLIST` asserts the third-party origin set exactly —
silent supply-chain allowlist growth now fails the build.

Conditional directive: `upgrade-insecure-requests` consistent across both
policies and, when present, the final directive.

Collector: `POST /csp-report` returns `204` and does not raise — the only
server-side place violations are recorded.

Companion headers: `nosniff`, `DENY`, referrer policy, `geolocation=(self)`
in `Permissions-Policy`, COOP, CORP, `X-Permitted-Cross-Domain-Policies`.

Plus one `xfail` tripwire for `templates/base.html`'s inline handlers so the
known debt stays visible in test output instead of being forgotten.

### Guard non-vacuity — mutation proof

A throwaway harness ran the tests' own detector logic against six known-bad
policies. **No repository source was modified.**

```text
REJECTED  CSP-ENFORCEMENT-01 historical: header == ''
REJECTED  script-src weakened with 'unsafe-inline'
REJECTED  script-src weakened with 'unsafe-hashes' (re-enables inline handlers)
REJECTED  interior empty directive segment
REJECTED  script-src with no nonce path at all
REJECTED  silent third-party allowlist growth (evil.example)
guards effective: 6/6      EXIT=0
```

### One test corrected during authoring

The first draft asserted the enforced policy has *no* empty `;` segment, which
failed on the trailing `base-uri 'self'; `. That assertion was **wrong, not the
code**: CSP parsing skips empty directives, so a single trailing separator is
valid. Corrected to reject *interior* empty segments (the actual malformation
class) and to allow at most one trailing separator, recorded as a cosmetic
finding. Recorded here because "the test was wrong" and "the code was wrong"
must not be conflated.

---

## 7. OWNERSHIP AND 0B OVERLAP ASSESSMENT

### `templates/transport/new_home.html` — the file the brief flagged

**UI-20 did not modify it, and does not need to.** Verified read-only:

```text
script tags: 3
   nonce=True  src=https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js
   nonce=True  src={{ url_for('static', filename='js/geo/geo-map.js') }}
   nonce=True  src=(inline)
inline handler attrs: none
```

3/3 scripts nonced, **zero** inline handlers. The file is **already CSP-clean**.
There is no UI-20 defect to fix in it, so the overlap question never arises. A
future agent should not "fix" CSP here.

**Independent proof that 0B is live:** `git diff HEAD --stat` for that file read
`19 +-` at the start of this session and `37 ++++++` (30 insertions, 7 deletions)
at the end, with no edit from this node. UI-LOC-0B is actively writing to it now.

### 0B OVERLAP: **none**

UI-20's two files (`tests/test_ui_20_csp.py`, `app/Documentation/CSP_POLICY.md`)
are disjoint from every file in the dirty set and from UI-LOC-0B's scope
(pickup/destination UX, GPS, map targeting, chips, disabled rider controls).
**No conflict was created.**

### Deliberate non-touch of concurrently-dirty files

Findings F2 and F3 name files that are already dirty from other workstreams.
Per the brief's worktree-safety rule, existing changes belonging to another
workstream must not be disturbed:

| File | Dirty from | Why UI-20 left it |
|------|-----------|-------------------|
| `templates/login.html` | concurrent auth workstream (dark-mode CSS, password toggle) | F2 fix is 3 nonced tags, but the file is live-edited |
| `templates/base.html` | CSP-ENFORCEMENT-01 nonce additions | shared shell, repo-wide blast radius; module-toggle behaviour is §28, out of scope |
| `templates/transport/base.html` | other workstream | same |
| `templates/transport/driver/base.html` | CSP-ENFORCEMENT-01 | same |
| `templates/transport/driver/driver_dashboard.html` | CSP-ENFORCEMENT-01 | same |
| `BACKLOG.md` | other workstream | §11 debt recorded in this evidence file instead; see §11 |

---

## 8. VERIFICATION

```text
$ .venv\Scripts\python.exe -m pytest tests/test_ui_20_csp.py -q
44 passed, 1 xfailed, 4 warnings in 67.83s        EXIT=0

$ .venv\Scripts\python.exe -m pytest tests/test_ui_20_csp.py \
      tests/test_geo_map_renderer.py \
      tests/test_accommodation_checkout_processes.py -q
63 passed, 1 xfailed, 4 warnings in 109.09s       EXIT=0
```

The two adjacent suites were chosen because they are the only pre-existing
tests that assert nonce usage
(`tests/test_geo_map_renderer.py:137`, `tests/test_accommodation_checkout_processes.py:73`);
both still pass, so the new file and the doc change disturbed nothing.

Mutation proof: `guards effective: 6/6`, EXIT=0 (see §6).

No lint/typecheck command is configured for this project (§37: only
`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`).

---

## 9. BROWSER EVIDENCE

Environment: Playwright/Chromium against `http://127.0.0.1:5599`, served by
`create_app(TestingConfig)` on the **test** database. No production data.

| # | Probe | Result |
|---|-------|--------|
| B1 | Response headers on `/login` | Enforcement policy exactly as in §3; nonce present |
| B2 | Nonce uniqueness, 4 requests | 4 distinct nonces |
| B3 | Header nonce vs body nonce on `/` | Match |
| B4 | `/login` console | 1 CSP **ERROR** (inline script blocked); 2 report-only style INFOs; theme-manager LOG |
| B5 | `/login` runtime effect | `window.bootstrap` is object; `body.class=light-mode` → external non-nonced scripts **did** run (R1) |
| B6 | `/login` password toggle | `type` unchanged after click → handler dead (R2 consequence) |
| B7 | `/register` console | 2 CSP **ERROR**s blocked at `:297`, `:336` |
| B8 | `/events/` console | 1 CSP **ERROR** blocked at `:968`; rendered inline handlers: 0 |
| B9 | Inline-handler probe | `onclick` did **not** fire; `addEventListener` did → R3 |
| B10 | Nonce-attribute detection method | `getAttribute('nonce')` is unreliable (browsers hide the content attribute); `HTMLScriptElement.nonce` is correct. First-pass scan using `getAttribute` produced a **false positive** and was discarded |
| B11 | Post-change re-probe of `/login` | Identical: same blocked inline script, same `sha256-DMolmxA0+LomqYaFx5viFfjS41t3D2kZ78lEbmzC710=` hash, toggle still dead, external scripts still run → UI-20 changed no runtime behaviour |

Console logs retained under `.playwright-mcp/`.

### NOT VERIFIED

- No per-page runtime capture of the F3 shell handlers (authentication required).
- No HTTPS run: `Strict-Transport-Security` is only set when
  `request.is_secure`, so HSTS was **not** exercised. The UI-20 test asserts the
  other hardening headers only.
- No `upgrade-insecure-requests == true` run (SystemConfig not set to
  `'true'`); the conditional-consistency test proved agreement on the `false`
  branch only.
- The R3 count of 665 is a **lower bound** (see F4).
- Other domains' pages (admin, owner, wallet, events, accommodation) were
  scanned at source level but **not** loaded in a browser.
- Production/CSP-report log volume was not inspected; no report-only data from
  real traffic was available.

---

## 10. MIGRATION STATUS

**NO MIGRATION.** No `flask db migrate` / `upgrade` / `downgrade` / `merge` was
executed. No schema change. No migration file created, edited or repaired. No
model touched.

---

## 11. RESIDUAL RISKS AND HANDOFF

### Not fixed, deliberately (each needs its own node)

1. **F4 — R2/R3 systemic debt.** 158 R2 inline scripts across 152 templates;
   665+ R3 handlers across 154+ templates. Multi-workstream migration.
2. **F2 — `/login` password toggle is dead.** 3-line fix (add
   `nonce="{{ csp_nonce }}"` to `templates/login.html:501,502,503`), but the
   file is live-edited by another agent. **Highest-value quick win available;
   hand it to the auth workstream that owns the file.**
3. **F3 — shared-shell handlers**, incl. the module-disabled
   `event.preventDefault()` guards that now navigate instead of warning.
4. **Cosmetic:** the enforced policy ends `base-uri 'self'; ` with one trailing
   separator when `upgrade_directive` is empty. Harmless; guarded by
   `test_enforced_policy_trailing_separator_is_at_most_one`.

### Console noise not fixed

5. `static/favicon.ico` does not exist and no route serves it → a 404 on every
   page load. Needs an asset/branding decision, so out of scope for a CSP node.

### §11 BACKLOG DEFERRED WORK — DRAFTED, NOT WRITTEN

`BACKLOG.md` is dirty from a concurrent workstream and a concurrent agent
appending to its tail risks a collision. Per §11 the work is recorded here
rather than silently dropped; **the panel should transcribe it into
`BACKLOG.md`**:

> **CSP-R2-R3-MIGRATION** — 158 inline `<script>` blocks without
> `nonce="{{ csp_nonce }}"` across 152 templates and 665+ inline event-handler
> attributes across 154+ templates are blocked by the enforced policy; each is
> dead page functionality. Browser-proven mechanism: R1 external scripts load
> regardless of nonce, R2 inline scripts need the nonce, R3 inline handlers are
> always blocked. Highest leverage: `templates/base.html` (9 handlers, every
> page inherits it) and `templates/transport/base.html`. Needs per-domain
> ownership, a contract, and per-page browser re-proof. Nonce-propagation and
> header-integrity are already guarded by `tests/test_ui_20_csp.py`.

---

## 12. FILES CHANGED

```text
 M app/Documentation/CSP_POLICY.md   (+106  -22)
?? tests/test_ui_20_csp.py           (new, 45 test cases)
?? docs/transport/nodes/UI-20-evidence.md   (new, this file)
```

No commit. The register was not touched.

---

## 13. IMPLEMENTATION RESULT

**CSP policy correctness: proven and now guarded.** The delivered policy is
enforced, non-empty, unweakened in `script-src`, nonce-fresh and
nonce-propagated, allowlist-pinned, with report-only correctly staged stricter.
Before UI-20 this had **zero** automated coverage; it now has 45 cases plus a
6/6 mutation proof that the guards are not vacuous.

**Console hygiene: classified, not eliminated.** The real defect is systemic
(158 R2 / 665+ R3 across ~150 templates) and is recorded for a dedicated
migration rather than half-fixed here. Two browser-proven defects with concrete
user impact (`/login` dead password toggle; shell module-guard handlers that
navigate instead of warning) are documented with exact fixes but deliberately
left in files owned by other agents.

## PANEL GATE: PASS — CLOSED

Submitted by the agent as `IMPLEMENTATION PASS / EVIDENCE GATE HOLD`.

Panel (DeepSeek + human) returned **PASS** on 2026-10-05: no implementation
defect, no evidence defect, no UI-LOC-0B overlap, no migration impact. The human
then declared the node **formally CLOSED**.

The gate was never the agent's to set, and was not set by the agent.

## RESIDUAL CSP DEBT — HANDED OVER, NOT MERGED ANYWHERE

The panel directed that the following remain a **separate future workstream**
and must not be folded into UI-LOC-0B or any other active node:

```text
CSP-R2-R3-MIGRATION
  158 R2 inline scripts            (inline <script> with no nonce -> BLOCKED)
  665+ R3 handlers                 (inline event-handler attrs -> BLOCKED; lower bound)
  /login toggle                    (password visibility, browser-proven dead)
  shared-shell handlers            (incl. module-guard preventDefault that navigates)
  favicon 404                      (no asset, no route)
```

Its BACKLOG.md transcription was **initially deferred by human decision** until
that file was quiet. `BACKLOG.md` was still dirty from a concurrent agent at
UI-20 close, so recording it then would have interrupted an active edit for a
bookkeeping entry; the drafted text was preserved verbatim in §11 of this file.

The human subsequently **overrode that deferral**: `BACKLOG.md` is the single
official backlog of record, so an unrecorded item is an effectively lost item. The
entry was appended on 2026-10-05 as `CSP-R2-R3-MIGRATION` (46 lines,
`BACKLOG.md:3562`, last entry in the file). Verified by
`git diff HEAD --numstat -- BACKLOG.md` → `80 0`, i.e. **zero deletions**, the
concurrent agent's separate 34-line entry intact; append-only via
`File.AppendAllText` on the 614 KB file; BOM-less UTF-8 preserved; 0 replacement
characters inside the appended text.

Open backlog item now: none from this node.

## NEXT

STOP. UI-20 is closed. UI-LOC-0B remains ACTIVE and was not touched. UI-LOC-0C
and Node 1+ remain HOLD. No further node was started.