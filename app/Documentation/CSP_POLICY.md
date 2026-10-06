### AFCON360 Web App - Content Security Policy (CSP)

This document describes the CSP we enforce, how nonces are generated and applied, how to monitor violations, and how developers should add scripts and styles going forward.

> Reconciled 2026-10-05 by node UI-20 against the policy actually delivered by
> `app/__init__.py::after_request_pipeline`. The previous revision of this file
> documented a policy the application no longer serves (missing
> `cdn.jsdelivr.net` / `cdnjs.cloudflare.com` / `use.fontawesome.com`, missing
> `connect-src` entry, unconditional `upgrade-insecure-requests`) and pointed
> change control at `apply_security_headers`, a function that does not exist.
> The allowlist below is now drift-guarded by `tests/test_ui_20_csp.py`.

#### Goals
- Prevent inline-script execution (XSS mitigation) using a per-request nonce.
- Minimize allowed origins (default to 'self').
- Provide a safe migration path away from inline styles.
- Capture violations via a reporting endpoint for early detection.

---

### Current runtime policy (enforced)

The app sets the `Content-Security-Policy` header in `app/__init__.py`:

```
default-src 'self';
script-src 'self' 'nonce-<per-request-nonce>' https://cdn.jsdelivr.net;
style-src  'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://use.fontawesome.com;
img-src    'self' data: https:;
font-src   'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com https://use.fontawesome.com https://cdn.jsdelivr.net;
connect-src 'self' https://cdn.jsdelivr.net;
object-src 'none';
frame-ancestors 'none';
form-action 'self';
base-uri 'self';
upgrade-insecure-requests;   <-- only when SystemConfig.CSP_UPGRADE_INSECURE == 'true'
```

Key points:
- Scripts: `'self'` and `cdn.jsdelivr.net` are allowed as origins, and the per-request nonce is offered as an additional path. **Inline scripts and inline event handlers are blocked.** See "Enforcement semantics" below for exactly what the nonce does and does not do — this is the single most commonly misread part of this policy.
- Styles: inline styles still allowed temporarily, to avoid regressions while styles are being migrated to static CSS. Google Fonts, jsDelivr, cdnjs and Font Awesome stylesheets allowed.
- Images: self, data URIs and https to accommodate avatars/CDN images; can be tightened if desired.
- Fonts: Google Fonts, cdnjs, Font Awesome and jsDelivr hosts allowed; can be narrowed once fonts are self-hosted.
- `connect-src` allows jsDelivr so client-side library calls to the CDN are not broken.
- Mixed content: `upgrade-insecure-requests` is **conditional**, read per response from `SystemConfig.CSP_UPGRADE_INSECURE`. It is absent by default (the lookup fails closed to `False`). Both the enforced and report-only policies always make the same decision.

The app also returns modern hardening headers:
- `Strict-Transport-Security` (on HTTPS)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(self), microphone=(), camera=(), payment=()`
  - `geolocation=(self)`: same-origin pages may use the browser Geolocation API. Required by the Driver Workspace (`/transport/driver-dashboard`) so location pings can read device position.
  - `microphone=()`, `camera=()`, `payment=()`: explicitly denied for all origins (including same-origin). The Driver Workspace does not need them; enable individually only with an approved need.
- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Resource-Policy: same-origin`
- `X-Permitted-Cross-Domain-Policies: none`

---

### Monitoring policy (Report-Only)

To safely progress to a strict no-inline-styles posture, we set a parallel `Content-Security-Policy-Report-Only` header:

```
default-src 'self';
script-src 'self' 'nonce-<per-request-nonce>' https://cdn.jsdelivr.net;
style-src  'self' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://use.fontawesome.com;
img-src    'self' data: https:;
font-src   'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com https://use.fontawesome.com https://cdn.jsdelivr.net;
connect-src 'self' https://cdn.jsdelivr.net;
object-src 'none';
frame-ancestors 'none';
form-action 'self';
base-uri 'self';
upgrade-insecure-requests;   <-- conditional, same setting as the enforced policy
report-to csp-endpoint; report-uri /csp-report
```

Note the one deliberate difference from the enforced policy: report-only
`style-src` has **no** `'unsafe-inline'`. That is the whole point of the
header — it measures the inline-style debt that the enforced policy still
tolerates, without blocking anything.

This allows us to see violations (mostly inline `<style>` and style attributes) without breaking production.

Reporting integration:
- `Report-To` (and the legacy `Reporting-Endpoints`) headers point to `/csp-report`.
- The app exposes `POST /csp-report` which logs violation payloads (`current_app.logger.warning`) and returns `204`.

---

### Enforcement semantics (browser-verified 2026-10-05, node UI-20)

The enforced `script-src` is `'self' 'nonce-<n>' https://cdn.jsdelivr.net`.
Verified in Chrome against a live server serving this policy:

| # | Construct | Result | Consequence |
|---|-----------|--------|-------------|
| R1 | External `<script src>` from an allowed origin, **no** `nonce` attribute | **ALLOWED** and executes | Host sources stay effective alongside the nonce. A missing nonce on an external script is a *consistency* defect, not an enforced-policy violation. |
| R2 | Inline `<script>` with no `src`, **no** `nonce` attribute | **BLOCKED** | The page's inline JavaScript never runs. Its controls are silently dead. |
| R3 | Inline event-handler attribute (`onclick="..."`, `onerror="..."`, …) | **BLOCKED** always | `script-src` has no `'unsafe-inline'`, and hashes do not apply to handler attributes without `'unsafe-hashes'`. |

Consequences for triage:

- Do **not** spend remediation effort on R1. Adding `nonce="{{ csp_nonce }}"` to external scripts is still good hygiene and is what the shared shells already do, but it fixes nothing observable.
- R2 and R3 are the enforced-violation classes. Each occurrence is real dead functionality.
- A browser will also emit these, which are **not** defects and should not be "fixed":
  - *Report-only* `style-src` violations for `style="..."` attributes — this is the migration instrument working as designed.
  - `[DOM] Input elements should have autocomplete attributes` — a browser authoring hint.
  - `favicon.ico` 404 — a missing asset, not CSP.
- Remediation for R2 is `nonce="{{ csp_nonce }}"` on the inline `<script>` (acceptable for a small block), or preferably moving the code to a file under `static/js/`.
- Remediation for R3 is `addEventListener` from a nonced/external script. Note that `event.preventDefault()` inside a blocked handler never runs, so a "disabled" link that relies on an inline `onclick` to cancel navigation **will navigate**.

---

### Nonce generation and usage

- A per-request nonce is generated in `@app.before_request` (`set_csp_nonce`) and exposed to templates via a context processor (`inject_csp_nonce`) as `{{ csp_nonce }}`. These are two separate registrations; the header nonce and the rendered nonce must match or every inline script is blocked (see R2).
- Inline `<script>` blocks must carry `nonce="{{ csp_nonce }}"` (not recommended; prefer external files).
- Inline event handlers (e.g., `onclick="..."`) are never allowed — they cannot be nonced. Use `addEventListener` in external JS modules.
- External `<script src>` tags should also carry `nonce="{{ csp_nonce }}"` for consistency with the shared shells, but per R1 this is not what makes them load.

Example in a template:
```
<script nonce="{{ csp_nonce }}" src="{{ url_for('static', filename='js/admin_moderation.js') }}"></script>
```

---

### Automated enforcement

`tests/test_ui_20_csp.py` is the guard for this policy. It asserts, against the
real response pipeline:

- the enforcement header is present, non-empty, and parses to real directives (the CSP-ENFORCEMENT-01 regression guard);
- `script-src` contains no `'unsafe-inline'`, `'unsafe-eval'` or `'unsafe-hashes'`, and does offer a nonce path;
- the nonce is non-trivial, unique per request, and identical in the header and the rendered body;
- report-only stays stricter than enforcement on `style-src` (no `'unsafe-inline'`), and its reporting directives agree with the `Report-To` / `Reporting-Endpoints` headers;
- `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`, and the companion hardening headers;
- the third-party origin allowlist has not drifted (`EXPECTED_ALLOWLIST`);
- `upgrade-insecure-requests` is conditional and consistent across both policies;
- `POST /csp-report` still accepts reports.

**Changing the allowlist is a security decision.** Update `app/__init__.py`
*and* `EXPECTED_ALLOWLIST` in `tests/test_ui_20_csp.py` *and* this document in
the same node. Never one alone.

The suite also carries one `xfail` tripwire for
`templates/base.html`'s inline handlers, so the known debt stays visible in
test output instead of being forgotten.

---

### Known debt (measured 2026-10-05, node UI-20)

Static scan of `templates/**` against the R2/R3 rules:

| Class | Count | Files | Browser-verified |
|-------|-------|-------|------------------|
| R2 inline `<script>` without nonce | 158 | 152 | Yes — `/login` (1), `/register` (2), `/events/` (1) |
| R3 inline event-handler attributes | 665+ (**lower bound**) | 154+ | Mechanism yes; per-page no (auth-gated) |

The R3 figure is a **lower bound**: the scanner cannot see handlers emitted
inside Jinja conditionals that span tag boundaries, which is how
`templates/base.html` really carries 9 handlers while the scan reports 1.

This debt is **not** remediated by UI-20. It is a multi-workstream migration
spanning rider, admin, owner, wallet, events and accommodation templates; it
needs a contract, per-domain ownership, and browser re-proof. See
`docs/transport/nodes/UI-20-evidence.md` and BACKLOG for the handover.

---

### Developer guidelines

Do
- Put JavaScript into files under `static/js/` and bind DOM events using `addEventListener`.
- Include scripts using `<script nonce="{{ csp_nonce }}" src="...">`.
- Keep styles in `static/css/` files.
- If you must load third-party assets, prefer self-hosting. If third-party is unavoidable, add Subresource Integrity (SRI) and pin versions, and request an explicit allow-list review.

Don't
- Don't use inline JS (`<script>...</script>` without a nonce, or `onclick=...` etc.).
- Don't add new inline `<style>` or style attributes; use classes and external CSS.

---

### Migration plan for styles (to remove 'unsafe-inline')

1) Move inline `<style>` blocks in admin templates to `static/css/modules/...` files. Reference them in the templates.
2) Replace `style="..."` attributes with semantic classes and CSS rules.
3) When no inline styles remain (or only nonced inline styles remain), switch `style-src` to:
```
style-src 'self' https://fonts.googleapis.com;
```
4) Optionally self-host Google Fonts and set `font-src 'self'` and remove `https://fonts.googleapis.com` reference.

Validation steps:
- Inspect DevTools for any CSP violations.
- Review `/csp-report` logs; fix issues until clean.
- Flip the enforced policy (remove `'unsafe-inline'` from `style-src` in the main header).

---

### Verification checklist
- [ ] All admin actions work (Approve/Publish/Suspend/Restore/Reject/Takedown), with POSTs carrying `credentials: 'same-origin'` and `X-CSRFToken`.
- [ ] No script CSP violations in DevTools.
- [ ] (During migration) Only expected style violations appear in `/csp-report`.
- [ ] After migration, zero CSP violations.

---

### Change control
- Enforced CSP and Report-Only policies are assembled in `app/__init__.py::after_request_pipeline` (step "2. Security headers"). *(Corrected 2026-10-05: this section previously named `apply_security_headers`, which does not exist in `app/__init__.py`.)*
- Hardening headers (incl. `Permissions-Policy`) are set in the same `after_request_pipeline`.
- CSP nonce generation in `set_csp_nonce` and injected via `inject_csp_nonce`.
- `upgrade-insecure-requests` is gated by `should_upgrade_insecure()`, which reads `SystemConfig.CSP_UPGRADE_INSECURE` and fails closed to `False`.
- CSP reporting handled by `POST /csp-report`.
- Policy assertions live in `tests/test_ui_20_csp.py`.

---

### Rollback
If a critical UI regression is observed:
- Temporarily re-add `'unsafe-inline'` to `style-src` in the enforced header while fixing the offending template. Do NOT re-add `'unsafe-inline'` to `script-src`.

