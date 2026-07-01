# Accommodation Platform Architecture
## Scaling from 1 Room to 1000-Room Chains — Efficient by Design

**Status:** Proposal for review
**Scope:** Data model, inventory/availability, pricing, media, search — the pieces needed to serve an individual host and a Marriott-scale chain from the same schema without wasting storage or compute.

---

## 0. The Core Problem With the Current Design

`Property` is a single bookable unit: one price, one `max_guests`, one status. That's correct for an individual with 1 room. It cannot represent a hotel, because a hotel isn't "many independent listings" — it's **one building selling inventory against room *types***, where many physical rooms share one price/availability pool.

Every major OTA (Booking.com, Expedia, Airbnb-for-hotels, Marriott's own systems) converges on the same three-layer shape. That convergence isn't a coincidence — it's the minimum structure that supports both a single room and a 1000-room tower without duplicating logic:

```
Property (the physical building / listing)
  └─ RoomType (the sellable SKU: "Deluxe King", "Standard Twin")
       └─ Inventory (how many of this SKU exist, and how many are free per date)
```

An individual host's listing is just the degenerate case: **1 Property, 1 RoomType, 1 unit of inventory.** No special-casing needed if the model is right from the start.

---

## 1. Data Model

### 1.1 Property — the container, not the sellable thing

Keep `Property` for what it's actually good at: identity, location, policies, media, ownership. Strip out what implies "this row = one bookable thing":

- Remove the assumption baked into `max_guests`, `base_price_per_night` living directly on `Property` — these move to `RoomType`.
- Keep: title, slug, description, address/geo, cancellation policy, house rules, status/verification, owner (user or org).

```python
class Property(BaseModel):
    __tablename__ = "accommodation_properties"
    owner_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    owner_org_id = Column(BigInteger, ForeignKey("organisations.id"), nullable=True)
    title = Column(String(200), nullable=False)
    slug = Column(String(220), unique=True, nullable=False)
    property_kind = Column(String(20), nullable=False, default="single_unit")
    # 'single_unit' = individual host, 1 implicit RoomType, hides RoomType UI entirely
    # 'multi_unit'  = hotel/hostel with multiple RoomTypes
    ...
    room_types = relationship("RoomType", back_populates="property", cascade="all, delete-orphan")
```

`property_kind` is the cheap trick that keeps the UI simple for the 1-room host: when a `Property` is created, auto-provision a single default `RoomType` behind the scenes and hide the room-type management screen entirely unless `property_kind == 'multi_unit'`. The host never sees the extra layer; your backend never needs a second code path.

### 1.2 RoomType — the actual sellable SKU

```python
class RoomType(BaseModel):
    __tablename__ = "accommodation_room_types"
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(100), nullable=False)             # "Deluxe King", or the property title for single_unit
    max_guests = Column(Integer, nullable=False, default=2)
    bedrooms = Column(Integer, default=1)
    beds = Column(Integer, default=1)
    bathrooms = Column(Float, default=1.0)

    base_price_per_night = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")

    total_units = Column(Integer, nullable=False, default=1)  # 1 for a private host, 200 for a hotel wing
    is_active = Column(Boolean, default=True)

    property = relationship("Property", back_populates="room_types")
```

`total_units` is the count of interchangeable rooms of this type. This is the single most important storage decision in the whole system — see §2.

### 1.3 RoomUnit — optional, only when physical assignment matters

Most bookings never need to know *which* Deluxe King a guest gets — only that one is free. Only create per-unit rows (`RoomUnit`: room number, floor, housekeeping status) for large operators who explicitly need housekeeping/maintenance tracking. Don't generate 1000 `RoomUnit` rows just because a hotel has 1000 rooms — that's pure storage overhead with no query benefit for 95% of operations (search, pricing, booking) which only care about counts, not identities.

```python
class RoomUnit(BaseModel):
    __tablename__ = "accommodation_room_units"
    room_type_id = Column(BigInteger, ForeignKey("accommodation_room_types.id", ondelete="CASCADE"), nullable=False)
    unit_label = Column(String(50), nullable=False)   # "1204", "Cabin 3"
    housekeeping_status = Column(String(20), default="clean")
    is_out_of_service = Column(Boolean, default=False)
```

Populate this table lazily — only for organisations that opt into room-level operations (housekeeping dashboards, maintenance blocks). A CSV bulk-import for a hotel chain should create `RoomType` rows with a `total_units` count, **not** 1000 individual rows. That's the fix for the bulk-import feature your agent half-built: it's currently positioned to create 1000 `Property` rows, which is the wrong unit of import entirely.

---

## 2. Availability — Counters, Not Calendars

This is the biggest resource-efficiency decision in the system.

**The naive approach** — a row per room per night — costs you `total_units × 365` rows per property per year. A 1000-room hotel becomes 365,000 rows/year just to say "available." That's the mistake a lot of side-project OTAs make and it kills both storage and query performance as the catalog grows.

**What actual OTAs do instead:** track availability as **counts**, derived on demand, with storage only for *exceptions*.

```python
class InventoryBlock(BaseModel):
    """Sparse table — only rows for dates that are NOT default-available."""
    __tablename__ = "accommodation_inventory_blocks"
    room_type_id = Column(BigInteger, ForeignKey("accommodation_room_types.id", ondelete="CASCADE"), nullable=False, index=True)
    date_range_start = Column(Date, nullable=False)
    date_range_end = Column(Date, nullable=False)   # half-open range, not one row per day
    units_blocked = Column(Integer, nullable=False, default=0)  # e.g. 3 rooms under renovation
    reason = Column(String(30), nullable=False)  # maintenance, seasonal_close, owner_block
    __table_args__ = (Index("idx_inv_block_range", "room_type_id", "date_range_start", "date_range_end"),)
```

Availability for a given date = `room_type.total_units − confirmed_bookings_overlapping(date) − blocked_units_overlapping(date)`.

Compute this with a single indexed range query, not a per-day row scan:

```python
def available_units(room_type_id: int, check_in: date, check_out: date) -> int:
    total = RoomType.query.get(room_type_id).total_units
    booked = (
        db.session.query(func.count(AccommodationBooking.id))
        .filter(
            AccommodationBooking.room_type_id == room_type_id,
            AccommodationBooking.status.in_(ACTIVE_STATUSES),
            AccommodationBooking.check_in < check_out,
            AccommodationBooking.check_out > check_in,
        )
        .scalar()
    )
    blocked = (
        db.session.query(func.coalesce(func.sum(InventoryBlock.units_blocked), 0))
        .filter(
            InventoryBlock.room_type_id == room_type_id,
            InventoryBlock.date_range_start < check_out,
            InventoryBlock.date_range_end > check_in,
        )
        .scalar()
    )
    return total - booked - blocked
```

Storage cost for a 1000-room hotel with a typical maintenance schedule: a handful of `InventoryBlock` rows, not 365,000. Bookings themselves are the only thing that scales with volume, and they're already a necessary table.

### 2.1 Preventing overbooking under concurrency

At the moment of booking confirmation, take a row lock on the `RoomType` (or use `SELECT ... FOR UPDATE`) and re-check `available_units()` inside the transaction before writing the booking. For very high-traffic single room types (e.g., a 200-unit type during a sold-out event), a Redis `DECR`-based semaphore per `room_type_id + date-bucket` in front of Postgres avoids lock contention — decrement optimistically, fall back to a DB re-check only near zero. This is the same pattern ticketing systems use for limited-inventory drops.

---

## 3. Pricing — Rules Over Rows

Same storage principle applies to pricing. Don't store a price row per room per night. Store `base_price_per_night` on `RoomType`, and layer **date-range rate rules** on top for seasonal/weekend pricing:

```python
class RatePlan(BaseModel):
    __tablename__ = "accommodation_rate_plans"
    room_type_id = Column(BigInteger, ForeignKey("accommodation_room_types.id", ondelete="CASCADE"), nullable=False, index=True)
    date_range_start = Column(Date, nullable=False)
    date_range_end = Column(Date, nullable=False)
    price_override = Column(Numeric(10, 2), nullable=True)      # absolute override
    price_multiplier = Column(Numeric(4, 2), nullable=True)     # e.g. 1.25 for AFCON tournament week
    day_of_week_mask = Column(Integer, nullable=True)           # bitmask, weekend-only rules etc.
```

Effective price = walk overlapping `RatePlan` rows for the stay window (small, indexed, sparse) rather than materializing a price per night per room.

---

## 4. Media — Finish What's Already Built, Don't Add a Fourth System

Your `media_handling.md` describes a genuinely solid unified system: SHA-256 content-addressable dedup, async WebP variants, storage backend abstraction. The problem isn't the design — it's that `Property` still has **three parallel, unconnected photo paths**:

1. `Property.main_image` (raw URL string)
2. `Property.gallery` (JSON array of URLs)
3. `PropertyPhoto` table (its own storage_key/display_order/is_cover)
4. The new `media` table (module='accommodation') — the one with dedup and optimization

Only #4 gets deduplication, WebP conversion, and CDN URLs. Anything a host pastes into the "(Legacy)" URL fields bypasses all of it — no dedup, no compression, no lifecycle management, and it's an unvalidated external URL your app doesn't control (dead links, hotlinking issues, no virus scan).

**Fix, in order:**
1. Stop rendering the legacy `main_image` / `gallery_urls` fields in the create-listing form — they're actively undermining the system you already paid to build.
2. Migrate existing `PropertyPhoto` rows into `media` (one-time script: for each `PropertyPhoto`, create a `Media` row with `module='accommodation'`, `entity_id=property.public_id`, hash the existing file if reachable).
3. Drop `Property.main_image`, `Property.gallery`, and the `PropertyPhoto` table once migrated. Every photo query becomes `GET /api/media/entity/accommodation/<property_id>` — one source of truth, full dedup coverage, consistent optimization.

This alone likely saves meaningful storage today, since duplicate/uncompressed images are almost certainly sitting in the legacy paths right now with zero dedup protection.

---

## 5. Search & Discovery — Don't Query Booking Logic to List Properties

As the catalog grows past a few thousand properties, "find available Deluxe rooms in Kampala under $100/night for these dates" run directly against the transactional Postgres tables gets slow and starts competing with booking writes for the same rows.

Standard fix, same one Booking.com/Airbnb use: **separate read and write paths.**

- **Write path (source of truth):** Postgres — `Property`, `RoomType`, `AccommodationBooking`, `InventoryBlock`. Optimized for correctness (transactions, locks).
- **Read path (search):** a denormalized index (OpenSearch/Elasticsearch, or even a materialized Postgres view refreshed every few minutes for smaller scale) containing property + room type + computed min-available-price for common date windows. Search queries hit this, never the booking tables directly.
- Invalidate/refresh the index on booking confirmation, cancellation, price change — event-driven, not polling.

At your current stage (before real scale pain), a materialized view refreshed every 5–15 minutes is enough and avoids standing up a new service. Migrate to a real search index only when property count or query volume actually demands it — don't build it prematurely.

---

## 6. Storage/Resource Optimization Summary

| Concern | Naive approach | Efficient approach (this doc) |
|---|---|---|
| Room-level availability | 1 row/room/night | Counter (`total_units`) − sparse blocks/bookings, range-queried |
| Pricing | 1 row/room/night | Base price + sparse date-range rate rules |
| Hotel photos | 3–4 separate storage paths, no dedup on legacy paths | Single `media` table, SHA-256 dedup, WebP, already built — just needs the legacy paths deleted |
| Bulk hotel import | 1000 `Property` rows | 1 `Property` + N `RoomType` rows with `total_units` |
| Physical room tracking | Always-on `RoomUnit` per room | Lazy, opt-in, only for orgs that need housekeeping ops |
| Search at scale | Query booking tables directly | Denormalized read index, refreshed async |
| Overbooking prevention | Optimistic writes, hope for the best | Row lock + re-check in transaction, Redis semaphore for hot inventory |

---

## 7. Migration Path (Incremental, No Big-Bang Rewrite)

1. **Add `RoomType` table.** Backfill: for every existing `Property`, create one `RoomType` with `total_units=1` and copy over `max_guests`/`base_price_per_night`. Set `property_kind='single_unit'`.
2. **Update `AccommodationBooking`** to reference `room_type_id` instead of (or alongside, during transition) `property_id`.
3. **Rewrite `HostService.create_property`** to also create the default `RoomType` transactionally.
4. **Build the real `RoomType` management UI** for `property_kind='multi_unit'` hosts — this replaces the cosmetic Section 8 the agent added without backend support.
5. **Fix bulk import** to create `RoomType` rows (with counts), not 1000 `Property` rows.
6. **Add `InventoryBlock`** for maintenance/seasonal blocking, replacing any per-day blocked-date explosion.
7. **Migrate photos** into the unified `media` table; delete legacy fields.
8. **Only once catalog/query volume justifies it:** stand up the denormalized search index.

Each step ships independently and keeps the app working throughout — no downtime migration required.

---

## 8. Amendment — Multi-Location Chains (Confirms §1–§7, No Changes to Them)

This section answers directly: **does the model in §1–§7 already support one brand operating many hotels in many cities?** Yes, via `owner_org_id` — this section just makes the pattern explicit and closes two gaps (bulk import shape, per-location staff).

### 8.1 One Organisation → Many Properties → Many RoomTypes

No new table needed. The chain-level entity is the `Organisation` you already have; a "location" is just a `Property` row scoped to it:

```
Organisation "Marriott"
  ├─ Property "Marriott Kampala"      (owner_org_id = marriott.id)
  │    ├─ RoomType "Standard King"   (total_units = 400)
  │    ├─ RoomType "Deluxe Suite"    (total_units = 120)
  │    └─ RoomType "Executive Floor" (total_units = 80)
  ├─ Property "Marriott Nairobi"      (owner_org_id = marriott.id)
  │    ├─ RoomType "Standard King"
  │    └─ RoomType "Deluxe Suite"
  └─ Property "Marriott Lagos"        (owner_org_id = marriott.id)
       └─ ...
```

`HostService.get_dashboard_data(owner_org_id=...)` already aggregates across every `Property` owned by an org (see the existing `property_query.filter(Property.owner_org_id == owner_org_id)` in `host_service.py`) — so the chain-wide dashboard, revenue rollup, and occupancy stats you already have work unmodified across locations. Nothing in §1–§7 needs touching for this to be true.

### 8.2 Bulk CSV Import — Correct Shape for Multi-Location

The gap: a CSV importer for a chain needs to create **locations and their room types together**, not a flat list of 1000 identical rows. Row shape:

```csv
location_name,city,country,room_type_name,total_units,base_price_per_night,max_guests
Marriott Kampala,Kampala,UG,Standard King,400,120.00,2
Marriott Kampala,Kampala,UG,Deluxe Suite,120,220.00,3
Marriott Nairobi,Nairobi,KE,Standard King,350,110.00,2
```

Import logic: group rows by `(location_name, city, country)` → one `Property` per group (`get_or_create`, `owner_org_id` = the importing org, `property_kind='multi_unit'`) → one `RoomType` per row within that group. This is a small addition to whatever CSV handler the bulk-import route ends up calling — it does not change `RoomType`, `Property`, or the availability logic in §2 at all.

### 8.3 Per-Location Staff (Optional — Add Only If Needed)

Not required for the model to work, but chains this size usually need "this manager only sees the Nairobi property," not full org-wide access. If/when that's needed, it's one small join table — additive, doesn't touch anything above:

```python
class PropertyStaffAssignment(BaseModel):
    __tablename__ = "accommodation_property_staff"
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(30), nullable=False, default="manager")  # manager, front_desk, housekeeping
    __table_args__ = (UniqueConstraint("property_id", "user_id", name="uq_property_staff"),)
```

Skip this until an org actually asks for scoped staff access — org owners can manage all their locations directly until then.
