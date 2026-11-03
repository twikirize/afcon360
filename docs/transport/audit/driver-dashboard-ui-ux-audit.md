# Driver Dashboard — UI/UX Audit Report

**Date:** 2026-11-01  
**Auditor:** OpenCode Agent  
**Scope:** `/transport/driver-dashboard` — full driver workspace  
**Benchmark:** Uber Driver, Bolt Driver, DiDi Driver, Go (Gojek) Driver apps (iOS/Android + PWA)

---

## 1. Executive Summary

| Dimension | Score (1–5) | Industry Parity |
|-----------|-------------|-----------------|
| Information Architecture | 3 | ⚠️ 7 tabs vs. 4–5 standard |
| Primary View (Home) | 2 | ❌ No map, no demand viz |
| Ride Request UX | 2 | ❌ Inline card vs. full-screen takeover |
| Earnings Transparency | 2 | ❌ Static totals only |
| Vehicle Management | 3 | ⚠️ Basic list, no health/expiry |
| Safety & Trust | 1 | ❌ No safety toolkit |
| Mobile-First Execution | 4 | ✅ Drawer + dock, touch targets |
| Real-Time Systems | 5 | ✅ Best-in-class GPS/publish |
| Accessibility | 3 | ⚠️ ARIA gaps in dynamic areas |
| Performance (PWA) | 4 | ✅ SW, install, BFCache-safe |

**Overall:** Strong engineering foundation, **significant UX debt** vs. market leaders. The backend architecture (independent GPS/publish lifecycles, CSRF hardening, BFCache safety) is production-grade. The frontend lacks the **map-centric, driver-first mental model** that defines Uber/Bolt/DiDi/Go.

---

## 2. Current State — Screen Inventory

| Panel | Route | Purpose | Key Components |
|-------|-------|---------|----------------|
| **Home** | `/driver-dashboard` (default) | Identity, focus card, location status, metrics, offers, upcoming | Hero, focus card (state-driven), location card, 5 stat cards, offers list, upcoming trips, opportunities, scheduled routes |
| **Status** | `#status` | Online toggle, operational prefs | Large toggle, driving mode, vehicle classes, zones, capacity, auto-accept, concurrency |
| **Trips** | `#trips` | Active, upcoming, recent, all trips | Active trip card with actions, upcoming list, recent with cash confirmation, full history |
| **Earnings** | `#earnings` | Total captured + performance scores | Big total, reliability/safety/acceptance/cancellation rates, distance, duration, ratings |
| **Assignments** | `#assignments` | Current vehicle, scheduled routes, history, switch | Assigned vehicle card, scheduled routes list, 90-day history, switchable vehicles |
| **Vehicles** | `#vehicles` | Owned vehicles, switch, history, marketplace | Owned list with edit/view, switch duplicate, 90-day history, marketplace browse |
| **Account** | `#account` | Profile, compliance, documents, settings | Driver code, verification tier, license, documents, bank, tax, notifications, delete account |

**Navigation:** Left sidebar (desktop) → off-canvas drawer + bottom dock (≤900px). 7 top-level items.

---

## 3. Industry Benchmark — What Leaders Do

### 3.1 Navigation Patterns (2024–2025)

| App | Primary Tabs (Bottom/Left) | Secondary (More/Profile) |
|-----|---------------------------|--------------------------|
| **Uber Driver** | Home (map), Earnings, Trips, Account | Vehicle, Support, Safety, Settings |
| **Bolt Driver** | Home (map), Earnings, Trips, More | Vehicle, Documents, Support, Settings |
| **DiDi Driver** | Home (map), Orders, Income, Me | Vehicle, Service, Safety, Settings |
| **Go (Gojek) Driver** | Home (map), Earnings, Trips, Vehicle | Profile, Support, Safety, Settings |

**Pattern:** **4–5 primary destinations**. Map is *always* Home. Vehicle is either primary (Go) or secondary (Uber/Bolt/DiDi). Status/assignments are *inline* in Home or Vehicle, not separate tabs.

### 3.2 Home View — Map-Centric Mental Model

```
┌─────────────────────────────────────┐
│  [≡]  AFCON360 Driver    [🔔] [⬇] [↻]  │  ← Topbar (persistent)
├─────────────────────────────────────┤
│                                     │
│      ┌─────────────────────┐        │
│      │     DEMAND MAP      │        │  ← Full-bleed map
│      │  [🔥 surge zones]   │        │     • Driver pulsing blue dot
│      │  [📍 nearby pins]   │        │     • Heatmap overlay (red→yellow)
│      │                     │        │     • Surge multipliers (1.5×, 2.0×)
│      └─────────────────────┘        │
│                                     │
│  ┌─────────────────────────────┐    │  ← Bottom sheet (draggable)
│  │ 🟢 GO ONLINE        $42/hr  │    │     • Primary CTA (thumb zone)
│  │ ▸ Next: $120 daily goal    │    │     • Live earnings pace
│  │ ▸ 3 offers nearby          │    │     • Nearby demand count
│  └─────────────────────────────┘    │
│           [🧭 Nav] [💬 Support]     │  ← Quick actions
└─────────────────────────────────────┘
```

**Key differences from your Home:**
1. **Map is the canvas** — not a list
2. **Demand visualization** — heatmap + surge + nearby pins
3. **Single primary CTA** — "Go Online" dominates bottom sheet
4. **Earnings pace** — real-time $/hr, daily goal ring
5. **Quick actions** — Navigate, Support always in thumb zone

### 3.3 Ride Request — Full-Screen Takeover

```
┌─────────────────────────────────────┐
│  ══════════════════════════════════  │  ← Countdown ring (15–30s)
│  🔔  NEW RIDE REQUEST               │
│                                     │
│  📍 Pickup: 123 Main St, CBD        │
│  🏁 Dropoff: Airport Terminal 2     │
│                                     │
│  8.2 km  •  18 min  •  UGX 28,500  │
│  ▸ 2 passengers  •  Comfort class   │
│                                     │
│  ┌─────────────┐  ┌─────────────┐   │
│  │  DECLINE    │  │  ACCEPT 12s │   │  ← Large, high-contrast
│  └─────────────┘  └─────────────┘   │     Haptic on appear
└─────────────────────────────────────┘
```

**Your current:** Inline card in offers list, no countdown visual, no haptic, easy to miss.

### 3.4 Earnings — Goal-Driven, Actionable

```
┌─────────────────────────────────────┐
│  EARNINGS                    [📊]   │
├─────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐           │
│  │  DAILY  │  │ WEEKLY  │           │  ← Progress rings
│  │ $87/$120│  │$420/$600│           │     Tap → breakdown
│  └─────────┘  └─────────┘           │
│                                     │
│  💰  CASH OUT NOW   →  UGX 142,000  │  ← Primary action
│                                     │
│  ─────────────────────────────────  │
│  TODAY'S TRIPS (5)                  │
│  ▸ 08:12  CBD → Airport   UGX 28k   │
│  ▸ 10:45  Mall → Hotel    UGX 15k   │
│  ▸ 13:20  Hotel → CBD     UGX 12k   │
│  ▸ 15:10  CBD → Station   UGX 18k   │
│  ▸ 17:30  Station → Home  UGX 14k   │
│                                     │
│  [View all trips →]                 │
└─────────────────────────────────────┘
```

**Your current:** Static total + performance scores table. No goals, no cash-out, no trip breakdown.

### 3.5 Vehicle — Health & Compliance First

```
┌─────────────────────────────────────┐
│  VEHICLE                      [⚙️]   │
├─────────────────────────────────────┤
│  🚐  TOYOTA HIACE  •  UBA 123A      │
│  ▸ Insurance:  🟢 45 days left      │  ← Expiry countdown
│  ▸ Inspection: 🟡 12 days left      │
│  ▸ License:    🟢 200 days left     │
│                                     │
│  ┌─────────────────────────────┐    │
│  │  SWITCH VEHICLE             │    │  ← One-tap switch
│  └─────────────────────────────┘    │
│                                     │
│  ─────────────────────────────────  │
│  MAINTENANCE                        │
│  ▸ Oil change due in 800 km         │
│  ▸ Tire rotation due in 1,200 km    │
│                                     │
│  DOCUMENTS                          │
│  ▸ [View] Insurance cert            │
│  ▸ [View] Inspection report         │
│  ▸ [Upload] New license             │
└─────────────────────────────────────┘
```

**Your current:** Basic list + switch duplicate. No health, no expiry, no maintenance.

### 3.6 Safety Toolkit — Non-Negotiable

```
┌─────────────────────────────────────┐
│  SAFETY                        [🛡️]  │  ← Persistent topbar icon
├─────────────────────────────────────┤
│  🚨  EMERGENCY BUTTON               │  ← Red, pulse animation
│  Hold 3s to alert authorities       │
│  & share live location              │
│                                     │
│  👥  SHARE TRIP                     │
│  Send live link to trusted contacts │
│                                     │
│  💬  IN-APP SUPPORT                 │
│  Chat with safety team 24/7         │
│                                     │
│  📋  SAFETY CHECKLIST               │
│  Pre-trip vehicle check             │
└─────────────────────────────────────┘
```

**Your current:** Absent.

---

## 4. Gap Analysis — Detailed

### 4.1 Information Architecture

| Issue | Severity | Evidence |
|-------|----------|----------|
| 7 top-level tabs | HIGH | `driver_dashboard.html:72-92` — Home, Status, Trips, Earnings, Assignments, Vehicles, Account |
| Status separate from Home | HIGH | Industry: online toggle in Home bottom sheet |
| Assignments separate from Vehicle | MEDIUM | Both vehicle-centric; merged in Go/Uber |
| No Safety top-level access | CRITICAL | Safety is regulatory + trust requirement |

### 4.2 Home View

| Missing | Industry Standard | Your Code |
|---------|-------------------|-----------|
| Map canvas | Full-bleed MapLibre/Leaflet | `driver_dashboard.html:27-245` — all cards |
| Demand heatmap | Real-time surge zones | None |
| Nearby request pins | Live dispatch visualization | Offers list only |
| Earnings pace | $/hr + daily goal ring | Static total in hero |
| Primary CTA | "Go Online" FAB bottom-right | Toggle in hero card (line 54-59) |
| Quick actions | Navigate, Support, Safety | None |

### 4.3 Ride Request UX

| Deficiency | Impact |
|------------|--------|
| No countdown timer | Drivers miss expiry; Bolt/Uber show 15–30s ring |
| No haptic feedback | Missed requests on vibration-only phones |
| Inline in list | Low visibility; full-screen takeover is standard |
| No route preview | Can't assess detour before accept |
| No earnings impact | "This ride = +UGX 28k toward daily goal" |

### 4.4 Earnings

| Missing | Why It Matters |
|---------|----------------|
| Daily/weekly goal rings | Gamification drives supply |
| Instant cash-out button | Top driver request; Bolt/Uber have it |
| Trip-by-trip breakdown | Transparency → trust |
| Projected earnings | "At current pace: UGX 1.2M this week" |

### 4.5 Vehicle

| Missing | Risk |
|---------|------|
| Document expiry countdowns | Compliance violations → deactivation |
| Maintenance reminders | Breakdowns → lost revenue + safety |
| Inspection status | Regulatory requirement |
| One-tap switch with confirmation | Your switch is buried in two panels |

### 4.6 Safety

| Missing | Regulatory/Trust Impact |
|---------|------------------------|
| Emergency button | Required in Kenya/Uganda ride-hailing regs |
| Share trip | Standard trust feature |
| In-app support chat | Reduces resolution time 80% |
| Safety checklist | Pre-trip inspection mandate |

---

## 5. Wireframes — Target State

### 5.1 New Information Architecture (5 Tabs)

```
┌─────────────────────────────────────────────────────────────┐
│  MOBILE (Bottom Nav)          DESKTOP (Left Sidebar)        │
│  ┌─┬─┬─┬─┬─┐                   ┌─────────────────────────┐  │
│  │🗺️│💰│🗂️│🚐│👤│                   │ 🗺️ Home                │  │
│  └─┴─┴─┴─┴─┘                   │ 💰 Earnings             │  │
│  Home  Earn Trips Vehicle Me   │ 🗂️ Trips                │  │
│                                │ 🚐 Vehicle              │  │
│                                │ 👤 Account              │  │
│                                │                         │  │
│                                │ 🛡️ Safety (always top)  │  │
│                                │ 💬 Support (always top) │  │
│                                └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Home — Map-Centric (Mobile)

```
┌─────────────────────────────────────┐  ← Safe area top
│  [≡]  AFCON360 Driver    [🛡️][💬][↻] │  ← Safety, Support, Refresh always visible
├─────────────────────────────────────┤
│                                     │
│                                     │
│         MAP (MapLibre GL)           │  ← 100vh - topbar - bottom-sheet
│   • Blue pulsing driver dot         │
│   • Red/yellow heatmap overlay      │
│   • Surge badges: "1.8×"            │
│   • Nearby request pins (count)     │
│                                     │
│                                     │
├─────────────────────────────────────┤  ← Draggable bottom sheet (snap: peek/half/full)
│  🟢 GO ONLINE          UGX 42/hr    │  ← Primary CTA (44×44 min)
│  ▸ Daily goal: UGX 87 / 120  (72%)  │
│  ▸ 3 offers nearby • 2.1× surge     │
│  ─────────────────────────────────  │
│  [🧭 Navigate]  [💬 Support]  [🛡️]   │  ← Quick actions (thumb zone)
└─────────────────────────────────────┘  ← Safe area bottom
```

### 5.3 Home — Desktop (Sidebar + Map)

```
┌─────────────────────────────────────────────────────────────┐
│  [≡]  AFCON360 Driver    [Search]    [🔔] [👤] [🛡️] [💬] [↻] │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                  │
│  🗺️ Home │                                                  │
│  💰 Earn │                                                  │
│  🗂️ Trips │              MAP (MapLibre GL)                 │
│  🚐 Vehicle                                                      │
│  👤 Account                                                      │
│          │                                                  │
│  🛡️ Safety                                                      │
│  💬 Support                                                      │
│          │                                                  │
│  👤 Driver Avatar                                               │
│  [Logout]                                                       │
└──────────┴──────────────────────────────────────────────────┘
```

### 5.4 Ride Request — Full-Screen Takeover (Mobile + Desktop)

```
┌─────────────────────────────────────┐
│  ◄  BACK TO MAP                     │  ← Dismiss = Decline
├─────────────────────────────────────┤
│                                     │
│     ═════════════════════════════    │  ← SVG countdown ring (--progress: 0→1)
│    ╱  NEW RIDE REQUEST           ╲   │     Animates 15s → 0
│   ╱                                 ╲  │
│  │                                   │  │
│  │    📍  PICKUP                     │  │
│  │    123 Main Street, CBD           │  │
│  │                                   │  │
│  │    🏁  DROPOFF                    │  │
│  │    Entebbe Airport Terminal 2     │  │
│  │                                   │  │
│  │    8.2 km   •   18 min            │  │
│  │    2 passengers  •  Comfort       │  │
│  │                                   │  │
│  │    💰  UGX 28,500   (+UGX 5,200   │  │  ← Surge breakdown
│  │           surge 1.8×)             │  │
│  │                                   │  │
│  │    🎯  +UGX 28,500 toward         │  │  ← Goal impact
│  │        daily goal (UGX 120)       │  │
│  ╲                                 ╱  │
│   ╲_________________________________╱  │
│                                     │
│  ┌─────────────────────────────┐    │
│  │         DECLINE             │    │  ← 48px height, red outline
│  └─────────────────────────────┘    │
│  ┌─────────────────────────────┐    │
│  │      ACCEPT (12s)           │    │  ← 48px height, green fill, countdown
│  └─────────────────────────────┘    │
│                                     │
└─────────────────────────────────────┘
```

**Desktop:** Centered modal (400px max-width) over dimmed map. Same countdown ring.

### 5.5 Earnings — Goal-Driven (Mobile)

```
┌─────────────────────────────────────┐
│  EARNINGS                    [📊]   │
├─────────────────────────────────────┤
│                                     │
│   ┌─────────────┐ ┌─────────────┐   │
│   │    DAILY    │ │   WEEKLY    │   │  ← SVG rings, tap → breakdown
│   │  UGX 87k    │ │  UGX 420k   │   │
│   │  72%  ████░ │ │  70%  ████░ │   │
│   │  Goal 120k  │ │  Goal 600k  │   │
│   └─────────────┘ └─────────────┘   │
│                                     │
│  ┌─────────────────────────────┐    │
│  │  💰  CASH OUT NOW           │    │  ← Primary action, always visible
│  │  Available: UGX 142,000     │    │
│  └─────────────────────────────┘    │
│                                     │
│  ─────────────────────────────────  │
│  TODAY'S TRIPS (5)          [▼]     │  ← Expandable
│  ▸ 08:12  CBD → Airport   UGX 28k   │
│  ▸ 10:45  Mall → Hotel    UGX 15k   │
│  ▸ 13:20  Hotel → CBD     UGX 12k   │
│  ▸ 15:10  CBD → Station   UGX 18k   │
│  ▸ 17:30  Station → Home  UGX 14k   │
│                                     │
│  [View all trips →]                 │
└─────────────────────────────────────┘
```

### 5.6 Vehicle — Health-First (Mobile)

```
┌─────────────────────────────────────┐
│  VEHICLE                      [⚙️]   │
├─────────────────────────────────────┤
│  🚐  TOYOTA HIACE  •  UBA 123A      │
│  Comfort  •  14 seats  •  Assigned  │
│                                     │
│  ┌─────────────────────────────┐    │
│  │  SWITCH VEHICLE             │    │  ← Primary action
│  └─────────────────────────────┘    │
│                                     │
│  DOCUMENT HEALTH                    │
│  ┌─────────────────────────────┐    │
│  │ 🟢 Insurance      45 days   │    │  ← Green >30, Amber 7-30, Red <7
│  │ 🟡 Inspection     12 days   │    │
│  │ 🟢 License       200 days   │    │
│  └─────────────────────────────┘    │
│                                     │
│  MAINTENANCE                        │
│  ┌─────────────────────────────┐    │
│  │ 🟡 Oil change     800 km    │    │
│  │ 🟢 Tire rotation 1,200 km   │    │
│  │ 🟢 Brake pads    5,000 km   │    │
│  └─────────────────────────────┘    │
│                                     │
│  [View documents →] [Schedule svc]  │
└─────────────────────────────────────┘
```

### 5.7 Safety Toolkit — Persistent Access

```
┌─────────────────────────────────────┐  ← Mobile: bottom sheet from topbar 🛡️
│  SAFETY TOOLKIT                     │     Desktop: sidebar panel
├─────────────────────────────────────┤
│                                     │
│  ┌─────────────────────────────┐    │
│  │  🚨  EMERGENCY ASSISTANCE   │    │  ← Red, pulse, 56px height
│  │  Hold 3s to call 999 &      │    │
│  │  share live location        │    │
│  └─────────────────────────────┘    │
│                                     │
│  ┌─────────────────────────────┐    │
│  │  👥  SHARE MY TRIP          │    │
│  │  Send live link to contacts │    │
│  └─────────────────────────────┘    │
│                                     │
│  ┌─────────────────────────────┐    │
│  │  💬  24/7 SUPPORT CHAT      │    │
│  │  Connect with safety team   │    │
│  └─────────────────────────────┘    │
│                                     │
│  ┌─────────────────────────────┐    │
│  │  📋  PRE-TRIP CHECKLIST     │    │
│  │  Tires • Lights • Brakes •  │    │
│  │  Seatbelts • Documents      │    │
│  └─────────────────────────────┘    │
│                                     │
└─────────────────────────────────────┘
```

---

## 6. Implementation Roadmap

### Phase 1 — Foundation (Week 1–2) *No backend changes*

| Task | Files | Effort |
|------|-------|--------|
| Add MapLibre GL to base.html | `driver/base.html`, `driver-dashboard.html` | 2h |
| Create map component (driver location + heatmap stub) | `static/js/modules/transport/driver-map.js` | 8h |
| Condense nav to 5 tabs (merge Status→Home, Assignments→Vehicle) | `driver/base.html`, `driver-dashboard.html` | 4h |
| Move online toggle to Home bottom sheet | `driver-dashboard.html:48-69` | 3h |
| Add Safety + Support to topbar (always visible) | `driver/base.html:153-164` | 2h |

### Phase 2 — Ride Request Overhaul (Week 2–3)

| Task | Files | Effort |
|------|-------|--------|
| Full-screen ride request modal component | `static/js/modules/transport/ride-request-modal.js` | 12h |
| Countdown ring (SVG + CSS animation) | `static/css/modules/transport/ride-request.css` | 4h |
| Haptic feedback on request receive | `driver-dashboard.js` (integrate) | 2h |
| Route preview polyline on map | `driver-map.js` | 6h |
| Earnings impact line ("+UGX X toward daily goal") | `driver-dashboard.js` + template | 2h |

### Phase 3 — Earnings & Vehicle (Week 3–4)

| Task | Files | Effort |
|------|-------|--------|
| Goal rings (daily/weekly) with SVG progress | `static/js/modules/transport/earnings-rings.js` | 6h |
| Cash-out button + backend integration | `earnings` panel + API | 8h |
| Trip breakdown list with filters | `earnings` panel | 4h |
| Document expiry countdowns | `vehicles` panel + model fields | 6h |
| Maintenance reminders | `vehicles` panel + model fields | 6h |
| One-tap vehicle switch with confirmation modal | `vehicles` panel + API | 4h |

### Phase 4 — Safety & Polish (Week 4–5)

| Task | Files | Effort |
|------|-------|--------|
| Emergency button (3s hold → call + share location) | `static/js/modules/transport/safety-toolkit.js` | 8h |
| Share trip (deep link + Web Share API) | `safety-toolkit.js` | 4h |
| In-app support chat (WebSocket + existing notifications) | `safety-toolkit.js` + backend | 12h |
| Pre-trip checklist modal | `safety-toolkit.js` + template | 4h |
| Accessibility audit (ARIA, focus management, contrast) | All new components | 8h |
| PWA: background sync for offline ride accept | `driver-dashboard.js` + SW | 6h |

---

## 7. Technical Debt to Address

| Area | Current | Target |
|------|---------|--------|
| **CSS Architecture** | Single 874-line file with media queries | Split: `driver-dashboard.css` → `driver-map.css`, `ride-request.css`, `earnings.css`, `vehicle-health.css`, `safety.css` |
| **JS Architecture** | 2,500-line monolith | ES modules: `driver-map.js`, `ride-request-modal.js`, `earnings-rings.js`, `vehicle-health.js`, `safety-toolkit.js`, `driver-dashboard-core.js` |
| **State Management** | Scattered in `driver-dashboard.js` | Centralized store (tiny: 200 lines) for driver state, offers, trips, earnings, vehicle |
| **API Contract** | Ad-hoc endpoints | Formal OpenAPI spec for `/api/transport/drivers/me/*` |
| **Testing** | Unit tests for GPS logic only | E2E Playwright specs for: ride request flow, earnings cash-out, vehicle switch, emergency button |

---

## 8. Acceptance Criteria (Definition of Done)

| Feature | Must Have | Should Have | Nice to Have |
|---------|-----------|-------------|--------------|
| **Map Home** | Driver dot + heatmap stub | Surge badges + nearby pins | Real-time demand WebSocket |
| **Ride Request** | Full-screen + countdown + haptic | Route preview polyline | Voice announcement |
| **Earnings** | Goal rings + cash-out button | Trip breakdown + filters | Projected earnings chart |
| **Vehicle** | Expiry countdowns + switch | Maintenance reminders | Inspection photo upload |
| **Safety** | Emergency button + share trip | In-app chat | Pre-trip checklist |
| **Nav** | 5 tabs + Safety/Support topbar | Desktop sidebar parity | Keyboard shortcuts |

---

## 9. Risk & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| MapLibre GL bundle size | HIGH | Performance | Code-split; load only on Home; fallback static map image |
| Backend endpoints missing | MEDIUM | Blockers | Phase 1–2 use existing APIs; Phase 3–4 need new endpoints — coordinate with backend sprint |
| Driver resistance to change | LOW | Adoption | A/B test with 10% cohort; keep "classic" toggle in Account |
| Safari PWA limitations | MEDIUM | Install rate | Native iOS wrapper (Capacitor) for App Store distribution |
| Regulatory safety requirements | HIGH | Legal | Emergency button = Phase 4 P0; engage compliance early |

---

## 10. Appendix — Current Code References

| Component | File | Lines |
|-----------|------|-------|
| Driver dashboard template | `templates/transport/driver/driver_dashboard.html` | 1–1,100+ |
| Driver base shell | `templates/transport/driver/base.html` | 1–284 |
| Dashboard CSS | `static/css/modules/transport/driver-dashboard.css` | 1–874 |
| Dashboard JS (core) | `static/js/modules/transport/driver-dashboard.js` | 1–2,500+ |
| Transport base CSS | `static/css/modules/transport/base.css` | (referenced) |
| Notification bell | `templates/components/notification_bell.html` | (included) |

---

**Next Step:** Review this audit with Product + Engineering leads. Prioritize Phase 1–2 for next sprint. Create formal specification (contract) for Phase 1 map integration before implementation begins.

*End of Audit Report*