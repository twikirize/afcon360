# Fix dashboard redirects, CSRF token, and broken owner role check

## Root causes

1. **`dashboard.dashboard` endpoint does not exist.** Multiple files redirect to it, causing `BuildError` (500).
2. **CSRF token syntax error.** `templates/admin/manage_roles.html` uses `{{ csrf_token }}` without parentheses, so the rendered value is the function object, not the actual token. This invalidates every POST from that form (observed on `/admin/owner/roles/assign`).
3. **`require_owner_role` in owner route modules is non-functional.** Both `app/owner/routes/role_management.py` and `app/owner/routes/settings.py` read `getattr(request, 'user_role', 'user')`, but `request.user_role` is never set anywhere in the codebase. The decorator therefore always treats the caller as a non-owner.

## Files changed

- `app/owner/routes/role_management.py`
- `app/owner/routes/settings.py`
- `app/admin/routes.py`
- `app/admin/route_modules/org_member.py`
- `templates/admin/manage_roles.html`

## What to change

### 1. Fix invalid `dashboard.dashboard` redirects

Replace every `url_for('dashboard.dashboard')` with a valid endpoint.

| File | Lines | Replacement |
|------|-------|-------------|
| `app/owner/routes/role_management.py` | 42 | `url_for('admin.owner.dashboard')` |
| `app/admin/routes.py` | 2141, 2148, 2153, 2176, 2183, 2188 | `url_for('admin.dashboard')` |
| `app/admin/route_modules/org_member.py` | 68 | `url_for('admin.dashboard')` |

### 2. Fix CSRF token in template

In `templates/admin/manage_roles.html` line 260:

```diff
- <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
+ <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

### 3. Fix `require_owner_role` decorator in owner route modules

Both files define a `require_owner_role` decorator that relies on `request.user_role` (never set). Replace the body with a real owner check using `flask_login.current_user`, mirroring the logic already used in `app.admin.owner.decorators.owner_required`.

**`app/owner/routes/role_management.py`** — add `current_user` import and replace the decorator:

```python
def require_owner_role(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_login import current_user
        is_owner = False

        if hasattr(current_user, 'has_role'):
            try:
                is_owner = current_user.has_role('owner')
            except Exception:
                pass

        if not is_owner and hasattr(current_user, 'roles'):
            try:
                for ur in current_user.roles:
                    if ur.role and ur.role.name == 'owner':
                        is_owner = True
                        break
            except Exception:
                pass

        if not is_owner:
            flash('Owner access required', 'danger')
            return redirect(url_for('admin.owner.dashboard'))

        return f(*args, **kwargs)

    return decorated_function
```

**`app/owner/routes/settings.py`** — same fix, but keep the existing JSON 403 response:

```python
def require_owner_role(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_login import current_user
        is_owner = False

        if hasattr(current_user, 'has_role'):
            try:
                is_owner = current_user.has_role('owner')
            except Exception:
                pass

        if not is_owner and hasattr(current_user, 'roles'):
            try:
                for ur in current_user.roles:
                    if ur.role and ur.role.name == 'owner':
                        is_owner = True
                        break
            except Exception:
                pass

        if not is_owner:
            return jsonify({
                'success': False,
                'error': 'Owner access required',
                'error_code': 'INSUFFICIENT_PERMISSIONS'
            }), 403

        return f(*args, **kwargs)

    return decorated_function
```

### 4. CSP status endpoint

Verified via direct app inspection: `/owner/csp/status` is registered as `csp.get_status` and `/owner/csp/toggle` as `csp.toggle`. The 404s in the provided logs were either from a transient state or a stale server process. No code change is required for CSP. If a 404 persists after this fix, restart the dev server and re-test.

## Verification

Run the app and confirm:

```powershell
& .venv/Scripts/python.exe -c "from app import create_app; app=create_app(); print({r.endpoint: r.rule for r in app.url_map.iter_rules() if 'dashboard' in r.endpoint and 'role' not in r.endpoint})"
```

Then manually test:
1. Access `/admin/owner/owner/role-management/` as owner → loads without `BuildError`.
2. POST the assign-role form from templates/admin/manage_roles.html → succeeds (CSRF token now valid).
3. Visit `/admin/org-member` without `org_member` role → redirects to `/admin/dashboard` without `BuildError`.
4. Visit `/admin/owner/settings` as non-owner → returns JSON 403 instead of crashing.

No migration is needed.
