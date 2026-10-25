# AFCON360 Timestamp Semantics Register

**Status:** partial source-level classification; no database columns are approved for conversion.  
**Scope:** the timezone draft branch only. This register does not authorize migrations or production changes.

## 1. The active migration graph is a separate blocker

The source files in `migrations/versions/` currently declare this graph:

```text
h3a20261020 (down_revision=None)
  └─ c076b257b11d
       └─ 1792869659
            └─ tza20261025
```

The parent declaration for `tza20261025` is consistent with the immediately preceding active revision `1792869659`; it must not be rewritten to `df55cbe3f516` merely to match a reported database state.

However, this does **not** establish that the deployed databases can traverse this graph. The previously recorded database checkpoint `df55cbe3f516` has its migration file under `migrations/_retired_versions/`, not `migrations/versions/`. The active H3 baseline is located in `migrations/versions/h3a20261020_static_baseline.py`, declares `down_revision = None`, and its docstring still says it is isolated under `migrations/h3_candidate` and is not the active application chain. File location and revision declarations make it part of the active Alembic graph, despite that docstring.

**Required:** run the source-only lineage auditor, then reconcile the active baseline with the database's actual `alembic_version`, physical schema, and approved H3 cutover record. Do not run `flask db upgrade`, stamp a revision, or edit the active H3 chain as part of this timezone task. A graph that is structurally connected is not proof that the target database is compatible with it.

Read-only source audit:

```powershell
python scripts/audit_timezone_migration_lineage.py
python scripts/audit_timezone_migration_lineage.py --database-revision df55cbe3f516
```

The second command is expected to report that `df55cbe3f516` is not in the active graph based on the currently tracked source. A nonzero result is a blocker report, not a database failure.

## 2. Column semantic classifications supported by source evidence

| Field / path | Source evidence | Classification now | Conversion disposition |
|---|---|---|---|
| `accommodation_bookings.check_in`, `check_out` | `app/accommodation/models/booking.py` declares these as SQLAlchemy `Date`, and booking indexes/checks treat them as calendar dates. | **Calendar dates, not timestamps.** | Excluded from the timestamp-column migration. Do not shift through UTC. |
| `server_sessions.expires_at` | `app/auth/sessions.py` declares `DateTime(timezone=True)`; its writer uses `datetime.now(timezone.utc) + timedelta(...)`. But `c076b257b11d` creates this physical column with `sa.DateTime()` (without timezone). | **Absolute instant by current writer semantics; model/migration schema mismatch confirmed in source. Historical row semantics unproven.** | Not approved for conversion until target inventory and historical values/writers are reviewed. |
| `server_sessions.created_at`, `updated_at` | `c076b257b11d` creates them as timezone-naive with `server_default=now()`; `ServerSession` inherits the timestamp mixin, whose current Python-side defaults use aware UTC. | **Intended lifecycle instants; historical database-default/session-timezone behavior requires evidence.** | Not approved for conversion yet. Inspect historical session timezone configuration and target column/data state. |
| `analytics_page_views.period_start` | `app/models/analytics.py` explicitly documents the aggregation window as UTC; model and `c076b257b11d` use `DateTime(timezone=True)`. | **UTC window instant**, as explicitly documented by this writer/model contract. | Expected already timezone-aware in the migration source. Verify physical parity per database; this is not blanket permission for similarly named columns. |
| `analytics_page_views.created_at` | The model describes a flush-time write and uses an aware UTC Python default; `c076b257b11d` creates it timezone-aware. | **UTC lifecycle instant** in current implementation. | Verify physical parity; not a naive-column conversion candidate if schema matches source. |
| `transport_bookings.pickup_time` | `app/transport/services/booking_service.py` uses an ISO timestamp. Offset-aware input is preserved as an instant; naive legacy input is interpreted in configured `APP_TZ`; instant bookings default to aware UTC now. | **Booking instant at the application boundary.** Historical rows may have been written by different versions. | Do not convert historical values without inspecting the actual target data and historical writers. Keep the documented `APP_TZ` compatibility behavior until transport's input contract is migrated deliberately. |
| `BookingRegistrationLink.expires_at` | `app/accommodation/services/booking_registration_link_service.py` constructs expiry from the calendar date `booking.check_in` at midnight UTC. | **Business rule unresolved:** it turns a venue-related calendar date into an absolute midnight-UTC instant. | Do not treat this as proven correct. Confirm whether expiry should be local start-of-day, a specified deadline, or another rule before changing implementation or storage. |
| Other timestamp fields, including generic `*_at` fields | Names alone do not establish the historical timezone. Existing source includes a mixture of Python defaults, database defaults, compatibility fallbacks, and explicit offsets. | **Unclassified until writer/data evidence is collected column by column.** | No blanket approval. Record each target as UTC instant, intentional local wall-clock value, date-only, or unresolved. |

This is deliberately a small source-supported set, not a complete database-column inventory. It does **not** establish the historical semantics of production or test rows.

## 3. Migration guard improvement

The timezone migration now has two separate exact-inventory sets:

- `APPROVED_LEGACY_UTC_COLUMNS`: legacy columns whose values are proven to represent UTC instants.
- `APPROVED_LEGACY_WALL_CLOCK_COLUMNS`: reviewed local civil-time columns that must stay `TIMESTAMP WITHOUT TIME ZONE` and whose SQLAlchemy models must agree.

Both sets are intentionally empty. They may not overlap. The migration refuses to proceed unless every naive timestamp column discovered on the exact target is covered by exactly one set. Only the UTC set is converted; wall-clock values are left untouched. Any column whose meaning is unknown blocks the migration.

The environment variable `AFCON360_LEGACY_NAIVE_TIMESTAMPS_ARE_UTC=YES` remains an operator attestation, not proof. The migration has **not** been run.

## 4. Evidence still required to approve any column

For each target database separately:

1. Capture current database identity, `alembic_version`, and a read-only physical timestamp-column inventory.
2. Link every candidate column to its model, historical writers, server defaults, jobs, input schemas, readers, serializers, and domain meaning.
3. Inspect representative values and compare them with source/system logs or other trustworthy evidence; catalog types alone cannot prove a historical timezone.
4. Assign a reviewed classification: UTC instant, intentional local wall-clock, calendar date/non-timestamp, or unresolved.
5. Confirm model/schema parity and regression behavior on a populated disposable clone before changing either allowlist.
6. Keep unresolved fields out of the migration until the owning domain defines the intended behavior.

No database query or data change was executed for this register.
