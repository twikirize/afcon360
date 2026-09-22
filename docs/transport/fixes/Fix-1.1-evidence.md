# Fix 1.1 — Evidence

## Command 1 — pytest
pytest tests/integration/test_booking_idempotency.py -v

Output:
4 tests passed in 24.66s (initial run)
4 tests passed in 24.99s (verification run)

## Command 2 — no duplicate keys
SELECT idempotency_key, COUNT(*)
FROM transport_bookings
WHERE idempotency_key IS NOT NULL
GROUP BY idempotency_key
HAVING COUNT(*) > 1;

Output: (0 rows)

## Command 3 — git diff --stat
Only files in Contract Section 3 appeared:
- app/transport/models.py (+12)
- app/transport/services/booking_service.py (+30)
- templates/transport/home.html (+8)
- templates/transport/new_home.html (+8)
- migrations/versions/aab3e38879dc_add_booking_idempotency_key.py (+34)
- tests/integration/test_booking_idempotency.py (+96)

## Manual verification
- Browser: /transport/new-home → filled pickup/dest → Find a Ride → selected vehicle → Book Now → Confirm. Booking TR260922JLR0K0 created.
- Direct service: 5-thread concurrent submit with same key → 1 row, 4 replays, all succeed.

## Environment
Date: 2026-09-22
Branch: main
Commits: 1bf34b9, a4c5e8b, 031acf2
Python: 3.13.14

## Result
All commands passed. Fix 1.1 gate: PASS.