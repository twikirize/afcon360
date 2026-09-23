# Fix Contract — Fix 2.5 — Booking Request Points Extraction

**Owner:** [your name]
**Date:** 2026-09-23
**Status:** READY FOR AGENT
**Roadmap reference:** Edition 2.0, Part VII, Fix 2.5
**Report format:** Compact

## 1. Guarantee

`app/transport/services/booking_service.py::booking_request_points()`
returns the same (points, skipped) for any input as it does today,
but without materializing Booking ORM instances. The query emits
only the two extracted coordinate scalars per row and streams results
to bound peak memory.

## 2. Current Behavior

`booking_request_points()` runs:

```python
rows = (Booking.query
        .filter(Booking.is_deleted == False)
        .filter(~Booking.status.in_(DEMAND_EXCLUDED_STATUSES))
        .filter(Booking.created_at >= start,
                Booking.created_at <= end)
        .all())
```

`.all()` materializes every matching Booking ORM instance. For a
30-day window in a mid-size city (roughly 500k rows), that is 500k ORM
objects held in memory simultaneously before the loop begins.

Verified by reading:

- `app/transport/services/booking_service.py` — the `booking_request_points`
  function and its `.all()` call.
- `DEMAND_EXCLUDED_STATUSES` is defined in the same file as
  `(BookingStatus.DRAFT, BookingStatus.CANCELLED)`.

## 3. Scope — Files In

- `app/transport/services/booking_service.py`
  → replace the query inside `booking_request_points()` with a
  scalar-extracting streaming query.

- `tests/transport/test_booking_request_points.py`
  → new file, tests named in Section 6.

## 4. Scope — Files Out

- Every other service in `app/transport/services/`
- `app/transport/models.py`
- `app/transport/api/*.py`
- `app/transport/routes.py`
- `migrations/**` (no schema change; `pickup_location` is already JSONB)
- `app/geo/**`
- `requirements.txt`
- `tests/conftest.py`
- Any template
- Any file not listed in Section 3

## 5. Interface Contract

### Signature

Unchanged:

```python
def booking_request_points(since, until) -> tuple[list[tuple[float, float, None]], int]:
```

### Return value

Unchanged:

- `points`: list of `(latitude: float, longitude: float, None)` tuples.
- `skipped`: int count of rows that failed extraction or validation.

### Extraction rule (must match current semantics exactly)

A row contributes to `points` if and only if:

- `pickup_location` is a JSON object with numeric-coercible
  `latitude` and `longitude` fields, AND
- `-90.0 <= latitude <= 90.0`, AND
- `-180.0 <= longitude <= 180.0`.

Any other row (missing fields, non-numeric, out of range,
non-object JSON) contributes to `skipped` instead.

### Implementation shape

Use a `select()` of two scalar expressions, not a `Booking.query`:

```python
stmt = (
    select(
        Booking.pickup_location.op("->")("latitude"),
        Booking.pickup_location.op("->")("longitude"),
    )
    .where(
        Booking.is_deleted.is_(False),
        ~Booking.status.in_(DEMAND_EXCLUDED_STATUSES),
        Booking.created_at >= start,
        Booking.created_at <= end,
    )
    .execution_options(yield_per=1000)
)

result = db.session.execute(stmt)
for lat_val, lng_val in result:
    ...
```

The coordinate expressions must preserve the native JSON scalar type
sufficiently for the existing Python coercion semantics to remain
unchanged. PostgreSQL `->` or an exactly equivalent JSONB scalar
extraction is preferred. `->>` text extraction is not acceptable where
it changes legacy handling of JSON booleans or other scalar types.

*Amendment note (2026-09-23): the original `->>` requirement is
superseded. Semantic review of the first implementation showed `->>`
converts JSON `true`/`false` to `"true"`/`"false"` text, turning legacy
`1.0`/`0.0` points into skips. The behavioral guarantee (§1) outranks
the extraction form.*

### Behavior when since/until are missing or invalid

Unchanged. The function still raises `ValueError` per its existing
pre-flight checks. Do not touch that logic.

### Return type change

None. Same tuple, same order, same element types.

## 6. Proof of Done

### Command 1

```text
pytest tests/transport/test_booking_request_points.py -v
```

Expected: 3 tests pass.

- `test_same_output_as_legacy_for_controlled_fixture`
  Seed a controlled set of bookings: numerics, numeric strings
  (including whitespace-padded), JSON booleans, boolean-looking
  strings, null/missing fields, invalid numeric strings, boundary and
  just-outside-boundary coords, non-object JSON (null, array, scalar),
  plus one cancelled, one draft, one deleted, out-of-window rows, and
  exact-window-boundary rows. Call `booking_request_points()`. Assert
  the returned points list and skipped count exactly match a test-only
  reference oracle replicating the legacy Python extraction semantics
  (differential comparison, per row).

- `test_query_selects_only_two_scalars`
  Capture the actual statement passed to `db.session.execute`, compile
  it with the PostgreSQL dialect, and assert it selects exactly two
  coordinate scalar expressions, not Booking rows; prove the SQL uses
  `->` native JSON scalar extraction (and NOT `->>` text extraction)
  so JSON type semantics survive, and that `yield_per=1000` is
  configured on the actual statement.

- `test_one_database_query_issued`
  Use `sqlalchemy.event.listen` on `before_cursor_execute` to count
  database round-trips during the call. Assert exactly 1 SELECT is
  issued regardless of the number of matching rows. Install and remove
  the listener in a `try/finally` (or equivalent teardown) so it cannot
  leak into other tests.

### Command 2

```text
pytest tests/transport/ -v
```

Expected: same pass/fail profile as before this node — 71 passed,
2 pre-existing failures in `test_marketplace_ux_harmonisation.py`
(recorded as pre-existing, not introduced by Fix 2.5).

### Command 3 — targeted git proof

```text
git diff --stat -- app/transport/services/booking_service.py
```

Expected: only the `booking_request_points` body changed.

```text
git status --short -- tests/transport/test_booking_request_points.py
```

Expected: ?? (new, untracked).

## 7. Rollback

```text
git revert <commit-sha-of-this-node>
```

No migration. No schema. No data. Rollback time under 30 seconds.

## 8. Constraints (Do NOT)

- Do NOT change `booking_request_points`'s signature.
- Do NOT change the `DEMAND_EXCLUDED_STATUSES` tuple.
- Do NOT change the `ValueError` pre-flight checks.
- Do NOT change the `(lat, lng, None)` tuple shape.
- Do NOT introduce a new dependency. SQLAlchemy's `select` and
  `yield_per` are already available.
- Do NOT add caching.
- Do NOT modify any other function in `booking_service.py`.
- Do NOT modify `tests/conftest.py`.
- Do NOT commit. Propose and stop.
- Do NOT run `flask db migrate` or `flask db upgrade`.

## 9. Acceptance Criteria

- [ ] `booking_request_points()` returns the same (points, skipped)
      as the current implementation for any input.
- [ ] No Booking ORM objects materialized — only two scalar columns
      selected.
- [ ] Results stream via `yield_per` (or equivalent).
- [ ] One database query issued per call.
- [ ] Pre-flight `ValueError` behavior unchanged.
- [ ] 3 tests pass.
- [ ] Full `tests/transport/` suite profile unchanged.
- [ ] Only Section 3 files touched.
- [ ] No new dependency.
- [ ] No migration.

## Notes for the Agent

Read `app/transport/services/booking_service.py` — specifically the
`booking_request_points` function and its docstring — before
proposing a plan. The docstring documents the semantics; the
implementation must preserve them exactly.

Answer these questions in your plan:

1. Which SQLAlchemy form will you use to extract the two scalars
   (`Booking.pickup_location.op('->>')('latitude')` vs
   `func.jsonb_extract_path_text(...)`)? Confirm it emits `->>`
   (text extraction), not `->` (JSON extraction), so `float()`
   coercion matches the current Python behavior on string values.

2. How will `test_one_database_query_issued` reset the event
   listener between tests? (The listener must be removed in teardown,
   or it will leak into other tests.)

Do not write code until the human approves your plan.
