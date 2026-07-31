# AFCON360 Payment System Architecture

**Complete technical reference for engineers, admins, and operators.**  
**Date:** 2026-07-28  
**Status:** Production-ready with known gaps documented below

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Core Payment Configuration](#2-core-payment-configuration)
3. [Wallet Module Architecture](#3-wallet-module-architecture)
4. [Accommodation Payment Flow](#4-accommodation-payment-flow)
5. [Events Payment Flow](#5-events-payment-flow)
6. [Payment Providers & Gateway](#6-payment-providers--gateway)
7. [Database Schema](#7-database-schema)
8. [Module Relationships](#8-module-relationships)
9. [Security & Compliance](#9-security--compliance)
10. [Current Gaps & TODO](#10-current-gaps--todo)
11. [File Inventory](#11-file-inventory)
12. [Quick Reference](#12-quick-reference)

---

## 1. Executive Summary

The **wallet module** is the single owner of all payment definitions and financial operations in AFCON360. It owns `PaymentMethodConfig`, the global registry of payment methods, and `TransactionModel`, the immutable ledger of every financial event. Accommodation, transport, and events consume wallet services and store only thin references (`wallet_txn_id`) — they do not maintain duplicate ledgers.

**Key components:**
- `PaymentMethodConfig` — global admin-controlled payment methods (mobile money, wallet, card), owned by wallet module
- `EventPaymentPreference` — per-event payment method acceptance
- `PropertyPaymentMethod` — per-property payment method acceptance
- `TransactionModel` — canonical immutable transaction record for every payment event
- `AccommodationBookingPayment` — thin accommodation index mapped to `TransactionModel` via `wallet_txn_id`
- `Transport BookingPayment` — thin transport index mapped to `TransactionModel` via `wallet_txn_id`
- `EventRegistration` — stores `wallet_txn_id` and `payment_status` directly; no separate ledger table
- `WalletService` — core financial operations (deposit, withdraw, transfer)
- `PaymentGateway` — external provider integrations (Flutterwave, Paystack, Mobile Money)
- `AccountModel` — chart of accounts (user wallets, org wallets, platform accounts)

**Money flow pattern:**
```
Customer pays → PaymentProcessor → WalletService → TransactionModel + LedgerEntryModel
                                     ↓
                               Module booking record
                               (AccommodationBooking / Booking / EventRegistration)
```

**Rule:** Wallet is the only module that writes to `TransactionModel`. Domain modules write to their own booking tables and link via `wallet_txn_id`.

---

## 2. Core Payment Configuration

### 2.1 `PaymentMethodConfig` Model

**File:** `app/wallet/models/payment_method.py`  
**Table:** `payment_method_configs`

This is the **single source of truth** for all available payment methods in the system. Admin can enable/disable methods globally.

| Field | Type | Description |
|-------|------|-------------|
| `method_id` | VARCHAR(50) | Unique ID, e.g. `mobile_money_mtn_ug`, `wallet` |
| `display_name` | VARCHAR(100) | Human-readable name |
| `method_type` | VARCHAR(50) | `mobile_money`, `wallet`, `card`, `bank_transfer` |
| `provider_name` | VARCHAR(50) | `mtn`, `airtel`, `safaricom`, `afcon360` |
| `country_code` | VARCHAR(2) | `UG`, `KE`, `NG` |
| `is_enabled` | BOOLEAN | Admin toggle |
| `is_active` | BOOLEAN | Runtime active flag |
| `requires_phone` | BOOLEAN | Whether phone number is required |
| `api_key` | VARCHAR(255) | Provider API key |
| `api_secret` | VARCHAR(255) | Provider API secret |
| `sandbox_url` | VARCHAR(255) | Sandbox endpoint |
| `production_url` | VARCHAR(255) | Production endpoint |
| `use_sandbox` | BOOLEAN | Sandbox mode flag |
| `supported_currencies` | JSON | `['UGX', 'USD']` |
| `min_amount` | NUMERIC(10,2) | Minimum transaction amount |
| `max_amount` | NUMERIC(10,2) | Maximum transaction amount |
| `transaction_fee` | NUMERIC(5,4) | Fee as decimal (0.0100 = 1%) |
| `config_json` | JSON | Additional provider config |
| `last_tested_at` | DATETIME | Last connectivity test |
| `last_test_result` | VARCHAR(20) | Test result status |
| `last_error_message` | TEXT | Last error |

**Key methods:**
- `get_available_methods(currency)` — returns enabled+active methods for currency
- `get_by_id(method_id)` — lookup by method_id string
- `supports_currency(currency)` — check currency support
- `calculate_fee(amount)` — calculate transaction fee
- `initialize_defaults()` — seed default methods (wallet, cash, MTN UG, Airtel UG, M-PESA KE, MTN NG, Airtel NG)

### 2.2 Default Payment Methods

| method_id | display_name | method_type | provider | country | currencies | min | max | fee |
|-----------|-------------|-------------|----------|---------|------------|-----|-----|-----|
| `wallet` | AFCON360 Wallet | wallet | afcon360 | UG | UGX, KES, NGN, USD, EUR, GBP | 0 | 10,000,000 | 0% |
| `cash` | Cash | cash | afcon360 | UG | UGX, KES, NGN, USD, EUR, GBP | 0 | 10,000,000 | 0% |
| `mobile_money_mtn_ug` | MTN Mobile Money Uganda | mobile_money | mtn | UG | UGX | 500 | 5,000,000 | 1% |
| `mobile_money_airtel_ug` | Airtel Money Uganda | mobile_money | airtel | UG | UGX | 500 | 5,000,000 | 1% |
| `mobile_money_mpesa_ke` | M-PESA Kenya | mobile_money | safaricom | KE | KES | 10 | 700,000 | 1% |
| `mobile_money_mtn_ng` | MTN Mobile Money Nigeria | mobile_money | mtn | NG | NGN | 100 | 10,000,000 | 1% |
| `mobile_money_airtel_ng` | Airtel Money Nigeria | mobile_money | airtel | NG | NGN | 100 | 10,000,000 | 1% |

### 2.3 `EventPaymentPreference` Model

**File:** `app/wallet/models/payment_method.py`  
**Table:** `event_payment_preferences`

Per-event payment preferences. Event organisers can restrict which global payment methods their event accepts.

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | BIGINT | FK to events |
| `user_id` | BIGINT | FK to users (organiser) |
| `accepted_methods` | JSON | List of method_ids |
| `preferred_currency` | VARCHAR(3) | Default currency |
| `auto_convert_wallet` | BOOLEAN | Auto-convert wallet currency |
| `wallet_conversion_rate` | NUMERIC(10,6) | Conversion rate |
| `payment_settings` | JSON | Additional settings |

**Key methods:**
- `accepts_method(method_id)` — check if event accepts a method
- `get_available_methods()` — returns intersection of global available + event accepted
- `get_or_create(event_id, user_id)` — auto-creates with all global methods accepted

---

## 3. Wallet Module Architecture

### 3.1 Models

**File:** `app/wallet/models/ledger.py`

| Model | Table | Purpose |
|-------|-------|---------|
| `AccountModel` | `accounts` | Financial accounts (user wallets, org wallets, platform accounts) |
| `LedgerEntryModel` | `ledger_entries` | Double-entry ledger records |

**File:** `app/wallet/models/transaction.py`

| Model | Table | Purpose |
|-------|-------|---------|
| `TransactionModel` | `transactions` | Immutable transaction records with idempotency |

**File:** `app/wallet/models/payment_method.py`

| Model | Table | Purpose |
|-------|-------|---------|
| `PaymentMethodConfig` | `payment_method_configs` | Global payment method configuration |
| `EventPaymentPreference` | `event_payment_preferences` | Per-event payment preferences |

**Key enums:**
- `EntryType` — `DEBIT`, `CREDIT`
- `AccountOwnerType` — `USER`, `ORGANISATION`, `PLATFORM`, `SYSTEM`
- `AccountStatus` — `ACTIVE`, `FROZEN`, `CLOSED`, `SUSPENDED`
- `AccountType` — `REVENUE`, `ESCROW`, `OPERATIONS`, `SETTLEMENT`, `RESERVE`, `USER_WALLET`, `ORG_WALLET`
- `TransactionType` — `DEPOSIT`, `WITHDRAW`, `TRANSFER`, `FEE`, `REFUND`, `ADJUSTMENT`
- `TransactionStatus` — `PENDING`, `COMPLETED`, `FAILED`, `CANCELLED`

### 3.2 Services

**File:** `app/wallet/services/wallet_service.py`

`WalletService` is the core financial engine. Key methods:

| Method | Purpose |
|--------|---------|
| `deposit(account_id, amount, currency, ...)` | Credit an account |
| `withdraw(account_id, amount, currency, ...)` | Debit an account |
| `transfer(from_account_id, to_account_id, amount, ...)` | Atomic transfer between accounts |
| `get_balance(user_id)` | Get user's wallet balance |
| `get_transaction_history(user_id, limit)` | Get recent transactions |

**Important:** All balance queries are derived from `ledger_entries`, never stored in `AccountModel`.

### 3.3 Repositories

| Repository | Purpose |
|------------|---------|
| `AccountRepository` | CRUD for `AccountModel` |
| `LedgerRepository` | Post ledger entries, calculate balances |
| `WalletRepository` | Wrapper around AccountRepository |
| `TransactionRepository` | CRUD for `TransactionModel` |
| `WebhookRepository` | Manage webhook events |

### 3.4 Payment Gateway

**File:** `app/wallet/services/payment_gateway.py`

Abstract gateway layer supporting:
- `PaymentProvider` enum: `FLUTTERWAVE`, `PAYSTACK`, `MTN_MOMO`, `AIRTEL_MONEY`, `VISA`, `MASTERCARD`, `UNIONPAY`, `BANK_TRANSFER`
- `PaymentMethod` enum: `CARD`, `BANK_TRANSFER`, `MOBILE_MONEY`, `USSD`, `QR_CODE`
- `PaymentRequest` / `PaymentResponse` dataclasses

Key functions:
- `handle_provider_webhook(provider, payload)` — route webhook to handler
- `verify_payment(provider, tx_ref)` — check payment status with provider
- `deposit_with_card(...)` — initiate card deposit
- `deposit_with_mobile_money(...)` — initiate mobile money deposit

### 3.5 Payment Providers

**Directory:** `app/wallet/payments/`

| File | Provider | Status |
|------|----------|--------|
| `flutterwave.py` | Flutterwave | Implemented |
| `paystack.py` | Paystack | Implemented |
| `mobile_money.py` | MTN, Airtel, Safaricom | Implemented |
| `paypal.py` | PayPal | Implemented |
| `alipay.py` | Alipay | Implemented |
| `wechat.py` | WeChat Pay | Implemented |
| `visa.py` | Visa | Implemented |

**Mobile Money flow:**
1. Create pending audit record
2. Call Mobile Money API
3. If success → call `WalletService.deposit()`
4. Update audit record with completion
5. If anything fails → update audit as failed

---

## 4. Accommodation Payment Flow

### 4.1 Models

**File:** `app/accommodation/models/booking.py`

`AccommodationBooking` payment fields:

| Field | Type | Description |
|-------|------|-------------|
| `payment_method` | VARCHAR(50) | `wallet`, `mobile_money`, `card`, `bank_transfer` |
| `payment_status` | VARCHAR(50) | `pending`, `paid`, `failed`, `refunded`, `partial_refund` |
| `wallet_txn_id` | VARCHAR(255) | External transaction reference |
| `paid_at` | DATETIME | Payment timestamp |

**Enums:**
- `AccommodationPaymentStatus` — `PENDING`, `PAID`, `FAILED`, `REFUNDED`, `PARTIAL_REFUND`
- `AccommodationPaymentMethod` — `WALLET`, `CARD`, `MOBILE_MONEY`, `BANK_TRANSFER`

**File:** `app/accommodation/models/booking_payment.py`

`AccommodationBookingPayment` — thin module-level index into `TransactionModel`. This is **not** a ledger. It maps a booking to its wallet transaction and caches payment status for fast queries.

| Field | Type | Description |
|-------|------|-------------|
| `booking_id` | BIGINT | FK to `accommodation_bookings` |
| `wallet_txn_id` | VARCHAR(255) | Canonical link to `TransactionModel` |
| `payment_reference` | VARCHAR(50) | Unique reference `PAY-XXXXX` |
| `payment_status` | VARCHAR(30) | Cached from `TransactionModel.status` |
| `payment_method` | VARCHAR(50) | Cached from `TransactionModel.payment_method` |
| `payment_gateway` | VARCHAR(50) | Cached from `TransactionModel.payment_provider` |
| `gateway_transaction_id` | VARCHAR(255) | Cached from `TransactionModel.external_reference` |
| `failure_reason` | TEXT | Module-specific error |
| `retry_count` | INTEGER | Module-specific retry tracking |

**Canonical fields live in wallet:** `amount`, `currency`, `fee_amount`, `conversion_rate`, `captured_at`, `refunded_at`, `gateway_response` — all stored in `TransactionModel.tx_metadata`. Read them via `wallet_txn_id`.

### 4.2 Services

**File:** `app/accommodation/services/payment_option_service.py`

`PaymentOptionService` — queries `PaymentMethodConfig` for available payment methods:

| Method | Purpose |
|--------|---------|
| `get_available_methods(currency)` | Returns list of available methods with icons |
| `get_method_by_id(method_id)` | Get specific method config |
| `is_method_available(method_id, currency)` | Check availability |
| `has_any_available(currency)` | Check if any method exists |

**File:** `app/accommodation/services/payment_policy_service.py`

`PaymentPolicyService` — manages property-level payment policies:

| Method | Purpose |
|--------|---------|
| `get_policy(property_id)` | Get booking policy for property |
| `get_or_create_policy(property_id)` | Get or create default policy |
| `get_allowed_options(property_id, booking_amount, guest_type)` | Returns allowed payment methods, timings, cancellation policy |

Returns dict with:
- `payment_methods` — list of allowed methods
- `allowed_methods` — list of method_ids
- `timing` — `pay_now`, `pay_on_arrival`, `deposit`, `deposit_percentage`
- `allowed_timings` — list of enabled timings
- `cancellation` — policy details
- `guest_requirements` — identity, phone, email, age requirements

**File:** `app/accommodation/services/payment_processors/`

Processor classes:

| File | Processor | Purpose |
|------|-----------|---------|
| `wallet_processor.py` | `WalletProcessor` | Charge user wallet |
| `mobile_money_processor.py` | `MobileMoneyProcessor` | Process mobile money |
| `card_processor.py` | `CardProcessor` | Process card payment |
| `invoice_processor.py` | `InvoiceProcessor` | Generate invoice (no charge) |

### 4.3 Checkout Flow

**File:** `app/accommodation/routes.py` — `guest_checkout()`

1. Validate required fields
2. Check property availability
3. Get payment policy for property
4. Validate selected payment method against allowed methods
5. **If wallet:** check account existence, check balance
6. Process payment via processor — **processor calls `WalletService` which writes to `TransactionModel`**
7. Update `AccommodationBooking` with `wallet_txn_id` and `payment_status`
8. Create/update thin `AccommodationBookingPayment` index record
9. Send notifications

**Key rule:** The `TransactionModel` write happens first. The module booking record and thin payment index are updated after wallet confirms success.

### 4.4 Payment Settings Management

Payment settings are controlled at two levels:

#### Owner Level (Global)

**Route:** `/owner/settings/wallet` → **Payment Methods** section  
**Access:** Owner only (`@require_owner_role`)

The owner manages the global payment catalogue via `PaymentMethodConfig`:

- **Enable/disable** payment methods globally (wallet, cash, mobile money, card)
- Changes take effect immediately across all properties
- Cash is included in defaults but disabled by default; owner must explicitly enable it
- UI: `templates/owner/wallet_settings.html` → Payment Methods tab
- API: `GET/POST /owner/settings/payment-methods`, `POST /owner/settings/payment-methods/<id>/toggle`

#### Host Level (Property-Specific)

**Route:** `/host/property/<id>/booking-policy`  
**Access:** Property host only

The host controls which globally-enabled methods their property accepts:

- **Payment timing:** `allow_pay_now`, `allow_pay_on_arrival`, `allow_deposit_payment`
- **Deposit settings:** `deposit_percentage`, `balance_due_days_before_checkin`
- **Accepted methods:** checkboxes for each globally-enabled `PaymentMethodConfig` method
- Saved to `PropertyBookingPolicy` and `PropertyPaymentMethod` tables
- Template: `templates/accommodation/host/booking_policy.html`

#### Guest Checkout

**Route:** `/accommodation/guest/checkout`  
**Logic:** `PaymentPolicyService.get_allowed_options()`

Checkout shows the intersection of:
1. Globally enabled methods (`PaymentMethodConfig.is_enabled=True`)
2. Property-accepted methods (`PropertyPaymentMethod.enabled=True`)
3. Property-allowed timings (`PropertyBookingPolicy.allow_*`)

If `cash` is globally enabled but the property does not accept it, cash is hidden from checkout.

---

## 5. Events Payment Flow

### 5.1 Models

**File:** `app/events/models.py`

`EventRegistration` payment fields:

| Field | Type | Description |
|-------|------|-------------|
| `payment_status` | VARCHAR(30) | `free`, `pending`, `paid`, `failed`, `refunded` |
| `wallet_txn_id` | VARCHAR(255) | Wallet transaction reference |
| `registration_fee` | FLOAT | Amount paid |

Constants:
- `PAYMENT_STATUS_FREE = "free"`
- `PAYMENT_STATUS_PENDING = "pending"`
- `PAYMENT_STATUS_PAID = "paid"`

### 5.2 Services

**File:** `app/events/payment_service.py`

`EventPaymentService` — processes ticket purchases:

| Method | Purpose |
|--------|---------|
| `process_ticket_purchase(...)` | Main entry point for ticket payment |
| `_process_wallet_payment(...)` | Wallet debit via `WalletService.withdraw()` |
| `_process_mobile_money_payment(...)` | Mobile money via `MobileMoneyService` |
| `_refund_payment(...)` | Compensating wallet deposit on failure |
| `get_available_payment_methods(event_currency, event_id)` | Returns methods filtered by event preferences |

**Flow:**
1. Check ticket capacity
2. Process payment via `WalletService.withdraw()` or `MobileMoneyService.process_deposit()`
3. Wallet creates `TransactionModel` record — this is the canonical financial event
4. Create `EventRegistration` records with `wallet_txn_id` pointing to the transaction
5. Reserve ticket seats
6. On registration failure → refund wallet payment (compensating `TransactionModel` entry)

**Key rule:** `EventRegistration` stores `wallet_txn_id` and `payment_status` only. All amounts, gateway details, and timing are read from `TransactionModel`. No separate payment ledger table is needed.

### 5.3 Routes

**File:** `app/events/routes.py`

| Route | Purpose |
|-------|---------|
| `GET /api/<identifier>/payment-methods` | Get available payment methods for event |
| `POST /api/<identifier>/register` | Register with payment processing |

---

## 6. Payment Providers & Gateway

### 6.1 Provider Integrations

All providers in `app/wallet/payments/`:

| Provider | File | Key Methods |
|----------|------|-------------|
| Flutterwave | `flutterwave.py` | `initiate_payment()`, `verify_payment()`, `process_refund()` |
| Paystack | `paystack.py` | `initiate_payment()`, `verify_payment()` |
| Mobile Money | `mobile_money.py` | `process_deposit()`, `process_withdrawal()` |
| PayPal | `paypal.py` | `create_order()`, `capture_payment()` |
| Alipay | `alipay.py` | `create_payment()`, `verify_payment()` |
| WeChat Pay | `wechat.py` | `create_payment()`, `verify_payment()` |
| Visa | `visa.py` | `initiate_payment()`, `verify_payment()` |

### 6.2 Webhook Handling

**File:** `app/wallet/api/webhooks.py`

Webhook endpoints:
- `POST /webhooks/flutterwave` — Flutterwave callbacks
- `POST /webhooks/paystack` — Paystack callbacks
- `POST /webhooks/mobile-money` — Mobile money callbacks

Features:
- Signature verification (HMAC SHA256/SHA512)
- PII scrubbing before DB storage
- Webhook event persistence in `webhook_events` table
- Retry logic via `WebhookService`

**File:** `app/wallet/services/webhook_service.py`

| Method | Purpose |
|--------|---------|
| `get_paginated_webhooks(...)` | List webhooks with filters |
| `get_stats()` | Webhook statistics |
| `retry_webhook(event_id)` | Re-queue failed webhook |
| `bulk_delete_webhooks(ids)` | Bulk cleanup |

---

## 7. Database Schema

### 7.1 Core Tables

| Table | Module | Purpose |
|-------|--------|---------|
| `payment_method_configs` | wallet | Global payment method configuration |
| `event_payment_preferences` | wallet | Per-event payment preferences |
| `accommodation_property_payment_methods` | accommodation | Property-to-method mapping |
| `accommodation_booking_payments` | accommodation | Payment event ledger |
| `accounts` | wallet | Financial accounts |
| `ledger_entries` | wallet | Double-entry records |
| `transactions` | wallet | Transaction records |
| `webhook_events` | wallet | Webhook logs |

### 7.2 `payment_method_configs` Schema

```sql
CREATE TABLE payment_method_configs (
    id BIGSERIAL PRIMARY KEY,
    method_id VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    method_type VARCHAR(50) NOT NULL,
    provider_name VARCHAR(50) NOT NULL,
    country_code VARCHAR(2) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE NOT NULL,
    is_active BOOLEAN DEFAULT FALSE NOT NULL,
    requires_phone BOOLEAN DEFAULT FALSE NOT NULL,
    api_key VARCHAR(255),
    api_secret VARCHAR(255),
    sandbox_url VARCHAR(255),
    production_url VARCHAR(255),
    use_sandbox BOOLEAN DEFAULT TRUE NOT NULL,
    supported_currencies JSON DEFAULT '[]',
    min_amount NUMERIC(10,2) DEFAULT 0.00,
    max_amount NUMERIC(10,2) DEFAULT 1000000.00,
    transaction_fee NUMERIC(5,4) DEFAULT 0.0000,
    config_json JSON DEFAULT '{}',
    last_tested_at TIMESTAMP,
    last_test_result VARCHAR(20),
    last_error_message TEXT,
    updated_by BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP
);
```

### 7.3 `accommodation_booking_payments` Schema

```sql
CREATE TABLE accommodation_booking_payments (
    id BIGSERIAL PRIMARY KEY,
    booking_id BIGINT NOT NULL REFERENCES accommodation_bookings(id),
    payment_reference VARCHAR(50) UNIQUE NOT NULL,
    idempotency_key VARCHAR(64) UNIQUE,
    amount NUMERIC(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    payment_method VARCHAR(50) NOT NULL,
    payment_method_details TEXT,
    payment_gateway VARCHAR(50),
    gateway_transaction_id VARCHAR(255),
    gateway_response TEXT,
    payment_status VARCHAR(30) DEFAULT 'pending',
    failure_reason TEXT,
    retry_count INTEGER DEFAULT 0,
    initiated_at TIMESTAMP,
    authorized_at TIMESTAMP,
    captured_at TIMESTAMP,
    refunded_at TIMESTAMP,
    is_reconciled BOOLEAN DEFAULT FALSE,
    reconciled_at TIMESTAMP,
    reconciled_by BIGINT,
    created_by BIGINT,
    updated_by BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP
);
```

### 7.4 Migrations

| Migration | Purpose |
|-----------|---------|
| `5582ce532c6f` | Created `payment_method_configs` table |
| `2459945a58a4` | Re-created `payment_method_configs` with preserved data |
| `69095234e1b0` | Created `accommodation_property_payment_methods` |
| `ed6307401623` | Multiple `payment_method_configs` alterations |

---

## 8. Module Relationships

### 8.1 Accommodation → Wallet

```
Accommodation Module:
  PaymentOptionService
      ↓ queries
  PaymentMethodConfig (wallet module)
      ↓ validates against
  PropertyPaymentMethod
      ↓ processes via
  PaymentProcessor (wallet, mobile_money, card, invoice)
      ↓ calls
  WalletService (wallet module)
      ↓ creates
  TransactionModel (canonical)
      ↓ updates
  AccommodationBooking (wallet_txn_id, payment_status)
      ↓ indexes
  AccommodationBookingPayment (thin: booking_id, wallet_txn_id, payment_status)
```

**Key files:**
- `app/accommodation/services/payment_option_service.py` — queries `PaymentMethodConfig` from wallet
- `app/accommodation/services/payment_policy_service.py` — property-level payment rules
- `app/accommodation/services/payment_processors/` — processor implementations
- `app/accommodation/services/booking_service.py` — creates thin `AccommodationBookingPayment` index after wallet confirms
- `app/accommodation/routes.py` — checkout orchestration

### 8.2 Events → Wallet

```
Events Module:
  EventPaymentService
      ↓ queries
  PaymentMethodConfig (wallet module)
      ↓ filters by
  EventPaymentPreference
      ↓ processes via
  WalletService.withdraw() / MobileMoneyService.process_deposit()
      ↓ creates
  TransactionModel (canonical)
      ↓ references
  EventRegistration (wallet_txn_id, payment_status)
```

**Key files:**
- `app/events/payment_service.py` — wallet/mobile money payment processing
- `app/events/payment_config.py` — backward-compatible re-exports from wallet
- `app/events/routes.py` — `/api/<identifier>/payment-methods`, `/api/<identifier>/register`

### 8.3 Transport → Wallet

```
Transport Module:
  TransportPaymentService
      ↓ queries
  PaymentMethodConfig (wallet module)
      ↓ processes via
  WalletService.withdraw()
      ↓ creates
  TransactionModel (canonical)
      ↓ updates
  Booking (wallet_transaction_id, payment_status)
      ↓ indexes
  BookingPayment (thin: booking_id, wallet_txn_id, payment_status)
```

**Key files:**
- `app/transport/services/payment_service.py` — transport payment processing with wallet integration
- `app/transport/models.py` — `Booking` + `BookingPayment` thin index

### 8.4 Admin → Wallet

```
Admin Module:
  admin_services/payment_methods.py
      ↓ manages
  PaymentMethodConfig (wallet module)
      ↓ initializes defaults via
  PaymentMethodConfig.initialize_defaults()
```

**Key files:**
- `app/admin/admin_services/payment_methods.py` — CRUD for payment methods
- `app/admin/routes.py` — admin payment method routes

---

## 9. Security & Compliance

### 9.1 Payment Security

1. **Idempotency** — `BookingPayment.idempotency_key` and `TransactionModel.client_request_id` prevent double-charges
2. **Webhook signature verification** — HMAC SHA256 (Flutterwave), SHA512 (Paystack)
3. **PII scrubbing** — `_scrub_sensitive()` redacts card numbers/CVVs before webhook storage
4. **Audit trail** — `AuditService.financial()` logs all payment events
5. **Balance derivation** — Wallet balances calculated from ledger, never stored

### 9.2 Compliance

| Component | Purpose |
|-----------|---------|
| `FraudDetectionService` | ML-based transaction scoring |
| `ComplianceEngine` | AML threshold checks, transaction monitoring |
| `TravelRuleService` | FATF Travel Rule compliance |
| `RegulatorService` | Regulatory reporting (AML, KYC, compliance) |
| `AdminAuditService` | Tracks all admin actions |

### 9.3 Known Security Gaps

1. **`accommodation/services/wallet_service.py` is a placeholder** — always returns success, not integrated with real `WalletService`
2. **No PCI DSS compliance** for card payments — placeholders only
3. **Webhook replay protection** not implemented — no timestamp/nonce validation beyond signature
4. **Mobile money sandbox URLs** are hardcoded in `PaymentMethodConfig` defaults

---

## 10. Current Gaps & TODO

### 10.1 Critical Gaps

| Gap | Impact | Location |
|------|--------|----------|
| `accommodation/services/wallet_service.py` is a placeholder | Accommodation wallet payments always succeed without real ledger | `app/accommodation/services/wallet_service.py` |
| Card payment processor not implemented | No real card processing | `app/accommodation/services/payment_processors/card_processor.py` |
| Invoice processor not implemented | No real invoice generation | `app/accommodation/services/payment_processors/invoice_processor.py` |
| `availability_service.py` has `NameError: name 'datetime' is not defined` | Blocks full app import | `app/accommodation/services/availability_service.py:143` |

### 10.2 Refactoring Opportunities

1. **Replace placeholder `WalletService` in accommodation** — `app/accommodation/services/wallet_service.py` should call real `WalletService`.
2. **Consolidate payment method enums** — `AccommodationPaymentMethod` enum in `booking.py` duplicates string values from `PaymentMethodConfig.method_type`. Should use a shared enum.
3. **Unify payment processor interface** — Each module has its own processor classes. Should standardise on `PaymentGateway` from wallet module.
4. **Add multi-currency platform accounts** — Currently all platform accounts are USD-only.

### 10.3 TODO

- [ ] Fix `availability_service.py` datetime import
- [ ] Implement real card payment processor
- [ ] Implement real invoice processor
- [ ] Integrate accommodation `wallet_service.py` with real `WalletService`
- [ ] Add automated tests for payment flows
- [ ] Implement escrow auto-release Celery task
- [ ] Add payment reconciliation reports
- [ ] Implement dual authorization approval UI

---

## 11. File Inventory

### Core Payment Config (Wallet Module)

| File | Purpose |
|------|---------|
| `app/wallet/models/payment_method.py` | `PaymentMethodConfig`, `EventPaymentPreference` — single source of truth |
| `app/wallet/__init__.py` | Exports `PaymentMethodConfig`, `EventPaymentPreference` |
| `app/wallet/models/__init__.py` | Exports payment method models |

### Events Module (Consumer)

| File | Purpose |
|------|---------|
| `app/events/payment_config.py` | Re-exports `PaymentMethodConfig`, `EventPaymentPreference` from wallet |
| `app/events/payment_service.py` | Event ticket payment processing |
| `app/events/models.py` | `EventRegistration` with payment fields |
| `app/events/routes.py` | `/api/<identifier>/payment-methods`, `/api/<identifier>/register` |

### Accommodation Module (Consumer)

| File | Purpose |
|------|---------|
| `app/accommodation/services/payment_option_service.py` | Queries `PaymentMethodConfig` from wallet |
| `app/accommodation/services/payment_policy_service.py` | Property-level payment policies |
| `app/accommodation/services/payment_processors/wallet_processor.py` | Wallet charging |
| `app/accommodation/services/payment_processors/mobile_money_processor.py` | Mobile money processing |
| `app/accommodation/services/payment_processors/card_processor.py` | Card processing (placeholder) |
| `app/accommodation/services/payment_processors/invoice_processor.py` | Invoice generation (placeholder) |
| `app/accommodation/services/wallet_service.py` | **Placeholder** — needs real wallet integration |
| `app/accommodation/services/host_service.py` | Uses `PaymentMethodConfig` from wallet for default property setup |
| `app/accommodation/models/property_payment_method.py` | Property-to-method mapping |
| `app/accommodation/models/booking_payment.py` | Thin accommodation payment index linked to `TransactionModel` via `wallet_txn_id` |

### Transport Module (Consumer)

| File | Purpose |
|------|---------|
| `app/transport/services/payment_service.py` | Transport payment processing with wallet integration |
| `app/transport/models.py` | `Booking` + `BookingPayment` thin index with `wallet_txn_id` |

### Accommodation Module (Consumer)
| `app/accommodation/models/booking.py` | Booking model with payment fields |
| `app/accommodation/routes.py` | Checkout orchestration |

### Wallet Module

| File | Purpose |
|------|---------|
| `app/wallet/models/ledger.py` | `AccountModel`, `LedgerEntryModel`, enums |
| `app/wallet/models/transaction.py` | `TransactionModel` with idempotency |
| `app/wallet/services/wallet_service.py` | Core financial operations |
| `app/wallet/services/payment_gateway.py` | Abstract gateway layer |
| `app/wallet/services/webhook_service.py` | Webhook management |
| `app/wallet/services/fraud_detection_service.py` | ML fraud scoring |
| `app/wallet/services/compliance_engine.py` | AML/KYC compliance |
| `app/wallet/payments/__init__.py` | Provider exports |
| `app/wallet/payments/mobile_money.py` | Mobile money integration |
| `app/wallet/payments/flutterwave.py` | Flutterwave integration |
| `app/wallet/payments/paystack.py` | Paystack integration |
| `app/wallet/api/webhooks.py` | Webhook endpoints |

### Admin

| File | Purpose |
|------|---------|
| `app/admin/admin_services/payment_methods.py` | CRUD for `PaymentMethodConfig` |
| `app/admin/routes.py` | Admin payment method routes |

### Migrations

| Migration | Purpose |
|-----------|---------|
| `migrations/versions/5582ce532c6f_add_agents_enabled_to_wallet_config.py` | Created `payment_method_configs` |
| `migrations/versions/2459945a58a4_add_fan_profiles_and_dashboard_contexts.py` | Re-created `payment_method_configs` |
| `migrations/versions/69095234e1b0_add_booked_by_snapshot_fields_to_.py` | Created `accommodation_property_payment_methods` |
| `migrations/versions/ed6307401623_make_wallet_admin_events_datetimes_.py` | Altered `payment_method_configs` |

---

## 12. Quick Reference

### Payment Method IDs

```
wallet                    → AFCON360 Wallet
cash                      → Cash
mobile_money_mtn_ug       → MTN Uganda
mobile_money_airtel_ug    → Airtel Uganda
mobile_money_mpesa_ke     → M-PESA Kenya
mobile_money_mtn_ng       → MTN Nigeria
mobile_money_airtel_ng    → Airtel Nigeria
card                      → Credit/Debit Card (placeholder)
invoice                   → Invoice (placeholder)
```

### Payment Timing Options (Accommodation)

| Timing | When Money Moves |
|--------|------------------|
| `pay_now` | Immediate payment at booking |
| `pay_on_arrival` | Payment at check-in |
| `deposit` | Partial payment now, balance later |
| `invoice` | No payment at booking, invoice sent later |

### Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `PaymentMethodConfig` | wallet | Global payment method config |
| `EventPaymentPreference` | wallet | Per-event accepted methods |
| `PropertyPaymentMethod` | accommodation | Per-property accepted methods |
| `BookingPayment` | accommodation | Payment event ledger |
| `EventRegistration` | events | Registration with payment status |
| `WalletService` | wallet | Core financial operations |
| `PaymentGateway` | wallet | Provider abstraction |
| `MobileMoneyService` | wallet | Mobile money integration |
| `EventPaymentService` | events | Event ticket payment |
| `PaymentOptionService` | accommodation | Available methods query |
| `PaymentPolicyService` | accommodation | Property payment policies |

### Environment Variables (Payment-related)

| Variable | Purpose |
|----------|---------|
| `FLUTTERWAVE_SECRET_KEY` | Flutterwave webhook verification |
| `PAYSTACK_SECRET_KEY` | Paystack webhook verification |
| `MOBILE_MONEY_SANDBOX` | Mobile money sandbox mode |
| `PLATFORM_ORG_ID` | Platform organisation for escrow |
| `PLATFORM_COMMISSION_PCT` | Platform commission percentage |

---

## 13. Refactoring Notes

### What Changed

`PaymentMethodConfig` was moved from `app/events/payment_config.py` to `app/wallet/models/payment_method.py`. The wallet module is now the **single owner** of payment method definitions.

**Before:**
```
accommodation → events (payment_config)
events → events (payment_config)
admin → events (payment_config)
```

**After:**
```
accommodation → wallet (payment_method)
events → wallet (payment_method)
admin → wallet (payment_method)
```

### Backward Compatibility

`app/events/payment_config.py` now re-exports `PaymentMethodConfig` and `EventPaymentPreference` from `app.wallet.models.payment_method` without deprecation warnings. This keeps existing imports working while the codebase transitions to direct wallet imports.

### Next Steps

- Update all `from app.events.payment_config import ...` to `from app.wallet import ...`
- Eventually remove `app/events/payment_config.py` re-export shim
- Remove duplicate `AccommodationPaymentMethod` enum in favor of shared wallet enum

---

*This document was auto-generated from the live codebase on 2026-07-28.*  
*For wallet architecture details, see `app/wallet/WALLET_ARCHITECTURE.md`.*  
*For escrow setup, see `app/wallet/ESCROW.md`.*  
*For implementation history, see `app/wallet/IMPLEMENTATION_REPORT.md`.*
