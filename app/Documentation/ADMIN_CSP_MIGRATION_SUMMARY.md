### Admin CSP Migration — Summary and Export

This document exports the key decisions and changes made during the CSP hardening and admin moderation reliability work.

#### Context
- Moderation buttons (Approve, Publish, Suspend, etc.) on admin pages used inline `onclick` handlers and inline `<script>` blocks.
- A strict CSP blocked inline scripts, so clicks appeared to do nothing.
- Objective: Restore functionality and harden security without compromising the CSP posture.

---

### Final state (current)
- Strict, nonce-based CSP for scripts (no `unsafe-inline`): `script-src 'self' 'nonce-<per-request>'`.
- Admin JS externalized: `static/js/admin_moderation.js` binds event listeners and handles CSRF, toasts, confirmations, row removal, and live clock.
- Identifier hardening: client derives the event identifier from DOM context if the inline-provided slug is missing, preventing `/null/<action>` calls.
- CSP reporting: Added `Content-Security-Policy-Report-Only` for a stricter style policy, `Report-To`/`Reporting-Endpoints`, and a `POST /csp-report` endpoint to log violations.
- Additional headers: HSTS (HTTPS), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `COOP`, `CORP`, `X-Permitted-Cross-Domain-Policies`.

---

### Key code changes
1) `app/__init__.py`
- Per-request nonce generation and injection (`set_csp_nonce`, `inject_csp_nonce`).
- Enforced CSP header focused on scripts with nonces; tightened sources; added security headers.
- Report-Only CSP mirroring the desired final style policy (no inline styles), plus `Report-To` and legacy `Reporting-Endpoints`.
- New endpoint: `POST /csp-report` to log violation payloads.

2) `static/js/admin_moderation.js` (new)
- All moderation logic moved here; binds via `addEventListener` (no inline `onclick`).
- Robust identifier resolution from DOM when slug is missing; blocks submissions if still indeterminate.
- Sends CSRF header and cookies (`credentials: 'same-origin'`), handles non-JSON responses gracefully, and provides UI toasts.

3) Templates
- `templates/events/admin/dashboard.html` and `templates/events/admin/events.html` load the external script with `nonce="{{ csp_nonce }}`.
- Inline scripts remain but are now ignored by CSP; external JS takes over.

4) Docs
- `app/Documentation/CSP_POLICY.md` — policy, rollout, reporting, and dev guidelines.

---

### Verification results
- Logs show successful actions:
  - `POST /events/admin/<slug>/takedown` → 200 with compliance log
  - `POST /events/admin/<slug>/suspend` → 200 with moderation log
- Navigating filtered views works (`/events/admin/events?status=suspended`).
- Earlier 404s at `/events/admin/null/<action>` eliminated by identifier resolution safeguards.

---

### Next steps (optional, recommended)
- Move inline `<style>` from admin templates to `static/css/...` and then remove `'unsafe-inline'` from `style-src` in the enforced CSP.
- Consider self-hosting fonts and reducing `style-src`/`font-src` to `'self'` only.
- Add CI lint to block inline `on*=` handlers and `<script>` without nonces in templates.
- Optionally add SRI for any third-party assets that must remain.

---

### Rollback notes
- If a UI regression surfaces, temporarily re-add `'unsafe-inline'` to `style-src` only. Do not re-add `'unsafe-inline'` to `script-src`.

---

### Snippets
Enforced CSP (shortened):
```
default-src 'self';
script-src 'self' 'nonce-<per-request>';
style-src  'self' 'unsafe-inline' https://fonts.googleapis.com;
img-src    'self' data: https:; font-src 'self' https://fonts.gstatic.com;
connect-src 'self'; object-src 'none'; frame-ancestors 'none';
form-action 'self'; base-uri 'self'; upgrade-insecure-requests;
```

Report-Only CSP (stricter styles):
```
default-src 'self';
script-src 'self' 'nonce-<per-request>';
style-src  'self' https://fonts.googleapis.com;
img-src    'self' data: https:; font-src 'self' https://fonts.gstatic.com;
connect-src 'self'; object-src 'none'; frame-ancestors 'none';
form-action 'self'; base-uri 'self'; upgrade-insecure-requests; report-to csp-endpoint; report-uri /csp-report
```

Admin JS include:
```
<script nonce="{{ csp_nonce }}" src="{{ url_for('static', filename='js/admin_moderation.js') }}"></script>
```
