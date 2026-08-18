_# Phase 3 Consumer Audit: Legacy Events Identity Fields

**Date:** 2026-08-15
**Status:** Audit Complete (Pending Review)

## 1. Overview
As part of the Events Phase 3 deprecation planning, a read-only audit of the codebase was performed to identify all usages of legacy ownership fields in the `Event` model. 
The target fields are:
- `organizer_id`
- `created_by_type`
- `created_by_entity_id`

## 2. Identified Consumers & Classifications

### 2.1 Field: `organizer_id`

**Semantic Classification:** 
Currently ambiguously mixed between "Event Owner" (permissions fallback) and "Primary Contact/Creator". It exhibits legacy duplication with `current_owner_id` but still carries domain semantics for older records.

#### Consumer 1: `app.events.permissions._resolve_organiser_id` / `_is_event_owner`
* **Consumer Type:** Read / Permission/authorization use
* **Semantic Intent:** Owner (used as ownership surrogate for legacy events)
* **Domain Semantics vs Legacy Duplication:** Legacy duplication acting as an ownership surrogate for events lacking `current_owner_id`.
* **Exact Replacement:** `current_owner_type` / `current_owner_id`
* **Data Backfill Required:** Yes. Ownership backfill must require evidence that `organizer_id` represents the actual legacy owner (e.g., via existing permissions or historical workflows), not merely that `current_owner_id` is null.
* **Compatibility Period Required:** Yes. Keep fallback logic alive until backfill is complete and verified.
* **Regression Test Covering Replacement:** `tests/test_events_ownership_characterization.py` and `tests/test_event_transfer_lifecycle.py`
* **Safe Removal Condition:** Database backfill confirms 0 events with null `current_owner_id`; all route/service usages migrated.
* **Rollback Strategy:** Revert `permissions.py` changes and keep reading `organizer_id`.

#### Consumer 2: `app.events.metrics_service.get_organizer_metrics`
* **Consumer Type:** Read / Reporting/analytics use
* **Semantic Intent:** Operator / Manager (metrics for the current operator/manager)
* **Domain Semantics vs Legacy Duplication:** Valid domain semantics if it implies "Metrics for the current operator", but duplicated if it strictly means "Event Owner Metrics".
* **Exact Replacement:** `current_owner_id` (filtered by `current_owner_type == 'individual'`) if ownership is the intent, or a dedicated metric query by `EventRole` / operator relationship if operational actor is the intent.
* **Data Backfill Required:** No database backfill for this consumer, relies on the primary ownership backfill.
* **Compatibility Period Required:** No.
* **Regression Test Covering Replacement:** Must write `test_get_organizer_metrics_canonical.py` before changing.
* **Safe Removal Condition:** Reporting service queries rewritten to use canonical ownership or explicit operator field.
* **Rollback Strategy:** Revert `metrics_service.py` to filter by `organizer_id`.

#### Consumer 3: `app.events.routes.py` and `routes_community_hosts.py`
* **Consumer Type:** Read & Write / UI/template/API use
* **Semantic Intent:** Owner or Primary Contact (depending on exact route usage, often used to set initial ownership or filter by owner)
* **Domain Semantics vs Legacy Duplication:** Legacy duplication. Forms and APIs read/write this field to set initial ownership.
* **Exact Replacement:** `current_owner_type` and `current_owner_id` via Unified Context (if ownership), or dedicated contact field (if primary contact).
* **Data Backfill Required:** Yes.
* **Compatibility Period Required:** Yes. APIs must accept old payloads temporarily or map them internally.
* **Regression Test Covering Replacement:** `test_events_user_workflows.py`
* **Safe Removal Condition:** API clients updated to stop passing `organizer_id`; endpoints refactored to read canonical ownership.
* **Rollback Strategy:** Revert route filters and form validation to include `organizer_id`.

#### Consumer 4: `app.events.models.Event.__init__`
* **Consumer Type:** Write / Model initialization
* **Semantic Intent:** Owner (mapping layer setting initial ownership)
* **Domain Semantics vs Legacy Duplication:** Legacy duplication mapping layer.
* **Exact Replacement:** Set `current_owner_*` directly in constructors.
* **Data Backfill Required:** No.
* **Compatibility Period Required:** No.
* **Regression Test Covering Replacement:** Model unit tests.
* **Safe Removal Condition:** Deprecate `organizer_id` argument entirely from `__init__`.
* **Rollback Strategy:** Revert `models.py`.

---

### 2.2 Field: `created_by_type` & `created_by_entity_id`

**Semantic Classification:** 
Polymorphic creator definition. Distinct from ownership, but duplicates `created_by_id` if only tracking individual creators. Carries valid domain semantics for identifying SYSTEM vs ORGANIZATION vs INDIVIDUAL creators.

#### Consumer 1: `app.events.models.Event.is_created_by_user`
* **Consumer Type:** Read / Model logic
* **Domain Semantics vs Legacy Duplication:** Domain semantics (distinguishing user-created vs system-created events).
* **Exact Replacement:** Can be preserved or mapped strictly to `created_by_id != 0` AND `created_by_type == 'individual'`.
* **Data Backfill Required:** No.
* **Compatibility Period Required:** No.
* **Regression Test Covering Replacement:** Model unit tests.
* **Safe Removal Condition:** Only remove if the platform-wide creator polymorphism is deprecated.
* **Rollback Strategy:** Revert method logic.

#### Consumer 2: `app.identity.routes.py` (Organisation Context)
* **Consumer Type:** Read / UI/template/API use
* **Domain Semantics vs Legacy Duplication:** Legacy duplication if querying for ownership, valid domain semantics if strictly querying for historical creator.
* **Exact Replacement:** Query `current_owner_id` and `current_owner_type == 'organization'` if ownership is the intent.
* **Data Backfill Required:** Yes (ownership backfill).
* **Compatibility Period Required:** Yes.
* **Regression Test Covering Replacement:** `test_identity_events.py` (to be written).
* **Safe Removal Condition:** All org event queries migrate to canonical ownership logic.
* **Rollback Strategy:** Revert API query filters.

#### Consumer 3: `app.events.services.EventService`
* **Consumer Type:** Write / API use
* **Domain Semantics vs Legacy Duplication:** Legacy duplication.
* **Exact Replacement:** Rely strictly on the `created_by_id` (BaseModel standard audit) unless polymorphic creator tracking is universally mandated.
* **Data Backfill Required:** No.
* **Compatibility Period Required:** No.
* **Regression Test Covering Replacement:** Service tests.
* **Safe Removal Condition:** Codebase standardizes on `BaseModel` creator logic.
* **Rollback Strategy:** Revert service assignments.

---

## 3. Human Review Gate
**Approval Required:**
Please review this comprehensive, code-evidence-backed consumer classification report. No legacy fields will be modified, deprecated, or removed in code or database until this audit is explicitly approved for Phase 4._