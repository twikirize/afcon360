# NOTIF-BELL-SYSTEM-SOUND-1 — Evidence (Notification Bell → Phone System Sound)

**Date:** 2026-09-26
**Gate reference:** Ad-hoc user request (no separate contract file); scope fixed by
the three clarification answers recorded below.
**Result:** PASS — human-confirmed on device

---

## 1. Scope (clarification answers, 2026-09-26)

1. Bell click itself: nothing broken — sound only was the ask.
2. Mechanism: **system notifications + sound** (Web Notifications API — the
   phone's own notification centre), not an in-app beep, not FCM/PWA push.
3. Triggers: new arrival (tab open), tab backgrounded, bell click with unread.

## 2. Files changed

`git diff --stat -- templates/components/notification_bell.html`:

```text
 templates/components/notification_bell.html | 112 +++++++++++++++++++-
 1 file changed, 109 insertions(+), 3 deletions(-)
```

New test file (untracked):

```text
?? tests/notifications/test_bell_system_notifications.py
```

No backend, migration, Redis, notification-service, or static-asset changes.
`app/transport/services/notification_service.py` (concurrent actor's file):
untouched.

## 3. Mechanism implemented

- Permission asked only from a user gesture: first bell click runs
  `askPermission()` → `Notification.requestPermission()`; never on page load.
- `sysNotify(title, body)`: `new Notification(..., {icon, tag:
  'afc360-unread', renotify: true})` — the OS plays its own notification
  sound on Android/iOS/desktop; `renotify` re-sounds each update instead of
  silently replacing the banner. Icon `/static/icons/icon-192.png` (exists —
  the accommodation script's `/static/images/notification-icon.png` 404s and
  was deliberately NOT copied).
- Content reuses the existing inbox API `GET /api/notifications?limit=1
  &unread_only=true` — no new backend surface.
- Arrival detection: the existing 60 s unread-count poll (a) no longer
  skips when `document.hidden` (backgrounded tabs keep announcing) and
  (b) compares `unread_count` against a watermark seeded from the
  server-rendered badge, updated on every poll and on mark-read responses
  (a read never masks the next arrival). Increase → one summarising banner.
- Bell click with unread > 0 → same banner path (`kind='unread'`).
- Denied permission → silent return; constructor throw (iOS PWA) →
  service-worker `showNotification` fallback; neither path ever raises.

## 4. Verification

```text
pytest tests/notifications → 75 passed  (incl. 10 new bell tests)
pytest tests/test_transport_driver_dashboard.py + bell file → 13 passed
python -c "from app import create_app" → APP_IMPORT_OK, exit 0
git diff --stat -- templates/components/notification_bell.html → +109 -3 (above)
```

New tests: gesture-only permission request, denial silence, OS payload
(tag + renotify), icon asset existence, inbox-API reuse, watermark wiring,
`document.hidden` guard removal, service-worker fallback, init guard,
and a real `render_template('components/notification_bell.html')` render
with a logged-in user.

Live Playwright E2E: skipped by explicit user decision (shared browser
locked by a concurrent session). Replaced by **human device verification**:

> "i checked on my phone and it brought the notification and sound"

(2026-09-26 — permission prompt, banner, and OS sound confirmed on the
user's phone.)

## 5. Environment / process

- Template-only change; dev server serves Jinja with auto-reload (DEBUG on)
  — no restart required or performed.
- No migration, no config key, no new dependency, no commit, no register
  update (register is the human's step).
- Concurrent worktree present (driver workspace consolidation, console
  removal, notification_service.py by another actor) — not touched.
