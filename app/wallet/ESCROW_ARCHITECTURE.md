# AFCON360 Escrow Account Architecture

## Purpose

This document is the **single source of truth** for the AFCON360 escrow account system.
It explains the data model, account lifecycle, service-type mapping, management UI,
and the rules every engineer must follow when touching escrow code.

**Audience:** Backend engineers, security auditors, compliance reviewers.
**Last updated:** 2026-07-26

---

## 1. Core Principles

| Principle | Rule |
|-----------|------|
| **Platform-owned** | All escrow accounts belong to the platform organisation (`owner_type=platform`, `platform_account=True`). |
| **Service-isolated** | Each service type gets its own escrow account, identified via `extra_data.service_type`. |
| **No auto-creation** | Escrow accounts are created explicitly via the owner dashboard or setup script. |
| **Funds holding** | Escrow accounts hold funds until service delivery is confirmed, then release to providers. |
| **Audit trail** | All escrow actions (create, freeze, unfreeze, transfer) are logged via `log_owner_action`. |
| **Dual auth** | High-risk escrow accounts require dual authorization for transfers. |

---

## 2. Data Model

Escrow accounts use the same `AccountModel` table as user and organisation wallets,
with distinguishing flags:

```
AccountModel (accounts table)
├── id                   UUID (primary key)
├── account_number       VARCHAR(20) — e.g. ESC-ACC-202607-1A2B
├── account_name         VARCHAR(200)
├── account_description  VARCHAR(500)
├── account_type         VARCHAR(30) = 'escrow'
├── owner_type           VARCHAR(20) = 'platform'
├── user_id              BIGINT = PLATFORM_ORG_ID
├── platform_account     BOOLEAN = True
├── status               VARCHAR(20) — active, frozen, closed, suspended
├── currency             VARCHAR(10), default 'USD'
├── is_frozen            BOOLEAN
├── daily_volume_limit   NUMERIC
├── monthly_volume_limit NUMERIC
├── require_dual_authorization BOOLEAN
├── extra_data           JSONB — contains service_type, icon, created_by, etc.
├── chart_of_accounts_code VARCHAR(20)
├── ifrs_category        VARCHAR(50)
├── created_at           TIMESTAMP
└── updated_at           TIMESTAMP

LedgerEntryModel (ledger_entries table)
├── id               UUID
├── account_id        UUID (FK to accounts.id)
├── amount            NUMERIC
├── currency          VARCHAR(10)
├── entry_type        VARCHAR(10) — DEBIT, CREDIT
├── transaction_id    UUID (FK to transactions.id)
├── created_at        TIMESTAMP
└── meta              JSONB
```

**Balance calculation:**
```python
balance = sum(ledger.amount for ledger in LedgerEntryModel
              where account_id=account.id and currency=account.currency)
```

---

## 3. Service Type Mapping

| Service Key | Display Name | Icon | Account Number Prefix | Description |
|-------------|--------------|------|----------------------|-------------|
| `accommodation` | Accommodation | `fa-bed` | `ESC-ACC` | Holds guest payments for accommodation bookings until check-out confirmation |
| `transport` | Transport | `fa-bus` | `ESC-TRN` | Holds passenger payments for transport bookings until trip completion |
| `events` | Events | `fa-calendar-alt` | `ESC-EVT` | Holds ticket payments for events until event completion |
| `tourism` | Tourism | `fa-umbrella-beach` | `ESC-TOU` | Holds payments for tourism services until service delivery |
| `tournament` | Tournament | `fa-trophy` | `ESC-TRN` | Holds payments for tournament participation and prizes |
| `wallet` | Wallet | `fa-wallet` | `ESC-WLT` | Holds wallet deposits and transfers for dispute resolution |

---

## 4. Account Lifecycle

```
                     ┌──────────────┐
                     │  No Account   │
                     └──────┬───────┘
                            │
                     Owner creates via dashboard
                            │
                     ┌──────▼───────┐
                     │   Account     │
                     │   (active)    │
                     └──────┬───────┘
                            │
                     Freeze / Unfreeze
                     (owner/compliance)
```

### 4.1 Creation
- Triggered by: owner dashboard (`/admin/owner/escrow/create`) or setup script.
- **Never** triggered by: guest checkout, payment processor, API client.
- Each `service_type` can have only one escrow account.

### 4.2 Active Account
- Supports incoming payments from guests/users.
- Supports outgoing transfers to service providers.
- Can be frozen by owner/compliance without deletion.

### 4.3 Frozen Account
- Cannot process new transactions.
- Existing funds remain locked until unfrozen or manually released.

---

## 5. File Structure

Per `tree.md` architecture:

```
app/
├── admin/
│   └── owner/
│       ├── escrow_services.py   # NEW: Escrow business logic
│       ├── escrow_routes.py     # NEW: Escrow routes (owner-only)
│       ├── routes.py            # MODIFIED: imports escrow_routes
│       └── __init__.py          # MODIFIED: registers escrow_bp
├── wallet/
│   ├── models/
│   │   └── ledger.py            # MODIFIED: added AccountStatus, AccountType, platform fields
│   └── repositories/
│       └── ledger_repository.py # USED: get_balance(account_id, currency)
└── models/
    └── system_config.py         # USED: SystemConfig for escrow settings

scripts/
└── setup_platform_escrow.py     # MODIFIED: creates all 5 platform accounts

templates/
└── owner/
    └── escrow/
        ├── index.html           # NEW: Dashboard overview
        ├── create.html          # NEW: Create escrow account
        ├── detail.html          # NEW: Account details
        ├── settings.html        # NEW: Escrow settings
        └── transactions.html    # NEW: Transaction history

static/
└── css/modules/admin/owner.css # EXISTING: owner dashboard styles
```

---

## 6. Routes

All routes are prefixed with `/admin/owner/escrow` and require owner authentication.

| Route | Method | Purpose |
|-------|--------|---------|
| `/admin/owner/escrow` | GET | Dashboard overview with stats |
| `/admin/owner/escrow/create` | GET, POST | Create a new escrow account |
| `/admin/owner/escrow/<uuid:account_id>` | GET | View account details |
| `/admin/owner/escrow/<uuid:account_id>/freeze` | POST | Freeze account |
| `/admin/owner/escrow/<uuid:account_id>/unfreeze` | POST | Unfreeze account |
| `/admin/owner/escrow/settings` | GET, POST | Global escrow settings |
| `/admin/owner/escrow/transactions` | GET | View all escrow transactions |

---

## 7. Service Methods

### `EscrowService.get_all_escrow_accounts()`
Returns list of dicts with `account`, `balance`, `service_type`, `display_name`.

### `EscrowService.get_escrow_account(account_id)`
Returns `AccountModel` filtered by UUID, `platform_account=True`, `account_type='escrow'`.

### `EscrowService.get_escrow_account_by_service(service_type)`
Returns existing escrow account for a service type, or `None`.

### `EscrowService.create_escrow_account(...)`
Creates a new escrow account with:
- Unique `account_number` (`ESC-<PREFIX>-<YYYYMM>-<RANDOM>`)
- `owner_type=platform`
- `platform_account=True`
- `account_type=escrow`
- `extra_data` containing `service_type`, `icon`, `created_by`, `created_at`

### `EscrowService.freeze_account(account_id, reason, frozen_by)`
Freezes account and logs owner action.

### `EscrowService.unfreeze_account(account_id, unfrozen_by)`
Unfreezes account and logs owner action.

### `EscrowService.get_account_balance(account_id)`
Returns `Decimal` balance via `LedgerRepository.get_balance(account.id, account.currency)`.

### `EscrowService.get_account_transactions(account_id, limit)`
Returns list of `LedgerEntryModel` entries for the account.

### `EscrowService.get_service_stats()`
Returns aggregated stats: total accounts, total balance, by_service breakdown, frozen count.

---

## 8. Settings

Escrow settings are stored in `SystemConfig` with `key` prefix `escrow_`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `escrow_auto_release_days` | string | `2` | Days after service completion before auto-release |
| `escrow_min_balance_alert` | string | `1000` | Alert threshold for low escrow balance |
| `escrow_require_dual_auth_default` | string | `true` | Whether new accounts default to dual auth |

---

## 9. Security & Compliance

1. **Owner-only access**: All routes use `@owner_login_required` which enforces `owner_required` + `login_required`.
2. **Audit logging**: Every create, freeze, and unfreeze action calls `log_owner_action` with full details.
3. **No auto-creation**: Escrow accounts are never created automatically by payment processors or checkout flows.
4. **Dual authorization**: Configurable per-account; enforced at transfer time by `WalletService.transfer()`.
5. **Platform org binding**: Every escrow account references `PLATFORM_ORG_ID` from app config.

---

## 10. Setup & Deployment

### 10.1 Create Platform Organisation + Accounts

Run the setup script:

```bash
python scripts/setup_platform_escrow.py
```

This creates:
- Platform `Organisation` with `org_id="PLATFORM"`
- Five platform `AccountModel` records (revenue, escrow, operations, settlement, reserve)

Copy printed `PLATFORM_ORG_ID` into `.env` or deployment config.

### 10.2 Create Service-Specific Escrow Accounts

After deployment, owners can create additional escrow accounts per service via:
```
/admin/owner/escrow/create
```

### 10.3 Migration

Run Alembic migration after modifying `AccountModel`:

```bash
flask db migrate -m "add platform account fields"
flask db upgrade
```

---

## 11. Integration Points

| Module | Integration | Description |
|--------|-------------|-------------|
| `app/accommodation` | `marketplace_service.py` | Uses platform escrow for booking payments |
| `app/events` | `payment_service.py` | Uses platform escrow for ticket payments |
| `app/transport` | `payment_service.py` | Uses platform escrow for trip payments |
| `app/wallet` | `wallet_service.py` | Transfers from guest wallets to escrow accounts |
| `app/admin/owner` | `escrow_routes.py` | Owner management UI |

---

## 12. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PLATFORM_ORG_ID not configured` | `.env` missing `PLATFORM_ORG_ID` | Run `scripts/setup_platform_escrow.py` and set env var |
| `Escrow account already exists` | Attempted to create duplicate for same service type | Use existing account or choose different service type |
| `Account frozen` | Account status is `frozen` | Unfreeze via owner dashboard or contact compliance |
| `Ledger balance mismatch` | Pre-existing data inconsistency | Run ledger reconciliation script |

---

## 13. Related Files

| File | Purpose |
|------|---------|
| `app/wallet/models/ledger.py` | `AccountModel`, `LedgerEntryModel`, `AccountOwnerType`, `AccountStatus`, `AccountType` |
| `app/wallet/repositories/ledger_repository.py` | Balance derivation from ledger entries |
| `app/wallet/repositories/account_repository.py` | Account DB operations |
| `app/admin/owner/escrow_services.py` | Escrow business logic |
| `app/admin/owner/escrow_routes.py` | Owner-only escrow routes |
| `app/admin/owner/routes.py` | Owner dashboard routes |
| `templates/owner/escrow/` | Escrow management templates |
| `scripts/setup_platform_escrow.py` | One-time platform org + accounts creation |
| `app/wallet/WALLET_ARCHITECTURE.md` | General wallet architecture |
| `app/models/system_config.py` | SystemConfig for escrow settings |

---

## 14. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-07-26 | Added `AccountStatus`, `AccountType`, platform account fields to `AccountModel`. Created `EscrowService`, `escrow_routes`, owner templates, and setup script. | Engineering |

---

*Questions? Tag `@wallet-maintainer` in the engineering Slack channel.*
