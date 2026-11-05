# AFCON360 native backend contract

Audit baseline: `37f5d2c3b6ad606a6fa269693f6416aacce6c8f2` (main, 4 November 2026). Native implementation is isolated on `feat/native-mobile-apps-20261104` and PR #21; it is not merged or deployed.

## Authority boundaries

- Flask remains the system of record. Mobile clients call HTTPS APIs; they never connect to PostgreSQL or calculate fare, payment, refund, Wallet balance or driver eligibility.
- Browser pages continue to use Flask-Login sessions and CSRF protection.
- Native APIs are versioned at `/api/mobile/v1`, require an explicit Bearer token on protected operations, and are CSRF-exempt only because browser cookies are omitted by the native API client. The bearer guard pins Flask-Login's request identity to the resolved token owner even if a client supplies a browser cookie.
- User, Identity, Transport, GEO and Wallet remain separate domain owners.

## Implemented native Identity contract

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/mobile/v1/auth/login` | Uses the canonical `authenticate_user()` password/lockout logic and creates existing server/device session records. |
| POST | `/api/mobile/v1/auth/password-reset/request` | Enumeration-safe reset-code request by username or email; the server sends a 6-digit code to the registered address. |
| POST | `/api/mobile/v1/auth/password-reset/confirm` | Verifies the one-time email code, applies the shared password strength rules and invalidates previous sessions. |
| POST | `/api/mobile/v1/auth/mfa/verify` | Completes TOTP or backup-code verification through existing Auth verification logic. |
| POST | `/api/mobile/v1/auth/refresh` | Rotates one-time opaque refresh tokens; detects replay and revokes the device/server session. |
| POST | `/api/mobile/v1/auth/logout` | Revokes the current device and server sessions. |
| GET | `/api/mobile/v1/auth/me` | Returns minimal account identity and eligible contexts. |
| POST | `/api/mobile/v1/auth/account-deletion` | Reauthenticates and calls the shared account-closure service. |

Access tokens are random opaque values, with only SHA-256 digests as Redis keys; access lifetime is 10 minutes and refresh lifetime is 30 days. Redis and the existing Identity `Session` plus Auth `ServerSession` records are checked fail-closed on protected requests. Refresh replay revokes the device session. No new database table or migration was added.

Password recovery uses a 6-digit email code with a 10-minute lifetime and a five-attempt limit. The request response does not reveal whether an account exists. Password updates reuse the server password-change service and revoke prior sessions.\n\n**MFA limitation:** native sign-in and account deletion currently support enrolled TOTP and TOTP backup codes only. Existing SMS MFA is not a completed verifier in the Auth implementation; native sign-in rejects it rather than treating an SMS code as valid. This needs a canonical Auth decision before supporting SMS.

## Implemented User / Transport contract

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/mobile/v1/transport/ride-options` | Calls canonical quote-only `RideOptionsResource`; no supply lookup or dispatch. |
| POST | `/api/mobile/v1/transport/payment-methods/options` | Asks the Wallet-owned method adapter for methods ready for exact currency/amount. |
| POST | `/api/mobile/v1/transport/ride-requests` | Reuses signed fare-quote validation, canonical location evidence, profile/KYC checks, idempotency, Wallet invoice creation and request-first dispatch. |
| GET | `/api/mobile/v1/transport/ride-requests/<request_reference>` | Owner-scoped request progress and driver/vehicle details only after conversion/assignment. |
| GET | `/api/mobile/v1/activity` | Owner-scoped recent ride requests/activity. |
| GET | `/api/mobile/v1/transport/bookings/<booking_reference>` | Reuses the canonical owner-scoped booking resource. |
| POST | `/api/mobile/v1/transport/rides/<booking_reference>/payment/settle-wallet` | Reuses Wallet-owned settlement retry; client supplies no amount/currency. |

GEO place search is the existing anonymous `GET /geo/api/geocode`; selected result provenance is echoed to the server and validated by `geocode_result_from_candidate()`. Fare discovery is currently denominated by the fare table (USD); a home-currency display amount is indicative only.

## Implemented Driver contract

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/mobile/v1/driver/me` | Server-resolved driver profile, verification/compliance and go-live checklist. |
| GET | `/api/mobile/v1/driver/offers` | Existing legacy and request-first offer service. |
| POST | `/api/mobile/v1/driver/offers/<reference>/accept` | Existing atomic offer acceptance/assignment. |
| POST | `/api/mobile/v1/driver/offers/<reference>/decline` | Existing offer decline. |
| POST | `/api/mobile/v1/driver/status` | Self-scoped wrapper around canonical go-live/availability service. |
| POST | `/api/mobile/v1/driver/location` | Self-scoped wrapper around canonical TrackingService; foreground, driver-initiated only. |
| GET | `/api/mobile/v1/driver/trips/active` | Server-resolved active trip; keeps completed unpaid cash trip visible to its completing driver until Wallet accepts receipt. |
| POST | `/api/mobile/v1/driver/trips/<reference>/status` | Existing server-owned trip transition table. |
| POST | `/api/mobile/v1/driver/trips/<reference>/payment/confirm-cash` | Existing post-trip, driver-confirmed Wallet cash receipt. |
| GET | `/api/mobile/v1/driver/earnings` | Captured trip totals grouped by currency. |

The driver app polls offers and active trip state. Push delivery, continuous/background GPS and offline financial writes are not implemented.

## Remaining domain and release gaps

- Native Wallet mutation flows (deposit, withdraw, transfer, PIN, transaction list and refunds) remain disabled; only the existing Wallet read and Transport settlement retry are connected.
- Accommodation, event/ticket and tourism booking flows remain linked to their existing web experiences, not duplicated natively.
- Push/FCM/APNs device registration and live socket delivery are not implemented.
- Live-like end-to-end tests and physical Android/iOS device acceptance are still required.
- Production API deployment, signing credentials, EAS project linking, store developer accounts, privacy/legal approvals and store submissions remain external release gates.
- No production deployment, production database change, schema migration or store submission has been performed.
