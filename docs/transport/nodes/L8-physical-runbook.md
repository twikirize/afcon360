# L8 Physical Runbook — Driver Background Location (D3)

Human-executed. No application changes. No server restart.
Target: live HTTPS server on port 5443 (verified listening 2026-09-29).
Phone: existing Android driver phone, same hotspot/WLAN as the laptop.

## 0. Prerequisites (check all before starting)

- [ ] Laptop can open the AFCON360 login page over HTTPS on port 5443.
- [ ] Phone is on the same hotspot/WLAN and can open the same HTTPS origin.
- [ ] A driver account with an assigned DriverProfile exists; the driver can
      log in on the phone browser/PWA and toggle Online.
- [ ] Laptop Chrome can reach `chrome://inspect` (USB debugging enabled on
      the phone, or same-network port-forwarded inspect session).
- [ ] Admin access on the laptop for
      `GET /transport/drivers/<id>/location` (reads `location_updated_at`).
- [ ] A stopwatch/clock with seconds; record ALL times as HH:MM:SS.

## 1. Foreground baseline (do not skip)

1. On the phone, open the driver workspace (`/transport/driver-dashboard`),
   log in, toggle **Online**.
2. Confirm the location badge (`#dcLocBadge`) shows a publishing state
   (e.g. "Location available … Publishing every 120s." or "Published …").
3. On the laptop admin page for this driver, record `location_updated_at`.
4. Wait through **two** publish ticks and record both `location_updated_at`
   values. Expected: cadence ≈ 120 s (the `data-ping-interval` default).
5. Baseline outputs: `T_base1`, `T_base2`, badge text. If publishing never
   starts in the foreground, STOP — that is a D2/foreground issue, not L8.

## 2. Remote-debug attach (laptop)

1. Open `chrome://inspect`, attach DevTools to the phone's PWA tab.
2. In DevTools Console, paste the observer snippet below (observe only —
   it installs listeners, changes no application behaviour):

```js
window.__L8 = { events: [] };
['pagehide', 'pageshow', 'visibilitychange'].forEach(function (t) {
  window.addEventListener(t, function (e) {
    window.__L8.events.push({
      t: t, at: new Date().toISOString(),
      hidden: document.hidden,
      persisted: (t === 'pageshow') ? e.persisted : undefined
    });
  });
});
var __l8tick = 0;
setInterval(function () {
  __l8tick++;
  window.__L8.events.push({ t: 'probe-tick', n: __l8tick,
    at: new Date().toISOString(), hidden: document.hidden });
}, 30000);
```

3. Keep the DevTools Network tab recording (filter: location).

## 3. Variant V1 — app-switch (home button, other app in front)

1. Record time `T_bg1`. Press Home, open another app, leave PWA hidden
   for **10 minutes** (covers the 5-minute intensive-throttle threshold
   and the 300 s freshness TTL).
2. At T_bg1+5min and T_bg1+10min, record on the laptop admin page:
   `location_updated_at` and its age in seconds. Do NOT touch the phone.
3. Record time `T_fg1`, return to the PWA (tap its task, no reload).
4. Record: badge text at return, `T_first_post1` (first fresh POST after
   return per Network tab / `location_updated_at` advance), whether any
   reload or online-toggle flick was needed (expected: none).
5. In DevTools run `JSON.stringify(window.__L8.events)` and save it.
   Record: pagehide fired Y/N; pageshow fired Y/N (+ `persisted` value).

Expected V1: POSTs stop while hidden; `location_updated_at` age exceeds
300 s (stale, truthful); on return, publishing resumes on its own.

## 4. Variant V2 — screen-off (lock)

Repeat §3 with the screen locked instead of app-switch:
`T_bg2` (lock) → observe at +5/+10 min via laptop admin page → `T_fg2`
(unlock, PWA still the foreground task, no reload) → `T_first_post2` →
save `window.__L8.events`.

Expected V2: same as V1, possibly with longer gaps (device sleep may halt
JS entirely; any 1/min throttled ticks are platform behaviour, not app
publishing — verify via Network tab: throttled timer ticks without a
fresh fix must NOT produce POSTs).

## 5. Per-variant record sheet (copy once per variant)

```text
Variant: V1 / V2
T_bg:            HH:MM:SS
Admin age +5min: ___ s   location_updated_at: ___
Admin age +10min: ___ s  location_updated_at: ___
T_fg:            HH:MM:SS
Badge at return: <exact text>
T_first_post:    HH:MM:SS (or NONE within 5 min)
Reload needed:   Y / N
Toggle needed:   Y / N
pagehide fired:  Y / N
pageshow fired:  Y / N   persisted: true / false / n/a
```

## 6. Decision tree (map observations → cause)

- **POSTs stop in background AND resume alone on return, no pagehide
  recorded** → platform throttling (Chrome timer/geolocation limits).
  The pagehide gap is REJECTED for this path. No code change.
- **No resume without reload/toggle AND pagehide WAS recorded with no
  (or persisted=false) pageshow recovery** → pagehide restart gap
  CONFIRMED. The proposed `pageshow` restart becomes eligible for a
  decision (still needs explicit authorization — do not implement here).
- **Both** (throttled ticks visible but no recovery even though the page
  was never hidden-killed) → record exact event log; escalate, do not
  invent a workaround.
- **Neither** (publishing continued in background with fresh fixes) →
  record device/Chrome versions; finding contradicts the platform model
  and must be re-verified before any conclusion is drawn.

## 7. iOS note (uncharacterized — do NOT generalize Android results)

If an iPhone is available, run §1–§6 verbatim on iOS Safari/Chrome and
record on a SEPARATE sheet labelled iOS with device + OS + browser
versions. Android Chrome findings in this node are not valid for iOS.

## 8. Close-out

Hand back: two (or three) filled record sheets, the saved
`window.__L8.events` logs, and the decision-tree verdict per variant.
Do not change code, do not change tests, do not restart the server.
