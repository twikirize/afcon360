# BL-22 — Evidence (driver never notified on assignment)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23
Scope:           one function (notify_driver_assigned driver branch),
                 one correction, one regression test
Last item of the current cleanup batch — no further cleanup started.

## 1. UNDERSTAND

- BACKLOG.md §BL-22 (Not started, raised 2026-09-23 NOTIF-TRANSPORT
  Part 3, DEFERRED / NOTIFICATIONS, owner Notifications, record-only
  authorization, implemented under this EGGE cleanup node).
- Current implementation (worktree app/notifications/services.py:1979):
  `driver_id = getattr(booking, 'driver_id', None)` for ALL modules,
  then `cls.send(user_id=driver_id, ... "New Trip Assigned" ...)`.
- send() semantics (services.py:289): user_id is "Target user's
  internal ID (BigInteger)" → looks up User. A DriverProfile id here
  would misaddress, not just miss.

## 2. MAP (assignment → booking → notification)

- AssignmentService.dispatch_claim (assignment_service.py:148-153):
  `assigned_driver_id=driver_id` where driver_id is a DriverProfile.id
  (r2 matches DriverProfile.__table__.c.id). Authoritative source.
- Booking.assigned_driver_id: plain BigInteger (models.py:1089);
  Booking.driver relationship joins DriverProfile via that column
  (models.py:1134-1138). No driver_id attribute/column on transport
  Booking. So the old getattr always yielded None → driver branch dead.
- Naive `assigned_driver_id`-as-user_id would be WRONG (profile id ≠
  user id); the canonical resolution is Booking.driver → user_id
  (DriverProfile.user_id FK → users.id, models.py:272).
- Sole caller of notify_driver_assigned: listeners.py:269 via the
  transport_driver_assigned blinker signal (signals.py:41).

## 3. TRACE (authoritative source)

dispatch_claim sets assigned_driver_id (DriverProfile.id) →
signal/listener passes the Booking → notify_driver_assigned must
address DriverProfile.user_id. No new relationship introduced; the
existing Booking.driver relationship is the single source of truth.
Non-transport branch (`booking.driver_id`) unchanged.

## 4. PROVE (before fix — behavioral, real rows)

tests/test_notify_driver_assigned_bl22.py (new): real rider User, real
driver User + DriverProfile, real ASSIGNED Booking with
assigned_driver_id=profile.id (asserted ≠ driver user id), signal
emitted through the wired listener, send/_notify_admins stubbed
(canonical seam). Pre-fix result: FAILED —
"assigned driver user received no notification (calls went to [949,
949])": rider notified twice, driver never. Wrong-recipient (nobody)
proven, not just a missing attribute.

## 5. MINIMAL CHANGE (isolated hunk @@ -1976,7 +1976,14)

```python
if is_transport:
    driver_profile = getattr(booking, 'driver', None)
    driver_id = getattr(driver_profile, 'user_id', None)
else:
    driver_id = getattr(booking, 'driver_id', None)
```
No redesign, no schema/migration, no dispatch/matching/offer/
eligibility change; wallet/GEO/auth untouched; other notification
handlers untouched. data booking_id/link/admin broadcast already
correct from concurrent NOTIF-TRANSPORT work (verified, not re-done).

## 6. VERIFY (after fix)

- New BL-22 test: 1 passed (driver user addressed + booking ref).
- Existing notification work: test_notifications_transport_payloads.py
  4 passed (untouched, still green).
- Transport regression: test_transport_service_integrity.py 49 passed.
- Integration: signal → listener → function → driver-user proven in
  the regression test with a real assigned booking. Full suite NOT run.
- Production-emission note (follow-up, NOT fixed — out of scope "do
  not build a new dispatch integration"): no producer of the
  transport_driver_assigned signal exists in app/ today; the live
  dispatch_claim path notifies the PASSENGER via _notify_assigned →
  send_transport_notification. So the corrected function is reachable
  via its hook but nothing emits that hook in production yet.

## 7. STARTUP

create_app() completes; NotificationService.notify_driver_assigned
present; listeners module imports (hook connected).

## 8. GATE

BL-22: PASS — defect confirmed; authoritative source identified;
minimal fix applied; regression test added/passed; driver user owns
the notification; existing behavior intact; transport tests pass;
startup succeeds; no unrelated files altered.
