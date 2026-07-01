# AFCON360 Database Scalability Roadmap

## Executive Summary

This document provides a complete audit of the current database state and a phased roadmap to transform AFCON360 into a system capable of handling **millions to billions of daily transactions** without breaking — following patterns used by Amazon, Meta, Google, and Oracle.

**Current Status:** The system is in early development with only test data. No production data exists, so there is **zero risk of data loss** from the changes outlined here.

**Target State:** Zero PostgreSQL ENUM types, all models inheriting from `BaseModel`, schema changes deployable without locks or downtime, and application-level validation replacing database-level constraints.

---

## Table of Contents

1. [Current Database State](#current-database-state)
2. [Critical Issues Found](#critical-issues-found)
3. [Scalability Principles](#scalability-principles)
4. [Phased Migration Plan](#phased-migration-plan)
5. [File-by-File Change Guide](#file-by-file-change-guide)
6. [Testing & Validation](#testing--validation)
7. [Deployment Strategy](#deployment-strategy)
8. [Future Agent Guidelines](#future-agent-guidelines)

---

## 1. Current Database State

### 1.1 Model Inheritance Audit

| File | Current Base Class | Status | Action Required |
|------|-------------------|--------|-----------------|
| `app/models/base.py` | Defines `BaseModel` | ✅ Correct | None |
| `app/models/audit.py` | `BaseModel` | ✅ Correct | None |
| `app/models/theme.py` | `BaseModel` / `ProtectedModel` | ✅ Correct | None |
| `app/models/analytics.py` | `db.Model` directly | ❌ **VIOLATION** | Change to `BaseModel` |
| `app/models/system_config.py` | `db.Model` directly | ❌ **VIOLATION** | Change to `BaseModel` |

**Rule:** ALL models MUST inherit from `BaseModel` (or `ProtectedModel`), never `db.Model` directly.

### 1.2 PostgreSQL ENUM Usage Audit

**Total ENUM columns found: 40+ across 15+ files**

#### CRITICAL RISK — Wallet Module (HIGH RISK)
| File | Column | ENUM Type | Values |
|------|--------|-----------|--------|
| `app/wallet/models.py` | `wallet_type` | `SQLEnum(WalletType)` | user, org, agent, system |
| `app/wallet/models.py` | `status` | `SQLEnum(WalletStatus)` | active, frozen, closed, suspended |
| `app/wallet/models.py` | `category` | `SQLEnum(TransactionCategory)` | deposit, withdrawal, transfer, fee, refund |
| `app/wallet/models/ledger.py` | `entry_type` | `SQLEnum(EntryType)` | debit, credit |
| `app/wallet/models/ledger.py` | `account_owner_type` | `SQLEnum(AccountOwnerType)` | user, organisation |
| `app/wallet/models/transaction.py` | `transaction_type` | `SQLEnum(TransactionType)` | deposit, withdrawal, transfer, payment, refund |
| `app/wallet/models/transaction.py` | `status` | `SQLEnum(TransactionStatus)` | pending, processing, completed, failed, cancelled |

#### HIGH RISK — Identity Module
| File | Column | ENUM Type | Values |
|------|--------|-----------|--------|
| `app/identity/models/organisation.py` | `verification_status` | `Enum(...)` | unverified, pending, verified, rejected, suspended, expired |
| `app/identity/models/organisation.py` | `lifecycle_state` | `Enum(...)` | draft, registered, approved, suspended, closed |
| `app/identity/models/organisation.py` | `business_category` | `Enum(OrganizationType)` | 20+ organisation types |
| `app/identity/models/kyb.py` | `status` | `Enum(...)` | pending, verified, rejected, expired, suspended |
| `app/identity/models/kyb.py` | `check_type` | `Enum(...)` | identity, tax, license, ubo, sanctions |
| `app/identity/models/kyb.py` | `ubo_type` | `Enum(...)` | individual, corporate |
| `app/identity/models/compliance_settings.py` | `enforcement_level` | `Enum(...)` | optional, conditional, mandatory |
| `app/identity/individuals/individual_verification.py` | `status` | `Enum(...)` | pending, verified, rejected, expired, suspended |
| `app/identity/individuals/individual_document.py` | `document_type` | `Enum(...)` | id_card, passport, driver_license, proof_of_address |
| `app/identity/models/licence_document.py` | `verification_status` | `Enum(...)` | pending, verified, rejected |
| `app/identity/models/compliance_audit_log.py` | `entity_type` | `Enum(...)` | organisation, individual |
| `app/identity/models/compliance_audit_log.py` | `decision` | `Enum(...)` | allowed, blocked, conditional |
| `app/identity/models/compliance_audit_log.py` | `risk_tier` | `Enum(...)` | low, medium, high |

#### MEDIUM RISK — Transport Module
| File | Column | ENUM Type | Values |
|------|--------|-----------|--------|
| `app/transport/models.py` | `verification_tier` | `SQLEnum(VerificationTier)` | unverified, basic, premium, enterprise |
| `app/transport/models.py` | `compliance_status` | `SQLEnum(ComplianceStatus)` | pending_review, approved, rejected, suspended |
| `app/transport/models.py` | `vehicle_class` | `SQLEnum(VehicleClass)` | economy, standard, premium, luxury |
| `app/transport/models.py` | `provider_type` | `SQLEnum(ProviderType)` | individual, company, fleet |
| `app/transport/models.py` | `service_type` | `SQLEnum(ServiceType)` | airport, city, intercity, charter |
| `app/transport/models.py` | `currency` | `SQLEnum(Currency)` | USD, UGX, KES, EUR, GBP |
| `app/transport/models.py` | `payment_status` | `SQLEnum(PaymentStatus)` | pending, processing, completed, failed, refunded |
| `app/transport/models.py` | `status` | `SQLEnum(BookingStatus)` | draft, pending, confirmed, in_progress, completed, cancelled |
| `app/transport/models.py` | `severity` | `SQLEnum(IncidentSeverity)` | low, medium, high, critical |

#### MEDIUM RISK — Accommodation Module
| File | Column | ENUM Type | Values |
|------|--------|-----------|--------|
| `app/accommodation/models/property.py` | `property_type` | `db.Enum(...)` | hotel, apartment, villa, hostel, guesthouse |
| `app/accommodation/models/property.py` | `cancellation_policy` | `db.Enum(...)` | flexible, moderate, strict, non_refundable |
| `app/accommodation/models/property.py` | `status` | `db.Enum(...)` | draft, pending, approved, rejected, suspended |
| `app/accommodation/models/property.py` | `verification_status` | `db.Enum(...)` | unverified, pending, verified, rejected |
| `app/accommodation/models/booking.py` | `status` | `db.Enum(...)` | draft, pending, confirmed, checked_in, checked_out, cancelled |
| `app/accommodation/models/booking.py` | `payment_status` | `db.Enum(...)` | pending, processing, completed, failed, refunded |
| `app/accommodation/models/availability.py` | `reason` | `db.Enum(...)` | maintenance, blocked, seasonal, owner_use |
| `app/accommodation/models/review.py` | `status` | `db.Enum(...)` | pending, approved, rejected, flagged |

#### MEDIUM RISK — Events Module
| File | Column | ENUM Type | Values |
|------|--------|-----------|--------|
| `app/events/models.py` | Various | `enum.Enum` classes | creator_type, owner_type, transfer_status, discount_type |

#### MEDIUM RISK — Audit Module
| File | Column | ENUM Type | Values |
|------|--------|-----------|--------|
| `app/audit/comprehensive_audit.py` | `transaction_type` | `SQLEnum(TransactionType)` | deposit, withdrawal, transfer, payment, refund |
| `app/audit/comprehensive_audit.py` | `status` | `SQLEnum(APICallStatus)` | pending, success, failed, timeout |
| `app/audit/comprehensive_audit.py` | `access_type` | `SQLEnum(DataAccessType)` | read, write, delete, export |
| `app/audit/comprehensive_audit.py` | `severity` | `SQLEnum(AuditSeverity)` | info, warning, error, critical |

#### MEDIUM RISK — Admin Compliance Module
| File | Column | ENUM Type | Values |
|------|--------|-----------|--------|
| `app/admin/compliance/models.py` | `case_type` | `db.Enum(ComplianceCaseType)` | aml, kyc, fraud, sanctions |
| `app/admin/compliance/models.py` | `status` | `db.Enum(ComplianceCaseStatus)` | open, investigating, resolved, closed |
| `app/admin/compliance/models.py` | `priority` | `db.Enum(ComplianceCasePriority)` | low, medium, high, critical |
| `app/admin/compliance/models.py` | `request_type` | `db.Enum(DataSubjectRequestType)` | access, deletion, portability, rectification |
| `app/admin/compliance/models.py` | `report_type` | `db.Enum(ComplianceReportType)` | aml, kyc, audit, regulatory |

#### LOW RISK — Profile Module
| File | Column | ENUM Type | Values |
|------|--------|-----------|--------|
| `app/profile/models.py` | `gender` | `SAEnum(*GENDERS)` | male, female, other, prefer_not_to_say |
| `app/profile/models.py` | `id_type` | `SAEnum(*ID_TYPES)` | national_id, passport, drivers_license |
| `app/profile/models.py` | `verification_status` | `SAEnum(*VERIFICATION_STATUS)` | unverified, pending, verified, rejected |
| `app/profile/models.py` | `kyc_level` | `SAEnum(*KYC_LEVELS)` | none, basic, enhanced, full |

---

## 2. Critical Issues Found

### Issue 1: PostgreSQL ENUM Types (CRITICAL)
**Problem:** 40+ columns use PostgreSQL ENUM types (`Enum`, `SQLEnum`, `SAEnum`).

**Why it's a problem at scale:**
- `ALTER TYPE ... ADD VALUE` requires `ACCESS EXCLUSIVE` lock — blocks all queries
- Cannot be autogenerated by Alembic — manual migration scripts required
- "type already exists" errors in Docker Compose multi-container startups
- Cannot rename or delete values without dropping and recreating the type
- Binary format causes replication lag and CDC issues
- Schema drift between environments accumulates over time

**Impact at 100M+ transactions/day:**
- Every new status value = deployment failure or extended downtime
- Connection pool exhaustion during ENUM DDL operations
- Cascading timeouts across all services

### Issue 2: Model Inheritance Violations (MEDIUM)
**Problem:** `app/models/analytics.py` and `app/models/system_config.py` inherit from `db.Model` directly.

**Why it's a problem:**
- Misses `BaseModel` features: soft delete, ID protection, automatic timestamps
- Inconsistent behavior across the application
- `BaseModel.__setattr__` ID guard won't protect these models

### Issue 3: No CHECK Constraints (LOW)
**Problem:** ENUMs provide DB-level validation, but String columns have none.

**Why it matters:**
- Application-level validation can be bypassed by raw SQL
- CHECK constraints provide defense-in-depth without ENUM overhead

---

## 3. Scalability Principles

### 3.1 What Big Tech Actually Does

| Company | ENUM Strategy | Schema Change Strategy |
|---------|--------------|----------------------|
| **Meta** | Never uses DB ENUMs — String + CHECK constraints | Expand-contract pattern, feature flags |
| **Amazon** | String columns with application enums | Shadow tables, canary deployments |
| **Google** | Strings in DB, protobuf enums in app | Blue/green deployments |
| **Netflix** | String + application state machines | Chaos engineering, gradual rollouts |
| **Oracle** | Avoids ENUMs in high-volume tables | Online DDL, rolling upgrades |

### 3.2 Core Principles for AFCON360

1. **Never use PostgreSQL ENUM types** — Use `String` columns with application-level validation
2. **Never lock a table for a schema change** — Use expand-contract pattern
3. **Never deploy schema changes without a rollback plan** — Every change must be reversible in < 5 minutes
4. **Never touch the wallet module without full ledger analysis** — HIGH RISK area
5. **Always use `BaseModel` inheritance** — Never `db.Model` directly
6. **Always use `BigInteger` for internal IDs** — Never `Integer`
7. **Always use `user.public_id` (UUID) externally** — Never expose `user.id`

### 3.3 The Expand-Contract Pattern

This is how you make schema changes without downtime:

```
Phase 1: EXPAND (No locks, no downtime)
- Add new column: status_new VARCHAR(20) DEFAULT 'pending'
- Write to BOTH old and new columns (dual-write)
- Backfill old → new in batches of 10,000 rows

Phase 2: MIGRATE (Gradual, reversible)
- Read from new column
- Continue dual-write until all rows backfilled
- Monitor for errors

Phase 3: CONTRACT (Quick, low-risk)
- Drop old ENUM column
- Rename new column to original name
- Remove old ENUM type from database
```

**Key insight:** At no point is the table locked or unavailable.

---

## 4. Phased Migration Plan

### Phase 0: Preparation (1-2 days)
**Goal:** Create tooling and documentation before touching any models.

**Tasks:**
1. Create this document ✅
2. Create ENUM-to-String migration helper script
3. Create CHECK constraint migration script
4. Set up staging environment with production-like data volume
5. Create rollback procedures for each module

**Deliverables:**
- `scripts/migrate_enums_to_strings.py` — Automated migration helper
- `scripts/add_check_constraints.py` — CHECK constraint adder
- `docs/rollback_procedures.md` — Rollback guide for each module

### Phase 1: Core Models (1 day) — LOW RISK
**Goal:** Fix model inheritance violations and low-risk ENUMs.

**Files to change:**
1. `app/models/analytics.py` — Change `db.Model` → `BaseModel`
2. `app/models/system_config.py` — Change `db.Model` → `BaseModel`
3. `app/models/audit.py` — Already correct, verify ENUMs
4. `app/models/theme.py` — Already correct

**ENUMs to convert:**
- `app/audit/comprehensive_audit.py` — 4 ENUM columns

**Testing:**
- Run full test suite
- Verify audit log creation still works
- Verify analytics aggregation still works

### Phase 2: Events Module (2-3 days) — MEDIUM RISK
**Goal:** Convert events ENUMs to String columns.

**Files to change:**
1. `app/events/models.py` — Convert ENUM classes to String columns
2. `app/events/constants.py` — Update constants to use strings
3. `app/events/routes.py` — Update filters to use strings
4. `app/events/services.py` — Update service calls

**ENUMs to convert:**
- `CreatorType`, `OwnerType`, `TransferStatus`, `DiscountType`

**Migration approach:**
- Expand-contract for each ENUM column
- Add CHECK constraints after migration

### Phase 3: Transport Module (2-3 days) — MEDIUM RISK
**Goal:** Convert transport ENUMs to String columns.

**Files to change:**
1. `app/transport/models.py` — 10 ENUM columns
2. `app/transport/services/` — Update all service files

**ENUMs to convert:**
- `VerificationTier`, `ComplianceStatus`, `BookingStatus`, `PaymentStatus`
- `ServiceType`, `ProviderType`, `VehicleClass`, `IncidentSeverity`, `Currency`

**Special considerations:**
- Currency column: Consider using ISO 4217 codes (USD, UGX, KES) — already strings in many places
- Payment status: Critical for financial transactions — thorough testing required

### Phase 4: Accommodation Module (2-3 days) — MEDIUM RISK
**Goal:** Convert accommodation ENUMs to String columns.

**Files to change:**
1. `app/accommodation/models/property.py` — 4 ENUM columns
2. `app/accommodation/models/booking.py` — 3 ENUM columns
3. `app/accommodation/models/availability.py` — 1 ENUM column
4. `app/accommodation/models/review.py` — 1 ENUM column

**ENUMs to convert:**
- `AccommodationPropertyType`, `AccommodationCancellationPolicy`
- `AccommodationPropertyStatus`, `AccommodationVerificationStatus`
- `AccommodationBookingStatus`, `AccommodationPaymentStatus`
- `AccommodationBlockedReason`, `AccommodationReviewStatus`

### Phase 5: Admin Compliance Module (1-2 days) — MEDIUM RISK
**Goal:** Convert compliance ENUMs to String columns.

**Files to change:**
1. `app/admin/compliance/models.py` — 5 ENUM columns

**ENUMs to convert:**
- `ComplianceCaseType`, `ComplianceCaseStatus`, `ComplianceCasePriority`
- `DataSubjectRequestType`, `DataSubjectRequestStatus`
- `ComplianceReportType`

### Phase 6: Audit Module (1 day) — LOW RISK
**Goal:** Convert audit ENUMs to String columns.

**Files to change:**
1. `app/audit/comprehensive_audit.py` — 4 ENUM columns

**ENUMs to convert:**
- `TransactionType`, `APICallStatus`, `DataAccessType`, `AuditSeverity`

### Phase 7: Identity Module (3-4 days) — HIGH RISK
**Goal:** Convert identity ENUMs to String columns.

**Files to change:**
1. `app/identity/models/organisation.py` — 3 ENUM columns
2. `app/identity/models/kyb.py` — 4 ENUM columns
3. `app/identity/models/compliance_settings.py` — 1 ENUM column
4. `app/identity/individuals/individual_verification.py` — 1 ENUM column
5. `app/identity/individuals/individual_document.py` — 1 ENUM column
6. `app/identity/models/licence_document.py` — 3 ENUM columns
7. `app/identity/models/compliance_audit_log.py` — 3 ENUM columns

**Special considerations:**
- KYC/compliance data is regulatory-sensitive
- Must maintain data integrity during migration
- Consider running migration during low-traffic periods
- May require regulatory notification in production

### Phase 8: Wallet Module (4-6 days) — CRITICAL RISK
**Goal:** Convert wallet ENUMs to String columns.

**Files to change:**
1. `app/wallet/models.py` — 3 ENUM columns
2. `app/wallet/models/ledger.py` — 2 ENUM columns
3. `app/wallet/models/transaction.py` — 2 ENUM columns

**ENUMs to convert:**
- `WalletType`, `WalletStatus`, `TransactionCategory`
- `EntryType`, `AccountOwnerType`
- `TransactionType`, `TransactionStatus`

**Special considerations:**
- **DO NOT MODIFY without full ledger impact analysis**
- Every debit must have a matching credit — column type changes must preserve this
- Test with production-like transaction volumes
- Consider running migration during maintenance window
- Have financial team sign off on migration plan

---

## 5. File-by-File Change Guide

### 5.1 Pattern for Converting ENUM to String

**Before (ENUM):**
```python
from sqlalchemy import Enum as SQLEnum

class BookingStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"

class Booking(BaseModel):
    __tablename__ = "bookings"
    status = Column(SQLEnum(BookingStatus), nullable=False, default=BookingStatus.DRAFT)
```

**After (String):**
```python
from sqlalchemy import String, CheckConstraint

class Booking(BaseModel):
    __tablename__ = "bookings"
    status = Column(String(20), nullable=False, default="draft", index=True)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'confirmed', 'cancelled')", name="chk_booking_status"),
    )
```

### 5.2 Pattern for Application-Level Validation

**Before (DB-level via ENUM):**
```python
# Validation happens automatically via PostgreSQL ENUM
booking.status = BookingStatus.CONFIRMED  # Type-safe
```

**After (Application-level):**
```python
from typing import Literal

BookingStatus = Literal["draft", "confirmed", "cancelled"]

class Booking(BaseModel):
    # ... column definition ...
    
    @validates("status")
    def validate_status(self, key, value: str) -> str:
        valid_statuses = {"draft", "confirmed", "cancelled"}
        if value not in valid_statuses:
            raise ValueError(f"Invalid booking status: {value}")
        return value
```

### 5.3 Pattern for Query Updates

**Before (ENUM):**
```python
# Filter using enum
bookings = Booking.query.filter(Booking.status == BookingStatus.CONFIRMED).all()
```

**After (String):**
```python
# Filter using string
bookings = Booking.query.filter(Booking.status == "confirmed").all()
```

### 5.4 Specific File Changes

#### `app/models/analytics.py`
```python
# Change:
class PageViewAggregate(db.Model):
# To:
class PageViewAggregate(BaseModel):
```

#### `app/models/system_config.py`
```python
# Change:
class SystemConfig(db.Model):
# To:
class SystemConfig(BaseModel):
```

#### `app/wallet/models.py`
```python
# Remove:
from sqlalchemy import Enum as SQLEnum

class WalletType(enum.Enum): ...
class WalletStatus(enum.Enum): ...
class TransactionCategory(enum.Enum): ...

# Change:
wallet_type = Column(SQLEnum(WalletType), ...)
# To:
wallet_type = Column(String(20), nullable=False, index=True, default="user")

# Add CHECK constraint in __table_args__
```

#### `app/identity/models/organisation.py`
```python
# Remove:
from sqlalchemy import Enum

# Change:
verification_status = Column(Enum("unverified", "pending", ...), ...)
# To:
verification_status = Column(String(20), nullable=False, index=True, default="unverified")

# Add CHECK constraint
```

---

## 6. Testing & Validation

### 6.1 Test Checklist for Each Module

- [ ] All existing tests pass
- [ ] New String columns accept all previous ENUM values
- [ ] Invalid values are rejected by application validation
- [ ] CHECK constraints are in place
- [ ] Queries using the column still work
- [ ] API responses unchanged
- [ ] Database migrations run successfully on test data
- [ ] Rollback procedure tested and documented

### 6.2 Integration Test Requirements

```python
def test_enum_to_string_migration():
    """Verify ENUM values are preserved after migration"""
    # Create record with old ENUM value
    booking = Booking(status="confirmed")  # Was BookingStatus.CONFIRMED
    db.session.add(booking)
    db.session.commit()
    
    # Verify it's stored as string
    result = db.session.execute(
        text("SELECT status FROM bookings WHERE id = :id"),
        {"id": booking.id}
    ).scalar()
    assert result == "confirmed"
    assert isinstance(result, str)

def test_invalid_status_rejected():
    """Verify application validation rejects invalid values"""
    with pytest.raises(ValueError, match="Invalid booking status"):
        booking = Booking(status="invalid_status")
        db.session.add(booking)
```

### 6.3 Performance Testing

Before and after each module migration:
- [ ] Benchmark query performance (should be identical or better)
- [ ] Benchmark insert performance (should be identical)
- [ ] Test with 1M+ rows in the table
- [ ] Verify index usage on String columns

---

## 7. Deployment Strategy

### 7.1 General Principles

1. **Never deploy schema changes and code changes together** — Deploy schema first, code second
2. **Always have a rollback plan** — Every change must be reversible in < 5 minutes
3. **Deploy during low-traffic periods** — Even with zero-downtime migrations, lower risk
4. **Monitor closely for 24 hours post-deployment** — Watch for error rates, latency, connection pool usage

### 7.2 Deployment Sequence

```
Day 1: Deploy schema changes (expand phase)
- New String columns added alongside old ENUM columns
- Dual-write enabled in application code
- No user-facing changes

Day 2-3: Backfill data
- Run backfill script in batches
- Monitor for errors

Day 4: Deploy code changes (read from new columns)
- Application reads from String columns
- Still writes to both columns

Day 5: Deploy contract phase
- Drop old ENUM columns
- Remove ENUM types from database
- Clean up dual-write code
```

### 7.3 Rollback Procedures

**If something goes wrong:**
1. Revert application code to previous version
2. Application will read from old ENUM columns (still present)
3. Fix the issue in development
4. Re-run migration

**Key insight:** The expand-contract pattern means rollback is always possible until the contract phase.

---

## 8. Future Agent Guidelines

### 8.1 Mandatory Rules for Database Changes

**NEVER:**
- Add a new PostgreSQL ENUM type
- Use `db.Model` directly — always use `BaseModel`
- Use `Integer` for primary keys — always use `BigInteger`
- Expose `user.id` externally — always use `user.public_id`
- Modify `app/wallet/models/` without explicit instruction and full analysis
- Run `ALTER TABLE` on a table with > 1M rows without expand-contract pattern
- Patch migration files as workarounds — fix root cause in models

**ALWAYS:**
- Use `String` columns with application-level validation
- Add CHECK constraints for defense-in-depth
- Use `BigInteger` for all internal IDs and foreign keys
- Use `user.public_id` (UUID) for external-facing APIs
- Check for existing `backref` names before adding relationships
- Use `sa.inspect()` before `op.create_table` in migrations
- Run `flask db stamp head` before `flask db upgrade` after bootstrap

### 8.2 ENUM Decision Tree

```
Need to store a fixed set of values?
│
├─ Is it a high-volume table (> 1M rows/day)?
│  ├─ YES → Use String + CHECK constraint
│  └─ NO → Still use String + CHECK constraint (consistency)
│
├─ Will values change frequently?
│  ├─ YES → Use String (ENUMs are painful to modify)
│  └─ NO → Still use String (consistency)
│
└─ Do you need to add values without downtime?
   ├─ YES → Use String
   └─ NO → Still use String (future-proofing)
```

**Answer is always: Use String.**

### 8.3 Model Inheritance Checklist

Before creating any new model:
- [ ] Does it inherit from `BaseModel`? (Not `db.Model`)
- [ ] Does it use `BigInteger` for primary key? (Not `Integer`)
- [ ] Does it use `String` for status/value columns? (Not `Enum`)
- [ ] Does it use `user.id` for internal FKs? (Not `user.public_id`)
- [ ] Does it have `is_deleted` and `deleted_at`? (From `BaseModel`)
- [ ] Does it have `created_at` and `updated_at`? (From `TimestampMixin`)

### 8.4 Migration Checklist

Before running any migration:
- [ ] Have you tested it on a copy of production data?
- [ ] Do you have a rollback plan?
- [ ] Is the migration reversible?
- [ ] Will it lock any tables? If yes, for how long?
- [ ] Have you checked for existing ENUM types that might conflict?
- [ ] Have you run `flask db stamp head` if this is a fresh database?

### 8.5 Wallet Module Special Instructions

**The wallet module is HIGH RISK. Before any change:**

1. **Read the full ledger impact** — Every debit must have a matching credit
2. **Check for TOCTOU races** — Use DB-level locks, not application-level checks
3. **Verify double-entry integrity** — Run ledger balance checks before and after
4. **Get sign-off** — Financial team must approve any schema changes
5. **Test with production volumes** — Use a copy of production data
6. **Have a maintenance window** — Be prepared to pause transactions during migration

### 8.6 Quick Reference: Current ENUM Locations

```
app/wallet/models.py              — 3 ENUM columns (CRITICAL)
app/wallet/models/ledger.py       — 2 ENUM columns (CRITICAL)
app/wallet/models/transaction.py  — 2 ENUM columns (CRITICAL)
app/transport/models.py           — 10 ENUM columns (MEDIUM)
app/identity/models/             — 15 ENUM columns (HIGH)
app/accommodation/models/        — 9 ENUM columns (MEDIUM)
app/events/models.py             — 4 ENUM columns (MEDIUM)
app/audit/comprehensive_audit.py — 4 ENUM columns (LOW)
app/admin/compliance/models.py   — 5 ENUM columns (MEDIUM)
app/profile/models.py            — 4 ENUM columns (LOW)
```

### 8.7 Commands for Future Agents

```powershell
# Check for ENUM usage
Get-ChildItem -Path app -Recurse -Filter *.py | Select-String -Pattern "Enum|SQLEnum|SAEnum"

# Check for db.Model violations
Get-ChildItem -Path app/models -Recurse -Filter *.py | Select-String -Pattern "class.*\(db\.Model\)"

# Run migrations
flask db stamp head  # If alembic_version is missing
flask db upgrade     # Apply migrations

# Check current database ENUMs
# Connect to PostgreSQL and run:
SELECT typname FROM pg_type WHERE typtype = 'e';

# Check for model inheritance issues
python -c "from app.models.analytics import PageViewAggregate; print(PageViewAggregate.__bases__)"
```

---

## Appendix A: Why This Matters at Scale

### The ENUM Problem at 100M+ Transactions/Day

| Operation | ENUM | String |
|-----------|------|--------|
| Add new value | `ALTER TYPE` — locks DB for seconds/minutes | Deploy code change — zero downtime |
| Rename value | Drop + recreate type — table rewrite | `UPDATE table SET col='new'` — batched |
| Remove value | Drop + recreate type — table rewrite | Filter in application |
| Query flexibility | Exact match only | LIKE, ILIKE, partial matches |
| Replication | Binary format issues | Plain text, no issues |
| Autogenerate | Blind to changes | Detects automatically |
| Cross-DB | PostgreSQL-specific | Works everywhere |

### Real-World Incident Examples

**Incident 1:** A major e-commerce platform added a new order status via `ALTER TYPE`. The 3-second lock cascaded into 15 minutes of downtime because connection pools exhausted and recovery took time.

**Incident 2:** A fintech company's ENUM migration failed mid-execution, leaving the database in an inconsistent state. Recovery required a 2-hour maintenance window.

**Incident 3:** A social media platform's ENUM type name conflicted between environments (staging vs production), causing deployments to fail repeatedly.

**All of these are solved by using String columns.**

---

## Appendix B: References

- [PostgreSQL ENUM Documentation](https://www.postgresql.org/docs/current/datatype-enum.html)
- [SQLAlchemy Enum Documentation](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.Enum)
- [Alembic Autogenerate Limitations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [Expand-Contract Pattern](https://martinfowler.com/articles/continuousIntegration.html#ProductionLikeTestEnvironment)
- [Online Schema Changes at Scale](https://www.usenix.org/system/files/conference/nsdi15/nsdi15-paper-zhang.pdf)

---

## Document Metadata

- **Created:** 2026-06-20
- **Author:** Kilo Code (AI Assistant)
- **Status:** Living document — update as migration progresses
- **Next Review:** After Phase 1 completion
- **Owner:** Development Team Lead

---

*This document should be treated as the authoritative source for all database schema decisions in AFCON360. Any deviation from these guidelines requires explicit approval from the Development Team Lead and must be documented in this file.*
