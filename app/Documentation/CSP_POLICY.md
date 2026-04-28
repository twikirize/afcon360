### AFCON360 Web App — Content Security Policy (CSP)

This document describes the CSP we enforce, how nonces are generated and applied, how to monitor violations, and how developers should add scripts and styles going forward.

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
script-src 'self' 'nonce-<per-request-nonce>';
style-src  'self' 'unsafe-inline' https://fonts.googleapis.com;
img-src    'self' data: https:;
font-src   'self' https://fonts.gstatic.com;
connect-src 'self';
object-src 'none';
frame-ancestors 'none';
form-action 'self';
base-uri 'self';
upgrade-insecure-requests;
```

Key points:
- Scripts: only same-origin scripts that carry the per-request nonce are allowed. Inline scripts/handlers are blocked.
- Styles: inline styles still allowed temporarily, to avoid regressions while styles are being migrated to static CSS. Google Fonts stylesheets allowed.
- Images: self, data URIs and https to accommodate avatars/CDN images; can be tightened if desired.
- Fonts: Google Fonts host allowed; can be removed once fonts are self-hosted.
- Mixed content is disallowed (`upgrade-insecure-requests`).

The app also returns modern hardening headers:
- `Strict-Transport-Security` (on HTTPS)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()`
- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Resource-Policy: same-origin`
- `X-Permitted-Cross-Domain-Policies: none`

---

### Monitoring policy (Report-Only)

To safely progress to a strict no-inline-styles posture, we set a parallel `Content-Security-Policy-Report-Only` header:

```
default-src 'self';
script-src 'self' 'nonce-<per-request-nonce>';
style-src  'self' https://fonts.googleapis.com;
img-src    'self' data: https:;
font-src   'self' https://fonts.gstatic.com;
connect-src 'self';
object-src 'none';
frame-ancestors 'none';
form-action 'self';
base-uri 'self';
upgrade-insecure-requests; report-to csp-endpoint; report-uri /csp-report
```

This allows us to see violations (mostly inline `<style>` and style attributes) without breaking production.

Reporting integration:
- `Report-To` (and the legacy `Reporting-Endpoints`) headers point to `/csp-report`.
- The app exposes `POST /csp-report` which logs violation payloads (`current_app.logger.warning`).

---

### Nonce generation and usage

- A per-request nonce is generated in `@app.before_request` and exposed to templates via a context processor as `{{ csp_nonce }}`.
- All allowed `<script>` tags must use either:
  - external sources from `'self'` plus an attribute `nonce="{{ csp_nonce }}"`, or
  - inline scripts with `nonce="{{ csp_nonce }}"` (not recommended; prefer external files)
- Inline event handlers (e.g., `onclick="..."`) are not allowed. Use `addEventListener` in external JS modules.

Example in a template:
```
<script nonce="{{ csp_nonce }}" src="{{ url_for('static', filename='js/admin_moderation.js') }}"></script>
```

---

### Developer guidelines

Do
- Put JavaScript into files under `static/js/` and bind DOM events using `addEventListener`.
- Include scripts using `<script nonce="{{ csp_nonce }}" src="...">`.
- Keep styles in `static/css/` files.
- If you must load third-party assets, prefer self-hosting. If third-party is unavoidable, add Subresource Integrity (SRI) and pin versions, and request an explicit allow-list review.

Don’t
- Don’t use inline JS (`<script>...</script>` without a nonce, or `onclick=...` etc.).
- Don’t add new inline `<style>` or style attributes; use classes and external CSS.

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
- Enforced CSP and Report-Only policies managed in `app/__init__.py::apply_security_headers`.
- CSP nonce generation in `set_csp_nonce` and injected via `inject_csp_nonce`.
- CSP reporting handled by `POST /csp-report`.

---

### Rollback
If a critical UI regression is observed:
- Temporarily re-add `'unsafe-inline'` to `style-src` in the enforced header while fixing the offending template. Do NOT re-add `'unsafe-inline'` to `script-src`.

