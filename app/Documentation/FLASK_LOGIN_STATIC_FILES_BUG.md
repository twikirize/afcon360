# Flask-Login Firing on Static File Requests — Diagnosis & Fix
**Date:** 2026-06-23  
**Severity:** Performance (silent in production, severe in dev; would surface under load)

---

## The Problem

Every `@before_request` hook in the app ran on **every** request Flask handled — including
`/static/css/...`, `/static/js/...`, `/static/icons/...`.

A single page load in the browser fires ~12 static file requests concurrently. Each one
triggered the full auth chain:

```
GET /static/css/dashboard.css
  → load_identity_context()     — accesses current_user → user_loader → DB query
  → ensure_clean_transaction()  — db.session.expire_all() on a static file
  → _run_deferred_startup()     — unnecessary work
  → refresh_module_flags()      — SystemSetting DB query on a static file
  → Flask serves the file
```

Result: **~20 user_loader DB queries per page load** instead of 1.

---

## Why Flask-Login Fires a DB Query

`current_user` is a `LocalProxy` wrapping:

```python
def _get_user():
    if "_login_user" not in g:
        current_app.login_manager._load_user()  # calls user_loader → DB query
    return g._login_user
```

Once `g._login_user` is set it's free. But `load_identity_context()` accesses
`current_user` on every request, including static files — so every static file request
triggers `_load_user()` → your `user_loader` → a DB query.

---

## Why No One Noticed

`user_loader` had no logging. Someone added `logger.warning("USER_LOADER called...")` to
debug an unrelated issue, and the scale of the problem became visible immediately.

The bug existed silently the whole time. In production with Nginx, `/static/` is served
directly by Nginx — Flask never sees it. But the dev server serves static files itself,
so the full `before_request` chain runs on every CSS/JS file.

---

## The Fix

Add a static-file guard at the top of every `before_request` hook that touches auth or DB:

```python
@app.before_request
def load_identity_context():
    if request.path.startswith(('/static/', '/favicon.ico')):
        return          # static files need no auth context
    # ... rest of hook
```

Applied to:
- `load_identity_context()` — `app/__init__.py`
- `ensure_clean_transaction()` — `app/__init__.py`
- `_run_deferred_startup()` — `app/__init__.py`
- `refresh_module_flags()` — `app/middleware/reload_modules.py`

---

## Permanent Team Rule

> **Any `@before_request` hook that touches auth, sessions, or the database must start with:**
> ```python
> if request.path.startswith(('/static/', '/favicon.ico')):
>     return
> ```

This applies to hooks registered directly on `app` and inside `init_app()` middleware functions.

---

## Additional Fixes Made in the Same Session

| Issue | Root Cause | Fix |
|---|---|---|
| Static file requests triggering user_loader | `before_request` hooks had no static-file guard | Added `/static/` guard to all 4 hooks |
| `ThemeManager` instantiated twice per page | `theme-manager.js` auto-inits at bottom; `base.html` also called `new ThemeManager()` | Removed duplicate in `base.html` |
| User CSS served via Flask route | `serve_user_theme_css` accessed `current_user` on every page load | Replaced Flask route with direct `/static/css/generated/user-{id}.css` path; `onerror="this.remove()"` handles missing files |
| `/theme/api/preferences` fetched on every navigation | `fetch()` sent `Cache-Control: no-cache` forcing a fresh DB query every time | Removed no-cache from JS; added `Cache-Control: private, max-age=60` on response |
| Global `no-store` overriding API cache | `after_request` set `no-store` on all authenticated responses unconditionally | Changed to only set `no-store` if route hasn't already set its own `Cache-Control` |
| `db.session.remove()` in `ensure_clean_transaction` | Detached `g._login_user`, causing Flask-Login to reload user on every ORM attribute access | Changed to `db.session.expire_all()` — marks state stale without detaching objects |
| `/accommodation/host/dashboard` → 302 | `can_host()` required KYC verification; owner account has no KYC records | Added owner/super_admin bypass at top of `can_host()` |
| `/accommodation/host/dashboard` → 500 | Template `accommodation/host/dashboard.html` didn't exist | Created the template |

---

## Benchmark

| Metric | Before | After |
|---|---|---|
| `user_loader` DB calls per page load | ~20 | 1 |
| `/theme/api/preferences` fetches per navigation | 2 (duplicate ThemeManager + no-cache) | 1 (cached 60s after first load) |
| DB queries for static file requests | ~12 per page | 0 |

At 1,000 users/min each loading one page:  
**Before:** ~20,000 auth DB queries/min  
**After:** ~1,000 auth DB queries/min  
**Reduction: 20×**

---

## Production Note

This bug is **invisible in production** when Nginx/Apache serves `/static/` directly
(Flask never sees those requests). However fixing it in development is correct architecture
and prevents the same class of bug from affecting authenticated API sub-requests
(`/theme/api/preferences`, `/api/*`, etc.) which do reach Flask in all environments.
