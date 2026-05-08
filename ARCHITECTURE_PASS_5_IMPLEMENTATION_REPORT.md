# AFCON 360 - Architecture Pass 5 Implementation Report

**Date:** 2026-05-06
**Architecture Doc:** `app/Documentation/ARCHITECTURE_PASS_5_FINAL.md`
**Status:** Code implementation **COMPLETE** - Pending manual DB migration/seed steps (Phase 2 table drop + Phase 4 re-seed)

---

## Overview

This report documents the implementation of the "AFCON 360 - Final Architecture Decision" which centralizes fan-related identity data into the `UserProfile` model, deprecates the standalone `FanProfile` table, aligns the `fan` role to `user`, and introduces a tournament skin toggle via `MODULE_FLAGS`.

The work was executed in 6 phases, with all code edits completed and Python syntax verified. A small number of database-level commands remain for the user to run manually to avoid Alembic issues in this environment.

---

## Phase 1 - Database: Add Fields to UserProfile

**Goal:** Add four new nullable columns to `user_profiles` to store fan identity, display name, avatar, and bio.

**Files Modified**
- `app/profile/models.py` - Added columns after `email`:
  - `fan_team` (`String(64)`, nullable, indexed)
  - `display_name` (`String(128)`, nullable)
  - `avatar_url` (`String(512)`, nullable)
  - `bio` (`Text`, nullable)

**Migration**
- User generated migration `a73a4f5c63aa` and ran `flask db upgrade` successfully.
- Verified: `user_profiles` table now contains the 4 new columns.

---

## Phase 2 - Database: Migrate FanProfile Data & Drop Table

**Goal:** Move any existing `fan_profiles` rows into `user_profiles`, then remove the deprecated model/table.

**Files Created**
- `scripts/migrate_fan_profiles.py` - One-time SQL migration script that:
  1. Reads `fan_profiles` rows
  2. Resolves `fan_profiles.user_id` (internal bigint) → `users.public_id` (UUID)
  3. Copies `display_name`, `avatar_url`, `bio` into the matching `user_profiles` row using `COALESCE` to avoid overwriting existing data
  4. Copies `nationality` only if the target field is empty

**Files Modified**
- `app/fan/models.py` - Entire model code replaced with a deprecation placeholder comment. The file is kept empty (except comments) to prevent import errors during transition.

**Pending DB Steps**
- Run data migration if `fan_profiles` has rows: `flask shell < scripts/migrate_fan_profiles.py`
- Generate drop migration: `flask db migrate -m "drop_fan_profiles_table"`
- Verify migration only contains `op.drop_table('fan_profiles')`
- Run `flask db upgrade`

---

## Phase 3 - Code: Remove `get_or_create_fan()` Calls

**Goal:** Eliminate all runtime dependency on `FanProfile` / `get_or_create_fan` and route everything through `UserProfile` (`get_profile_by_user`).

**Files Modified**

| File | Change |
|------|--------|
| `app/fan/routes.py` | `view_fan_profile()` now calls `get_profile_by_user(current_user.public_id)` instead of `get_or_create_fan(internal_id)` |
| `app/fan/routes.py` | `update_fan_profile_route()` now updates `UserProfile` fields directly (display_name, nationality, fan_team, avatar_url) and commits |
| `app/auth/onboarding_routes.py` | `fan_onboarding()` - removed `get_or_create_fan` import and call; now sets `profile.display_name = full_name` inside the `db_transaction` block |
| `app/auth/onboarding_routes.py` | `_commit_driver_onboarding()` - removed `get_or_create_fan` call; sets `profile.display_name` on the `UserProfile` record |
| `app/auth/onboarding_routes.py` | `_commit_organisation_onboarding()` - removed `get_or_create_fan` call |
| `app/identity/individuals/individual_verification.py` | Updated architectural boundary comments to reference `UserProfile` instead of deprecated `FanProfile` |

**Verification**
- Post-edit grep confirmed **zero functional references** to `get_or_create_fan`, `FanProfile`, or `from app.fan.models import` remain in `app/` (only the deprecation comment in `app/fan/models.py` and the stale `app/fan/services/registry.py` file remain - the latter is now orphaned).

---

## Phase 4 - Code: Align `fan` Role → `user`

**Goal:** Rename the default end-user role from `fan` to `user` across seed definitions, decorators, helpers, and route logic.

**Files Modified**

| File | Change |
|------|--------|
| `app/auth/seed_roles.py` | `GLOBAL_ROLE_DEFS`: `RoleDef("fan", 13, ...)` → `RoleDef("user", 13, "Default registered user - can browse and book services")` |
| `app/auth/seed_roles.py` | `GLOBAL_PERMISSION_DEFS`: all `accommodation.search`, `accommodation.view`, `accommodation.book` permission role lists changed `"fan"` → `"user"` |
| `app/auth/decorators.py` | `get_highest_role()` hierarchy list: `"fan"` → `"user"`; default return: `"user"` |
| `app/auth/helpers.py` | `ROLE_HIERARCHY` tuple: `"fan"` → `"user"` |

**Pending DB Steps**
- Re-seed: `flask seed-all`
- Update existing rows in `user_roles` that reference the old `fan` role ID to point to the new `user` role ID (SQL provided in terminal instructions).

---

## Phase 5 - Code: Tournament Skin via `MODULE_FLAGS`

**Goal:** Make the fan-allegiance UI conditional on `MODULE_FLAGS["tournament"]` and wire `fan_team` through forms/templates.

**Files Modified**

| File | Change |
|------|--------|
| `app/__init__.py` | `inject_sitewide()` context processor now returns `"tournament_mode": current_app.config.get("MODULE_FLAGS", {}).get("tournament", False)` |
| `templates/fan/dashboard.html` | Added `{% if tournament_mode %}` block containing `fan-allegiance-badge` (if `profile.fan_team` is set) and `fan-declare-prompt` (otherwise). End block clearly marked. |
| `templates/profile/edit.html` | Added `<select name="fan_team">` with all AFCON teams (Algeria through Other/Neutral) bound to `profile.fan_team`. Placed inside the existing form, before submit buttons. |
| `app/profile/routes.py` | `edit_profile()` POST handler now reads `request.form.get("fan_team", "").strip() or None` and assigns to `profile.fan_team`. Placed in the mutable-fields section, safely outside immutability enforcement. |
| `templates/profile/public.html` | Added `{% if tournament_mode and profile.fan_team %}` badge inside the profile header: green pill badge reading "AFCON fan - {team}" |

---

## Phase 6 - Verification (In Progress)

**Automated Checks Performed**
- `python -m py_compile` passed on all 9 modified `.py` files - zero syntax errors.

**Remaining Manual Verification Steps**

Run these in PowerShell to fully verify the system state:

```powershell
$env:PYTHONPATH="C:\Users\ADMIN\Desktop\afcon360_app"
cd C:\Users\ADMIN\Desktop\afcon360_app

# 1. Verify user_profiles columns
C:\Users\ADMIN\Desktop\afcon360_app\.venv\Scripts\python.exe -m flask shell -c "
from app.extensions import db
from sqlalchemy import inspect, text
cols = [c['name'] for c in inspect(db.engine).get_columns('user_profiles')]
assert 'fan_team' in cols and 'display_name' in cols and 'avatar_url' in cols and 'bio' in cols
print('Phase 1: PASS - columns exist')
"

# 2. Verify fan_profiles table is gone
C:\Users\ADMIN\Desktop\afcon360_app\.venv\Scripts\python.exe -m flask shell -c "
from app.extensions import db; from sqlalchemy import inspect
assert 'fan_profiles' not in inspect(db.engine).get_table_names()
print('Phase 2: PASS - fan_profiles dropped')
"

# 3. Verify no FanProfile references remain (excluding docs & registry orphan)
# (Already confirmed via grep - zero hits in app/ except deprecation comment)

# 4. Verify role rename
C:\Users\ADMIN\Desktop\afcon360_app\.venv\Scripts\python.exe -m flask shell -c "
from app.extensions import db; from sqlalchemy import text
assert db.session.execute(text('SELECT COUNT(*) FROM roles WHERE name=''fan''')).scalar() == 0
assert db.session.execute(text('SELECT COUNT(*) FROM roles WHERE name=''user''')).scalar() == 1
print('Phase 4: PASS - role aligned')
"

# 5. Smoke test: app starts and routes are present
C:\Users\ADMIN\Desktop\afcon360_app\.venv\Scripts\python.exe -m flask routes 2>&1 | Select-String -Pattern "fan.dashboard|profile.edit_profile"

# 6. Unit tests
C:\Users\ADMIN\Desktop\afcon360_app\.venv\Scripts\python.exe -m pytest tests/test_onboarding.py tests/test_registration_flow.py -v
```

---

## Summary of Modified Files

### Python (models, routes, helpers, seed)
1. `app/profile/models.py`
2. `app/fan/models.py`
3. `app/fan/routes.py`
4. `app/auth/onboarding_routes.py`
5. `app/auth/seed_roles.py`
6. `app/auth/decorators.py`
7. `app/auth/helpers.py`
8. `app/profile/routes.py`
9. `app/__init__.py`
10. `app/identity/individuals/individual_verification.py`

### Templates (HTML)
11. `templates/fan/dashboard.html`
12. `templates/profile/edit.html`
13. `templates/profile/public.html`

### Scripts
14. `scripts/migrate_fan_profiles.py` (new)

### Pending DB migrations
15. `migrations/versions/*drop_fan_profiles_table.py` (to be generated)

---

## Forbidden Actions Honoured
- Route URLs and blueprint prefixes: **unchanged**
- Wallet system (models, routes, services): **untouched**
- KYC system (`kyc_compliance.py`, `kyc_routes.py`): **untouched**
- Org model (`Organisation`, `OrganisationMember`, `OrgUserRole`): **untouched**
- Admin roles (owner, super_admin, admin, moderator, support, auditor): **untouched**
- Service provider roles (driver, transport_admin, accommodation_admin, event_manager): **untouched**
- Onboarding blueprints and routes (other than `get_or_create_fan` removal): **untouched**
- Login/logout/register routes: **untouched**
- Existing applied migrations: **untouched**

---

## Next Actions
1. Run the **Phase 2 pending DB steps** (data migration if needed, then drop `fan_profiles` table migration).
2. Run the **Phase 4 pending DB steps** (`flask seed-all` + SQL update of `user_roles` rows).
3. Run the **Phase 6 verification commands** above to confirm everything is clean.
