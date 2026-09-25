# CONSOLIDATED REVIEW — Record (auth/permissions/moderation/notifications)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23
Scope:           reconcile only — no architecture, schema, wallet, KYC,
                 dispatch, matching, or fare changes.

## Reconciliation

- require_role fallback (decorators.py:280): `is_super_admin()` ✓.
  tests/test_auth_require_role.py 7 passed.
- Permission siblings (decorators.py:841; routes.py:1757/:1849):
  `is_super_admin()` ✓. Deny paths (decorator/grant/revoke, no
  mutation) + owner/super-admin allow paths proven by
  tests/test_bl23_transport_permission_guards.py 13 passed.
- Redirects: no live `auth.index` (endpoint never existed); success →
  admin.transport_admin_dashboard, deny → user.dashboard; both
  registered and resolving; all four grant/revoke paths return clean
  302s with correct mutations (proven in the 13).
- Audit API: grant/revoke use ForensicAuditService.log_attempt with
  valid params (routes.py:1806/1869); authorized paths prove
  mutation → audit → clean response (same 13).
- BL-19 reversal: reason fields restored on vehicle/driver reject
  forms; reason required for all three entity types; vehicle/driver
  reasons captured via _audit_rejection_reason (audit trail,
  best-effort); no column invented, no migration. Booking
  (cancellation_reason) + flag (create_flag) unchanged.
  tests/transport/test_moderator_actions.py 7 passed (3 T-10 + 4
  rewritten BL-19: require-bounce, with-reason accept + audit call,
  field presence, booking preservation).
- BL-22: transport driver branch resolves Booking.driver → user_id
  (uncommitted hunk @@ -1976,7 +1976,14, verified present);
  DriverProfile.id ≠ User.id proven in-test; notification reaches the
  driver User. 1 + 4 + 49 passed.
- Signal gap: transport_driver_assigned has a listener but NO
  producer in app/ (verified by search) → recorded as BL-24
  (Deferred). Nothing wired (out of scope by design).

## Verification totals

- test_auth_require_role.py: 7 passed
- test_bl23_transport_permission_guards.py: 13 passed
- test_moderator_actions.py: 7 passed
- test_notify_driver_assigned_bl22.py + test_notifications_transport_payloads.py: 5 passed
- test_transport_service_integrity.py: 49 passed
- Startup: create_app() green; 8/8 affected endpoints registered;
  both redirect targets resolve. Full suite NOT run.

## Backlog state

- AUTH-REQUIRE-ROLE-FALLBACK (SEC-FALLBACK): Done (unchanged)
- BL-23: Done (unchanged)
- AUTH-REDIRECT-INDEX: Done (unchanged)
- BL-19: Deferred (reconciled; history preserved)
- BL-22: Done (unchanged; hunk still uncommitted)
- BL-24 (new): Deferred — signal production emission

## Files changed this run

- templates/transport/moderate_vehicle.html (+4: reason field restored)
- templates/transport/moderate_driver.html (+4: reason field restored)
- app/transport/routes.py (+helper + gate restore + audit capture)
- tests/transport/test_moderator_actions.py (4 BL-19 tests rewritten)
- BACKLOG.md (BL-19 → Deferred; BL-24 added)
- docs/transport/fixes/CONSOLIDATED-REVIEW-record.md (new)

Gate: CONSOLIDATED REVIEW: PASS
