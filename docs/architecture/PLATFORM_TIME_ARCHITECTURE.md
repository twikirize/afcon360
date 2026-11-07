# AFCON360 Platform Time Architecture

**Status:** Active platform standard  
**Applies to:** all application modules, APIs, migrations, workers, reports and user interfaces  
**Effective branch:** UTC / business-calendar harmonisation (PR #52)

## 1. The three layers

AFCON360 uses three distinct time concepts. They must not be collapsed into one global timezone.

| Layer | Authority | Examples |
|---|---|---|
| Technical instant | UTC | transaction completion, audit event, booking creation, API event timestamp, Celery execution timestamp |
| Business calendar | Explicit IANA timezone belonging to the process or physical service location | KYC/AML day, property check-in date, event day, scheduled pickup |
| Display | Business context first, then user preference, then browser | driver dashboard, guest itinerary, personal history, admin report |

**UTC answers “when did this happen?” The business timezone answers “which local calendar day governs this decision?” The display timezone answers “what clock should this person see?”**

## 2. Technical instant — UTC only

- All instant-valued database columns use PostgreSQL `TIMESTAMPTZ` / SQLAlchemy `DateTime(timezone=True)`.
- Application values are aware UTC datetimes. Use `datetime.now(timezone.utc)`; never use a naive value as an instant.
- Application SQLAlchemy PostgreSQL connections, Alembic online connections and the tracked PostgreSQL service enforce UTC. The engine fails closed if a new PostgreSQL connection is not UTC.
- Celery and inter-service event ordering use UTC.
- Correct existing instants are not shifted when changing connection or server timezone. A different session timezone may change the rendered offset, but not the underlying instant.
- Standalone database clients do not inherit Flask engine options. They must use an explicitly verified UTC server default or set `PGTZ=UTC`.

**Never use the PostgreSQL session timezone to decide a business date.**

## 3. Calendar dates are not instants

Keep calendar-only concepts as SQL `DATE` values:

- accommodation `check_in` and `check_out`;
- event `start_date` and `end_date`;
- date of birth and other genuine calendar dates.

Do not convert these fields to UTC or attach an offset. A local service time such as “property check-in at 14:00” is separate from its check-in date. Where a scheduled local time must be a real-world instant, resolve it in the responsible location's IANA zone and store the resulting UTC instant plus its local scheduling provenance.

## 4. Business-calendar timezone authority

A business calendar must name the IANA timezone that governs it. Browser timezone, device timezone, IP geolocation and the application's host OS timezone are never business authorities.

| Process | Governing timezone source | AFCON360 implementation |
|---|---|---|
| KYC daily/monthly cumulative limits | Account regulatory jurisdiction or explicit product policy | `JurisdictionProfile.timezone_name`; resolver uses regulatory account metadata / latest verified KYC jurisdiction and then the configured product default |
| AML / CTR / structuring aggregation | Regulatory reporting jurisdiction | `JurisdictionProfile.timezone_name` |
| Transport scheduled pickup | Physical pickup point | Server resolves IANA zone from validated pickup coordinates using the offline timezone boundary dataset |
| Accommodation availability, check-in and check-out | Property location | `Property.timezone_name`, with safe coordinate/country resolution |
| Event lifecycle and registration calendar | Venue location | `Event.timezone_name`, with a safe country default only where unambiguous |
| System/regulator/financial reports | Explicit report configuration or requested report zone | `REGULATOR_REPORT_TIMEZONE`, `EVENT_REPORT_TIMEZONE`, `ACCOMMODATION_REPORT_TIMEZONE` |

### Country and location resolution

The location resolver applies this order:

1. Explicit, validated IANA timezone.
2. Validated WGS84 latitude/longitude resolved against the packaged timezone boundary data.
3. A country default only when the supported country mapping has one suitable timezone.
4. Otherwise return a configuration error. Do not guess.

Countries spanning multiple timezones (for example, the United States, Canada and Australia) require precise coordinates or an explicit IANA name. A country code alone is not enough.

For legacy property/event records, migrations backfill from proven coordinates or safe single-zone country defaults. Records without sufficient evidence remain unconfigured for owner/admin correction. No existing booking or event calendar date is reinterpreted by the timezone-column migration.

## 5. Day and month boundaries

Use the shared helpers in `app/utils/time_policy.py`:

- `local_day_utc_bounds(day, timezone_name)`
- `local_month_utc_bounds(day, timezone_name)`

They return UTC boundaries for a local calendar period. Query an instant column using a half-open interval:

```python
start_utc, end_utc = local_day_utc_bounds(business_day, timezone_name)

query = query.filter(
    Model.created_at >= start_utc,
    Model.created_at < end_utc,
)
```

The half-open interval `[start, end)` avoids double-counting a transaction at adjacent report boundaries and can use an index on the timestamp column.

Do not introduce:

- `date.today()` for a business decision without first deriving the relevant business timezone;
- bare `func.date(timestamptz_column)` for KYC, AML or local reporting;
- `AT TIME ZONE` with an implicit or assumed timezone;
- new global `APP_TZ` assumptions.

If SQL date grouping is genuinely required, apply the explicitly selected zone first, for example:

```sql
(created_at AT TIME ZONE 'Africa/Kampala')::date
```

For filtering a known local day, prefer UTC range boundaries instead of wrapping the timestamp column in a SQL date function.

## 6. Transport scheduling contract

For a new scheduled ride:

1. The client submits the selected local wall time and validated pickup location coordinates.
2. The server resolves the pickup point's IANA timezone. The browser's timezone is ignored.
3. The server rejects nonexistent or ambiguous DST wall times. If the request includes an offset, the offset must agree with the location's IANA zone at that instant.
4. The service converts the wall time into an aware UTC instant and persists it as the booking/request pickup instant.
5. It also retains the original local wall time, IANA timezone and resolved UTC offset in the booking/request's `pickup_schedule` metadata for audit and display.
6. The 15-minute lead-time rule compares the resolved UTC instant with server request-receipt time.

Instant rides use server-side UTC request time. Client-supplied time is not trusted to determine arrival.

Driver and admin displays render pickup time in the pickup location's timezone. When the viewer is elsewhere, show the viewer's timezone alongside it where useful.

**Existing bookings are never reinterpreted.** For legacy bookings without saved schedule provenance, derive a display zone from their saved pickup coordinates where possible; do not change their stored UTC instant. If the location cannot be resolved, label the timestamp explicitly as UTC instead of inventing a local zone.

## 7. Accommodation and event contracts

### Accommodation

- `Property.timezone_name` is the business calendar for that property.
- Property-local dates govern availability activity, inventory occupancy, check-in readiness, check-in authorization, booking date amendments and stay completion/review eligibility.
- Host and admin property forms expose an IANA timezone setting. Multi-timezone countries require an explicit timezone or precise coordinates.
- If a legacy property's zone cannot be resolved, fail closed for date-sensitive check-in/inventory actions. Do not silently use the server date.

### Events

- `Event.timezone_name` governs event start/end calendar dates, event expiry and registration/ticket availability.
- `start_date` and `end_date` remain `DATE`; venue-local registration/ticket windows are resolved to UTC instants.
- If no registration close instant is specified, the default cutoff is venue-local midnight on the event start date, converted to UTC.
- A timezone change does not shift existing registration deadline instants. An organizer changes the zone, saves, then reopens the event to edit deadlines in the new local timezone.
- An event with an unresolved multi-timezone venue is not opened for registration until its timezone is configured.

## 8. Display precedence

For a rendered instant, use:

1. Relevant business context (pickup, property, venue or selected report timezone).
2. User profile `preferred_timezone`.
3. Browser timezone.
4. UTC fallback.

The user preference is for personal history and general user views. It must never override the pickup/property/venue timezone governing an actual service.

Show both business-local and viewer-local times when the difference is operationally useful. Label zone abbreviations and/or the location when ambiguity is possible. The shared `static/js/global/timezone-display.js` formats offset-bearing instants; it does not alter persisted values or scheduling decisions.

## 9. Configuration

- `KYC_DEFAULT_JURISDICTION_CODE`: explicit product-policy fallback for KYC jurisdiction resolution; current default is `UG`.
- `REGULATOR_REPORT_TIMEZONE`: regulator reporting calendar; default `UTC`.
- `EVENT_REPORT_TIMEZONE`: system-wide event reporting calendar; default `UTC`.
- `ACCOMMODATION_REPORT_TIMEZONE`: platform-wide accommodation analytics calendar; default `UTC`.

Per-event and per-jurisdiction reports use the timezone stored on the event or jurisdiction profile, or an explicit report override.

There is no global `APP_TZ` for new business scheduling.

## 10. Migration and release safeguards

- Timezone metadata migrations add nullable columns, backfill only when the source location evidence is adequate and do not shift event dates or stored instants.
- Never convert date-only columns to timestamps as part of timezone harmonisation.
- Do not modify existing UTC instants just to change their displayed offset.
- Run migrations against a clean, disposable PostgreSQL database and prove Alembic reaches head without `stamp`.
- Test the Kampala midnight boundary (21:00 UTC), month-end, DST gap/fold behavior in a DST-observing zone, and a location in a multi-zone country.
- Run the UTC policy, KYC/AML boundary, transport request-first, mobile-auth and public-site navigation PostgreSQL workflows before merge.
- Do not merge while a relevant regression workflow is red or unexplained.

## 11. Code ownership and enforcement

Shared conversion functions live in `app/utils/time_policy.py`; location resolution lives in `app/utils/location_timezone.py`. Domain models/services own the source of business timezone. Templates and the display helper format already-resolved instants only.

Any new “today”, “this week”, “month start”, scheduled wall time or daily aggregate must state the governing timezone in code and tests. A future code review should reject implicit host/session/browser timezone usage in business logic.
