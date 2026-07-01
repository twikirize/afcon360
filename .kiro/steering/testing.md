# AFCON360 — Testing Conventions

## Test Runner
- pytest + pytest-flask + pytest-cov
- Config: `tests/conftest.py`
- Run all: `pytest tests/ -v` (from project root with venv active)
- Coverage: `pytest --cov=app tests/`

## Test Database
- Separate test DB via `.env.test`
- Reset: `python scripts/reset_test_db.py`
- Schema setup: `python scripts/setup_test_db_schema.py`
- NEVER run migrations inside tests — use existing schema

## Test Structure
```
tests/
  conftest.py              # fixtures
  wallet/                  # wallet-specific tests
  test_registration_flow.py
  test_payment_flow.py
  test_event_workflow.py
  test_trust_system.py
  test_impersonation.py
```

## Rules
- Mock all external payment gateways — never call real Flutterwave/Paystack in tests
- Mock Redis in unit tests — do not test against live Redis
- Wallet tests: use isolated DB transactions, rollback after each test
- Role/permission tests: create test users with `tests/setup_owner.py` helpers
- NEVER commit test data to the main DB

## Running Specific Suites
```bash
pytest tests/wallet/ -v          # wallet tests only
pytest tests/ -k "impersonation" # filter by name
pytest --tb=short                # shorter tracebacks
```
