# Performance Fixes — AFCON 360
**Date:** May 15, 2026  
**Scope:** Startup time & per-request latency (every page click)

---

## The Problem in Plain Terms

Every time any user clicked any menu item or loaded any page, the server was
running **15–20 database queries before even starting to build the HTML**.
This happened because Flask **context processors** run on every single request,
and several of them were doing heavy DB work with no caching.

Separately, every time the server **booted**, it was making 3 database
connections synchronously — blocking the startup sequence until those queries
completed.

---

## Root Cause 1 — Per-Request DB Overload (Every Click)

### What context processors are
Flask injects them into **every template render** on every request.
If a context processor queries the DB, that cost is paid on every page load
for every user.

### The offenders

| Context Processor | DB Queries / Request | What it was doing |
|---|---|---|
| `inject_feature_flags` | 1 | Called `ModuleToggleService.get_flags()` → `SystemSetting` DB query, even though the data was already in `app.config` |
| `inject_links` | 1 | Called `ModuleToggleService.get_flags()` again (2nd identical DB hit same request) |
| `inject_kyc_data` | **9+** | Called `calculate_kyc_tier()` (User + Profile + Verification = 3 queries) then separately called `get_user_limits()` which internally re-ran `calculate_kyc_tier` (3 more) + AccountModel + Transaction sum = 9+ queries, on **every page** |
| `inject_audit_summary` | 1 | Queried `DataChangeLog` for 7 days of records on every request — result was only ever used by one single component (`audit_timeline.html`) |
| `inject_sitewide` | 1 | Called `get_profile_by_user()` — 1st of 3 times per request |
| `inject_user_context` | 3+ | Called `get_profile_by_user()` again (3rd time same request), ran a **broken** `User.query.filter_by(public_id=<BIGINT>)` that always returned `None` (UUID ≠ BIGINT — pure wasted query), then called `WalletService.get_balance()` |
| `inject_wallet_status` | 1 | `WalletRepository.get_by_user_id()` on every page |
| `WalletStatusService` | 3–4 | `get_sidebar_items()`, `get_action_buttons()`, `get_wallet_banner()` each called `get_wallet_status()` separately — 3 independent `AccountModel` queries for the same data |

**Total: 15–20+ DB queries per page render, for every user, on every click.**

---

## Root Cause 2 — Startup Blocks on DB Queries

Before serving a single request, `create_app()` was running:

```
1. ModuleToggleService.load_overrides_into_app()   ← DB query (SystemSetting)
2. inspect(db.engine).get_columns('users')          ← DB schema inspection
3. inspect(db.engine).get_indexes('transactions')   ← DB index scan (slowest)
```

All three inside `with app.app_context()` blocks — synchronous, blocking,
happening before the server was ready to accept connections.

---

## Root Cause 3 — Disabled Modules Still Imported at Boot

Four feature modules were imported at Python level during startup **regardless
of whether they were enabled**:

```python
# These ran unconditionally at startup:
from app.tournament import tournament_bp
from app.tourism    import tourism_bp
from app.transport  import transport_bp, transport_admin_bp
from app.accommodation import accommodation_bp
```

Python parses and executes every file in those packages (models, services,
forms, helpers) even when the module was disabled via `MODULE_FLAGS`. Wasted
import time and memory.

---

## Fixes Applied

### Fix 1 — Context Processors: Stop Double-Querying Module Flags

**File:** `app/__init__.py`

`inject_feature_flags` and `inject_links` both called `ModuleToggleService.get_flags()`
which hit the database. The flags were **already loaded into `app.config`** at
startup via `load_overrides_into_app()`. Changed both to read directly:

```python
# Before (DB hit):
modules = ModuleToggleService.get_flags()

# After (zero DB):
modules = current_app.config.get("MODULE_FLAGS", {})
```

**Saved: 2 DB queries per request.**

---

### Fix 2 — Per-Request Profile Cache (`flask.g`)

**File:** `app/__init__.py`

`get_profile_by_user()` was called independently in `inject_sitewide`,
`inject_kyc_data`, and `inject_user_context` — three separate DB queries for
the same row in the same request.

Added a `flask.g` cache so the profile is fetched once and reused:

```python
if not hasattr(_g, '_req_profiles'):
    _g._req_profiles = {}
if _pk not in _g._req_profiles:
    _g._req_profiles[_pk] = get_profile_by_user(public_id)
profile = _g._req_profiles[_pk]
```

`flask.g` lives only for the duration of one request — safe, no stale data.

**Saved: 2 duplicate profile DB queries per request.**

---

### Fix 3 — Cache KYC Data in Redis (5-Minute TTL)

**File:** `app/__init__.py`

`inject_kyc_data` was doing 9+ DB queries **on every page** because:
- `calculate_kyc_tier()` = 3 queries
- `get_user_limits()` internally calls `calculate_kyc_tier()` again = 3 more + Account + Transactions

KYC tier does not change every few seconds. Cached the full result per user:

```python
_cache_key = f'kyc_ctx_{current_user.id}'
_cached = cache.get(_cache_key)
if _cached is not None:
    return _cached          # zero DB hit
# ... compute ...
cache.set(_cache_key, result, timeout=300)   # 5-minute TTL
```

**Saved: 9+ DB queries per request on cache-warm loads.**

---

### Fix 4 — Cache Audit Summary in Redis (60-Second TTL)

**File:** `app/__init__.py`

`inject_audit_summary` ran a `DataChangeLog` date-range query (7 days of records)
on **every request** — but the result was only ever displayed in one single
template component. Cached per user with a 60-second TTL:

```python
_cache_key = f'audit_summary_{current_user.public_id}'
_cached = cache.get(_cache_key)
if _cached is not None:
    return {'audit_summary': _cached}
# ... query ...
cache.set(_cache_key, result, timeout=60)
```

**Saved: 1 expensive range query per request on cache-warm loads.**

---

### Fix 5 — Remove Broken User Query + Cache Wallet Balance

**File:** `app/__init__.py`

`inject_user_context` contained a bug: it ran `User.query.filter_by(public_id=current_user.id)` where `current_user.id` is a **BIGINT** but `public_id` is a **UUID** — the query always returned `None`. It was a wasted round-trip to the DB on every authenticated request.

Also added 30-second Redis cache for wallet balance:

```python
# Removed entirely (always returned None):
user = User.query.filter_by(public_id=str(current_user.id)).first()

# Wallet balance now cached:
_wb_key = f'wallet_balance_{current_user.id}'
_wb_cached = cache.get(_wb_key)
if _wb_cached is None:
    balance_data = WalletService().get_balance(current_user.id)
    cache.set(_wb_key, ..., timeout=30)
```

**Saved: 2 DB queries per request (broken query + uncached balance).**

---

### Fix 6 — Per-Request Wallet Status Cache (`flask.g`)

**File:** `app/wallet/services/wallet_status_service.py`

`get_sidebar_items()`, `get_action_buttons()`, and `get_wallet_banner()` each
independently called `get_wallet_status()` which queries `AccountModel`.
On a wallet page, this was 3–4 separate identical DB queries.

Added `flask.g` caching inside `get_wallet_status()` itself:

```python
_g_key = f'_wallet_status_{user.id}_{owner_type}'
if _g_key in _g._wallet_status_cache:
    return _g._wallet_status_cache[_g_key]   # reuse
# ... query ...
_g_cache[_g_key] = _result   # store for rest of request
```

**Saved: 2–3 duplicate AccountModel queries per wallet page.**

---

### Fix 7 — Deferred Startup (First-Request Handler)

**File:** `app/__init__.py`

Moved all DB-touching startup operations out of `create_app()` into a
`before_request` handler that runs **exactly once** on the first real request,
using a `threading.Event + Lock` for thread safety:

```python
_deferred_done = threading.Event()
_deferred_lock = threading.Lock()

@app.before_request
def _run_deferred_startup():
    if _deferred_done.is_set():
        return                  # fast path for all subsequent requests
    with _deferred_lock:
        if _deferred_done.is_set():
            return
        _deferred_done.set()
        ModuleToggleService.load_overrides_into_app()   # DB
        # ... DB schema validation ...
```

**Removed from startup critical path:**
- `ModuleToggleService.load_overrides_into_app()` — `SystemSetting` query
- `inspect(db.engine).get_columns('users')` — schema inspection
- `inspect(db.engine).get_indexes('transactions')` — index scan

**Impact: Server is ready to accept connections faster. First request pays the cost instead of blocking boot.**

---

### Fix 8 — Lazy Feature Module Imports

**File:** `app/__init__.py`

Tournament, tourism, transport, and accommodation blueprints were imported
unconditionally at startup, loading all their models/services/forms:

```python
# Before — always imported regardless of MODULE_FLAGS:
from app.tournament    import tournament_bp
from app.tourism       import tourism_bp
from app.transport     import transport_bp, transport_admin_bp
from app.accommodation import accommodation_bp
```

Moved each import inside its flag-conditional block:

```python
# After — only imported if the module is enabled:
if module_config.get('tournament', False):
    from app.tournament import tournament_bp
    app.register_blueprint(tournament_bp)
```

**Impact: Disabled modules load zero Python files. Enabled-only modules load their code. Startup import time scales with what's actually used.**

---

### Fix 9 — DB Connection Pool

**File:** `app/config.py`

`SQLALCHEMY_ENGINE_OPTIONS` only had `isolation_level`. Added proper pooling
so SQLAlchemy reuses connections across requests instead of opening new ones:

```python
SQLALCHEMY_ENGINE_OPTIONS = {
    "isolation_level": "REPEATABLE_READ",
    "pool_size":    5,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800,
    "pool_pre_ping": True,   # drops stale connections before reuse
}
```

---

## Summary

| Area | Before | After |
|---|---|---|
| DB queries per page (authenticated) | 15–20+ | 1–3 on cache-warm |
| KYC queries per page | 9+ | 0 (5-min cache) |
| Profile queries per request | 3× same row | 1× cached in `g` |
| Wallet status queries per wallet page | 3–4 | 1× cached in `g` |
| Startup DB queries | 3 blocking queries | 0 at boot (deferred) |
| Disabled module imports | Always loaded | Never loaded |
| Module flag source | DB query every request | `app.config` in-memory |

### Cache TTLs at a glance

| Data | TTL | Why |
|---|---|---|
| KYC tier + limits | 5 minutes | Changes only on verification approval |
| Audit summary | 60 seconds | Near-real-time but not instant |
| Wallet balance | 30 seconds | Frequent enough reads, infrequent writes |
| Profile (per request) | Request lifetime (`g`) | Safe; new request = fresh fetch |
| Wallet status (per request) | Request lifetime (`g`) | Safe; new request = fresh fetch |
