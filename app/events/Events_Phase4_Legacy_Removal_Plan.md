# Phase 4 Legacy Migration and Conditional Removal Plan

**Date:** 2026-08-15
**Status:** PLAN ONLY (Pending Human Review)

## 1. Overview
This document outlines the step-by-step implementation plan for migrating legacy consumers of organizer_id, created_by_type, and created_by_entity_id, and safely deprecating the fields, based on the Phase 3 Consumer Audit. 

No database schema changes or column drops will occur until all application consumers are verifiably migrated and legacy fields are fully isolated.

## 2. General Execution Sequence

The migration will be executed in the following staged order:
1. **Step 1 — Pre-removal evidence**: (consumer inventory, legacy input observability, backfill candidate report)
2. **Step 2 — Migrate consumers**: (ownership, operator, contact, creator)
3. **Step 3 — Conditional backfill**: (YES -> canonical ownership, NO -> unchanged, AMBIGUOUS -> review)
4. **Step 4 — Full regression + observation**
5. **Step 5 — Mark deprecated**
6. **Step 6 — Remove only proven redundancy**

## 3. Consumer Migration Strategies

### 3.1 Field: organizer_id

#### 3.1.1 app/events/permissions.py: _resolve_organiser_id / _is_event_owner
* **Semantic Intent:** Owner
* **Exact Migration Change:** Update authorization paths to strictly use current_owner_type and current_owner_id. Keep organizer_id fallback alive during the compatibility window. Remove the fallback only after the ownership backfill is proven.
* **Required Tests (Real Code):** Existing tests/test_events_ownership_characterization.py and tests/test_event_transfer_lifecycle.py must pass after the fallback removal.
* **Data-Backfill Eligibility Rule:** Prior to backfill, generate a read-only candidate report detailing Event, organizer_id, current_owner_type/id, organization_id, transfer history, and owner evidence. Classify eligibility as YES, NO, or MANUAL REVIEW. Backfill ONLY IF classified as YES.
* **Compatibility Window:** Maintained during backfill.
* **Deployment/Order Requirements:** Migrate consumers in a controlled sequence while retaining the compatibility fallback. Complete evidence collection, backfill, and regression verification before removing the fallback.
* **Rollback Procedure:** Re-enable the organizer_id fallback in _is_event_owner.
* **Exact Condition for Removability:** Database backfill confirms 0 eligible events with null current_owner_id. 0 reads from this consumer.

#### 3.1.2 app/events/metrics_service.py: get_organizer_metrics
* **Semantic Intent:** Operator / Manager
* **Exact Migration Change:** Refactor queries to utilize EventRole or an explicit operator relationship rather than inferring from organizer_id.
* **Required Tests (Real Code):** Create tests/test_get_organizer_metrics_canonical.py against current code, then apply migration.
* **Data-Backfill Eligibility Rule:** N/A (Relies on proper EventRole operator mapping).
* **Compatibility Window:** Minimal. Service can cut over directly to the canonical field.
* **Deployment/Order Requirements:** Before final deprecation.
* **Rollback Procedure:** Revert query filter back to organizer_id.
* **Exact Condition for Removability:** Service tests pass using the operator semantic model.

#### 3.1.3 app/events/routes.py and routes_community_hosts.py
* **Semantic Intent:** Owner, Operator, Primary Contact, or Creator
* **Exact Migration Change:** Identify semantic intent for each route individually. Replace with current_owner_* (if Owner), EventRole/operator (if Operator), explicit contact (if Contact), or audit/creator fields (if Creator). APIs map inbound organizer_id payloads to the target semantic model internally during transition.
* **Required Tests (Real Code):** Execute tests/test_events_user_workflows.py.
* **Data-Backfill Eligibility Rule:** Inherits the ownership backfill rule.
* **Compatibility Window:** API endpoints must accept old payload shapes temporarily. Implement observability (metrics/logs) for legacy inputs.
* **Deployment/Order Requirements:** Execute immediately to stop bleeding legacy data into new events.
* **Rollback Procedure:** Revert payload mapping.
* **Exact Condition for Removability:** Client payloads updated to omit organizer_id. Instrument compatibility path and establish an observation period sufficient to demonstrate 0 active consumers using the legacy API parameter.

#### 3.1.4 app/events/models.py: Event.__init__
* **Semantic Intent:** Owner (Initialization mapping)
* **Exact Migration Change:** Set current_owner_* strictly directly.
* **Required Tests (Real Code):** Model unit tests.
* **Data-Backfill Eligibility Rule:** N/A
* **Compatibility Window:** Accept organizer_id kwarg temporarily but trigger deprecation warning.
* **Deployment/Order Requirements:** After route/API migration.
* **Rollback Procedure:** Restore fallback in __init__.
* **Exact Condition for Removability:** Codebase search confirms 0 invocations passing organizer_id to the constructor.

---

### 3.2 Field: created_by_type & created_by_entity_id

#### 3.2.1 app/events/models.py: Event.is_created_by_user
* **Semantic Intent:** Historical Creator distinction (System vs User)
* **Exact Migration Change:** Refine to created_by_id != 0 AND created_by_type == 'individual' if polymorphism is preserved.
* **Required Tests (Real Code):** Model unit tests verifying system vs individual creator semantics.
* **Data-Backfill Eligibility Rule:** N/A
* **Compatibility Window:** N/A
* **Deployment/Order Requirements:** Independent execution.
* **Rollback Procedure:** Revert logic.
* **Exact Condition for Removability:** **HARD RULE**: Field will **not** be removed and will be retained permanently if it retains platform-wide legitimate polymorphism for System/Org/Individual creators.

#### 3.2.2 app/identity/routes.py (Organisation Context)
* **Semantic Intent:** Legacy ownership querying
* **Exact Migration Change:** Change filter to current_owner_type == 'organization' and current_owner_id == org.id.
* **Required Tests (Real Code):** Write and run tests/test_identity_events.py.
* **Data-Backfill Eligibility Rule:** Event ownership backfill.
* **Compatibility Window:** None for reads.
* **Deployment/Order Requirements:** Post-backfill.
* **Rollback Procedure:** Revert route filters.
* **Exact Condition for Removability:** Query successfully replaced by canonical ownership logic.

#### 3.2.3 app/events/services.py: EventService
* **Semantic Intent:** Audit Trail
* **Exact Migration Change:** Standardize on BaseModel created_by_id logic unless polymorphism is strictly required.
* **Required Tests (Real Code):** Service tests.
* **Data-Backfill Eligibility Rule:** N/A
* **Compatibility Window:** N/A
* **Deployment/Order Requirements:** Align with platform-wide model standardization.
* **Rollback Procedure:** Revert assignments.
* **Exact Condition for Removability:** Full consensus on BaseModel creator logic.

## 4. Human Review Gate
**Approval Required:**
Please review this implementation plan. No code or schema migration will begin until this artifact is authorized.
