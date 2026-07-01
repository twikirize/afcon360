# AFCON360 — Wallet System Rules

## ⚠️ HIGH RISK MODULE — Treat all wallet changes with maximum caution

## Architecture
- Double-entry ledger — every debit has a matching credit
- `app/wallet/models/` — multiple model files, DO NOT modify without explicit instruction
- `app/wallet/services/` — business logic layer
- `app/wallet/repositories/` — data access layer
- `app/wallet/payments/` — gateway integrations (Flutterwave, Paystack, MTN, Airtel)
- `app/wallet/middleware/` — wallet-specific middleware
- `app/wallet/api/` — wallet API endpoints
- `app/wallet/routes_pin.py` — PIN lockout logic, do not touch unless asked

## Hard Rules
- NEVER modify `app/wallet/models/` without explicit user approval
- All wallet transactions require idempotency keys — use `app.utils.idempotency`
- Always use `db.session.rollback()` in wallet route error handlers
- AML service (`app/compliance/aml_service.py`) changes require compliance review
- Webhook processing is async via Celery — changes to `app/tasks/webhook_processor.py` need extra care

## Payment Gateways
- Flutterwave, Paystack, Mobile Money (MTN/Airtel Uganda) integrations
- All gateway credentials live in `.env` — never log or expose them
- FX rates service handles multi-currency conversion (`templates/wallet/fx_rates.html`)

## Compliance Gates
- Transactions > UGX 20M trigger FIA Uganda reporting
- KYC level gates wallet transaction limits
- AML checks via `app/compliance/aml_service.py`
- Reconciliation job: `app/tasks/reconcile.py`

## Documentation
- `app/wallet/WALLET_SYSTEM_DOCUMENTATION1.md` — primary wallet docs
- `Readme's/WALLET_SYSTEM_ANALYSIS.md` — system analysis
