# Module Isolation Audit Report

**Date:** May 14, 2026  
**Purpose:** Analyze existing codebase for module isolation patterns before implementing robust module isolation

## Existing Functions Analysis

### 1. Safe URL Functions
**Status:** NOT FOUND
- No existing `safe_url` function found in codebase
- No existing context processors with `@app.context_processor` that provide URL safety
- Templates directly use `url_for()` which will crash if endpoints don't exist

### 2. Module Guard Functions
**Status:** PARTIALLY EXISTING
- Found `app/utils/module_switch.py` with `module_enabled_required()` decorator
- Found `check_module_enabled()` function that safely returns True/False
- **Gap:** No `module_enabled()` function that works outside app context
- **Gap:** No safe import utilities

### 3. Widget Loading Patterns
**Status:** NOT FOUND
- No existing `get_wallet_widget` or similar patterns
- Fan dashboard directly imports and calls services without safety checks
- Wallet service calls are not wrapped in try/catch blocks

## Current Module Registration Pattern

### App Factory Analysis (`app/__init__.py`)
**Current Pattern:** Mixed approach - some conditional, some unconditional

**Conditional Registration:**
```python
# These are conditionally registered based on config flags
if app.config.get("TOURNAMENT_ENABLED", True):
    app.register_blueprint(tournament_bp)

if app.config.get("TOURISM_ENABLED", True):
    app.register_blueprint(tourism_bp)

if app.config.get("TRANSPORT_ENABLED", True):
    # Transport module initialization
    init_transport_module(app)
    app.register_blueprint(transport_bp, url_prefix='/transport')
    app.register_blueprint(transport_admin_bp, url_prefix='/transport/admin')

if app.config.get("ACCOMMODATION_ENABLED", True):
    app.register_blueprint(accommodation_bp)
```

**Unconditional Registration:**
```python
# These are always registered regardless of MODULE_FLAGS
from app.wallet.routes import wallet_bp
app.register_blueprint(wallet_bp)  # Always registered!
```

**Problem:** Wallet module is always registered even though it has MODULE_FLAGS entry

## Template URL Patterns Analysis

### High-Risk Templates (Direct Module URLs)
These templates will crash if modules are disabled:

**base.html:**
- `{{ url_for('wallet.wallet_dashboard') }}` (multiple instances)
- `{{ url_for('events.list') }}`
- `{{ url_for('events.create_event') }}`
- `{{ url_for('events.my_events') }}`
- `{{ url_for('events.my_registrations') }}`
- `{{ url_for('events.events_hub') }}`

**accommodation templates:**
- `{{ url_for('accommodation.detail') }}`
- `{{ url_for('accommodation.admin.moderate') }}`
- `{{ url_for('accommodation.guest.search') }}`

**wallet templates:**
- Multiple wallet URL references throughout

**Safe Templates (Core System):**
- `auth.*` endpoints - safe (core authentication)
- `profile.*` endpoints - safe (core user management)
- `admin.owner.*` endpoints - safe (core admin)
- `fan.dashboard` - safe (core dashboard)
- `index` - safe (homepage)

## Module Flags Configuration

### Current MODULE_FLAGS (from config.py)
```python
MODULE_FLAGS = {
    "wallet": os.getenv("ENABLE_WALLET", "true").lower() == "true",
    "tourism": os.getenv("ENABLE_TOURISM", "true").lower() == "true",
    "transport": os.getenv("ENABLE_TRANSPORT", "true").lower() == "true",
    "accommodation": os.getenv("ENABLE_ACCOMMODATION", "true").lower() == "true",
    "tournament": os.getenv("ENABLE_TOURNAMENT", "true").lower() == "true",
    "agents": os.getenv("ENABLE_AGENTS", "false").lower() == "true",
    "admin": os.getenv("ENABLE_ADMIN", "true").lower() == "true",
}
```

### Database Override System
- **Found:** `ModuleToggleService` in `app/services/module_toggle_service.py`
- **Functionality:** Loads database overrides into app config after DB initialization
- **Status:** Working correctly

## Blueprint Registration Issues

### Critical Issues Found:

1. **Wallet module inconsistency:**
   - Has MODULE_FLAGS entry but always registered
   - Should be conditionally registered like other modules

2. **Events module:**
   - Has try/catch for import but always registered if import succeeds
   - No MODULE_FLAGS check

3. **Tourism/Transport/Accommodation:**
   - Properly conditional based on individual config flags
   - **Problem:** Uses separate config flags instead of unified MODULE_FLAGS

## Existing Context Processors

### Found Context Processors in `app/__init__.py`:
1. `inject_impersonation_status()` - handles user impersonation
2. `inject_user_role_info()` - provides role information
3. `inject_sitewide()` - provides site-wide variables

**Gap:** No context processor for safe URL generation or module status

## Security & Stability Risks

### High Risk Issues:
1. **Template crashes:** Direct `url_for()` calls to disabled modules will cause 500 errors
2. **Import failures:** No safe import utilities for optional modules
3. **Service calls:** Fan dashboard directly calls wallet services without safety checks
4. **Inconsistent registration:** Some modules ignore MODULE_FLAGS entirely

### Medium Risk Issues:
1. **Navigation links:** Disabled modules still appear in navigation
2. **Dashboard widgets:** Will fail if underlying services are unavailable
3. **Admin interface:** May show options for disabled modules

## Recommendations

### Phase 1: Core Utilities (REQUIRED)
1. Create `app/utils/module_guard.py` with:
   - `safe_url()` function for template use
   - `module_enabled()` function safe outside app context
   - `safe_import()` utility function

2. Create `app/utils/template_helpers.py` with:
   - Context processor to inject safe_url and module_enabled
   - Register in app factory

### Phase 2: Fix Registration Issues
1. Update wallet module to be conditionally registered
2. Update events module to check MODULE_FLAGS
3. Unify all module checks to use MODULE_FLAGS instead of separate config flags

### Phase 3: Template Safety
1. Replace all module URL calls with safe_url()
2. Add conditional checks around module-specific navigation
3. Update dashboard templates to handle disabled modules gracefully

### Phase 4: Service Safety
1. Create widget loader system for dashboard components
2. Wrap all service calls in try/catch blocks
3. Provide fallback data for disabled modules

## Implementation Priority

**P0 (Critical):** Core utilities (safe_url, module_enabled)
**P1 (High):** Fix blueprint registration inconsistencies  
**P2 (Medium):** Template URL safety updates
**P3 (Low):** Widget system implementation

## Testing Strategy

1. Set all MODULE_FLAGS to False - app should run without crashes
2. Enable modules one by one - verify functionality
3. Test with mixed enabled/disabled modules
4. Verify database overrides work correctly

---

**Conclusion:** The codebase has partial module isolation infrastructure but critical gaps exist that will cause crashes when modules are disabled. Implementation of the recommended utilities is required before any module disabling can be safely performed.
