# AFCON360 mobile API inventory

**Inspected against:** `twikirize/afcon360` main at `37f5d2c3b6ad606a6fa269693f6416aacce6c8f2` (4 November 2026).

This is a source inventory, not a claim that these routes are already native-ready. Flask `login_required` means the current session-based authentication path unless a route-specific bearer contract is verified.

## Customer / User app

| Capability | Existing route | Current state | Mobile work |
|---|---|---|---|
| Fare discovery | `POST /api/transport/ride-options` | Anonymous quote-only endpoint; requires resolved pickup/dropoff coordinates; returns signed `quote_token`, fare currency/version and breakdown | Reuse after confirming response schema/version contract |
| Create ride booking | Current authenticated web booking flow | REST `POST /api/transport/bookings` is admin/system-only | Add rider-authorized JSON command that reuses signed quote validation and canonical BookingService |
| View booking/trip | `GET /api/transport/bookings/<booking_reference>` | Authenticated; owner/admin check; browser session auth not native-proven | Add native auth and verify minimal owner-scoped response |
| Retry Wallet settlement | `POST /api/transport/rides/<booking_reference>/payment/settle-wallet` | Authenticated, owner scoped; amount and currency derive from stored booking | Adapt to native auth; never accept client amount/currency |
| Wallet balance | `GET /api/wallet/me` | Authenticated browser session | Add native auth support and verify minimal wallet response |
| Wallet transactions | `GET /api/wallet/transactions` | Authenticated browser session | Add native auth support and paging schema |
| Deposit / withdraw / transfer | `POST /api/wallet/deposit`, `/withdraw`, `/transfer` | Authenticated; CSRF, frozen-account controls and rate limits; writes require idempotency | Preserve all controls; native CSRF design must be reviewed with native auth |

## Driver app

| Capability | Existing route | Current state | Mobile work |
|---|---|---|---|
| View offers | `GET /api/transport/drivers/me/offers` | Authenticated; server resolves driver's profile | Native auth and tested polling/reconnect contract |
| Accept offer | `POST /api/transport/drivers/me/offers/<booking_reference>/accept` | Authenticated, public booking reference | Native auth; preserve atomic assignment/ownership checks |
| Decline offer | `POST /api/transport/drivers/me/offers/<booking_reference>/decline` | Authenticated, public booking reference | Native auth; preserve expiry and offer state checks |
| Trip progress | `POST /api/transport/drivers/me/trips/<booking_reference>/status` | Authenticated, public booking reference; server owns transitions | Native auth; add read endpoint for active trip and lifecycle state |
| Confirm cash receipt | `POST /api/transport/drivers/me/trips/<booking_reference>/payment/confirm-cash` | Authenticated; explicit post-trip cash receipt | Native auth; preserve one-time/idempotent settlement semantics |
| Change availability | `POST /api/transport/drivers/<driver_id>/status` | Authenticated, but path uses an internal driver ID | Add self-scoped `/drivers/me/status` route and verify go-live gates |
| Publish location | `POST /api/transport/drivers/<driver_id>/location` | Authenticated; existing mobile comment; path uses internal driver ID | Add self-scoped `/drivers/me/location` or a verified public-ID route; trace freshness, dedupe and ownership |
| Earnings | `dashboard_service.get_driver_earnings` | Service-level capability found; a driver-safe mobile REST read contract not established | Add owner-scoped REST endpoint that reads canonical records; do not calculate on device |

## Auth and identity

| Capability | Existing source | Current state |
|---|---|---|
| Sign in | `POST /login` in `app/auth/routes.py` | HTML form and redirect; browser Flask-Login session |
| Device record | `start_device_session()` in `app/auth/sessions.py` | Creates existing `sessions` record and returns opaque UUID |
| Device revocation | `revoke_device_session()` | Existing revoke timestamp/reason and audit event |
| Native access/refresh token | No confirmed route/contract found in inspected source | Must design and security-test before app sign-in |
| Role/context | Existing Identity/Auth context services | Server must resolve role, organization membership, driver profile and eligibility for every request |

## Prioritized backend integration work

1. **MOB-AUTH-01:** Native login/MFA, short-lived access credentials, refresh-secret hashing and rotation, replay detection, device revocation, logout and `/me`. Reuse Auth, Identity, MFA, audit and device-session policy; do not create a second user system.
2. **MOB-RIDE-01:** Rider-authorized JSON booking endpoint using the existing signed fare quote and booking service; include idempotency and exact quote-expiry/state behavior.
3. **MOB-DRIVER-01:** Self-scoped go-live and location endpoints that resolve the current driver's profile without internal IDs in client paths.
4. **MOB-DRIVER-02:** Owner-scoped active-trip/earnings read APIs and documented offer polling cadence/reconnect behavior.
5. **MOB-WALLET-01:** Native auth compatibility for read and write wallet APIs while preserving freeze policy, ledger ownership, CSRF/idempotency protections and audit.
6. **MOB-PUSH-01:** Device registration and revocation, APNs/FCM, offer/trip notification policy, retry and deep-link authorization.

## Non-goals

- Do not make apps connect directly to PostgreSQL.
- Do not create a client-side fare engine, booking state machine or wallet ledger.
- Do not label offer creation as booking confirmation.
- Do not enable continuous background location before permission, privacy, platform and battery gates pass.
- Do not cache authenticated HTML, API responses, access tokens or refresh credentials in the service worker or AsyncStorage.
