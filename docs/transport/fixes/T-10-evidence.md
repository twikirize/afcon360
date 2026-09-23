# T-10 — Evidence

## Test runs (raw output)

Command 1 (behavior proof — new file):
```
& .venv/Scripts/python.exe -m pytest tests/transport/test_moderator_actions.py -x -q --tb=short
```

Output 1:
```
[OK] Kept 3 test items from 'tests/' directory.
...                                                                      [100%]
============================== warnings summary ===============================
tests/transport/test_moderator_actions.py::test_moderate_vehicle_writes_status_directly
tests/transport/test_moderator_actions.py::test_moderate_vehicle_writes_status_directly
  .../flask_session/filesystem/filesystem.py:75: DeprecationWarning: FileSystemSessionInterface is deprecated and will be removed in a future release. Instead use the CacheLib backend directly.
    warnings.warn(
tests/transport/test_moderator_actions.py::test_moderate_vehicle_writes_status_directly
tests/transport/test_moderator_actions.py::test_moderate_vehicle_writes_status_directly
  migrations/env.py:42: DeprecationWarning: 'get_engine' is deprecated and will be removed in Flask-SQLAlchemy 3.2. Use 'engine' or 'engines[key]' instead. If you're using Flask-Migrate or Alembic, you'll need to update your 'env.py' file.
    return current_app.extensions['migrate'].db.get_engine()
tests/transport/test_moderator_actions.py::test_moderate_vehicle_writes_status_directly
tests/transport/test_moderator_actions.py::test_moderate_vehicle_writes_status_directly
tests/transport/test_moderator_actions.py::test_moderate_driver_approve_delegates_to_service
tests/transport/test_moderator_actions.py::test_moderate_booking_approve_unchanged
  .../flask_sqlalchemy/query.py:30: LegacyAPIWarning: The Query.get() method is considered legacy as of the 1.x series of SQLAlchemy and becomes a legacy construct in 2.0. The method is now available as Session.get() (deprecated since: 2.0) (Background on SQLAlchemy 2.0 at: https://sqlalche.me/e/b8d9)
    rv = self.get(ident)
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
3 passed, 8 warnings in 23.74s
```

3 passed. Warnings are pre-existing DeprecationWarnings/LegacyAPIWarnings from third-party
libraries and migrations/env.py; unrelated to this change.

Command 2 (regression suite):
```
& .venv/Scripts/python.exe -m pytest tests/test_transport_service_integrity.py -x -q --tb=short
```

Output 2:
```
[OK] Kept 49 test items from 'tests/' directory.
.................................................                        [100%]
============================== warnings summary ===============================
tests/test_transport_service_integrity.py::TestListAllBookings::test_returns_empty_when_no_bookings
tests/test_transport_service_integrity.py::TestListAllBookings::test_returns_empty_when_no_bookings
  .../flask_session/filesystem/filesystem.py:75: DeprecationWarning: FileSystemSessionInterface is deprecated and will be removed in a future release. Instead use the CacheLib backend directly.
    warnings.warn(
tests/test_transport_service_integrity.py::TestListAllBookings::test_returns_empty_when_no_bookings
tests/test_transport_service_integrity.py::TestListAllBookings::test_returns_empty_when_no_bookings
  migrations/env.py:42: DeprecationWarning: 'get_engine' is deprecated and will be removed in Flask-SQLAlchemy 3.2. Use 'engine' or 'engines[key]' instead. If you're using Flask-Migrate or Alembic, you'll need to update your 'env.py' file.
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
49 passed, 4 warnings in 126.83s (0:02:06)
```

49 passed. Warnings are pre-existing and unrelated.

## What the new tests prove

tests/transport/test_moderator_actions.py (3 tests, marker usefixtures("db_session")):

1. test_moderate_vehicle_writes_status_directly
   - POST /transport/moderate/vehicle/<id>/approve as a moderator-only user → 302,
     then vehicle.status == "active".
   - POST .../reject with {"reason": "duplicate listing"} → 302, then vehicle.status
     == "rejected".
   - Proves the moderate path writes the real status column directly; it does NOT
     go through ProviderService.update_vehicle_status (no permission gate).
2. test_moderate_driver_approve_delegates_to_service
   - POST /transport/moderate/driver/<id>/approve as moderator → 302, then
     DriverProfile.compliance_status == ComplianceStatus.APPROVED.
   - Proves delegation to ProviderService.update_driver_status produces the real
     DB effect.
3. test_moderate_booking_approve_unchanged
   - POST /transport/moderate/booking/<id>/approve as moderator → 302, then
     Booking.status == BookingStatus.CONFIRMED.
   - Proves the booking branch is preserved (unchanged by design).

## Facts verified during diagnosis (unchanged code)

- Vehicle has status but no verification_status/verified_at/rejection_reason columns.
- DriverProfile has compliance_status/verification_tier and no such columns either.
- ProviderService.update_vehicle_status carries @require_permission('vehicle:update_status')
  which is granted to no role (owner-only effective); the moderator route must not
  delegate vehicle through it (BL-16).
- Admin moderator twin at app/admin/moderator/routes.py writes entity.status directly
  with a hasattr guard for verified_at — the moderate_action vehicle branch now matches
  that twin.

## Working-tree reconciliation performed this session

- app/transport/services/provider_service.py was modified by a prior session to REMOVE
  the vehicle:update_status permission guard. That removal was not required by the
  ratified Option B decision and was reverted to HEAD (git checkout). The moderate
  vehicle branch writes columns directly instead, so no permission change was needed.
- A stale untracked test file tests/test_transport_moderate_action_delegation.py
  (asserting the superseded vehicle-delegation shape) was deleted; replaced by
  tests/transport/test_moderator_actions.py above.
- BACKLOG.md BL-16 corrected: the permission gate was NOT removed in T-10; entry stands
  as an open deferred item (admin approve/reject routes still 500 for non-owners).

## Residual risk

- The 9 POST forms (templates/transport/moderate_*.html) were not modified; their
  field names remain compatible, so no template change was required. Verified by
  reading the forms (name="reason" on reject forms) — not covered by an automated test.
- The test authenticates by setting the Flask-Login session cookie directly; it does not
  exercise the real login screen. Coarse before_request gating for these endpoints is
  covered only by the fact that the moderator-only session reaches the route handler.