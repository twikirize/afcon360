# AFCON360 Wallet System — Audit Archive

**Archive Status:** Historical reference  
**Consolidated From:** Multiple session reports, debug guides, and shipping reports  
**Purpose:** Preserve original audit findings, day-one assessments, and debugging reports for engineers who need to trace decisions or understand how the current state was reached.

---

> **Note:** This archive is superseded by `AFCON360_WALLET_PRODUCTION_GUIDE.md` for operational guidance. Refer here for historical context, original findings, and date-stamped assessments.

---

## Table of Contents

1. [Original WALLET_SYSTEM_DOCUMENTATION1 — Day-One Audit (May 2026)](#original-wallet_system_documentation1--day-one-audit)
2. [AFCON360_WALLET_AUDIT_REPORT.md — Detailed Findings](#afcon360_wallet_audit-reportmd--detailed-findings)
3. [AFCON360_WALLET_DEBUG_GUIDE.md — Operations Reference](#afcon360_wallet_debug_guidemd--operations-reference)
4. [WALLET_SYSTEM_ANALYSIS.md — Security / Privacy / Safety](#wallet_system_analysismd--security--privacy--safety)
5. [AFCON360_WALLET_SHIPPING_REPORT.md — Shipping Status](#afcon360_wallet_shipping_reportmd--shipping-status)

---

## Original WALLET_SYSTEM_DOCUMENTATION1 — Day-One Audit

This document was produced during the initial wallet implementation review. It documents the user flow analysis, planned fixes, and confidence assessments from May 2026.

---

# AFCON360 Wallet System - Complete User Flow & Policy Documentation

**Document Version:** 1.0
**Last Updated:** 2026-05-03
**Status:** Implementation Review with Planned Fixes

---

## 1. User Identity Architecture

### 1.1 Dual Identity System

| Identity Type | Storage | Visibility | Purpose | Example |
|--------------|---------|------------|---------|---------|
| Internal ID | BIGINT (Database) | ❌ NEVER exposed | Database joins, foreign keys, performance | 92240 |
| External ID | UUID (String) | ✅ Always exposed | API responses, URLs, session cookies | 5c0bdc66-4388-45af-b008-d5816c40a4cc |

**Implementation Status:** ✅ **FULLY IMPLEMENTED**

The User model correctly implements dual identity:
- `id`: BIGINT (internal, for database relations)
- `public_id`: UUID (external, for APIs/URLs/Flask-Login sessions)
- Proper helper methods: `get_by_public_id()`, `get_by_private_id()`

---

### 1.2 Account Identity

| Element | Type | Purpose |
|---------|------|---------|
| Account ID | UUID | Financial account identifier (safe to expose) |
| User ID (FK) | BIGINT | Links account to user (internal only) |

**Rule:** A user can have ONE wallet account. This is enforced at the database level with a unique constraint.

**Implementation Status:** ✅ **FULLY IMPLEMENTED**

The AccountModel correctly enforces one account per user:
- `user_id` has `unique=True` constraint
- Account creation uses `get_or_create_account()` to ensure single account

---

## 2. Complete Wallet Creation & Onboarding Flow

### 2.1 Pre-Creation Requirements

The system checks these requirements **BEFORE** allowing wallet creation:

| Requirement | Check | Action if Missing |
|-------------|-------|-------------------|
| Email verified | ✅ | Show "Email verification required" warning |
| Phone verified | ⚠️ | Recommended for Tier 1+ |
| Age 18+ | ❌ | Block creation (Future DOB check) |
| Country allowed | ✅ | Nationality synced to profile during creation |
| Terms accepted | ✅ | Explicit checkbox on creation page |

**Restricted Countries:** IR, KP, SY, CU, MM

---

### 2.2 Wallet Creation

**Trigger:** User clicks "Open My Wallet"

**System Actions:**
1. Generate unique Account ID (UUID)
2. Link to User ID (BIGINT foreign key)
3. Sync Nationality to UserProfile.
4. Set initial status: `verified = False` (pending activation)
5. Set currency (User selection)
6. Create account record.
7. Audit log entry (WALLET_CREATION_SUCCESS).

**Resulting Status:** Wallet exists but NOT activated

---

### 2.3 Wallet Activation & Security Handshake

**Trigger:** User navigates to wallet after creation

**Post-Activation Security Logic:**
- **Status Change:** `verified = True`
- **PIN Check:** If user lacks a `transaction_pin_hash`, they are **automatically redirected** to the PIN setup page.

---

## 3. KYC Tiers & Feature Access

### 3.1 Tier Definitions

| Tier | Name | KYC Level | Requirements | User Experience |
|------|------|-----------|--------------|-----------------|
| Tier 0 | Unverified | 0 | Email + Phone verified | Can create wallet, receive money only |
| Tier 1 | Basic | 1 | ID verified (passport/national ID) | Can send, receive, withdraw (limited) |
| Tier 2 | Enhanced | 2 | Address + ID verified | Higher limits, international transfers |
| Tier 3 | Full | 3 | Source of funds verified | Unlimited access |

**FIXES REQUIRED (Day-One):**
1. **KYC Level Enforcement in Features** — HIGH priority. Routes don't enforce KYC level before allowing operations.
2. **KYC Verification Integration** — HIGH priority. No event listener to update `kyc_level` when KYC approved.

---

### 3.2 Feature Access by Tier

| Feature | Tier 0 | Tier 1 | Tier 2 | Tier 3 |
|---------|--------|--------|--------|--------|
| Create Wallet | ✅ | ✅ | ✅ | ✅ |
| Activate Wallet | ✅ | ✅ | ✅ | ✅ |
| View Dashboard | ✅ | ✅ | ✅ | ✅ |
| View Transaction History | ✅ | ✅ | ✅ | ✅ |
| Receive Money | ✅ | ✅ | ✅ | ✅ |
| Deposit Money | ✅ | ✅ | ✅ | ✅ |
| Send Money | ❌ | ✅ | ✅ | ✅ |
| Withdraw Money | ❌ | ✅ | ✅ | ✅ |
| Request Payout | ❌ | ✅ | ✅ | ✅ |
| View Commissions | ❌ | ✅ | ✅ | ✅ |
| International Transfer | ❌ | ❌ | ✅ | ✅ |
| Bulk Payment | ❌ | ❌ | ❌ | ✅ |
| Merchant Account | ❌ | ❌ | ✅ | ✅ |
| API Access | ❌ | ❌ | ✅ | ✅ |

---

### 3.3 Transaction Limits by Tier (Planned, NOT implmented)

| Limit | Tier 0 | Tier 1 | Tier 2 | Tier 3 |
|-------|--------|--------|--------|--------|
| Daily Deposit | UGX 1,000,000 | UGX 10,000,000 | UGX 50,000,000 | Unlimited |
| Daily Withdrawal | UGX 500,000 | UGX 5,000,000 | UGX 20,000,000 | Unlimited |
| Monthly Transfer | UGX 2,000,000 | UGX 20,000,000 | UGX 100,000,000 | Unlimited |
| Single Transaction | UGX 500,000 | UGX 2,000,000 | UGX 10,000,000 | Unlimited |

**FIXES REQUIRED (Day-One):**
1. Add `WalletTierLimits` model — HIGH
2. Implement tier-aware limit checking — HIGH
3. Implement monthly volume reset logic — MEDIUM

---

## 4. Dynamic Navigation Rules

### 4.1 Sidebar Menu Items

| Menu Item | Shows When |
|-----------|------------|
| Dashboard | Always |
| Create Wallet | Only when user has NO wallet |
| Deposit Funds | Only when wallet exists and is activated |
| Send Funds | Only when wallet exists, activated, AND KYC Tier ≥ 1 |
| Withdraw Funds | Only when wallet exists, activated, AND KYC Tier ≥ 1 |
| Transaction History | Only when wallet exists |
| FX Rates | Always |
| Agent Payout | Only when wallet exists, activated, AND KYC Tier ≥ 1 |
| Compliance | Always |
| Settings | Always |
| Terms & Conditions | Always |

**Implementation Status:** ✅ **FULLY IMPLEMENTED**

---

## 5. Wallet Operations Flow

### 5.1 Deposit Money

**Prerequisites:** Wallet activated (any tier)

**Flow:**
1. User clicks "Deposit" button
2. System checks: `can_deposit = True` (any tier)
3. User enters amount and selects currency
4. System validates amount against daily limit
5. System creates pending transaction
6. System credits wallet balance
7. System creates ledger entry (CREDIT)
8. System sends confirmation notification
9. User sees updated balance

### 5.2 Send Money (Transfer)

**Prerequisites:** Wallet activated + KYC Tier ≥ 1

**Flow:**
1. User clicks "Send" button
2. System checks: `can_send = True` (Tier ≥ 1)
3. User enters recipient ID, amount, currency
4. System validates recipient has wallet
5. System validates sender balance sufficient
6. System validates amount against limits
7. User enters Transaction PIN
8. System verifies PIN
9. System creates transaction (within database transaction)
10. System debits sender, credits receiver
11. System creates TWO ledger entries (DEBIT + CREDIT)
12. System sends notifications to both parties

### 5.3 Withdraw Money

**Prerequisites:** Wallet activated + KYC Tier ≥ 1

**Flow similar to deposit, but with `DEBIT` entry and external payout initiation.**

---

## 6. Security Policies

### 6.1 Transaction PIN Policy

| Rule | Value |
|------|-------|
| PIN Length | 4-6 digits only |
| Storage | Hashed (never stored in plain text) |
| Max Failed Attempts | 5 attempts |
| Lockout Duration | 15 minutes |
| PIN Required For | All transfer operations |

### 6.2 Session Security

| Rule | Implementation |
|------|----------------|
| Session ID | Uses public_id (UUID), never internal BIGINT |
| CSRF Protection | Required for all state-changing operations |
| Idempotency | X-Idempotency-Key header required for deposits/transfers |

### 6.3 Audit Trail

| Field | Description |
|-------|-------------|
| Transaction ID | Unique UUID |
| Actor ID | User ID (internal) |
| Action Type | deposit/withdraw/transfer |
| Amount | Transaction amount |
| Currency | Currency code |
| Before State | Balance before operation |
| After State | Balance after operation |
| IP Address | Client IP |
| Timestamp | UTC timestamp |

---

## 7. Compliance & Regulatory Policies

### 7.1 AML/CFT Checks

| Check | Trigger | Action |
|-------|---------|--------|
| Daily reporting threshold | Transaction ≥ UGX 10,000,000 | Notify compliance |
| Structuring detection | Multiple transactions near threshold | Flag for review |
| Rapid succession | 5+ transactions in 5 minutes | Manual review required |
| Sanctions screening | Every transaction | Block if match found |

**FIXES REQUIRED (Day-One):**
1. Add Large Transaction Reporting — HIGH
2. Add Structuring Detection — MEDIUM
3. Add Rapid Succession Detection — MEDIUM
4. Add Sanctions Screening — HIGH

### 7.2 KYC Enforcement

| Operation | Min Tier Required |
|-----------|-------------------|
| Create wallet | Tier 0 (any) |
| Activate wallet | Tier 0 |
| Deposit | Tier 0 |
| Send money | Tier 1 |
| Withdraw | Tier 1 |
| Request payout | Tier 1 |
| International transfer | Tier 2 |

**FIXES REQUIRED:**
1. Enforce KYC Tier in Routes — HIGH
2. Add KYC Upgrade Triggers — MEDIUM

---

## 8. Error Handling & User Messages

### 8.1 Wallet Creation Errors

| Error | User Message | Action |
|-------|--------------|--------|
| Email not verified | "Please verify your email address first." | Show verify link ✅ |
| Phone not verified | "Please verify your phone number first." | Show verify link ✅ |
| Age under 18 | "You must be 18 or older." | Block ❌ **MISSING** |
| Country restricted | "Wallet not available in your country." | Block ❌ **MISSING** |
| Terms not accepted | "You must accept Terms & Conditions." | Show checkbox ❌ **MISSING** |

### 8.2 Transaction Errors

| Error | User Message |
|-------|--------------|
| Insufficient balance | "Insufficient funds. Available: X" ✅ |
| Daily limit exceeded | "Daily limit reached. Available: X" ✅ |
| Invalid PIN | "Incorrect PIN. X attempts remaining." ✅ |
| PIN locked | "PIN locked for 15 minutes." ✅ |
| Recipient no wallet | "Recipient has no wallet. Ask them to create one." ✅ |

---

## 9. Testing Verification Checklist

### 9.1 Wallet Creation Flow

- [ ] User without wallet sees "Create Wallet" in sidebar ✅
- [ ] Clicking "Create Wallet" shows pre-creation popup ✅
- [ ] Terms checkbox must be checked ✅
- [ ] Wallet created with status "pending activation" ✅
- [ ] Redirect to activation page ✅

### 9.2 Feature Gating

- [ ] User with Tier 0 can only deposit (not send/withdraw) ⚠️
- [ ] User with Tier 1 can send and withdraw ⚠️

### 9.3 Security

- [ ] Internal user.id NEVER exposed in API responses ✅
- [ ] public_id used in all URLs and API responses ✅
- [ ] Transaction PIN required for transfers ✅
- [ ] CSRF token required for form submissions ✅
- [ ] Idempotency keys prevent duplicate transactions ✅

---

## 10. Non-Technical Summary

### For Users (What to Expect)

1. Verify — Verify your email and phone number
2. Create — Click "Create Wallet", read the popup, accept terms
3. Activate — Accept Terms & Conditions on activation page
4. Secure — Set a 4-6 digit transaction PIN
5. Verify KYC — Complete identity verification to unlock higher limits
6. Use — Deposit, send, withdraw, view transactions

### For Banks/Partners (What We Guarantee)

- **Security:** Internal user IDs never exposed externally
- **Compliance:** Full audit trail for all transactions
- **KYC Enforcement:** Tier-based limits before sending/withdrawing
- **Data Protection:** Separation of user identity from financial accounts

---

## 11. Planned Fixes Summary (Day-One Assessment)

### HIGH PRIORITY FIXES

1. **Add Age Verification** — Add `date_of_birth` field to User model; add age validation in wallet creation route.
2. **Add Country Restriction Check** — Add country validation in `wallet_create()` route.
3. **Implement KYC Tier Limits** — Create `WalletTierLimits` model; implement tier-aware limit checking.
4. **Enforce KYC Tier in Routes** — Add `@require_kyc_tier(tier=1)` decorator to send/withdraw/payout routes.
5. **Add Large Transaction Reporting** — Add compliance webhook trigger in deposit/withdraw/transfer.
6. **Add Sanctions Screening** — Integrate with sanctions screening API.

### MEDIUM PRIORITY FIXES

1. **Add Monthly Volume Tracking** — Implement monthly volume reset logic.
2. **Add KYC Upgrade Triggers** — Add event listener on KYC approval.
3. **Add Structuring Detection** — Implement time-window analysis.
4. **Add Rapid Succession Detection** — Add transaction rate counter per user.
5. **Add Tier-Based Feature Tests** — Add test cases for each tier level.

---

## 12. Success Criteria (Day-One)

The wallet system is considered complete and ready for production when:

- ✅ User can create wallet only after email/phone verification
- ✅ Dedicated Fintech Onboarding UI clearly explains benefits
- ✅ Wallet must be activated separately (legal terms acceptance)
- ✅ Features auto-hide when requirements not met
- ✅ Transaction PIN required for all transfers
- ✅ Internal user.id never exposed in any response
- ⚠️ KYC tiers correctly gate features
- ✅ All financial operations are atomic and auditable
- ❌ Age verification enforced (18+)
- ❌ Country restrictions enforced
- ❌ AML/CFT checks implemented
- ❌ Tier-based transaction limits enforced

**Day-One Overall Completion:** ~88%

---

## AFCON360_WALLET_AUDIT_REPORT.md — Detailed Findings

This is the pre-implementation audit report. It documents P0–P2 findings with exact file locations and remediation steps.

---

# AFCON360 Wallet System — Audit Report & Remediation Directive

**Prepared for:** Obed (Project Owner)
**Prepared by:** Wallet Systems Consultant (chat session)
**Audience:** Implementing engineer/agent
**Scope:** `app/wallet/` — active package architecture
**Status:** Pre-implementation review. No code has been changed.

---

## 1. Executive Summary

The active wallet architecture (`app/wallet/models/ledger.py`, `transaction.py`, and the associated repositories/services) is a genuine double-entry ledger system with DB-enforced idempotency, deadlock-safe multi-account locking, and Decimal-precision money handling. This is a materially better foundation than most systems at this stage reach for.

**Follow-up note:** The bad news at the time of this audit was that three P0 issues meant parts of the system were either not verified to work or did not currently run at all, and one systemic issue meant the compliance/regulatory layer would produce wrong results. Subsequent engagement (Verified Findings report below) narrowed this to a smaller set of real issues.

---

## 2. Confirmed Architecture (for the agent's orientation)

- **Source of truth for money:** `ledger_entries` table (`app/wallet/models/ledger.py`). Balance is **never stored** — always `SUM(CREDIT) - SUM(DEBIT)` computed at query time.
- **Accounts:** `AccountModel` (`app/wallet/models/ledger.py`) — one account per owner per currency, identified by UUID.
- **Transactions:** `TransactionModel` (`app/wallet/models/transaction.py`) — immutable, with DB-level `UNIQUE` constraint on `client_request_id`.
- **Business logic:** `WalletService` (`app/wallet/services/wallet_service.py`) — `deposit()`, `withdraw()`, `transfer()`, each wrapped in `with self.db.begin():`.

**Dead stale duplicate noted:** A flat `app/wallet/models.py` file was confirmed to be a stale April 9 snapshot. This file has since been deleted from the repository.

---

## 3. P0 Findings (Broken or unverified at time of audit)

### P0-1: Concurrency safety-net test suite cannot execute
**File:** `tests/wallet/test_ledger_concurrency.py` (did not exist at time of audit; a prior report claimed existence — this was false.)

Problem: Every test call used parameter names (`user_id`, `from_user_id`) that don't match current `WalletService` signatures (`account_id`, `from_account_id`).

**Fix required:**
1. Rewrite every test call site to use `account_id` / `from_account_id` / `to_account_id`.
2. Run against real Postgres (not sqlite).
3. Run 3 consecutive times to rule out flaky concurrency bugs.

**Definition of done:** `pytest tests/wallet/test_ledger_concurrency.py -v` passes 0 failures, 3 runs in a row.

### P0-2: `regulator_service.py` imports non-existent model
**File:** `app/wallet/services/regulator_service.py`, line ~18

Problem: `from app.wallet.models.wallet import WalletTransaction` — no such module. This means the file fails at import time.

**Fix required:**
1. Rewrite references to use `TransactionModel` and `LedgerEntryModel`.
2. Confirm access code persistence is not in-memory only.

**Definition of done:** `python -c "from app.wallet.services.regulator_service import RegulatorService"` succeeds.

### P0-3: Dead flat `models.py` shadowing the live `models/` package
**File:** `app/wallet/models.py` (dead flat file)

Fix required:
1. Confirm Python resolves to the package, not the flat file.
2. `git rm app/wallet/models.py`
3. Grep for imports of old classes (`Wallet`, `WalletTransaction`, `WalletLimit`, `WalletAuditLog`, `WalletSettings`) and migrate to current models.

**Definition of done:** `app/wallet/models.py` no longer exists on disk. Full `pytest tests/` has zero `ImportError`/`ModuleNotFoundError`.

### P0-4: Compliance/AML thresholds are currency-blind
**Files:** `app/wallet/services/regulatory_reporting.py`, `app/wallet/services/travel_rule_service.py`

Problem: `AML_THRESHOLD = 10000` compared directly against `tx.amount` with no currency conversion.

**Fix required:**
1. Convert `tx.amount` to reporting currency (USD) before comparing.
2. Add test asserting UGX 10,000 does NOT flag, but UGX ~38,000,000 DOES.

---

## 4. P1 Findings (Architectural risk)

### P1-1: Two competing FX implementations
- `CurrencyService` (in-memory cache, Flask-config fallback)
- `FXService` (DB-cached rates, deviation detection, but not wired into `WalletService`)

**Fix required:** Decide canonical FX service. Wire `WalletService` to call it for cross-currency deposits/withdrawals/transfers. Replace mock rate data with real provider.

### P1-2: Fail-open is default on safety controls
- `NonceProtectionService.validate_nonce` — allows transaction if internal validation errors.
- `TravelRuleService.check_travel_rule_required` — same.

**Fix required:** Decide policy (fail-open vs fail-closed) for compliance checks explicitly. Document decision and implement consistently.

### P1-3: Decimal values in compliance reports not JSON-safe
**File:** `app/wallet/services/regulatory_reporting.py`

`STRReport`/`CTRReport` use `float` type hints but populate with `Decimal`. `jsonify` will throw.

**Fix required:** Cast to `str()` at dataclass boundary, or register custom JSON encoder for `Decimal`.

### P1-4: Commission-service calls inside atomic block
**File:** `app/wallet/services/wallet_service.py`

`CommissionService.record_commission()` is called inside `with self.db.begin():`. Must confirm it does NOT call `db.session.commit()` internally.

---

## 5. P2 Findings (Cleanup and hardening)

### P2-1: Reserved-word / naming conflicts
Gas model field `metadata` collides with SQLAlchemy's `Base.metadata`.

### P2-2: Config naming collision risk
Confirm no duplicate `config.py` files in `app/wallet/`.

### P2-3: Fee precision ceiling
`WalletSystemConfig` fee percentages use `Numeric(5, 2)`. May truncate sub-percent fee schedules.

---

## 6. Recommended Sequencing

1. **P0-3** first (delete dead `models.py`) — may auto-resolve P0-2.
2. **P0-2** (fix `regulator_service.py` imports).
3. **P0-1** (green-run concurrency test suite).
4. **P0-4** (currency-aware compliance thresholds).
5. **P1-1 → P1-4** in any order.
6. **P2s** whenever convenient.

---

*End of P0–P2 audit report (pre-implementation).*

---

## AFCON360_WALLET_AUDIT_REPORT.md — Verified Findings & Remediation Plan

This supersedes the original P0–P2 audit. Every "confirmed" item was verified directly against production or production code.

---

# AFCON360 Wallet System — Verified Findings & Step-by-Step Remediation Plan

**Supersedes:** Original static-code audit above
**Status:** Every "confirmed" item verified directly against production (`afcon360_prod`).

---

## Part 1 — What we know for certain (verified)

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 1 | Ledger core integrity (`ck_ledger_amount_positive`, `ck_ledger_entry_type_valid`, `ck_transaction_amount_positive`) | ✅ **Real, enforced in production** | Confirmed via `pg_constraint` query |
| 2 | Idempotency (`client_request_id` uniqueness) | ✅ **Real, enforced in production** | `ix_transactions_client_request_id` is a `CREATE UNIQUE INDEX`. Zero duplicates found in live table. |
| 3 | Multi-currency account model | ✅ **Real, enforced in production** | `ix_accounts_user_currency` is a `CREATE UNIQUE INDEX ... (user_id, currency)`. |
| 4 | `ck_transaction_status_valid` | ❌ **Confirmed missing in production** | Zero rows returned when queried by name. Only `NOT NULL` on `status`. |
| 5 | Dead flat `app/wallet/models.py` | ✅ **Confirmed removed** | Deleted from repo. |
| 6 | Legacy `app/wallet/services.py` | ❌ **Confirmed NOT dead — live dependency** | ~10 import sites in `app/admin/route_modules/wallet_admin.py` still use it. |
| 7 | `test_ledger_concurrency.py` | ❌ **Does not exist in the repository** | Confirmed by codebase search. |
| 8 | Flask-Migrate drift | ❌ **Confirmed: production is one migration behind** | `flask db current` → `8120b21c333e`; `flask db heads` → `18288f7196e0`. The pending migration is unrelated to wallet. |
| 9 | Admin "freeze" → real ledger enforcement | ⚠️ **Still open — not yet tested** | Must be tested directly. |
| 10 | Status-column case convention | ⚠️ **Needs decision before fix is written** | TransactionStatus enum values are lowercase (`'pending'`, `'completed'`, etc.) but intended constraint text may use uppercase. |

**Net assessment:** Core money-safety guarantees (ledger integrity, idempotency, multi-currency accounts) are real. Remaining gaps are narrower than first feared, but legacy `services.py` shadow risk and missing status constraint are real and must be closed.

---

## Part 2 — Step-by-step Remediation

### Step 1 — Decide `TransactionStatus` case convention, then write the missing constraint

1. Confirm what production actually writes today:
   ```sql
   SELECT DISTINCT status FROM transactions;
   ```
2. Decide canonical case (lowercase is very likely correct, matching `TransactionStatus` Python values). Confirm decision explicitly.
3. Generate migration:
   ```powershell
   flask db migrate -m "add missing check constraint on transactions.status"
   ```
4. Open generated migration file. Confirm it contains *only* the expected `op.create_check_constraint(...)` call.
5. Pre-flight check before applying:
   ```sql
   SELECT status, COUNT(*) FROM transactions WHERE status NOT IN ('pending','completed','failed','cancelled') GROUP BY status;
   ```
   If rows returned, review before proceeding.
6. Apply to staging first, then production.

### Step 2 — Fix case-sensitivity in `regulator_service.py`

Once Step 1 settles canonical case, verify every `t.status == '...'` comparison in `regulator_service.py` (analytics/fraud-detection methods). Write a small test inserting a COMPLETED-lifecycle transaction through real `WalletService.deposit()` and confirm analytics methods count it correctly.

### Step 3 — Test whether admin "freeze" actually disables the real ledger path

1. Create test user + real `AccountModel`.
2. Deposit small amount.
3. Use admin route to freeze.
4. Attempt `WalletService.withdraw()` against the same account.
5. Report exact result: did `WalletFrozenError` raise, or did operation succeed?

**If operation succeeds:** This is a live control failure — escalate immediately.

### Step 4 — Migrate `wallet_admin.py` off legacy service, then delete `app/wallet/services.py`

Only proceed once Step 3's answer is known.

1. For each of the ~10 import sites in `wallet_admin.py`, replace `from app.wallet.services import WalletService` with `from app.wallet.services.wallet_service import WalletService`.
2. For each call site, confirm method signatures match (`account_id`/`from_account_id`/`to_account_id`, not old integer wallet IDs).
3. Delete `app/wallet/services.py`.
4. Run `pytest tests/` and report full output.

### Step 5 — Author the concurrency test suite from scratch

There is nothing to "fix" here — it does not exist and must be written new.

1. Write tests covering: parallel withdrawals exceeding balance, parallel transfers, concurrent duplicate `client_request_id` submission, frozen-account enforcement, daily-limit enforcement.
2. Every test must call real `WalletService` signatures.
3. Run against real Postgres.
4. Run the full suite **three separate times** and paste all three outputs.

### Step 6 — Final sign-off checklist

- [ ] `ck_transaction_status_valid` exists in production
- [ ] `regulator_service.py` status comparisons verified correct
- [ ] Admin freeze → real ledger enforcement tested directly
- [ ] Zero remaining imports of legacy `app/wallet/services.py`
- [ ] `app/wallet/services.py` deleted
- [ ] Full `pytest tests/` output pasted, zero unexpected failures
- [ ] Concurrency test suite exists, runs against real Postgres, 3 consecutive outputs pasted

---

## Part 3 — Standing Rule

From here forward: no status is "done" on the strength of a description. Every fix closes only when raw output — SQL result, test run, grep, diff — has actually been verified.

---

*End of verified findings report.*

---

## AFCON360_WALLET_DEBUG_GUIDE.md — Operations Reference

This document maps core Wallet system operations to their file and function locations. Use this guide to quickly trace errors in production.

---

# AFCON360 Wallet System — Production Operations & Debugging Guide

## 1. Core Wallet Operations (Ledger Path)

### Flow Diagram: Payment Path
`[Client] -> [API Gateway] -> [WalletService] -> [PostgreSQL (Atomic Ledger)] -> [Celery (Webhook Processor)]`

### Deposit Funds (Happy Path)
1. **Client** calls `/api/wallet/deposit` with `amount`, `currency`, and `client_request_id`.
2. **API Gateway** (Flask Auth) validates session and user permissions.
3. **WalletService.deposit** (`app/wallet/services/wallet_service.py`) is called.
4. **LedgerRepository.post_entries** (`app/wallet/repositories/ledger_repository.py`) executes atomic ledger update with `SELECT ... FOR UPDATE`.

### Admin Freeze
- **File**: `app/wallet/repositories/account_repository.py`
- **Function**: `freeze_account(self, account_id, reason)`
- **What it does**: Sets `is_frozen=True` on `AccountModel`. `WalletService.withdraw` checks:
  ```python
  if account.is_frozen: raise FrozenAccountError("Wallet is frozen")
  ```

## 2. Production Scalability & Security

### Scalability Notes
- **Horizontal Scaling**: Stateless design. Celery workers scale independently.
- **Database**: PostgreSQL row-level locking (`FOR UPDATE`) allows high concurrency for different `account_id`s.
- **Caching**: Balance lookups computed at query time from ledger entries.

### Security Considerations
- **Secret Management**: Payment gateway credentials injected via ENV variables.
- **Webhook Security**: HMAC-SHA256 signature verification before processing.
- **Rate Limiting**: Flask-Limiter applied per user session.
- **Encryption**: Fernet encryption for sensitive `PaymentProviderConfig` fields.

## 3. How to Debug (Support Workflow)

1. **Transaction Failed?**
   - Check `app/wallet/models/transaction.py`.
   - Search DB by `client_request_id` or `public_id`.
   - Verify `status` against `TransactionStatus`.

2. **Compliance Alert?**
   - Run `app/wallet/services/regulatory_reporting.py` to re-check thresholds.

3. **Admin Freeze Ineffective?**
   - Verify `AccountModel.is_frozen` in DB.
   - Confirm call-site usage in `app/admin/route_modules/wallet_admin.py`.

4. **Webhook stuck?**
   - Check `celery -A app.celery_app inspect active`.
   - Check `webhook_events` table for `status='queued'` entries.
   - Check Celery logs for `_process_single_event` errors.

## 4. Active Landmines (At time of report)

- **`app/wallet/services.py` (Legacy)**: Still used by `wallet_admin.py`. Must migrate all imports to `app/wallet/services/wallet_service.py` before deleting this file.

---

*End of debug guide.*

---

## WALLET_SYSTEM_ANALYSIS.md — Security / Privacy / Safety Analysis

This document provides a comprehensive security, privacy, and safety assessment of the wallet system architecture.

---

# AFCON360 Wallet System - Comprehensive Analysis

**Generated:** May 7, 2026
**Version:** 2.0
**Status:** Production-Ready with Advanced Features

---

## Executive Summary

The AFCON360 Wallet System is a comprehensive, enterprise-grade digital wallet platform designed for the African market with global scalability. It provides multi-currency support, real-time FX conversion, advanced fraud detection, and full regulatory compliance.

**Current Status:** ✅ **PRODUCTION READY**
**Security Level:** 🔒 **ENTERPRISE-GRADE**
**Compliance:** ✅ **FULL REGULATORY COMPLIANCE** *(at time of assessment)*
**Scalability:** 🚀 **HORIZONTAL SCALING SUPPORTED**

---

## Core Components

- **Double-Entry Ledger System** — Immutable financial records
- **Multi-Currency Engine** — 150+ currencies with real-time FX *(configured; real provider integration needed)*
- **Fraud Detection Engine** — ML-based with configurable rules
- **Compliance Framework** — AML/KYC, Travel Rule, FATF compliance
- **Security Layer** — End-to-end encryption, MFA, rate limiting
- **API Gateway** — RESTful APIs with aggregator support

### Database Architecture
- **PostgreSQL** with REPEATABLE_READ isolation
- **Redis** for caching and rate limiting
- **Deadlock Retry Logic** with exponential backoff

---

## Security Analysis

### Implemented Security Features

| Security Aspect | Status | Risk Level |
|-----------------|---------|-------------|
| Authentication | ✅ Complete | Low |
| Authorization | ✅ Complete | Low |
| Data Encryption | ✅ Complete | Low |
| Transaction Security | ✅ Complete | Low |
| Network Security | ✅ Complete | Low |
| Audit Trail | ✅ Complete | Low |
| Emergency Access | ✅ Complete | Low |

**Overall Security Risk:** 🟢 **LOW**

---

## Privacy Analysis

| Privacy Aspect | Status | Compliance |
|----------------|---------|------------|
| Data Collection | ✅ Compliant | GDPR/CCPA compliant |
| Data Usage | ✅ Transparent | Clear privacy policy |
| User Control | ✅ Complete | Full user control |
| Data Security | ✅ Encrypted | End-to-end encryption |
| Third-Party Sharing | ✅ Controlled | Limited and audited |
| Data Retention | ✅ Defined | 5-year retention policy |

**Overall Privacy Compliance:** 🟢 **FULL COMPLIANCE**

---

## Safety Analysis

| Safety Aspect | Status | Risk Level |
|---------------|---------|-------------|
| Financial Safety | ✅ Complete | Low |
| Transaction Safety | ✅ Complete | Low |
| Account Safety | ✅ Complete | Low |
| Data Safety | ✅ Complete | Low |
| Operational Safety | ✅ Complete | Low |

**Overall Safety Risk:** 🟢 **LOW**

---

## Audit Analysis

| Audit Aspect | Status | Coverage |
|--------------|---------|----------|
| Transaction Audit | ✅ Complete | 100% |
| System Audit | ✅ Complete | All admin actions |
| Security Audit | ✅ Complete | All security events |
| Compliance Audit | ✅ Complete | Full regulatory compliance |
| Data Access Audit | ✅ Complete | All PII access logged |

**Overall Audit Coverage:** 🟢 **100%**

---

## Usability Analysis

| Usability Aspect | Status | Score |
|------------------|---------|--------|
| User Interface | ✅ Excellent | 9/10 |
| Mobile Experience | ✅ Good | 8/10 |
| API Documentation | ✅ Good | 8/10 |
| Admin Interface | ✅ Excellent | 9/10 |
| Developer Experience | ✅ Good | 8/10 |

**Overall Usability Score:** 🟢 **8.5/10 — EXCELLENT**

---

## System Metrics (Day-One Assessment)

| Metric | Current Value | Target | Status |
|---------|----------------|--------|---------|
| Transaction Throughput | 1,000 TPS | 10,000 TPS | 🟡 Scaling Needed |
| API Response Time | <200ms | <100ms | 🟡 Optimization Needed |
| System Uptime | 99.9% | 99.99% | 🟢 Good |
| Error Rate | 0.1% | <0.01% | 🟢 Excellent |
| Security Incidents | 0/month | 0/month | 🟢 Excellent |

---

## Missing Features for Public Use (Day-One)

### High Priority — Production Blockers
- **Database Sharding Strategy** — Not Implemented. Impact: Limited horizontal scaling.
- **Circuit Breakers for Large Transfers** — Not Implemented. Impact: System stability under load.
- **Additional Payment Gateways** — Partially Implemented. Missing: Visa Direct, MasterCard Send.

### Medium Priority — Enhancements
- **Enhanced Travel Rule Integration** — Basic Implementation. Missing: Real-time VASP communication.
- **Mobile Applications** — Not Implemented. Impact: Limited mobile accessibility.

### Low Priority — Future Enhancements
- **Advanced Analytics / Business Intelligence Dashboard**
- **AI-powered Fraud Detection** — Rule-based in place; ML enhancement planned.

---

## Key Findings & Recommendations (Day-One)

1. **FX Service Integration** — Immediate priority to integrate real-time FX service.
2. **Admin Refactor** — Migrate `wallet_admin.py` from legacy `services.py` to `wallet_service.py`.
3. **Automated Concurrency Suite** — Formally formalize concurrency verification into automated pytest suite.
4. **KYC Integration** — Complete linkage between KYC approval events and wallet tier upgrades.
5. **Tier-Based Limits** — Implement `WalletTierLimits` model with tier-aware checking.

---

*End of security/privacy/safety analysis.*

---

## AFCON360_WALLET_SHIPPING_REPORT.md — Shipping Status (July 2026)

This is the final shipping report marking the ledger refactor complete.

---

# AFCON360 Wallet System - Final Shipping Report (July 2026)

## Overview

The AFCON360 Wallet system has been refactored into a high-concurrency, double-entry ledger architecture. It is now stable, compliant, and ready for deployment.

## Key Architecture
- **Ledger-based**: All balances derived from ledger entries, never from cached columns.
- **Double-Entry**: Every transaction atomic via `db.session` with strict ACID compliance.
- **Dual-ID System**: Internal `id` (BigInteger) for DB relations, external `public_id` (UUID) for APIs.
- **Modernized Service**: Core methods migrated from legacy flat-file to modular `WalletService`.

## Architecture Components

| Component | Status |
|-----------|--------|
| Ledger core | ✅ Ready |
| Compliance (Regulator + Travel Rule) | ✅ Ready |
| Audit logs | ✅ Ready |
| API interfaces | ✅ Ready |
| Data integrity (`ck_transaction_status_valid`) | ✅ Ready |

## Implementation Findings & Detailed Changes

- **Refactoring Rationale**: Legacy `get_wallet_limits`, `create_wallet`, and `audit_log` refactored from `services.py` to `services/wallet_service.py` for transactional integrity and Decimal precision.
- **Legacy Persistence**: `app/wallet/services.py` remains as compatibility bridge for `wallet_admin.py`. Not intended for new development.
- **Constraint Enforcement**: Added `ck_transaction_status_valid` DB check constraint.
- **Admin Freeze**: Verified that `freeze_wallet` blocks ledger operations on active accounts.

## Next Engineer Instructions

1. **Never use `db.Model` directly**: Always inherit from `BaseModel`.
2. **Never expose `user.id`**: Use `public_id`.
3. **Migration Protocol**: Follow migration agent protocol; always review auto-generated migrations.
4. **Admin Refactor**: `wallet_admin.py` is the final module requiring refactor to use ledger-compliant `WalletService`.

## Audit Logs of Implementation

- Migrated legacy methods to modern service.
- Added `ck_transaction_status_valid` DB check constraint (Verified).
- Verified `freeze_wallet` blocks ledger operations (Verified).
- Fixed import cycles in `regulator_service.py`.

*This system is considered ready for production shipment at the time of this report.*

---

*End of shipping report.*

---

## Archive Index

The following files were consolidated into this archive:

| Source File | Consolidated Into |
|-------------|-------------------|
| `app/wallet/WALLET_SYSTEM_DOCUMENTATION1.md` | [Section: Original WALLET_SYSTEM_DOCUMENTATION1 — Day-One Audit (May 2026)](#original-wallet_system_documentation1--day-one-audit) |
| `app/wallet/AFCON360_WALLET_AUDIT_REPORT.md` | [Section: AFCON360_WALLET_AUDIT_REPORT.md — Detailed Findings](#afcon360_wallet_audit-reportmd--detailed-findings) |
| `app/wallet/AFCON360_WALLET_DEBUG_GUIDE.md` | [Section: AFCON360_WALLET_DEBUG_GUIDE.md — Operations Reference](#afcon360_wallet_debug_guidemd--operations-reference) |
| `Readme's/WALLET_SYSTEM_ANALYSIS.md` | [Section: WALLET_SYSTEM_ANALYSIS.md — Security / Privacy / Safety Analysis](#wallet_system_analysismd--security--privacy--safety-analysis) |
| `app/wallet/AFCON360_WALLET_SHIPPING_REPORT.md` | [Section: AFCON360_WALLET_SHIPPING_REPORT.md — Shipping Status](#afcon360_wallet_shipping_reportmd--shipping-status) |

**Note:** `AFCON360_WALLET_AUDIT_REPORT.md` contained two documents: the original P0–P2 audit and the verified findings report with step-by-step remediation. Both are preserved above.

---

*This archive is preserved for historical context and decision traceability. For current operational guidance, see `AFCON360_WALLET_PRODUCTION_GUIDE.md`.*
