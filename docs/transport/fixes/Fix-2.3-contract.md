# Fix Contract — Fix 2.3 — Reservation Callback Idempotency

**Last updated:** 2026-09-22
**Owner:** Human (Obed)
**Worker:** AFCON360 agent

## Description

Reservation callbacks from Wallet/Payment are NOT idempotent on the
`wallet_transaction_reference`. A duplicate wallet/payment callback carrying
the same `wallet_transaction_reference` may drive a second obligation
transition (or attempt one) on the reservation side. Fix 2.3 closes that gap
so the reservation side treats a repeated external financial event as a
no-op, in the same spirit as Fix 1.1's booking idempotency.

## 1. Guarantee

When a wallet/payment callback triggers
`TransportReservationService.apply_obligation_event()` with a
`wallet_transaction_reference`, the call is idempotent:

- The FIRST call with a given `wallet_transaction_reference` advances the
  obligation exactly once and records the reference.
- A DUPLICATE call with the same `wallet_transaction_reference` is a no-op:
  - it must NOT create an extra obligation transition;
  - it must NOT record an extra audit entry;
  - it must NOT raise an error;
  - it MUST return the current reservation row so the caller proceeds
    normally.
- A call with a DIFFERENT `wallet_transaction_reference` is a normal new
  event.

## 2. Files In Scope

- `app/transport/models.py` — add a partial unique index on
  `TransportReservation.wallet_transaction_reference`.
- `app/transport/services/reservation_service.py` — catch the unique-index
  `IntegrityError` in the commit path of `apply_obligation_event()` and treat
  it as a no-op success.
- `migrations/versions/<autogen>_reservation_wallet_ref_unique.py` — new
  migration (must include a working `downgrade()` that drops the index).
- `tests/integration/test_reservation_callback_idempotency.py` — new
  integration tests.

## 3. Files Out of Scope

Read-only when needed; never modified:

- `app/transport/services/fare_service.py`
- `app/transport/services/booking_service.py`
- `app/transport/services/assignment_service.py`
- `app/transport/services/offer_service.py`
- `app/transport/api/*.py`
- `app/transport/routes.py`
- `app/wallet/**`
- `requirements.txt`
- `tests/conftest.py`
- any file not listed in Scope In

## 4. Index

Partial unique index on `TransportReservation.wallet_transaction_reference`:

```sql
CREATE UNIQUE INDEX ix_reservation_wallet_ref
ON transport_reservations (wallet_transaction_reference)
WHERE wallet_transaction_reference IS NOT NULL;
```

## 5. Handler

In `apply_obligation_event()`, at the commit path:

```python
try:
    db.session.commit()
except IntegrityError:
    db.session.rollback()
    db.session.expire_all()
    existing = db.session.get(TransportReservation, reservation_id)
    return existing
```

## 6. Proof of Done

1. New integration test file
   `tests/integration/test_reservation_callback_idempotency.py` with these
   tests, all passing:
   - `test_first_callback_transitions_obligation`
   - `test_duplicate_callback_is_noop`
   - `test_duplicate_callback_same_reference_different_state_is_noop`

       pytest tests/integration/test_reservation_callback_idempotency.py -v

2. No duplicate references exist in the database:

   ```sql
   SELECT wallet_transaction_reference, COUNT(*)
   FROM transport_reservations
   WHERE wallet_transaction_reference IS NOT NULL
   GROUP BY wallet_transaction_reference
   HAVING COUNT(*) > 1;
   ```

   returns 0 rows.

3. `git diff --stat main` — only Scope-In files changed.

## 7. Constraints

- Do NOT modify the reservation state machine
  (`reservation_state_machine.py`).
- Do NOT change the signature of `apply_obligation_event()`.
- No new dependencies.
- Do NOT touch `app/wallet/`.
- Do NOT modify `tests/conftest.py`.
- Do NOT add a new column to `TransportReservation`.
- Migration must include a working `downgrade()`.

## 8. Rollback

    DROP INDEX IF EXISTS ix_reservation_wallet_ref;
    git revert <commit>