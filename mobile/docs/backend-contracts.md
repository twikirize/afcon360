# Mobile-to-Flask backend contract gate

Audit baseline: 37f5d2c3b6ad606a6fa269693f6416aacce6c8f2 (main, 4 November 2026).

## Verified in source

- Flask is the backend and remains the business/data authority.
- Browser pages use Flask-Login sessions and CSRF protection.
- GET /api/csrf-token issues a CSRF token tied to the browser session; it is not a native authentication endpoint.
- The driver web dashboard calls existing transport APIs and registers /transport/sw.js for its PWA. The browser dashboard is not a native authentication/permission contract.
- Transport, Wallet, Identity/KYC and Notifications have separate domain ownership. Wallet is the canonical money/ledger owner.

## Critical integration gap

The initial source search did not establish a supported first-party native login, refresh-token rotation, mobile logout/revocation or token-authentication contract. Do not assume Authorization: Bearer works on every existing Flask endpoint. Do not pass browser cookies or CSRF tokens into SecureStore and call that native authentication.

The shared client is only a transport boundary. It omits cookies, adds an Authorization bearer header only when a verified native access token is present, applies HTTPS validation and enforces request timeouts. It does not mint credentials, sign users in or invent endpoints.

## Backend work required before live use

### 1. Native authentication (P0)

Design and test versioned endpoints under /api/mobile/v1/auth:

- POST /login — verify existing account credentials/MFA/OTP policy and issue a device-bound mobile session.
- POST /refresh — rotate the refresh credential; detect replay and revoke the session family.
- POST /logout — revoke the current device session and refresh credential.
- GET /me — return minimal authenticated identity plus eligible contexts/roles.
- Include session list/revoke controls, rate limits, audit events, device label, issue/expiry times and error codes.

Token format, lifetimes, rotation, MFA behavior and persistence must be approved against existing Auth/Identity architecture before migrations or implementation. Do not introduce a competing user/role model.

### 2. Authorization and context (P0)

Every protected operation must resolve current user and current membership/driver eligibility from the server. Client-selected roles, public IDs and context values are hints, never authority. Driver APIs must verify the authenticated user owns the active driver profile and that compliance/go-live/vehicle predicates pass.

### 3. Domain API inventory (P0)

Before wiring screens, trace exact endpoints and response schemas for user profile/account recovery; transport fare options, quote acceptance, booking, matching, trip tracking, cancellation and completion; driver readiness, offers, active trip, status, cash receipt and location publishing; wallet balance, invoices, payments, transactions, refunds and earnings/payouts; accommodation search/booking; events/tickets; tourism; notifications and device registration.

Each endpoint needs authorization, idempotency for writes, stable errors, pagination, date/time/currency semantics and tests. Do not duplicate fare calculations, ledger logic or booking state machines in the apps.

### 4. Real-time and notifications (P1)

Select the supported transport for offer delivery and trip updates after tracing existing Socket.IO/event infrastructure. Push requires server-side device-token registration/revocation, APNs/FCM credentials, retry policy and deep-link authorization. A push notification is a wake-up notice, not authoritative trip state.

### 5. Driver location (P1)

- Start with foreground permission and visible, driver-initiated location use.
- Trace the canonical location endpoint and GPS freshness/deduplication contract before publishing.
- Background tracking requires privacy/data-retention assessment, explicit disclosure and consent, Android foreground-service handling, iOS background mode, store declarations and real-device battery/network tests.
- Never queue stale coordinates for indefinite replay. Server timestamps, ordering and stale-observation rejection remain authoritative.

### 6. Money and offline behavior (P0)

Display wallet values returned by Wallet. No client-side ledger, refund decision, fee calculation or FX conversion may become authoritative. Financial writes require server-side idempotency and pending/success/failure reconciliation. Offline mode may cache safe public content but must not claim an offline booking, payment or driver assignment.
