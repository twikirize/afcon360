# AFCON360 Theme Coverage

**Purpose:** Tracks which user-facing templates are dark/light theme-aware using the existing theme
system (theme-variables.css, dark-mode.css, theme-manager.js), and which files are intentionally
excluded.

**Last updated:** 2026-09-15 (theme unification pass)

---

## Theme System (single source of truth)

| Asset | Location | Role |
|---|---|---|
| Theme tokens | `static/css/global/theme-variables.css` | token layer (light) + `body.dark-mode` token overrides + pre-JS media guard (`:root:not(.light-mode)`) |
| Dark overrides | `static/css/global/dark-mode.css` | `:where(body.dark-mode)` generic component flips + standalone body rule |
| Manager | `static/js/global/theme-manager.js` | reads `/theme/api/preferences`, applies `body.dark-mode`, dashboard colors on `<html>`, guarded for unauth (`data-theme-disabled` respected) |

**Canonical include block** (used on standalone pages; `base.html` already includes it):

```html
<meta name="user-authenticated" content="true|false">
<link rel="stylesheet" href="{{ url_for('static', filename='css/global/theme-variables.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/global/dark-mode.css') }}">
...
<script src="{{ url_for('static', filename='js/global/theme-manager.js') }}" defer></script>
```

---

## Coverage map

### A. Pages extending `base.html` (COVERED automatically)
`base.html` ships theme-variables.css, dark-mode.css and theme-manager.js. ~230 templates extend
`base.html` either directly or via `admin/admin.html`, `audit/base_audit.html`,
`user/base_user_dashboard.html`, `shell/dashboard_shell.html`. Nothing to do.

### B. Module base templates (COVERED — edited this pass)
| Base | Theme assets |
|---|---|
| `wallet/base_wallet.html` | theme-variables (pre-existing); dark-mode.css + theme-manager.js added |
| `admin/moderator/base_moderator.html` | theme-variables (pre-existing); dark-mode.css + theme-manager.js added |
| `admin/compliance/base_compliance.html` | theme-variables (pre-existing); dark-mode.css + theme-manager.js added |
| `transport/base.html` | theme-variables.css + dark-mode.css + meta added; `js/theme-manager.js` dead path fixed → `js/global/theme-manager.js` |
| `transport/dashboard/base_dashboard.html` | theme-variables (pre-existing); dark-mode.css + meta added; dead JS path fixed → `js/global/theme-manager.js` |

Notes: those bases define design tokens on `:root` mapping to theme vars (e.g. `--bg: var(--bg-body)`),
so they flip correctly in dark mode via var pending-substitution. `user/base_user_dashboard.html`
and `shell/dashboard_shell.html` are covered via `base.html`.

### C. Standalone (own `<html>`) pages (COVERED — edited this pass)
| Page | Extra handling |
|---|---|
| `login.html` | page-specific `body.dark-mode` override `<style>` block |
| `reset_request.html` / `reset_password.html` / `reset_confirm.html` | assets only |
| `receiver_wallet.html` | assets only (`user-authenticated=true`) |
| `kyc/overview.html` | assets only |
| `bulk_verify.html` | assets only |
| `errors/404.html` | assets + `.error-card` dark overrides |
| `errors/500.html` | assets + `.error-card`/`.error-title`/`.error-message`/`.error-details`/`.btn-secondary` overrides |
| `placeholder/coming_soon.html` | assets only |
| `agent_commissions.html` | assets only |
| `auditor/dashboard.html` | assets + `.card-header`/`.table`/body overrides (inline hex rules beat generic CSS) |
| `org/dashboard_old.html` | assets + `body`/`.container`/`h1`/`.placeholder` overrides (`!important` on body bg) |
| `admin/settings.html` | assets only; heavy custom CSS → some inner surfaces residual (see BACKLOG) |

### D. Transport legacy / fragments (SKIPPED — intentionally)
- `transport/home_pane.html`, `transport/partials/*`, `transport/partials/modals/*`,
  `transport/partials/tables/*`, `transport/dashboard/widgets/*` — fragments included inside
  themed bases; do NOT add theme assets.
- `transport/{analytics,bookings,drivers,incidents,organisations,routes,settings,vehicles}/*,
  dashboard/keep.html` — 9–10 line empty scaffolds or archived duplicates; dead/unrouted.
- `monitor.html` — intentionally dark-by-design; **excluded**.

### E. Excluded (never theme-integrated)
- **Email templates**: `templates/email/*`, `templates/notifications/email/*` — mail clients strip
  external CSS/JS; light-mode inline styles only. Do NOT add theme assets.
- Empty shells: `verify.html`, `accommodation/host/listings/create.html`, `owner/backup_codes.html`,
  `owner/later.html`, `admin/moderator_dashboard.html`-style confirmed-empty placeholders are dead.

---

## Verification performed
- `python -c "from app import create_app"` — import OK.
- Compiled all 19 edited templates via `app.jinja_env.get_template(...)` — ALL_COMPILED (no Jinja
  syntax errors introduced).
- Confirmed no remaining references to the 0-byte `static/js/theme-manager.js` (one comment fixed).
- Dark-mode visual verification (Light → Dark → Light) is a pending manual/Playwright step.

## Residual items
- `admin/settings.html` and other heavily custom inline-styled admin pages: surfaces not covered by
  dark-mode.css generic tokens may remain light in dark mode — tracked in BACKLOG.md.
- Broken `{% extends %}` targets (admin/base.html, owner/*) — pre-existing, tracked in BACKLOG.md.