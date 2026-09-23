# Fix 2.5 — Evidence (Booking Request Points Extraction, corrected)

**Date:** 2026-09-23
**Owner:** [your name]
**Gate reference:** Edition 2.0, Part VII, Fix 2.5
**Result:** PASS (subject to human confirmation)

---

## 0. Correction history (read first)

The first implementation used `->>` text extraction and was REJECTED on
semantic review: `->>` converts JSON `true`/`false` to `"true"`/`"false"`
text, turning legacy `1.0`/`0.0` points into skips. The contract's
behavioral guarantee outranks the extraction form, so the contract was
amended (`->` preferred, `->>` not acceptable where it changes legacy
handling) and the implementation corrected to `->` native JSON scalar
extraction. Everything below documents the CORRECTED final state only.

## 1. Contract verification and amendment

`docs/transport/fixes/Fix-2.5-contract.md` read from the repository
before editing. Amended per human direction: §5 shape now mandates
`->` with the native-scalar-type paragraph + amendment note recording
the semantic-review supersession; §6 test descriptions updated to the
expanded matrix and the `->`/not-`->>` proof. All other sections
unchanged.

## 2. Implementation diff (application change)

`git diff --stat -- app/transport/services/booking_service.py`:

```text
 app/transport/services/booking_service.py | 33 +++++++++++++++++++------------
 1 file changed, 20 insertions(+), 13 deletions(-)
```

Single hunk, confined to `booking_request_points()` body (def line,
pre-flight checks, range gate, append, return untouched):

```diff
-    rows = (Booking.query
-            .filter(Booking.is_deleted == False)  # noqa: E712
-            .filter(~Booking.status.in_(DEMAND_EXCLUDED_STATUSES))
-            .filter(Booking.created_at >= start,
-                    Booking.created_at <= end)
-            .all())
+    stmt = (
+        sa.select(
+            Booking.pickup_location.op("->")("latitude"),
+            Booking.pickup_location.op("->")("longitude"),
+        )
+        .where(
+            Booking.is_deleted.is_(False),
+            ~Booking.status.in_(DEMAND_EXCLUDED_STATUSES),
+            Booking.created_at >= start,
+            Booking.created_at <= end,
+        )
+        .execution_options(yield_per=1000)
+    )
+    result = db.session.execute(stmt)
     points: List[Any] = []
     skipped = 0
-    for booking in rows:
-        loc = booking.pickup_location
-        if not isinstance(loc, dict):
-            skipped += 1
-            continue
+    # Row values are native JSON scalars (-> preserves type: numbers,
+    # strings, booleans, nulls), so the float()/range/skip logic below
+    # is exactly the legacy Python semantics.
+    for lat_val, lng_val in result:
         try:
-            lat = float(loc.get("latitude"))
-            lng = float(loc.get("longitude"))
+            lat = float(lat_val)
+            lng = float(lng_val)
         except (TypeError, ValueError):
             skipped += 1
             continue
```

No import changes (`sa`, `db`, `Booking` already imported). No `.all()`.
No `order_by`. No schema change.

## 3. Focused tests (corrected)

`.venv\Scripts\python.exe -m pytest tests/transport/test_booking_request_points.py -v`:

```text
test_same_output_as_legacy_for_controlled_fixture PASSED [ 33%]
test_query_selects_only_two_scalars PASSED [ 66%]
test_one_database_query_issued PASSED [100%]
3 passed in 12.89s
```

The behavior test is differential: a 29-row matrix (numerics,
numeric strings incl. whitespace-padded, JSON true/false,
"true"/"false" strings, null/missing keys, "abc"/"12km",
boundaries -90/90/-180/180 in and just-outside out, non-object
null/array/scalar, DRAFT/CANCELLED/deleted/out-of-window/boundary
filters) is evaluated by a test-only `_legacy_reference` oracle
replicating the pre-Fix-2.5 Python semantics, and the function's
actual output must match per row (sorted multiset + exact skip
count + row accounting). The statement test asserts exactly two
`BinaryExpression` selections, exactly two single-arrow `->` uses,
zero `->>`, latitude/longitude keys, and `yield_per == 1000` — all on
the captured statement.

Process notes (test-file only): seed rows derive `pickup_time` from
their own `created_at` to satisfy DB check `chk_pickup_time_future`
(`CHECK (pickup_time > created_at)`, DB-level, absent from model
metadata — recorded as follow-up). Credential for that lookup came
from `.env.testing` via a temp script deleted immediately after; no
secret recorded here.

## 4. Full transport suite

`.venv\Scripts\python.exe -m pytest tests/transport/`:

```text
2 failed, 74 passed in 114.09s (0:01:54)
```

74 = 71 baseline + 3 new. The 2 failures are the identical
pre-existing `test_marketplace_ux_harmonisation` owner-review 302s
proven pre-existing on the clean tree during Fix 2.6. No unrelated
failure introduced or fixed.

## 5. Targeted git proof

`git diff --stat -- app/transport/services/booking_service.py` →
only that file (20+/13-, single hunk above).

`git status --short` for the node files:

```text
?? docs/transport/fixes/Fix-2.5-contract.md
?? tests/transport/test_booking_request_points.py
```

Remaining working-tree entries (T-10, My Trips, Fix 2.4/2.6 files,
BACKLOG, etc.) are pre-existing concurrent work, NOT Fix 2.5.

## 6. Environment / config state

- Date 2026-09-23, Windows, Python 3.13.14, PostgreSQL test DB
  `afcon360_test`, SQLAlchemy/psycopg2.
- No migration, no config key, no new dependency, no caching added,
  no conftest change, no commit, no register update, no BACKLOG update.
- Temp scripts deleted after use.
