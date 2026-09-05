# EXECUTIVE SUMMARY: DetachedInstanceError Root Cause

## One-Sentence Answer
**The user_loader's Redis cache hit path uses `db.session.get(User, id)` to retrieve a User instance that was loaded in a previous HTTP request's SQLAlchemy session and then detached when that session was removed.**

---

## The Problem in 30 Seconds

```python
# Request 1 ends:
@app.teardown_request
def handle_transaction(exception=None):
    db.session.remove()  # ← Detaches all User instances

# Request 2 starts:
@login_manager.user_loader
def load_user(public_id):
    _cached = cache.get(f"user:{public_id}")  # Redis hit from Request 1
    if _cached is not None:
        user = db.session.get(User, _cached['id'])  # ← DETACHED INSTANCE
        return user  # User is still marked as detached

# Later in the request:
current_user.is_authenticated  # Accesses .is_active
# SQLAlchemy detects detached object → DetachedInstanceError
```

---

## Three Paths Through user_loader

### ✅ Safe: Per-Request Cache (g._cached_user)
- Fresh every request
- Never detached

### ❌ Broken: Redis Cache + db.session.get()
- Redis stores User ID from Request 1
- Request 2 calls db.session.get(User, id)
- Returns SAME User object from Request 1 (still detached)
- **DetachedInstanceError** when accessing attributes

### ✅ Safe: Full DB Query
- Queries fresh with joinedload
- Properly bound to current session

---

## Smoking Gun: Test Workaround

The test file `tests/test_onboarding_stage4.py` has a documented workaround:

```python
def _fresh_get(client, url, **kwargs):
    """The user_loader Redis cache returns a user ID, then db.session.get()
    returns a detached instance from a previous request's session scope.
    Clearing the cache forces the full DB query path which returns a
    properly-bound instance."""
    from app.extensions import cache
    cache.clear()  # WORKAROUND
    return client.get(url, **kwargs)
```

**The test author documented the exact problem we're diagnosing.** They work around it by clearing the entire cache before every HTTP request to force the safe path.

---

## Session Lifecycle Evidence

**Request 1:**
```
Start      → new app_context + db.session
Load User  → Path C (full query) → User bound to Request1 Session
End Request → teardown_request → db.session.remove()
           → User DETACHED, Redis cache has {id: 42}
```

**Request 2:**
```
Start      → new app_context + new db.session (isolated scope)
Load User  → Path B (cache hit) → db.session.get(User, 42)
           → Same User object from Request 1 (DETACHED)
Access .is_active → DetachedInstanceError ❌
```

---

## Root Cause Identified In

| File | Lines | Issue |
|------|-------|-------|
| `app/__init__.py` | 1767 | `db.session.get(User, _cached['id'])` on detached instance |
| `app/__init__.py` | 794 | `db.session.remove()` detaches all User instances |
| `tests/test_onboarding_stage4.py` | 167-169 | Test comment confirms diagnosis |

---

## Minimal Correct Fix (app/__init__.py, lines 1763-1774)

Replace:
```python
user = db.session.get(User, _cached['id'])  # ❌ Detached instance
```

With:
```python
user = (
    db.session.query(User)
    .options(joinedload(User.roles))
    .filter_by(public_id=_cached['public_id'])
    .first()
)  # ✅ Fresh query, properly bound
```

**Why:** Query fresh from DB using cached public_id (scalar, always safe) instead of trying to retrieve a detached User object.

---

## Impact Classification

| Category | Finding |
|----------|---------|
| **Production Bug** | YES — occurs when user makes 2+ requests in same session |
| **Only in Tests** | NO — happens whenever Redis cache is warm and user makes sequential requests |
| **Cache Problem** | NO — Redis data is correct; the issue is how it's used |
| **Session Scoping Problem** | YES — root cause is detachment across request boundaries |
| **User Loader Problem** | YES — Path B implementation is broken |
| **Test Fixture Problem** | NO — fixtures are correctly scoped |
| **Flask-Login Problem** | NO — authentication mechanism is correct |

---

## Verification

To confirm the diagnosis, the test should:

1. **Without fix:** Make 2 sequential HTTP requests without `cache.clear()`
   - Request 1 succeeds
   - Request 2 fails with DetachedInstanceError on attribute access
   - Evidence: Test currently calls `cache.clear()` before every request

2. **With fix:** Same test, replace Path B with fresh query
   - Request 1 succeeds
   - Request 2 succeeds (fresh User query, no detachment)
   - cache.clear() workaround no longer needed

---

## Next Steps (NOT Included in This Report)

This is a READ-ONLY diagnosis. To implement the fix:

1. Replace `db.session.get()` with fresh `db.session.query()` in Path B
2. Remove `cache.clear()` workarounds from tests
3. Verify E2E test passes without cache.clear()
4. Run full test suite
5. Deploy

---

**DIAGNOSIS COMPLETE. READY FOR FIX IMPLEMENTATION.**
