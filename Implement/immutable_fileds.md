# Immutable Fields — Implementation Report

## Context

The file `Implement/immutable_fileds.md` was empty (0 bytes). This report documents the investigation of the existing immutable fields infrastructure in the AFCON360 codebase and the implementation of missing application-level enforcement.

---

## System State Analysis

### What Already Existed (No Duplication Needed)

#### 1. DB-Level Enforcement — `app/profile/models.py`

The `UserProfile` model already has a complete DB-level immutable fields system:

- **`IMMUTABLE_AFTER_VERIFICATION`** set (line 35-38) — 9 fields locked after verification:
  - `full_name`, `date_of_birth`, `gender`, `nationality`
  - `id_type`, `id_number`, `id_document_url`, `id_document_mime`, `id_document_size`

- **`enforce_immutable_after_verification`** SQLAlchemy `before_update` event listener (line 317-348) — intercepts any UPDATE attempt on verified profiles, compares old vs new values for each immutable field, raises `ValueError` if a change is detected, and logs the blocked attempt to both `UserProfileAudit` and `ForensicAuditService`.

- **`UserProfileAudit`** model (line 298-311) — append-only audit table tracking attempted changes to immutable fields with `old_value`, `attempted_value`, `attempted_at`, and `attempted_by_user_id`.

#### 2. Creator Immutability — `app/events/models.py`

The `Event` model has immutable creator fields (line 237-245):
- `created_by_type` — set at creation, never changes
- `created_by_entity_id` — set at creation, never changes
- Documented as "immutable after creation" in the model docstring

#### 3. Immutable Audit Records — `app/audit/comprehensive_audit.py`

- **`FinancialAuditLog`** (line 84-205) — described as "immutable audit log for ALL financial transactions" with `REQUIRED` retention: PERMANENT (never delete)
- **`SecurityEventLog`** (line 372-445) — 7-year retention, append-only
- **`DataChangeLog`** (line 452-544) — tracks data modifications with 7-year retention

#### 4. Existing Documentation

- `app/Documentation/PROFILE_KYC_SYSTEM.md` (lines 140-169) — documents the immutable fields concept, enforcement mechanisms, and the 9 locked fields
- `app/Documentation/ARCHITECTURE_PASS_5_FINAL.md` (line 68) — explicitly states "Do not change IMMUTABLE_AFTER_VERIFICATION"

### What Was Missing (Application-Level Enforcement)

While the DB-level enforcement worked correctly, the application-layer routes had gaps:

1. **`edit_profile()` in `app/profile/routes.py` (line 185)** — Only blocked `full_name` for verified users (lines 204-207). The other 8 immutable fields (`date_of_birth`, `gender`, `nationality`, `id_type`, `id_number`, `id_document_url`, `id_document_mime`, `id_document_size`) were not explicitly checked at the application level. The DB event would catch them, but the user would get a generic `ValueError` instead of a specific message about which fields are immutable.

2. **`update_settings()` in `app/profile/routes.py` (line 261)** — Had NO immutability enforcement at all. It directly set `profile.full_name`, `profile.phone_number`, etc. without checking if the user was verified. The DB event would catch immutable field changes, but again with a generic error and no audit logging at the application level.

---

## Implementation

### 1. New File: `app/utils/immutable_fields.py`

A reusable utility module following the existing `app/utils/` pattern (same as `id_guard.py`, `idempotency.py`, `module_guard.py`, etc.).

**Functions:**

| Function | Signature | Purpose |
|----------|-----------|---------|
| `get_immutable_fields()` | `() -> Set[str]` | Returns a copy of the `IMMUTABLE_AFTER_VERIFICATION` set |
| `is_field_immutable(field_name)` | `(str) -> bool` | Checks if a single field is in the immutable set |
| `filter_immutable_changes(profile, data, is_verified)` | `(Any, Dict[str, Any], bool) -> Tuple[Dict, Set[str]]` | Splits form data into allowed changes and blocked fields; only blocks fields that actually changed (compares old vs new values) |
| `enforce_immutability(profile, data, is_verified, user_id)` | `(Any, Dict[str, Any], bool, Optional[int]) -> Dict[str, Any]` | Returns a dict of blocked fields with old/attempted values for audit logging |

**Design decisions:**
- Imports `IMMUTABLE_AFTER_VERIFICATION` from `app.profile.models` to avoid duplication
- `filter_immutable_changes` compares old vs new values so it only blocks fields that were actually changed, not fields that appear in the form data with unchanged values
- `enforce_immutability` is the more detailed variant that returns old/attempted values for audit purposes
- Both functions are pure (no side effects), making them testable and reusable

### 2. Modified: `app/profile/routes.py`

#### `edit_profile()` (line 185)

**Before:** Only blocked `full_name` for verified users. Other immutable fields were silently passed through and caught by the DB event with a generic `ValueError`.

**After:**
- Builds an `editable_data` dict with all form fields (both mutable and immutable)
- Calls `filter_immutable_changes()` to split into allowed and blocked fields
- Sets only allowed fields on the profile object
- For blocked fields, logs each to `ForensicAuditService.log_blocked()` with entity type, entity ID, action, user ID, reason, old value, attempted value, and IP address
- Shows a user-friendly flash message: "Some fields cannot be changed after verification."
- Returns early to `redirect(url_for('profile.edit_profile'))` without attempting DB commit

#### `update_settings()` (line 287)

**Before:** No immutability enforcement. Directly set `profile.full_name`, `profile.phone_number`, etc. without checking verification status.

**After:**
- Checks `profile.verification_status == 'verified'`
- Builds an `editable_data` dict with all form fields
- Calls `filter_immutable_changes()` to split into allowed and blocked fields
- Sets only allowed fields on the profile/user objects
- For blocked fields, logs each to `ForensicAuditService.log_blocked()` and returns a 403 JSON response with `success: False`, an error message, and the list of blocked fields
- Only commits to DB if no fields were blocked

### 3. Modified: `app/utils/__init__.py`

Added imports and `__all__` exports for the four new utility functions:
- `get_immutable_fields`
- `is_field_immutable`
- `filter_immutable_changes`
- `enforce_immutability`

---

## What Was NOT Done (Avoiding Duplication)

| Area | Reason |
|------|--------|
| DB schema / migration | `IMMUTABLE_AFTER_VERIFICATION`, `UserProfileAudit`, and `enforce_immutable_after_verification` already exist in `app/profile/models.py` |
| `app/events/models.py` | Creator immutability is already enforced at the model level |
| `app/audit/comprehensive_audit.py` | `FinancialAuditLog` already has immutable audit records |
| `app/admin/routes.py` | Admin `update_profile()` and `update_profile_by_username()` only modify mutable fields (address, city, country) |
| `app/auth/routes.py` | `complete_profile()` is for initial profile setup (users are not verified at this stage) |
| `app/auth/onboarding_routes.py` | Onboarding flow is for new users who are not yet verified |
| `app/kyc/routes.py` | KYC verification routes set identity fields as part of the verification process, which is the correct workflow |

---

## Migration Needed?

No. No schema changes were made. The implementation builds entirely on existing database tables and columns.

---

## Manual Steps

None required. The implementation uses existing infrastructure.

---

## Risks / Conflicts

| Risk | Mitigation |
|------|------------|
| `filter_immutable_changes` imports `IMMUTABLE_AFTER_VERIFICATION` from `app.profile.models`, creating a dependency from `app.utils` to `app.profile` | This is consistent with how other utilities import from models (e.g., `app.utils.id_kinds` imports from models). No circular import exists because `app.profile.models` imports `app.utils.id_kinds`, not `app.utils.immutable_fields` |
| `edit_profile()` now returns early when immutable fields are blocked, before reaching `db.session.commit()` | This is correct behavior — the DB event would have caught the violation anyway, but now it's caught earlier with a specific message |
| `update_settings()` now returns a 403 JSON response for blocked fields | The frontend must handle 403 responses. Previously, the DB event would have raised a ValueError that was caught by the generic `except ValueError` handler |
| The `filter_immutable_changes` function only blocks fields that actually changed (comparing old vs new values) | This is intentional — setting a field to its current value should not be treated as a blocked change |

---

## Verification

1. **Import check:** `python -c "from app.utils.immutable_fields import get_immutable_fields, is_field_immutable, filter_immutable_changes, enforce_immutability; print('OK')"`
2. **Profile test suite:** `pytest tests/ -k profile`
3. **Manual test — verified user:** Attempt to change `full_name` via `/profile/edit` → should see flash message "Some fields cannot be changed after verification."
4. **Manual test — verified user:** Attempt to change `nationality` via `/update-settings` → should receive 403 JSON with `blocked_fields: ["nationality"]`
5. **Manual test — unverified user:** Change `full_name` via `/profile/edit` → should succeed normally
6. **Audit check:** Verify `ForensicAuditService.log_blocked()` is called when immutable fields are blocked (check `forensic_audit` table)
7. **DB event still works:** The `before_update` event listener in `app/profile/models.py` remains the defense-in-depth layer — if application-level enforcement is bypassed, the DB event still prevents changes