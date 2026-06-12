# AFCON360 Events — Registration System Refactor Plan

**Audience:** CLI coding agent (e.g. Claude Code) operating on this Flask/SQLAlchemy
codebase.

**Scope:** Make the `self` / `third_party` / `group` registration model fully
consistent across `models.py`, `services.py`, `payment_service.py`, `routes.py`,
and every attendee/organizer template that reads or writes `EventRegistration`
rows. No new registration *types* are introduced — the three-type taxonomy is
correct. This plan fixes correctness bugs, removes duplicated/divergent logic,
and adds the minimum new fields needed for organizer-side grouping.

**Companion document:** `REGISTER_FORM_REDESIGN.md` covers the rebuilt
`register.html` (manual rows / "generate N" / bulk Excel upload for large
groups). That depends on Phase 1 of this plan (the `group_label` column and
`group_index` semantics) and should be done **after** Phases 0–1 land.

---

## How to use this document

Work through phases **in order** — each phase assumes the previous one is
merged, because later phases read/write fields that earlier phases fix or add.
Within a phase, items can be done in parallel. Each item has:

- **Problem** — what's wrong, in plain terms
- **Location** — file + function/line area
- **Goal** — the end state
- **Solution** — concrete implementation steps
- **Acceptance criteria** — how to verify it's done

Run the existing test suite (or write minimal regression tests for each item
if none exist) before moving to the next phase. Phase 0 items are production
bugs — fix and deploy independently of the rest if needed.

---

# Phase 0 — Critical bugfixes (P0)

These are active bugs. 0.1 is the literal 500 from the logs. 0.2 is a **more
severe latent bug** discovered while reviewing `payment_service.py` — it
silently corrupts data for paid group/third-party registrations and should be
treated as equally urgent.

## 0.1 — `register_for_event_optimistic` missing `group_index` parameter

**Problem:** `EventService.register_for_event()` (the public entry point)
accepts and forwards `group_index`, and `_register_for_event_pessimistic()`
accepts it and writes it to the `Registration` row. But
`register_for_event_optimistic()` — the path actually used
(`use_optimistic = True`) — has no `group_index` parameter, so any call that
forwards it raises:

```
TypeError: EventService.register_for_event_optimistic() got an unexpected
keyword argument 'group_index'
```

**Location:** `app/events/services.py`, `register_for_event_optimistic`
(signature ~line 653, `Registration(...)` constructor ~line 766).

**Goal:** `register_for_event_optimistic` accepts `group_index` and persists
it on the created row, matching `_register_for_event_pessimistic`.

**Solution:**
1. Add `group_index: Optional[int] = None` to the method signature (after
   `group_booking_id: str = None`).
2. In the `Registration(...)` constructor inside the method, add
   `group_index=group_index,` alongside the existing
   `group_booking_id=group_booking_id,` line.

**Acceptance criteria:** A POST to `/events/<slug>/register` with
`booking_type=group` and one or more `group_attendees_data` entries no longer
500s, and the resulting `event_registrations` rows have non-null
`group_index` (see 1.5 for the exact values expected).

---

## 0.2 — `payment_service._get_or_create_attendee_user` is a stub that corrupts paid group/third-party data

**Problem:** For **paid** events, third-party and group registrations go
through `EventPaymentService._create_registrations()` →
`_get_or_create_attendee_user()`. That method is an unfinished stub:

```python
def _get_or_create_attendee_user(self, attendee_data: Dict) -> int:
    email = attendee_data.get("email")
    if email:
        user = User.query.filter_by(email=email).first()
        if user:
            return user.id
    # Create a temporary user record or use the primary user's ID
    # For now, return the primary user's ID (this needs proper implementation)
    return attendee_data.get("primary_user_id", 1)
```

If the attendee's email doesn't match an existing user (the normal case for a
new third-party/group attendee), this returns **literal user id `1`** for
*every* such attendee, since `attendee_data` never contains
`primary_user_id`. Consequences:

- Every new attendee in a paid group registration gets
  `EventRegistration.user_id = 1` (whoever that account belongs to —
  possibly the platform's first admin/system user).
- The DB unique constraint `uq_reg_event_user (event_id, user_id)` means the
  **second** such attendee in the same event raises `IntegrityError`, caught
  by the generic `except Exception` in `process_ticket_purchase`, rolled back,
  and surfaced as a vague `"error": str(e)` to the registrant — even though
  payment may already have been debited before the rollback.
- Even for the *first* attendee, the registration is permanently mis-attributed
  to user `1`, polluting that account's `my_registrations` and any
  attendee-facing dashboard.

Meanwhile, `EventService.find_or_create_attendee_user()` (used by the free-event
path in `routes.py`) already does this correctly — it creates a real guest
user account for the attendee.

**Location:** `app/events/payment_service.py`,
`EventPaymentService._get_or_create_attendee_user` (~line 388) and its caller
`_create_registrations` (~line 294-313).

**Goal:** Paid third-party/group attendees get a real, unique user account
(existing or newly-created guest), identical in behavior to the free-event
path — one source of truth for "find or create an attendee account."

**Solution:**
1. Delete `_get_or_create_attendee_user` from `payment_service.py`.
2. In `_create_registrations`, for each `attendee_data` in `group_attendees`,
   call `EventService.find_or_create_attendee_user(email=..., name=...,
   phone=...)` (import `EventService` at the top of `payment_service.py`,
   matching how `services.py` already imports across modules — watch for
   circular imports; if `EventService` imports `EventPaymentService`
   anywhere, move `find_or_create_attendee_user` to a shared module, e.g.
   `app/events/attendee_accounts.py`, and have both services import from
   there).
3. Propagate the `(user_id, error)` tuple: if `error` is set for any attendee,
   do **not** silently fall back — record it in a per-attendee errors list and
   skip creating that registration (see 0.5 for how errors propagate to the
   route/response).
4. Add a regression test: paid group registration with 2+ attendees who have
   no existing accounts must create 2+ distinct `users` rows and 2+ distinct
   `event_registrations.user_id` values, none equal to `1` (unless user 1
   actually is the payer/registrant).

**Acceptance criteria:** Paid group registration with N new attendees creates
N new guest user accounts (or reuses existing ones by email) and N
`event_registrations` rows with distinct `user_id` values, all correctly
referencing `booked_by_user_id = <payer's user id>`.

---

## 0.3 — Free-event group loop never sets `group_index`

**Problem:** Even after 0.1 is fixed, the **free-event** group branch in
`routes.py` calls `register_for_event(...)` in a loop without passing
`group_index` at all, so every row in a free-event group batch has
`group_index = NULL`. The **paid-event** group branch (via
`payment_service._create_registrations`) sets `group_index=None` for the
payer and `1..N` for additional attendees — but only because
`create_primary_for_payer=False` is used for paid groups, so the payer's own
row isn't created in that branch at all (it must already exist).

These two paths must produce **the same shape of data** for the same logical
operation. See 1.5 for the unified semantics; this item is just "wire it
through" once 1.5 defines the rule.

**Location:** `app/events/routes.py`, free-event group branch (~lines
683–760, the "1. Register or find primary registrant" / "2. Register
additional attendees" loops).

**Goal:** Every registration created as part of a group batch has a
deterministic, non-null `group_index` following the rule in 1.5, regardless
of whether the event is free or paid.

**Solution:** Implement after 1.5 is decided — see Phase 1. Do not implement
in isolation, or you'll need to redo it.

**Acceptance criteria:** For a free-event group submission of "myself + 3
colleagues," all 4 rows share one `group_booking_id` and have `group_index`
values per the rule in 1.5 (e.g. `0, 1, 2, 3`).

---

## 0.4 — Two independent `group_booking_id` generation sites

**Problem:** `routes.py` generates a fresh `group_booking_id = str(uuid.uuid4())`
in **two separate places** — once in the free-event group branch (~line 694)
and again in the paid-event group branch (~line 829). They're mutually
exclusive today (an event is either free or has `ticket_type_id`), so they
don't currently collide, but this duplication is exactly how the divergence in
0.3 happened, and it blocks the unified submission format in
`REGISTER_FORM_REDESIGN.md`.

**Location:** `app/events/routes.py`, both group branches inside
`events.register` (POST handler).

**Goal:** One function, one place, generates `group_booking_id` for a group
submission, regardless of free/paid.

**Solution:**
1. At the very top of the group-handling logic in `events.register` (before
   branching on free/paid), compute:
   ```python
   group_booking_id = str(uuid.uuid4())
   ```
   once, and pass it into whichever sub-path (free-event loop or
   `process_ticket_purchase`) runs next.
2. Remove the two inline `uuid.uuid4()` calls inside each branch.
3. This sets up Phase 0.3/1.5's unified loop — ideally both branches become
   thin wrappers around one "create N registrations for this batch" helper
   (see 1.5 Solution step 3).

**Acceptance criteria:** Grep for `uuid.uuid4()` inside `events.register` —
exactly one call site remains for `group_booking_id`.

---

## 0.5 — Unhandled exceptions mid-group-loop leave inconsistent state

**Problem:** In the free-event group branch, if attendee #4 of 5 raises
`SoldOutException` (or any other exception) from
`register_for_event_optimistic`, nothing in the loop catches it — it
propagates out of the whole route as an unhandled 500. Attendees #1–3 are
already committed (each call commits independently inside
`register_for_event_optimistic`'s `@with_transaction`), so the registrant
sees a generic error page while actually holding 3 confirmed tickets they
don't know about.

Separately, `_create_registrations` for paid groups runs everything inside one
DB transaction committed at the end of `process_ticket_purchase` — so a
mid-loop exception there rolls back cleanly, but the *payment* (wallet debit)
already happened in `_process_wallet_payment` before `_create_registrations`
is called, and that debit is **not** rolled back by `db.session.rollback()`
since wallet ledger writes go through `WalletService`, not necessarily the
same session/transaction. This needs verification (see Solution step 3).

**Location:**
- Free path: `app/events/routes.py`, attendee loop in the group branch
  (~lines 730–760).
- Paid path: `app/events/payment_service.py`, `process_ticket_purchase`
  (~line 29) and `_create_registrations` (~line 264).

**Goal:** A partial failure mid-batch (sellout, validation error, duplicate)
never produces an unhandled 500, never leaves the registrant in an unknown
state, and never debits a wallet for tickets that weren't actually issued.

**Solution:**
1. **Free path:** wrap each per-attendee `register_for_event(...)` call in
   `try/except (SoldOutException, Exception) as e`, append a human-readable
   message to the existing `errors` list (same list already used for
   duplicate-email skips), and `continue` to the next attendee. If
   `SoldOutException` occurs, stop the loop early (no point trying remaining
   attendees against a sold-out tier) but still report what succeeded.
2. **Paid path:** before calling `_create_registrations`, pre-validate
   capacity for the *full* requested quantity (`ticket_type.capacity -
   ticket_type.available_seats >= quantity`) — this already exists
   (`process_ticket_purchase` line ~64) and runs **before** payment, which is
   correct. The remaining risk is a registration-creation error *after*
   payment succeeds. Wrap the `_create_registrations` call in `try/except`;
   on failure, attempt a **compensating refund** via `WalletService` (credit
   back `total_price` with a `metadata` tag referencing
   `audit_transaction_id`), log an `AuditService.financial` entry with
   `status="reversed"`, and return
   `{"success": False, "error": "Payment was refunded due to a registration error. Please try again."}`.
   If a refund mechanism doesn't already exist in `WalletService`, add a
   `deposit`/credit call mirroring the `withdraw` call used in
   `_process_wallet_payment`.
3. Add a code comment at the top of `process_ticket_purchase` documenting
   this ordering invariant (capacity check → payment → registration creation
   → on registration failure, refund) so future edits don't reorder it.

**Acceptance criteria:** A test that forces `_create_registrations` to raise
on the 2nd of 3 attendees results in: (a) zero `event_registrations` rows
created for that batch, (b) the wallet balance unchanged from before the
attempt, (c) a 200/400 JSON response with a clear error — never a 500.

---

# Phase 1 — Model & constants consistency (P1)

## 1.1 — Add a `BookingType` enum to `constants.py`

**Problem:** `booking_type` / `registered_by` are free-form strings
(`"self"`, `"third_party"`, `"group"`) scattered across `models.py`,
`services.py`, `payment_service.py`, and `routes.py` with no central
definition — unlike `EventStatus`, which has a proper `Enum` with
`choices()`, `values()`, `is_valid()`. Typos (`"3rd_party"`,
`"groupbooking"`) would silently create rows that never match any filter.

**Location:** `app/events/constants.py` (new class, alongside `EventStatus`).

**Goal:** One enum, same pattern as `EventStatus`, used everywhere a
booking-type string is read or written.

**Solution:**
```python
class BookingType(str, Enum):
    """Who the registration is for, relative to who submitted the form."""
    SELF = "self"
    THIRD_PARTY = "third_party"
    GROUP = "group"

    @classmethod
    def values(cls) -> List[str]:
        return [b.value for b in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.values()
```
Then replace string literals:
- `models.py`: `booking_type = Column(String(30), default=BookingType.SELF.value, ...)`
- `services.py`: every `booking_type="self"/"third_party"/"group"` →
  `BookingType.SELF.value` etc. (import `from app.events.constants import
  BookingType`).
- `payment_service.py`: same.
- `routes.py`: `data.get('booking_type', BookingType.SELF.value)`, and the
  `if booking_type == "group":` checks → `== BookingType.GROUP.value`.
- Add validation at the route boundary: if `BookingType.is_valid(booking_type)`
  is `False`, return a 400 immediately instead of falling through to
  `register_for_event` with `registered_by` set to garbage.

**Acceptance criteria:** `grep -rn '"third_party"\|"self"\|"group"' app/events/`
(excluding `constants.py` and test fixtures) returns only enum-construction
lines and template Jinja conditions (templates are handled separately in
Phase 3, but can also reference `{{ BookingType.GROUP.value }}` if exposed to
Jinja context — optional polish).

---

## 1.2 — Deprecate `registered_by` in favor of `booking_type`

**Problem:** `registered_by` and `booking_type` are written identically at
every creation site (`registered_by=booking_type`), making them permanently
redundant *if* every write path stays disciplined — but
`my_registrations.html` already hedges by checking both
(`r.booking_type == 'self' or r.registered_by == 'self'`), which is a sign
this redundancy is already a source of doubt. Two columns recording one fact
is a maintenance hazard: a future write path that updates one and not the
other silently breaks every template/query that reads the other.

**Location:** `app/events/models.py`, `EventRegistration` class — `registered_by`
column (~line 686) and the `_deprecated()` helper (~line 46-60, already used
for `is_checked_in`).

**Goal:** `booking_type` is the single source of truth. `registered_by`
becomes a read-only computed alias (for backward compatibility with any
existing raw SQL/reports), and all template/query reads migrate to
`booking_type`.

**Solution:**
1. Keep the `registered_by` **column** in the DB for now (no migration to
   drop it yet — that's a separate, later cleanup once you've confirmed
   nothing external reads it directly via SQL).
2. Stop *writing* a real value to it in `services.py` and
   `payment_service.py` — either drop the kwarg from the `Registration(...)`
   constructors, or set it to `booking_type` once at creation and never touch
   it again (either is fine since it's now informational-only).
3. Add a property using the existing pattern:
   ```python
   @property
   def registered_by_flag(self) -> str:
       return self.booking_type
   registered_by_display = _deprecated("registered_by_flag")
   ```
   (Naming note: the existing `_deprecated()` helper assumes a `_flag` suffix
   convention from the `is_checked_in` case — adapt naming as needed, the key
   point is a `DeprecationWarning` on access.)
4. Fix `templates/events/attendee/my_registrations.html` line with
   `r.booking_type == 'self' or r.registered_by == 'self'` →
   `r.booking_type == 'self'` only (after confirming via a one-off query that
   no existing rows have diverging `booking_type`/`registered_by` — if any
   do, that's pre-existing data drift worth logging before removing the
   fallback).

**Acceptance criteria:** No template or route does an `or`-fallback between
`booking_type` and `registered_by`. `_registration_to_dict` still exposes
`registered_by` (for API backward compat) but its value is always identical
to `booking_type`.

---

## 1.3 — Resolve `attendee_user_id` vs `user_id` redundancy

**Problem:** For every booking type today, `user_id` and `attendee_user_id`
end up pointing at the same account
(`user_id = actual_attendee_id`, `attendee_user_id = actual_attendee_id if
booking_type != "self" else None`). `attendee_user_id` currently carries zero
information beyond `user_id` + `booking_type != "self"`.

**Location:** `app/events/models.py`, `EventRegistration.attendee_user_id`
column (~line 692) and its `attendee_user` relationship.

**Goal:** Either give `attendee_user_id` a real, distinct purpose, or remove
it. This decision affects Phase 2/3 (organizer views) and Phase 4
(cancellation authorization), so resolve it before those.

**Solution — pick one (recommend Option A for this pass):**

- **Option A (recommended, minimal):** Keep the column but document it
  explicitly as *redundant-by-design, reserved for future re-assignment*
  (e.g., "transfer this ticket to a different attendee" without changing
  `user_id`, which is tied to the original registration record's identity for
  audit purposes). Add a code comment in `models.py` stating this. Do not
  remove it — removing a column is a migration with rollback risk for no
  immediate benefit, and Option B's use case (ticket transfer) is plausible
  future work for an event platform.
- **Option B (if you want to actually use it now):** Build the "transfer
  ticket to someone else" feature: an organizer or booker can change
  `attendee_user_id` to a different user without altering `user_id` (which
  remains the "original registrant of record" for the unique constraint and
  audit trail), and `_registration_to_dict` / attendee dashboards display
  `attendee_user_id`'s profile as "current holder." This is materially more
  work and **out of scope for this refactor pass** — note it as a backlog
  item if chosen.

**Acceptance criteria (Option A):** A docstring/comment exists on
`attendee_user_id` explaining its current redundancy and intended future use;
no code change required beyond the comment.

---

## 1.4 — Add `group_label` column (the cross-batch cohort field)

**Problem:** There is currently no way for a registrant to signal "these
registrations belong to the same logical group/department," across multiple
submission batches (each batch gets its own `group_booking_id`). This blocks
both the organizer attendee-list grouping (Phase 3) and the redesigned form
(`REGISTER_FORM_REDESIGN.md`).

**Location:** `app/events/models.py`, `EventRegistration` class, alongside
`group_booking_id` and `group_index` (~line 690-693). New Alembic migration
in `migrations/versions/` (follow the naming/style of
`0df1a94b3534_add_multi_guest_booking_fields_for_.py`, which appears to be the
migration that originally added `group_booking_id`/`booking_type`/
`group_index`/`attendee_user_id`/`booked_by_user_id`).

**Goal:** A nullable, indexed, user-supplied string field that persists across
batches and is searchable/groupable by organizers.

**Solution:**
1. Add to `EventRegistration`:
   ```python
   # Optional, registrant-supplied label for cross-batch grouping
   # (e.g. "Acme Corp - Marketing Team"). Not validated against any
   # canonical list in this phase — see Phase 6 for AttendeeGroup.
   group_label = Column(String(150), nullable=True, index=True)
   ```
2. Add an index to `__table_args__` if not covered by `index=True` on the
   column already (column-level `index=True` is sufficient for a single-column
   btree index in SQLAlchemy — no separate `Index(...)` entry needed, but add
   one consistent with the existing style if other similar columns use
   explicit `Index(...)` entries):
   ```python
   Index("idx_reg_group_label", "group_label"),
   ```
3. Create the Alembic migration:
   ```bash
   flask db revision -m "add group_label to event_registrations"
   ```
   Migration body: `op.add_column('event_registrations',
   sa.Column('group_label', sa.String(150), nullable=True))` +
   `op.create_index('idx_reg_group_label', 'event_registrations',
   ['group_label'])`. Downgrade: drop index, drop column.
4. Update `register_for_event_optimistic`,
   `_register_for_event_pessimistic`, and
   `payment_service._create_single_registration` to accept and persist
   `group_label: Optional[str] = None`, threaded through from `routes.py`
   (`data.get('group_label')`).
5. Update `_registration_to_dict` and `_registration_to_dict_with_assignments`
   in `services.py` to include `"group_label": registration.group_label,`.

**Acceptance criteria:** A registration submitted with `group_label="Acme
Corp - Marketing"` persists that exact string on every row in the batch
(including the registrant's own row, if `booking_type=self`/`group`).
Submissions without it leave the column `NULL`. `SELECT * FROM
event_registrations WHERE group_label = 'Acme Corp - Marketing'` returns rows
across multiple `group_booking_id`s once a second batch reuses the same
label.

---

## 1.5 — Standardize `group_index` semantics across free and paid paths

**Problem:** As noted in 0.3, the free and paid group paths currently produce
different `group_index` shapes (free: always `NULL`; paid: `NULL` for payer,
`1..N` for attendees, payer's own row often not even created in that
branch). Any UI that orders/displays "position in this group" needs one rule.

**Location:** `app/events/routes.py` (`events.register` POST handler, both
group branches), `app/events/payment_service.py`
(`_create_registrations`/`_create_single_registration`).

**Goal:** A single rule, applied identically regardless of free/paid:

> Within one `group_booking_id` batch, `group_index = 0` is the **booker's
> own attendance row**, if the booker is attending (i.e.
> `booking_type` for that row is `self` or `group` with the booker as
> attendee). Additional attendees get `group_index = 1, 2, 3, ...N` in the
> order submitted. If the booker is *not* attending this batch (pure
> third-party/"register for others only"), `group_index` starts at `1` for
> the first attendee and there is no `group_index = 0` row.

**Solution:**
1. In `routes.py`, before branching free/paid, build a single normalized
   attendee list from the incoming payload (this is also the shape
   `REGISTER_FORM_REDESIGN.md` specifies):
   ```python
   attendees = []  # list of dicts: {index, is_self, name, email, phone}
   ```
   `index` is assigned here, server-side, by enumerating the payload in order
   — do not trust a client-supplied index.
2. **Free path:** loop over `attendees`; for `is_self=True`, call
   `register_for_event_optimistic(..., booking_type=BookingType.SELF.value
   if len(attendees) == 1 else BookingType.GROUP.value, group_index=0, ...)`;
   for others, `booking_type=BookingType.THIRD_PARTY.value,
   group_index=entry["index"]`.
3. **Paid path:** when calling `process_ticket_purchase`, if `attendees[0].is_self`
   is `True`, set `create_primary_for_payer=True` and pass
   `group_attendees=attendees[1:]` (so `_create_registrations` assigns
   `group_index=None` to the payer today — **fix this too**: change
   `_create_single_registration`'s payer branch from
   `group_index=None` to `group_index=0` when `create_primary_for_payer=True`
   and a `group_booking_id` is present). For `attendees[1:]`,
   `_create_registrations`'s existing `idx = 1; ... idx += 1` loop already
   produces `1..N` — keep that, just confirm it lines up with `entry["index"]`
   from step 1 (it should, since both enumerate in submission order starting
   at 1).
4. Add a short docstring comment near both loops referencing this section
   ("group_index: 0 = booker's own row if attending, 1..N = additional
   attendees in submission order — see REFACTOR_PLAN.md 1.5").

**Acceptance criteria:** For both a free event and a paid event, submitting
"myself + 2 colleagues" produces 3 rows sharing one `group_booking_id` with
`group_index` values `0, 1, 2`. Submitting "2 colleagues only" (booker not
attending) produces 2 rows with `group_index` values `1, 2` and no row with
`group_index=0`.

---

# Phase 2 — Confirmation page & "My Registrations" (P2)

## 2.1 — `registration_confirmation` group view breaks after the session expires

**Problem:** `group_registrations` in `registration_confirmation.html`
(~line 872) is populated only from `session['last_registration']`, set at the
moment of registration. Any later visit to the same confirmation URL — e.g.
via the "View QR Code" link from `my_registrations.html`, or a page
refresh/new device — has no session data, so the page shows only the single
attendee tied to `reg_ref`, with no indication the other registrations in the
batch exist.

**Location:** `app/events/routes.py`, `registration_confirmation` route;
`templates/events/attendee/registration_confirmation.html` (~lines 872-900).

**Goal:** The group view is always reconstructable from the database, with
the session data used only as a same-request optimization (e.g., to also show
per-attendee `errors` from the registration attempt, which *aren't* persisted
anywhere else).

**Solution:**
1. In the `registration_confirmation` route, after loading `registration` by
   `reg_ref`:
   ```python
   group_registrations = None
   group_errors = []
   session_data = session.get('last_registration')
   if session_data and session_data.get('registration', {}).get('registration_ref') == reg_ref:
       group_registrations = session_data.get('group_registrations')
       group_errors = session_data.get('errors', [])

   if group_registrations is None and registration.group_booking_id:
       siblings = EventRegistration.query.filter_by(
           group_booking_id=registration.group_booking_id
       ).order_by(EventRegistration.group_index.asc().nullsfirst()).all()
       if len(siblings) > 1:
           group_registrations = [EventService._registration_to_dict(r) for r in siblings]
   ```
2. Pass `group_registrations` and `group_errors` to the template as before;
   the template's existing `{% if group_registrations %}` block needs no
   change.
3. Note: `group_errors` (failed attendees from the original submission) is
   genuinely ephemeral — it's not useful to persist failed attempts. The
   template should simply not show that section on a non-session visit, which
   the `group_errors = []` default already handles.

**Acceptance criteria:** Visiting `/events/<slug>/registration/<reg_ref>` for
any attendee in a group, in a fresh session (no `last_registration`), still
shows the full "Group Registration" table of all siblings sharing that
`group_booking_id`.

---

## 2.2 — "My Registrations" has no view of registrations made *for others*

**Problem:** `get_user_registrations(user_id)` filters on
`Registration.user_id`. For third-party/group bookings, `user_id` is the
**attendee's** account (their own, or a freshly-created guest account), not
the booker's. A user who registers themselves + 5 colleagues sees only their
own ticket on `my_registrations.html` — the other 5 rows, which they paid for
and are responsible for, are invisible to them. `booked_by_user_id` already
records this relationship but nothing queries it for this purpose.

**Location:** `app/events/services.py`, `get_user_registrations` (~line 646);
`app/events/routes.py`, the route rendering
`templates/events/attendee/my_registrations.html`;
`templates/events/attendee/my_registrations.html` itself.

**Goal:** A second section, "Registrations You've Made for Others," listing
every row where `booked_by_user_id == current_user.id AND user_id !=
current_user.id`, grouped visually by `group_booking_id` (and `group_label`
when present).

**Solution:**
1. Add to `services.py`:
   ```python
   @classmethod
   def get_registrations_made_for_others(cls, user_id: int) -> List[Dict]:
       Registration = cls._get_registration_class()
       rows = Registration.query.filter(
           Registration.booked_by_user_id == user_id,
           Registration.user_id != user_id
       ).order_by(Registration.group_booking_id, Registration.group_index.asc().nullsfirst()).all()
       return [cls._registration_to_dict(r) for r in rows]
   ```
2. In the route, fetch this alongside the existing `registrations` and pass
   as `managed_registrations` (or similar) to the template.
3. In `my_registrations.html`, add a new section below "Past Events" (or as a
   tab — match existing UI conventions in the file):
   - Group `managed_registrations` by `group_booking_id` in the template
     (Jinja `groupby` filter) or pre-group in Python and pass a list of
     `{group_booking_id, group_label, event, attendees: [...]}` dicts —
     **prefer pre-grouping in Python** to keep the template simple and
     consistent with how `registration_confirmation` will eventually share
     this logic (consider a shared helper
     `EventService.group_registrations_by_batch(rows)` used by both 2.1 and
     2.2).
   - For each group, show: event name, `group_label` if set (else "Group
     registration"), attendee count, and a compact table (name, email, status,
     ticket #) with a per-row "Resend ticket" / "View QR" action linking to
     `registration_confirmation`.

**Acceptance criteria:** A user who registered themselves + 3 colleagues sees
their own ticket in the existing "Upcoming Events" section *and* a new
"Registrations You've Made for Others" section listing the 3 colleagues,
grouped under one heading per `group_booking_id`/`group_label`.

---

# Phase 3 — Organizer & admin attendee views (P3)

## 3.1 — `templates/events/organizer/attendees.html` has zero group awareness

**Problem:** The organizer attendee table (the file with check-in
functionality) renders `registration_ref`, `full_name`, `email`,
`ticket_type`, `status`, `checked_in_at` — nothing about
`booking_type`, `group_booking_id`, `group_label`, or `booked_by_user_id`.
Organizers cannot see who registered together, filter by group, or contact
the booker about a problematic group registration.

**Location:** `templates/events/organizer/attendees.html` (whole file);
backend route `events.event_attendees` (wherever it's defined — search
`routes.py` for the route rendering this template) for data prep.

**Goal:** Organizers can see group membership at a glance, filter to a single
group, and see who booked on whose behalf — without breaking the existing
search/status/ticket-type filters or check-in flow.

**Solution:**
1. **Backend:** ensure the `registrations` passed to this template include
   `booking_type`, `group_booking_id`, `group_label`, `group_index`, and
   `booked_by_user_id` → resolve to a display name (join/lookup the booker's
   name once per unique `booked_by_user_id`, not per row — batch this query).
   `_registration_to_dict_with_assignments` already avoids extra queries per
   row; extend it to include these fields (it currently omits
   `booking_type`/`group_booking_id` entirely — only `_registration_to_dict`
   has them).
2. **Table changes:**
   - Add a "Group" column. For rows with a `group_booking_id` shared by 2+
     rows in the current result set, render a colored badge showing a short
     group identifier (e.g. first 6 chars of `group_booking_id`, or
     `group_label` if set, truncated) plus the group size, e.g. `Acme Corp ·
     5`. Rows with no group partner in this event show `—`.
   - Add a "Booked By" column showing the booker's name/email when
     `booking_type != 'self'`, else "—" (self-registrations have no separate
     booker).
   - Add `data-group-id="{{ reg.group_booking_id or '' }}"` and
     `data-group-label="{{ (reg.group_label or '')|lower }}"` attributes to
     each `<tr>`, following the existing `data-*` pattern used for
     search/filter.
3. **Filter additions:** extend the existing filter row with a "Group" select
   populated server-side with distinct `(group_booking_id, group_label or
   short-id, count)` tuples for this event, plus an "All / Individual /
   Group bookings" toggle backed by `booking_type` (mirrors the filter
   proposed for `my_registrations`/organizer dashboards generally). Wire into
   the existing `filterTable()` JS function alongside `statusFilter`/
   `ticketFilter`.
4. **Visual grouping (optional polish, do after the above):** rows sharing a
   `group_booking_id` get a shared subtle background tint
   (`data-group-id`-keyed CSS class assigned via a small JS pass on page
   load — cycle through 4-5 tint classes by hashing `group_booking_id`) so
   they visually cluster even when the table is otherwise sorted/filtered.
5. **Bulk check-in for a group (optional, do last):** when the "Group" filter
   is active and showing exactly one group, show a "Check in entire group"
   button that POSTs each visible row's `qr_token` to the existing
   `events.api_checkin` endpoint sequentially (or add a new bulk endpoint
   accepting a list of `qr_token`s — prefer the bulk endpoint to avoid N
   round-trips for large groups).

**Acceptance criteria:** For an event with at least one group registration of
3+, the organizer attendee table shows a group badge with correct count on
those rows, a "Booked By" value for non-self rows, and the group filter
isolates exactly those rows when selected. Existing search/status/ticket-type
filters continue to work in combination with the new group filter (AND logic).

---

## 3.2 — `templates/events/admin/attendees_list.html` — apply the same treatment

**Problem:** Same gaps as 3.1, in the system-admin-facing attendee list (a
separate template from the organizer one).

**Location:** `templates/events/admin/attendees_list.html`.

**Goal:** Consistency — an admin debugging a group-registration support
ticket should see the same group/booked-by information as the organizer.

**Solution:** Once 3.1 is implemented, extract the group-badge rendering and
the "Booked By" cell into a shared Jinja macro/include (e.g.
`templates/events/_partials/attendee_group_cell.html`) and include it in both
`organizer/attendees.html` and `admin/attendees_list.html`, rather than
duplicating the markup. The admin view may additionally want a raw
`group_booking_id` (full UUID) shown on hover/tooltip for support purposes,
since admins are more likely to need to correlate with logs.

**Acceptance criteria:** Both templates render group/booked-by information via
the same shared partial; a change to the badge styling only requires editing
one file.

---

# Phase 4 — Validation, authorization, and limits (P4)

## 4.1 — Server-side cap on group size

**Problem:** The current form UI caps additional attendees at 9 via a
`<select>`, but the server trusts `group_attendees_data` as submitted — a
POST with 100+ entries would attempt 100+ sequential
`register_for_event_optimistic` calls (each its own DB transaction +
idempotency check), or, for paid events, a single
`process_ticket_purchase` with `quantity=100` against the wallet.

**Location:** `app/events/routes.py`, `events.register` POST handler, start
of group-handling logic (after Phase 0.4's normalized `attendees` list is
built).

**Goal:** A configurable hard cap on attendees-per-submission for the
*inline form* path, with a clear error if exceeded — large groups are
redirected to the bulk-upload flow (`REGISTER_FORM_REDESIGN.md`), which has
its own, higher cap and different processing strategy.

**Solution:**
1. Define `MAX_INLINE_GROUP_SIZE = 25` (or your preferred number — 25 is a
   reasonable line between "fill in a form" and "should be a spreadsheet") as
   a constant in `app/events/constants.py`.
2. At the top of group handling in `routes.py`:
   ```python
   if len(attendees) > MAX_INLINE_GROUP_SIZE:
       return jsonify({
           'success': False,
           'error': f"Groups larger than {MAX_INLINE_GROUP_SIZE} must use bulk upload. "
                    f"Please use the 'Import from spreadsheet' option."
       }), 400
   ```
3. Define a separate `MAX_BULK_GROUP_SIZE` (e.g. 500) for the bulk-upload
   endpoint introduced in `REGISTER_FORM_REDESIGN.md`.

**Acceptance criteria:** A POST with 26 attendees via the inline JSON path
returns a 400 with the message above and creates zero registrations. A POST
with 25 succeeds (assuming capacity).

---

## 4.2 — Centralize cancellation/management authorization

**Problem:** "Who can cancel/manage registration X" isn't a single checked
rule anywhere yet — it's implied by which route/template a user reaches. As
the attendee dashboard (2.2) and organizer tools (3.1) both grow the ability
to act on registrations, an inconsistent check (booker can cancel their own
ticket but not a colleague's, or vice versa, depending on which UI they used)
becomes likely.

**Location:** New helper in `app/events/services.py` or
`app/events/permissions.py` (the latter already exists per the file tree —
prefer adding it there alongside other permission helpers).

**Goal:** One function, used by every route/action that mutates or reveals a
registration's details to a non-organizer.

**Solution:**
```python
# app/events/permissions.py
def can_manage_registration(user, registration) -> bool:
    """True if `user` may view/cancel/resend this registration as its
    attendee or as the person who booked it on someone else's behalf."""
    if user is None:
        return False
    return (
        registration.user_id == user.id
        or registration.booked_by_user_id == user.id
    )
```
Apply this check in:
- The cancellation route (wherever `EventRegistration` rows can be
  cancelled/refunded by non-organizers).
- `registration_confirmation` if it currently has no ownership check (verify —
  if `reg_ref` is treated as a bearer token / QR-equivalent secret, that's a
  *different*, intentional design choice; document which it is).
- The new "Registrations You've Made for Others" actions in 2.2.

Organizer/admin routes use their own existing role-based checks
(`event.organizer_id == user.id` etc.) — `can_manage_registration` is
specifically for the attendee/booker self-service surface.

**Acceptance criteria:** A single grep for `can_manage_registration` shows it
used in every attendee-facing route that mutates a registration; no route
duplicates the `user_id == ... or booked_by_user_id == ...` condition inline.

---

## 4.3 — Discount codes in group registrations

**Problem:** `register_for_event_optimistic` applies `data.get("discount_code")`
via `validate_discount_code`. The free-event group loop in `routes.py`
constructs a fresh, minimal `data` dict per additional attendee
(`{'ticket_type_id', 'full_name', 'email', 'phone'}`) that never includes
`discount_code` — so a discount code entered by the booker silently applies
only to their own row (if `booking_type=group` for the payer counts as
"self"-like) and not to additional attendees. The paid-group path via
`process_ticket_purchase` doesn't reference `discount_code`/
`validate_discount_code` at all — discounts and group payment purchases are
currently unrelated code paths.

**Location:** `app/events/routes.py` (free-event group loop, ~line 730-755);
`app/events/payment_service.py` (`process_ticket_purchase`,
`_create_registrations`).

**Goal:** Explicit, documented behavior — recommend: **a discount code
applies per-seat** (every attendee in the batch gets the discount applied to
their `registration_fee`/the batch's per-unit price), since that matches how
`unit_price * quantity` works in `process_ticket_purchase` and is the least
surprising to a registrant who entered a "20% off" code expecting it to apply
to their whole order.

**Solution:**
1. **Free path:** when building each additional attendee's `data` dict in the
   group loop, copy `discount_code` from the top-level `data` into it, so
   `register_for_event_optimistic` applies it per-row consistently.
2. **Paid path:** before calling `process_ticket_purchase`, if
   `data.get('discount_code')` is present, call
   `EventService.validate_discount_code(identifier, discount_code,
   ticket_type_id)` once to get the per-unit `discount_amount`, then compute
   `unit_price = ticket_type.price - discount_amount` and pass this adjusted
   price basis into `process_ticket_purchase` (this likely requires a new
   parameter, e.g. `unit_price_override: Optional[Decimal] = None`, since
   `process_ticket_purchase` currently derives `unit_price` solely from
   `ticket_type.price`). Apply the same discount-amount to each
   `_create_single_registration`'s `registration_fee` for accurate per-row
   reporting.
3. Add a one-line comment at both sites: `# Discount applies per-seat — see
   REFACTOR_PLAN.md 4.3`.

**Acceptance criteria:** A group of 4 with a 20%-off discount code, on a
$10 ticket, results in: total wallet debit of `4 * $8 = $32`, and each of the
4 `event_registrations` rows has `registration_fee = 8.00` and
`discount_amount = 2.00` (or however `discount_amount` is currently scaled —
match the existing single-registration convention in
`register_for_event_optimistic`).

---

# Phase 5 — Bulk import (see companion document)

The "register 50-100+ people" case is handled by a dedicated
**Excel/CSV bulk-upload flow**, specified in full in
`REGISTER_FORM_REDESIGN.md`. That document covers:

- Template download endpoint
- Upload → server-side parse/validate → preview (with per-row errors)
- Confirm → reuses the same normalized `attendees[]` + `group_label` payload
  shape defined in Phase 1.5/1.4, so it plugs into the same
  `register_for_event_optimistic` / `process_ticket_purchase` paths — **no
  third registration-processing code path is introduced**.
- A new `MAX_BULK_GROUP_SIZE` and an async (Celery, via the existing
  `tasks.py`) path for very large files.

Do not start Phase 5 until Phases 0, 1, and 4.1 are complete — the bulk
endpoint's "confirm" step is, by design, just another caller of the
now-unified, now-capped, now-correctly-indexed group registration path.

---

# Phase 6 — Future / optional: persistent cross-batch cohorts (`AttendeeGroup`)

**Not required for this pass.** `group_label` (1.4) covers the "Department X
registers over several weeks" case via a simple shared string, which matches
how Eventbrite/Ticketmaster-style platforms actually handle this (free-text
team/company field, filterable in exports) — no relational schema needed for
v1.

If, after shipping Phases 0-5, organizers want to **manage** named cohorts
(rename, merge two `group_label`s that were typed slightly differently, move
individual attendees between cohorts, bulk-action by cohort beyond what a
string filter supports), introduce:

```python
class AttendeeGroup(BaseModel):
    __tablename__ = "event_attendee_groups"
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    created_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)

class AttendeeGroupMember(BaseModel):
    __tablename__ = "event_attendee_group_members"
    group_id = Column(BigInteger, ForeignKey("event_attendee_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    registration_id = Column(BigInteger, ForeignKey("event_registrations.id", ondelete="CASCADE"), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("group_id", "registration_id", name="uq_group_member"),)
```

Migration path: backfill is **optional** — `AttendeeGroup` rows can be created
lazily, on first organizer action, by matching distinct `group_label` values
for the event. This is purely additive and doesn't touch anything from Phases
0-5.

---

# Summary checklist for the CLI agent

- [ ] 0.1 `group_index` param on `register_for_event_optimistic`
- [ ] 0.2 Fix `_get_or_create_attendee_user` stub (paid path data corruption)
- [ ] 0.3 Free-path `group_index` wiring (after 1.5)
- [ ] 0.4 Single `group_booking_id` generation site
- [ ] 0.5 Per-attendee error handling + compensating refund on partial failure
- [ ] 1.1 `BookingType` enum, replace string literals
- [ ] 1.2 Deprecate `registered_by`
- [ ] 1.3 Document `attendee_user_id` redundancy (Option A)
- [ ] 1.4 `group_label` column + migration
- [ ] 1.5 Unified `group_index` semantics (0 = self, 1..N = others)
- [ ] 2.1 DB-fallback group view on confirmation page
- [ ] 2.2 "Registrations You've Made for Others" on `my_registrations.html`
- [ ] 3.1 Organizer `attendees.html` group badges/filter/booked-by
- [ ] 3.2 Admin `attendees_list.html` via shared partial
- [ ] 4.1 `MAX_INLINE_GROUP_SIZE` cap
- [ ] 4.2 `can_manage_registration` helper, applied everywhere
- [ ] 4.3 Discount code per-seat consistency
- [ ] 5.x See `REGISTER_FORM_REDESIGN.md`
- [ ] 6.x (optional/backlog) `AttendeeGroup` tables
Done
