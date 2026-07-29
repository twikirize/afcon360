# AFCON360 Escrow System — Complete Guide

**For owners, admins, and engineers.**  
This document explains what the escrow system is, why it exists, how it was built, how to set it up, and how to use it—without assuming you can read Python code.

---

## 1. What Is Escrow?

Escrow is a **trusted holding account**. When a customer pays for a service, the money doesn’t go straight to the service provider. It goes into an escrow account first. Once the service is delivered and confirmed, the money is released to the provider.

**Real-world analogy:**  
Think of a hotel booking. You pay at checkout, but the hotel doesn’t receive the cash immediately. The money sits in a trusted account until you actually stay the night and check out. Only then does the hotel get paid.

### Why AFCON360 Needs Escrow

- **Protects customers** — If a service isn’t delivered, the money can be returned.
- **Protects service providers** — They know the money is reserved and will be paid once they do their part.
- **Builds trust** — Both sides know a neutral platform holds the funds.
- **Regulatory-ready** — Financial rules require clear separation of customer funds from operating money.

---

## 2. The Five Platform Accounts

AFCON360 uses **five separate accounts** inside one platform organisation. Each has a specific job.

| Account Number | Name | Purpose | When Money Moves |
|----------------|------|---------|------------------|
| `00000001` | **Platform Revenue** | Collects platform commissions and fees | Automatically deducted when a booking is completed |
| `00000002` | **Platform Escrow** | Holds guest payments until stay/service completion | Guest pays → stays here → released to host/provider after completion |
| `00000003` | **Platform Operations** | Pays for platform running costs | Used internally for server costs, staff salaries, etc. |
| `00000004` | **Platform Settlement** | Bulk payouts to hosts/providers | Large batch payments to many providers at once |
| `00000005` | **Platform Reserve** | Emergency/contingency funds | Only used in exceptional situations |

### Which Account Should I Use?

| Scenario | Account |
|----------|---------|
| A guest books accommodation and pays | **Platform Escrow** (`00000002`) |
| The platform takes its 10% commission | **Platform Revenue** (`00000001`) |
| The host receives their payout after the stay | **Platform Settlement** (`00000004`) or **Platform Operations** (`00000003`) |
| We need to keep extra funds for emergencies | **Platform Reserve** (`00000005`) |

---

## 3. How the Money Flows

```
Guest pays $1,000 for accommodation
        │
        ▼
[Platform Escrow 00000002]  ← $1,000 sits here
        │
        │  Stay is completed and confirmed
        │
        ├──────────────────┐
        │                  │
        ▼                  ▼
Host gets $900       Platform keeps $100
(Platform Settlement) (Platform Revenue)
```

---

## 4. Setup Instructions

### Step 1: Database Migration

Run the migration to add the new account fields:

```bash
flask db upgrade
```

If you get an error about `accounts_user_id_key` or `ix_accounts_user_currency`, run this first:

```bash
.venv\Scripts\python.exe -c "
from app import create_app
from app.extensions import db
from sqlalchemy import text
app = create_app()
with app.app_context():
    db.session.execute(text('ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_user_id_key'))
    db.session.execute(text('DROP INDEX IF EXISTS ix_accounts_user_currency'))
    db.session.commit()
    print('Cleaned up old constraints')
"
```

Then re-run:
```bash
flask db upgrade
```

### Step 2: Create the Platform Organisation and Accounts

Run the setup script:

```bash
python scripts/setup_platform_escrow.py
```

You should see:
```
============================================================
PLATFORM ACCOUNT SETUP COMPLETE
============================================================
Organisation ID (internal): 4
Organisation public_id:     <UUID>

  00000001: Platform Revenue Account (revenue)
  00000002: Platform Escrow Account (escrow)
  00000003: Platform Operations Account (operations)
  00000004: Platform Settlement Account (settlement)
  00000005: Platform Reserve Account (reserve)
============================================================
Set this in your .env or deployment config:
PLATFORM_ORG_ID=4
============================================================
```

### Step 3: Set Environment Variables

Add these to your `.env` file:

```bash
PLATFORM_ORG_ID=4
PLATFORM_COMMISSION_PCT=10.0
```

| Variable | What It Is | Example |
|----------|------------|---------|
| `PLATFORM_ORG_ID` | The internal database ID of the platform organisation. This links all 5 accounts to one owner. | `4` |
| `PLATFORM_COMMISSION_PCT` | The percentage the platform takes from each transaction. | `10.0` means 10% |

**Important:** If you ever recreate the database and re-run the setup script, the `PLATFORM_ORG_ID` might change. Always copy the new value from the script output into `.env`.

### Step 4: Restart the Application

```bash
python app.py
```

---

## 5. How to Manage Escrow Accounts (Owner Dashboard)

You don’t need to touch code to manage escrow. Everything is available in the owner dashboard.

### 5.1 View All Platform Accounts

**URL:** `/admin/owner/platform-accounts`

Here you can see:
- All 5 platform accounts
- Current balance of each account
- Account status (active / frozen)
- Daily and monthly limits

### 5.2 Create Service-Specific Escrow Accounts

**URL:** `/admin/owner/escrow/create`

If you need a separate escrow account for a specific service (e.g., Transport, Events, Tourism), you can create one here.

**Available service types:**
- Accommodation
- Transport
- Events
- Tourism
- Tournament
- Wallet

**Rules:**
- Each service type can have only **one** escrow account.
- If you try to create a second one for the same service, the system will tell you it already exists.
- Dual authorization can be required for large transfers.

### 5.3 View Escrow Dashboard

**URL:** `/admin/owner/escrow`

Shows:
- Total escrow balance across all accounts
- Number of frozen accounts
- Active services with escrow enabled
- Breakdown by service type

### 5.4 Freeze / Unfreeze Accounts

If an account needs to be stopped (e.g., suspicious activity, dispute):

1. Go to `/admin/owner/platform-accounts` or `/admin/owner/escrow`
2. Click **View Details** on the account
3. Click **Freeze Account** and provide a reason
4. To unfreeze, click **Unfreeze Account**

**Frozen accounts cannot:**
- Receive new payments
- Send money to providers
- Process any transactions

### 5.5 Configure Global Settings

**URL:** `/admin/owner/escrow/settings`

| Setting | What It Controls | Default |
|---------|------------------|---------|
| Auto-Release Days | How many days after service completion before funds are automatically released to the provider | `2` |
| Minimum Balance Alert | Alert threshold when escrow balance falls below this amount | `1000` |
| Require Dual Authorization by Default | Whether new escrow accounts require two admins to approve large transfers | `true` |

---

## 6. File Inventory

Everything is organised by type. No surprises.

### Python Backend (`app/`)

| File | What It Does |
|------|--------------|
| `app/wallet/models/ledger.py` | The `AccountModel` database table. Added platform account fields: `account_number`, `account_type`, `status`, `platform_account`, limits, `extra_data`, and `freeze()`/`unfreeze()` methods. |
| `app/admin/owner/escrow_services.py` | Business logic for creating, freezing, unfreezing, and querying escrow accounts. |
| `app/admin/owner/escrow_routes.py` | Web routes for the owner escrow dashboard (`/admin/owner/escrow/*`). |
| `app/admin/owner/routes.py` | Owner dashboard routes including platform account management (`/admin/owner/platform-accounts/*`). |
| `app/admin/owner/__init__.py` | Registers the escrow blueprint onto the owner blueprint. |
| `app/models/system_config.py` | Stores global escrow settings (auto-release days, alerts, dual auth). |

### Scripts

| File | What It Does |
|------|--------------|
| `scripts/setup_platform_escrow.py` | One-time script. Creates the platform organisation and all 5 platform accounts. Prints `PLATFORM_ORG_ID` for your `.env`. |

### Templates (`templates/`)

| File | What It Shows |
|------|--------------|
| `templates/owner/platform_accounts/index.html` | Grid of all platform accounts with balances |
| `templates/owner/platform_accounts/detail.html` | Single account view with freeze/unfreeze controls |
| `templates/owner/escrow/index.html` | Escrow dashboard with stats and service breakdown |
| `templates/owner/escrow/create.html` | Form to create a new service-specific escrow account |
| `templates/owner/escrow/detail.html` | Single escrow account view with transactions |
| `templates/owner/escrow/settings.html` | Global escrow configuration form |
| `templates/owner/escrow/transactions.html` | Paginated transaction history for all escrow accounts |

### Documentation

| File | What It Contains |
|------|------------------|
| `app/wallet/WALLET_ARCHITECTURE.md` | General wallet architecture, account lifecycle, repository rules |
| `app/wallet/ESCROW_ARCHITECTURE.md` | Detailed escrow architecture for engineers |

### Database Migration

| File | What It Does |
|------|--------------|
| `migrations/versions/88d91ff49abe_add_platform_account_fields.py` | Adds all new columns to the `accounts` table with safe defaults for existing rows |

---

## 7. Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PLATFORM_ORG_ID` | **Yes** | None | Internal database ID of the platform organisation. Get this by running `python scripts/setup_platform_escrow.py`. |
| `PLATFORM_COMMISSION_PCT` | No | `10.0` | Percentage the platform takes from each completed transaction. |

### Where to Set Them

**Local development (`.env`):**
```bash
PLATFORM_ORG_ID=4
PLATFORM_COMMISSION_PCT=10.0
```

**Production (deployment config / secrets manager):**
```bash
PLATFORM_ORG_ID=4
PLATFORM_COMMISSION_PCT=10.0
```

**Never** hard-code these in Python files. They are environment-specific.

---

## 8. How Escrow Is Used by Other Modules

The escrow accounts are not just for show. Other parts of the system use them automatically.

| Module | How It Uses Escrow |
|--------|-------------------|
| **Accommodation** | When a guest pays, funds go to the platform escrow account. After check-out and confirmation, funds are released to the host minus the platform commission. |
| **Events** | Ticket payments go to escrow. After the event is marked complete, organisers receive their payout. |
| **Transport** | Passenger payments go to escrow. After the trip is confirmed complete, the driver/company gets paid. |
| **Tourism** | Tour payments go to escrow. After the service is delivered, the provider is paid. |
| **Tournament** | Entry fees and prize payouts flow through escrow. |
| **Wallet** | Internal wallet transfers may use escrow for dispute resolution. |

### What the Code Does (Simplified)

1. **Guest selects payment method** → Wallet / Mobile Money / Card / Invoice
2. **If wallet is selected:**
   - Check that the guest has a wallet account
   - Check that the guest has enough balance
   - Transfer funds from guest wallet → **Platform Escrow** (`00000002`)
3. **If mobile money / card / invoice:**
   - Payment is processed by the external provider
   - Funds are still directed to the platform escrow account
4. **When service is completed:**
   - System calculates host/provider amount
   - System calculates platform commission
   - Transfers host amount → **Platform Settlement** (`00000004`)
   - Transfers commission → **Platform Revenue** (`00000001`)

---

## 9. Security & Compliance Rules

1. **No auto-creation** — Escrow accounts are never created automatically. An owner must create them explicitly.
2. **Dual authorization** — Large transfers from escrow can require two separate approvals.
3. **Audit trail** — Every create, freeze, unfreeze, and transfer is logged with who did it and when.
4. **Frozen accounts stop everything** — If an account is frozen, no money in or out until unfrozen.
5. **Platform-only ownership** — All escrow accounts belong to the platform organisation. No individual user or external organisation can own an escrow account.
6. **Balance is never stored** — Balances are calculated from transaction records, not stored in a column. This prevents tampering.

---

## 10. Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `PLATFORM_ORG_ID not configured` | Missing from `.env` | Run `python scripts/setup_platform_escrow.py` and copy the printed value into `.env` |
| `Duplicate key value violates unique constraint "accounts_user_id_key"` | Old database constraint blocking multiple accounts per org | Run the cleanup SQL: `ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_user_id_key; DROP INDEX IF EXISTS ix_accounts_user_currency;` |
| `Escrow account already exists` | Tried to create two accounts for the same service type | Use the existing account. Each service type can have only one escrow account. |
| `Account frozen` | Status is `frozen` | Unfreeze via the owner dashboard or contact compliance |
| `Insufficient wallet balance` | Guest wallet doesn’t have enough funds | Guest must top up wallet or choose another payment method |

---

## 11. Frequently Asked Questions

### Q: Can I delete an escrow account?
**A:** No. Escrow accounts can be frozen but not deleted, because historical transactions must remain traceable.

### Q: What happens if the platform org ID changes?
**A:** If you recreate the database and re-run the setup script, a new platform org will be created with a new ID. Update `PLATFORM_ORG_ID` in `.env` to the new value printed by the script.

### Q: Can a host/provider withdraw directly from escrow?
**A:** No. Funds are released by the system after service completion confirmation. Hosts receive payouts to their own wallets or bank accounts.

### Q: What currency are escrow accounts in?
**A:** Currently USD. The setup script creates accounts with `currency='USD'`. Multi-currency support would require additional configuration.

### Q: Who can see escrow accounts?
**A:** Only owners and super admins can view and manage escrow accounts via `/admin/owner/platform-accounts` and `/admin/owner/escrow`.

### Q: What if I need more than 5 platform accounts?
**A:** The 5 accounts are the standard financial chart of accounts. If you need a new account type, add it to `scripts/setup_platform_escrow.py` and create a corresponding `AccountType` enum value in `app/wallet/models/ledger.py`.

---

## 12. Quick Reference Card

```
SETUP (first time only)
======================
1. flask db upgrade
2. python scripts/setup_platform_escrow.py
3. Copy PLATFORM_ORG_ID into .env
4. python app.py

DAILY USE
=========
View accounts:  /admin/owner/platform-accounts
Escrow dashboard: /admin/owner/escrow
Create escrow:   /admin/owner/escrow/create
Settings:        /admin/owner/escrow/settings

ACCOUNT MAP
===========
00000001 = Revenue (platform keeps this)
00000002 = Escrow (money sits here during booking)
00000003 = Operations (paying bills)
00000004 = Settlement (batch payouts to hosts)
00000005 = Reserve (emergency funds)

MONEY FLOW
==========
Guest pays → Escrow (00000002)
           → Host paid from Settlement (00000004)
           → Platform keeps Revenue (00000001)
```

---

*Last updated: 2026-07-28*  
*Maintained by: AFCON360 Engineering*  
*Questions? Tag `@wallet-maintainer`*
