# AFCON360 — Complete Implementation Guide
# For Aider CLI Implementation
# ============================================================
# This document is self-contained. copilot should read it fully
# before touching any file. Every change has a reason, a location,
# and exact before/after behaviour described.
# ============================================================

---

## PART 1 — BACKGROUND & ROOT CAUSE ANALYSIS

### What is broken and why

Two independent bugs exist. They share the same root cause: a previous
developer called `ForensicAuditService.log_attempt(entity_id=None)` on
page-view routes where no specific database entity is being accessed.

The `ForensicAuditService` writes to `DataChangeLog`, which extends
`ProtectedModel`. `ProtectedModel.__setattr__` calls
`IDGuard.check_public_id()` on every field assignment. When `entity_id`
is `None`, IDGuard raises:

    RuntimeError: ID System Violation: Public ID is not a valid UUID: None

**Bug 1 — `/wallet/dashboard` (soft failure)**
The call is wrapped in `try/except Exception: pass` so the page loads,
but a `SYSTEM_ERROR` is written to the audit log on every single visit.
Confirmed at `app/wallet/routes.py` line 224.

**Bug 2 — `/tourism/` (hard 500 crash)**
The same call exists with NO try/except. Every visit to the tourism home
crashes with a 500. Confirmed at `app/tourism/routes.py` line 19.

### The classification rule (critical — apply everywhere)

    ForensicAuditService.log_attempt(entity_id=None)   → ALWAYS WRONG. Delete it.
    ForensicAuditService.log_attempt(entity_id=<value>) → Legitimate. Keep it.
    AnalyticsService.track_page_view(module)            → Correct for page views.

A forensic audit log requires a real entity because it answers the
compliance question: "Who did what to which specific record?" A page view
has no "which specific record" — it belongs in analytics, not audit logs.

### The wallet route architecture (why 3 routes exist)

The wallet was designed as a shippable standalone product (stated in
`app/wallet/models.py` docstring). Three entry points exist intentionally:

    /wallet/          → home()         Module root. External links point here.
    /wallet/home      → wallet_home()  Public marketing page for non-logged-in users.
    /wallet/dashboard → wallet_dashboard()  The actual authenticated dashboard.

**Current problem with this architecture:**

1. `home()` has `@login_required` — so unauthenticated users hitting
   `/wallet/` get bounced to the login page instead of seeing the
   marketing page. This is backwards.

2. `wallet_home()` also has `@login_required` — the marketing page
   (`wallet_home.html`) which extends `base.html` and is clearly designed
   for public/unauthenticated users, is gated behind login. Wrong.

3. `home()` and `wallet_home()` both blindly redirect to `wallet_dashboard`
   with no intelligence — they should check auth status first.

4. `wallet_dashboard()` receives all traffic but doesn't query the wallet
   before the audit log call — so entity_id is always None at that point.

### The correct three-gate architecture (how PayPal, MoMo, M-Pesa do it)

    Gate 1: Public/Unauthenticated  → wallet_home.html  (marketing, no login needed)
    Gate 2: Logged in, no wallet    → wallet_dashboard.html with no_wallet=True
                                      OR redirect to wallet_activate if wallet
                                      exists but is not yet activated
    Gate 3: Logged in, wallet active → wallet_dashboard.html with full data

The routing decision tree lives in ONE place: the `home()` route at `/wallet/`.
All other entry points funnel into this decision tree.

### The `original_file.html` situation

`original_file.html` is legacy/orphaned. It references model fields
(`wallet.nationality`, `wallet.location`, `wallet.home_currency`,
`wallet.balance_home`, `wallet.balance_local`) that do not exist on the
current `Wallet` model in `app/wallet/models.py`. The current model has
`balance`, `available_balance`, `currency`. This template should be
retired — it will cause NameErrors if rendered.

### The 9 known issues from WALLET_SYSTEM_DOCUMENTATION.md

The documentation already identified these. They are all fixed here:

| # | Issue | Location | Fix |
|---|---|---|---|
| 1 | CSRF not validated on activation POST | wallet/routes.py | Add validate_csrf() call |
| 2 | Re-activation allowed | wallet/routes.py | Guard with if account.verified check |
| 3 | requires_terms_acceptance never used | wallet_status_service.py | Wire to dashboard banner |
| 4 | require_payout_access inconsistency | wallet/routes.py | Use decorator consistently |
| 5 | redirect_to param unused | wallet_check.py | Use it or remove it |
| 6 | action variable not passed to template | wallet/routes.py | Pass action='verify' |
| 7 | Template uses `wallet` but route passes `account` | wallet_activate.html | Pass as wallet= |
| 8 | csrf_token not called as function | wallet_activate.html | Change to csrf_token() |
| 9 | accept_terms field missing from activation form | wallet_activate.html | Already present — verify |

---

## PART 2 — TOURISM FIX

### Files to modify
- `app/tourism/routes.py`

### Problem
`home()` calls `ForensicAuditService.log_attempt(entity_id=None)` with no
try/except. Hard 500 on every visit to `/tourism/`.

### Rule
- `home()` — visiting a public listing page is NOT a forensic audit event.
  Remove the call entirely. Add `AnalyticsService.track_page_view("tourism")`
  instead once analytics service is in place (use try/except to be safe until
  then).
- `detail(slug)` — accessing a SPECIFIC named resource IS a legitimate audit
  event. `entity_id=slug` is a real value. Keep this call exactly as-is.
- `moderate()` — moderator access is a security event. Keep `AuditService.security()`
  exactly as-is.

### Exact change to `app/tourism/routes.py`

**REMOVE** lines 15–24 (the entire ForensicAuditService block in `home()`):

```python
# DELETE THIS ENTIRE BLOCK from home():
ForensicAuditService.log_attempt(
    entity_type="tourism",
    entity_id=None,
    action="view_home",
    user_id=current_user.id,
    ip_address=request.remote_addr,
    user_agent=request.user_agent.string if request.user_agent else None
)
```

**REPLACE** the `home()` function with:

```python
@tourism_bp.route("/", endpoint="home")
@login_required
@require_role('fan', 'admin', 'owner')
def home():
    """
    Tourism home page.
    No forensic audit — visiting a listing page is not a security event
    and there is no specific entity_id to reference.
    Analytics tracking added instead (lightweight Redis counter).
    """
    try:
        from app.services.analytics import AnalyticsService
        AnalyticsService.track_page_view("tourism")
    except Exception:
        pass  # Analytics must never block page load
    return render_template("tourism_home.html")
```

**KEEP** `detail()`, `moderate()`, `moderate_action()`, `flag_listing()`
exactly as they are. Do not touch them.

**REMOVE** the top-level import of `ForensicAuditService` only if it is
no longer used anywhere else in `tourism/routes.py`. Check first — if
`detail()` still uses it, leave the import.

---

## PART 3 — WALLET ROUTES FIX

### Files to modify
- `app/wallet/routes.py`

### 3.1 Fix `home()` at `/wallet/`

This is the most important change. Transform the dumb redirect into the
intelligent traffic director. Remove `@login_required` so public users
can reach the marketing page.

**REPLACE** the entire `home()` function:

```python
@wallet_bp.route('/')
def home():
    """
    Wallet module entry point — intelligent traffic director.

    Decision tree (matches PayPal/MoMo/M-Pesa pattern):
      - Not logged in              → wallet_home.html (public marketing page)
      - Logged in, no wallet       → wallet_dashboard (shows no_wallet=True state)
      - Logged in, wallet inactive → wallet_activate (needs activation)
      - Logged in, wallet active   → wallet_dashboard (full experience)

    No audit log here — no entity exists yet.
    No analytics here — this is a redirect, not a landing.
    """
    if not current_user.is_authenticated:
        return render_template('wallet/wallet_home.html')

    # User is authenticated — check wallet status
    try:
        from app.wallet.services.wallet_status_service import get_wallet_status
        wallet_status = get_wallet_status(current_user.id)

        if wallet_status is None or not wallet_status.has_wallet:
            # No wallet exists — go to dashboard which shows "Create Wallet" CTA
            return redirect(url_for('wallet.wallet_dashboard'))

        if not wallet_status.is_activated:
            # Wallet exists but not activated — go to activation page
            return redirect(url_for('wallet.wallet_activate'))

        # Wallet exists and is active — go to dashboard
        return redirect(url_for('wallet.wallet_dashboard'))

    except Exception as e:
        current_app.logger.error(f"Wallet home routing error: {e}")
        # Fail safe — send authenticated users to dashboard
        return redirect(url_for('wallet.wallet_dashboard'))
```

### 3.2 Fix `wallet_home()` at `/wallet/home`

This is the public marketing page alias. Remove `@login_required`.
Authenticated users with an active wallet should not see this page.

**REPLACE** the entire `wallet_home()` function:

```python
@wallet_bp.route('/home')
def wallet_home():
    """
    Public wallet marketing page — accessible without login.
    Shows wallet features, benefits, how it works, FAQs.
    Redirects authenticated users with active wallets to dashboard.
    """
    if current_user.is_authenticated:
        try:
            from app.wallet.services.wallet_status_service import get_wallet_status
            wallet_status = get_wallet_status(current_user.id)
            if wallet_status and wallet_status.is_activated:
                # Already has an active wallet — no need to see marketing page
                return redirect(url_for('wallet.wallet_dashboard'))
        except Exception:
            pass
    return render_template('wallet/wallet_home.html')
```

### 3.3 Fix `wallet_dashboard()` at `/wallet/dashboard`

Remove the broken audit log call. Add analytics AFTER the wallet is
queried so we have a real entity. Keep all existing dashboard logic.

**FIND** this block in `wallet_dashboard()` and DELETE it entirely:

```python
# DELETE — this is the source of the 🔴 ID SYSTEM VIOLATION
try:
    from app.audit.forensic_audit import ForensicAuditService
    ForensicAuditService.log_attempt(
        entity_type="wallet",
        entity_id=None,
        action="view_dashboard",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
except Exception:
    pass
```

**ADD** analytics tracking at the top of `wallet_dashboard()`, before
any DB queries:

```python
# Analytics: lightweight Redis counter. No UUID required. ~0.1ms.
try:
    from app.services.analytics import AnalyticsService
    AnalyticsService.track_page_view('wallet')
except Exception:
    pass
```

**ADD** a legitimate audit log call AFTER the wallet/account is queried
from the database (find the line where `account` is assigned, add
AFTER it):

```python
# Legitimate forensic audit — we now have a real entity_id
if account and account.public_id:
    try:
        from app.audit.forensic_audit import ForensicAuditService
        ForensicAuditService.log_attempt(
            entity_type="wallet",
            entity_id=account.public_id,   # ← real UUID, not None
            action="view_dashboard",
            user_id=current_user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None
        )
    except Exception:
        pass
```

### 3.4 Fix `wallet_activate()` — Issue 6 (action variable not passed)

**FIND** the `wallet_activate()` GET route and ensure it passes `action='verify'`
to the template when a wallet exists:

```python
@wallet_bp.route('/activate', methods=['GET'])
@login_required
def wallet_activate():
    """Wallet activation page."""
    try:
        from app.wallet.services.wallet_status_service import get_wallet_status
        wallet_status = get_wallet_status(current_user.id)

        if not wallet_status or not wallet_status.has_wallet:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))

        if wallet_status.is_activated:
            flash('Your wallet is already activated.', 'info')
            return redirect(url_for('wallet.wallet_dashboard'))

        # Get account object for template — pass as 'wallet' not 'account'
        # (fixes Issue 7: template uses {{ wallet.id }} not {{ account.id }})
        account = wallet_status.account  # or however account is retrieved
        return render_template(
            'wallet/wallet_activate.html',
            wallet=account,       # ← 'wallet', not 'account' — fixes Issue 7
            action='verify'       # ← fixes Issue 6
        )
    except Exception as e:
        current_app.logger.error(f"Wallet activation page error: {e}")
        flash('Error loading activation page.', 'danger')
        return redirect(url_for('wallet.wallet_dashboard'))
```

### 3.5 Fix `wallet_activate_submit()` — Issues 1, 2, 3

**FIND** the activation POST handler and apply these fixes:

```python
@wallet_bp.route('/activate', methods=['POST'])
@login_required
def wallet_activate_submit():
    """Process wallet activation."""
    # Issue 1 fix: validate CSRF
    from flask_wtf.csrf import validate_csrf
    csrf_token = request.form.get('csrf_token')
    if not csrf_token:
        flash('Security token missing. Please try again.', 'danger')
        return redirect(url_for('wallet.wallet_activate'))
    try:
        validate_csrf(csrf_token)
    except Exception:
        flash('Invalid security token. Please try again.', 'danger')
        return redirect(url_for('wallet.wallet_activate'))

    # Issue 2 fix: prevent re-activation
    try:
        from app.wallet.services.wallet_status_service import get_wallet_status
        wallet_status = get_wallet_status(current_user.id)
        if wallet_status and wallet_status.is_activated:
            flash('Your wallet is already activated.', 'info')
            return redirect(url_for('wallet.wallet_dashboard'))
    except Exception:
        pass

    # ... rest of existing activation logic unchanged ...
```

### 3.6 Fix Issue 4 — `require_payout_access` consistency

**FIND** `agent_payout_history()` and change:

```python
# BEFORE:
@require_wallet_for_feature(feature=WalletFeature.VIEW_PAYOUT_HISTORY)

# AFTER:
@require_payout_access
```

Make sure `require_payout_access` is imported at the top of the file.

### 3.7 Fix Issue 5 — `redirect_to` parameter in wallet_check.py

**FILE:** `app/wallet/middleware/wallet_check.py`

**FIND** `require_wallet_for_feature()` and either:

Option A — use the parameter:
```python
def require_wallet_for_feature(feature=None, redirect_to=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # ... existing checks ...
            target = redirect_to or url_for('wallet.wallet_dashboard')
            return redirect(target)
        return wrapper
    return decorator
```

Option B — remove it if unused:
```python
def require_wallet_for_feature(feature=None):  # remove redirect_to param
```

Choose Option A — it makes the decorator more useful for future routes.

---

## PART 4 — TEMPLATE FIXES

### 4.1 Fix `wallet_activate.html` — Issues 8 and 9

**FILE:** `templates/wallet/wallet_activate.html`

**Issue 8:** CSRF token called as variable not function.

**FIND** (in the activation form, `{% if action == 'verify' %}` section):
```html
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
```
**REPLACE WITH:**
```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

**Issue 9:** The `accept_terms` checkbox is already present in the
template as shown in the documentation. Verify it exists:
```html
<label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;margin-bottom:16px;">
    <input type="checkbox" name="accept_terms" value="1" required>
    I have read and accept the Terms and Conditions
</label>
```
If it is missing from the `{% if action == 'verify' %}` branch, add it
before the submit button.

### 4.2 Retire `original_file.html`

**FILE:** `templates/wallet/original_file.html`

This template references model fields that do not exist on the current
`Wallet` model: `wallet.nationality`, `wallet.location`,
`wallet.home_currency`, `wallet.balance_home`, `wallet.balance_local`.

**ACTION:** Rename to `original_file.html.bak` or add a prominent comment
at the top:

```html
{# RETIRED — DO NOT USE. #}
{# This template was written against an old wallet model that no longer exists. #}
{# Fields referenced here (wallet.nationality, wallet.home_currency, etc.) #}
{# do not exist on the current Wallet model in app/wallet/models.py. #}
{# The current dashboard is wallet_dashboard.html. #}
```

Do not delete it — keep it for reference in case any route still points
to it (check first with: grep -r "original_file" app/ templates/).

### 4.3 Fix `wallet_home.html` — public access confirmation

**FILE:** `templates/wallet/wallet_home.html`

This template already extends `base.html` (not `base_wallet.html`), which
is correct for a public page. No structural changes needed.

**Verify** the auth links at the bottom still point to correct endpoints:
```html
<a href="{{ url_for('auth.register') }}">Create an account</a>
<a href="{{ url_for('auth.login') }}">log in</a>
```
If `auth.register` or `auth.login` are not the correct endpoint names in
your app, update them to match your actual auth blueprint endpoints.

### 4.4 Fix `wallet_dashboard.html` — wallet status banner logic

**FILE:** `templates/wallet/wallet_dashboard.html`

The template already has `{% if no_wallet %}` logic. This is correct.
Extend it to also handle the "wallet exists but not activated" state:

**FIND:**
```html
{% if no_wallet %}
<!-- No Wallet Banner -->
<div class="panel" ...>
  ...Create Wallet CTA...
</div>
{% else %}
  ...full dashboard...
{% endif %}
```

**REPLACE WITH:**
```html
{% if no_wallet %}
<!-- No Wallet: Show creation CTA -->
<div class="panel" style="margin-bottom:24px;background:linear-gradient(135deg,var(--blue),#1d4ed8);color:#fff;">
  <div style="padding:40px;text-align:center;">
    <h2 style="font-family:var(--font-display);font-weight:700;margin-bottom:12px;">Welcome to Your Wallet</h2>
    <p style="font-size:16px;opacity:0.9;margin-bottom:24px;">You don't have a wallet yet. Create one to start sending and receiving money.</p>
    <a href="{{ safe_url('wallet.wallet_create_page') }}" class="btn btn-lg" style="background:#fff;color:var(--blue);font-weight:600;">
      <i class="fas fa-wallet"></i> Create Wallet
    </a>
  </div>
</div>

{% elif not wallet_activated %}
<!-- Wallet exists but not activated: Show activation CTA -->
<div class="panel" style="margin-bottom:24px;background:linear-gradient(135deg,var(--orange),#c2410c);color:#fff;">
  <div style="padding:40px;text-align:center;">
    <h2 style="font-family:var(--font-display);font-weight:700;margin-bottom:12px;">Activate Your Wallet</h2>
    <p style="font-size:16px;opacity:0.9;margin-bottom:24px;">Your wallet has been created but needs activation before you can send or withdraw funds.</p>
    <a href="{{ safe_url('wallet.wallet_activate') }}" class="btn btn-lg" style="background:#fff;color:var(--orange);font-weight:600;">
      <i class="fas fa-check-circle"></i> Activate Now
    </a>
  </div>
</div>

{% else %}
<!-- Active wallet: Full dashboard -->
<div class="heading-row">
  ...existing full dashboard content unchanged...
</div>
...
{% endif %}
```

This requires the route to pass `wallet_activated` to the template.
See Section 3.3 — ensure `wallet_dashboard()` passes:
```python
wallet_activated=wallet_status.is_activated if wallet_status else False
```

### 4.5 Fix Issue 3 — `requires_terms_acceptance` banner in base_wallet.html

**FILE:** `templates/wallet/base_wallet.html`

The sidebar already has a `requires_activation` warning banner (line ~833).
Add a second banner for terms acceptance pending:

**FIND:**
```html
{% if wallet_status and wallet_status.requires_activation %}
  <div class="alert alert-warning" style="margin:16px;padding:12px;font-size:12px;">
    <i class="fas fa-exclamation-triangle"></i>
    Please activate your wallet to use all features.
  </div>
{% endif %}
```

**REPLACE WITH:**
```html
{% if wallet_status and wallet_status.requires_activation %}
  <div class="alert alert-warning" style="margin:16px;padding:12px;font-size:12px;">
    <i class="fas fa-exclamation-triangle"></i>
    Please activate your wallet to use all features.
    <a href="{{ safe_url('wallet.wallet_activate') }}" style="color:var(--accent-dk);font-weight:600;display:block;margin-top:6px;">
      Activate now →
    </a>
  </div>
{% elif wallet_status and wallet_status.requires_terms_acceptance %}
  <div class="alert alert-info" style="margin:16px;padding:12px;font-size:12px;">
    <i class="fas fa-file-contract"></i>
    Please accept the wallet Terms & Conditions.
    <a href="{{ safe_url('wallet.wallet_activate') }}" style="color:var(--blue);font-weight:600;display:block;margin-top:6px;">
      Review terms →
    </a>
  </div>
{% endif %}
```

---

## PART 5 — ANALYTICS SERVICE (new file)

### Why this is needed now

The audit log calls are being removed. The analytics service provides
the replacement — lightweight Redis counters that don't touch the audit
system, don't require UUIDs, and handle AFCON match-day traffic spikes.

### File to create: `app/services/analytics.py`

Create this file. It has zero hard dependencies — if Redis is unavailable,
every method silently returns without error. Nothing breaks.

```python
"""
app/services/analytics.py

AFCON360 Analytics Service
===========================
Lightweight page-view and conversion tracking using Redis counters.

Architecture:
  Route call → Redis INCR (fire and forget, ~0.1ms)
             → Hourly Celery/cron job flushes to analytics_page_views table
             → Long-term aggregates kept in Postgres forever (tiny storage)

What this is NOT:
  - Not a forensic audit log (use ForensicAuditService for security events)
  - Not a per-user event store
  - Not a replacement for compliance logging

Safe to call from any route. All errors are swallowed. Redis down = no tracking,
page still loads normally.
"""
from __future__ import annotations
import json
import random
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Optional

from flask import current_app, has_request_context, request
from flask_login import current_user

logger = logging.getLogger(__name__)

_redis_client = None

KNOWN_MODULES = frozenset({
    'dashboard', 'wallet', 'transport', 'accommodation',
    'tourism', 'tournament', 'events', 'profile', 'kyc',
})

TTL_HOURLY  = 172_800    # 48h  — flushed to Postgres before expiry
TTL_DAILY   = 2_592_000  # 30d  — kept in Redis for live dashboards
TTL_SAMPLE  = 604_800    # 7d   — 1% debug samples
SAMPLE_RATE = 0.01


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        _redis_client = redis.Redis(
            host=current_app.config.get('REDIS_HOST', 'localhost'),
            port=int(current_app.config.get('REDIS_PORT', 6379)),
            db=int(current_app.config.get('REDIS_ANALYTICS_DB', 1)),
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=0.5,
        )
        _redis_client.ping()
        return _redis_client
    except Exception as exc:
        logger.warning('AnalyticsService: Redis unavailable (%s). Tracking disabled.', exc)
        return None


class AnalyticsService:

    @classmethod
    def track_page_view(cls, module: str, user_id: Optional[int] = None,
                        metadata: Optional[dict] = None) -> None:
        if not cls._is_enabled():
            return
        module = cls._validate_module(module)
        if not module:
            return
        uid = cls._resolve_uid(user_id)
        r = _get_redis()
        if not r:
            return
        try:
            now = datetime.now(timezone.utc)
            date_str = now.strftime('%Y%m%d')
            hour_str = now.strftime('%Y%m%d%H')
            pipe = r.pipeline(transaction=False)
            pipe.incr(f'pv:h:{module}:{hour_str}')
            pipe.expire(f'pv:h:{module}:{hour_str}', TTL_HOURLY)
            pipe.incr(f'pv:d:{module}:{date_str}')
            pipe.expire(f'pv:d:{module}:{date_str}', TTL_DAILY)
            if uid:
                pipe.pfadd(f'uu:{module}:{date_str}', uid)
                pipe.expire(f'uu:{module}:{date_str}', TTL_DAILY)
            pipe.execute()
        except Exception as exc:
            logger.debug('AnalyticsService.track_page_view: %s', exc)

    @classmethod
    def track_conversion(cls, module: str, event: str,
                         user_id: Optional[int] = None) -> None:
        if not cls._is_enabled():
            return
        module = cls._validate_module(module)
        if not module:
            return
        uid = cls._resolve_uid(user_id)
        r = _get_redis()
        if not r:
            return
        try:
            today = datetime.now(timezone.utc).strftime('%Y%m%d')
            pipe = r.pipeline(transaction=False)
            pipe.incr(f'cv:{module}:{event}:{today}')
            pipe.expire(f'cv:{module}:{event}:{today}', TTL_DAILY)
            if uid:
                pipe.pfadd(f'ucv:{module}:{event}:{today}', uid)
                pipe.expire(f'ucv:{module}:{event}:{today}', TTL_DAILY)
            pipe.execute()
        except Exception as exc:
            logger.debug('AnalyticsService.track_conversion: %s', exc)

    @classmethod
    def get_realtime_stats(cls, module: str, date: Optional[str] = None) -> dict:
        empty = {'views_today': 0, 'unique_users_today': 0, 'views_this_hour': 0}
        module = cls._validate_module(module)
        if not module:
            return empty
        r = _get_redis()
        if not r:
            return empty
        try:
            now = datetime.now(timezone.utc)
            date = date or now.strftime('%Y%m%d')
            hour_str = now.strftime('%Y%m%d%H')
            return {
                'views_today': int(r.get(f'pv:d:{module}:{date}') or 0),
                'views_this_hour': int(r.get(f'pv:h:{module}:{hour_str}') or 0),
                'unique_users_today': r.pfcount(f'uu:{module}:{date}'),
            }
        except Exception:
            return empty

    @classmethod
    def _is_enabled(cls) -> bool:
        try:
            return current_app.config.get('ANALYTICS_ENABLED', True)
        except RuntimeError:
            return False

    @classmethod
    def _validate_module(cls, module: str) -> Optional[str]:
        m = module.lower().strip()
        if m not in KNOWN_MODULES:
            logger.warning("AnalyticsService: unknown module '%s' ignored.", module)
            return None
        return m

    @classmethod
    def _resolve_uid(cls, explicit: Optional[int]) -> Optional[int]:
        if explicit is not None:
            return explicit
        try:
            if has_request_context() and current_user.is_authenticated:
                return current_user.id
        except Exception:
            pass
        return None


def track_view(module: str):
    """Decorator: automatically tracks page view for a route."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            AnalyticsService.track_page_view(module)
            return f(*args, **kwargs)
        return wrapper
    return decorator
```

---

## PART 6 — DATABASE MIGRATION (new file)

### File to create: `migrations/versions/afcon360_analytics_001.py`

```python
"""Add analytics_page_views aggregate table

Revision ID: afcon360_analytics_001
Revises: <replace with current alembic head — run: flask db heads>
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = 'afcon360_analytics_001'
down_revision = None  # ← REPLACE with your current head before running

def upgrade():
    op.create_table(
        'analytics_page_views',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('module', sa.String(50), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_type', sa.String(10), nullable=False),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unique_users', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_apv_module_period', 'analytics_page_views',
                    ['module', 'period_start', 'period_type'])
    op.create_index('ix_apv_period_start', 'analytics_page_views', ['period_start'])
    op.create_unique_constraint('uq_apv_module_period', 'analytics_page_views',
                                ['module', 'period_start', 'period_type'])

def downgrade():
    op.drop_constraint('uq_apv_module_period', 'analytics_page_views', type_='unique')
    op.drop_index('ix_apv_period_start', table_name='analytics_page_views')
    op.drop_index('ix_apv_module_period', table_name='analytics_page_views')
    op.drop_table('analytics_page_views')
```

---

## PART 7 — CONFIG ADDITIONS

### File to modify: `app/config.py`

Add these settings if they do not already exist:

```python
# ── Analytics ──────────────────────────────────────────────
ANALYTICS_ENABLED    = True
REDIS_HOST           = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT           = int(os.environ.get('REDIS_PORT', 6379))
REDIS_ANALYTICS_DB   = int(os.environ.get('REDIS_ANALYTICS_DB', 1))
# Use DB 1 for analytics so it doesn't share with session/cache on DB 0
```

---

## PART 8 — ACCOMMODATION BUG (separate issue, same session)

### Problem confirmed from error log

```
BuildError: Could not build url for endpoint 'accommodation.guest.detail'
Did you mean 'accommodation.guest_detail' instead?
```

**FILE:** `templates/accommodation/guest/search.html` line 88

**FIND:**
```html
<a href="{{ url_for('accommodation.guest.detail', identifier=property.slug or property.id) }}"
```

**REPLACE WITH:**
```html
<a href="{{ url_for('accommodation.guest_detail', identifier=property.slug or property.id) }}"
```

Also check line where `accommodation.guest.search` is referenced (the
error log shows `safe_url: endpoint 'accommodation.guest.search' not found`):

**FIND any occurrence of:**
```
'accommodation.guest.search'
```
**REPLACE WITH:**
```
'accommodation.guest_search'
```

Search the entire templates directory for `accommodation.guest.` (with
trailing dot) and replace the dot-notation with underscore-notation for
all accommodation guest endpoints.

---

## PART 9 — COMPLETE CHANGE SUMMARY FOR AIDER

Aider should process files in this order to avoid dependency issues:

### Step 1 — Create new service (no dependencies on existing code)
- CREATE `app/services/analytics.py` (full content in Part 5)

### Step 2 — Fix tourism (simplest change, stops the hard 500)
- MODIFY `app/tourism/routes.py`
  - Remove `ForensicAuditService.log_attempt(entity_id=None)` from `home()`
  - Add `AnalyticsService.track_page_view("tourism")` in `home()`
  - Keep everything else exactly as-is

### Step 3 — Fix wallet routes
- MODIFY `app/wallet/routes.py`
  - Replace `home()` — remove @login_required, add decision tree (Part 3.1)
  - Replace `wallet_home()` — remove @login_required, add auth redirect (Part 3.2)
  - In `wallet_dashboard()` — remove broken audit log block (Part 3.3)
  - In `wallet_dashboard()` — add analytics call at top (Part 3.3)
  - In `wallet_dashboard()` — add legitimate audit call after account query (Part 3.3)
  - Fix `wallet_activate()` GET — pass action='verify' and wallet= (Part 3.4)
  - Fix `wallet_activate_submit()` POST — CSRF + re-activation guard (Part 3.5)
  - Fix `agent_payout_history()` — use @require_payout_access (Part 3.6)

### Step 4 — Fix wallet middleware
- MODIFY `app/wallet/middleware/wallet_check.py`
  - Fix `redirect_to` parameter usage (Part 3.7)

### Step 5 — Fix templates
- MODIFY `templates/wallet/wallet_activate.html`
  - Fix `csrf_token` → `csrf_token()` in activation form (Issue 8)
  - Verify `accept_terms` checkbox exists in both form branches (Issue 9)
- MODIFY `templates/wallet/wallet_dashboard.html`
  - Add `{% elif not wallet_activated %}` branch (Part 4.4)
- MODIFY `templates/wallet/base_wallet.html`
  - Add `requires_terms_acceptance` banner (Part 4.5)
- MODIFY `templates/accommodation/guest/search.html`
  - Fix endpoint dot-notation to underscore (Part 8)
- ADD retirement comment to `templates/wallet/original_file.html` (Part 4.2)

### Step 6 — Add config
- MODIFY `app/config.py`
  - Add analytics config block (Part 7)

### Step 7 — Add migration
- CREATE `migrations/versions/afcon360_analytics_001.py` (Part 6)
  - Remember to set `down_revision` to current alembic head before running

---

## PART 10 — VERIFICATION CHECKLIST

After implementation, verify each item manually:

### Tourism
- [ ] `GET /tourism/` returns 200 (was 500)
- [ ] No `🔴 ID SYSTEM VIOLATION` in log when visiting `/tourism/`
- [ ] `GET /tourism/detail/<slug>` still returns 200 and audit log entry exists
- [ ] `GET /tourism/moderate` still returns 200 and security audit log entry exists

### Wallet — unauthenticated user
- [ ] `GET /wallet/` renders `wallet_home.html` (marketing page, no redirect to login)
- [ ] `GET /wallet/home` renders `wallet_home.html`
- [ ] `GET /wallet/dashboard` redirects to login (still protected)

### Wallet — authenticated user, no wallet
- [ ] `GET /wallet/` redirects to `/wallet/dashboard`
- [ ] `/wallet/dashboard` shows "Create Wallet" CTA (no_wallet=True)
- [ ] No `🔴 ID SYSTEM VIOLATION` in log
- [ ] No `SYSTEM_ERROR` entry in audit log

### Wallet — authenticated user, wallet exists but not activated
- [ ] `GET /wallet/` redirects to `/wallet/activate`
- [ ] `/wallet/activate` renders correctly with `action='verify'`
- [ ] Activation form shows terms checkbox
- [ ] Activation form POST validates CSRF
- [ ] Submitting activation form twice gives "already activated" message

### Wallet — authenticated user, active wallet
- [ ] `GET /wallet/` redirects to `/wallet/dashboard`
- [ ] `/wallet/home` redirects to `/wallet/dashboard` (no marketing page for active users)
- [ ] `/wallet/dashboard` shows full balance/transaction data
- [ ] Audit log entry created with real `wallet.public_id` as entity_id
- [ ] Sidebar shows correct menu items based on KYC tier

### Accommodation
- [ ] `GET /accommodation/guest/` returns 200 (was 500)
- [ ] Property links in search results work without BuildError

### Analytics
- [ ] No errors if Redis is not running (silent fail)
- [ ] `flask analytics stats wallet` shows view counts after visiting dashboard
- [ ] `flask analytics stats tourism` shows view counts after visiting tourism home

---

## PART 11 — WHAT NOT TO CHANGE

Aider must NOT touch these:

- `app/audit/forensic_audit.py` — do not modify the audit service itself
- `app/utils/id_guard.py` — IDGuard is working correctly, it caught the real bugs
- `app/wallet/models.py` — wallet models are correct
- `app/audit/comprehensive_audit.py` — audit models are correct
- `app/wallet/services/wallet_status_service.py` — only modify if needed
  to expose `is_activated` and `has_wallet` properties (check if they
  already exist before adding)
- Any existing audit log call where `entity_id` is a real non-None value
- The `detail()`, `moderate()`, `moderate_action()`, `flag_listing()`
  functions in `app/tourism/routes.py` — these are correct as-is
- `templates/wallet/base_wallet.html` CSS and sidebar structure — only
  add the banner logic described in Part 4.5, nothing else

---

*Guide written: 2026-06-01*
*Covers: wallet routing, tourism 500 fix, audit log violations,*
*analytics service, 9 documented wallet issues, accommodation endpoint bug*
*Platform: AFCON360 — Flask/SQLAlchemy/Redis/PostgreSQL*