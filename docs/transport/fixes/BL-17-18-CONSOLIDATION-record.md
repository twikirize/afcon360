# BL-17/18 — Record (moderator surface consolidation)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23
Direction:       RETIRE transport.moderate*; KEEP canonical
                 admin.moderator.transport_* (per audit verdict, verified).

## UNDERSTAND / MAP

- Transport surface: 5 routes (moderate, moderate_booking/vehicle/
  driver, moderate_action), guard login+require_moderator, templates
  transport/moderate*.html (self-links only, no sidebar entry).
- Canonical surface: dashboard + 3 queues + 3 detail views + action
  endpoint, guard login+require_role(moderator,admin,super_admin,
  owner), sidebar entry base_moderator.html:811-813, 15+ forms across
  7 templates — all self-contained (no template references the
  transport surface).
- Only cross-surface live links: moderator registry review_url_fn
  (registry.py + transport/__init__.py) → repointed to admin views.
- Only test consumers: tests/transport/test_moderator_actions.py +
  tests/test_transport_d5_execution_lifecycle.py (legacy booking URLs).

## PROVE (duplication + pre-fix defects)

- Audit verdict TRUE DUPLICATE confirmed against current code; intended
  audience identical; post-SEC-FALLBACK both guards admit exactly the
  four roles (guard matrix proven: plain → denied+unchanged on both).
- 7 twin tests written pre-fix: 7 failed — driver view 500
  (Booking.filter_by(driver_id), nonexistent), driver search 500
  (phantom name/email/phone columns), reject unaudited, suspend
  half-persisted, driver-approve tier-only, reject forms reason-less.
- Suspend phantom fields classified NONEXISTENT repo-wide:
  suspension_reason/suspended_at on neither model; driver is_active
  transient. Verb preserved per BL-19 lesson.

## MINIMAL CHANGE

Canonical (admin/moderator/routes.py):
- view_transport_driver: driver_id → assigned_driver_id (was 500).
- transport_drivers search: phantom columns → driver_code (+ truthful
  placeholder).
- Driver approve/reject merged with transport semantics (tier +
  service compliance calls) so delegation regresses nothing.
- Reject (all types): reason required + audit-captured
  (_audit_moderation_reason); booking model persistence kept.
- Suspend: real is_available=False both + audit-captured reason;
  phantom writes removed (recorded as BL-25).
- view title: driver_code (first_name/last_name nonexistent; display
  enrichment is follow-up).
Canonical templates: required reason inputs (+ labels) on all 5
reject forms (driver/vehicle top+bottom, booking bottom).
Retirement (transport/routes.py, registry x2):
- moderate_action delegates to canonical (guards preserved).
- moderate + 3 detail GETs redirect to canonical equivalents (guarded).
- Registry review URLs → admin views (both files).
- Deleted templates/transport/moderate{,_{booking,vehicle,driver}}.html
  (zero consumers remaining; docs references kept as history).

## Records / backlog

- BL-17, BL-18 → Done. BL-19 stays Deferred (canonical reject now
  audit-captures too — consistent).
- BL-25 (phantom suspend fields → migration batch), BL-26 (booking
  reject lifecycle gap; 4 pre-existing d5 failures, not hidden).
- d5 TestModeratorBookingActions: 4 failed / 22 passed — failures
  proven pre-existing (identical writes on both implementations;
  desired release/guard contract implemented nowhere).

## Verification

- tests/transport/test_moderator_actions.py: 16 passed.
- tests/test_transport_service_integrity.py: 49 passed.
- tests/test_transport_d5_execution_lifecycle.py: 22 passed, 4 failed
  (pre-existing, recorded as BL-26).
- Startup: create_app() green; all 11 moderator endpoints registered
  (6 canonical + 5 legacy-redirect); legacy detail GETs 302 to
  canonical (asserted); canonical views GET 200 (asserted).
- Authorization preserved: require_role/require_moderator untouched;
  plain denied both surfaces, moderator allowed both.

## Residual risk / follow-ups

- Driver display names blank on canonical views (no name columns;
  code shown). Display enrichment is follow-up, not a 500.
- Concurrent Fix-2.2 circuit-breaker work
  (external_platforms.py + test_directions_circuit_breaker.py) and
  Fix-2.2-contract.md edits are NOT this node's — preserved untouched.
- BL-19 audit helper removed from transport routes with delegation
  (single audit path now; history in BL-19 record).

Gate: BL-17/18 MODERATOR CONSOLIDATION: PASS
