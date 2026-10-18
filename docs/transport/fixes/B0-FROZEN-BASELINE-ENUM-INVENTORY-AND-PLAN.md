# B0 — Clean-Install Baseline Correction: Complete ENUM Inventory & Static Baseline Plan

**Status:** PLAN / FOR REVIEW — no migration executed, no database touched, no model edited, nothing committed.
**Scope:** Investigate the clean-install failure at `8a0deccce6f6` and produce a *static* (source-only) baseline plan/diff that gives every retained ENUM exactly one explicit creation owner, with exact persisted labels, before any dependent table.
**Architecture:** Follows the agreed **frozen, explicit baseline** (= H3 N-squash family): `down_revision=None`, explicit `op.*` operations, **no application-model imports**, **no `db.metadata.create_all()` / `drop_all()`**, **no dynamic schema derivation**, every retained ENUM created exactly once, non-destructive downgrade.
**Method:** AST static analysis of `app/**` and `migrations/**` (no app import, no DB connection) + source inspection.

---

## 0. Constraints honored

- All existing dirty and untracked work preserved (no `reset` / `clean` / `stash` / `checkout .`).
- No migration executed; no database altered; no protected DB permission changed.
- No retired migration edited; nothing committed.
- The failed replay against `afcon360_verify_20261017_test` is treated as evidence; that database was not reset or recreated.
- Analysis artifacts written only to the pre-approved temp dir, not the repo.

---

## 1. Evidence — the failed replay

| Item | Value |
|---|---|
| Target | `afcon360_verify_20261017_test` (fresh scratch) |
| Revision reached | `8a0deccce6f6` (root, `down_revision=None`) |
| Error | `psycopg2.errors.UndefinedObject: type "transactiontype" does not exist` |
| Post-failure state | **zero user tables**, **no `alembic_version`**, **no ENUM types** |
| Interpretation | The root runs in a single transaction; it failed before creating anything, then rolled back. The whole upgrade is atomic. |

`transactiontype` is `PgEnum(AuditTransactionType, name="transactiontype", create_type=False)` at `app/audit/comprehensive_audit.py:74`. Because `create_type=False` suppresses SQLAlchemy's automatic `CREATE TYPE`, and the root body is `db.metadata.create_all(op.get_bind())` (`migrations/versions/8a0deccce6f6_initial_full_schema_baseline.py:36`), **no owner ever creates the 39 `create_type=False` ENUM types before the tables that use them.** The first such table the dependency sort reaches is `financial_audit_logs`; Postgres rejects the `CREATE TABLE`.

This is **not** a one-type bug. `transactiontype` is simply the first casualty. The complete ownerless set is enumerated in §3.

---

## 2. Method & completeness (source-only verification)

- Walked `app/**/*.py` and `migrations/**/*.py` with Python `ast` only. No application import, no DB connection. (Many repo files carry a UTF-8 BOM; the parser reads them as `utf-8-sig`.)
- Enum classes resolved across modules, including `from … import X as Y` aliases (e.g. `from app.utils.enums import Currency as CurrencyEnum`).
- **Completeness check:** raw grep of `PgEnum(`, `SQLEnum(`, `Enum(` declaration lines in `app/` = **58**; AST declaration sites = **58**. Exact match.
- **Consistency check:** every type name is internally consistent across all its declaration sites — labels, persisted kind (NAMES/VALUES), and `create_type` — **0 inconsistencies**.

---

## 3. Model-side ENUM inventory (authoritative, from source)

**58 declaration sites = 49 `PgEnum` + 9 `Enum/SQLEnum` → 47 distinct type names.**

- **GROUP A — 39 distinct names / 49 sites**, `PgEnum(..., create_type=False)`. **No owner in the active chain** → must be created explicitly by the baseline.
- **GROUP B — 8 distinct names / 9 sites**, `db.Enum(...)` / `SQLEnum(...)` with **no `create_type`** (defaults to `True`) → SQLAlchemy currently auto-creates these during `CREATE TABLE`. Name is derived from the lowercased class name.
- `VALUES` = persists member **values** (`values_callable` present). `NAMES` = persists member **names** (default). Labels are listed in **declaration order** (order is significant in PostgreSQL ENUMs).

### GROUP A — `create_type=False` (must be created explicitly)

| type | persists | sites | ordered labels |
|---|---|---:|---|
| `apicallstatus` | NAMES | 1 | `SUCCESS`, `FAILURE`, `TIMEOUT`, `RATE_LIMITED` |
| `auditseverity` | NAMES | 1 | `INFO`, `WARNING`, `CRITICAL`, `SECURITY` |
| `compensationmodel` | NAMES | 2 | `REVENUE_SPLIT`, `FIXED_RENTAL`, `HYBRID`, `FIXED_FEE`, `PERCENTAGE`, `PER_KM`, `PER_HOUR`, `DAILY_RATE`, `WEEKLY_RATE`, `MONTHLY_RATE`, `REVENUE_SHARE` |
| `compliance_decision` | VALUES | 1 | `allowed`, `blocked`, `conditional` |
| `compliance_enforcement_level` | VALUES | 1 | `optional`, `conditional`, `mandatory` |
| `compliancestatus` | NAMES | 2 | `PENDING_REVIEW`, `UNDER_REVIEW`, `APPROVED`, `SUSPENDED`, `REVOKED`, `BLACKLISTED` |
| `contractstatus` | NAMES | 1 | `DRAFT`, `ACTIVE`, `SUSPENDED`, `TERMINATED`, `EXPIRED`, `PENDING_SIGNATURE` |
| `currency` | NAMES | 2 | `USD`, `EUR`, `GBP`, `XOF`, `XAF`, `NGN`, `KES`, `GHS`, `ZAR`, `UGX` |
| `dataaccesstype` | NAMES | 1 | `READ`, `EXPORT`, `DELETE`, `MODIFY` |
| `doc_verification_status` | VALUES | 1 | `pending`, `verified`, `rejected` |
| `entity_type` | VALUES | 1 | `organisation`, `individual` |
| `gateway_environment` | NAMES | 1 | `SANDBOX`, `PRODUCTION` |
| `gender_enum` | VALUES | 1 | `male`, `female`, `other`, `unspecified` |
| `id_type_enum` | VALUES | 1 | `passport`, `national_id`, `driver_license`, `other` |
| `incidentseverity` | NAMES | 1 | `INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `ind_document_type` | VALUES | 1 | `id_card`, `passport`, `driver_license`, `proof_of_address` |
| `ind_verification_status` | VALUES | 1 | `pending`, `verified`, `rejected`, `expired`, `suspended` |
| `kyb_doc_status` | VALUES | 1 | `pending`, `verified`, `rejected` |
| `kyc_level_enum` | VALUES | 1 | `basic`, `enhanced`, `government` |
| `org_change_source` | VALUES | 1 | `system`, `user`, `admin` |
| `org_change_type` | VALUES | 1 | `create`, `update`, `delete`, `verify`, `suspend` |
| `org_kyb_check_status` | VALUES | 1 | `pending`, `passed`, `failed`, `manual_review` |
| `org_kyb_check_type` | VALUES | 1 | `identity`, `tax`, `license`, `ubo`, `sanctions` |
| `org_lifecycle_state` | VALUES | 1 | `draft`, `registered`, `approved`, `suspended`, `closed` |
| `org_verification_status` | VALUES | 2 | `unverified`, `pending`, `verified`, `rejected`, `suspended`, `expired` |
| `payment_gateway_provider` | NAMES | 1 | `FLUTTERWAVE`, `PAYSTACK`, `MTN_MOMO`, `AIRTEL_MONEY`, `VISA`, `MASTERCARD`, `PAYPAL`, `ALIPAY`, `WECHAT_PAY`, `BANK_TRANSFER`, `STRIPE`, `MPESA` |
| `paymentstatus` | NAMES | 2 | `PENDING`, `AUTHORIZED`, `CAPTURED`, `PARTIALLY_CAPTURED`, `REFUNDED`, `PARTIALLY_REFUNDED`, `FAILED`, `CANCELLED` |
| `propertydocumentstatus` | NAMES | 1 | `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED` |
| `propertydocumenttype` | NAMES | 1 | `ID_DOCUMENT`, `BUSINESS_LICENSE`, `TAX_CERTIFICATE`, `PROPERTY_DEED`, `INSURANCE_CERTIFICATE`, `OTHER` |
| `providertype` | NAMES | 1 | `INDIVIDUAL_DRIVER`, `HOTEL_FLEET`, `TOUR_OPERATOR`, `TRANSPORT_COMPANY`, `EXTERNAL_PLATFORM` |
| `risk_tier` | VALUES | 1 | `low`, `medium`, `high` |
| `rvpcr_status_enum` | NAMES | 1 | `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`, `EXPIRED` |
| `servicetype` | NAMES | 2 | `AIRPORT_ARRIVAL`, `AIRPORT_DEPARTURE`, `STADIUM_SHUTTLE`, `HOTEL_TRANSFER`, `CITY_TOUR`, `ON_DEMAND`, `SCHEDULED_ROUTE`, `CUSTOM_TOUR` |
| `transactiontype` | NAMES | 1 | `DEPOSIT`, `WITHDRAWAL`, `TRANSFER`, `REFUND`, `FEE`, `REVERSAL`, `CURRENCY_EXCHANGE`, `COMMISSION`, `PAYOUT`, `EXCHANGE` |
| `ubo_type` | VALUES | 1 | `individual`, `corporate` |
| `vehicleclass` | NAMES | 1 | `ECONOMY`, `COMFORT`, `PREMIUM`, `LUXURY`, `VAN`, `BUS` |
| `verification_status_enum` | VALUES | 1 | `pending`, `verified`, `rejected`, `suspended` |
| `verificationtier` | NAMES | 2 | `PENDING`, `BASIC_VERIFIED`, `PLATFORM_VERIFIED`, `EVENT_CERTIFIED` |
| `window_mode_enum` | NAMES | 4 | `CALENDAR`, `ROLLING` |

### GROUP B — implicit `Enum` (currently auto-created)

| type | persists | sites | ordered labels |
|---|---|---:|---|
| `applicationstatus` | NAMES | 1 | `PENDING`, `UNDER_REVIEW`, `APPROVED`, `REJECTED`, `WITHDRAWN`, `EXPIRED` |
| `compliancecasepriority` | NAMES | 2 | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `compliancecasestatus` | NAMES | 1 | `OPEN`, `IN_REVIEW`, `PENDING_INFO`, `APPROVED`, `REJECTED`, `ESCALATED`, `CLOSED` |
| `compliancecasetype` | NAMES | 1 | `KYC_REVIEW`, `KYB_REVIEW`, `AML_ALERT`, `PAYOUT_REVIEW`, `DATA_REQUEST`, `FLAG_ESCALATION`, `LICENSE_REVIEW`, `OTHER` |
| `compliancereporttype` | NAMES | 1 | `KYC_SUMMARY`, `AML_SUMMARY`, `PAYOUT_SUMMARY`, `CASE_HISTORY`, `AUDIT_TRAIL`, `RISK_ASSESSMENT`, `REGULATORY_FILING` |
| `datasubjectrequeststatus` | NAMES | 1 | `PENDING`, `VERIFIED`, `PROCESSING`, `COMPLETED`, `REJECTED`, `EXPIRED` |
| `datasubjectrequesttype` | NAMES | 1 | `ACCESS`, `DELETION`, `RECTIFICATION`, `PORTABILITY`, `OBJECTION` |
| `marketplacelistingstatus` | NAMES | 1 | `DRAFT`, `ACTIVE`, `PAUSED`, `FILLED`, `EXPIRED`, `CLOSED` |

**Declaration sites (for traceability):**
- Group A: `app/audit/comprehensive_audit.py` (transactiontype, apicallstatus, auditseverity, dataaccesstype), `app/accommodation/models/property_document.py`, `app/identity/**`, `app/profile/models.py`, `app/transport/models.py` (13 names), `app/wallet/models/regulatory_volume.py` (rvpcr_status_enum, window_mode_enum ×4), `app/identity/models/org_payment_gateway.py`.
- Group B: `app/admin/compliance/models.py` (:78,:84,:85,:105,:184,:185,:248), `app/transport/models.py` (:3231 marketplacelistingstatus, :3323 applicationstatus).

**Model-state finding:** `organisations.business_category` is **`Column(String(40))`** at `app/identity/models/organisation.py:333`; `app/auth/onboarding_routes.py:486-488` states it "is a plain String(40) column and no longer uses the org_business_category enum." Therefore the 47 model-declared types **do not include** `org_business_category`.

---

## 4. Migration-side ENUM inventory

### Active chain (single head `df55cbe3f516`, 27 revisions)

Only **two** active migrations create ENUM types, and only **four** distinct types — all four are already model-declared `create_type=False` in Group A:

| Migration | Type(s) created | Labels (as written) | Matches model? |
|---|---|---|---|
| `aab3e38879dc` (`sa.Enum(..., name=…)`, default `create_type`) | `payment_gateway_provider` | `FLUTTERWAVE`…`MPESA` (12) | ✅ exact |
| `aab3e38879dc` | `gateway_environment` | `SANDBOX`, `PRODUCTION` | ✅ exact |
| `f91075478868` (`sa.Enum(..., create_constraint=True)`) | `window_mode_enum` | `CALENDAR`, `ROLLING` | ✅ exact |
| `f91075478868` | `rvpcr_status_enum` | `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`, `EXPIRED` | ✅ exact |

**Coverage gap:** 39 − 4 = **35 Group-A types have no creating migration**, and even the four above run in migrations *after* the root. So no ordering places a creator before the root's tables.

Related active-chain findings:
- `df55cbe3f516:28` references `postgresql.ENUM(name='servicetype', create_type=False)` — a **reference with no creator** (same class of defect).
- `df55cbe3f516:124,152` references `org_business_category` as `ENUM('merchant','service_provider','marketplace_seller','non_profit')` (4 labels, lowercase) in `alter_column` (upgrade/downgrade converting to/from `String(40)`).
- `20260930_1335_booking_status_enum_to_string.py:81,85`: downgrade-only `CREATE TYPE bookingstatus_12 AS ENUM (...)` and `DROP TYPE bookingstatus`.
- `migrations/env.py:19-35`: the `skip_enum_create` rewriter returns `op` unchanged and `include_object` always returns `True` — **dead no-op code**; its comment ("we've converted all enums to String columns") is stale and contradicts the retention policy.

### Retired baseline `ab6dd422c152` (in `migrations/_retired_versions/`, not in active chain)

Enum types referenced by `alter_column` asserts (labels **indicated**, not proven live):

| type | labels as written in retired migration | register class |
|---|---|---|
| `account_owner_type_enum` | `USER`, `ORGANISATION` | REFERENCED (live column default) |
| `creatortype` | `INDIVIDUAL`, `ORGANIZATION`, `SYSTEM`, `individual`, `organization`, `system` (6) | REFERENCED |
| `ownertype` | `INDIVIDUAL`, `ORGANIZATION`, `SYSTEM`, `individual`, `organization`, `system` (6) | REFERENCED |
| `discounttype` | `PERCENTAGE`, `FIXED` | orphan |
| `eventstatus` | `draft`,`pending_approval`,`approved`,`rejected`,`live`,`published`,`suspended`,`paused`,`cancelled`,`archived`,`deleted` (11) | orphan |
| `transferstatus` | `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED` | orphan |
| `transaction_type_enum` | `DEPOSIT`,`WITHDRAW`,`TRANSFER`,`FEE`,`REFUND`,`ADJUSTMENT` | orphan |
| `transaction_status_enum` | `PENDING`,`COMPLETED`,`FAILED`,`CANCELLED` | orphan |

---

## 5. Census reconciliation against the register (item 17b)

| Register figure | This inventory | Note |
|---|---|---|
| 47 shared table-column types | **47** model-declared names | exact match |
| 48 USED (… + `org_business_category`) | 47 + `org_business_category` | `org_business_category` is a **legacy live-enum in `afcon360_test`**, not in the current model (§3) |
| 3 REFERENCED (`account_owner_type_enum`, `creatortype`, `ownertype`) | present in retired `ab6dd422c152` only | no model column uses them |
| 16 dev-only orphans | 8 named in retired migration + 8 legacy-from-earlier partially named | not fully enumerable from source |
| `bookingstatus` | referenced only by `20260930_1335` downgrade | not a live column type |
| prod 68 / test 49 | not re-derived here (no DB access) | unchanged, source-only |

**Consequence for a *fresh* install:** the final-state schema needs only the **47** model-declared types. `org_business_category`, the 3 REFERENCED, the 16 orphans, and `bookingstatus` are **existing-database legacy objects**, not fresh-install requirements. This distinction is load-bearing and is flagged in §7.

---

## 6. Proposed static baseline plan

### 6.1 Shape of the corrected root (`8a0deccce6f6.upgrade()`)

Replace the dynamic body with an explicit, ordered sequence. Sketch (the ENUM block is final; the table block is generated, per §20, from metadata — see §6.3):

```python
from alembic import op
import sqlalchemy as sa

revision = "8a0deccce6f6"
down_revision = None
branch_labels = None
depends_on = None

# --- explicit ENUM ownership: exactly one CREATE TYPE per retained type ---
_ENUM_TYPES = [
    ("apicallstatus", ["SUCCESS", "FAILURE", "TIMEOUT", "RATE_LIMITED"]),
    ("auditseverity", ["INFO", "WARNING", "CRITICAL", "SECURITY"]),
    # … 37 more Group-A entries + 8 Group-B entries (see §3) …
]

def _create_enum_types():
    bind = op.get_bind()
    for name, labels in _ENUM_TYPES:
        op.execute(
            "CREATE TYPE %s AS ENUM (%s)"
            % (name, ", ".join("'" + l.replace("'", "''") + "'" for l in labels))
        )

def upgrade():
    _create_enum_types()           # 1) all types first — no dependent table may precede
    _create_tables_and_indexes()   # 2) explicit op.create_table(...) generated from metadata

def downgrade():
    raise NotImplementedError(
        "Baseline downgrade is intentionally disabled; recovery = verified backup restore."
    )
```

No `from app… import`, no `op.get_bind().execute(<metadata DDL>)`, no `db.metadata.create_all()`/`drop_all()`.

### 6.2 The exact explicit CREATE TYPE block (Group A then Group B)

```python
op.execute("CREATE TYPE apicallstatus AS ENUM ('SUCCESS', 'FAILURE', 'TIMEOUT', 'RATE_LIMITED')")
op.execute("CREATE TYPE auditseverity AS ENUM ('INFO', 'WARNING', 'CRITICAL', 'SECURITY')")
op.execute("CREATE TYPE compensationmodel AS ENUM ('REVENUE_SPLIT', 'FIXED_RENTAL', 'HYBRID', 'FIXED_FEE', 'PERCENTAGE', 'PER_KM', 'PER_HOUR', 'DAILY_RATE', 'WEEKLY_RATE', 'MONTHLY_RATE', 'REVENUE_SHARE')")
op.execute("CREATE TYPE compliance_decision AS ENUM ('allowed', 'blocked', 'conditional')")
op.execute("CREATE TYPE compliance_enforcement_level AS ENUM ('optional', 'conditional', 'mandatory')")
op.execute("CREATE TYPE compliancestatus AS ENUM ('PENDING_REVIEW', 'UNDER_REVIEW', 'APPROVED', 'SUSPENDED', 'REVOKED', 'BLACKLISTED')")
op.execute("CREATE TYPE contractstatus AS ENUM ('DRAFT', 'ACTIVE', 'SUSPENDED', 'TERMINATED', 'EXPIRED', 'PENDING_SIGNATURE')")
op.execute("CREATE TYPE currency AS ENUM ('USD', 'EUR', 'GBP', 'XOF', 'XAF', 'NGN', 'KES', 'GHS', 'ZAR', 'UGX')")
op.execute("CREATE TYPE dataaccesstype AS ENUM ('READ', 'EXPORT', 'DELETE', 'MODIFY')")
op.execute("CREATE TYPE doc_verification_status AS ENUM ('pending', 'verified', 'rejected')")
op.execute("CREATE TYPE entity_type AS ENUM ('organisation', 'individual')")
op.execute("CREATE TYPE gateway_environment AS ENUM ('SANDBOX', 'PRODUCTION')")
op.execute("CREATE TYPE gender_enum AS ENUM ('male', 'female', 'other', 'unspecified')")
op.execute("CREATE TYPE id_type_enum AS ENUM ('passport', 'national_id', 'driver_license', 'other')")
op.execute("CREATE TYPE incidentseverity AS ENUM ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')")
op.execute("CREATE TYPE ind_document_type AS ENUM ('id_card', 'passport', 'driver_license', 'proof_of_address')")
op.execute("CREATE TYPE ind_verification_status AS ENUM ('pending', 'verified', 'rejected', 'expired', 'suspended')")
op.execute("CREATE TYPE kyb_doc_status AS ENUM ('pending', 'verified', 'rejected')")
op.execute("CREATE TYPE kyc_level_enum AS ENUM ('basic', 'enhanced', 'government')")
op.execute("CREATE TYPE org_change_source AS ENUM ('system', 'user', 'admin')")
op.execute("CREATE TYPE org_change_type AS ENUM ('create', 'update', 'delete', 'verify', 'suspend')")
op.execute("CREATE TYPE org_kyb_check_status AS ENUM ('pending', 'passed', 'failed', 'manual_review')")
op.execute("CREATE TYPE org_kyb_check_type AS ENUM ('identity', 'tax', 'license', 'ubo', 'sanctions')")
op.execute("CREATE TYPE org_lifecycle_state AS ENUM ('draft', 'registered', 'approved', 'suspended', 'closed')")
op.execute("CREATE TYPE org_verification_status AS ENUM ('unverified', 'pending', 'verified', 'rejected', 'suspended', 'expired')")
op.execute("CREATE TYPE payment_gateway_provider AS ENUM ('FLUTTERWAVE', 'PAYSTACK', 'MTN_MOMO', 'AIRTEL_MONEY', 'VISA', 'MASTERCARD', 'PAYPAL', 'ALIPAY', 'WECHAT_PAY', 'BANK_TRANSFER', 'STRIPE', 'MPESA')")
op.execute("CREATE TYPE paymentstatus AS ENUM ('PENDING', 'AUTHORIZED', 'CAPTURED', 'PARTIALLY_CAPTURED', 'REFUNDED', 'PARTIALLY_REFUNDED', 'FAILED', 'CANCELLED')")
op.execute("CREATE TYPE propertydocumentstatus AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')")
op.execute("CREATE TYPE propertydocumenttype AS ENUM ('ID_DOCUMENT', 'BUSINESS_LICENSE', 'TAX_CERTIFICATE', 'PROPERTY_DEED', 'INSURANCE_CERTIFICATE', 'OTHER')")
op.execute("CREATE TYPE providertype AS ENUM ('INDIVIDUAL_DRIVER', 'HOTEL_FLEET', 'TOUR_OPERATOR', 'TRANSPORT_COMPANY', 'EXTERNAL_PLATFORM')")
op.execute("CREATE TYPE risk_tier AS ENUM ('low', 'medium', 'high')")
op.execute("CREATE TYPE rvpcr_status_enum AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED')")
op.execute("CREATE TYPE servicetype AS ENUM ('AIRPORT_ARRIVAL', 'AIRPORT_DEPARTURE', 'STADIUM_SHUTTLE', 'HOTEL_TRANSFER', 'CITY_TOUR', 'ON_DEMAND', 'SCHEDULED_ROUTE', 'CUSTOM_TOUR')")
op.execute("CREATE TYPE transactiontype AS ENUM ('DEPOSIT', 'WITHDRAWAL', 'TRANSFER', 'REFUND', 'FEE', 'REVERSAL', 'CURRENCY_EXCHANGE', 'COMMISSION', 'PAYOUT', 'EXCHANGE')")
op.execute("CREATE TYPE ubo_type AS ENUM ('individual', 'corporate')")
op.execute("CREATE TYPE vehicleclass AS ENUM ('ECONOMY', 'COMFORT', 'PREMIUM', 'LUXURY', 'VAN', 'BUS')")
op.execute("CREATE TYPE verification_status_enum AS ENUM ('pending', 'verified', 'rejected', 'suspended')")
op.execute("CREATE TYPE verificationtier AS ENUM ('PENDING', 'BASIC_VERIFIED', 'PLATFORM_VERIFIED', 'EVENT_CERTIFIED')")
op.execute("CREATE TYPE window_mode_enum AS ENUM ('CALENDAR', 'ROLLING')")
# --- Group B (currently create_type defaults True) ---
op.execute("CREATE TYPE applicationstatus AS ENUM ('PENDING', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'EXPIRED')")
op.execute("CREATE TYPE compliancecasepriority AS ENUM ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')")
op.execute("CREATE TYPE compliancecasestatus AS ENUM ('OPEN', 'IN_REVIEW', 'PENDING_INFO', 'APPROVED', 'REJECTED', 'ESCALATED', 'CLOSED')")
op.execute("CREATE TYPE compliancecasetype AS ENUM ('KYC_REVIEW', 'KYB_REVIEW', 'AML_ALERT', 'PAYOUT_REVIEW', 'DATA_REQUEST', 'FLAG_ESCALATION', 'LICENSE_REVIEW', 'OTHER')")
op.execute("CREATE TYPE compliancereporttype AS ENUM ('KYC_SUMMARY', 'AML_SUMMARY', 'PAYOUT_SUMMARY', 'CASE_HISTORY', 'AUDIT_TRAIL', 'RISK_ASSESSMENT', 'REGULATORY_FILING')")
op.execute("CREATE TYPE datasubjectrequeststatus AS ENUM ('PENDING', 'VERIFIED', 'PROCESSING', 'COMPLETED', 'REJECTED', 'EXPIRED')")
op.execute("CREATE TYPE datasubjectrequesttype AS ENUM ('ACCESS', 'DELETION', 'RECTIFICATION', 'PORTABILITY', 'OBJECTION')")
op.execute("CREATE TYPE marketplacelistingstatus AS ENUM ('DRAFT', 'ACTIVE', 'PAUSED', 'FILLED', 'EXPIRED', 'CLOSED')")
```

**Group B caution (open decision):** these 8 columns currently let SQLAlchemy auto-create the type during `CREATE TABLE`. If the baseline ALSO creates them explicitly, the tables must reference them with `create_type=False` or Postgres raises "type already exists". That requires either (a) adding `create_type=False` (+ explicit `name=`) to those 8 model declarations (a **model change**, needs authorization), or (b) **not** pre-creating Group B and letting `CREATE TABLE` own them. §7 Decision D6.

### 6.3 Table operations (mechanism — for the replay-ready version, not this static plan)

- The `op.create_table(...)` block must be **generated from the real metadata** by the approved `flask db migrate` workflow (per constitution §20.3), not hand-written. Because 39 columns carry `create_type=False`, autogenerate renders `postgresql.ENUM(..., create_type=False)` references and emits **no** `CREATE TYPE`; the explicit block in §6.2 is therefore the deliberate, documented ownership layer added to the generated migration. This is the one place where the frozen-baseline architecture intentionally departs from pure autogenerate and must be explicitly approved (§7 Decision D7).
- **Ordering guarantee:** every `CREATE TYPE` in §6.2 executes before the first `op.create_table`. No type depends on another, so order among types is free; alphabetical is used for determinism.
- **Downstream neutralization:** under the chosen frozen baseline, `aab3e38879dc` and `f91075478868` (and every other revision already represented in the baseline) must be retired/merged in the same commit; otherwise their `sa.Enum(...)` `create_table`/`alter_column` re-creates the four types/tables. `20260930_1335`'s `CREATE TYPE bookingstatus_12`/`DROP TYPE bookingstatus` must not run (item 21: no `bookingstatus` creation by that name; non-destructive downgrade).

### 6.4 Server defaults (item 28a) — preserved, not invented

The 145 default-diffs (132 prod-only, 12 test-only, 1 both-differ `system_configs.created_at`) are **not** resolved by this enum plan. The generated `op.create_table` must carry the **intended** server defaults explicitly; where the intended value is not decided, the item stays a declared exception. Do not normalize defaults merely to make environments match.

---

## 7. Unresolved dependencies & decisions (do not guess)

| ID | Decision required | Why it blocks the frozen baseline |
|---|---|---|
| **D1** | **Architecture: H3 (N-squash reproducing final model) vs H2′ (frozen old root + downstream).** | Determines whether `org_business_category` is created at all. H3 → **not** created (model is `String(40)`); H2′ → root creates it and `df55cbe3f516` converts. Item 18 remains GATED. |
| **D2** | **`org_business_category` 39-label UPPER set source.** | Appears in **no** migration; only the 4-label lowercase set exists (in `df55cbe3f516`). 39 labels are not derivable from source. Needed only if D1 = H2′ / for existing-test conversion. |
| **D3** | **3 REFERENCED types** (`account_owner_type_enum`, `creatortype`, `ownertype`). | No model column uses them; labels come only from a **retired** `alter_column` assert (and `creatortype`/`ownertype` show a suspicious 6-label mixed-case set → likely historical error). Preserve-or-migrate the 3 legacy column defaults (item 21) is undecided. Not needed for a fresh baseline. |
| **D4** | **16 dev-only orphan types** disposition (retain/drop). | Drop-candidate pending ruling (item 24). Not needed for a fresh baseline. |
| **D5** | **`bookingstatus` / `bookingstatus_12`.** | Item 21: no `bookingstatus` creation by that name; retain unless downgrade abandoned. Not needed for a fresh baseline. |
| **D6** | **Group B ownership mechanism** (§6.2 caution). | Either edit 8 model declarations (`create_type=False` + explicit `name=`) — a model change needing authorization — or leave Group B to `CREATE TABLE`. |
| **D7** | **Provenance of the hand-added explicit `CREATE TYPE` block** in an otherwise autogenerated migration. | Constitution §20.4 forbids manually editing generated migrations. The frozen-baseline architecture requires the explicit ownership layer. Needs explicit approval of this exception (or an alternative mechanism). |
| **D8** | **145 server-default dispositions (item 28a).** | Precondition for item 37 convergence; must be encoded in generated `create_table`. |
| **D9** | **Supported starting revisions (item 13)**, **docker census (12b)**, **per-DB parity artifact** (17a cond. 5). | Register prerequisites to item 18; unchanged. |

---

## 8. Source-only verification performed

| Check | Method | Result |
|---|---|---|
| Declaration-site completeness | raw grep (58) vs AST (58) in `app/` | **match** |
| Label/persist/create_type consistency per type | AST grouping | **0 inconsistencies** |
| Model type-name count vs register | AST (47) vs register (47 shared) | **match** |
| 4 migration-created types vs model labels | source inspection | **exact match** |
| Root body dynamic-creation defect | source (`8a0deccce6f6:36`) | **confirmed** |
| `create_type=False` with no active creator | AST + active-chain scan | **35 of 39 have no creator; the other 4 create only after the root** |
| `df55cbe3f516` tracked | `git ls-files` | **tracked** |
| BOM in `app/**` | AST parse failures | several files (parser uses `utf-8-sig`) |

No database was read or written for this verification.

---

## 9. Proposed change set (for review — NOT applied)

1. **`migrations/versions/8a0deccce6f6_initial_full_schema_baseline.py`** — replace the `create_all()`/`drop_all()` body with: (a) the explicit `CREATE TYPE` block (§6.2), then (b) generated explicit `op.create_table`/index/constraint ops (§6.3); non-destructive `downgrade`.
2. **Same commit:** retire/merge the now-represented downstream revisions (`aab3e38879dc`, `f91075478868`, and any other fully-contained revision) and neutralize `20260930_1335`'s `bookingstatus` DDL.
3. **Optional (D6):** if Group B is pre-created, add `create_type=False` + explicit `name=` to the 8 Group-B declarations (`app/admin/compliance/models.py` ×7 sites, `app/transport/models.py:3231,3323`) — **model change, needs authorization**.
4. **`migrations/env.py`:** remove or repair the dead no-op `skip_enum_create`/`include_object` code and its stale comment (separate, low-risk).
5. **Register:** record this inventory + the D1–D9 decisions (owner-only; the agent does not edit the register).

---

## 10. Acceptance criteria for the corrected baseline (for the later, authorized replay)

- `flask db upgrade` from a **genuinely empty** database completes with **no** `UndefinedObject`.
- Final schema contains all **47** model-declared ENUM types with the exact labels in §3, plus any D1–D5 objects the owner decides to retain.
- `flask db check` reports no unintended enum/type differences.
- `downgrade` performs no destructive action.
- Fresh-built schema equals the migration-built schema (item 37), accounting for the item-28a defaults exceptions.

---

## 11. Not done (explicit)

No migration executed or authored into the repo; no model modified; no database read or written; no retired migration edited; nothing committed; the failed scratch database was not reset. All artifacts are source-only. This plan is offered for review before any replay.

---
---

# Addendum A — 2026-10-17 — H3 Architecture Direction (owner-directed)

**Status:** DOCUMENTATION ONLY — no migration authored, edited, retired or applied; no model changed; nothing staged or committed. Versions 1–2 (above) are preserved verbatim; nothing in §0–§11 was rewritten or replaced.
**Scope:** Record the owner's direction to proceed with **H3 (new squash root / N-squash)** rather than extending the existing root under H2′; record the verified blockers; record the payment-identity index discrepancy with evidence; state the H3 transition safeguards required before any implementation.

## A.1 Recorded decision vs implementation readiness

The **architectural direction is H3**: establish a new squash root (`N-squash`, `down_revision=None`), retire the superseded active migration files **in the same controlled change**, and define explicit handling for every existing database state.

This records a **direction**, not readiness. Implementation remains **gated** by the register items in §A.4. Decision D1 in §7 is now answered (**H3**); D2–D9 remain open. Item 18 ("Approve one architecture") is advanced but not closed by this addendum alone — the register is the owner's artifact and is not edited here.

## A.2 Why H3 is preferable to continuing H2′

Evidence is the register's architecture comparison (item 17), not assumption:

| Criterion | H2′ (frozen old root + downstream) | H3 (N-squash) |
|---|---|---|
| Fresh install | Deterministic frozen root | Same; **smaller replay set** |
| Enum ownership location | Frozen root **+ `f91075478868` exception required** | N-squash body; **`f91075478868` retires, defect dissolves** |
| Repair surface | **Strictly more** for the same enum outcome | Strictly less |
| Immutability | Violates once, explicitly | Preserves old files |
| Rollback | Downgrade chain | Re-track + re-stamp |
| Future authoring | Unchanged | Clean lineage; retired-ID ban |

Three concrete consequences (register items 15, 17, and 21/22):

1. **H3 puts schema creation into a new root** and reduces historical replay surface. Only the final model state is authored once.
2. **Retiring `f91075478868` removes the need to repair its repeated `window_mode_enum` emission.** Register item 22: the 4× `CREATE TYPE` emit at `f91075478868:23,24,53,54` is predicted to fail under either architecture, but under H3 it dissolves because the file retires; under H2′ it requires an in-place history exception. (The working tree currently carries a H2′ conditionalizing repair to that file — an uncommitted artifact of the superseded direction.)
3. **H2′ requires separately resolving historical migration conflicts** (slug pair `71893e3a42a2`/`bd9d3bb673aa`, `window_mode_enum`, enum ownership) that H3 dissolves by authoring the final state directly.

**Load-bearing caveat (register items 14, 14a, 17b):** a matching `alembic_version` value does **not** prove matching schemas. Existing databases still require state-specific handling and independently verified schema parity. H3 does not remove this hazard; it only reduces the authoring surface.

## A.3 Repository / working-tree state at the time of this addendum

| Fact | Evidence |
|---|---|
| Local `origin/main` = `f0c41e7`; local `HEAD` = `fbd54e1` (main, 1 ahead of origin/main) | `git log --oneline -1 origin/main`, `-1 HEAD` |
| Dirty migration files (H2′-era, uncommitted): `8a0deccce6f6`, `f91075478868`, `1788729103`, `bd9d3bb673aa` | `git status --short` |
| This plan document is **untracked** (`??`) | `git status --short` |
| **`df55cbe3f516` IS tracked** on both `origin/main` (`f0c41e7`) and local `HEAD` | `git cat-file -e origin/main:<path>` → tracked; `git log --all --oneline -- <path>` → `f0c41e7` |
| Existing archive convention = `migrations/_retired_versions/` | directory listing of `migrations/` |

**New evidence contradicting a register premise (recorded, not edited):** register item 16d / canonical correction C4 state that `df55cbe3f516` is untracked and "a clean checkout cannot resolve it." The revision **is** tracked at `origin/main` (`f0c41e7`) and `HEAD`. A clean checkout therefore resolves the revision ID. What remains unverified is whether the **coupled FK-name/model diffs** (item 16c: "df55cbe3f516's FK names match the dirty working tree, not committed HEAD") landed **atomically** in `f0c41e7` — that atomicity check is an owner action and is not asserted here. The register is not edited by this agent.

## A.4 Verified blockers (register cross-reference, unchanged status)

These remain blocking. None is reported as closed by this addendum:

| Register item | Status | Substance |
|---|---|---|
| **12b — Docker census** | [OPEN] | Docker database unreachable (containers down). Q1–Q4 probe still required. **Blocks H3.** |
| **13 — Supported starting revisions** | [OPEN] | Human product decision; cannot advance from source. |
| **14 / 17b — Physical schema parity** | [ADVANCED]/[CLOSED evidence] | `afcon360_prod` and `afcon360_test` share revision `df55cbe3f516` but differ physically: **1 column-type difference** (`organisations.business_category`: 39-label UPPER enum in test vs `varchar(40)` in prod) and **145 server-default differences** (132 prod-only, 12 test-only, 1 both-differ `system_configs.created_at`). Prod = 68 enum types; test = 49. |
| **16d — `df55cbe3f516` atomic tracking** | [PREREQ] | File is now tracked (§A.3). Coupled-diff atomicity unverified. Prerequisite to either architecture. |
| **28a — Default differences** | [NEW] | 145 server-default differences must be classified and dispositioned before any convergence claim. Item 37 (fresh-vs-upgraded) is gated on this. |
| **30–39 — Verification** | [NOT STARTED] | Isolated DB (30), clean-install (31), independent physical-schema comparison (32), model/schema parity (33), current-head behavior (34), supported-starting-state upgrades (35), data integrity (36), fresh-vs-upgraded convergence (37), failure recovery (38), automated regression gates (39). None reported closed. |

## A.5 Payment-identity index discrepancy — evidence and unresolved follow-up

The superseded H2′ root working-tree DDL contains:

```sql
CREATE INDEX ix_payment_identity_account ON payment_identities (account_id);
```

The repository's current `f91075478868_production_console.py:132` instead creates:

```python
batch_op.create_index(
    batch_op.f('ix_payment_identities_account_id'),
    ['account_id'],
    unique=False,
)
```

**Verified trace (do not assume equivalence — definitions and dependencies were checked):**

| Source | Index name | Definition | Evidence |
|---|---|---|---|
| Model `__table_args__` | `ix_payment_identity_account` | non-unique, single column `account_id` | `app/wallet/models/payment_identity.py:63` |
| Model **column** `account_id` | `ix_payment_identities_account_id` (SQLAlchemy auto-name from `index=True`) | non-unique, single column `account_id` | `payment_identity.py:124` (`index=True`) |
| Retired migration `f4a1b2c3d5e6` | `ix_payment_identity_account` | `op.create_index('ix_payment_identity_account', ...)` | `migrations/_retired_versions/f4a1b2c3d5e6_payment_identity_architecture.py:92` |
| Active migration `f91075478868` | `ix_payment_identities_account_id` | `batch_op.create_index(batch_op.f('ix_payment_identities_account_id'), ...)` | `migrations/versions/f91075478868_production_console.py:132` |
| **Verify DB (physical, at head)** | **BOTH exist** | two separate non-unique indexes on `account_id` | read-only `inspect(engine).get_indexes('payment_identities')` |

**Findings:**

1. The **model itself declares the index twice** — an explicit `Index('ix_payment_identity_account', 'account_id')` in `__table_args__` *and* `index=True` on the `account_id` column. SQLAlchemy materialises both as distinct `Index` objects (confirmed in `db.metadata`: 5 indexes on the table, of which two target `account_id`). The other three named indexes (`owner`, `org_owner`, `normalized`) have **no** `index=True` on their columns — `account_id` is the sole column with this double declaration, which strongly indicates the `index=True` flag is the accidental duplicate.
2. The two indexes are **definitionally equivalent** (verified: same table, same single column `account_id`, both non-unique). No foreign key or constraint references an index name, so no schema-level dependency distinguishes them. They are redundant physical objects.
3. The verify DB (H2′-built, at head) **physically contains both names** — the redundant pair is live, not hypothetical.

**Disposition — BLOCKED (schema-owner decision required):** the canonical index name must be chosen explicitly before the H3 root is authored, because `f91075478868` will no longer own the creation path. The evidence favours **`ix_payment_identity_account`** (the hand-named `__table_args__` index and the retired migration's name), with the redundant `index=True` on `account_id` removed from the model — but this agent does **not** choose the name. Recorded as a follow-up; no silent resolution.

## A.6 H3 transition safeguards (requirements for the subsequent implementation)

Recorded as mandatory for the later, authorized implementation — not performed here:

1. **Handle every existing database state explicitly:** empty, root-stamped, intermediate-revision, current-head, and unknown-revision. Per-state commands; reject ambiguous states and **stop for investigation rather than guessing**.
2. **Capture an independent schema-parity artifact** before any stamp or transition that depends on physical equivalence (register item 17a condition 5).
3. **Do not stamp solely because `alembic_version` matches** — same-ID/different-schema is field-proven (items 14, 14a, 17b).
4. **Retain the existing archive convention** — `migrations/_retired_versions/`. Do not invent a new archive directory.
5. **Define rollback as the documented H3 re-tracking/re-stamping recovery procedure**, subject to verified parity — **not** as an assumed destructive downgrade. (Consistent with §6.1/§10 of the original plan: the baseline downgrade is intentionally disabled; recovery = verified backup restore.)

---
---

# Addendum B — 2026-10-17 — `db.create_all()` as a Supported Schema-Creation Path (separate workstream)

**Status:** INVESTIGATION / DOCUMENTATION ONLY — no application code or migration modified; nothing staged or committed.
**Database activity (corrected §B.7):** this workstream performed **READ-ONLY introspection** of the disposable verification database `afcon360_verify_20261017_test` (see §B.7 for the exact reads). **No database was created, altered, written, reset or dropped;** protected databases `afcon360_prod` / `afcon360_test` were **not** accessed. The earlier §0–§11 "no database read or written" claim is scoped to that **source-only AST phase only** and is preserved unchanged there.
**Scope:** Make `db.create_all()` a **deliberately supported PostgreSQL bootstrap path** whose capabilities and parity limitations are explicit. This is **not** merged into the H3 Alembic root; the two paths are separated (§B.3).

## B.1 Phase 1 — Trace of the current `create_all()` path

### B.1.1 Call sites

| Site | Behaviour | Evidence |
|---|---|---|
| `tests/conftest.py` | Conditionally `db.create_all()` only if `"users"` absent; then **unconditionally** `alembic_stamp(revision="head", purge=True)` | `:255-256` (conditional create_all), `:261` (unconditional stamp) |
| `scripts/setup_test_db_schema.py` | Unconditionally `db.create_all()`; then `flask db stamp head`; then a **narrow** verify (3 accommodation tables + `users`/`events` existence) | `:152`, `:156-167`, `:180-230` |
| H2′ root `8a0deccce6f6` (working tree, dirty) | `db.metadata.create_all(op.get_bind())` at the historical root — superseded direction; **H3 replaces this** | register item 17; dirty working tree |

**Doctrine split (register item 12):** `docs/POSTGRES_TESTING_CONTRACT.md` mandates migrate-then-test; constitution §21 and `tests/conftest.py:254-262` mandate conditional `create_all` + stamp. Two incompatible official paths coexist.

### B.1.2 Model registration completeness (`app/core/model_registry.py`)

`register_all_models()` is called before `db.init_app()` (per its docstring and the app factory). Its reliability is **uneven**:

- **Accommodation** (`:49-81`): `except ImportError` **logs an error** (deliberately not silent) — fixed so `create_all()` cannot silently omit accommodation tables.
- **Notifications** (`:169-202`): logs an error on failure.
- **Silent `except ImportError: pass`** on: events (`:84-89`), wallet payment config (`:92-95`), transport (`:104-123`), transport permissions (`:127-129`), admin moderation (`:132-136`), audit (`:139-142`), KYC (`:145-148`), individual verification (`:151-154`), compliance (`:157-160`), AML (`:164-167`), feed (`:205-208`), fan (`:211-214`), media (`:217-220`), wallet config (`:223-226`), GEO (`:230-233`).

**Consequence (Phase 2, requirement 1):** a silent import failure in any of those 15 domains yields an **incomplete `db.metadata`** and therefore an incomplete `create_all()` **with no error surfaced**. This directly violates the intended contract that "every intended model is registered before creation begins." The docstring's claim that this entry makes registration "independent of blueprint registration" holds only for accommodation.

### B.1.3 Native ENUM handling — full ownership reconciliation (all 47 names)

**Empirical reconciliation (live `db.metadata` walk after `register_all_models()` + app init), cross-checked three ways:**

| Cross-check | Result |
|---|---|
| Live `db.metadata` distinct enum names | **47** = **39 Group A** (`create_type=False`) + **8 Group B** (`create_type=True`/implicit), **0 other** |
| Live metadata vs doc §3 (AST) | identical name set |
| Live metadata vs doc §6.2 `CREATE TYPE` literals — name presence | **0** differences (doc-not-meta NONE; meta-not-doc NONE) |
| Live metadata vs doc §6.2 — **exact label order** | **0 mismatches** |
| Live metadata vs doc §6.2 — Group-A/B assignment | **0** symmetric difference |
| Live metadata vs **physical `pg_enum`** (verify DB, read-only) | **all 47 present, 0 label mismatches**; verify DB holds 49 = the 47 + `bookingstatus` + `org_business_category` |

**Single creation owner per type — exactly one, no overlap:**

- **Group A (39 names) → owner = the explicit bootstrap pre-create block (§B.5 item 2).** SQLAlchemy suppresses `CREATE TYPE` for these (`create_type=False`), so nothing else creates them; without the pre-create, `create_all()` fails with `UndefinedObject` (§1, `transactiontype`).
- **Group B (8 names) → owner = SQLAlchemy `db.create_all()` itself** (`create_type=True`/implicit default). `create_all()` emits `CREATE TYPE` for these during `CREATE TABLE`; the bootstrap must **NOT** pre-create them, or the `CREATE TABLE` hits "type already exists".

**Therefore the bootstrap pre-creates 39, not 47.** The prior §B.5 wording ("pre-create the 47") is corrected in this revision (see §B.8). `persistence` = `NAMES` persists member names; `VALUES` persists member values (`values_callable`) — the label lists in §3/§6.2 are the **persisted** labels, verified equal to physical `pg_enum` above.

| # | type (Group A — pre-create) | persists | labels |
|---|---|---|---:|
| 1 | `apicallstatus` | NAMES | 4 |
| 2 | `auditseverity` | NAMES | 4 |
| 3 | `compensationmodel` | NAMES | 11 |
| 4 | `compliance_decision` | VALUES | 3 |
| 5 | `compliance_enforcement_level` | VALUES | 3 |
| 6 | `compliancestatus` | NAMES | 6 |
| 7 | `contractstatus` | NAMES | 6 |
| 8 | `currency` | NAMES | 10 |
| 9 | `dataaccesstype` | NAMES | 4 |
| 10 | `doc_verification_status` | VALUES | 3 |
| 11 | `entity_type` | VALUES | 2 |
| 12 | `gateway_environment` | NAMES | 2 |
| 13 | `gender_enum` | VALUES | 4 |
| 14 | `id_type_enum` | VALUES | 4 |
| 15 | `incidentseverity` | NAMES | 5 |
| 16 | `ind_document_type` | VALUES | 4 |
| 17 | `ind_verification_status` | VALUES | 5 |
| 18 | `kyb_doc_status` | VALUES | 3 |
| 19 | `kyc_level_enum` | VALUES | 3 |
| 20 | `org_change_source` | VALUES | 3 |
| 21 | `org_change_type` | VALUES | 5 |
| 22 | `org_kyb_check_status` | VALUES | 4 |
| 23 | `org_kyb_check_type` | VALUES | 5 |
| 24 | `org_lifecycle_state` | VALUES | 5 |
| 25 | `org_verification_status` | VALUES | 6 |
| 26 | `payment_gateway_provider` | NAMES | 12 |
| 27 | `paymentstatus` | NAMES | 8 |
| 28 | `propertydocumentstatus` | NAMES | 4 |
| 29 | `propertydocumenttype` | NAMES | 6 |
| 30 | `providertype` | NAMES | 5 |
| 31 | `risk_tier` | VALUES | 3 |
| 32 | `rvpcr_status_enum` | NAMES | 5 |
| 33 | `servicetype` | NAMES | 8 |
| 34 | `transactiontype` | NAMES | 10 |
| 35 | `ubo_type` | VALUES | 2 |
| 36 | `vehicleclass` | NAMES | 6 |
| 37 | `verification_status_enum` | VALUES | 4 |
| 38 | `verificationtier` | NAMES | 4 |
| 39 | `window_mode_enum` | NAMES | 2 |

| # | type (Group B — SQLAlchemy `create_all()` owns; bootstrap must NOT pre-create) | persists | labels |
|---|---|---|---:|
| 1 | `applicationstatus` | NAMES | 6 |
| 2 | `compliancecasepriority` | NAMES | 4 |
| 3 | `compliancecasestatus` | NAMES | 7 |
| 4 | `compliancecasetype` | NAMES | 8 |
| 5 | `compliancereporttype` | NAMES | 7 |
| 6 | `datasubjectrequeststatus` | NAMES | 6 |
| 7 | `datasubjectrequesttype` | NAMES | 5 |
| 8 | `marketplacelistingstatus` | NAMES | 6 |

- Under `create_all()`, `create_type=False` **suppresses `CREATE TYPE`**. A bare `create_all()` on an empty schema therefore does **not** create the 39 Group-A types, and any table whose column references them fails with `UndefinedObject` — the same class of failure recorded in §1 (`transactiontype`).
- This is **not** solved by removing `create_type=False` (forbidden in Phase 2) nor by a speculative `ensure_all_enums()` helper (register item 11a: it never existed). The 39 Group-A types need the **one explicit creation owner** in §B.5 item 2, created **before** dependent tables.
- **Distinct from the H3 §6.2 block:** §6.2 creates all 47 because the H3 Alembic root renders *every* table column with `create_type=False` (§6.3), so in H3 **all 47** need an explicit owner (its Group-B caution = open decision D6). The `create_all()` path is different: here Group B stays with SQLAlchemy. Do not conflate the two ownership models.

### B.1.4 Migration-managed objects absent from model metadata

Read-only introspection of the verify DB (at head) vs `db.metadata`:

| Object class | Present in DB | Absent from model metadata | Creator | `create_all()` can create it? |
|---|---|---|---|---|
| Triggers | `trg_guard_user_roles_delete` (BEFORE DELETE on `user_roles`), `trg_guard_users_delete` (BEFORE DELETE on `users`) | **Yes — absent** | `guard_delete_v1` | **No** (SQLAlchemy does not model triggers) |
| Functions | `guard_user_roles_delete()`, `guard_users_delete()` | **Yes — absent** | `guard_delete_v1` | **No** |
| Extensions | `plpgsql` only | n/a (cluster default) | n/a | n/a |
| Server defaults | 145 columns (item 28a) | migration-emitted only in 132 cases | migrations | **No** for the migration-only side |
| Indexes (4 agent tables) | `agent_float_accounts` / `agent_float_ledgers` / `agent_onboarding_approvals` / `agent_onboardings` — model declares BaseModel `created_at`/`updated_at`/`is_deleted` indexes absent in DB | model-only | `c2f495a06ed4` (migration DDL) | Divergent — migration-built DBs lack them; `create_all()`-built DBs would have them |
| Payment-identity index pair | both `ix_payment_identity_account` and `ix_payment_identities_account_id` physically present (§A.5) | model double-declares | H2′ root + `f91075478868` | `create_all()` would create **both** (redundant) |

**These objects require an explicit disposition** (Phase 2, requirement 4). `create_all()` will never produce the guard triggers/functions; a `create_all()`-built database is therefore **not** migration-equivalent by construction.

### B.1.5 The false-stamp risk

`tests/conftest.py:261` executes `alembic_stamp(revision="head", purge=True)` **unconditionally**, after only an `"users"`-table existence check (`:255`). `tests/postgres_contract.py:assert_migrated_postgres_database` then **passes** because `alembic_version == head` and the two required tables (`alembic_version`, `users`) exist. Neither check compares physical schema against the migration-built expectation. This is precisely the "false Alembic head stamp" the contract forbids (§B.2, requirement 6), and it is the mechanism behind the 145 default-diffs (item 28a): a `create_all()`-built test DB is stamped as if migration-built, then prod/test parity silently diverges.

## B.2 Phase 2 — The correct contract

The intended outcome is a reliable PostgreSQL model-based bootstrap that does **not** silently claim migration-equivalence. The six required properties, mapped to the findings:

1. **Complete registration before creation.** Every silent `except ImportError: pass` in `model_registry.py` must be converted to a logged/hard failure (mirroring accommodation `:49-81`). Until then, requirement 1 is **not met**.
2. **Exactly one explicit creation owner per native enum, with exact name and labels** (reconciled for all 47 in §B.1.3). **Split ownership, no overlap:**
   - **39 Group-A types → owner = the bootstrap pre-create block** (§B.5 item 2), run **before** `create_all()`. Source of truth for their exact persisted labels = the verified §3/§6.2 set (0 mismatches vs live metadata and physical `pg_enum`).
   - **8 Group-B types → owner = `db.create_all()` itself.** The bootstrap must **not** pre-create these; doing so makes `CREATE TABLE` fail with "type already exists".
   No duplicate-creation failures; no reliance on `create_all()` to emit Group-A DDL (suppressed by `create_type=False`). This replaces the earlier "pre-create the 47" wording (§B.8 correction 1).
3. **Full inventory** of expected tables, indexes, constraints, foreign keys and server defaults (this document §3 + register item 17b provide the enum/table parts; the 145 defaults and the agent-table index gap remain open).
4. **Explicit disposition for every migration-managed object absent from model metadata** — the 2 guard triggers, 2 guard functions, migration-only server defaults, the agent-table index divergence, and the payment-identity index pair (§A.5). Each gets a documented owner; nothing is copied indiscriminately into startup code.
5. **Independent comparison against the approved H3 schema** — a parity artifact captured before any parity claim.
6. **No false Alembic head stamp.** `conftest.py:261` must not stamp `head` unconditionally. `tests/postgres_contract.py` currently passes on a `create_all()`-built DB only because `alembic_version == head` and `alembic_version`/`users` exist — it never compares physical schema. This is a **design defect that must be resolved before any parity claim**; the two candidate designs are specified in §B.6. The gate (§B.5, G5) stays **BLOCKED** until one design is chosen and implemented.

**Explicitly forbidden solutions (per task):** blindly removing `create_type=False`; adding a speculative `ensure_all_enums()` helper; relying on `create_all()` to alter existing tables. `db.create_all()` is **not** a schema-migration mechanism.

## B.3 Phase 3 — Separation of the supported paths

| Path | Role |
|---|---|
| **H3 / Alembic** (N-squash root + retired chain) | The **authoritative** installation and upgrade path. Owns enum creation, triggers, functions, server defaults, and all migration-managed objects. |
| **`db.create_all()`** | A **deliberately supported PostgreSQL bootstrap path** (test/dev convenience). Its capabilities and parity limitations are explicit: it creates model-declared tables/indexes/constraints and can create the 8 Group-B enums, but it does **not** create the 39 Group-A enums (suppressed), guard triggers/functions, or migration-only server defaults. |

If full convergence requires **additional model metadata** (e.g., removing the redundant `index=True` on `payment_identities.account_id`, or adding missing BaseModel indexes to the 4 agent tables) or **supplemental idempotent PostgreSQL DDL** (e.g., a guarded trigger/function bootstrap), that requirement must be **identified and its ownership established before implementation**. Do not copy migration operations indiscriminately into startup code.

## B.4 Phase 4 — Verification requirements (not yet run)

Must use only an explicitly authorized, disposable PostgreSQL verification database. Protected databases (`afcon360_prod`, `afcon360_test`) and the existing verification database are **not** to be modified or reset.

Acceptance tests must prove:

1. Creation from a genuinely **empty** PostgreSQL schema.
2. Exact enum + table creation with **no** duplicate-type failures.
3. Completeness of tables, indexes, constraints, foreign keys, defaults.
4. Independent comparison with the **H3 schema** (parity artifact).
5. **Safe repeated invocation** where idempotency is intended.
6. Correct behaviour when a required object or model is **missing**.
7. **No false Alembic head stamp** and **no silent fallback** after failure.

**Do not report parity until every difference has been classified and resolved or explicitly accepted.**

## B.5 Minimal implementation plan and gates

Proposed (not implemented; needs authorization):

1. Convert silent `ImportError` handlers in `model_registry.py` to logged/hard failures (15 sites) — makes registration failure loud.
2. Pre-create **only the 39 Group-A types** (§B.1.3), each via a **PostgreSQL-supported existence-checking `DO` block** — **not** `CREATE TYPE ... IF NOT EXISTS`, which **PostgreSQL does not support** for `CREATE TYPE` (PG 15 `sql-createtype.html` shows no `IF NOT EXISTS` option in any of the four forms). Run this block **before** `create_all()`. Group B is **not** pre-created (owned by SQLAlchemy). Not by removing `create_type=False`; not by an `ensure_all_enums()` helper.

   Template (per type; exact labels from the verified §3/§6.2 set, shown for `transactiontype`):

   ```sql
   DO $afcon360_enum$
   BEGIN
       IF NOT EXISTS (
           SELECT 1 FROM pg_type t
           JOIN pg_namespace n ON n.oid = t.typnamespace
           WHERE t.typname = 'transactiontype' AND n.nspname = current_schema()
       ) THEN
           CREATE TYPE transactiontype AS ENUM
               ('DEPOSIT','WITHDRAWAL','TRANSFER','REFUND','FEE','REVERSAL',
                'CURRENCY_EXCHANGE','COMMISSION','PAYOUT','EXCHANGE');
        ELSE
            IF (SELECT array_agg(e.enumlabel::text ORDER BY e.enumsortorder)
                FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'transactiontype' AND n.nspname = current_schema())
               IS DISTINCT FROM ARRAY['DEPOSIT','WITHDRAWAL','TRANSFER','REFUND','FEE','REVERSAL',
                                      'CURRENCY_EXCHANGE','COMMISSION','PAYOUT','EXCHANGE']::text[] THEN
               RAISE EXCEPTION 'ENUM label mismatch for type %.%',
                               current_schema(), 'transactiontype';
           END IF;
       END IF;
   END
   $afcon360_enum$;
   ```

   **Existence check** = `pg_type` + `pg_namespace` filtered on `n.nspname = current_schema()` (PG 15 §53.64). **Label check** = `pg_enum` joined to `pg_type` **and** `pg_namespace`, **also filtered on `n.nspname = current_schema()`**, ordered by `enumsortorder` (PG 15 §53.20), compared **exactly** (order + case + membership) against the expected array. **Both sides are explicitly cast to `text`/`text[]`** (`enumlabel::text` in the aggregate; `ARRAY[...]::text[]` on the literal), so the `IS DISTINCT FROM` comparison is performed on a single, unambiguous element type rather than relying on `name`-to-`text` coercion. A mismatch **raises and stops**; it is never silently accepted or auto-corrected. Labels are case- and whitespace-sensitive (PG 15 §8.7.4), so the comparison is literal.

   **Schema-scoping must be identical in both branches, for every one of the 39 Group-A instantiations.** Each of the 39 `DO` blocks is generated from this one template and differs only in the type name and label array. Both the existence branch and the label branch carry the `pg_namespace` join **and** the `n.nspname = current_schema()` predicate. A label check filtered by `t.typname` alone would `array_agg` labels across **every** schema holding a same-named type (enum type names are schema-scoped, not globally unique), which can produce a spurious mismatch — or worse, silently mask a real one in the target schema. This is the exact defect this correction removes; the schema-scoped form is therefore mandatory and uniform across all 39.
3. Gate `alembic_stamp(revision="head")` in `conftest.py` behind the stamping design chosen in §B.6; **fail rather than stamp** when the check cannot run.
4. Disposition the migration-managed objects (§B.1.4): guard triggers/functions must be created by the bootstrap (or their absence explicitly accepted for test-only DBs).
5. Resolve the payment-identity index pair (§A.5) as part of the H3 root authoring decision, not separately.

**Gates (G5 PASS at source level; the rest remain blocked on execution or H3):**

| Gate | Result | Reason |
|---|---|---|
| G1 — `create_all()` builds from empty without enum failure | **DEFERRED** | The 39-type Group-A `DO`-block pre-create is implemented (`app/core/model_bootstrap.py`) and its SQL is unit-tested, but running it needs a disposable PostgreSQL target, which does not exist. |
| G2 — Completeness vs H3 schema (tables/indexes/constraints/FKs/defaults) | **BLOCKED** | H3 root not yet authored; parity artifact impossible. Design 2 deliberately does not claim physical equivalence. |
| G3 — Idempotent repeated invocation | **DEFERRED** | Implemented (a verified, fingerprint-matching model-bootstrap database validates and returns; any mismatch raises). Not executed against a live database. |
| G4 — Missing-object/model failure behaviour | **PARTIAL** | Registration-failure guard implemented and proven by test (checked before any metadata/engine access); partial-schema behaviour implemented via the `building` marker. Live execution still blocked. |
| G5 — No false stamp | **PASS** (source level) | Unconditional `alembic_stamp(head)` removed from all four provisioning paths; `tests/postgres_contract.py` rejects a marked database; `docs/POSTGRES_TESTING_CONTRACT.md` amended. `test_pytest_code_does_not_use_sqlite_or_schema_ddl` moved FAIL(3) → PASS(0). Live end-to-end proof still blocked. |
| G6 — Migration-managed object dispositions | **BLOCKED** | 28a defaults + trigger/function ownership undecided. |
| G7 — Exact-label validation on pre-existing types | **DEFERRED** | `DO`-block label check implemented exactly as specified in §B.5 item 2 (schema-scoped, `enumlabel::text`, `ARRAY[...]::text[]`, `RAISE EXCEPTION`, no `IF NOT EXISTS`) and covered by unit tests; not yet executed against a live type. |

## B.6 Stamping contract — **DECISION RECORDED: Design 2** (G5 resolved)

The false-stamp defect (§B.1.5) cannot be closed by a vague "gate the stamp" instruction. Exactly one of the following designs must be selected and implemented. Both are recorded below as the reviewed options; **the owner has chosen Design 2**.

**Design 1 — Parity-gated `head` stamp (full equivalence).**
- The test DB is built by `create_all()` + Group-A pre-create, then an **independent physical-schema comparison** against the approved H3 schema must pass (tables, columns, types, nullability, defaults, indexes, constraints, FKs, enum types **and** labels) **before** `alembic_stamp(revision="head")` runs. Any difference → **do not stamp**, fail loudly.
- Consequence: to pass, the bootstrap must also produce the migration-managed objects `create_all()` cannot make (§B.1.4: 2 guard triggers, 2 guard functions, 132 migration-only server defaults). **Full parity is therefore not achievable by `create_all()` alone** — Design 1 requires extending the bootstrap to cover those objects (or accepting their documented absence as an explicitly enumerated exception list that the comparison skips).
- Testing contract: `docs/POSTGRES_TESTING_CONTRACT.md` and constitution §21 remain as-is (migrate-or-equivalent, stamped `head`).
- Cost: highest; but a stamped `head` is then truthful.

**Design 2 — Separate model-bootstrap state (never `head`).**
- The test DB is explicitly labelled a **model-bootstrap** revision (e.g. stamp a dedicated sentinel revision id, or record a non-Alembic marker) and is **never represented as Alembic `head`**. It is supported by an **explicitly amended testing contract** that states: the test schema is derived from model metadata, is *not* migration-equivalent, and that migration-path tests (items 31, 34, 35, 37) must run against a **separately provisioned migration-built** DB, not the model-bootstrap one.
- `tests/postgres_contract.py` must then **reject** a model-bootstrap DB for any assertion that claims migration equivalence, instead of passing it (today it passes — that is the bug).
- Cost: lower to implement; but it splits test provisioning into two databases and amends the published testing contract.
- Truthfulness: this design is the honest reflection of the current facts — `create_all()` genuinely cannot produce triggers/functions/migration-only defaults, so calling its output `head` is a mislabel.

**Recommendation (superseded by the decision below):** Design 2 is the accurate description of what `create_all()` produces today and requires no hidden assumptions; Design 1 is the convergence goal and is only reachable once §B.1.4 objects are owned by the bootstrap.

### Decision — Design 2 adopted

`db.create_all()` is a separately identified PostgreSQL **model-bootstrap** path. It is **never** stamped or represented as Alembic `head`. H3/Alembic stays the authoritative installation and upgrade path; this decision does **not** rewrite the H3 root.

| Element | Decision |
|---|---|
| Marker | Dedicated non-Alembic table `afcon360_model_bootstrap`, single row keyed `afcon360-model-bootstrap`, holding `status` and a model-derived `fingerprint`. Deliberately outside `db.metadata`, so `create_all()` cannot create it and the ORM cannot see it. No fabricated revision is ever written to `alembic_version`. |
| State transitions | `empty` → write marker `building` → pre-create Group-A types → `db.create_all()` → validate → marker `complete`. The marker flips to `complete` only after validation, so a failed bootstrap never leaves a valid-looking success marker. |
| Non-empty databases | Only a genuinely empty database is bootstrapped. `migration_built_at_head`, `migration_built_not_at_head`, `model_bootstrap_building`, `unmarked_nonempty` and `contradictory` all stop with an actionable description; nothing is dropped, repaired, migrated or stamped. Repeating against a verified, fingerprint-matching model-bootstrap database validates and returns. |
| Registration guard | `app/core/model_registry.py` records every `except ImportError` into `registration_failures()`. `bootstrap_model_schema()` checks it **first**, before any metadata or engine access, and refuses an incomplete model set. Global startup stays non-fatal, because no domain is currently failing (0 failures) and making startup fail globally is not established as safe. |
| Enum ownership | 39 Group A (`create_type=False`) pre-created explicitly with schema-scoped exact-label validation; 8 Group B left to `db.create_all()`. The reviewed §B.1.3 inventory is embedded as drift detection, so a model change cannot silently move a type between owners. No `CREATE TYPE IF NOT EXISTS` (unsupported on PostgreSQL 15), no removal of `create_type=False`, no `ensure_all_enums()`. |
| False-stamp removal | The unconditional `alembic_stamp(revision="head", purge=True)` was removed from `tests/conftest.py`, `scripts/setup_test_db_schema.py`, `scripts/setup_test_db.py` and `tests/browser/start_test_server.py`; the dead `stamp` import was removed from `tests/check_alembic.py`. Two of these (`scripts/setup_test_db.py`, `tests/browser/start_test_server.py`) were **not** in the original call-site list and were found by tracing. |
| Migration-equivalence | `tests/postgres_contract.py` now rejects a marked database. `docs/POSTGRES_TESTING_CONTRACT.md` documents the two paths, adds the empty/marked state transitions, and states that pytest never provisions or repairs schema and never stamps head. |

**Evidence:** 32/32 focused `no_database` tests pass; `test_database_contract.py::test_pytest_code_does_not_use_sqlite_or_schema_ddl` moved **FAIL (3) → PASS (0)**; the 72 `test_application_and_pytest_code_do_not_embed_sql_text` violations are unchanged and pre-existing, with **no new violation introduced** (the new module and tests use the SQLAlchemy expression API and declared `pg_catalog` tables, not `text()`). Alembic head remains `df55cbe3f516`.

**Not closed by this decision:** end-to-end DB verification of a fresh bootstrap is **BLOCKED** — no authorized disposable PostgreSQL target exists, and `afcon360_prod` / `afcon360_test` / the verify database are out of bounds for `create_all()`. The 145 migration-only server defaults, the `organisations.business_category` type conflict, the 4 agent-table index gap, the payment-identity index pair and the guard-trigger/default dispositions remain open for H3 (§B.1.4, §B.8).

## B.7 Database activity — read-only inspection vs modification (§B status correction)

To keep the evidence accurate, the activity statement is stated explicitly:

| Activity | Performed? | Target |
|---|---|---|
| Read-only introspection (`information_schema` / `pg_catalog` / `pg_enum` / `pg_type` / SQLAlchemy `inspect()`) | **YES** | disposable `afcon360_verify_20261017_test` |
| — payment-identity index inventory (§A.5) | yes (read) | verify DB |
| — triggers / functions / extensions inventory (§B.1.4) | yes (read) | verify DB |
| — `pg_enum` exact-label comparison for all 47 enum types (§B.1.3) | yes (read) | verify DB |
| — live `db.metadata` enum walk (in-process, no DB write) | yes (read) | app metadata |
| `CREATE` / `ALTER` / `DROP` / `INSERT` / `UPDATE` / `DELETE` | **NO** | — |
| Database created / reset / dropped | **NO** | — |
| Protected DBs `afcon360_prod` / `afcon360_test` accessed | **NO** | — |
| Migration run / stamped / applied | **NO** | — |
| Application code, models or migrations modified | **NO** | — |
| Anything staged or committed | **NO** | — |

The original §0/§8 statement "No database was read or written for this verification" remains **correct for the source-only AST phase (§0–§11)** and is preserved unchanged. It does **not** describe this addendum session, which performed the read-only inspections listed above against the disposable verification database only. No write, reset or destructive operation was performed on any database in either phase.

## B.8 Corrections applied in this revision (2026-10-17)

| # | Prior (defective) statement | Correction | Trigger |
|---|---|---|---|
| 1 | §B.5 item 2: "Pre-create the **47** enum types (§6.2 block)… owned by this workstream" — contradicted §B.3 ("`create_all()` … can create the 8 Group-B enums"). Two owners for Group B. | Pre-create **only the 39 Group-A** types; Group B stays owned by SQLAlchemy `create_all()`. Full 47-name ownership reconciliation added at §B.1.3. | Task item 1 |
| 2 | §B.2 req 2: "Reuse the §6.2 `CREATE TYPE` block as the single source of truth" (all 47) for the `create_all()` path. | §6.2 is the **H3** ownership layer (all 47, because H3 renders every column `create_type=False`). The `create_all()` path uses Group-A-only ownership. Two ownership models now explicitly distinguished. | Task item 1 |
| 3 | §B.5 item 2: "`CREATE TYPE ... IF NOT EXISTS`-style bootstrap". | PostgreSQL **does not support** `IF NOT EXISTS` for `CREATE TYPE`. Replaced with a `DO` block using `pg_type`/`pg_namespace` existence check + `pg_enum`-based **exact label validation** that **raises and stops** on mismatch. Added gate **G7**. | Task item 2 |
| 4 | §B.2 req 6 / §B.5 item 3: "gate the stamp behind a parity check" — left the stamping design unresolved while implying the gate was handled. | Both candidate designs specified in **§B.6**; recommendation stated but **no decision taken**; **G5 remains BLOCKED**. | Task item 3 |
| 5 | §B status: "no database changed" (incomplete — omitted the read-only inspection). | §B status rewritten + **§B.7** table added distinguishing read-only inspection from modification; earlier §0–§11 claim preserved as scoped to that phase. | Task item 4 |

**Nothing in Addendum A or B modifies application code, migration files, or any database. The only change is this document.**
