# AFCON360 Escrow Capability — Agent Implementation Brief

## How to use this document

You are implementing escrow **capabilities**, not a new system. AFCON360 already
has ~80% of the primitives this needs, living in the `wallet` module. Your job
has three phases, in this order, and you may not skip Phase 0:

1. **AUDIT** — inventory what already exists against the checklist in this doc.
2. **BUILD** — patch/extend only what's missing, following the architecture
   rules below exactly (they are not suggestions).
3. **REPORT** — produce `ESCROW_BUILD_REPORT.md` at the project root using the
   exact template in Section 10. This is a required deliverable, not optional
   documentation. It must contain file paths and line numbers, not summaries.

Do not create a parallel system. Do not invent new core financial tables.
Do not touch `AccountModel.virtual_balance`/`real_balance` style stored
balances — this codebase's ledger is derived-at-query-time by design
(see `app/wallet/models/ledger.py` docstring: "NEVER update a balance column
directly"). If you find yourself about to store a balance, stop and re-read
Section 2.

---

## 1. Non-negotiable architecture principles

**P1 — Escrow is a workflow layer, not a new ledger.**
An escrow account is `AccountModel(account_type=AccountType.ESCROW,
service_type=<service>, platform_account=True)`. A hold/release/refund is a
`TransactionModel` row plus balanced `LedgerEntryModel` debit/credit rows. This
already exists as a pattern — extend it, don't replace it.

**P2 — Escrow must be fully deactivatable without touching the wallet.**
AFCON360 is a payment *facilitator*, not a fund custodian in the legal/product
sense you've settled on: money moves through the platform, it isn't held on
behalf of payer or payee beyond the minimum needed to bridge payment-to-service
completion. Concretely:
- Every module that calls into escrow (accommodation, transport, events,
  tourism, tournament) must check a runtime flag before routing through
  escrow at all. If the flag is off — globally or for that specific
  service — the module falls back to **direct wallet transfer** (existing
  `wallet_service.py` deposit/withdraw, no hold, no delay).
- This means the escrow adapter is called from each module, but the module's
  existing payment code must **not be rewritten** — only wrapped with a
  conditional. Find every existing call site first (Phase 0), then wrap.
- `app/wallet/middleware/kill_switch.py` already exists for exactly this
  pattern in the wallet module — read it before building a new one.
  Extend it or mirror its pattern for an `ESCROW_ENABLED` /
  per-service-type kill switch rather than inventing new middleware.

**P3 — Settings are data, not code.**
Every fee percentage, dispute window, release delay, dual-auth threshold,
and enabled/disabled state must be editable from an admin settings page and
take effect immediately, with zero deploy. Read `app/wallet/models/config.py`
and `app/admin/owner/wallet_config.py` first — there is very likely already a
settings pattern in this codebase (key/value or typed config rows) that
escrow settings should extend, not duplicate. If no such extensible pattern
exists, build one generic enough that the *next* payment feature doesn't need
its own settings table either.

**P4 — No stored balance duplication.**
`daily_volume`/`monthly_volume` on `AccountModel` already exist as
incrementally-updated counters — reuse them for escrow limit enforcement
rather than adding new counters. Do not add `escrow_balance` anywhere.

**P5 — Idempotency and audit trail are inherited, not reinvented.**
`TransactionModel.client_request_id` already has a DB-enforced unique
constraint. Every escrow-originated transaction must set this. Do not build a
separate idempotency mechanism for escrow — `app/wallet/middleware/idempotency.py`
already exists; confirm it applies to escrow call sites too.

**P6 — Verify every edit actually landed.**
This codebase has a documented history of silent Aider write failures
(`app/transport/models.py`, `app/events/assignment.py` in a prior session).
After every file edit in this task, run `grep` or `findstr` against the
target string to confirm the change is actually on disk before moving on.
Do not trust the tool's own success message.

---

## 2. Phase 0 — Mandatory Audit (do this before writing any code)

Run these against the real repo and record results verbatim in the report:

```bash
# 1. Confirm current state of the two known bugs
grep -n "PENDING\|COMPLETED\|FAILED\|CANCELLED" app/wallet/models/transaction.py
grep -n "class TransactionStatus" -A6 app/wallet/models/transaction.py
grep -n "unique=True" app/wallet/models/ledger.py

# 2. Inventory existing config/settings pattern
cat app/wallet/models/config.py
cat app/admin/owner/wallet_config.py
grep -rn "class.*Config" app/wallet/

# 3. Inventory existing kill-switch / activation pattern
cat app/wallet/middleware/kill_switch.py
cat app/wallet/middleware/wallet_activation.py
cat app/wallet/middleware/wallet_check.py

# 4. Inventory existing idempotency pattern
cat app/wallet/middleware/idempotency.py

# 5. Find every place a module currently moves money directly
#    (these are the call sites that need the escrow-or-direct branch)
grep -rn "wallet_service\." app/accommodation/ app/events/ app/*/services/ 2>/dev/null
grep -rn "deposit_to_escrow\|withdraw_from_escrow\|hold_payment\|release_payment" app/ 2>/dev/null

# 6. Inventory existing admin route/template patterns to mirror, not duplicate
ls app/admin/owner/route_modules/
ls app/templates/wallet/admin/
cat app/admin/owner/route_modules/wallet_admin.py

# 7. Inventory existing reconciliation job wiring
grep -n "reconcil" app/celery_app.py app/*/tasks.py 2>/dev/null

# 8. Inventory webhook pattern to reuse for escrow.* events
cat app/wallet/models/webhook_event.py
cat app/wallet/services/webhook_service.py
```

Record, per item above: **exists / partially exists / missing**, with file
path + line number for anything that exists. This becomes Section A of your
final report. Do not proceed to Phase 1 until this is done — if the config
or kill-switch patterns turn out not to exist, that changes what Phase 3/4
need to build, and building blind here is exactly the failure mode from the
prior third-party audit that missed ~30 FK issues by not checking ground
truth first.

---

## 3. Phase 1 — Prerequisite fixes (blocking)

1. **Status/constraint mismatch** in `app/wallet/models/transaction.py`:
   `TransactionStatus` enum values are lowercase (`'pending'`), the
   `CheckConstraint` whitelist is uppercase (`'PENDING'`). Pick one casing
   and make both match. Write a migration if any rows already exist with
   the mismatched casing.

2. **`accounts.user_id` unique constraint** in `app/wallet/models/ledger.py`:
   currently `unique=True` at the column level AND a composite unique index
   on `(user_id, currency)`. The column-level constraint makes the composite
   index unreachable and caps the system at one account per user_id total.
   Drop the column-level `unique=True`; keep the composite index.

3. **Add `service_type` to `accounts`**: nullable `String(30)`, plus a
   partial unique index — one active escrow account per
   `(service_type, currency)` where `account_type = 'escrow'`. Write this as
   a proper Alembic migration, not a handwritten SQL patch, consistent with how
   migrations are already tracked in this repo (`alembic/versions/`, see
   `5582ce532c6f_add_agents_enabled_to_wallet_config.py` as a template for
   style).

Run existing tests after these three changes before proceeding —
particularly `tests/wallet/test_ledger_concurrency.py` and
`tests/test_payment_flow.py` — since both touch the models you're changing.

---

## 4. Phase 2 — Settings-driven configuration

Build (or extend, per Phase 0 findings) a settings model with these fields,
editable from the admin UI with no redeploy:

| Setting | Scope | Type |
|---|---|---|
| `escrow_globally_enabled` | platform-wide | bool |
| `escrow_enabled` | per service_type | bool |
| `fee_pct` | per service_type | decimal |
| `release_delay_hours` | per service_type | int |
| `dispute_window_days` | per service_type | int |
| `dual_auth_threshold` | per service_type | decimal |
| `auto_reconcile_tolerance_pct` | platform-wide | decimal, default 0.01 |
| `daily_volume_limit` / `monthly_volume_limit` | per escrow account | decimal (already exists on `AccountModel`, just needs to be admin-editable) |

This is the mechanism that satisfies "no need to go back to code to change
anything." Every one of Section 1's `SERVICE_RULES`-style constants (from
any earlier draft code you find in the repo, including the one attached to
this conversation if it's already been dropped in) must be re-sourced from
this settings table at call time, not hardcoded. If you find a hardcoded
`SERVICE_RULES` dict anywhere, replace its usages with settings lookups and
delete it — leaving both would create the exact two-registries-drift problem
already found and fixed once in this codebase's ID-architecture work
(`BaseModel.NON_FK_STRING_IDS` vs `IDGuard.STRING_FK_EXCEPTIONS`). One source
of truth per fact, always.

---

## 5. Phase 3 — Backend service layer

Create `app/wallet/services/escrow_service.py` (or extend if Phase 0 finds a
partial one already dropped into the repo) implementing:

```python
class EscrowWorkflowService:
    # Account resolution
    get_or_create_escrow_account(service_type, currency)
    list_escrow_accounts()                      # for admin dashboard

    # Core money movement (all: TransactionModel + balanced LedgerEntryModel rows)
    hold_payment(service_type, user_id, amount, currency, client_request_id, reference, metadata)
    release_payment(service_type, provider_user_id, amount, currency, client_request_id, reference, metadata)
    refund_payment(service_type, user_id, amount, currency, client_request_id, reference, reason)

    # Balance — always derived, never stored
    get_balance(account_id) -> Decimal
    get_escrow_balance(service_type, currency) -> Decimal

    # Admin controls
    freeze_escrow_account(service_type, currency, reason, frozen_by)   # reuse AccountModel.freeze()
    unfreeze_escrow_account(service_type, currency)                    # reuse AccountModel.unfreeze()
    manual_deposit(account_id, amount, from_user_id, reason, performed_by)
    manual_withdraw(account_id, amount, to_user_id, reason, performed_by)  # gate on dual_auth_threshold

    # Dispute / release timing (stored in tx_metadata JSONB, no new columns)
    get_pending_releases(service_type)          # release_delay_hours not yet elapsed
    get_disputable_transactions(service_type)   # within dispute_window_days
    process_scheduled_releases()                # called by celery beat

    # Reconciliation (reuses ReconciliationRun / ReconciliationIssue as-is)
    reconcile_escrow_account(service_type, currency, real_bank_balance, run) -> Optional[ReconciliationIssue]
    reconcile_all_escrow_accounts() -> ReconciliationRun
    classify_discrepancy(virtual, real) -> str   # type_a/b/c/d per doc's original scheme

    # The kill-switch check every module integration point uses
    is_escrow_active(service_type) -> bool       # reads settings from Phase 2, not code
```

Balanced double-entry requirement for `release_payment`: debit(amount) must
equal credit(net) + credit(fee). Do not let this drift — add an assertion,
not just a comment, since a silent imbalance here is exactly the kind of bug
that produces a Type C "unexplained" discrepancy down the line.

---

## 6. Phase 4 — Per-module integration adapters (non-destructive)

For each of `accommodation`, `transport`, `events`, `tourism`, `tournament`:

1. Locate the **existing** payment call site from Phase 0's grep results
   (e.g. `app/accommodation/services/booking_service.py`,
   `app/accommodation/services/wallet_service.py`).
2. Do not rewrite that function. Wrap it:

```python
def capture_booking_payment(booking):
    if EscrowWorkflowService.is_escrow_active('accommodation'):
        return EscrowWorkflowService.hold_payment(
            service_type='accommodation',
            user_id=booking.guest_user_id,
            amount=booking.total_amount,
            currency=booking.currency,
            client_request_id=f"booking:{booking.id}",
            reference=booking.booking_reference,
            metadata={'property_id': booking.property_id, 'host_id': booking.host_user_id},
        )
    # Fallback: existing direct wallet flow, untouched
    return existing_wallet_service.transfer(...)
```

3. Same pattern for release (on service completion) and refund (on
   cancellation) — three call sites per module, six modules, eighteen wrap
   points total. List every one of them explicitly in the report with
   before/after file+line references.

This is what makes escrow deactivatable without killing the wallet: turning
`escrow_enabled` off for a service_type (or globally) makes every one of
these eighteen call sites fall through to the pre-existing direct-transfer
path with zero code change.

---

## 7. Phase 5 — Admin backend routes

Mirror the existing structure — do not create a sibling `escrow/` app
directory. Extend:

- `app/admin/owner/route_modules/wallet_admin.py` — add escrow account
  CRUD, freeze/unfreeze, manual deposit/withdraw, settings endpoints,
  following the same auth decorators (`app/admin/owner/decorators.py`)
  already used for wallet admin routes.
- `app/wallet/api/admin_api.py` — add JSON endpoints for the same
  operations if the wallet admin API is used by any JS-driven dashboard
  widgets (check existing `wallet_admin_dashboard.html` for whether it's
  server-rendered or fetch-driven before deciding).

Routes needed (map onto whatever URL convention `wallet_admin.py` already
uses — do not introduce a new one):

| Action | Method |
|---|---|
| List escrow accounts | GET |
| Create escrow account | POST — manual creation, any service_type + currency combo, from a form, no code change required |
| Account detail | GET |
| Freeze / unfreeze | POST |
| Manual deposit / withdraw | POST — dual-auth gated per settings |
| Update settings (fees, windows, thresholds, enabled flags) | POST |
| Run reconciliation | POST |
| Reconciliation report | GET |
| Transaction history | GET, filterable |

---

## 8. Phase 6 — Admin frontend (HTML)

Do not design a new visual language. `app/templates/wallet/admin/` already
has `financial_controller.html`, `payment_aggregator.html`,
`regulator_access.html`, `sandbox_testing.html`, and the top-level
`wallet_admin_dashboard.html`, `wallet_control.html`, `wallet_detail.html`,
`wallet_stats.html`. Escrow is a capability *of* the wallet in this product,
not a separate product — so:

- Add `app/templates/wallet/admin/escrow_dashboard.html` styled identically
  to `wallet_admin_dashboard.html` (same layout partials, same CSS classes,
  reuse `app/templates/wallet/admin/` partials directory if one exists).
- Add `escrow_account_detail.html`, `escrow_create.html` (the manual
  creation form — service_type dropdown, currency, fee %, dispute window,
  dual-auth threshold, all writing to Phase 2's settings/account tables),
  `escrow_settings.html`, `escrow_reconciliation_report.html`.
- Reuse existing table/row partials (`app/templates/wallet/admin/` or
  transport's `partials/tables/*.html` pattern) rather than writing new
  markup from scratch.

**Best-platform feature parity** (Stripe Connect, Escrow.com, Upwork,
Airbnb) to fold into these screens, not as separate pages:
- Real-time balance display (ledger-derived, refreshed on load — don't
  cache a stale virtual_balance anywhere in the template context).
- Timeline/audit view per transaction (hold → pending release → released/
  disputed → resolved), not just a flat transaction list.
- One-click freeze with mandatory reason field (already modeled —
  `AccountModel.freeze()` requires `reason`).
- Dispute window countdown visible per transaction, not just in raw days.
- Dual-authorization approval queue as its own filtered view for large
  manual withdrawals.

---

## 9. Phase 7 — Async jobs & webhooks

- Wire `EscrowWorkflowService.process_scheduled_releases()` into
  `app/celery_app.py` on a schedule (e.g. hourly) — check how
  `app/tasks/reconcile.py` (already referenced in this project's
  architecture decisions) is scheduled and match that pattern.
- Wire `reconcile_all_escrow_accounts()` into the same daily/weekly/monthly
  cadence already used for wallet reconciliation, if one exists — check
  `app/celery_app.py` and any `beat_schedule` config before adding a new one.
- Emit `escrow.deposit`, `escrow.withdrawal`, `escrow.refund`,
  `escrow.reconciliation`, `escrow.discrepancy` through the **existing**
  `app/wallet/services/webhook_service.py` and `webhook_event.py` model —
  do not build a second webhook dispatch mechanism.

---

## 10. Required deliverable: `ESCROW_BUILD_REPORT.md`

Produce this file at the project root when done. Structure, exactly:

```markdown
# Escrow Build Report — <date>

## Section A: Phase 0 audit findings
(one row per audit item from Section 2, with exists/partial/missing + file:line)

## Section B: Prerequisite fixes applied
(the 3 items from Phase 1 — what was found, what was changed, migration filename)

## Section C: What already existed and was reused as-is
(component, file path, why no change was needed)

## Section D: What was built new
(component, file path, line count, what it does)

## Section E: Integration points wrapped (Phase 4)
(module, function, file:line, confirmed fallback path tested)

## Section F: Settings now exposed in admin UI
(setting name, where it's editable, confirmed it takes effect without redeploy)

## Section G: Tests added/run
(test file, what it covers, pass/fail)

## Section H: Still TODO before this is fully deployable
(explicit list — do not omit anything genuinely incomplete; a report that
claims completeness without evidence is worse than an honest gap list)

## Section I: Known risks / things a human should verify before production
(e.g. dual-auth threshold not yet enforced in UI, discrepancy Type A/D not
auto-logged, whatever is actually true at the time this report is written)
```

Section H and I must not be left empty or filled with vague reassurance —
if you find yourself wanting to write "all P0 issues resolved" without a
specific test or grep result backing that claim, that is the signal to
instead write down exactly what wasn't verified.

---

## 11. Explicit guardrails

- Do not add any column named `virtual_balance` or `real_balance` anywhere.
- Do not create a second config/settings table if one already exists —
  extend it.
- Do not create a second kill-switch/middleware mechanism — extend
  `kill_switch.py`.
- Do not touch `RoomType.total_units` or anything in the accommodation
  booking-loop bug list from the separate ongoing audit — out of scope here.
- Do not mark anything "complete" in the report without a corresponding
  grep/test result in the same section proving it.
- After every file edit, re-verify the change landed on disk before
  proceeding to the next file.
