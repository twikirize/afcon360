# TZ-UNIFY-01: System-wide Timezone-Aware Datetime Migration

**Node Type**: ARCHITECTURAL
**Status**: DRAFT → pending human approval
**Scope**: All modules with naive `DateTime` columns → migrate to `DateTime(timezone=True)` with UTC storage

---

## 1. Objective

Establish a single, uniform timezone-aware datetime system across AFCON360:
- **Storage**: All datetimes stored as UTC in PostgreSQL (`TIMESTAMP WITH TIME ZONE`)
- **Transport**: ISO 8601 with `Z` suffix (e.g., `2026-10-28T09:15:00Z`)
- **Presentation**: Convert to user's IANA timezone at render/API response edge
- **Input**: Parse incoming datetimes as UTC (or reject if ambiguous)

This ensures a user in **Canada (America/Toronto)** booking a hotel in **Nairobi (Africa/Nairobi)** has unambiguous, correct timestamps throughout the lifecycle.

---

## 2. Current State Audit (Complete)

### 2.1 Already Timezone-Aware (Verified)
Modules using `DateTime(timezone=True)` exclusively:
- `app.admin.models` (moderation, emergency_access)
- `app.events.models` (registrations, tickets, inventory)
- `app.accommodation.models` (property, room, review, special_request, cancellation_policy, platform_override)
- `app.identity.models.delegation`
- `app.event_accommodation.models` (opportunity, badge)
- **`app.transport.models`** — all datetime columns already timezone-aware
- **`app.wallet.models`** — all datetime columns already timezone-aware

### 2.2 Naive Datetime Columns Requiring Migration (89 columns across 18 files)

| File | Table | Columns (naive `DateTime`) | Count |
|------|-------|---------------------------|-------|
| `app/identity/models/user.py` | `users` | `password_changed_at`, `password_expires_at`, `email_verified_at`, `phone_verified_at`, `activated_at`, `deleted_at`, `locked_until`, `last_login`, `transaction_pin_locked_until`, `emergency_access_granted`, `emergency_access_expires`, `assigned_at` (APIKey), `last_used` (APIKey), `created_at` (APIKey), `expires_at` (Session), `revoked_at` (Session), `revoked_at` (Device) | 17 |
| `app/identity/models/kyb.py` | `kyb_records`, `kyb_documents` | `decided_at`, `expires_at`, `effective_from`, `effective_to`, `verified_at` | 5 |
| `app/identity/models/organisation.py` | `organisations` | `verified_at`, `compliance_reviewed_at`, `referred_at` | 3 |
| `app/identity/models/organisation_controller.py` | `organisation_controllers` | `appointed_at` | 1 |
| `app/identity/models/organisation_member.py` | `organisation_members`, `member_roles` | `assigned_at`, `granted_at` | 2 |
| `app/identity/models/organisation_provider_capability.py` | `org_provider_capabilities` | `activated_at`, `verified_at` | 2 |
| `app/identity/models/provider_participation.py` | `provider_participations` | `activated_at`, `verified_at` | 2 |
| `app/identity/models/licence_document.py` | `licence_documents`, `licence_document_versions` | `uploaded_at`, `verified_at`, `changed_at` | 3 |
| `app/identity/models/compliance_settings.py` | `compliance_settings` | `created_at`, `updated_at` | 2 |
| `app/identity/models/compliance_audit_log.py` | `compliance_audit_logs` | `decided_at` | 1 |
| `app/identity/individuals/individual_verification.py` | `individual_verifications` | `requested_at`, `decided_at`, `expires_at` | 3 |
| `app/identity/individuals/individual_document.py` | `individual_documents` | `expires_at` | 1 |
| `app/accommodation/models/booking.py` | `accommodation_bookings` | `changed_at` | 1 |
| `app/audit/comprehensive_audit.py` | `comprehensive_audit_logs` | `reviewed_at`, `completed_at`, `handled_at` | 3 |
| `app/auth/config_model.py` | `auth_configs` | `updated_at` | 1 |
| `app/compliance/aml_service.py` | `sanctions_screenings`, `aml_alerts`, `monitoring_runs` | `screening_date`, `reviewed_date`, `monitoring_date` | 3 |
| `app/compliance/aml_regulatory_models.py` | `aml_cases`, `monitoring_windows`, `regulatory_reports`, `compliance_periods`, `attestations` | `suspicion_formed_at`, `due_at`, `filed_at`, `terminated_at`, `edd_approved_at`, `last_calibrated_at`, `run_at`, `window_start`, `window_end`, `completed_at`, `expires_at`, `period_start`, `period_end`, `attested_at`, `last_reviewed_at` | 15 |
| `app/feed/models.py` | `feed_posts` | `start_date`, `end_date` | 2 |
| `app/media/models.py` | `media_processing_jobs` | `started_at`, `completed_at` | 2 |
| `app/models/base.py` | (base class) | `deleted_at` | 1 |
| `app/models/system_config.py` | `system_configs` | `updated_at` | 1 |
| `app/notifications/models.py` | `notifications`, `notification_deliveries`, `notification_batches` | `scheduled_for`, `sent_at`, `delivered_at`, `read_at`, `last_attempt_at`, `attempted_at`, `next_retry_at`, `queued_at`, `sent_at`, `delivered_at`, `read_at`, `read_at`, `archived_at` | 13 |
| `app/notifications/events/models.py` | `event_notifications`, `notification_templates`, `delivery_attempts` | `published_at`, `processed_at`, `published_at`, `locked_at`, `last_success_at`, `last_failure_at`, `next_attempt_at`, `delivered_at` | 8 |
| `app/profile/models.py` | `user_profiles`, `profile_verifications`, `agent_applications` | `last_reviewed_at`, `deleted_at`, `suspended_at`, `revoked_at`, `attempted_at`, `admin_approved_at`, `compliance_approved_at`, `super_admin_approved_at`, `owner_approved_at`, `approved_at`, `applied_at`, `rejected_at` | 12 |

**Total: 89 naive DateTime columns** across 10 modules.

---

## 3. Specification

### 3.1 Database Schema Changes

For each naive `DateTime` column:
```python
# Before
locked_until = Column(DateTime, nullable=True)

# After
locked_until = Column(DateTime(timezone=True), nullable=True)
```

PostgreSQL type changes from `TIMESTAMP` → `TIMESTAMP WITH TIME ZONE` (timestamptz).

### 3.2 Migration Strategy

**Approach**: Single comprehensive migration (big-bang) with verified backfill.

**Backfill Rule**: All existing naive datetime values are assumed to be **UTC** (consistent with current writers using `datetime.now(timezone.utc)`).

**Alembic Migration Pattern** (per column):
```python
op.alter_column(
    'table_name', 'column_name',
    type_=DateTime(timezone=True),
    postgresql_using="column_name AT TIME ZONE 'UTC'",
    existing_nullable=True,
)
```

### 3.3 Code Changes Required

#### Models (all affected modules)
- Add `timezone=True` to every `DateTime` column
- Verify defaults use `lambda: datetime.now(timezone.utc)`

#### Services/Writers
- Ensure all `datetime.now()` → `datetime.now(timezone.utc)`
- No naive datetime construction anywhere

#### Serializers/API
- Output: ISO 8601 with `Z` suffix (`dt.isoformat().replace('+00:00', 'Z')`)
- Input: Parse with `datetime.fromisoformat()` → ensure aware UTC

#### Frontend/Templates
- Receive UTC ISO strings
- Display using user's `profile.timezone` (IANA) via JavaScript `Intl.DateTimeFormat` or server-side conversion

### 3.4 User Timezone Handling

1. **Profile field**: Add `timezone` column to `UserProfile` (IANA string, default `'UTC'`)
2. **Middleware**: Attach user timezone to request context
3. **Template filter**: `{{ dt|user_tz }}` → converts UTC to user TZ
4. **API**: `/api/timezone/convert` for client-side conversion

---

## 4. Verification Requirements

### 4.1 Unit Tests
- Naive → aware migration preserves values (UTC assumption)
- Writers produce aware UTC datetimes
- Serializers output `Z`-suffix ISO strings
- Parsers accept `Z` and `+00:00` formats

### 4.2 Integration Tests
- **Canada user books Nairobi hotel**: 
  - Request sent as `2026-10-28T14:00:00Z` (UTC)
  - Stored as `2026-10-28 14:00:00+00` in DB
  - Canadian user sees `2026-10-28 10:00 EDT`
  - Nairobi hotel sees `2026-10-28 17:00 EAT`
- DST transitions (spring forward, fall back)
- Legacy naive data reads correctly post-migration

### 4.3 Migration Tests
- Run on production data clone
- Verify row counts match
- Spot-check known timestamps
- Zero data loss

---

## 5. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Existing naive values not actually UTC | Medium | High | Audit sample before migration; if mixed, per-column backfill logic |
| Application code passes naive datetimes | Medium | High | Static analysis + runtime assertions in test suite |
| Frontend displays wrong timezone | Medium | Medium | Comprehensive UI test matrix |
| Migration lock time on large tables | Low | High | Run during maintenance window; consider `pg_repack` |

---

## 6. Deliverables

1. **Complete column inventory** (this document — Section 2.2)
2. **Alembic migration file(s)** with `postgresql_using` casts for all 89 columns
3. **Model changes** across 10 affected modules (18 files)
4. **Service/writer audit** — all datetime construction sites
5. **Serializer updates** — ISO 8601 `Z` output
6. **UserProfile.timezone** field + middleware + template filter
7. **Test suite** — unit, integration, migration verification
8. **Rollback plan** — `downgrade()` migration tested

---

## 7. Authorization Required

This node requires explicit human approval for:
- [ ] Schema migration across 10 modules (89 columns in 18 files)
- [ ] API contract change (ISO 8601 `Z` format)
- [ ] New `UserProfile.timezone` column (IANA string, default `'UTC'`)
- [ ] Potential maintenance window for migration

**Gate**: PASS only after human confirms scope, reviews migration plan, and authorizes `flask db migrate` + `flask db upgrade`.

---

## 8. Follow-up Nodes

- `TZ-UNIFY-02`: Frontend timezone picker & persistence
- `TZ-UNIFY-03`: Scheduled job / Celery beat timezone alignment
- `TZ-UNIFY-04`: Historical data audit & correction (if mixed TZ discovered)

---

## Migration History Repair (2026-10-28)

**Grep term:** `TZ-UNIFY-02 recovery`

The TZ-UNIFY-02 step is intentionally split across three migrations because the original source for two of them was lost and had to be recovered from compiled artifacts:

- `c8c6a2c5a3f9` — 387 timestamp conversions + drops the 366 baseline timestamp indexes.
- `31287acd4eb8` — 54 further timestamp conversions.
- `85776e36d829` — recreates 370 indexes: the 366 dropped by `c8c6` plus 4 new ones.

**Do not squash or collapse these three files.**

The original commit `315c36e` chained only:

`c4b306c2ed73 -> 85776e36d829 -> fc87cdbd0e6a`

It did **not** include `c8c6a2c5a3f9` or `31287acd4eb8`. Its `85776` had 370 `create_index` operations and 370 downgrade `drop_index` operations, but **zero** `alter_column` conversions. The repaired chain is:

`1793013676 -> c4b306c2ed73 -> c8c6a2c5a3f9 -> 31287acd4eb8 -> 85776e36d829 -> fc87cdbd0e6a`

**Repair commit:** the commit that adds this section. The recovered files were validated by operation counts, fresh install from empty, a data-bearing downgrade/upgrade, and full catalog parity; the exact original `.pyc` source text was not recoverable.

### Deploy warning

A database that ran `315c36e`'s broken chain must **not** be upgraded in place or stamped to the repaired head. It carries `85776`/`fc87` revision markers but is missing the `c8c6`/`31287` conversions and the 366 index drops; `flask db upgrade` will see `fc87` and do nothing.

Audit any database claiming to be at head:

- Naive timestamp columns: `SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND data_type='timestamp without time zone';` — must be `0`.
- Aware timestamp columns: same query with `timestamp with time zone` — must be `983` (plus intentional new columns).
- Public index count: must be `1,746` at this head.

Rebuild from a verified backup, or apply the missing DDL under review with row-count/hash and catalog evidence. Do not simply stamp it.

Databases at `c4b306c2ed73` or earlier can upgrade through the repaired chain. Fresh installs from empty were proven on 2026-10-28: 226 tables, 0 naive / 983 aware, 1,746 indexes, full catalog parity with production. A database already at `fc87cdbd0e6a` with 0 naive / 983 aware and 1,746 indexes is already correct; these files are a history/reproducibility repair, not a new schema change.

For any still-naive database, run the conversions with the legacy values interpreted as `Africa/Nairobi` wall-clock (the historical `PGTZ`/session timezone). Do not add `AT TIME ZONE 'UTC'` casts to these columns.
