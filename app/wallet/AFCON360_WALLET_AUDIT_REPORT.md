# AFCON360 Wallet System — Audit Report & Remediation Directive
**Prepared for:** Obed (Project Owner)
**Prepared by:** Wallet Systems Consultant (chat session)
**Audience:** Implementing engineer/agent
**Scope:** `app/wallet/` — active package architecture (`app/wallet/models/`, `services/`, `repositories/`, `middleware/`)
**Status:** Pre-implementation review. No code has been changed. This document is the work order.

---

## 0. How to use this document

This is a directive, not a suggestion list. Work top to bottom by severity tier (P0 → P1 → P2). **Do not start P1 work until every P0 item has a passing test proving it's fixed.** Each finding includes: what's wrong, why it matters, the exact evidence, and what "done" looks like. Where I flag something as "needs verification," it means I have not seen the file in question — read it before touching anything nearby, and report back what you find before assuming my hypothesis is correct.

---

## 1. Executive Summary

The active wallet architecture (`app/wallet/models/ledger.py`, `transaction.py`, and the associated repositories/services) is a genuine double-entry ledger system with DB-enforced idempotency, deadlock-safe multi-account locking, and Decimal-precision money handling. This is a materially better foundation than most systems at this stage reach for. That is the good news.

The bad news: three P0 issues mean parts of the system are either **not verified to work** or **do not currently run at all**, and one systemic issue means the **compliance/regulatory layer will produce wrong results** in a live multi-currency deployment. None of this requires a rewrite — it requires focused, sequenced fixes.

---

## 2. Confirmed Architecture (for the agent's orientation)

- **Source of truth for money:** `ledger_entries` table (`app/wallet/models/ledger.py`). Balance is **never stored** — it is always `SUM(CREDIT) - SUM(DEBIT)` computed at query time via `LedgerRepository.get_balance()`.
- **Accounts:** `AccountModel` (`app/wallet/models/ledger.py`) — one account per owner (user or organisation) per currency, identified by UUID. This is the "Alipay model" referenced in code comments: UUID `account_id` is the primary identifier, not `user_id`.
- **Transactions:** `TransactionModel` (`app/wallet/models/transaction.py`) — immutable, with a DB-level `UNIQUE` constraint on `client_request_id` for idempotency.
- **Business logic:** `WalletService` (`app/wallet/services/wallet_service.py`) — `deposit()`, `withdraw()`, `transfer()`, each wrapped in a single `with self.db.begin():` block with no compensation logic.
- **There is a dead, stale duplicate of the whole module system:** a flat `app/wallet/models.py` file (confirmed via `backups/app__wallet__models.py_20260409011912.bak` to be an April 9 snapshot) sitting alongside the current `app/wallet/models/` package. See §4.3.

**Agent: before doing anything else, confirm this mental model is correct by running:**
```
python -c "from app.wallet.models import ledger, transaction; print('OK')"
python -c "import app.wallet.models as m; print(m.__file__)"
```
The second command tells you definitively whether Python is resolving `app.wallet.models` as the package or the flat file. Report the result before proceeding — if it resolves to the flat file, several of my findings below need to be re-evaluated because the system I audited would not be the one actually running.

---

## 3. P0 — Broken or unverified right now. Fix before anything else.

### P0-1: The concurrency safety-net test suite cannot execute

**File:** `tests/wallet/test_ledger_concurrency.py`

**Problem:** Every test calls the service with parameter names that no longer exist:
```python
service.deposit(user_id=funded_account.user_id, ...)
service.withdraw(user_id=funded_account.user_id, ...)
service.transfer(from_user_id=..., to_user_id=..., ...)
```
But the live `WalletService` (`app/wallet/services/wallet_service.py`) signatures are:
```python
def deposit(self, account_id: str, amount, currency, client_request_id, ...)
def withdraw(self, account_id: str, amount, currency, client_request_id, ...)
def transfer(self, from_account_id: str, to_account_id: str, amount, currency, client_request_id, ...)
```
Every single test in this file will raise `TypeError: got an unexpected keyword argument` before any thread runs any logic.

**Why it matters:** This file's stated purpose is to prove "no double spending under high concurrency." Right now, that claim is **unverified**. It has apparently never been run successfully against the current API surface. Nobody should be telling stakeholders, investors, or (eventually) regulators that concurrency safety is "tested" until this actually passes.

**Fix required:**
1. Rewrite every test call site to use `account_id` / `from_account_id` / `to_account_id` (UUIDs), matching `funded_account.id`, not `funded_account.user_id`.
2. Also check the `AccountRepository().get_or_create(...)` calls inside the test file — they're called with `(user_id, currency)` positional args; confirm this matches the real `AccountRepository.get_or_create` signature (file not reviewed — **needs verification**, see §5.1).
3. Run the full suite against a real Postgres test DB (not sqlite — row-level locking semantics for `SELECT FOR UPDATE` differ, and this suite specifically depends on Postgres locking behavior).
4. Do not consider this closed until `test_no_double_spend_100_parallel_withdrawals` and `test_no_double_send_parallel_transfers` pass green, with the exact success/failure counts asserted in the test (10/90 and 20/30 respectively).

**Definition of done:** `pytest tests/wallet/test_ledger_concurrency.py -v` passes, 0 failures, run at least 3 times in a row (concurrency bugs are flaky by nature — one green run is not proof).

---

### P0-2: `regulator_service.py` imports a model that does not exist

**File:** `app/wallet/services/regulator_service.py`, line ~18

**Problem:**
```python
from app.wallet.models.wallet import WalletTransaction
```
There is no `app/wallet/models/wallet.py` in the current package. `WalletTransaction` only exists in the dead flat `app/wallet/models.py` (see P0-3) — a class that has no relationship to the current `ledger_entries`/`transactions` architecture. This means `regulator_service.py` fails at import time, or at minimum operates on a model class disconnected from the real ledger.

**Why it matters:** This is the module that provides secure API access to **regulators and external auditors**. It is, by definition, the part of the system most likely to be scrutinized by exactly the kind of institutional actors referenced in this project's ambitions (IMF/World Bank-style oversight). It currently cannot run.

**Fix required:**
1. Determine what `RegulatorService` actually needs to query — almost certainly `TransactionModel` (`app/wallet/models/transaction.py`) and `LedgerEntryModel` (`app/wallet/models/ledger.py`), not a `WalletTransaction` class.
2. Rewrite every reference to `WalletTransaction` in this file to use the current ledger/transaction models, with an internal->external field mapping (this file already implies user-facing serialization — make sure UUIDs, not internal BigInt IDs, are exposed, consistent with the "Alipay model" convention seen in `wallet_service.py`, e.g. `# Internal only — NEVER returned` comments throughout).
3. Confirm `self._store_access_code(...)` (referenced but only "simplified — would use proper storage" per its own docstring) is not an in-memory dict. If it is, access codes vanish on process restart and won't work across multiple gunicorn/uwsgi workers. This needs real persistence (a dedicated model/table) before this is production-usable. **Needs verification** — read the rest of `regulator_service.py` past what was reviewed here.

**Definition of done:** `python -c "from app.wallet.services.regulator_service import RegulatorService"` succeeds. A test exists that generates an access code, restarts the "session" (simulating a new process), and confirms the code is still valid — proving persistence isn't in-memory-only.

---

### P0-3: Dead flat `models.py` shadowing the live `models/` package

**Files:** `app/wallet/models.py` (dead) vs. `app/wallet/models/` (live package)

**Problem:** Both exist in the same directory. Confirmed via `backups/app__wallet__models.py_20260409011912.bak` that the flat file is a stale April 9 snapshot predating the ledger-package split. Python's import resolution will pick one deterministically (packages generally shadow same-named modules), but **having both on disk is itself the bug** — it's exactly the kind of ambiguity that caused P0-2 (code still written against the old `WalletTransaction` class from the dead file).

**Fix required (do this first, before P0-1 and P0-2, since it may explain both):**
1. Run the import-resolution check from §2. Confirm which one Python actually loads.
2. `git log --follow app/wallet/models.py` to confirm the file has had no meaningful commits since the package split (i.e., it really is dead, not a second active thing).
3. `git rm app/wallet/models.py`. Do not just leave it "for reference" — move genuinely useful reference content (if any) into a `docs/` or `Documentation/` note instead, or squash it into `WALLET_SYSTEM_DOCUMENTATION1.md`/`WALLET_SYSTEM_DOCUMENTATION_AIDER.md` if there's history worth preserving.
4. Grep the entire codebase for imports of `app.wallet.models` where the intent was actually a class only present in the old file (`Wallet`, `WalletTransaction`, `WalletLimit`, `WalletAuditLog`, `WalletSettings`) — these are landmines. `regulator_service.py` (P0-2) is one confirmed hit. Search for others:
   ```
   grep -rn "from app.wallet.models import\|from app.wallet.models\.\(Wallet\|WalletTransaction\|WalletLimit\|WalletAuditLog\|WalletSettings\)" app/
   ```
5. For every hit, migrate to the equivalent in `app/wallet/models/ledger.py` / `transaction.py` / `config.py`, following the same pattern used in `wallet_repository.py` (which correctly imports from `app.wallet.models.ledger`).

**Definition of done:** `app/wallet/models.py` no longer exists on disk. Full test suite (`pytest tests/`) has zero `ImportError`/`ModuleNotFoundError` failures related to `app.wallet.models`.

---

### P0-4: Compliance/AML thresholds are currency-blind

**Files:** `app/wallet/services/regulatory_reporting.py`, `app/wallet/services/travel_rule_service.py`

**Problem:** `RegulatoryReportingService.AML_THRESHOLD = 10000` and `CTR_THRESHOLD = 10000` are compared directly against `tx.amount` with **no currency conversion**:
```python
structuring_txns = [tx for tx in txns if tx.amount >= cls.AML_THRESHOLD * 0.9 and tx.amount < cls.AML_THRESHOLD]
...
if tx.amount >= cls.AML_THRESHOLD:  # "large_transaction"
```
`TravelRuleService.check_travel_rule_required()` has the same flaw and **says so in its own comment**:
```python
amount_usd = amount  # Simplified - would convert based on currency
```
The default wallet currency in this system is UGX (per `Wallet.currency` default in the dead file, and the general Uganda context of this project). A transaction of UGX 10,000 (~USD 2.60) will be flagged as large/suspicious by this code, while genuinely large UGX amounts (millions of shillings) won't be evaluated against a sensible USD-equivalent threshold unless the raw number happens to cross 10,000.

**Why it matters:** This isn't a UX nitpick — Suspicious Transaction Reports (STR) and Currency Transaction Reports (CTR) are the actual legal deliverables in an AML/CTF compliance program. If the threshold logic is wrong, the reports are wrong, and "we generate STR/CTR reports" is not a true statement even though the code exists and runs. Given this project's stated ambition to operate at IMF/World Bank-adjacent standards, this is the single highest-value fix from a regulatory-credibility standpoint after the P0 import bugs.

**Fix required:**
1. Every threshold comparison in `regulatory_reporting.py` and `travel_rule_service.py` must convert `tx.amount` (in `tx.currency`) to a single reporting currency (USD, presumably) using the FX service **before** comparing to `AML_THRESHOLD`/`CTR_THRESHOLD`/`fiat_threshold_usd`/`crypto_threshold_usd`.
2. This depends on resolving P1-1 (which FX service is canonical) first — do not wire this against `CurrencyService`'s in-memory config-fallback rates and call it done; it needs the real, audited rate source once that's decided.
3. Add a test that creates a UGX 10,000 transaction and a UGX 38,000,000 transaction (~USD 10,000 at current mock rates) and asserts only the second is flagged.

**Definition of done:** No comparison of a raw `tx.amount` to a USD-denominated constant exists anywhere in the compliance services without a preceding FX conversion step. Test from step 3 passes.

---

## 4. P1 — Real architectural risk. Fix before this handles real money at any volume.

### P1-1: Two competing, disconnected FX implementations

**Files:** `app/wallet/services/currency_service.py` vs `app/wallet/services/fx_service.py`

- `CurrencyService` — used by `WalletService` (imported in `wallet_service.py`), in-memory cache, rates pulled from Flask config fallback.
- `FXService` — has real safety mechanics (`RateStaleError`, `RateDeviationError`, DB-cached `FXRateModel`), but **is not called anywhere in `WalletService.deposit/withdraw/transfer`**. There is currently no visible cross-currency transfer code path at all — every transfer implicitly assumes both accounts share `currency`.
- `FXService._fetch_from_api_safe()` is **entirely mock data** with `random.uniform(0.995, 1.005)` jitter standing in for real market movement — meaning its own "deviation safety halt" is presently testing itself against synthetic noise it generates, not real signal.

**Agent instructions:**
1. Decide (with Obed) which service is canonical. Given `FXService` has the better safety architecture, the likely correct move is: keep `FXService`'s safety mechanics, retire `CurrencyService`, and wire `WalletService` to call `FXService` for any deposit/withdraw/transfer where the transaction currency differs from the account's native currency.
2. Replace `_fetch_from_api_safe`'s mock table with a real provider integration (the file's own `TODO` — e.g., OpenExchangeRates, Fixer.io, or a licensed FX data provider appropriate for UGX/regional currencies) before this goes anywhere near production. Mock rates with random jitter must not ship.
3. Add an explicit cross-currency transfer path to `WalletService.transfer()` (or a clearly-named sibling method) if this is a required product feature — right now it's architecturally absent, not just unfinished.

### P1-2: Fail-open is the default posture on every safety control

**Files:** `app/wallet/services/nonce_protection_service.py` (`validate_nonce`), `app/wallet/services/travel_rule_service.py` (`check_travel_rule_required`)

Both explicitly default to **allowing** the transaction if the check itself throws an internal error ("Fail open - allow transaction if validation fails" / "proceed if check fails"). This may be a deliberate, defensible uptime-over-strictness choice for replay protection, but for AML/travel-rule gating specifically, this is the kind of default an examiner will flag — compliance controls are generally expected to fail *closed* (block + alert an operator) on internal error, not silently pass through.

**Agent instructions:** Do not silently "fix" this by flipping the default — it's a policy decision, not a pure bug. Raise it explicitly with Obed: which checks (if any) should fail open vs. closed, and document the decision in `WALLET_SYSTEM_DOCUMENTATION1.md` or equivalent. Implement whichever is decided, consistently, across both files.

### P1-3: Decimal values in compliance reports are not JSON-safe

**File:** `app/wallet/services/regulatory_reporting.py`

`STRReport`/`CTRReport` dataclasses type-hint `total_amount: float` but populate it via `sum()` over `Decimal` transaction amounts. `export_report_to_dict()` passes this straight through. Flask's default `jsonify` cannot serialize `Decimal` — if these reports are ever exposed through an API route without a custom JSON encoder registered, this throws at serialization time.

**Fix required:** Either (a) register a custom JSON encoder for `Decimal` app-wide (check `app/extensions.py` / app factory for where this belongs), or (b) explicitly cast to `str()` (preferred for money, to avoid float reintroduction — see the original float-precision thesis) at the dataclass boundary. Add a test that calls `export_report_to_dict()` and round-trips the result through `json.dumps()`.

### P1-4: Commission-service calls inside the outer atomic block — needs verification

**File referenced but not reviewed:** `app/wallet/services/commission_service.py`

`wallet_service.py`'s `deposit`, `withdraw`, and `transfer` all call `CommissionService.record_commission(...)` **inside** the `with self.db.begin():` block, wrapped in a bare `except Exception: log and continue`. **Agent: read `commission_service.py` before touching anything else here.** Specifically confirm whether `record_commission` calls `db.session.commit()` internally. If it does, that would prematurely close the outer atomic block and silently undermine the "everything or nothing" guarantee that `transfer()`'s docstring promises. If it doesn't commit internally (i.e., it only calls `db.session.add(...)`, matching the pattern in `LedgerRepository.post_entries`), this is fine as-is.

**Definition of done:** A written confirmation (comment or test) that `CommissionService` never commits independently of the caller's transaction boundary.

---

## 5. P2 — Cleanup and hardening. Cheap now, expensive later.

### P2-1: Reserved-word / naming landmines — repo-wide `metadata` column check

The dead flat `models.py` declared `metadata = Column(JSON, ...)` on two models — `metadata` collides with SQLAlchemy's own reserved `Base.metadata` attribute and would raise `InvalidRequestError` if ever instantiated under standard Declarative usage. The live package correctly avoids this (`ledger.py` uses `meta`, `transaction.py` uses `tx_metadata`, `config.py` uses `config_json`). **Agent: run this repo-wide, not just in wallet, since this pattern likely recurs in other modules built by the same agents/timeframe:**
```
grep -rn "^\s*metadata\s*=\s*Column" app/
```
Rename every hit to a non-reserved name (`meta`, `extra_data`, `_metadata` with a property, etc.) following the convention already established in the live wallet models.

### P2-2: `config.py` naming collision risk

`app/wallet/models/config.py` defines `PaymentProviderConfig` and `WalletSystemConfig`. Confirm there isn't a second, differently-scoped `config.py` elsewhere in `app/wallet/` (e.g. under `middleware/` or `api/`) that could cause the same "flat file vs. package" ambiguity seen in P0-3, just with a different filename. Check:
```
find app/wallet -name "config.py" -o -name "*config*.py"
```
Cross-reference against the tree's `wallet_config.py` (under `app/admin/owner/`) — that one is a different module and almost certainly fine, but confirm nothing imports the wrong one.

### P2-3: Fee precision ceiling

`WalletSystemConfig` fee percentages use `Numeric(5, 2)` (e.g., `1.50`). This supports whole-percent-and-cents fees but would silently truncate a tiered fee schedule needing finer granularity (e.g., `0.125%`). Not urgent — just confirm this matches actual product requirements before it's load-bearing.

---

## 6. Additional areas the agent must independently verify (not yet reviewed in this audit)

I have not seen these files. Do not assume they're clean — read them with the same scrutiny applied above, specifically checking for: (a) references to the dead flat `models.py` classes, (b) `float` used for money instead of `Decimal`/`Numeric`, (c) currency-blind threshold comparisons, (d) transaction-boundary violations (nested commits inside an outer `with db.begin():`).

- `app/wallet/repositories/account_repository.py`, `transaction_repository.py` — the two repositories referenced constantly but not supplied. Confirm `get_or_create`, `get_by_id(for_update=...)`, `update_volume` signatures match every call site across `wallet_service.py` and the (currently broken) test file.
- `app/wallet/services/commission_service.py` — see P1-4.
- `app/wallet/routes.py`, `routes_pin.py`, `api/wallet_api.py` — confirm the HTTP layer passes `account_id` (UUID), not `user_id`, matching the current service signatures — this is the same class of drift that broke the test suite (P0-1); the routes may have the identical bug, silently, in production request handling.
- `app/wallet/models/fx.py`, `travel_rule.py`, `nonce_protection.py`, `audit.py` — the model definitions backing `FXService`, `TravelRuleService`, `NonceProtectionService`, and the idempotency middleware, respectively. Confirm none of them import from or reference the dead flat `models.py`.
- `app/wallet/services/payment_gateway.py`, `webhook_service.py`, `api/webhooks.py` — webhook reliability (dead-letter handling) is referenced (`tests/test_dead_letter_alert.py` exists in the tree) but wasn't part of this review. This is a full axis (see the "eight-axis framework" below) that needs its own pass.
- `transaction.py.before-fix` in the tree listing — a stray `.before-fix` file sitting next to the live `transaction.py`. Same category of risk as P0-3: confirm it's genuinely inert and either delete it or move it out of the package directory entirely.

---

## 7. Recommended sequencing

1. **P0-3** first (delete dead `models.py`) — this may auto-resolve or reveal the true scope of P0-2.
2. **P0-2** (fix `regulator_service.py` imports).
3. **P0-1** (fix and green-run the concurrency test suite) — do this before any further feature work, since it's your actual proof of correctness for the riskiest part of the system.
4. **P0-4** (currency-aware compliance thresholds) — blocks on deciding P1-1 (which FX service is canonical), so start that decision in parallel.
5. **P1-1 → P1-4** in any order, but don't consider the system "production-ready" until all are closed.
6. **P2s** whenever convenient — cheap, no dependencies.
7. Independently review every item in §6 with the same rigor before declaring the wallet module audit-complete.

---

## 8. What "done" looks like for this whole engagement

- `pytest tests/` passes with zero import errors anywhere under `app/wallet/`.
- The concurrency suite passes 3 consecutive green runs against real Postgres.
- A UGX 10,000 transaction and a UGX ~38,000,000 transaction produce correct, differentiated STR/CTR classification.
- `app/wallet/models.py` (flat file) no longer exists in the repository.
- One FX service is canonical, is wired into the actual money-movement path, and pulls from a real (non-mock) rate source.
- The fail-open/fail-closed policy for compliance checks is a documented decision, not an unexamined default.
