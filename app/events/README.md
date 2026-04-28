# Events Module — Consolidated README

This document consolidates all Events-related READMEs/notes into a single, up‑to‑date reference. It de-duplicates overlapping content, aligns claims with the current codebase, and highlights what remains to be done.

Source docs merged and cross-checked:
- Readme's/2026-04-11_events_concurrency_fixes.md
- Readme's/registration_report2_15-04 (audit transcript with Events routes and checks)
- Code in app/events: models.py, services.py, routes.py, permissions.py, signal_handlers.py, signals.py


## 1) Module Overview

The Events module provides full lifecycle management for events:
- Creation, editing, publishing, moderation and takedown flows
- Ticket tiers and capacity control (limited or unlimited)
- Registration and waitlist
- Discount codes
- Check-in and QR codes
- Organizer/staff dashboards and analytics
- Cross-module signals (loose coupling to Transport/Accommodation, etc.)

Blueprint: `events_bp` with user-facing and admin routes.


## 2) Data Models (app/events/models.py)

Key models and highlights:
- Event
  - Status flags and transitions; owner/creator types (user/organization/system)
  - Public `ref` and `public_id` generation helpers
  - Soft delete, admin remove, restore; ownership checks
- TicketType
  - `capacity` and `available_seats` with `version` for concurrency
  - Seat reservation/release helpers; sold-out checks
- EventRegistration
  - Registration refs and QR token; status flags (checked-in/confirmed/cancelled)
- Waitlist
  - Tracks users waiting for seats; notification/conversion marking
- EventRole
  - Roles for staff/participants
- DiscountCode
  - Validation and discount calculation
- EventTransferRequest / EventTransferLog
  - Transfer workflow with status
- EventModerationLog
  - Stores moderation actions
- EventAssignment
  - Assign services (transport, accommodation, etc.) to attendees

These models are actively used by `EventService` and routes.


## 3) Services (app/events/services.py)

`EventService` centralizes business logic (2k+ LOC). Key capabilities:
- Querying: `get_all_events`, `get_event`, `get_event_model`, organizer/org views
- Content lifecycle: `create_event`, `update_event`, `delete_event` (soft), moderation actions (approve/reject)
- Home/Discovery: `get_featured_event`, `get_upcoming_events`
- Registration:
  - `register_for_event_optimistic` — high-concurrency path with atomic capacity updates (see Concurrency below)
  - `register_for_event_with_payment` — payment-aware flow
  - `cancel_registration`, `check_in_attendee` (with QR)
- Ticketing: `add_ticket_type`, validations, discount code validation
- Dashboards: attendee, organizer, service provider
- Participation & assignments: create participation, assign services, fetch assignments
- Admin metrics: `get_admin_dashboard_data`

Utility:
- `IdempotencyChecker` for deduping retries
- `with_transaction` decorator for DB transaction isolation handling


## 4) Routes (app/events/routes.py)

Important endpoints (function names kept short; see file for full behavior and decorators):
- Public/User
  - `/events/` → `list`
  - `/events/<identifier>` → `landing` (identifier can be slug/public_id)
  - `/events/register/<identifier>` → `register`
  - `/events/registration-confirmation/<reg_ref>` → `registration_confirmation`
  - `/events/my-registrations` → `my_registrations`
  - `/events/properties` and `/events/api/properties` (supporting views)
- Organizer/Creator
  - `/events/create` → `create_event`
  - `/events/<identifier>/edit` → `edit_event`
  - `/events/organizer/<identifier>` → `organizer_dashboard`
  - `/events/my-events` → `my_events`
  - `/events/<identifier>/attendees` → `event_attendees`
  - `/events/<identifier>/scanner` → `scanner`
  - `/events/<identifier>/analytics` → `event_analytics`
  - `/events/<identifier>/export-attendees` → `export_attendees`
  - `/events/<identifier>/add-ticket-type` → `add_ticket_type`
  - `/events/<identifier>/assign-service/<booking_type>` → `assign_service_to_attendee_route`
  - `/events/<identifier>/assignments` → `get_event_assignments`
  - `/events/<identifier>/available-bookings/<booking_type>` → `get_available_bookings`
  - `/events/<identifier>/staff` → `event_staff` and `remove_staff`
- Admin/Moderation (namespaced under `/events/admin*` in routes)
  - `/events/admin-dashboard` → `admin_dashboard`
  - `/events/admin/events` → `admin_events`
  - Approvals & status transitions:
    - `admin_approve`, `admin_reject`, `admin_suspend`, `admin_deactivate`, `admin_takedown`, `admin_publish`, `admin_restore`
  - Debug endpoints: `admin_debug_events`, `admin_debug_counts`
- API helpers
  - `/events/api/event/<public_id>` → `api_get_event_by_public_id`
  - `/events/api/checkin` → `api_checkin`
  - `/events/api/checkin-stats/<event_slug>` → `api_checkin_stats`

Note: `landing`, `list`, `create_event`, etc., confirmed present (former notes questioned existence; code now contains them).


## 5) Permissions (app/events/permissions.py)

Permission helpers determine who can do what based on:
- Global roles: system admin, super admin, event manager
- Organization roles for the event’s organisation
- Event ownership (created by/owned by)
- Event status (e.g., only published/approved can be certain actions)

Key functions:
- `resolve_user_roles`, `get_user_event_permissions`
- Action gates: `can_manage_event`, `can_approve_event`, `can_publish_event`, `can_suspend_event`, `can_pause_event`, `can_resume_event`, `can_cancel_event`, `can_delete_event`, etc.
- Analytics & check-in: `can_view_analytics`, `can_check_in`, `can_check_in_attendees`

These are invoked in routes to protect admin/organizer functionality.


## 6) Signals and Handlers (app/events/signal_handlers.py, app/events/signals.py)

The Events module emits and consumes signals for loose coupling:
- Emitted: `event_registered`, `event_cancelled`, `event_capacity_released`, `offer_services_after_registration`, `service_provider_data_requested`
- Other modules (Accommodation, Transport) subscribe via listeners (no hard imports inside Events), enabling modular integration.
- `app/events/signals.py` re-exports from `signal_handlers.py` for backwards compatibility.


## 7) Concurrency & Capacity Control (from 2026-04-11 updates)

Goals: prevent overselling and handle AFCON-scale concurrent registrations.

Implemented patterns:
- Atomic SQL updates via SQLAlchemy `update()` with guard filters
- Optimistic locking using a `version` column on `TicketType`
- Distinguish unlimited vs limited capacity
  - Unlimited (capacity None/0): skip seat decrement, increment `version`
  - Limited (>0): decrement `available_seats` atomically; if no rows updated → sold out
- Capacity release on cancellations/expiry uses capped atomic increments that never exceed `capacity`
- Retry logic and idempotency for transient failures/duplicate submissions

Verification (per source doc):
- Concurrency scripts and tests validated that successful registrations match capacity, with rejections when full
- Signal connectivity verified (loose coupling in place)


## 8) Templates & Dashboards

Not exhaustive, but commonly used templates include:
- templates/events/admin: `dashboard.html`, `events.html`
- templates/events/organizer: `waitlist.html`, `my_events.html` (references `events.my_events` route which exists in routes)
- Public landing/listing templates referenced by routes

Dashboards:
- Attendee dashboard (service method `get_attendee_dashboard_data`)
- Organizer dashboard (service method `get_organizer_dashboard_data`)
- Service provider dashboard (service method `get_service_provider_dashboard_data`)
- Admin dashboard (route `admin_dashboard`, service `get_admin_dashboard_data`)


## 9) Known Gaps, Assumptions, and Open Items

Cross-checked notes vs current codebase; here is what to keep an eye on:
- Docs vs Code parity
  - Earlier audit notes questioned existence of several routes (e.g., `events.list`, `events.landing`, `events.create_event`); these now exist in `routes.py`.
- Concurrency verification scripts
  - The README mentioned `verify_concurrency.py`, `test_concurrency.py`, etc. Ensure these helper scripts/tests are available in your repo/scripts if you rely on them in CI; otherwise, consider porting their core checks into unit tests.
- Signal listeners in other modules
  - Docs cite listeners in Accommodation/Transport; verify project-specific listeners are connected in your app factory when enabling those modules.
- Security and policy
  - Some global CSP/session management concerns were raised in the wider app (outside Events). Track these centrally; Events routes/templates should inherit safe defaults.

If you spot any mismatch between this README and the code, update this document alongside code changes.


## 10) Quick Start (Developer)

- Discover/list events: use `/events/` and `/events/<identifier>`
- Create/manage events: `/events/create`, `/events/<identifier>/edit`, organizer dashboard under `/events/organizer/<identifier>`
- Registration: POST to `/events/register/<identifier>` (see route for required payload); confirm at `/events/registration-confirmation/<reg_ref>`
- Check-in: organizer/staff via `/events/<identifier>/scanner` and API `/events/api/checkin`
- Admin: `/events/admin-dashboard`, `/events/admin/events` and moderation endpoints

Key service entry points when coding:
```python
from app.events.services import EventService

# Example: get event data for landing page
edata = EventService.get_event("public_id_or_slug")

# Example: register a user (optimistic concurrency path)
registration = EventService.register_for_event_optimistic(
    identifier="public_id_or_slug",
    user_id=current_user.id,
    data={
        "ticket_type_id": 123,
        # ... other fields such as discount_code, metadata, etc.
    },
)
```


## 11) Changelog Links (historical context)

- Concurrency and SQLAlchemy fixes (2026‑04‑11): `Readme's/2026-04-11_events_concurrency_fixes.md`
- Registration/user system audit transcript referencing Events: `Readme's/registration_report2_15-04`

These sources contained overlapping details that are merged into this README.
