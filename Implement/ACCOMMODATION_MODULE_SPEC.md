
# AFCON360 Accommodation Module — Tuning Spec (Existing System → Envisioned Product)

**Prepared as:** a tuning plan, not a rebuild plan. The system already has the
right bones — this document maps the gap between what's built and the
marketplace we've envisioned (single room → international chain), and lays
out the specific adjustments to close it.
**Status of this document:** based only on files actually read and verified
against source. Every finding below is either confirmed against real code, or
explicitly marked unverified. Nothing in here repeats unverified claims from
prior AI-generated reports without saying so.

---

## 0. Mandate

**This is a tuning exercise, not a build-from-scratch exercise.** The
`RoomType` model, the `Room`/`RoomCategory` models, `AvailabilityService`,
`PricingService`, the booking model's `room_type_id`/`assigned_room_id`/
`RoomBooking` linkage, and the org-level dashboard aggregation **all already
exist and are correctly designed** — they already match the shape of the
product we want. What's missing is a small number of connection points
between pieces that were never wired to each other (§3.1, §3.2), plus some
duplicated/dead code left over from earlier passes (§3.4, §3.9). Only one
piece of this document describes something genuinely absent: the
facility/add-on model (§5.5). Everything else is tuning — taking an engine
that's already assembled correctly and connecting the last few wires so it
runs the way it was designed to.

The target we're tuning toward: a **booking marketplace**, not a hotel
operations system (PMS). Hosts do not run day-to-day hotel operations through
this — no housekeeping shift management, no night audit, no folio accounting.
The system's job: let anyone from a single homeowner to an international
hotel chain **list**, get **discovered**, and get **booked**, reliably, with
correct pricing and correct inventory counts, at any scale.

### The four scenarios this must serve
1. **Single room, homeowner** — one room, one price, may be free or paid (Airbnb single-room case).
2. **Small hotel/lodge, 1 or a few room types** — several categories, each with a handful of units.
3. **Hotel with many categories** — ordinary → VIP, host-defined, arbitrary count.
4. **Multi-location chain** — same brand, many properties, many countries, needs
   cross-property reporting and management.
5. **Bookable facilities/add-ons** — gym, pool, conference/event space — attached to
   a property but not part of room inventory.

---

## 1. The Envisioned Product's Data Model (target we're tuning toward)

```
Organisation (chain-level identity — for scenario 4 only)
   └── Property (one physical address / building / compound)
         ├── RoomType   (the sellable SKU — "Deluxe King", or the whole unit
         │                for a single-room listing)
         │     ├── total_units   ← MUST be derived from real inventory, never hand-typed
         │     ├── base_price_per_night, currency, fees
         │     └── InventoryBlock (date-range holds: maintenance, seasonal, owner block)
         │
         ├── Room        (physical instance — Room 101, Suite A — OPTIONAL layer,
         │                only needed once you want to track individual units,
         │                housekeeping status, or assign a specific room at check-in)
         │     └── belongs to exactly one RoomType via RoomCategory/RoomType link
         │
         ├── Facility / Add-on   (gym, pool, conference room — separate model,
         │                         NOT part of room inventory, own booking rules)
         │
         └── Booking → targets a RoomType (required), optionally assigned a
               specific Room afterward (RoomBooking junction — already exists
               and is correctly designed, see §3.1)
```

**Key rule going forward:** `RoomType.total_units` is a *fact derived from* the count
of active `Room` rows under it (when the Room layer is used), or a host-set number
(when the host doesn't want to track individual physical rooms — the single-room
case, or a big hotel that just wants "50 units" without naming each one). Either
way, **the number guests see availability against must never silently disagree
with what the host actually has.**

---

## 2. Executive Summary — Where Things Actually Stand

**Confidence in this number: high, based on direct source inspection, not vibes.**

| Area | Assessment |
|---|---|
| Breadth of features attempted | Wide — analytics, KYC, wallet, moderation, calendar, multiple payment processors, and a long tail of speculative features (see §4.6) |
| Correctness of the **core loop** (list → discover → book → pay) | **Broken in at least 6 independent, confirmed ways** (§3) |
| Schema design intent | Mostly *correct* once fully traced — RoomType/Room/Booking relationships are properly linked in the models (§3.1). The bugs are missing glue code and dead legacy paths, not a wrong design. |
| Migration integrity | **Confirmed conflict** — two migrations branch from the same parent revision (§3.7) |
| Prior "deployment readiness" documentation | **Fabricated / not grounded in the code.** Discard entirely (§3.8). |
| Estimated readiness | **~15–20%** of the way to a trustworthy core booking loop. Breadth is not the bottleneck; correctness of the path every user actually needs is. |

---

## 3. Confirmed Findings (verified against source, file + line referenced)

Severity key: 🔴 blocks core loop · 🟠 will cause real incidents in production · 🟡 sloppy/latent risk

### 3.1 RoomType ↔ Room relationship — design is correct, sync glue is missing 🔴
- `AccommodationBooking` has both `room_type_id` (FK → `RoomType`) and
  `assigned_room_id` (FK → `Room`), plus a `RoomBooking` junction table
  (`room.py`) linking booking ↔ specific physical room with its own
  check-in/out. **This is the right design** — book a SKU, assign a physical
  unit later.
- **The gap:** `HostService.create_property()` (`host_service.py:152-170`)
  auto-creates exactly one `RoomType` with `total_units=1` for every new
  property. Nothing in `host_room_category_add()` / `host_room_add()`
  (`routes.py:2206-2348`, which create `RoomCategory`/`Room` rows) ever
  touches `RoomType.total_units`. Result: **every property is permanently
  capped at 1 bookable unit**, regardless of how many rooms the host adds
  through the working host UI.
- **Confirmed independently** by `test_accommodation_roomtype.py`, which has
  to manually do `rt.total_units = 5` to simulate a hotel — proof no code
  path does this automatically today.

### 3.2 Create-listing form has dead fields 🔴
- `create_listing.html` has an entire "Room Types" UI section
  (`room_type_name[]`, `room_type_price[]`, `room_type_max_guests[]`,
  `total_rooms`, `available_rooms`, `maintenance_rooms`) that is **not bound
  to `PropertyForm`** and is never read anywhere in `host_create_listing()`
  (`routes.py:1748`). Confirmed by grepping the entire `routes.py` for every
  one of these field names — zero hits outside the CSV bulk-template string.
  Whatever a host types there is silently discarded.

### 3.3 Guest-facing property lookup can serve fake data instead of 404ing 🔴
- `search_service.get_property_by_identifier()` only returns a real property
  if `status == "active" and is_verified`. If that check fails, it **falls
  through to `HARDCODED_PROPERTIES`** (a hardcoded demo fixture with ids `1`
  and `2`). So a real, unapproved property with id `1` or `2` doesn't 404 —
  it silently masquerades as "Central Hotel" / "Riverside Lodge" demo data.
  Only ids ≥3 (or non-matching slugs) reveal the real pending-review 404.
  **This means testing against ids 1/2 in this system cannot be trusted at
  all** until this is fixed.
- Same file: the `except` block calls `db.session.rollback()` but `db` is
  never imported in `search_service.py` — will raise `NameError` and mask
  the real exception if this path is ever hit.

### 3.4 Dead/duplicate legacy availability logic, with a fatal import bug 🔴
- `models/availability.py` has its own module-level `is_date_available()`,
  which imports `from app.accommodation.models.booking import
  AccommodationBookingStatus, Booking`. **There is no class named `Booking`**
  in `booking.py` — the real class is `AccommodationBooking`. This import
  will raise `ImportError` the instant this function is called.
- It's not dead code: `AccommodationBooking.is_available()` (`booking.py:355`)
  calls this exact function. Any caller of `booking.is_available()` will
  crash.
- Even ignoring the crash, this legacy function has **zero concept of
  multiple units** — it treats "any overlapping confirmed booking" as "date
  fully unavailable," which is wrong for anything with >1 room. The correct,
  unit-aware version already exists at
  `services/availability_service.py: AvailabilityService.is_date_available()`.
  **Action: delete the legacy functions in `models/availability.py`
  (`is_date_available`, `get_available_dates`, `block_dates`,
  `unblock_dates`), keep only the `BlockedDate`/`AvailabilityRule` data
  models.**

### 3.5 Media dedup is not scoped per-property 🟠
- `MediaService.upload_photo()` dedup check (`service.py`, step 6) matches
  on `sha256_hash` + `module` only — **no `entity_id` filter**. Uploading
  the same photo to two different properties (very likely for a chain host
  reusing stock photography) silently returns the *first* property's media
  record. The second property's gallery never gets the photo, with no error
  surfaced to the host.
- `file_size = file.content_length or 0` (`service.py`, step 2) trusts a
  header that many clients don't reliably set — could silently zero out
  quota enforcement and storage accounting. Needs verification against a
  real upload, not just code reading.
- Files are saved to storage *before* the DB row commits, with no cleanup
  path if the Celery task queueing or the commit fails — orphaned files
  accumulate with no sweep job.

### 3.6 Admin "Preview" button doesn't work for the properties it exists to review 🟠
- `admin_verification.html`'s Preview link points at
  `guest_detail(identifier=prop.id)` — the exact function gated by the
  broken/masking lookup in §3.3. Previewing a pending property with id 1/2
  shows fake demo data; previewing any other pending id 404s. The one
  screen whose entire purpose is "let an admin look at a pending listing
  before approving it" cannot actually do that reliably.

### 3.7 Two Alembic migrations branch from the same parent revision 🔴
- `1d30290f4f67_add_room_types_and_inventory_blocks_.py` and
  `20260701_add_room_types_and_inventory_blocks.py` both declare
  `down_revision = 'a976e4599bfe'`. Unless a merge migration exists that
  references both (none found in the tree provided), this is an unresolved
  multi-head state — `alembic upgrade head` will likely refuse to run.
  **Needs verification: run `alembic heads` directly against the repo.**
- `1d30290f4f67` is also a large, unreviewed "please adjust!" autogenerate
  dump that bundles unrelated schema changes (media settings column
  renames/drops, payment_provider_configs, wallet_system_configs) into a
  migration nominally about room types. This makes it hard to trust what
  state the DB schema is actually in without a direct inspection.

### 3.8 Existing "deployment readiness" documentation is not credible 🔴 (documentation risk, not code risk)
- `DEPLOYMENT_READINESS_ASSESSMENT.md` claims 9.2/10 "EXCELLENT," full OWASP/
  ISO 27001/SOC 2/PCI DSS compliance, "GO — IMMEDIATE" deployment
  recommendation, and specific competitive benchmarks against Stripe/PayPal/
  Square/Revolut. **None of this is reconcilable with the confirmed findings
  above.** Treat this document as fabricated template output, not an audit
  grounded in this codebase. Do not let it influence any go/no-go decision.
- A separate AI-generated status report (referred to here as "Kilo's
  report") was independently checked against source in this audit and found
  **partially accurate** (media pipeline description checks out) but
  **materially wrong on the single most important point** — it described
  `RoomCategory` as if it were `RoomType`, erasing the actual root cause of
  the "can't see my rooms" bug. Any future AI-generated report on this repo
  should be spot-checked against actual source the same way, not trusted
  on its own authority.

### 3.9 Structural / hygiene issues visible from the repo tree, not yet individually verified 🟡
- `app/accommodation/routes.py` **and** `routes_old.py` both exist in the
  live package — confirm nothing imports the old one.
- `app/accommodation/services.py` (single file) **and**
  `app/accommodation/services/` (package) coexist — this is a real Python
  import-shadowing risk and needs resolving, not just noting.
- `app/accommodation/event_listeners.py` **and** `listeners.py` — likely
  duplicate, needs reading both to confirm which is live.
- `backups_today/accommodation/` — a second copy of `routes.py`/`services.py`
  sitting inside the app tree (not `.git` history). Confirm it's excluded
  from the Python path.

---

## 4. What Still Needs Verification (files not yet read — there are many)

This audit is **not complete**. The following are known gaps, not assumed-fine:

- `app/accommodation/services/booking_service.py` — the actual booking
  creation/confirmation flow; referenced constantly but never read directly.
- `app/accommodation/models/wishlist.py`, `models/review.py` — untouched.
- `app/identity/models/organisation.py` — the `Organisation` model itself;
  we've only seen `owner_org_id` used correctly as a foreign key, never the
  model it points to, or whether chain-level branding/settings exist.
- `app/admin/route_modules/org_admin.py`, `org_member.py` — the actual
  chain-management UI, if any exists.
- `app/media/tasks.py`, `media/utils/virus_scanner.py`,
  `media/utils/quota_manager.py`, `media/utils/perceptual_hash.py`,
  `media/models.py`, `media/routes.py`, `media/settings_service.py` — the
  async processing, quota, virus-scan, and moderation implementations
  themselves (only the calling code in `service.py` has been read).
- `app/accommodation/services/identity_service.py`,
  `payment_processors/*.py`, `wallet_service.py`, `payment_policy_service.py`
  — the actual payment execution paths.
- `app/accommodation/routes_old.py`, the loose `services.py`,
  `event_listeners.py` vs `listeners.py` — need reading to confirm which
  are dead vs. live, per §3.9.
- The ten "speculative" services (`ai_search_service.py`,
  `ai_trip_planner_service.py`, `blockchain_reviews_service.py`,
  `competitive_intelligence_service.py`, `dynamic_pricing_service.py`,
  `gamified_loyalty_service.py`, `hyper_personalization_service.py`,
  `immersive_tour_service.py`, `predictive_availability_service.py`,
  `voice_booking_service.py`) — unread. Recommendation below is to
  **deprioritize reading these until the core loop is fixed** — they cannot
  matter if the basic booking path doesn't work.
- Full `accommodation/` template set (guest detail, host dashboard, calendar,
  booking flow templates) — only `create_listing.html`, `edit_listing.html`,
  and `admin/verification.html` have been read.
- `booking_forms.py` (in `app/forms/`) — unread; unclear if it duplicates or
  supplements anything in `accommodation/forms.py`.
- Confirm the actual Alembic head state (`alembic heads`) — cannot be
  determined from static file reading alone.

**Do not assume anything in this list is fine. Read it, check it against
source the way every finding above was checked, before building on top of
it.**

---

## 5. Desired Flows (target state)

### 5.1 Host — single room (Airbnb-style)
1. Host fills create-listing form once. `RoomType` auto-created with
   `total_units=1`, correctly reflecting "this is the whole listing."
2. Price can be `0` — pricing/payment code must tolerate a free stay
   (deposit/guarantee logic should simply skip charging).
3. Submitted → `pending_review`. Host sees it in their dashboard as pending,
   with a working preview link that actually shows their real data (fixes §3.3, §3.6).
4. Admin approves → live. Guest search/detail pages show it correctly.

### 5.2 Host — small hotel, 1–3 room types
1. Host creates property (as above).
2. Host uses the **existing** `host_room_category_add()`/`host_room_add()`
   flow — this already works end-to-end for creating `RoomCategory`/`Room`
   rows — but that flow now also keeps the matching `RoomType.total_units`
   correct (the one-line fix from §6 P0-1). No new screen is required to
   unblock this; a purpose-built "Manage Room Types" UI is a UX
   improvement, not a prerequisite.
3. `total_units` remains the source of truth for guest-facing availability
   regardless of whether individual physical rooms are tracked — that part
   of the design (`AvailabilityService`, `PricingService`) already works
   correctly and needs no changes once §6 P0-1 is done.

### 5.3 Host — large hotel, many categories, ordinary → VIP
- Same as 5.2, just more `RoomType` rows, host-defined names/prices/units
  freely. No schema change needed beyond fixing the UI-to-`RoomType` wiring.

### 5.4 Host — multi-location chain
1. Org-level host account (`owner_org_id`) lists multiple properties, each
   with their own `RoomType`s.
2. Org dashboard (`get_dashboard_data`, `get_advanced_analytics` — already
   correctly aggregate by `owner_org_id`, confirmed in `host_service.py`)
   shows cross-property revenue, occupancy, bookings.
3. **Needed, not yet found:** a UI surface for actually switching between/
   managing multiple properties as an org host (the calendar page already
   supports a property-switcher dropdown — confirm this pattern is
   consistent across all host screens, or extend it).

### 5.5 Facilities/add-ons (gym, pool, conference space)
- New `PropertyFacility` model: `property_id`, `name`, `type` (amenity /
  bookable), `is_bookable`, `capacity`, pricing if applicable.
- If bookable with a time dimension (conference room by the hour), a
  lightweight separate slot-booking table — **do not** reuse `RoomType`/
  `Room` for this; conflating "sellable room-night SKU" with "hourly meeting
  room" recreates the exact kind of confusion this audit just spent many
  turns untangling.

### 5.6 Guest — search, view, book
1. Search/explore pages already correctly filter to `active` + `verified`
   (confirmed correct in `search_service.py`, `explore_search_api`).
2. Detail page availability/pricing already correctly prefers `RoomType`
   when present (confirmed in `guest_detail()`, `PricingService`,
   `AvailabilityService`) — **once §3.1 is fixed, this whole downstream
   chain should work with no further changes.**
3. Booking targets a `RoomType`; physical `Room` assignment (if used) happens
   after confirmation via the existing `RoomBooking` junction — no new model
   needed, just confirm `booking_service.py` actually does this (unverified,
   §4).

---

## 6. Prioritized Tuning Plan

**P0 — blocks the core loop, fix first**
1. Sync `RoomType.total_units` to real inventory. Cheapest fix: have
   `host_room_add`/`host_room_category_add` (both already exist and already
   work — routes.py:2206-2348) also update the matching `RoomType.total_units`
   after each add/delete. No new screen strictly required — this can be a
   few lines added to code that already runs. A dedicated "Manage Room
   Types" screen (§5.2) is a nicer UX, not a requirement to unblock the bug.
2. Fix `get_property_by_identifier()` fallback logic — only serve hardcoded
   data when `prop is None`, never when a real property exists but fails
   the status check. Add the missing `db` import.
3. Delete the legacy duplicate availability functions in
   `models/availability.py` (broken import, unit-blind logic superseded by
   `AvailabilityService`).
4. Resolve the migration head conflict (§3.7) — verify with `alembic heads`,
   write a proper merge migration if needed.
5. Wire the create-listing form's room-type fields to something real, or
   remove them and point hosts at the new Manage Room Types screen instead
   of leaving dead inputs in production.

**P1 — will cause real incidents, fix soon after**
6. Scope media dedup to `entity_id`, not just `module`.
7. Verify `file.content_length` reliability for quota enforcement; fix if
   it's silently zeroing.
8. Confirm/resolve the `routes.py` vs `routes_old.py` and
   `services.py` vs `services/` ambiguities (§3.9).

**P2 — needed for full scenario coverage, not blocking core loop**
9. Build the `PropertyFacility`/add-on model (§5.5) — doesn't exist at all
   today.
10. Confirm/build proper multi-property switching UI for org hosts across
    all host screens, not just calendar.
11. Read and verify everything in §4 before assuming any of it is fine.

---

## 7. Definition of Done for "core loop trustworthy"

- [ ] A host can create a listing with N room types, each with a correct
      unit count, and that count reflects reality without manual DB edits.
- [ ] A guest can find, view, and book any approved listing — including
      ids that happen to collide with old demo/fixture data — and always
      see real data or a real 404, never a masked fake.
- [ ] `alembic upgrade head` runs cleanly with a single head.
- [ ] No code path in the accommodation module throws `ImportError` or
      `NameError` under normal operation (both confirmed instances fixed).
- [ ] An admin can preview *any* pending listing and see its real content.
- [ ] Uploading the same photo to two different properties results in two
      distinct, correctly-attached media records.
- [ ] A single-room host, a 3-room-type lodge, a many-category hotel, and a
      multi-property chain host can all complete listing creation through
      to a live, bookable, correctly-priced listing without any manual
      database intervention.

---

*This document reflects only what has been directly verified against source
in this audit. Where a claim is marked unverified, treat it as unknown, not
as reassurance.*
