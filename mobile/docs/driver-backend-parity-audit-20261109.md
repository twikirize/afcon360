# AFCON360 Native Driver Workspace — Backend Parity Audit

**Audit updated:** 2026-11-10  
**Authoritative backend:** `main` at `2e95ac007aafcd67c045e4f54f3cc150bad14958`  
**Native integration baseline:** `feat/native-mobile-apps-20261104` at `f2ab3109673e2ba86363b927381b13edf6953833`  
**Driver implementation:** `feat/native-driver-workspace-parity-20261109`  
**Backend parity work:** PR #72, `feat/driver-native-core-parity-api-20261109`  
**Scope:** Driver-facing capabilities only. Admin, dispatcher, fleet-owner and organisation-governance operations are not Driver-client obligations.

## Executive finding

The native Driver app now has the seven workspace areas corresponding to the website's Home, Status, Trips, Earnings, Assignments, Vehicles and Account panels. The app is a separate React Native client, not a second backend or identity system. Its protected operations use Flask Bearer APIs and the existing Transport/Wallet services.

The native implementation now includes:
- Driver profile/readiness, performance and assigned-vehicle summaries.
- Online/offline status, ride offers and the active-trip lifecycle.
- Upcoming/recent trip-history UI (waiting on backend PR #62).
- Currency-grouped captured earnings, with the completed-driver attribution correction in PR #72.
- Owned/current/switchable vehicle, assignment-history and scheduled-route views.
- Vehicle registration/edit and marketplace browse/application flows.
- A foreground-only location publisher while the Driver is confirmed online.
- A native map, GEO place search and a demand overlay that consumes the proposed aggregate-only endpoint in PR #63.
- A Driver Transport notification inbox and self-reported incident workflow.
- Account compliance/readiness, support/privacy handoffs, account deletion and secure logout.

**This is not yet a complete parity or release sign-off.** The native workspace CI and selective Android/iOS compatibility runs must pass on the current branch. The backend parity PR's latest PostgreSQL/Redis rerun must pass. Trip history and demand-cell APIs are still in separate draft PRs. Incoming offer delivery remains polling-based; native push/realtime and background location are not claimed as complete. Authenticated Android login/session restoration remains deliberately held until the parity gate is met.

## 1. Native-to-backend contract inventory

| Driver operation | API / service authority | Current state |
|---|---|---|
| Driver identity/readiness | `GET /api/mobile/v1/driver/me`; DriverProfile and `can_go_live` | Existing Bearer route; PR #72 adds safe performance, operating preferences, compliance facts and current assigned-vehicle display fields |
| Online/offline | `POST /api/mobile/v1/driver/status`; DriverStatusResource and go-live guard | Existing; server remains authoritative |
| Offers | `GET /api/mobile/v1/driver/offers`, accept/decline routes; OfferService and RideRequestDispatchService | Existing; native Home polls while active |
| Active trip | `GET /api/mobile/v1/driver/trips/active`; BookingService projection | PR #72 adds pickup schedule, booking mode, `can_cancel` and server-calculated `can_mark_no_show` |
| Trip lifecycle | `POST /api/mobile/v1/driver/trips/{reference}/status` | Existing; state transitions and fees remain server-owned |
| Cash receipt | `POST /api/mobile/v1/driver/trips/{reference}/payment/confirm-cash` | Existing; Wallet owns the payment/ledger state |
| Upcoming/recent trips | `GET /api/mobile/v1/driver/trips?scope=upcoming|recent&limit=...` | Proposed by backend PR #62; native Trips UI is ready for that contract but must not be released until the route is integrated |
| Earnings | `GET /api/mobile/v1/driver/earnings` | PR #72 corrects completed-driver attribution after AssignmentService releases the live assignment |
| Assignments and routes | `GET /api/mobile/v1/driver/assignments` | PR #72; returns current assigned vehicle, owned/switchable vehicles, 90-day assignment history and self-scoped scheduled routes |
| Switch vehicle | `POST /api/mobile/v1/driver/vehicles/switch` | PR #72; ownership, active status and blocked-driver rules enforced server-side |
| Vehicle registration/edit | `POST /api/mobile/v1/driver/vehicles`, `PUT /api/mobile/v1/driver/vehicles/{public_id}` | PR #72; registration rechecks KYC tier 3 and canonical ProviderService validation; edits are owner-scoped |
| Marketplace | `GET /api/mobile/v1/driver/marketplace/vehicles`, `POST /api/mobile/v1/driver/marketplace/vehicles/{listing_public_id}/apply` | PR #72; active/public listing projection; actor is derived from Bearer identity |
| Map configuration | `GET /api/mobile/v1/driver/map-config` | PR #72; GEO renderer's public allowlisted map config only |
| Place search | `GET /geo/api/geocode?q=...` | Existing anonymous-allowed, rate-limited GEO geocoder; returns provider attribution |
| Demand cells | `GET /api/mobile/v1/driver/demand/cells` | Proposed by backend PR #63; native map displays only aggregate cells and gracefully reports unavailable until the route is deployed |
| Location publishing | `POST /api/mobile/v1/driver/location` | Existing Bearer adapter to TrackingService; native publisher is foreground-only and active only when server confirms online |
| Transport notifications | `GET /api/mobile/v1/driver/notifications`, read/read-all routes | PR #72; user + Transport-module scoped; opaque signed notification references, no internal notification IDs exposed |
| Incident reporting/history | `GET/POST /api/mobile/v1/driver/incidents` | PR #72; reporter/user/driver identity derived from token, optional booking reference must belong to the Driver |
| Account/support | Existing account deletion, logout, support/privacy website handoffs | Native app; no fake in-app support or emergency/SOS operation is claimed |

The native client must never connect directly to PostgreSQL/Redis or use website cookies as a substitute for Bearer authentication.

## 2. Seven-panel capability comparison

| Website Driver capability | Native implementation | Remaining qualification |
|---|---|---|
| **Home — identity/readiness** | Driver code, verification/compliance, go-live checklist, rating, safety/acceptance/cancellation metrics, trip totals/distance and assigned vehicle | Backend PR #72 must be integrated before release |
| **Home — online/offline** | Native Status screen; server go-live guard controls transitions | No local approval or bypass |
| **Home — offers** | Native offer list, accept/decline and expiry display | Polling remains active-tab/foreground; native push/realtime offer alerts are not implemented |
| **Home — active trip** | Active trip, pickup time, fare/payment, cancel/no-show prompts and cash confirmation | Cancel/no-show affordances follow server capability flags; BookingService remains authoritative |
| **Home — live location** | Foreground watch while signed-in Driver is confirmed online; balanced GPS, 120-second watcher cadence, single-flight publishing, stop on offline/background/unmount | Background location is intentionally not requested; network/backoff, Android process death and long-running shift behaviour still require device testing |
| **Home — map/place search** | Leaflet map in WebView using GEO public tile config, OSM attribution and existing geocoder; current-device location is shown only after explicit permission/action | Map depends on network/CDN/tiles; error state leaves Driver operations usable |
| **Home — demand heatmap** | Native aggregate-cell overlay consuming `center` and `request_count` only | API is still proposed in PR #63; until integrated, demand status reports unavailable. No raw booking points or rider identity are shown |
| **Home — opportunities/scheduled work** | Assignments tab lists server-scoped scheduled routes | Only the current self-scoped scheduled-route projection is implemented; do not expose admin route CRUD |
| **Status — preferences/compliance** | Service types, vehicle classes, zones, capacities, auto-accept, licence/background-check/training facts | Display-only; changing sensitive preferences remains governed by Transport |
| **Trips — active lifecycle** | Active trip actions and pickup schedule | Server action contracts and eligibility flags remain authoritative |
| **Trips — upcoming/recent** | Native history view with safe route/fare/payment summary | Backend PR #62 must be rebased, tested and integrated before release |
| **Earnings — captured amounts** | Currency-grouped totals, platform commission and driver net display | PR #72 corrects metadata attribution; detailed website period/performance analytics are not yet equivalent |
| **Earnings — performance** | Home and Account show canonical rating/safety/acceptance/cancellation/trip/distance summary | Not a full period-by-period analytics report |
| **Assignments — current/switch/history** | Current assignment, switchable owned vehicles and last-90-day vehicle history | PR #72 supplies self-scoped API; no admin assignment operations exposed |
| **Assignments — scheduled routes** | Native scheduled-route cards | Read-only driver scope; no dispatcher route management |
| **Vehicles — owned vehicles** | Ownership-scoped list, distinction from current assignment | PR #72 adapter uses ProviderService.get_user_vehicles |
| **Vehicles — register/edit** | Native forms | Backend enforces KYC tier 3, approval, validation and ownership; API CI remains required |
| **Vehicles — marketplace** | Native public listing browse and application form | Listing/eligibility/service validation remains in MarketplaceService |
| **Account — compliance/readiness** | Native Driver identity, go-live checks and server-provided compliance facts | No document approval or licence secret exposure |
| **Account — notifications** | Native Transport-only inbox, unread count, mark one/read-all | Inbox polls while page is active; background/push notifications are not yet delivered natively |
| **Account — safety/incidents** | Native incident submission and self-reported incident history | No emergency SOS, live call centre or emergency dispatch is claimed |
| **Account — support/privacy/delete/logout** | Explicit website support/privacy handoff, account deletion and secure logout | Website handoff is labelled; no pretend native support workflow |

## 3. Backend parity corrections in PR #72

1. **Driver profile projection:** `GET /driver/me` returns safe performance fields and a display-only current assigned-vehicle projection. Encrypted licence data, emergency contacts and private metadata are excluded.
2. **Operational preferences/compliance:** the same response now includes server-held service types, vehicle classes, operating zones, capacity/preferences and safe licence/background-check/training status.
3. **Active trip projection:** reuses BookingService for booking mode, pickup timezone and no-show eligibility; selects only a pickup-schedule whitelist. Cancel is exposed only for the pre-start statuses already permitted by the website.
4. **Earnings attribution:** completed trips can release `assigned_driver_id`; mobile earnings now also recognizes the persisted `completed_by_driver_profile_id` attribution used by the website.
5. **Assignments/vehicles:** self-scoped assignment, route and history reads; owned-vehicle switch; KYC-gated registration; owner-only editable specification fields; active/public marketplace browse and Driver-scoped application.
6. **Map config:** derives from GEO's public renderer config and emits only `PUBLIC_MAP_CONFIG_KEYS`; tile URL's OSM subdomain placeholder is resolved for the native raster renderer.
7. **Notifications:** Bearer endpoints filter by authenticated user and `module='transport'`; internal notification primary keys are wrapped in a user-bound HMAC reference before returning to the client.
8. **Incidents:** submission derives reporter, user and Driver IDs from the authenticated context; optional booking association is checked against current or completed Driver attribution; ISO-8601 timestamps require an explicit offset; GET exposes only the authenticated Driver's own reports.

These changes add no database schema or migration. They do not make admin endpoints available to Driver tokens.

## 4. Endpoints that must not be called directly from the native Bearer client

| Existing endpoint/resource | Reason |
|---|---|
| `GET /api/transport/drivers`, `GET /api/transport/vehicles`, `GET /api/transport/routes`, `GET /api/transport/incidents` | Admin-only listing surfaces, not Driver self-service |
| `POST /api/transport/drivers/{id}/vehicles/switch` | Cookie-session resource; use the mobile Bearer adapter that preserves ownership/assignment checks |
| `POST /api/transport/vehicles/{id}/request-contract` | Cookie-session resource; use the mobile marketplace adapter and never accept a caller-supplied Driver ID |
| `/api/notifications/*` | Flask-session `login_required`; use the Driver Bearer notification adapter |
| `POST /api/transport/incidents` | Generic body permits caller-supplied identity fields; do not use it from native. Use the identity-derived mobile route |
| Admin Driver/Vehicle/Incident approval, assignment, investigation and override endpoints | Must remain unavailable to a regular Driver client |

## 5. Remaining gaps and release gates

1. Rebase/retest backend PR #62 (trip history) and PR #63 (demand cells) onto current `main`; both were authored against an older main commit and still need integration.
2. Confirm PR #72's current PostgreSQL/Redis rerun is green after the new notification/map/incident contracts. Do not treat an earlier passing run as proof for later commits.
3. Pass the current native workspace CI, SDK dependency validation, strict TypeScript, Android/iOS export, Driver Android APK install/launch, iOS minimum/current builds and APK manifest audit.
4. Verify the seven screens against live Flask responses in a disposable test environment, including forbidden-user/vehicle/trip cases, KYC denial, no-show eligibility, cash receipt and signed notification read ownership.
5. Complete incoming offer alerts (push/realtime or a validated fallback), offer expiry/refresh behaviour and device alert preferences. Do not claim native push or background operation until implemented and tested.
6. Validate foreground location on physical Android/iOS devices, including permissions denied/revoked, offline state, app background/foreground, process restart and stale GPS. Background tracking remains out of scope until separately designed and permitted.
7. **Only after parity/API gates pass, run authenticated Android E2E:** Driver login, MFA (where required), profile/offers/trips/earnings/assignments/notifications reads, session restore, refresh, logout and server/device/Redis revocation.

## Safety boundaries

- No production database writes, configuration changes or deployment have been made.
- No schema or migration change is introduced by this parity work.
- The website/backend `main` remains authoritative; this PR adds no alternate backend.
- All Driver operations are scoped to the authenticated Driver profile and delegate to existing Transport, Booking, Assignment, Marketplace, Tracking and Wallet authorities.
- No User app screens/workflows are imported into the Driver app.
- Do not claim complete functionality solely because a screen renders; API contracts and end-to-end verification are required.
