# Plan: Fix SystemSetting Import Error in Admin Module

## Root Cause

The `SystemSetting` class was removed from `app/admin/owner/models.py` and merged into `SystemConfig` (`app/models/system_config.py`). Multiple files still try to import or reference `SystemSetting`, causing `ImportError` on `/admin/super` and breaking property moderation and other admin features.

## Evidence

- `class SystemSetting` no longer exists anywhere in the codebase (`grep` returns 0 matches).
- `SystemConfig` (`app/models/system_config.py`) already provides the same `.get()` and `.set()` API.
- Some newer modules already correctly use `SystemConfig`; the broken references are concentrated in admin owner/security routes.

## Files to Modify

### 1. `app/admin/routes.py`
- **Line 170:** replace `from app.admin.owner.models import SystemSetting` with `from app.models.system_config import SystemConfig as SystemSetting`
- **Line 1073:** same replacement

### 2. `app/admin/owner/routes.py`
- **Line 810:** update comment `SystemSetting` → `SystemConfig`
- **Line 932:** replace deferred import with `from app.models.system_config import SystemConfig as SystemSetting`
- **Line 1144:** same replacement
- **Line 1162:** same replacement
- **Line 1191:** same replacement
- **Line 1221:** same replacement

### 3. `app/admin/owner/security_service.py`
- **Line 12:** change existing `from app.models.system_config import SystemConfig` to `from app.models.system_config import SystemConfig as SystemSetting`
- This makes line 158 (`SystemSetting.query.filter_by`) work again without touching working `SystemConfig` references on lines 38, 91, 94.

### 4. `app/admin/owner/security_routes.py`
- **Line 13:** change existing `from app.models.system_config import SystemConfig` to `from app.models.system_config import SystemConfig as SystemSetting`
- This fixes all `SystemSetting` usages on lines 118, 140, 158, 176, 195, 204, 230.

### 5. `app/services/module_toggle_service.py`
- **Line 21:** update docstring comment from `SystemSetting` to `SystemConfig` for consistency.

## Fix Strategy

Use `SystemConfig as SystemSetting` aliases wherever these files already import `SystemConfig` at the top, and replace deferred broken imports with new deferred aliased imports. This minimizes diff size and maintains backward compatibility for any other internal references.

## Migration Needed

No. The `system_configs` table and `SystemConfig` model are already in place; data migration has already occurred.

## Verification

1. Start Flask app and load `/admin/super` — should render without `ImportError`.
2. Test owner security dashboard routes (`/owner/security-dashboard`, `/danger-zone`, `/toggle-global-maintenance`, `/toggle-lockdown`).
3. Test module toggle route (`/admin/toggle/<module>`).
4. Run `pytest` for admin tests if available.

## Risks

- **Low risk.** `SystemConfig.get()` and `SystemConfig.set()` have identical signatures to the old `SystemSetting`, so aliasing is behaviorally safe.
- No circular imports are introduced; `app.models.system_config` is already widely used.
