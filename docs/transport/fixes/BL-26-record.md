# BL-26 — Record (moderator booking lifecycle contract)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23

## Contract source (existing, not invented)

- STATUS_TRANSITIONS (api/booking_routes.py:34-46, now owned by
  booking_service): PENDING_PAYMENT→{CONFIRMED,CANCELLED},
  CONFIRMED→{ASSIGNED,CANCELLED}, ASSIGNED→{DRIVER_EN_ROUTE,CANCELLED},
  DRIVER_EN_ROUTE→{PICKUP_ARRIVED,CANCELLED}, IN_PROGRESS→
  {COMPLETED,DISPUTED}, terminal COMPLETED/CANCELLED/NO_SHOW → none,
  DISPUTED→{COMPLETED,CANCELLED}.
- AssignmentService.release: terminal ∈ {COMPLETED,CANCELLED,NO_SHOW};
  assigned branch requires ACTIVE_ASSIGNMENT_STATUSES, clears
  assigned_* and frees resources with late-release protection.
- E6 (d5 header): moderator booking actions operate through the
  guarded release path.

## Before-fix proof (4 failures, exact)

- :836 assigned_driver_id == 510, expected None (no release).
- :865 IN_PROGRESS → 'cancelled' (must stay in_progress).
- :892 COMPLETED → 'cancelled' (must stay completed).
- :910 confirmed_at None (must be set on approve).

## Minimal change (one authoritative path, no new machine)

- booking_service.py: owns STATUS_TRANSITIONS + _can_transition (moved,
  single definition) and new BookingService.transition_status static:
  map gate → release() for assigned terminal transitions (timestamps
  ride along in release's commit, as the endpoint did) → timestamps +
  cancel fields + audit_log otherwise. Typed errors.
- api/booking_routes.py BookingStatusResource: delegates to the
  service; HTTP shapes preserved (400/404/422+allowed/409+code/200
  with release payload); dead local map/helper/import removed.
- admin moderator booking branch: approve PENDING_PAYMENT→CONFIRMED
  via service (confirmed_at), CONFIRMED idempotent no-op, DISPUTED
  resolve preserved as-is; reject → service with initiated_by=
  "moderator". Refusals flash + redirect unchanged.
- No new statuses/models/migrations; vehicle/driver branches, guards,
  notifications, wallet/KYC/GEO/fare/matching untouched.

## After-fix behavior (d5 green, unmodified tests)

- ASSIGNED reject → CANCELLED + assigned_* None + cancelled_at +
  reason + initiated_by 'moderator' + driver/vehicle available.
- IN_PROGRESS / COMPLETED reject → refused, state + resources held.
- PENDING_PAYMENT approve → CONFIRMED + confirmed_at; re-approve
  no-op; executing approve refused.
- Only BookingStatusResource + moderator action perform booking
  transitions (transport surface delegates; no duplicate logic).

## Tests

- d5 full file: 26 passed (was 22+4 failed).
- moderator_actions: 16 passed. integrity: 49 passed.
- Full suite NOT run.

## Startup

create_app() green; transport_api.booking_status + all moderator
endpoints registered; service imports resolve.

## Backlog

BL-26 → Done. No new items; no product rule invented (map + E6
decided every case).

Gate: BL-26: PASS
