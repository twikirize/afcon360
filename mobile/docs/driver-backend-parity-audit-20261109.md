# AFCON360 Native Driver Workspace — Backend Parity Audit

**Audit date:** 2026-11-09  
**Backend source:** `main` at `2e95ac007aafcd67c045e4f54f3cc150bad14958`  
**Native source baseline:** `feat/native-mobile-apps-20261104` at `f2ab3109673e2ba86363b927381b13edf6953833`  
**Scope:** Driver-facing capabilities only. Admin, dispatcher, fleet-owner and organisation-governance endpoints are not obligations of the Driver client.

## Executive finding

The native Driver React Native app is **not yet at Driver Workspace parity**. It already has code for the operational essentials (Driver profile/readiness, online/offline, offer list/accept/decline, active-trip actions, one-shot location publishing and captured earnings). The Trips and Account screens have additional in-progress work in this branch.

That is not the same as proving end-to-end operation: authenticated Android login/session validation is deliberately not a release gate until the missing Driver capabilities and their APIs have been reconciled. Existing login E2E work must remain separate from this parity work.

The canonical website workspace has seven panels: Home, Status, Trips, Earnings, Assignments, Vehicles and Account. The native app can retain its four-tab navigation, but every real Driver workflow inside those panels must be reachable and backed by the same Flask services and database.

## 1. Existing native-to-backend wiring

The baseline Driver app calls these Bearer-protected mobile routes:

| Mobile API | Native use | Audit |
|---|---|---|
| `GET /api/mobile/v1/driver/me` | Driver code, verification/compliance, online/available and go-live checklist | Present; response is too narrow for website profile/performance parity |
| `GET /api/mobile/v1/driver/offers` | Current offer cards | Present |
| `POST /api/mobile/v1/driver/offers/{reference}/accept` | Accept server-owned offer | Present |
| `POST /api/mobile/v1/driver/offers/{reference}/decline` | Decline server-owned offer | Present |
| `POST /api/mobile/v1/driver/status` | Online/offline transition | Present; delegates to the canonical go-live guard |
| `POST /api/mobile/v1/driver/location` | Publish a location fix | Present; currently invoked as a one-shot user action, not a live foreground publisher |
| `GET /api/mobile/v1/driver/trips/active` | Active trip / outstanding cash receipt | Present; projection omits no-show/cancel capability flags |
| `POST /api/mobile/v1/driver/trips/{reference}/status` | En-route, arrived, start and complete transitions | Present; backend additionally supports cancel and no-show |
| `POST /api/mobile/v1/driver/trips/{reference}/payment/confirm-cash` | Explicit post-completion cash receipt | Present; Wallet remains settlement authority |
| `GET /api/mobile/v1/driver/earnings` | Currency-grouped captured earnings | Present; query does not match the website's completed-driver attribution rule |

The mobile API is a deliberate Bearer adapter. Do not replace it by calling website routes with invented cookies or by querying a parallel client-side database.

## 2. Seven-panel capability comparison

| Website Driver capability | Native status | Required parity work |
|---|---|---|
| **Home — profile/readiness** | Partial; readiness is displayed on Home. PR #70 adds a richer Account view. | Add safe performance/profile facts: rating, safety score, acceptance/cancellation rates, trip totals and distance. Do not expose encrypted licence numbers or admin-only data. |
| **Home — online/offline** | Present | Retain the server go-live decision and invariant. Show actionable server hints; never locally approve a Driver. |
| **Home — offers** | Present | Improve offer refresh/expiry handling and background/foreground notification behaviour. Current native Home polls every 10 seconds. |
| **Home — active trip** | Partial | Expose server-derived `can_mark_no_show` and `can_cancel`; add guarded cancel/no-show actions. Do not calculate no-show grace periods on-device. |
| **Home — live location** | Incomplete | Replace one-shot location publishing with a permission-aware foreground watch while online and foregrounded, using the configured server cadence, bounded retries, stale-fix rejection and single-flight writes. Stop on offline/logout/background. Background tracking is not assumed. |
| **Home — map and place search** | Missing | Add a native map using the public GEO map configuration and existing geocode service. Preserve provider attribution. A default map centre must never be presented as the Driver's actual location. |
| **Home — demand heatmap** | Missing | Backend Bearer route is proposed in PR #63, but no native map layer consumes it yet. It must show only thresholded aggregate demand cells, never booking IDs, rider details, raw pickup points or driver supply. |
| **Home — opportunities / scheduled work** | Missing | Add a self-scoped scheduled-route read API and screen/card. The website currently reads routes assigned to the current Driver directly from Transport data. Do not use the admin route-list endpoint. |
| **Status — preferences** | Partial | Online/offline works; vehicle classes are shown read-only. The website's current Status panel also presents these preferences read-only. Do not invent edit controls unless a canonical write contract exists. |
| **Trips — active lifecycle** | Partial | Add server-authorized cancel and no-show actions, pickup schedule/time and capability flags. Existing server transitions remain authoritative. |
| **Trips — upcoming/recent history** | UI work in PR #68; API work in PR #62 | Rebase/retest the backend API against current `main`, merge it first, then integrate the UI. PR #68 must not ship against a missing endpoint. |
| **Earnings — captured amounts** | Partial | Keep currency groups separate. Fix the backend attribution query: completed trips clear `assigned_driver_id` and persist `completed_by_driver_profile_id`; website earnings includes both, current mobile earnings only includes the former. |
| **Earnings — performance** | Missing | Add the existing safe Driver performance metrics to the mobile summary response. The website shows safety, acceptance and cancellation performance. Do not recalculate them in React. |
| **Assignments — current vehicle** | Missing | Add a self-scoped Driver API projection for the current assigned vehicle. |
| **Assignments — switch vehicle** | Missing | Add a Bearer adapter to the canonical self-service switch operation. Preserve its ownership, active-status and blocked-driver checks; only vehicles actually owned by the Driver/user may be selected. |
| **Assignments — vehicle history** | Missing | Add a self-scoped last-90-days history projection; do not use the admin Driver history route. |
| **Assignments — scheduled work** | Missing | Add a self-scoped read-only scheduled-route projection. The current generic route-list API is admin-only. |
| **Vehicles — owned vehicles** | Missing | Add a self-scoped list/projection that distinguishes ownership from assignment. Use the existing provider service and model ownership rules. |
| **Vehicles — registration/edit** | Missing in native | Existing website forms may be used as an explicitly labelled web handoff until validated owner-scoped mobile API contracts exist. Do not call admin Vehicle CRUD endpoints. |
| **Vehicles — marketplace/contract request** | Missing | Add public listing projection and Bearer contract-request adapter. The current request endpoint is cookie-session based and must be adapted without trusting a client-supplied Driver ID. |
| **Account — profile/readiness** | PR #70 adds Driver profile and go-live checklist | Retain this change. Continue to expose only safe fields and server-provided checks. |
| **Account — notifications** | Missing | The website shows Transport notification previews and unread counts. Existing `/api/notifications` routes require a Flask login session, not the native Bearer contract. Add a self-scoped mobile adapter and read-state actions. |
| **Account — safety/incidents** | Missing | Add a self-scoped open-incident list and safe Driver incident-report endpoint. The existing incident GET is admin-only; generic POST accepts client-supplied identity fields and is not a safe native Driver contract. Force Driver/user identity from the Bearer session. |
| **Account — offer alert sounds** | Missing | Add native local alert preference/preview and integrate with incoming offer notifications. This is device preference, not a new Transport business rule. |
| **Account — support/privacy/logout/delete** | Partial | Support/privacy handoffs, account deletion and secure logout exist. Retain clear labels and avoid fictitious in-app support/SOS actions. |

## 3. Backend/API gaps and unsafe shortcuts to avoid

1. **Trip history:** current `main` does not yet expose `GET /api/mobile/v1/driver/trips?scope=upcoming|recent`. PR #62 proposes it with a narrow, redacted projection. It was based on commit `70816040885e3d52a7158719dc163afe99180b38`; comparison with current `main` shows the branch is diverged by two main-branch commits. Rebase and rerun PostgreSQL/Redis tests before integration.
2. **Demand cells:** the current website demand endpoint is cookie/context based. PR #63 proposes extracting a shared Transport demand service and adding a Driver-Bearer adapter. It is also two main-branch commits behind/diverged and needs rebase/retest. The native map UI is still missing.
3. **Driver profile metrics:** `DriverProfile` already contains average rating, safety score, acceptance/cancellation rates, total/completed trips and distance. The current mobile `/driver/me` response omits these safe summary fields.
4. **Earnings correctness:** website `BookingService.get_driver_earnings` and its period breakdown include rows attributed by either current `assigned_driver_id` or `booking_metadata.completed_by_driver_profile_id`. The current mobile earnings query uses only `assigned_driver_id`, so it can undercount completed trips after canonical assignment release.
5. **Trip actions:** the canonical driver action executor supports `en_route`, `arrive`, `start`, `complete`, `cancel` and `no_show`. No-show timing/fee/credit must remain in BookingService. The mobile active-trip projection currently does not return the server's `can_mark_no_show` flag.
6. **Location:** the website publisher has a continuous geolocation watcher, cadence, quality checks, backoff, health/network handling and explicit offline/visibility behaviour. Native currently sends one fix only after the Driver taps a button. This is inadequate for a fresh-location-dependent demand view and ongoing Driver operation.
7. **Vehicle APIs:** `DriverVehicleSwitchResource` is cookie-session authenticated but contains the canonical ownership/blocked/active checks and calls `assign_driver_to_vehicle`. Reuse that authority through a Bearer adapter; do not reimplement the assignment write. Generic Vehicle listing/detail CRUD is admin-only.
8. **Scheduled routes:** generic `ScheduledRouteListResource` GET is admin-only. Driver workspace uses a profile-scoped query on `current_driver_id`; add a narrow self-scoped API rather than opening admin routes.
9. **Incidents:** generic incident list/detail/follow-up GET/PUT actions are admin-only. Generic POST is not protected by login and trusts identity fields in the body; do not point the native app at it. A mobile adapter must force the authenticated Driver identity, validate the request and return a narrow projection.
10. **Notifications:** existing `/api/notifications` is protected by Flask session `login_required`, not the native mobile Bearer adapter. Do not assume it works from `authClient`; expose a properly scoped Bearer route or add an explicitly shared token-aware adapter.
11. **Place search:** `/geo/api/geocode` is public, rate-limited and returns provider attribution. It can be consumed by native map search. Map tiles/configuration need a public-safe config contract; never embed private provider credentials in the app.
12. **Offer delivery:** current website Driver offer delivery uses an HTTP polling module with a 4-second base and adaptive backoff; native Home currently polls every 10 seconds. No native push registration/offer notification implementation was found in the Driver client. Do not claim socket/push parity without an implemented and tested channel.

## 4. Endpoints that must not be called directly from the native Bearer client

| Existing endpoint/resource | Why it is not the native contract |
|---|---|
| `GET /api/transport/drivers`, `GET /api/transport/vehicles`, `GET /api/transport/routes`, `GET /api/transport/incidents` | Admin-only listing surfaces, not Driver self-service. |
| `POST /api/transport/drivers/{id}/vehicles/switch` | Existing self-service logic is valid, but endpoint uses Flask session authentication. Add a Bearer adapter that preserves the same service/resource checks. |
| `POST /api/transport/vehicles/{id}/request-contract` | Cookie-session authenticated; actor is derived from current user. Add Bearer adapter and never trust a body Driver ID. |
| `/api/notifications/*` | Flask session-based `login_required`; no native Bearer integration in this route group. |
| `POST /api/transport/incidents` | Not a safe native contract: request body supplies Driver/user identity and the endpoint has no login decorator. Add a self-scoped mobile route. |
| Admin Driver/Vehicle/Incident detail, approval, assignment, investigation and override endpoints | Must remain unavailable to a regular Driver client. |

## 5. Implementation order and release gates

1. **Complete the contract inventory and merge/rebase-safe backend API work:** trip history, demand cells, Driver summary/performance, correct earnings attribution, active-trip capability flags, vehicle/assignment/scheduled-route reads and writes, notifications and safe incident adapters.
2. **Implement native Driver UX:** map + geocode + aggregate demand; foreground location publishing; upcoming/recent and full active-trip actions; vehicle/assignment/scheduled-route screens; performance/earnings; notification inbox/alerts; safety/incidents.
3. **Automated app checks:** navigation contract, strict TypeScript, Expo dependency check, Android/iOS exports/builds, targeted API contract tests. Test failures should distinguish missing API, authorization, contract mismatch and client defects.
4. **Parity gate:** every website Driver capability above is either implemented natively, explicitly handed off to a canonical website flow, or labelled as a true backend dependency. No inert placeholder tiles.
5. **Only then run authenticated Android E2E:** successful Driver login, protected profile/offer/trip/earnings/vehicle/notification reads, session restore, logout, and server/device/Redis revocation. Until then login E2E is not the completion criterion for this task.

## Safety boundaries

- No changes to production database, production configuration, website business logic or User app.
- No schema/migration changes are presumed necessary; add migrations only if an evidence-backed domain requirement proves one is needed and it is separately authorised.
- All native Driver operations remain scoped to the authenticated Driver profile and delegate to existing Transport/Wallet services.
- No duplicate Driver identity, Booking, Wallet, dispatch, location or vehicle-assignment implementation is permitted.
