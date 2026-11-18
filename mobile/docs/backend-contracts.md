# AFCON360 native backend contract

Audit baseline: `70816040885e3d52a7158719dc163afe99180b38` (main, 8 November 2026). Native User and Driver sources remain isolated on `feat/native-mobile-apps-20261104`; they are not website/backend code and are not production-deployed.

## Authority boundaries

- Flask remains the system of record. Mobile clients call HTTPS APIs; they never connect to PostgreSQL or calculate fare, payment, refund, Wallet balance or driver eligibility.
- Browser pages continue to use Flask-Login sessions and CSRF protection.
- Native APIs are versioned at `/api/mobile/v1`, require an explicit Bearer token on protected operations, and are CSRF-exempt only because browser cookies are omitted by the native API client. The bearer guard pins Flask-Login's request identity to the resolved token owner even if a client supplies a browser cookie.
- User, Identity, Transport, GEO and Wallet remain separate domain owners.

## Implemented native Identity contract

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/mobile/v1/auth/login` | Uses the canonical `authenticate_user()` password/lockout logic and creates existing server/device session records. |
| POST | `/api/mobile/v1/auth/mfa/verify` | Completes the one-time challenge issued by canonical Auth: TOTP/backup code, or provider-gated SMS for eligible verified-phone accounts. |
| POST | `/api/mobile/v1/auth/refresh` | Rotates one-time opaque refresh tokens; detects replay and revokes the device/server session. |
| POST | `/api/mobile/v1/auth/logout` | Revokes the current device and server sessions. |
| GET | `/api/mobile/v1/auth/me` | Returns minimal account identity and eligible contexts. |
| POST | `/api/mobile/v1/auth/account-deletion` | Reauthenticates and calls the shared account-closure service. |
| POST | `/api/mobile/v1/auth/password-reset/request` | Sends a short-lived email code when an active account with a registered email matches; always returns the same generic 202 response to avoid account enumeration. |
| POST | `/api/mobile/v1/auth/password-reset/confirm` | Validates the one-time code, applies the canonical password-strength policy, changes the password and revokes existing server/device sessions. |

Access tokens are random opaque values, with only SHA-256 digests as Redis keys; access lifetime is 10 minutes and refresh lifetime is 30 days. Redis and the existing Identity `Session` plus Auth `ServerSession` records are checked fail-closed on protected requests. Refresh replay revokes the device session. No new database table or migration was added.

Native password recovery uses a six-digit code delivered to the account's registered email address. The code expires after 10 minutes, is stored as a keyed hash, is rate-limited, and is atomically consumed once; incorrect attempts do not consume the code. The request endpoint deliberately gives the same response when no matching active account exists. A successful password reset revokes previous server and native device sessions. The User and Driver apps keep this flow inside their native screens.

**MFA contract:** TOTP and backup codes use the canonical Auth verifier. Native SMS sign-in is only offered when the account has a verified E.164 phone number and a real owner-configured SMS provider (Twilio or Africa's Talking) is available. The server sends a one-time, short-lived code and returns the masked destination; it does not fall back to console logging. The native UI may display the SMS challenge, but live provider delivery and end-to-end acceptance remain release tests.

## Implemented User / Wallet contract

The native Wallet screen calls the canonical Wallet API and does not calculate balances or maintain a separate ledger. The following endpoints are present on `main`:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/mobile/v1/wallet` | Ledger-derived wallet accounts and balances. |
| GET | `/api/mobile/v1/wallet/transactions` | Owner-scoped transaction history. |
| GET | `/api/mobile/v1/wallet/pin` | Transaction PIN status. |
| POST | `/api/mobile/v1/wallet/pin` | Secure PIN setup/change with the server's password/current-PIN checks. |
| POST | `/api/mobile/v1/wallet/recipients/resolve` | Resolves a verified payment identity without exposing internal IDs. |
| POST | `/api/mobile/v1/wallet/transfers` | Same-currency Wallet transfer through WalletService, protected by PIN and idempotency. |
| POST | `/api/mobile/v1/wallet/deposits` | Creates a provider-backed pending deposit intent; this does not credit the ledger. |
| GET | `/api/mobile/v1/wallet/deposits/<reference>` | Owner-scoped provider deposit status. |
| POST | `/api/mobile/v1/wallet/deposits/<reference>/refresh` | Rechecks provider status; only exact verified amount/currency success may credit the ledger. |

**Wallet boundaries:** customer withdrawals have no merged `main` endpoint. The native withdrawal code remains disabled (`NATIVE_WITHDRAWALS_ENABLED=false`) while draft PR #44 still needs the financial clearing/revenue-account journal decision and verified provider acceptance. Cross-currency Wallet transfers and generic user refunds are not exposed. Flutterwave sandbox/webhook acceptance remains a release gate.

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

- Native Wallet has merged API support for balances, history, PIN, recipient resolution, same-currency transfers and provider-verified deposits. Withdrawals remain disabled; cross-currency transfers and generic refunds are not available.
- Native accommodation APIs remain in draft PR #45 and native event/free-ticket APIs remain in draft PR #46; until those server PRs merge and app integration passes, these screens must not be represented as release-ready live functionality. PR #46 deliberately rejects paid tickets. Tourism remains an explicit website handoff.
- Push/FCM/APNs device registration and live socket delivery are not implemented.
- Live-like end-to-end tests and physical Android/iOS device acceptance are still required.
- Production API deployment, signing credentials, EAS project linking, store developer accounts, privacy/legal approvals and store submissions remain external release gates.
- No production deployment, production database change, schema migration or store submission has been performed.
