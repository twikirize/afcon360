# Wallet / Financial OS Audit — DeepSeek comparison

Date: 2026-05-01

This report compares the product checklist provided ("DeepSeek" feature matrix) against the current codebase in `app/wallet` and related modules. For each feature I indicate: Status (Built / Partial / Missing / Post-MVP), Evidence (file paths & notes), and recommended next steps.

Summary checklist (high-priority MVP gaps first)

- [x] Double-entry ledger — Built
- [x] Immutable audit trail — Built (comprehensive audit)
- [x] Idempotency protection — Built (middleware)
- [x] Multi-currency & FX — Built (with mock providers) / Partial UX
- [x] Payment providers (Flutterwave, Paystack) — Built
- [x] Webhook handlers (Flutterwave, Paystack, MTN, Airtel) — Built
- [ ] Transaction PIN / transfer confirmation — Missing (MVP gap)
- [ ] Webhook retry queue / dead-letter queue — Missing (MVP gap)
- [ ] Transaction reconciliation job (scheduled, provider matching) — Partial (admin endpoint exists)
- [ ] Gateway failover (auto-retry alternate provider) — Missing
- [ ] Notifications (integrated SMS/email for wallet events) — Partial (SMS/email services exist; wallet doesn't consistently call them)
- [ ] KYC submission UI — Built (routes & templates present) but verify end-to-end verification flow

Detailed feature-by-feature audit

CORE WALLET ENGINE

- Double-entry ledger — Built
  - Evidence: `app/wallet/models/ledger.py`
  - Notes: Immutable ledger entries (`LedgerEntryModel`), Account model with balance derived from ledger entries (commented rules). This is the canonical source of truth.

- Immutable audit trail, balances derived not stored — Built
  - Evidence: `app/audit/comprehensive_audit.py` (FinancialAuditLog & AuditService), many places call `AuditService.financial()` in payments code (e.g. `app/wallet/payments/flutterwave.py`, `app/wallet/payments/paystack.py`).
  - Notes: Audit tables are comprehensive and designed to be append-only.

- Multi-currency accounts — Built
  - Evidence: `app/wallet/services/fx_service.py` (FXService), `AccountModel.currency` in ledger models, FXRate/FXTransaction models (exists under `app/wallet/models/fx.py`).
  - Notes: FXService currently uses mock rates and caches rates in DB; conversion, spread and FX transaction records are implemented.

- Idempotency protection — Built
  - Evidence: `app/wallet/middleware/idempotency.py` (middleware checks X-Idempotency-Key, has DB fallback caching and enforcement).

PAYMENT GATEWAYS

- Flutterwave integration — Built
  - Evidence: `app/wallet/payments/flutterwave.py`, `app/wallet/services/payment_gateway.py` (FlutterwaveGateway)

- Paystack integration — Built
  - Evidence: `app/wallet/payments/paystack.py`, `app/wallet/services/payment_gateway.py` (PaystackGateway)

- MTN / Airtel mobile money — Partial
  - Evidence: Webhook handlers exist (`app/wallet/api/webhooks.py`), PaymentProvider enum and orchestrator include `MTN_MOMO` and `AIRTEL_MONEY` entries. Mobile money deposit/withdraw helper functions exist (`payment_gateway.deposit_with_mobile_money`, etc.).
  - Notes: Full direct integration flows (e.g., MTN two-way push/collection APIs) appear to be partially implemented or mocked.

- Gateway failover — Missing
  - Evidence: `app/wallet/services/payment_gateway.py` orchestrates gateways but there is no failover logic that retries with an alternate provider if the primary fails.
  - Recommendation: Add a failover orchestrator that accepts a provider preference list and retries on configurable errors, plus circuit-breaker monitoring.

DEPOSITS & WITHDRAWALS

- Card / Paystack / Flutterwave deposits — Built
  - Evidence: `payment_gateway.deposit_with_card`, `FlutterwaveGateway.initiate_payment`, `PaystackGateway.initiate_payment`.

- Bank transfer (virtual account) — Built (integration points exist)
  - Evidence: paystack/Flutterwave transfer endpoints and bank transfer support in gateway code.

- Mobile money deposit/withdrawal — Partial
  - Evidence: webhooks for MTN/Airtel exist; mobile-money deposit functions exist but direct provider flows are partially mocked.

- Withdrawal limits, daily caps, approval flow — Partial / Missing
  - Evidence: `AccountModel` stores daily/monthly volumes and reset timestamps; however manual approval workflow for withdrawals above threshold is not implemented in `wallet_service` flows.

PEER-TO-PEER TRANSFERS

- User-to-user transfer — Built
  - Evidence: `app/wallet/services_with_audit.py` contains example P2P transfer processing; core wallet_service supports transfers (see `wallet_service.py`).

- Transfer fee engine — Partial
  - Evidence: fee calculations appear in FXService and commission service. Transfer fee engine per-transfer/tier config is partially implemented (see `app/wallet/services/commission_service.py`).

- Transfer confirmation / PIN — Missing
  - Evidence: No references to a transaction PIN, TOTP, or required confirmation step before funds leave. Search for "pin", "totp", "transaction_pin" returned no wallet-related implementation.
  - Impact (MVP): High — users need a confirm step (PIN or approval) to trust transfers.
  - Recommendation: Implement a server-side PIN check and a UI flow (API + templates) that requires the PIN for outgoing transfers. Files to touch: `app/wallet/routes.py` (transfer endpoints), `app/wallet/services/wallet_service.py` (enforce pin check), add a `transaction_pin` column to `User` model or separate PIN table + secure hashing and lockout.

- Transfer reversal — Missing
  - Evidence: TODOs in webhooks mention reversals; `AuditService` has `REVERSAL` type but no owner dashboard reversal workflow implemented.
  - Recommendation: Provide reversible states with admin actions, and record reversal entries in ledger & audit.

FOREIGN EXCHANGE (FX)

- Real-time FX rates (150+ currencies) — Partial
  - Evidence: `app/wallet/services/fx_service.py` implements rate fetching, caching and historical records; uses mock providers and a `SUPPORTED_CURRENCIES` list. Rate providers configured but not integrated with real APIs.
  - Recommendation: Integrate a production rate provider (e.g., XE, OpenExchangeRates) and expand supported currency list. Add transparent UX for rate lock / quote expiry.

- FX conversion between wallets — Built
  - Evidence: `FXService.convert_amount`, `create_fx_transaction`.

- FX spread configuration — Partial
  - Evidence: `FXService.default_spread` exists and is persisted on FXRateModel; owner UI to configure spread may be partly missing.

- Rate lock / quote expiry — Missing
  - Evidence: No explicit 30s quote-lock implementation; `FXService.get_rate` caches rates but no reserved quote mechanism.

COMPLIANCE & KYC

- AML transaction monitoring — Built (engine scaffolding)
  - Evidence: `app/wallet/services/fraud_detection_service.py`, `app/audit/comprehensive_audit.py` stores risk flags and aml_flagged columns.

- Sanctions screening — Built (scaffolding)
  - Evidence: compliance modules referenced; `app/identity/models/kyb.py` and related KYB models exist.

- KYC tier system — Built
  - Evidence: `app/auth/kyc_routes.py`, templates in `templates/kyc/*`, `app/identity/models/kyb.py`, `app/auth/kyc_compliance.py` (tier calculations).
  - Notes: UI templates are present (`templates/kyc/*`) and routes register conditionally in `app/__init__.py`.

- KYC submission UI — Built (exists) / verify end-to-end
  - Evidence: `app/auth/kyc_routes.py` (`overview`, `upgrade`, `submit_upgrade`) and templates in `templates/kyc/` and `templates_backup_20260429_001434/kyc/`.
  - Notes: The submit route currently logs the submission and flashes a message; the integration with document store / verification provider may be manual/mocked. Marked as Partial if you require full automated verification pipeline.

AGENT NETWORK

- Agent account type, commission calculation, payout — Built
  - Evidence: `app/wallet/services/commission_service.py`, `app/wallet/services/commission_service.py` records commissions and `PayoutService` exists under `app/wallet/services`.*

- Agent transaction dashboard / cash-in / cash-out — Partial / Missing
  - Evidence: Agent dashboards and onboarding code exist but agent cash-in/cash-out physical flow and geo-mapping are not fully implemented.

OWNER / ADMIN DASHBOARD

- Payment provider config, system config — Built
  - Evidence: Owner/admin endpoints and config management exist (see `app/__init__.py` and admin blueprints).

- Transaction oversight — Partial
  - Evidence: Admin reconciliation endpoint: `app/wallet/api/admin_api.py` (auditor_reconciliation) provides balanced/imbalance check. Search & filter tools for transactions exist partially in admin views but not comprehensive real-time revenue dashboard.

- Fraud alert inbox, bulk export — Missing
  - Evidence: Audit tables exist, but a consolidated inbox UI and bulk export endpoints for admins are not present.

WEBHOOKS & RELIABILITY

- Provider webhook handlers — Built
  - Evidence: `app/wallet/api/webhooks.py` contains handlers for Flutterwave, Paystack, MTN Momo and Airtel Money; signature verification implemented.

- Webhook signature verification — Built
  - Evidence: `verify_flutterwave_signature`, `verify_paystack_signature` in `webhooks.py`, provider gateway `handle_webhook` also validates.

- Webhook retry queue / dead-letter queue — Missing
  - Evidence: No queueing or retry mechanism found for failed webhook processing. When webhook processing fails, code typically logs and returns 500. No dead-letter storage or reprocessing service.
  - Impact: High — without retries, some deposits may be missed if webhook delivery temporarily fails.
  - Recommendation: Implement a durable queue (Redis/DB or Celery) to enqueue webhook events for async processing with retry/backoff and a dead-letter table for manual inspection. Files to add/update: `app/wallet/api/webhooks.py` (enqueue instead of direct processing), new worker `app/tasks/webhook_processor.py`, DB table `webhook_events` for DLQ.

- Transaction reconciliation (daily job) — Partial
  - Evidence: `app/wallet/api/admin_api.py` has `auditor_reconciliation()` to check ledger debits vs credits. However, a scheduled nightly job that matches provider records to ledger entries and produces actionable reports is not implemented.
  - Recommendation: Add a scheduled reconciliation job (Celery beat or cron) that pulls provider reports (via API or stored webhook logs), matches by provider reference and amount, and writes reconciliation results to an audit table. Provide admin UI for exceptions.

USER-FACING PRODUCT

- User dashboard, deposit/withdraw UI — Built (basic templates)
  - Evidence: templates like `templates/receiver_wallet.html`, owner dashboard templates, and wallet routes exist.

- Transaction history UI — Partial
  - Evidence: `templates/receiver_wallet.html` and other fragments show transaction lists but lack pagination, search, and filtering in some places. API endpoints exist for transaction queries but may be partial.

- PIN / 2FA setup — Missing
  - Evidence: No transaction PIN or TOTP setup found. OTP and SMS/email exist for verification flows, but secure PIN storage and enforcement for transfers are absent.

- Notifications (in-app/SMS/email) — Partial
  - Evidence: `app/services/sms_service.py` and `app/auth/email.py` exist and work; a transport `NotificationService` exists (`app/transport/services/notification_service.py`) but wallet events do not uniformly call a centralized notification service. Many payment code paths call `AuditService` but not always notification triggers.
  - Recommendation: Add `app/notifications` service (if not present) or re-use transport notification service; call notifications in `wallet_service.deposit()`, `wallet_service.transfer()` and webhook success handlers. Configure email/SMS providers in config and send key user notifications (deposit received, transfer sent/received, withdrawal initiated/completed, KYC status change).

POST-MVP

- Virtual cards, bill payments, QR code payments, savings pockets, mobile apps, lending — Post-MVP (not implemented, expected)

Priority recommended roadmap (short-term MVP fixes)

1) Critical (blocker for safe launch)
   - Implement Transaction PIN / Transfer confirmation
     - Where: `app/wallet/services/wallet_service.py`, `app/wallet/routes.py`, `app/identity/models/user.py` (pin hash field or separate model)
     - Approach: Add secure, salted hash (use PBKDF2/argon2), lockout after N failed attempts, API endpoints for set/change PIN, and require PIN on outgoing transfers.

   - Webhook retry queue + Dead-letter queue
     - Where: `app/wallet/api/webhooks.py`, new `app/tasks/webhook_processor.py`, DB table `webhook_events` and/or Redis list/Celery
     - Approach: On webhook receive, enqueue event for background worker; worker processes with idempotency checks and retries; failures go to DLQ with admin UI.

   - Transaction reconciliation job
     - Where: `app/wallet/tasks/reconciliation.py`, scheduled job runner (Celery beat or cron)
     - Approach: Daily job queries ledger and provider reports, flags mismatches, writes reconciliation report to `financial_reconciliation` table and notifies auditors.

2) High priority (improve UX/ops)
   - Gateway failover / circuit breaker
     - Add orchestrator logic to retry on provider errors with alternate provider list; configurable per-country provider preference.

   - Notifications wired for wallet events
     - Ensure wallet events call SMS/email/push providers. Provide templates/messages and feature flags to enable providers per environment.

3) Medium priority
   - Transfer reversal admin flows
   - Rate lock / quote expiry UX (30s locked quote)
   - Complete mobile-money direct integrations for MTN/Airtel

Evidence index (quick links)

- Ledger: app/wallet/models/ledger.py
- Audit: app/audit/comprehensive_audit.py
- Idempotency middleware: app/wallet/middleware/idempotency.py
- Payment gateway orchestrator: app/wallet/services/payment_gateway.py
- Flutterwave: app/wallet/payments/flutterwave.py
- Paystack: app/wallet/payments/paystack.py
- Webhooks: app/wallet/api/webhooks.py
- FX: app/wallet/services/fx_service.py
- SMS: app/services/sms_service.py
- Email OTP: app/auth/email.py
- KYC routes: app/auth/kyc_routes.py and templates/kyc/
- Notification (transport): app/transport/services/notification_service.py (can be reused)

Appendix: Suggested quick implementation plan for top 3 critical items

1) Transaction PIN (server + UI)
   - DB: add `transaction_pin_hash` and `pin_salt` to the `users` table (migration)
   - API: endpoints POST `/wallet/pin/set`, POST `/wallet/transfer` requires `pin` param
   - Service: in `wallet_service.transfer()` verify PIN using secure hash compare; increment failed attempt counter and lock after threshold
   - UI: modal for inputting PIN before confirm; fallback to OTP for PIN-reset

2) Webhook retry queue + DLQ
   - On webhook receipt, validate signature, then enqueue raw payload into `webhook_events` table with status=queued; return 202
   - Background worker consumes events, performs verify_payment/verify_payout, updates ledger and audit; on repeated failures mark status=failed and move to `webhook_dlq` or keep with retry_count
   - Add admin UI: `/admin/webhooks/failed` to inspect and reprocess

3) Reconciliation job
   - Create `reconciliation_runs` table to store run metadata and `reconciliation_exceptions` for unmatched items
   - Implement worker that: 1) fetches ledger transactions for period, 2) fetches provider API / APIAuditLog entries, 3) matches by `external_reference` and `amount`, 4) writes exceptions
   - Add alerting to owners on exception counts > threshold

If you want, I can: (pick one)

- implement the Transaction PIN API + DB migration and wire it into `wallet_service.transfer()` (I will create code + tests)
- implement a webhook enqueue + background worker skeleton and DLQ table (I will add files & migration)
- produce a prioritized JIRA-style task list and small code patches for each change above

Tell me which of the high-priority items you want implemented first and I will start making changes in the repository.

---
Report generated by codebase scan (files referenced come from the workspace). If you want a trimmed CSV or a formatted checklist for project management, tell me the desired format.

