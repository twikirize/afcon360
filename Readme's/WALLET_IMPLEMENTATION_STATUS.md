# Wallet Implementation Status Report

## Missing Routes/Endpoints in `app/wallet/routes.py`

The following endpoints are referenced in templates but NOT IMPLEMENTED:

| Endpoint | Referenced In | Status |
|----------|--------------|--------|
| `wallet.wallet_dashboard` | base.html (lines 143, 152, 239, 246, 247) | MISSING |
| `wallet.wallet_home` | public_home.html (lines 70, 74, 251) | MISSING |
| `wallet.deposit_page` | wallet_dashboard.html (line 14) | MISSING |
| `wallet.send_page` | wallet_dashboard.html (line 17) | MISSING |
| `wallet.withdraw_page` | wallet_dashboard.html (line 20) | MISSING |
| `wallet.wallet_transactions` | wallet_dashboard.html (lines 23, 57) | MISSING |
| `wallet.deposit_form` | templates/wallet/deposit.html (line 14) | MISSING |
| `wallet.send_funds` | templates/wallet/send.html (line 12) | MISSING |
| `wallet.withdraw_funds` | templates/wallet/withdraw.html (line 12) | MISSING |
| `wallet.agent_payout_history` | templates/wallet/overview.html (line 14), templates/wallet/transactions.html (line 46) | MISSING |
| `wallet.agent_payout_request_page` | templates/wallet/overview.html (line 15) | MISSING |

## Currently Implemented (in routes.py)
- `wallet.home` -> redirects to `wallet.overview`
- `wallet.overview` -> renders wallet/overview.html

## Files Still Using Old Wallet Model (BROKEN)

### `app/fan/routes.py` - CRITICAL
- **Line 29-30**: `wallet = Wallet.query.filter_by(user_id=current_user.id).first()` - Uses undefined `Wallet`
- **Line 133**: `wallet = Wallet.query.filter_by(user_id=current_user.id).first()` - Uses undefined `Wallet`
- **Lines 138-140**: `wallet.transactions.order_by(...)` - Uses undefined relationship
- **Lines 174, 177, 178**: `from app.wallet import get_or_create_wallet` - Import doesn't exist
- **Lines 185, 188**: `wallet = get_or_create_wallet(current_user.id)` - Function doesn't exist

## Missing Services/Functions

### `app/wallet/__init__.py`
Needs to export:
- `get_or_create_wallet()` - Referenced by fan/routes.py but doesn't exist

### `app/wallet/services/`
Services exist but may need AccountModel integration:
- `wallet_service.py` - Has WalletService class
- `payment_gateway.py` - Payment provider integration
- `currency_service.py` - Currency conversion
- `fx_service.py` - Foreign exchange
- `compliance_engine.py` - Compliance checks

## Template Files Status

### `templates/wallet/` - EXISTS
- overview.html - References old `wallet` object properties
- deposit.html - References `wallet.deposit_form`
- send.html - References `wallet.send_funds`
- withdraw.html - References `wallet.withdraw_funds`
- transactions.html - References `wallet.transactions`
- dump.html - Unknown purpose
- original_file.html - Backup/reference file

### `templates/owner/wallet_config/` - EXISTS
- index.html - Owner wallet config dashboard
- providers.html - Payment providers list
- edit_provider.html - Edit provider config
- system.html - System configuration
- env_setup.html - Environment setup instructions

### `static/css/modules/wallet/` - EXISTS
- deposit.css - Styles for deposit page

## API Endpoints (Exist in app/wallet/api/)

### `wallet_api.py`
- REST API endpoints exist with proper security
- Uses `wallet_api_bp` blueprint (url_prefix='/api/wallet')
- References `wallet_api.wallet_home` in base.html - but route is actually in wallet_bp

### `admin_api.py`
- Admin wallet management endpoints

### `fx_api.py`
- Foreign exchange endpoints

### `webhooks.py`
- Payment provider webhook handlers

## Summary of Required Actions

### 1. Add Missing Routes to `app/wallet/routes.py`:
```python
# Required endpoints:
- wallet_dashboard  # Main dashboard view
- wallet_home       # Alternative home (for public_home.html)
- deposit_page      # GET deposit form
- deposit_form      # POST deposit handler
- send_page         # GET send form
- send_funds        # POST send handler
- withdraw_page     # GET withdraw form
- withdraw_funds    # POST withdraw handler
- wallet_transactions # View all transactions
- agent_payout_history # View agent payouts
- agent_payout_request_page # Request payout form
```

### 2. Fix `app/fan/routes.py`:
- Replace `Wallet.query` with `AccountModel.query`
- Update `get_or_create_wallet` imports to use new AccountModel
- Update wallet relationship references

### 3. Update `app/wallet/__init__.py`:
- Add `get_or_create_wallet` helper function for backward compatibility

### 4. Update Templates:
- `templates/wallet/overview.html` - Change `wallet.xxx` to use AccountModel properties
- `templates/wallet_dashboard.html` - Change `wallet.xxx` references

## Model Architecture

### New Architecture (AccountModel-based):
- `app/wallet/models/ledger.py` - Contains `AccountModel`, `LedgerEntryModel`
- Account balance is DERIVED from ledger entries, NOT stored
- Uses `WalletService.get_balance(account_id)` to calculate

### Old Architecture (Wallet model):
- Direct `Wallet` model with stored balance
- `wallet.balance_home`, `wallet.balance_local` properties
- Relationships like `wallet.transactions`

## Files Not Yet Created

### Role-Based Wallet Templates (if needed):
- `templates/wallet/admin/` - Admin wallet views
- `templates/wallet/agent/` - Agent wallet views
- `templates/wallet/merchant/` - Merchant wallet views

### Additional Static Assets:
- `static/js/wallet/` - JavaScript for wallet interactions
- More CSS modules for send/withdraw/transactions pages
