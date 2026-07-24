# Fix Missing `system_configs` Table

## Root Cause
PostgreSQL is missing the `system_configs` table, but Alembic `alembic_version` is stamped to `2d264b2fdc99` (HEAD). The schema state and migration version are out of sync — the database was marked fully migrated without applying the `system_configs` creation.

## Evidence
- `app/accommodation/routes.py:490` queries `SystemConfig` → `system_configs`
- DB query confirms `system_configs` does not exist; only `wallet_system_configs` and `system_configurations` are present
- `flask db current` shows HEAD despite the missing table
- Revision `20260706_add_system_configs_table` exists and defines the table, but its parent migration `ba262522c43c_convert_accommodation_enums_to_strings` unconditionally drops `system_configs` in its upgrade path, making a naive stamp-back-and-upgrade unsafe

## Decision
Do **not** run `flask db upgrade` or patch migration files. Reconcile by creating the missing table directly via SQL (matching the model and latest migration intent), then stamp Alembic to HEAD so version and schema align.

## Plan

### 1. Create missing table directly
Run SQL matching `app/models/system_config.py` and `migrations/versions/0260706_add_system_configs_table.py`:

```sql
CREATE TABLE IF NOT EXISTS system_configs (
    id BIGSERIAL PRIMARY KEY,
    key VARCHAR(100) NOT NULL,
    value TEXT NOT NULL,
    description TEXT,
    created_by BIGINT,
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_system_configs_key ON system_configs(key);
CREATE INDEX IF NOT EXISTS ix_system_configs_created_at ON system_configs(created_at);
CREATE INDEX IF NOT EXISTS ix_system_configs_is_deleted ON system_configs(is_deleted);
CREATE INDEX IF NOT EXISTS ix_system_configs_key ON system_configs(key);
CREATE INDEX IF NOT EXISTS ix_system_configs_updated_at ON system_configs(updated_at);
```

### 2. Seed default accommodation configs
Insert defaults so the admin settings page renders without empty-state issues:
- `accommodation_module_enabled` = `true`
- `accommodation_max_photos` = `10`
- `accommodation_commission_rate` = `10.0`
- `accommodation_booking_hold_minutes` = `15`
- `accommodation_max_guests` = `10`
- `accommodation_enable_instant_book` = `false`
- `accommodation_default_cancellation_policy` = `moderate`
- `accommodation_require_guest_verification` = `true`
- `accommodation_max_bookings_per_user` = `5`

Use `INSERT ... ON CONFLICT (key) DO UPDATE` for idempotency.

### 3. Verify
- Re-run the temp check script to confirm `system_configs` exists
- Load `GET /accommodation/admin/settings` and confirm HTTP `200`
- Confirm `SystemConfig.query.filter(SystemConfig.key.like('accommodation_%')).count() > 0`

## Risks
- **Data-loss**: This is a dev DB (no sensitive production data indicated), so direct SQL is acceptable. If this is a shared DB, confirm no one depends on the missing table before proceeding.
- **Migration drift**: The DB remains stamped at HEAD while one table was created outside migrations. Future developers should be aware; consider running `flask db migrate` later to generate a proper migration that captures any further drift.
- **Secondary issue noticed**: `app/admin/owner/routes.py:747` raises `NameError: name 'owner_only' is not defined`, breaking the owner module. This is unrelated to the `system_configs` error but should be fixed separately.

## Verification Commands
```powershell
# 1. Confirm table exists
$env:PYTHONPATH = "C:\Users\OBED\Desktop\afcon360_app"; C:\Users\OBED\Desktop\afcon360_app\.venv\Scripts\python.exe -c "from app import create_app; app = create_app(); from app.extensions import db; from sqlalchemy import text; print(db.session.execute(text(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'system_configs'\")).fetchall())"

# 2. Test route
# Visit: http://127.0.0.1:5000/accommodation/admin/settings
```

## Open Questions
- Is the PostgreSQL instance local/dev only? If production or shared, escalate before mutating schema directly.
- Should the root migration inconsistency (HEAD stamp without full apply) be permanently fixed with a proper migration later?
