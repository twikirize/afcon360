# AFCON360 Wallet Architecture

## Purpose

This document is the **single source of truth** for the AFCON360 wallet module.
It explains the data model, account lifecycle, payment integration points,
and the rules every engineer must follow when touching wallet code.

**Audience:** Backend engineers, security auditors, compliance reviewers.
**Last updated:** 2026-07-26

---

## 1. Core Principles

| Principle | Rule |
|-----------|------|
| **No auto-creation** | Wallet accounts are **never** created automatically during checkout, payment, or any guest-facing flow. |
| **Explicit onboarding** | Accounts are created only during deliberate wallet onboarding/activation. |
| **Double-entry ledger** | Every debit must have a matching credit. Balances are **derived**, never stored. |
| **Internal vs Public IDs** | `user.id` (BIGINT) is for DB relations only. `public_id` (UUID) is for APIs/URLs/sessions. |
| **Owner types** | Accounts can belong to `USER`, `ORGANISATION`, `PLATFORM`, or `SYSTEM`. Platform accounts are explicitly flagged. |

---

## 2. Data Model

```
AccountModel (accounts table)
├── id                   UUID (primary key)
├── account_number       VARCHAR(20) — financial account code (e.g. 00000001)
├── account_name         VARCHAR(200)
├── account_description  VARCHAR(500)
├── account_type         VARCHAR(30) — revenue, escrow, operations, settlement, reserve, user_wallet, org_wallet
├── owner_type           VARCHAR(20) — user, organisation, platform, system
├── user_id              BIGINT (FK → users.id, ON DELETE RESTRICT)
├── platform_account     BOOLEAN — true for platform-owned accounts
├── status               VARCHAR(20) — active, frozen, closed, suspended
├── currency             VARCHAR(10), default 'USD'
├── is_frozen            BOOLEAN
├── frozen_at            TIMESTAMP
├── frozen_by            BIGINT (FK → users.id, ON DELETE SET NULL)
├── daily_volume         NUMERIC
├── monthly_volume       NUMERIC
├── daily_volume_limit   NUMERIC
├── monthly_volume_limit NUMERIC
├── per_transaction_limit NUMERIC
├── require_dual_authorization BOOLEAN
├── chart_of_accounts_code VARCHAR(20)
├── ifrs_category        VARCHAR(50)
├── verified             BOOLEAN
├── terms_accepted_at    TIMESTAMP
├── extra_data           JSONB
├── created_at           TIMESTAMP
├── updated_at           TIMESTAMP
└── [NO balance column]

LedgerEntryModel (ledger_entries table)
├── id               UUID
├── account_id        UUID (FK → accounts.id, ON DELETE CASCADE)
├── amount            NUMERIC (positive = credit, negative = debit)
├── currency          VARCHAR(10)
├── entry_type        VARCHAR(10) — DEBIT, CREDIT
├── transaction_id    UUID (FK → transactions.id, ON DELETE CASCADE)
├── created_at        TIMESTAMP
└── meta              JSONB

WalletCreationEventModel (wallet_creation_events table)
├── id               UUID (primary key)
├── user_id          BIGINT (FK → users.id, ON DELETE SET NULL)
├── account_id       UUID (FK → accounts.id, ON DELETE SET NULL)
├── event            VARCHAR(50) — initiated, email_verified, terms_accepted, kyc_checked, account_created, account_verified, activation_pending, activated, completed, failed
├── step_order       BIGINT
├── step_metadata    JSONB
├── session_id       VARCHAR(128)
├── ip_address       VARCHAR(45)
├── user_agent       TEXT
└── created_at       TIMESTAMP
```

**Balance calculation:**
```python
balance = sum(ledger.amount for ledger in LedgerEntryModel
              where account_id=account.id and currency=account.currency)
```

---

## 3. Account Types & Platform Accounts

### 3.1 Account Types

| Type | Purpose | Owner |
|------|---------|-------|
| `user_wallet` | Individual user wallet | USER |
| `org_wallet` | Organisation wallet | ORGANISATION |
| `revenue` | Platform commission collection | PLATFORM |
| `escrow` | Guest payment holding | PLATFORM |
| `operations` | Operating expenses | PLATFORM |
| `settlement` | Bulk payouts | PLATFORM |
| `reserve` | Contingency funds | PLATFORM |

### 3.2 Platform Account Structure

```
PLATFORM ACCOUNTS
├── 00000001 – PLATFORM_REVENUE (Commission collection)
├── 00000002 – PLATFORM_ESCROW (Guest payment holding)
├── 00000003 – PLATFORM_OPERATIONS (Operating expenses)
├── 00000004 – PLATFORM_SETTLEMENT (Bulk payouts)
└── 00000005 – PLATFORM_RESERVE (Contingency funds)
```

Platform accounts are created via `scripts/setup_platform_escrow.py` and are managed
through `/admin/owner/platform-accounts` (owner-only).

---

## 4. Account Lifecycle

```
                      ┌──────────────┐
                      │  No Account   │
                      └──────┬───────┘
                             │
                      Onboarding / Activation
                             │
                      ┌──────▼───────┐
                      │   Account     │
                      │  (inactive)   │
                      └──────┬───────┘
                             │
                      KYC + Terms Accepted
                             │
                      ┌──────▼───────┐
                      │   Account     │
                      │   (active)    │
                      └──────┬───────┘
                             │
                      Freeze / Unfreeze
                      (admin/compliance)
```

### 4.1 No Account
- User has never created a wallet.
- `AccountRepository.get_by_user_id()` returns `None`.
- Checkout must **not** create an account. User must choose a non-wallet payment method or complete wallet activation first.

### 4.2 Account Creation (Explicit Only)
- Triggered by: wallet activation page, admin console, or setup script.
- **Never** triggered by: checkout, payment processor, API client.
- Created via: `AccountRepository` direct insert or `OrganisationRegistrationService.create_org_wallet()`.
- Every creation step is tracked by `WalletCreationTracker` (session + database) for audit trail.

### 4.3 Active Account
- Supports deposits, transfers, withdrawals, and payments.
- Can be frozen by admin/compliance without deletion.

### 4.4 Wallet Creation Tracker
- `WalletCreationTracker` (`app/wallet/services/wallet_creation_tracker.py`) provides step-by-step traceability of the wallet creation lifecycle.
- Events are persisted to both Flask session (user-facing) and `wallet_creation_events` table (admin-facing).
- Events tracked: `initiated`, `email_verified`, `terms_accepted`, `kyc_checked`, `account_created`, `account_verified`, `activation_pending`, `activated`, `completed`, `failed`.
- Anti-hijacking: session binding with IP/user-agent tracking and ownership verification.
- Admins can view the complete creation timeline in the financial account detail page (`/wallet/financial/account/<public_id>`).

---

## 5. Platform Account Setup

Accommodation and event payments flow through platform accounts.

```
Guest Wallet  ──(transfer)──>  Platform Escrow  ──(payout)──>  Host Wallet
     │                              │
     │         commission           │
     └──────────────────────────────┘
```

### 5.1 Setup (One-Time)

Run the setup script:

```bash
python scripts/setup_platform_escrow.py
```

This script:
1. Creates the platform `Organisation` with `org_id="PLATFORM"` if missing.
2. Creates five `AccountModel` records with `owner_type=PLATFORM`.
3. Prints `PLATFORM_ORG_ID=<org.id>` to stdout.

**Copy `PLATFORM_ORG_ID` into your `.env` or deployment config.**

### 5.2 Runtime Lookup

`MarketplaceService._get_platform_account_id(currency)`:
1. Reads `PLATFORM_ORG_ID` from `current_app.config`.
2. Queries `AccountModel` by `user_id=PLATFORM_ORG_ID` and `currency`.
3. Because auto-creation is disabled, raises `RuntimeError` if the account
   does not exist. **This is intentional** — it prevents silent failures.

### 5.3 Environment Variable

| Variable | Description | Example |
|----------|-------------|---------|
| `PLATFORM_ORG_ID` | Internal BIGINT `id` of the platform organisation | `42` |
| `PLATFORM_COMMISSION_PCT` | Platform commission percentage | `10.0` |

---

## 6. Payment Processor Rules

### 6.1 Wallet Processor
- **Must not** auto-create accounts.
- **Must** check account existence before charging.
- **Must** check balance >= charge amount for `pay_now` and `deposit` timing.
- On failure, returns `(False, None, error_message)` — never raises.

### 6.2 Mobile Money / Card / Invoice
- No wallet account required.
- Mobile money and card are placeholders pending real gateway integration.
- Invoice creates no upfront charge; `payment_status = pending`.

### 6.3 Checkout Flow
```
User selects payment method
        │
        ├── wallet ──► Check account exists ──► Check balance ──► Charge
        │                    │                       │
        │                    ▼                       ▼
        │                 Flash warning         Flash insufficient
        │
        ├── mobile_money ──► Process via gateway
        ├── card ──► Process via gateway
        └── invoice ──► Create invoice, no charge
```

---

## 7. Repository Rules

### 7.1 AccountRepository

| Method | Behavior |
|--------|----------|
| `get_by_id(account_id)` | Returns `AccountModel` or `None`. Never creates. |
| `get_by_user_id(user_id, currency)` | Returns `AccountModel` or `None`. Never creates. |
| `get_or_create(user_id, currency)` | Returns `AccountModel` or `None`. **Does not create.** |
| `get_wallets_for_update(user_ids)` | Returns list with row locks. Missing wallets are omitted. |

### 7.2 WalletRepository (Wrapper)

| Method | Behavior |
|--------|----------|
| `get_by_user_id(user_id)` | Delegates to `AccountRepository.get_by_user_id()`. |
| `get_or_create_by_user_id(user_id)` | Delegates to `AccountRepository.get_or_create()`. Returns `Optional[AccountModel]`. |
| `get_balance(user_id)` | Returns balance dict. If no account, returns `exists=False, balance=0`. |

---

## 8. Security & Compliance Rules

1. **Never expose `user.id` (BIGINT) externally.** Use `public_id` (UUID) in APIs and URLs.
2. **All ledger writes use idempotency keys** (`client_request_id`) to prevent double-charges.
3. **AML checks** are enforced via `app.compliance.aml_service` for transactions above thresholds.
4. **Frozen accounts** cannot send, withdraw, or pay. `AccountRepository.freeze_account()` sets the flag.
5. **Forensic audit logging** must use real entity IDs. Never call audit log with `entity_id=None` on page views.
6. **Platform accounts** require `owner_type=PLATFORM` and `platform_account=True`. Never create platform accounts via user-facing flows.
7. **IDGuardMixin** validates FK assignments at runtime. UUID FK columns (ledger `account_id`, `transaction_id`, transaction `account_id`) are accepted as `uuid.UUID` objects. BIGINT FK columns (`user_id`, `frozen_by`) must be integers. String FK exceptions (`UserProfile.user_id`) accept UUID strings.
8. **FK constraints** are enforced at the database level: `accounts.user_id → users.id` (RESTRICT), `accounts.frozen_by → users.id` (SET NULL), `ledger_entries.account_id → accounts.id` (CASCADE), `ledger_entries.transaction_id → transactions.id` (CASCADE).

---

## 9. Testing Rules

- Tests that need wallet accounts must create them **explicitly** in fixtures.
- Do not rely on `get_or_create()` auto-creating accounts in tests.
- Use `AccountModel(user_id=..., owner_type=..., currency=...)` and add to session.
- Platform accounts should be created in test setup using `AccountModel(user_id=org.id, owner_type=AccountOwnerType.PLATFORM, platform_account=True, ...)`.

---

## 10. Cross-Module Payment Integration

### 10.1 Wallet as Source of Truth

Wallet owns every actual movement of money. Accommodation, transport, events, and any future module must treat wallet as the **single source of truth** for financial events.

```
Wallet Module (source of truth)
├── TransactionModel      ← immutable record of every financial event
├── LedgerEntryModel      ← double-entry records
├── AccountModel          ← balances derived from ledger
└── PaymentMethodConfig   ← global payment catalogue

Accommodation             Transport             Events
├── AccommodationBooking  ├── Booking           ├── EventRegistration
│   ├── wallet_txn_id     │   ├── wallet_txn_id │   ├── wallet_txn_id
│   └── payment_status    │   └── payment_status│   └── payment_status
└── AccommodationBookingPayment (thin index)
    ├── booking_id
    ├── wallet_txn_id      ← canonical link to TransactionModel
    ├── payment_reference
    ├── payment_status     ← cached from TransactionModel
    └── retry_count        ← module-specific
```

**Rule:** Every module stores only `wallet_txn_id` as the canonical reference. All amount, currency, gateway, and status reads must come from `TransactionModel` via that ID. Module-specific payment tables are thin indexes, not ledgers.

### 10.2 Accommodation Integration

- `AccommodationBooking.wallet_txn_id` → `TransactionModel.external_reference`
- `BookingService.confirm_booking()` calls `WalletService.transfer()` first, then sets `booking.payment_status = PAID`
- `AccommodationBookingPayment` is a thin module index: `booking_id`, `wallet_txn_id`, `payment_reference`, `payment_status`, `retry_count`
- **Do not** store `amount`, `currency`, or gateway timestamps in `AccommodationBookingPayment` — read them from `TransactionModel`

### 10.3 Transport Integration

- `Booking.wallet_transaction_id` → `TransactionModel.external_reference`
- `BookingPayment` is the thin module index: `booking_id`, `wallet_txn_id`, `payment_reference`, `payment_status`
- `TransportPaymentService.process_payment()` must call `WalletService.withdraw()` for wallet payments before updating the booking

### 10.4 Events Integration

- `EventRegistration.wallet_txn_id` → `TransactionModel.external_reference`
- `EventPaymentService` already calls `WalletService.withdraw()` for wallet payments
- No separate payment ledger table; `EventRegistration` itself is the thin wrapper

### 10.5 Migration Path to Unified Ledger

When wallet is ready to own a single payment-events table:

1. Create `payment_events` in wallet with columns: `booking_id`, `booking_type` (`accommodation`/`transport`/`event`), `payment_reference`, `wallet_txn_id`, `payment_status`, `payment_method`, `payment_gateway`, `gateway_transaction_id`, `failure_reason`, `retry_count`, `created_at`, `updated_at`
2. Backfill from `accommodation_booking_payments` and `transport_booking_payments` with `booking_type` discriminator
3. Drop module-specific payment tables
4. Modules read from `TransactionModel` + `payment_events` via `booking_type`

Because accommodation and transport now store only thin indexes with `wallet_txn_id`, this backfill is a simple `INSERT INTO payment_events SELECT ..., 'accommodation' FROM accommodation_booking_payments`.

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `RuntimeError: Wallet account not found` | User selected wallet but has no account | User must activate wallet or choose another payment method |
| `RuntimeError: Platform escrow account not found` | `PLATFORM_ORG_ID` not set or account missing | Run `scripts/setup_platform_escrow.py` and set env var |
| `Insufficient wallet balance` | Account balance < charge amount | User must top up wallet or choose another payment method |
| `AccountRepository.get_or_create()` returns `None` | Account does not exist and auto-creation is disabled | Create account explicitly via onboarding or setup script |
| `NameError: name 'datetime' is not defined` | Pre-existing bug in `availability_service.py` | Unrelated to wallet changes; fix in that module |

---

## 12. Related Files

| File | Purpose |
|------|---------|
| `app/wallet/models/ledger.py` | `AccountModel`, `LedgerEntryModel`, `AccountOwnerType`, `AccountStatus`, `AccountType` |
| `app/wallet/models/creation_tracker.py` | `WalletCreationEventModel` — persisted wallet creation lifecycle events |
| `app/wallet/models/__init__.py` | Wallet model exports including `WalletCreationEventModel` |
| `app/wallet/repositories/account_repository.py` | Account DB operations |
| `app/wallet/repositories/wallet_repository.py` | Wallet service wrapper |
| `app/wallet/services/wallet_service.py` | Transfer, balance, freeze operations |
| `app/wallet/services/wallet_creation_tracker.py` | `WalletCreationTracker` — step-by-step creation traceability with anti-hijacking |
| `app/wallet/services/wallet_status_service.py` | Wallet status, sidebar items, action buttons |
| `app/wallet/services/currency_service.py` | Currency conversion and rate management |
| `app/wallet/services/commission_service.py` | Platform commission recording |
| `app/utils/id_guard.py` | `IDGuard` — runtime FK assignment validation with UUID support |
| `app/accommodation/services/marketplace_service.py` | Booking payment/refund integration |
| `app/accommodation/services/payment_processors/wallet_processor.py` | Checkout wallet charging |
| `app/accommodation/models/booking_payment.py` | Thin accommodation payment index (linked to TransactionModel via wallet_txn_id) |
| `app/transport/models.py` | Transport BookingPayment (thin index with wallet_txn_id) |
| `app/events/payment_service.py` | Event ticket payment via WalletService.withdraw() |
| `scripts/setup_platform_escrow.py` | One-time platform org + all platform accounts creation |
| `app/admin/owner/routes.py` | Owner-only platform account management routes |
| `templates/owner/platform_accounts/` | Platform account management templates |
| `app/wallet/AFCON360_WALLET_PRODUCTION_GUIDE.md` | Operational runbook |

---

## 13. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-07-30 | Added FK constraints to `accounts.user_id` (RESTRICT) and `accounts.frozen_by` (SET NULL). Added `WalletCreationEventModel` for persisted tracker events. Updated `IDGuardMixin` to handle native UUID FK columns (`LedgerEntryModel.transaction_id`, `LedgerEntryModel.account_id`, `TransactionModel.account_id`). Added `get_events_for_account()` and `get_events_for_user()` to `WalletCreationTracker`. Added wallet creation events section to financial account detail template. Fixed sidebar endpoint names (`deposit_page` → `deposit`, `send_page` → `send`, `withdraw_page` → `withdraw`). Fixed UUID slicing in dashboard and account detail templates. | Engineering |
| 2026-07-28 | Added cross-module payment integration section. Wallet is now the single source of truth for all financial events. Accommodation and transport use thin payment indexes linked via `wallet_txn_id`. Events consumes `WalletService.withdraw()` directly. Documented migration path to unified `payment_events` table. | Engineering |
| 2026-07-26 | Added platform account structure: `AccountStatus`, `AccountType`, `account_number`, `account_type`, `status`, `platform_account`, financial controls, and `freeze()`/`unfreeze()` methods to `AccountModel`. Disabled auto-creation in `AccountRepository.get_or_create()`. Added mandatory payment method validation in checkout. Added owner-only platform account management routes and templates. | Engineering |

---

*Questions? Tag `@wallet-maintainer` in the engineering Slack channel.*
