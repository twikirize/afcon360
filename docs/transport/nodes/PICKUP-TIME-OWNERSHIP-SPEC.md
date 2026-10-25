# PICKUP-TIME-OWNERSHIP-SPEC — Instant/Scheduled Pickup-Time Semantics

**Mode:** SPECIFICATION (read-only analysis; no implementation authorized)
**Status:** DRAFT — awaiting owner decision
**Date:** 2026-10-25
**Node class:** BEHAVIORAL / HIGH_RISK boundary (any fix path may touch a production CHECK constraint)

> **Non-authorization statement:** This document specifies and compares options only.
> It does NOT change the `ck_pickup_time_sane` constraint, does NOT change service or
> frontend code, and does NOT authorize a migration. Any implementation node derived
> from this spec must carry its own contract, and any path touching the schema must
> follow AGENTS.md §20 canonical migration flow with explicit owner authorization
> (§48 populated-table safety rules apply).

---

## 1. Purpose

Record the verified behavior chain behind the instant-booking pickup-time defect,
state the ownership question it exposes, and compare the three owner-named
alternatives. The scheduled-booking contract (15-minute lead, timezone rules,
invalid-input behavior) is recorded separately in §6 and must stay separate from
any decision about instant semantics.

## 2. Verified behavior chain

Four links, each verified against current source on 2026-10-25:

### 2.1 The frontend supplies a client-computed instant pickup time

`templates/transport/new_home.html`:

- `setPickupTimeNow()` (lines 1431–1434) writes the **client machine's current
  time** into the hidden field: `d.toISOString().slice(0, 16)` → `hPickupTime.value`.
- `finalizePickupTime()` (lines 1918–1935) is called at the commitment boundary —
  stage `d` (line 1564) and the form-submit guard (lines 1979–1982, UI-14-F1).
  For `state.schedule === 'later'` it posts the chosen schedule time and refuses
  empty/invalid/past selections (lines 1923–1931); otherwise it calls
  `setPickupTimeNow()` (line 1933).
- The hidden `pickup_time` field therefore carries a value computed on the
  **client clock** for instant rides, not a value computed by the server.

### 2.2 The service passes the supplied pickup_time through for instant mode

`app/transport/services/booking_service.py`:

- Lines 535–542: if `pickup_time` is present it is parsed with
  `datetime.fromisoformat()`; a naive timestamp is localized to the configured app
  zone (`APP_TZ`, default `Africa/Nairobi`, resolved at lines 525–526).
- Lines 550–552: server-now (`datetime.now(timezone.utc)`) is used **only when
  `pickup_time` is absent** for an instant booking. The code comment (lines
  550–551) states the design assumption verbatim: *"The ck_pickup_time_sane
  constraint (5-min grace) absorbs any processing latency."*
- Net effect: for a normal instant request the stored `pickup_time` is the
  **client-supplied timestamp from form entry**, not a server-normalized
  "acceptance time".

### 2.3 The constraint anchors pickup_time to created_at (insert time), not acceptance time

- `app/transport/models.py:939–942`:

  ```python
  CheckConstraint(
      "pickup_time > created_at - INTERVAL '5 minutes'",
      name="ck_pickup_time_sane"
  )
  ```

- `created_at` is populated **at ORM INSERT**: `app/models/base.py:30–36`
  (`TimestampMixin`, Python-side `default=lambda: datetime.now(timezone.utc)`,
  `server_default=func.now()` as raw-SQL fallback).
- The constraint therefore compares a value fixed at **request time** (possibly
  minutes earlier, on a client clock) against a value fixed at **row-insert time**.

### 2.4 A sufficiently delayed request violates the constraint and surfaces as a misleading 503

- Any gap ≥ 5 minutes between the pickup-time value and the INSERT makes
  `pickup_time > created_at - 5 minutes` false → PostgreSQL `CheckViolation` →
  `IntegrityError`.
- Failure path: `booking_service.py:713–714` —
  `logger.error("IntegrityError with no key — cannot recover")` →
  `raise ServiceUnavailableError("Booking service temporarily unavailable")`.
  A stale-input condition is reported to the user as a transient outage.
- The same path fires for a **client clock behind server time by ≥ 5 minutes**,
  because the instant pickup value originates on the client clock (§2.1).

## 3. Status classification

Per the owner's adjudication of the E1–E10 proof run:

- **Pickup-time defect: OPEN / NOT PROVEN.** The six passing probe tests document
  current behavior; they do not prove the defect fixed.
- The constraint is proven active and enforced in the migration-built test schema
  (`test_instant_beyond_grace_rejected` asserts `ServiceUnavailableError` for a
  10-minute-past instant request).
- No fix has been implemented; this spec is the required decision gate before one.

## 4. The design question (owner-dictated)

Capturing a trusted **server-side request-acceptance time (T_acc)** is *necessary*
but **not sufficient**:

> If `pickup_time := T_acc` and the row is inserted at `T_ins` with
> `T_ins − T_acc ≥ 5 minutes`, then `pickup_time > created_at − 5min` is still
> false and the booking still fails.

Any fix must therefore decide **which clock event the invariant is anchored to**,
and whether the cutoff is a *correctness rule* (user intent must match stored
state) or a *staleness guard* (old requests must not silently book). The three
alternatives below differ precisely on that question.

## 5. Alternatives

### Option 1 — Preserve the instant-request time (change the invariant)

**Intent:** store what the user actually asked for (pickup at request time) and
make the invariant independent of insert latency.

Requires both of:

1. Capture `T_acc` server-side at request entry; set `pickup_time := T_acc`
   (removes client-clock skew from the equation — fixes the §2.4 skew failure);
2. Replace the insertion-time-dependent rule with an invariant anchored to an
   acceptance-time event. Two variants:

   - **1a — re-anchor `created_at` to `T_acc`.** No new column, but changes
     `created_at`'s meaning from "row created" to "request accepted".
     `created_at` backs four `Booking` indexes (`models.py:915–920`) and is a
     shared `TimestampMixin` contract (`base.py:28–44`) — blast radius extends
     beyond transport. **Rejected as unsafe without a dedicated ownership review.**
   - **1b — add an `accepted_at` column and re-declare the CHECK against it.**
     New column + constraint change = **schema migration** → §20 canonical flow,
     explicit owner authorization, §48 populated-table safety: existing
     `transport_bookings` rows need an evidence-backed backfill or an explicitly
     designed nullable/two-variant CHECK (three-valued logic makes a NULL
     `accepted_at` silently pass a CHECK — that backfill/nullability decision is
     an owner decision, not an agent default).

**Pros:** root-cause fix; preserves user intent; fixes both latency and
client-clock-skew classes; keeps instant bookings honest.
**Cons:** migration-backed (1b) or cross-domain semantics change (1a); highest
governance cost; requires backfill strategy for populated production tables.

### Option 2 — Retain the stale-request cutoff, return an accurate validation response

**Intent:** the 5-minute rule stays a deliberate staleness cutoff; failures become
honest 4xx validation errors instead of a misleading 503.

- Pre-validate at entry: compare server `T_acc` against the supplied
  `pickup_time` for instant mode; if older than the cutoff, raise `ValidationError`
  ("this instant request is too old — refresh and retry") **before** insert, with
  `ck_pickup_time_sane` retained as the database backstop.
- Additionally/alternatively, map a `CheckViolation` on this constraint
  distinctly at `booking_service.py:713` instead of the generic
  `IntegrityError → 503` branch.

**Pros:** no schema change; minimal scope; removes the misleading 503; keeps a
bounded staleness window.
**Cons:** the request still fails (user must retry); a permanently slow request
or a device with a badly skewed clock remains permanently unable to book an
instant ride — the defect class in §2.4 is *reported* correctly but not
*eliminated*.

### Option 3 — Widen the five-minute grace

**Intent:** reduce failure frequency by raising the window (e., 5 → 30 minutes)
via constraint alteration.

**Pros:** smallest visible behavior change; reduces frequency of both latency and
skew failures within the new window.
**Cons:** `ALTER` on a populated production table = migration (§20/§48 same
authorization bar as 1b); a fixed grace **never** changes the class of failure —
any delay or skew beyond the new window still 503s; a wider window weakens the
staleness guarantee the cutoff exists to provide (backdated/delayed requests
become committable for longer). Widening alone cannot satisfy an invariant like
"an instant request always commits", because the constraint remains anchored to
insert time.

### 5.1 Comparison

| Criterion | Opt 1 (invariant change) | Opt 2 (honest cutoff) | Opt 3 (wider grace) |
|---|---|---|---|
| Anchors invariant to acceptance | Yes (by design) | No — cutoff stays time-based | No |
| Eliminates latency/skew failures | Yes (1b: any insert delay) | No — reports them honestly | Partial — only within new window |
| Schema migration required | Yes (1b) / semantic review (1a) | No | Yes (constraint ALTER) |
| Populated-table backfill decision | Yes (1b) | No | No |
| Misleading 503 fixed | Yes | Yes | No (path unchanged) |
| Staleness guard strength | Owner redefines it | Preserved exactly | Weakened |
| Scope/governance cost | High | Low | Medium (migration) |
| Fixes client-clock skew | Yes (server T_acc) | No (skewed clocks stay locked out) | Partially (bigger window) |

### 5.2 Decision criteria for the owner

1. Is `pickup_time` for instant rides **user intent** (→ Option 1) or a
   **freshness signal** (→ Option 2/3)?
2. Is the 5-minute cutoff a product requirement (what stale-request exposure is
   acceptable) or merely an implementation artifact of anchoring to `created_at`?
3. Migration appetite: is a `transport_bookings` schema change acceptable now,
   or should an honest-validation fix (Option 2) ship first and an invariant
   change (Option 1b) be planned separately?
4. Client-clock skew policy: should a device with a wrong clock be locked out of
   instant rides (today's behavior) or normalized to server time (Option 1)?

A hybrid — Option 2 as an immediate honest-failure fix plus Option 1b as a
separately authorized follow-up node — is available; it still requires explicit
migration authorization for the 1b half.

## 6. Scheduled-mode contract (explicitly separate)

These rules are **not** in dispute and must not be altered by any option above:

- **Mode validation:** `booking_mode` must be `instant` or `scheduled`
  (`booking_service.py:528–533`, `ValidationError`).
- **Explicit time required:** scheduled bookings without `pickup_time` raise
  `ValidationError` (`:545–550`).
- **15-minute minimum lead:** `pickup_time` must be ≥ server-now + 15 min
  (`:558–567`), message:
  *"Scheduled pickups must be at least 15 minutes from now. For an immediate ride, choose 'Now'."*
  Enforced in Python before the DB (probe `test_scheduled_near_past_rejected_by_app`).
- **Timezone:** naive `pickup_time` is interpreted as `APP_TZ`
  (default `Africa/Nairobi`), never machine-local and never implicitly UTC
  (`:525–526`, `:538–542`; probe `test_naive_timestamp_interpreted_as_nairobi`).
- **Universal backstop:** `ck_pickup_time_sane` applies to both modes
  (`:554–557` comment; constraint is mode-agnostic).
- **Frontend mirror:** `SCHED_MIN_LEAD_MS` = 15 min and `isScheduleValid()`
  (`new_home.html:1466–1467`, lead check at `:1473`); UI-14-F1/F2 block commit of
  empty/invalid/past schedule selections (`:1919–1928`, `:1979–1982`).
- **Observed invalid-input quirk (recorded, not adjudicated):** a malformed
  `pickup_time` is caught by `except (ValueError, TypeError, KeyError)` at
  `:543`; for scheduled it becomes the clear `ValidationError` above, but for
  instant it falls through to the server-now default (`:550–552`). If the owner
  wants malformed-input behavior specified, it needs its own decision — it is
  out of scope for the instant-semantics choice.

## 7. Test evidence mapping

`tests/transport/test_booking_mode_probe.py` — run 2026-10-25 against
migration-built `afcon360_test` (rev `1792869659`): **6 passed, 0 errors, exit 0**.

| Test | What it proves | Closes the defect? |
|---|---|---|
| `test_instant_now_commits` | instant booking with client-time pickup commits (`:73–83`) | n/a — behavior baseline |
| `test_instant_with_latency_commits` | 2-minute-past pickup inside grace commits (`:85–95`) | No — grace still bounded |
| `test_instant_beyond_grace_rejected` | 10-min-past instant → `ServiceUnavailableError` (`:97–106`) | **No — documents the defect's failure surface** |
| `test_scheduled_future_commits` | scheduled +30 min commits, mode persisted (`:108–118`) | n/a — scheduled baseline |
| `test_scheduled_near_past_rejected_by_app` | +3 min scheduled rejected in Python with 15-min message (`:120–129`) | n/a — scheduled rule |
| `test_naive_timestamp_interpreted_as_nairobi` | naive input → APP_TZ (`:131–146`) | n/a — timezone rule |

## 8. Decision request

Owner to select: **Option 1b** (spec → separate implementation node with migration
authorization), **Option 2**, **Option 3**, or a **hybrid** (e.g., 2 now, 1b as a
follow-up node). Whichever is chosen, a follow-up node contract must name the
authorized files, the verification commands, and — for 1b/3 — the migration
authorization explicitly.

**No code, constraint, or migration changes are authorized by this document.**

## 9. Evidence index (all re-verified 2026-10-25)

- `templates/transport/new_home.html:1431–1434, 1564, 1918–1935, 1979–1982`
- `app/transport/services/booking_service.py:525–567, 713–714`
- `app/transport/models.py:939–942` (`ck_pickup_time_sane`), `:915–920` (created_at indexes)
- `app/models/base.py:28–44` (`TimestampMixin.created_at` — Python default at INSERT)
- `tests/transport/test_booking_mode_probe.py:73–146` (6 probe tests)
- Gate run 2026-10-25: `pytest tests/transport/test_booking_mode_probe.py -v` → 6 passed, exit 0;
  DB post-state 18 populated / 523 rows / rev `1792869659` (baseline match)
