# T-10 — Record

Status:          PASS
Commit:          none (not requested; working tree only)
Date:            2026-09-22
Owner:           agent + human (decision ratified in working session)

Node scope:
  transport.moderate_action (app/transport/routes.py) — Vehicle and Driver
  branches persisted nothing on approve/reject because the old body wrote
  verification_status / verified_at / rejection_reason, none of which are real
  columns on Vehicle or DriverProfile. Fix the Vehicle and Driver branches;
  leave the Booking branch and flag branch unchanged.

Files changed:
  - app/transport/routes.py                                (moderate_action Vehicle/Driver branches)
  - tests/transport/test_moderator_actions.py              (new, 3 tests)
  - docs/transport/fixes/T-10-evidence.md                  (new)
  - docs/transport/fixes/T-10-record.md                    (new)
  - BACKLOG.md                                             (BL-16 corrected; see note)

Reported as already-in-working-tree from the prior session (NOT authored this
session; evaluated against scope):
  - app/transport/routes.py _PUBLIC_ENDPOINTS              (+5: transport.moderate,
                                                            moderate_booking, moderate_vehicle,
                                                            moderate_driver, moderate_action)
  - BACKLOG.md BL-17, BL-18                                (deferred-work records)

Concurrent working-tree state (NOT T-10; appeared during this session from an
external process; verified untouched by me — do not treat as T-10 output):
  - app/transport/routes.py bookings_index rewrite         ("Rider My Trips": get_user_bookings,
                                                            _split_rides, _parse_ride_time)
  - templates/transport/bookings/index.html                (large rewrite, 233 lines)
  - tests/test_transport_my_trips_page.py                  (untracked)
  These belong to a separate My Trips workstream sharing the same routes.py file.
  No overlap with the functions this node changed; the 49-pass integrity suite
  ran against the combined tree.

Reverted this session (was NOT part of the ratified decision):
  - app/transport/services/provider_service.py             (removal of
                                                            @require_permission('vehicle:update_status')
                                                            on update_vehicle_status) — restored to HEAD.
  - tests/test_transport_moderate_action_delegation.py     (stale untracked file asserting the
                                                            superseded vehicle-delegation shape) — deleted.

Evidence:
  See docs/transport/fixes/T-10-evidence.md

Runtime verification:
  `& .venv/Scripts/python.exe -m pytest tests/transport/test_moderator_actions.py -x -q --tb=short`
  → 3 passed, 8 warnings in 23.74s
  `& .venv/Scripts/python.exe -m pytest tests/test_transport_service_integrity.py -x -q --tb=short`
  → 49 passed, 4 warnings in 126.83s

Behavior change:
  - Vehicle approve:  writes item.status = 'active' (real column) + commit; sets
    verified_at when the column exists (hasattr guard, matching the admin
    moderator twin). No longer depends on the dead vehicle:update_status
    permission gate.
  - Vehicle reject:   writes item.status = 'rejected' + reason -> rejection_reason
    (hasattr guard) + commit.
  - Driver approve:   delegates to ProviderService.update_driver_status(id, 'approved')
    — the same implementation the admin approve routes use.
  - Driver reject:    delegates to update_driver_status(id, 'rejected').
  - Booking branch:   unchanged by design (confirmed status 'confirmed' / 'cancelled').
  - Flag branch:      unchanged.
  - Redirect:         final return redirect(redirect_url) (was url_for('transport.moderate')).
  - No schema change. No migration. No template change.

Note on BL-16:
  The prior session recorded the vehicle:update_status guard as "removed in T-10".
  That removal was outside the ratified decision and was reverted. BL-16 was
  corrected to reflect reality: the guard is still present, the moderator vehicle
  branch no longer crosses it (direct column write), and the admin
  approve_vehicle/reject_vehicle routes still 500 for non-owner admins via that
  exact chain. That latent admin-route bug is the deferred follow-up.

Residual risk:
  The 9 POST forms (templates/transport/moderate_*.html) are untouched; their
  field names remain compatible (reject forms submit name="reason"). This was
  verified by reading the templates, not by an automated template test. The test
  authenticates via session cookie injection (standard Flask test client
  technique), so the login screen itself is not exercised. Coarse before_request
  gating for these endpoints is only verified to the extent that a moderator-only
  session reaches the route handler.

Follow-ups:
  - BL-16: admin approve_vehicle/reject_vehicle (routes.py:2305/2334) still 500
    for non-owner admins — grant/seed vehicle:update_status or drop the guard to
    match update_driver_status precedent (DRIVER_GATE-3).
  - BL-17: two moderator surfaces do the same job (transport.moderate_action vs
    admin/moderator/routes.py transport_moderate_action) — choose one canonical.
  - BL-18: no nav entry reaches the transport moderation surface
    (base_moderator.html:786-807) — add one or retire the surface.
  - Consider retiring transport.moderate in favor of the admin twin.

Migration:  none required.

Gate reference:
  T-10 — transport moderator moderate_action real-column fix. GATE = PASS:
  behavior proof (3) + regression suite (49) green; scope held to routes.py +
  new test file (+ evidence/record/BACKLOG documentation); no schema/wallet/
  template changes.