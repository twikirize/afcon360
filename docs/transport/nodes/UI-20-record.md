# UI-20 — Record

Status:          PASS (panel-confirmed, node CLOSED)
Commit:          none — see "Commit status" below
Date:            2026-10-05
Owner:           agent (implementation + evidence + record); human (gate + register)
Node class:      BEHAVIORAL (security-header behaviour + browser-console hygiene)
Gate history:    agent submitted `IMPLEMENTATION PASS / EVIDENCE GATE HOLD`
                 → panel (DeepSeek + human) returned PASS
                 → human declared the node formally CLOSED

---

## Guarantee delivered

The Content-Security-Policy the application actually serves is correct, is
enforced, and is now guarded by automated tests; and the browser-console noise
on the inspected surfaces is classified into genuine CSP defects versus
by-design migration signal versus unrelated noise.

## Files changed

```text
 M app/Documentation/CSP_POLICY.md              (+106  -22)
?? tests/test_ui_20_csp.py                      (new, 45 test cases)
?? docs/transport/nodes/UI-20-evidence.md       (new)
?? docs/transport/nodes/UI-20-record.md         (new, this file)
 M BACKLOG.md                                   (+46  -0, appended CSP-R2-R3-MIGRATION)
```

No runtime code was modified. No template was modified. No model, schema or
migration was touched. `BACKLOG.md` was appended to, never rewritten.

## What changed

1. **`tests/test_ui_20_csp.py` (new).** Before this node the CSP response
   header had **zero** automated coverage — `grep -r "Content-Security-Policy"
   tests/` matched nothing, and a search for `X-Frame-Options`,
   `Permissions-Policy`, `Strict-Transport` or `security_header` across the whole
   test tree matched no file at all. The CSP-ENFORCEMENT-01 regression shipped,
   was found by hand in a browser, was fixed, and shipped again with nothing to
   hold it. 45 cases now assert: header present / non-empty / no malformed
   directives; `script-src` free of `'unsafe-inline'`, `'unsafe-eval'` and
   `'unsafe-hashes'`; a nonce path is always offered; nonce non-trivial, unique
   per request, and identical in the header and the rendered body;
   report-only strictly stricter than enforcement on `style-src`; reporting
   directives agreeing with `Report-To` / `Reporting-Endpoints`; the baseline
   hardening directives and companion headers; the third-party origin allowlist
   pinned exactly; `upgrade-insecure-requests` conditional and consistent across
   both policies; `POST /csp-report` accepting reports. One `xfail` tripwire
   keeps the known `templates/base.html` handler debt visible in test output.

2. **`app/Documentation/CSP_POLICY.md` (+106 −22).** Reconciled to the policy
   actually delivered. The prior revision had drifted on five directives
   (missing `cdn.jsdelivr.net` / `cdnjs.cloudflare.com` /
   `use.fontawesome.com`, missing the `connect-src` entry, unconditional
   `upgrade-insecure-requests`) and pointed change control at
   `app/__init__.py::apply_security_headers`, a function verified not to exist
   (Operating System §6, stale legacy state; real owner is
   `after_request_pipeline`). Added the browser-verified enforcement-semantics
   table, an automated-enforcement section, and a measured known-debt section.

## Evidence

See `docs/transport/nodes/UI-20-evidence.md` — source-proven, browser-proven and
not-verified claims are kept separate throughout.

## Runtime verification

```text
.venv\Scripts\python.exe -m pytest tests/test_ui_20_csp.py -q
    44 passed, 1 xfailed                                       EXIT=0

+ tests/test_geo_map_renderer.py
+ tests/test_accommodation_checkout_processes.py
    63 passed, 1 xfailed                                       EXIT=0

Mutation proof (guards proven non-vacuous, no repo source modified):
    6/6 known-bad policies rejected                             EXIT=0
```

Browser (Playwright/Chromium vs a throwaway `create_app(TestingConfig)` server on
the **test** database, stopped after proof):

- enforcement header captured verbatim; nonce unique across 4 requests; header
  nonce matches the nonce rendered into the body;
- **R2 blocked** on `/login` (×1), `/register` (×2), `/events/` (×1) — counts
  match the source scan exactly;
- **R1 confirmed**: external scripts from allowed origins load and execute with
  no nonce attribute (`window.bootstrap` is an object; `theme-manager.js` ran);
- **R3 confirmed**: an element given `setAttribute('onclick', …)` did not fire,
  while the same logic bound via `addEventListener` did;
- `/login` password-visibility toggle proven dead (input `type` unchanged after
  a click) — its handler lives in the R2-blocked inline script;
- post-change re-probe byte-identical (same `sha256-DMolmxA0+LomqYaFx5viFfjS41t3D2kZ78lEbmzC710=`
  inline-script hash) → UI-20 altered no runtime behaviour.

## Two corrections made during the node

Recorded because "the hypothesis was wrong" must not be presented as "the code
was right":

1. **Source hypothesis overturned by experiment.** The initial reading — that a
   nonce in `script-src` causes host sources to be ignored, making all 252
   non-nonced `<script>` tags blocked — was wrong. Browser evidence showed
   external scripts execute regardless of the nonce (R1), narrowing the real
   enforced-violation classes to inline scripts (R2) and inline handlers (R3).
   This changed the remediation priority and prevented a pointless 94-file
   "fix".
2. **First-pass scan discarded.** It read the nonce via
   `getAttribute('nonce')`, which browsers deliberately blank to prevent
   exfiltration. That produced a false positive. `HTMLScriptElement.nonce` is
   the correct API; the scan was redone.

One test was also corrected mid-authoring: the initial assertion that the policy
contains no empty `;` segment failed on the trailing `base-uri 'self'; `. The
**test** was wrong, not the code — CSP parsing skips empty directives — so it was
narrowed to reject interior empty segments only.

## Residual risk

The policy itself is sound and now guarded, but the *template layer* still
carries systemic, browser-proven dead JavaScript that UI-20 deliberately did not
fix: 158 inline `<script>` blocks without a nonce across 152 templates, and 665+
inline event-handler attributes across 154+ templates (a disclosed lower bound —
the scanner cannot see handlers inside Jinja conditionals spanning tag
boundaries; `templates/base.html` alone really carries 9 while the scan reports
1). Each occurrence is dead page functionality, not merely untidy markup. The
sharpest instances are the `/login` password toggle and the shared-shell
module-disabled guards whose `event.preventDefault()` never runs, so a
"disabled" module link navigates instead of warning — which touches
AGENTS.md §28 module-toggle behaviour and was therefore out of scope. This debt
is systemic across five domains and needs its own contract, per-domain
ownership and per-page browser re-proof; remediating it inside UI-20 would have
been the broad refactor the node forbids. Separately, `static/favicon.ico` does
not exist and no route serves it, so every page load logs a 404.

## Follow-ups

Carried as a single future workstream, `CSP-R2-R3-MIGRATION`, and explicitly
**not** to be merged into UI-LOC-0B or any other active node:

1. 158 R2 inline scripts across 152 templates.
2. 665+ R3 inline handlers across 154+ templates (lower bound).
3. `/login` password-visibility toggle (3-line fix; hand to the agent that owns
   `templates/login.html`, which was live-edited during this node).
4. Shared-shell handlers, including the module-guard `preventDefault` defect.
5. `favicon.ico` 404 — needs an asset/branding decision, so it was never a
   plausible CSP-node fix.

Its `BACKLOG.md` transcription was **initially deferred by human decision**,
because that file was dirty from a concurrent agent at UI-20 close and recording
it then would have interrupted an active edit for a bookkeeping entry. The human
subsequently overrode that deferral — `BACKLOG.md` is the one official backlog of
record and an untracked item is effectively a lost item. The entry was therefore
**appended on 2026-10-05** as `CSP-R2-R3-MIGRATION` (46 lines, `BACKLOG.md`
line 3562, the last entry in the file), matching the file's existing house format.

Transcription was verified, not assumed: `git diff HEAD --numstat -- BACKLOG.md`
reports `80 0` — **zero deletions**, so no pre-existing line was destroyed; the
concurrent agent's own 34-line entry is still intact; the file remains BOM-less
UTF-8 with an LF terminator; and a byte-level scan found 0 U+FFFD replacement
characters inside the appended text (the 25 present in the file are pre-existing
mojibake from an earlier session, not introduced here). The append was done with
`File.AppendAllText`, so a 614 KB file was never rewritten in full.

Also outstanding, for the record: no `docs/transport/nodes/UI-20-contract.md`
exists. The human's UI-20 directive was treated as the task contract. The panel
may wish to back-fill a formal contract.

## Ownership / concurrency statement

UI-20 owned exactly three files: `tests/test_ui_20_csp.py`,
`app/Documentation/CSP_POLICY.md` (clean before this node touched it), and its
own two node documents. `templates/transport/new_home.html` was **not** modified
and needs no change — it is already CSP-clean (3/3 scripts nonced, 0 inline
handlers). That UI-LOC-0B was actively writing to it during this session was
independently confirmed by its diffstat growing from 19 to 37 changed lines with
no edit from this node. No conflict was created with any concurrent workstream.

## Commit status

No commit was made. The working tree is intentionally shared across concurrent
agents, no commit was requested, and the panel did not ask for one. When the
human chooses to commit, the intended content is only:

```text
app/Documentation/CSP_POLICY.md
tests/test_ui_20_csp.py
docs/transport/nodes/UI-20-evidence.md
docs/transport/nodes/UI-20-record.md
BACKLOG.md   (append-only: the CSP-R2-R3-MIGRATION entry — stage with
              `git add -p` or a hunks-limited add, because a concurrent
              agent's separate entry lives in the same file)
```

Every other dirty file in the tree belongs to another workstream and must be
staged separately by its owner. No `git stash`, `git reset --hard`, `git clean`
or destructive checkout was used at any point in this node.

## Gate reference

Panel review of 2026-10-05 (DeepSeek + human): PASS.
Node declared CLOSED by the human. Register updated by the human — this node
wrote no register row.