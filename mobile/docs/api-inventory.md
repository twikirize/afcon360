# AFCON360 native API inventory

**Implementation branch:** `feat/native-mobile-apps-20261104` (PR #21, draft, not merged/deployed). Original source baseline inspected at `37f5d2c3b6ad606a6fa269693f6416aacce6c8f2`.

Protected native client routes under `/api/mobile/v1` are bearer-only and pin Flask-Login request identity to the validated bearer-token owner. Public exceptions are the password-reset request/confirmation endpoints and the existing anonymous GEO place-search route. Existing domain resources/services remain authoritative.

## Identity and session

| Capability | Native route | Current implementation |
|---|---|---|
| Password sign-in | `POST /auth/login` | Uses existing `authenticate_user()`, account lockout and device session. |
| Password reset request | `POST /auth/password-reset/request` | Enumeration-safe username/email lookup; 6-digit code sent to the registered email address. |
| Password reset confirm | `POST /auth/password-reset/confirm` | Five-attempt, 10-minute OTP verification; password rules and session revocation are server-owned. |
| MFA | `POST /auth/mfa/verify` | TOTP/backup codes only. SMS MFA remains unsupported by the canonical Auth verifier. |
| Refresh | `POST /auth/refresh` | Rotating, one-use opaque refresh tokens; replay revokes the device session. |
| Logout | `POST /auth/logout` | Revokes current Identity device session and Auth server session. |
| Identity | `GET /auth/me` | Minimal user identity and eligible contexts. |
| Account closure | `POST /auth/account-deletion` | Shared closure service, reauth, MFA, session/API-key revocation, identifier scrubbing and record retention controls. |
| Web deletion resource | `GET/POST /apps/delete-account` | Public information page; POST requires signed-in owner, current password, confirmation and TOTP when enabled. |

## User

| Capability | Native route | Domain owner / behavior |
|---|---|---|
| Search places | `GET /geo/api/geocode` | GEO; provider-evidenced results and required attribution. |
| Fare discovery | `POST /transport/ride-options` | Transport; signed quote, no driver availability lookup or matching. |
| Payment readiness | `POST /transport/payment-methods/options` | Transport adapter delegates to Wallet certification. |
| Request ride | `POST /transport/ride-requests` | Request-first Transport service; signed quote, resolved geocode evidence, idempotency, Wallet invoice, profile/KYC gate. |
| Track request | `GET /transport/ride-requests/<reference>` | Rider-owned state; driver/vehicle detail only when assigned. |
| Activity | `GET /activity` | Recent ride requests and converted booking/payment data. |
| Booking detail | `GET /transport/bookings/<reference>` | Existing owner-scoped booking reader. |
| Retry Wallet settlement | `POST /transport/rides/<reference>/payment/settle-wallet` | Existing Wallet-owned settlement; server amount/currency. |
| Wallet balance | Existing `GET /api/wallet/me` | Existing Wallet balance reader; no client calculation. |

## Driver

| Capability | Native route | Domain owner / behavior |
|---|---|---|
| Driver home/readiness | `GET /driver/me` | Resolves current driver's profile; uses `can_go_live()`. |
| Offer polling | `GET /driver/offers` | Existing legacy + request-first offer services. |
| Accept/decline | `POST /driver/offers/<reference>/accept`, `/decline` | Existing assignment and offer ownership/expiry validation. |
| Availability | `POST /driver/status` | Existing go-live and provider status services; no client-selected driver ID. |
| Foreground GPS | `POST /driver/location` | Existing TrackingService; user-initiated while using app only. |
| Active trip | `GET /driver/trips/active` | Own assigned trip or completed unpaid cash receipt belonging to the completing driver. |
| Trip state | `POST /driver/trips/<reference>/status` | Existing Transport trip transition table. |
| Cash receipt | `POST /driver/trips/<reference>/payment/confirm-cash` | Existing Wallet invoice receipt; only after completion and actual cash handover. |
| Earnings | `GET /driver/earnings` | Completed + captured trips grouped by currency. |

## Not yet implemented

- Wallet deposits, withdrawals, transfers, transaction history, refunds and PIN flows.
- Native accommodation, event/ticket and tourism booking.
- Push notifications/APNs/FCM, device token registration and real-time trip streaming.
- Continuous/background driver location.
- Native SMS MFA support until Auth has a complete verified SMS-login contract.
- Physical device tests, live-like auth/booking/deletion end-to-end tests, EAS project linking and store release.
