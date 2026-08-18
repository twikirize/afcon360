# AFCON360 Events - Phase 0 Audit Report & Migration Plan

## PHASE 0: AUDIT BASELINE

### 1. IDENTITY & ORG CONSUMPTION
**How do the current Events models link to Users and Organisations?**
The `Event` model (`app/events/models.py`) utilizes a dual approach to identity and ownership, consisting of direct Foreign Keys and polymorphic entity pointers:
- **`organizer_id`** (FK to `users.id`): The primary public-facing human contact (User) managing the event.
- **`organization_id`** (FK to `organisations.id`): Explicit link to an organisation context for the event.
- **`original_creator_id`** (FK to `users.id`): Audit reference for the human who physically created the record.
- **Immutable Creator (Polymorphic)**: `created_by_type` (`CreatorType` enum: individual, organization, system) and `created_by_entity_id` (BigInteger pointing to user_id, org_id, or 0). 
- **Mutable Owner (Polymorphic)**: `current_owner_type` (`OwnerType` enum) and `current_owner_id` (BigInteger). Ownership can be transferred via `EventTransferRequest`.
- **`EventRole` model**: Links `event_id` to `user_id` and optionally `organisation_id` to store event-level staff roles (e.g., co_organizer, steward).

### 2. PLATFORM RBAC DISCOVERY
**How the platform validates User/Organisation permissions (in `routes.py`/`services.py`):**
Authorization is centralized in `app/events/permissions.py`, which provides contextual capability functions (e.g., `can_manage_event`, `can_publish_event`, `can_hard_delete_event`) used extensively across the module.
- **Platform-level validation**: It leverages `app.auth.helpers` such as `has_global_role(user, 'super_admin')` or `has_global_permission(user, 'events.manage')` to grant system-wide access.
- **Organisation-level validation**: It uses `has_org_role(user, org_id, 'org_owner', 'org_admin')` to confirm if the user administers the event's associated organisation.
- **Event-level validation**: It aggregates the platform roles, org roles, `EventRole` staff records, and direct `organiser_id`/owner checks via `resolve_user_roles(user, event)` into a unified set of roles for the specific request context.
- **Route enforcement**: Routes employ `@login_required` and typically invoke a `permissions.py` check (or `require_event_permission` dispatcher) before processing logic in services.

### 3. COUPLING & SIDE EFFECTS
**Integrations and signals relying on the authorization/ownership structure:**
- **Signals (`app/events/signal_handlers.py`)**: 
  - `event_registered` and `event_cancelled`: Hook into external module logic (accommodation, transport cancellations/bookings).
  - `offer_services_after_registration`: Cross-module up-selling trigger.
  - `event_capacity_released`: Connected to the Reaper task for atomic ticket pool adjustments.
- **Cross-Module Models (`EventAssignment`)**: Direct `CROSS_MODULE_REF` integration linking event attendees (`attendee_id`) to `accommodation_booking_id`, `transport_booking_id`, and `community_host_id`.
- **Moderation and Transfer Tracking**: 
  - `EventModerationLog` tracks state transitions coupled to `user_id`.
  - `EventTransferRequest` and `EventTransferLog` explicitly manipulate and log changes to the polymorphic `current_owner_type` / `current_owner_id`. Any restructuring of ownership must strictly address the logic in these transfer models.

## MIGRATION PLAN
*(To be detailed in Phase 1 as we move towards implementation in phases, ensuring zero breakage of existing workflows, ticketing, moderation, or assignments.)*

- **Status**: Audit completed. No code changes implemented yet.
