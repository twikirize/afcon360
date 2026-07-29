# Fix TravelRuleTransfer Fk Type Mismatch

## Root Cause

`TransactionModel.id` is `UUID` (`app/wallet/models/transaction.py:60-64`), but `TravelRuleTransfer.transaction_id` is defined as `BigInteger` in `app/wallet/models/travel_rule.py:99`. The auto-generated migration `90dbd473780b` creates `travel_rule_transfers.transaction_id` as `BIGINT` and adds `FOREIGN KEY(transaction_id) REFERENCES transactions (id)`, which fails because `transactions.id` is `uuid`.

All other wallet models that reference `transactions.id` (`ledger.py`, `audit.py`, `adjustment.py`) correctly use `UUID(as_uuid=True)`.

## Files to Change

1. `app/wallet/models/travel_rule.py`
   - Import `UUID` from `sqlalchemy.dialects.postgresql`
   - Change `transaction_id = Column(BigInteger, ForeignKey('transactions.id'), ...)` to `transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.id'), ...)`

2. `app/wallet/services/travel_rule_service.py`
   - Change `transaction_id: int` type hint to `transaction_id: uuid.UUID` (or `str`) in `create_travel_rule_record`

## Migration Action

After the model is fixed, the user must regenerate the migration:

```powershell
flask db migrate -m "fix travel_rule_transfers transaction_id type to uuid"
flask db upgrade
```

**Do not run migrations automatically.**

## Verification

1. Confirm `TransactionModel.id` is UUID and `TravelRuleTransfer.transaction_id` matches it.
2. Confirm other wallet models (`ledger`, `audit`, `adjustment`) already use UUID for `transactions.id` FKs.
3. Run `python -c "from app import create_app"` to verify no import errors.
4. Regenerate and run migration successfully.

## Risks

- Migration `90dbd473780b` has not been applied (it failed), so changing the model is safe.
- `TravelRuleService.create_travel_rule_record` is defined but not currently called in routes, so changing its type hint has no runtime impact.
- No other files in `app/` reference `TravelRuleTransfer.transaction_id` as an integer.
