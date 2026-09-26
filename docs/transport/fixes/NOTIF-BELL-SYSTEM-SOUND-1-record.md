# NOTIF-BELL-SYSTEM-SOUND-1 — Record (Notification Bell → Phone System Sound)

Status:          PASS (human-confirmed on device, 2026-09-26)
Date:            2026-09-26
Owner:           [your name]

Files changed:
  - templates/components/notification_bell.html   (+109 -3: system-notification
    machinery, gesture permission, arrival watermark, backgrounded polling,
    bell-click unread notice)
  - tests/notifications/test_bell_system_notifications.py   (new, 10 tests)
  - docs/transport/fixes/NOTIF-BELL-SYSTEM-SOUND-1-evidence.md   (new)
  - docs/transport/fixes/NOTIF-BELL-SYSTEM-SOUND-1-record.md   (new)

Evidence:
  See docs/transport/fixes/NOTIF-BELL-SYSTEM-SOUND-1-evidence.md

Behavior summary:
  The universal notification bell now raises phone system notifications
  (banner + OS sound) via the Web Notifications API:
  - first bell click (user gesture) requests permission;
  - a rise in unread_count — detected by the existing 60 s poll, which now
  - keeps running while the tab is hidden — posts one summarising banner
    built from the newest unread item of the existing /api/notifications
    inbox API;
  - bell click with unread > 0 posts the same notice;
  - tag afc360-unread + renotify:true makes the OS re-sound every update;
  - denied permission / unsupported API degrades to silence, never an error.
  Server side, wallet, push channel, and notification preferences untouched.

Verification:
  pytest tests/notifications → 75 passed (10 new contract/render tests).
  pytest tests/test_transport_driver_dashboard.py + bell file → 13 passed.
  python -c "from app import create_app" → APP_IMPORT_OK.
  Live E2E via Playwright skipped (browser locked by concurrent session);
  replaced by human device check: "i checked on my phone and it brought the
  notification and sound".

Residual risk:
  Hidden-tab timers are browser-throttled to ~1/minute, so background
  arrivals can ring up to ~60 s late. iOS Safari in a normal tab has no
  Notification API (works only as a home-screen PWA, service-worker path).
  OS sound follows the phone's own notification-sound setting.

Follow-ups:
  - DRIVER-OFFER-UX-REPAIR-1E still awaits human PASS confirmation
    (evidence/record not yet written for that node).
  - 12 concurrent-actor test failures (test_driver_console x4 — route
    removed; test_driver_workspace_sections x8 — in-flight consolidation)
    belong to that actor's node; recorded, not fixed here.
  - Split-node leftovers: BACKLOG entries, HTTPS restart + live verify of
    rider/admin page split.

Gate reference:
  Ad-hoc user request, 2026-09-26; scope per recorded clarification answers.
