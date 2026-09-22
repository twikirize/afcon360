# Fix 2.3 — Evidence

## Test run (raw output)

Command:
```
& .venv/Scripts/python.exe -m pytest tests\integration\test_reservation_callback_idempotency.py -v --no-header
```

Output:
```
============================= test session starts =============================
collecting ... [OK] Kept 3 test items from 'tests/' directory.
collected 3 items

tests/integration/test_reservation_callback_idempotency.py::TestReservationCallbackIdempotency::test_first_callback_transitions_obligation PASSED [ 33%]
tests/integration/test_reservation_callback_idempotency.py::TestReservationCallbackIdempotency::test_duplicate_callback_is_noop PASSED [ 66%]
tests/integration/test_reservation_callback_idempotency.py::TestReservationCallbackIdempotency::test_duplicate_callback_same_reference_different_state_is_noop PASSED [100%]

============================== warnings summary ===============================
tests/integration/test_reservation_callback_idempotency.py::TestReservationCallbackIdempotency::test_first_callback_transitions_obligation
tests/integration/test_reservation_callback_idempotency.py::TestReservationCallbackIdempotency::test_first_callback_transitions_obligation
  C:\Users\OBED\Desktop\afcon360_app\.venv\Lib\site-packages\flask_session\filesystem\filesystem.py:75: DeprecationWarning: FileSystemSessionInterface is deprecated and will be removed in a future release. Instead use the CacheLib backend directly.
    warnings.warn(

tests/integration/test_reservation_callback_idempotency.py::TestReservationCallbackIdempotency::test_first_callback_transitions_obligation
tests/integration/test_reservation_callback_idempotency.py::TestReservationCallbackIdempotency::test_first_callback_transitions_obligation
  C:\Users\OBED\Desktop\afcon360_app\migrations\env.py:42: DeprecationWarning: 'get_engine' is deprecated and will be removed in Flask-SQLAlchemy 3.2. Use 'engine' or 'engines[key]' instead. If you're using Flask-Migrate or Alembic, you'll need to update your 'env.py' file.
    return current_app.extensions['migrate'].db.get_engine()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 3 passed, 4 warnings in 15.51s ========================
```

3 passed. 4 warnings (DeprecationWarnings from flask_session and migrations/env.py; pre-existing, unrelated to the fix).