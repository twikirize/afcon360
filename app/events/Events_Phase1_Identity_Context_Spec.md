# AFCON360 Events - Phase 1 Identity, Context, & Authority Specification

**Status:** Specification Freeze (Pending Human/Architectural Review)
**Target Module:** Events (`app/events`)
**Goal:** Define the canonical Identity, Context, and Authority model for the Events module to align with platform-wide standards before any code modifications begin.

---

## 1. Canonical Identity Model

To eliminate semantic confusion and establish a platform-wide standard, the Events module will adopt the following canonical model:

* **User**: The authenticated human identity. This represents the actual person logged into the system and is immutable during a session.
* **Context**: The general authorization scope in which an action is performed. An Organisation is just one type of context. Other examples may include Personal Context, Platform Context, or specific Resource Contexts.
* **Actor**: The authenticated User acting within a particular Context. 
* **Effective Authority**: The combination of the Actor and their active Context, alongside specific Memberships, Roles, and Permissions. The authenticated identity never changes, only the authority context changes.

## 2. Separation of Ownership and Authority

A core architectural rule is the explicit separation of ownership from authority: **Active Context is NOT Ownership**.

An entity having permission to manage an event does not automatically mean they own the event. 
For example:
* **User**: John
* **Active Context**: NBooking (Organisation)
* **Resource**: Hotel/Event
* **Owner**: NBooking
* **Authority**: John as `org_admin` for NBooking

John has the authority to act on the event because NBooking authorizes him, but John is not the owner. His authority is derived from his role within the active context. This explicitly separates the roles of **OWNER**, **OPERATOR**, and **VENUE**, while preserving the **CREATOR** (for audit/history) and **PARTICIPANT**.

## 3. Explicit Active Context & Session State Security

The system will enforce a session-level active context switching mechanism. The client must never be trusted merely because it submits a context or organisation ID.

### Context ≠ Role
Context determines the authorization scope; roles determine capabilities within that scope. A role does not itself constitute a context.
For example, if John's context is NBooking, and his roles are `org_admin` and `event_manager`, the effective permissions are resolved from all applicable roles/permissions within that context.

### Security and State Rules:
* **Selection:** Context is selected via the UI (Persona Switcher) and sent to a secure endpoint that validates the request.
* **Validation:** The server must always verify that the authenticated User is eligible to operate in the requested Context (e.g., they have an active membership in the organisation). `active_role`, if retained by the unified context contract, is a selected/displayed persona or context metadata and must never be treated as an authoritative permission grant by itself. The server remains the authority.
* **Storage:** The active context should be stored securely on the server-side session (or secure token claims) writing only minimal keys (e.g., `active_context_type`, `active_context_id`, `active_role`).
* **Revocation/Role Changes:** If a user's membership is revoked or their role changes, the active context must be immediately invalidated or downgraded. Re-validation of eligibility must occur on each protected action.
* **Survival:** Context may survive a page reload or token refresh, but a complete logout clears the active context.
* **Invalidation:** Stale context (e.g., due to permission revocation) is handled by the target resolver layer (`app/auth/context.py`) failing closed during authorization checks.
* **API Handling:** APIs receive context implicitly via the validated session/token state, preventing arbitrary `organisation_id` injection in request payloads.
* **Audit Logging:** Every context switch must be logged via the Forensic Audit Service.
* **Default/No Context:** For users with no organisation or upon initial login, the default context is their Personal Context.

## 4. Events Compatibility Strategy

During the migration (Phase 2+), existing Events fields will not be abruptly removed. The strategy ensures zero breakage for ticketing, moderation, and assignments.

* The existing centralized `app/events/permissions.py`, `resolve_user_roles()`, and polymorphic ownership concepts will be retained and evolved.
* `EventRole` and `organisation_id` assignments will be evaluated to see if they can already represent an organisation operating an event on behalf of another owner with minimal extension.
* Ambiguous fields will be preserved as derived or compatibility fields during the transition.
* New authorization infrastructure will **NOT** be created; this is a consolidation and refinement effort.

## 5. Migration Matrix

### Migration Lifecycle
The module refactoring will follow this sequence to ensure stability:
* **Phase 0** — Audit
* **Phase 1** — Canonical Specification
* **Phase 2** — Compatibility Implementation
* **Phase 3** — Legacy Deprecation
* **Phase 4** — Legacy Removal

The following matrix maps current Events fields to their Phase 1 disposition and future state. Ambiguities are explicitly documented.

| Current Field | Current Meaning (Ambiguities) | Canonical Future Meaning | Source of Truth | Disposition | Compatibility Behavior | Migration Phase |
|---|---|---|---|---|---|---|
| `organizer_id` | **Ambiguous**: Creator? Manager? Owner? Primary contact? | **UNRESOLVED** — must be established from Events domain behavior and existing workflows. | Derived / Legacy | Retain as compatibility field pending semantic resolution. | Do not reinterpret or repurpose during Phase 2. | Phase 3 (Deprecation) |
| `organization_id` | The organisation tied to the event. | Organisation associated with the event's operating/organizational relationship, where applicable. It is not itself proof of the requesting user's active context or authority. | Canonical | Retain / Evolve | Used to validate context against `EventRole`. | Phase 2 (Map) |
| `original_creator_id` | The human who created the event. | Immutable audit actor (Creator). | Canonical | Retain | Immutable reference for audit. | Phase 2 (Map) |
| `created_by_type` / `created_by_entity_id` | Polymorphic creator (User/Org/System). | Contextual audit record of *how* it was created. | Derived / Audit | Review for deprecation | Maintained by system logic for legacy audit. | Phase 3 (Deprecation) |
| `current_owner_type` / `current_owner_id` | Polymorphic owner. | Explicit Owner (Who legally/administratively controls the event). | Canonical | Retain / Evolve | Regulated strictly via `EventTransferRequest`. | Phase 2 (Map) |
| `EventRole` | Event-specific staff roles. | Resource-level Authorization. | Canonical | Retain | Evaluated alongside Active Context. | Phase 2 (Map) |
| `EventTransferRequest` / `Log` | Ownership transfer tracking. | Immutable audit trail for Canonical Ownership changes. | Canonical | Retain | Continues to track polymorphic owner shifts. | Phase 2 (Map) |

## 6. Alignment with Existing Specs

This specification is designed to align with:
* `app/Documentation/UNIFIED_IDENTITY_CONTEXT_SPEC.md`
* `app/Documentation/IDENTITY_POLICIES.md`

**Conflicts & Observations:**
* The `UNIFIED_IDENTITY_CONTEXT_SPEC.md` already defines a fail-closed, normalized context-switching contract (`active_context_type`, `active_context_id`, `active_role`) using `app/auth/context.py`. This Events Phase 1 spec fully adopts this without contradiction.
* `IDENTITY_POLICIES.md` mandates the strict separation of internal `id` (BIGINT) and external `public_id` (UUID). The canonical model defined here will continue to enforce this separation across all context and ownership references.
* No new architectural conflicts have been identified. The Events module will adapt to consume the existing Unified Identity Context layer rather than inventing a parallel one.

## 7. Existing Architecture Evaluation & Reconciliation

A comprehensive audit of the current Events and Identity architecture (`app/events/permissions.py`, `models.py`, `resolve_user_roles()`) revealed the following ground truths:

| Canonical Concept | Existing Implementation | Evidence | Compatible? | Gap | Decision |
|---|---|---|---|---|---|
| **User** | Existing `User` model | Code/Spec | Yes | None | Retain as the immutable Actor. |
| **Context** | Existing context system | Code/Spec | Yes | `active_role` is a session persona, not an absolute grant. | Evolve context system to enforce strict boundary between Context (scope) and Role (capabilities). |
| **Organisation membership** | Existing `organisations` relation | Code | Yes | None | Retain for validation. |
| **Authority** | Existing `permissions.py` / `resolve_user_roles` | Code | Yes | Relies heavily on `organizer_id` to infer ownership. | Evolve `permissions.py` to decouple explicit `Owner` from operational `Actor`. |
| **Ownership** | `current_owner_type` / `id` | Code | Yes | Duplicate meaning often inferred from `organizer_id`. | Strictly regulate via `EventTransferRequest`. |
| **Creator** | `original_creator_id`, `created_by_*` | Code | Yes | Used primarily for audit. | Deprecate polymorphic fields; retain `original_creator_id`. |
| **Event role** | `EventRole` | Code | Yes | None | Retain as the canonical resource-level authorization store. |

### Compatibility Classification

Based on the architecture audit, the existing mechanisms are classified as follows:
* **`app/events/permissions.py`**: **Compatible with refinement**. Will be retained and refined to decouple ownership from operational authority.
* **`resolve_user_roles()`**: **Compatible with refinement**. Will consume the normalized canonical Identity model.
* **`organizer_id`**: **Unknown**. Requires further investigation via ADR to determine if it is the primary contact, actor, or legacy owner surrogate.
* **`organization_id`**: **Compatible with refinement**. Used for organizational context checks (`_is_org_member_of_event`), will be formalized as context boundary without implying ownership.
* **`EventRole`**: **Compatible — retain**. Fully aligns with resource-level authorization.
* **`EventTransferRequest/Log`**: **Compatible — retain**. Correctly handles ownership transfer lifecycle.
* **`created_by_type` / `created_by_entity_id`**: **Redundant**. Eventual deprecation in favor of a clean Actor-based audit log.

---
**CRITICAL NOTE:** Phase 1 is a specification freeze point. Before any implementation begins, this specification must undergo human/architectural review to approve the canonical contract. Only after approval will Phase 2 implementation begin. Do NOT write code yet.