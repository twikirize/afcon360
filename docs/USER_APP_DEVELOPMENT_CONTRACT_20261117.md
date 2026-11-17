# AFCON360 User App — Development Contract and Handoff

**Updated:** 17 November 2026  
**Repository:** `twikirize/afcon360`  
**Active development branch:** `feat/user-offline-first-foundation-20261117`  
**Baseline commit when selected:** `7a033f3f37b2304d16212e4cc6dabb9254dd3782`

This document is the instruction of record for every coding agent, IDE session, reviewer and APK-build session working on the native AFCON360 User app. Read it before changing code.

## 1. One development line

- Develop the User app only on `feat/user-offline-first-foundation-20261117`.
- Treat that branch as the canonical active User-app development line for this phase.
- Do not start another parallel User-app feature branch unless the owner explicitly requests one.
- Do not develop User-app code on website/backend `main`; repository guards intentionally separate native-app work.
- `feat/native-user-app-integration-20261108` remains the protected original integration branch and the eventual consolidation destination until the owner changes that decision.
- The active foundation was created from the assembled candidate at `7a033f3`. At the time of selection it was byte-for-byte/commit-for-commit identical to `integration/final-user-gemini-20261117`, and it contained the history of the original User branch through `48cec771ca76c9377fb049d02f16b1476e81914f`.
- Do not reset, force-push, delete, or rewrite the active or original branch. No production database changes or releases without explicit approval.

**Important:** the branch name “offline-first-foundation” is a starting point for this work, not proof that SQLite/offline sync is already implemented. At the inspected baseline, the User package did not declare `expo-sqlite` or a SQLCipher database dependency, and there was no User offline repository/service at the inspected `src/services/offline.ts` path. Audit the full workspace before concluding what has since been added.

## 2. Freeze the selected Gemini/Pamoja Home

The selected Gemini-derived Pamoja Home is the intended product design. **Do not redesign, replace, simplify, restyle, reorder, or regress it.**

Preserve the current AFCON360-native implementation and its visible hierarchy, including:
- Pamoja brand/header and account/activity access;
- mint illustrated hero/search treatment;
- Transport, Stays, Events & Tickets and Adventure service entry points;
- wallet and My bookings shortcuts;
- My Events/registration information and the discovery/feed content;
- the selected typography, spacing, illustrations, colours, cards, icons and navigation treatment.

The relevant current composition includes `mobile/apps/user/app/(tabs)/index.tsx`, `GeminiHomeTop.tsx`, `MyEventsOverview.tsx` and the selected Pamoja discovery components. Read the live code before editing.

The earlier laptop/dashboard/curation designs are preserved references, **not replacement designs**. Do not cherry-pick their old Home screen over the selected Gemini-derived Home. Functionality may be improved behind existing visible elements without changing the selected presentation. A visual change requires the owner's explicit approval and a before/after review.

## 3. Product architecture: online-authoritative, offline-capable

Use the server as the authority and SQLite as a local resilience/cache layer. The product should work online as its normal mode and retain useful, truthful functionality during connectivity loss. “Offline-first foundation” must not become a second financial or booking authority.

### Server remains authoritative for
- authentication, account identity, device/session state and identity verification;
- wallet balance, ledger, deposits, transfers, refunds and payment status;
- fare quotes, ride matching, driver acceptance, trip state and settlement;
- accommodation pricing, availability, booking confirmation and cancellation;
- event registration, ticket issuance, redemption and check-in;
- all other transactions whose validity depends on current server state.

Never show a wallet transfer, payment, booking, ride, accommodation reservation or ticket as confirmed merely because the phone queued a request. Use an explicit **Pending sync / Awaiting server confirmation** state until the API accepts it.

### Local SQLite may store
- permitted cached Home/feed/service data and read-only summaries;
- user preferences and non-sensitive presentation settings;
- resumable drafts and safe user intents;
- sync cursors, cache metadata and an outbox for operations explicitly designed to be safely retried.

Do not store provider credentials, raw identity evidence, payment secrets, or an authoritative wallet ledger in an ordinary local database.

### Sync and conflict rules
- Implement a repository/data-access boundary so screens do not directly own database/network coordination.
- Give every queued intent a stable idempotency key; the server must enforce idempotency for any mutation that can be retried.
- Use server versions/cursors, deduplication, bounded retries with backoff, and an explicit conflict policy.
- Never use “last write wins” for money, bookings, tickets, driver matching or other transactional state.
- Scope cached data by authenticated account and environment. Account switching must never expose the previous account's cache.
- On logout/account removal, clear the correct account cache and local credentials according to a documented retention policy.
- Treat Redis as shared, short-lived server cache—not a permanent data store or replacement for SQLite/PostgreSQL.
- Make stale data visibly stale and show last-sync/connectivity state where it helps the user make a safe decision.

### Database security gate
Before selecting or adding a SQLite package, verify that it is supported by the repository's Expo SDK/native build and the intended Android/iOS release path. Decide explicitly whether SQLCipher/encryption-at-rest is required and prove that encryption is actually enabled in the built native binary; do not infer this from a JavaScript dependency name. Keep database encryption keys in platform secure storage, define backup/exclusion and key-loss behaviour, and test reinstall, logout, account switching and device-loss implications. Do not claim a remote logout can erase a phone that is offline.

Avoid a large “offline sync” rewrite in one step. Map data owners, API contracts, cacheable reads and safe queued writes first; implement and test one service slice at a time.

## 4. Existing preview server-connection setting — preserve it

The server-selection capability already exists in the selected baseline. It is currently exposed from the app's **Settings / Manage this installation** area under **Connection** (rather than a separate `about.tsx` route):

- `mobile/apps/user/app/(service)/settings.tsx` displays the Connection section and links to `/server-settings`.
- `mobile/apps/user/app/server-settings.tsx` allows the user to choose public Pamoja or enter a reachable preview/staging API origin; it calls `GET /api/health/ping` before saving.
- `mobile/apps/user/src/services/api.ts` stores the selected origin under `afcon360.user.api-base-url` using SecureStore and gates manual server selection with `SERVER_SELECTION_ENABLED`.
- `mobile/apps/user/app.config.ts` enables server selection only for preview builds; the normal default API is `https://www.pamoja.space`.

Keep this facility available while the owner is configuring and testing laptop/hotspot/staging connections. Do not remove it during the APK rebuild. Keep it restricted to internal preview builds. Production must use the approved HTTPS production endpoint; production users must not be able to redirect the app to arbitrary servers.

Preserve and test these safeguards:
- public/remote endpoints use HTTPS;
- plain HTTP is limited to private-network preview testing on the permitted laptop port;
- validate the origin and run the AFCON360 health check before saving;
- changing environments must clear/revoke or invalidate old local credentials as the current flow intends, and require sign-in against the new environment;
- never put usernames, passwords, tokens, database credentials or other secrets in a server URL;
- do not run production credentials or financial tests over private HTTP.

If the owner wants this entry moved visually under an About label, do so only as a navigation/presentation relocation while retaining the same preview-only gate and safety behaviour. Do not make it a public production setting.

## 5. Make every selected Home action real

Audit every visible Home/service/account/wallet/activity/settings control and every website handoff. Each must:
- navigate to a real native route or a deliberate canonical HTTPS Pamoja page;
- preserve the current user's authentication/context where required;
- show loading, empty, error, offline and retry states;
- avoid dead links, placeholder handlers, fake content and silent no-ops;
- return users to a sensible place after a handoff;
- distinguish native flows from partner/website handoffs clearly.

Do not change a selected card's look just to make the handler work. Wire the existing control to the correct real flow. Confirm Transport, Stays, Events & Tickets, Adventure/Tourism, Wallet, My bookings, Activity, Account and Settings individually. Check that events, bookings, tickets and wallet display data for the signed-in account only.

## 6. APK/release engineering gates

The APK currently being rebuilt must be built from the active foundation branch, not from an old laptop or Gemini reference branch. Keep these release properties aligned:
- correct User package/application identity and EAS project;
- correct preview vs production profile, channel and API origin;
- monotonic Android `versionCode`/EAS auto-increment (never reuse a code);
- correct signing credentials and signature continuity for upgrades;
- artifact type (APK for direct preview distribution; AAB when the approved store release requires it);
- reproducible build metadata and SHA-256 checksum;
- no localhost/loopback API in a shareable preview or public build;
- no production release/OTA publication without explicit owner approval.

An E2E APK configured for `127.0.0.1` is a test harness artifact, not a usable public/preview APK for a phone. Do not label it a release build.

Keep the authenticated Android journey aligned to the current Pamoja Home. It must assert the current home first, then scroll and test My Events and the remaining service journeys. Do not roll back the selected UI just to satisfy an obsolete text selector. Run relevant Android API levels and the install/upgrade PackageInstaller matrix; investigate genuine failures rather than marking them as environment noise.


### 6.1 Reusable native APK and rebuild policy

**The native APK is keyed to the native runtime fingerprint, not to each application source commit.** Use Expo Fingerprint (Android platform, balanced preset) as the compatibility/build key. Do not key the APK on the whole `mobile/apps/user/**` or `mobile/packages/**` source tree.

The fingerprint configuration deliberately excludes Expo `extra` values such as the API origin and preview server-selection flags. Those are JavaScript/runtime configuration and can travel with a compatible OTA update. The EAS build profile remains part of the APK build fingerprint. The workflow keeps a disposable E2E APK cache keyed by the fingerprint and validates its SHA-256 before reuse.

| Change | Native APK action |
|---|---|
| Screens, navigation, styling, illustrations, ordinary JavaScript/TypeScript logic, offline repositories and presentation | Reuse existing APK; type-check/export and use a compatible OTA update |
| Backend/API implementation or data changes that do not add a native mobile dependency | No mobile APK rebuild |
| Test assertions, Python E2E scripts, docs and workflow-only test harness changes | Reuse APK and run the relevant test harness; do not create a signed preview APK |
| Add/remove/update a native Expo or React Native module; Expo SDK / React Native native runtime upgrade | New native fingerprint; rebuild |
| Native config plugin, Android/iOS source, manifest, permissions, entitlements, package/bundle identity, scheme or other native-affecting Expo config | New native fingerprint; rebuild |
| EAS APK profile/distribution/build-recipe change that changes the produced binary | Invalidate the matching APK cache/build recipe and rebuild |

A dependency-manifest change is only a *candidate* native change. The fingerprint is the final decision: if it remains the same, reuse the APK. A JavaScript-only dependency or normal source edit must not force a native build merely because its commit SHA changed.

Keep `runtimeVersion: { policy: "appVersion" }` as the OTA compatibility contract. **Before publishing an OTA update that depends on a changed native fingerprint, increment the app version and produce the matching native build first.** Never send JS that expects native APIs absent from an installed APK. Preview OTA publishing remains an explicit, gated action on the permanent integration branch; a feature-branch push must not publish OTA automatically.

For normal PyCharm development, make changes on the active feature branch, commit/push, and let CI type-check and export the JavaScript bundle. If the native fingerprint is unchanged, the existing APK remains the test/install binary; do not rebuild it. When the fingerprint changes, CI creates and verifies a new APK and only then allows the signed preview-build gate. A forced rebuild is reserved for a deliberate rebuild/test request or a broken/missing cache—not ordinary source edits.

The disposable E2E APK embeds the local test API and has OTA disabled. It is only for automated backend journeys and must never be distributed as the phone preview APK. The signed EAS preview APK is the installable phone artifact. Keep these artifacts clearly distinguished.

## 7. Required implementation sequence

1. **Read-only map:** inspect current routes, API clients, AuthProvider, SecureStore use, service contracts, EAS profiles and existing tests. Record what already exists; do not duplicate it.
2. **Build/release baseline:** prove the current preview APK configuration, package/version/signing/API endpoint and authenticated start-up.
3. **Connectivity contract:** preserve the preview server selector and health test; add clear connection state and safe reconnect behaviour.
4. **Local data layer:** select a supported database/encryption approach only after native compatibility and threat-model review. Add schema/versioning, account/environment scoping and a small read-cache slice.
5. **Sync foundation:** implement pull cursors, stale indicators, idempotent outbox semantics and retry/backoff for safe operations only.
6. **Service slices:** migrate Home/feed and read-only summaries first, then suitable drafts/preferences. Handle transport, stays, events and wallet according to their distinct authoritative transaction rules.
7. **Navigation/functional audit:** verify every visible tile, shortcut, tab, deep link and web handoff.
8. **Verification:** targeted tests per change, TypeScript/navigation checks, Android build, authenticated E2E, offline/reconnect tests, account-switch tests, upgrade install tests and then full relevant CI.
9. **Release gate:** only after owner review and passing evidence, prepare the public-release configuration. Production remains locked to the approved HTTPS API.

## 8. Non-negotiable engineering controls

- Follow **UNDERSTAND → MAP → TRACE → PROVE → MINIMAL CHANGE → VERIFY → GATE → RECORD → NEXT**.
- Prefer read-only audit before edits, small changes and targeted tests.
- Do not silently weaken, delete or rewrite tests to obtain a green build.
- Do not hand-write or manually edit Alembic migration files. If a backend schema change is needed, prepare the model change and let the owner generate/review the migration using the agreed Flask workflow.
- No production DB writes, migrations, destructive resets, force pushes, branch deletion or public release without explicit owner approval.
- Do not add a dependency until its Expo SDK/native compatibility, maintenance status, licence, build impact and security implications have been reviewed.
- Do not import Gemini APIs, mock data, auth, navigation or business logic. Only the selected visual treatment belongs in AFCON360.
- Every coding session must report: exact branch and starting SHA, files changed, behaviour changed, tests run with actual results, unresolved risks and next gate.

## 9. Branch reconciliation snapshot (17 Nov 2026)

The Git comparisons are commit-graph comparisons, not a claim that every branch is byte-for-byte identical. A branch may contain unique historical commits whose resulting changes were merged elsewhere or superseded by a newer implementation.

| Branch | Finding at audit | Direction |
|---|---|---|
| `feat/native-user-app-integration-20261108` | Original branch head is the active foundation's ancestor/base | Preserve as protected consolidation destination |
| `feat/user-account-hub-20261114` | PR #106 already merged into original | Redundant after confirming tree; retire after archive policy |
| `feat/user-home-discovery-integration-20261116` | No branch-only commits versus active foundation | Redundant; retire |
| `fix/user-release-engineering-20261115` | Ancestor of the assembled candidate; active foundation is two commits later | Redundant; retire |
| `integration/final-user-gemini-20261117` | Same commit as active foundation at the baseline | Temporary mirror; close/retarget PR #124 before retiring |
| `integration/user-gemini-ui-port-20261116` | Earlier Gemini port with unique history; selected Pamoja implementation is the later replacement | Preserve as reference until UI/interaction parity is signed off, then retire |
| `feat/user-home-dashboard-redesign-20261114` | Laptop design alternative; not the selected Home | Do not merge its Home UI; preserve the laptop baseline |
| `preserve/user-home-laptop-baseline-20261116` | Preserved laptop design snapshot; `.easignore` and `mobile/pnpm-lock.yaml` blobs match active foundation, while active EAS/CI configuration is newer | Retain as archive, not development branch |
| `work/user-home-curation-20261116` | Alternative Home refinements; preservation copy `preserve/user-home-curation-20261116` was created from its exact SHA | Retain archive only; do not replace Gemini Home |
| `feat/user-dashboard-web-parity-20261114` | Earlier dashboard/service-screen direction; not the selected Gemini Home | Retire only after final flow parity check |
| `fix/user-e2e-ci-integration-20261112` | Has branch-only E2E/workflow commits; do not assume all are represented by the later candidate | Keep until test harness differences are reviewed and any useful checks ported |
| `test/user-packageinstaller-ui-matrix-20261115` | Contains a separate install/upgrade test workflow and harness, absent from active candidate; its earlier CI run failed | Keep until failures are triaged and the useful test is ported or explicitly retired |
| `test/native-user-services-api-e2e-20261109` | Several service files/tests match current main; its mobile API/workflow are older than main | Candidate has current main ancestry; verify endpoint/test contracts before retiring the old test branch |

Do not delete a branch solely because a comparison reports a large number of commits on the other side. First compare the actual changed paths/blobs, merged PRs, test coverage and the replacement implementation. In particular, the separate PackageInstaller and E2E test branches must not be discarded until their useful test coverage is present and passing on the active foundation.

## 10. Definition of done for this phase

The User app is ready for public-release consideration only when:
- the selected Gemini/Pamoja Home is unchanged and visually verified;
- every visible service entry and handoff reaches a working flow;
- the live production endpoint is authoritative and preview endpoint switching remains internal-only;
- offline cache is isolated, bounded, secure and useful;
- reconnect/sync is idempotent and never invents transaction success;
- account/session/device transitions do not leak cached user data;
- Android versioning, signing, install and upgrade flows are proven;
- preview APK and release APK/AAB configurations are demonstrably correct;
- authenticated online/offline/reconnect journeys and relevant CI pass;
- the owner approves the release gate.

**Instruction to every development agent:** work from the active branch named above, preserve the selected Gemini/Pamoja Home, do not make the phone a second source of truth, and report evidence rather than claiming completion without tests.
