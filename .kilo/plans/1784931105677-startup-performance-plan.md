# Startup Performance Optimization Plan

## Root Cause Analysis

Based on timing analysis of app factory logs:

| Timestamp | Event | Delta |
|-----------|-------|-------|
| 01:05:03,927 | Owner blueprint registered | 0s |
| 01:05:04,983 | Mail extension initialized | ~1.05s |
| 01:05:07,281 | Events signal handlers connected | ~2.3s |
| 01:05:07,337 | Media admin blueprint | ~0.05s |

**Total app factory: 6.68s**

### Primary Culprits

1. **`pandas` imported at module level in `app/events/bulk_upload.py` (line 8)**
   - `pandas` is ~100MB+ and takes 1-2 seconds to import
   - Triggered by `from app.events.bulk_upload import bulk_bp` in `events/__init__.py`
   - **Estimated impact: ~1.5-2s**

2. **`app/events/__init__.py` eager imports cascade**
   - `routes` (2513 lines) → imports models, services, constants
   - `services` (1869 lines) → imports models, trust_service, attendee_accounts
   - `payment_config`, `settings_model`, `settings_routes`
   - All happen when `events_bp` is first imported
   - **Estimated impact: ~0.5-1s**

3. **Redundant signal handlers import in `app/__init__.py` (line 1005-1006)**
   - `connect_event_signal_handlers()` is already called via `events_bp.record_once`
   - Explicit re-import and call is unnecessary
   - **Impact: minor, but adds confusion**

4. **Mail extension initialization (~1s)**
   - `mail.init_app(app)` at line 565
   - Possible template scanning overhead with custom `EncodingSafeLoader`
   - **Needs investigation**

## Implementation Plan

### Fix 1: Lazy-load `pandas` in `bulk_upload.py` (HIGH IMPACT)

**File:** `app/events/bulk_upload.py`

**Change:** Move `import pandas as pd` inside the `upload_bulk()` function where it's actually used.

**Before:**
```python
import pandas as pd
...
@bulk_bp.route('/<identifier>/upload', methods=['POST'])
def upload_bulk(identifier):
    ...
    df = pd.read_excel(file)
```

**After:**
```python
@bulk_bp.route('/<identifier>/upload', methods=['POST'])
def upload_bulk(identifier):
    import pandas as pd
    ...
    df = pd.read_excel(file)
```

**Why:** pandas is only used in the upload endpoint. Moving the import inside the function defers it until the endpoint is actually called, saving ~1.5-2s at startup.

---

### Fix 2: Make `events/__init__.py` lazy-load heavy imports (HIGH IMPACT)

**File:** `app/events/__init__.py`

**Change:** Defer routes, services, and other heavy imports to `record_once` or remove unnecessary eager imports.

**Current problematic imports:**
```python
from app.events import routes                    # 2513 lines
from app.events import routes_community_hosts
from app.events.services import EventService     # 1869 lines
from app.events.settings_model import EventSettings
from app.events import payment_config
```

**Strategy:**
- `routes` and `routes_community_hosts` MUST be imported before `register_blueprint` for route decorators to work
- `EventService`, `EventSettings`, `payment_config` can be imported lazily where used
- Move non-critical imports into functions or remove if not needed at module level

**Specific changes:**
1. Keep `from app.events import routes` and `from app.events import routes_community_hosts` — these are needed for Flask route registration
2. Remove `from app.events.services import EventService` — import inside functions that use it
3. Remove `from app.events.settings_model import EventSettings` — import inside functions
4. Remove `from app.events import payment_config` — import inside functions
5. Move `from app.events.bulk_upload import bulk_bp` to after the heavy imports, or make it lazy

---

### Fix 3: Remove redundant signal handlers import in `app/__init__.py` (LOW IMPACT)

**File:** `app/__init__.py` (lines 1001-1011)

**Current code:**
```python
# ------------------------------------------------------------------
# Initialize Event Signal Handlers
# ------------------------------------------------------------------
try:
    from app.events.signal_handlers import connect_event_signal_handlers
    connect_event_signal_handlers()
    logger.info("✅ Event signal handlers connected")
except ImportError:
    logger.warning("Event signal handlers not found – skipping")
except Exception as e:
    logger.error(f"Failed to connect event signal handlers: {e}")
```

**Change:** Remove this block entirely. Signal handlers are already connected via `events_bp.record_once` in `app/events/__init__.py` (lines 33-41).

---

### Fix 4: Investigate mail extension delay (MEDIUM IMPACT)

**File:** `app/__init__.py` (around line 565)

**Current code:**
```python
mail.init_app(app)
logger.info("✅ Mail extension initialized")
```

**Investigation needed:**
1. Check if `mail.init_app(app)` is doing template scanning
2. Check if custom `EncodingSafeLoader` (line 191-226) is scanning all templates during mail init
3. Consider lazy initialization of mail if possible

**Potential fix:** Profile what `mail.init_app` is doing. If it's scanning templates, consider deferring or optimizing.

---

## Expected Results

| Fix | Estimated Time Saved | Risk |
|-----|---------------------|------|
| Lazy pandas import | ~1.5-2.0s | Low |
| Lazy events imports | ~0.3-0.5s | Low |
| Remove redundant signal handlers | ~0s | None |
| Mail investigation | ~0.5-1.0s | Medium |

**Total expected improvement: 2.5-4s reduction** (from 6.68s to ~2.5-4s)

---

## Verification Plan

1. **Before fix:** Run `python -c "from app import create_app; import time; t=time.time(); create_app(); print(f'Startup: {time.time()-t:.2f}s')"` and note timing
2. **After fix:** Run same command and compare
3. **Functional test:** Verify events module still works:
   - Event list loads
   - Event registration works
   - Bulk upload endpoint still works (pandas imported lazily)
   - Signal handlers still fire for capacity release
4. **Import test:** `python -c "from app import create_app; create_app(); print('OK')"` should exit 0

---

## Rollout Order

1. Fix 1 (pandas lazy import) — immediate, highest impact, lowest risk
2. Fix 3 (remove redundant signal handlers) — immediate, zero risk
3. Fix 2 (events lazy imports) — moderate refactor, test carefully
4. Fix 4 (mail investigation) — investigate first, then implement

---

## Migration Needed

**No database migrations needed.** All changes are to Python import statements and module initialization code.

---

## Risks

1. **Circular imports:** Moving imports into functions may expose hidden circular dependencies. Test thoroughly.
2. **Flask route registration:** Routes must be imported before `register_blueprint` for decorators to take effect. Do NOT lazy-load `routes` or `routes_community_hosts`.
3. **Signal handlers:** Ensure `connect_event_signal_handlers()` is still called exactly once. The `record_once` callback in `events/__init__.py` handles this.
4. **pandas availability:** Ensure pandas is still installed and importable when the upload endpoint is called.
