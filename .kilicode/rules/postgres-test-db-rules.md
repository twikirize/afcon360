# PostgreSQL Test Database Rules — AFCON360

The repository root `AGENTS.md` is the authoritative engineering constitution.
This rule exists to guarantee every Kilo run targets the **test** PostgreSQL
database (`afcon360_test`) and **never** the production database. It is
auto-loaded from `.kilicode/rules/` and applied to every Kilo session.

---

## 1. Core invariant

- **Never** connect to, mutate, or run migrations against `afcon360_prod`.
- Every Kilo session runs in **test mode against `afcon360_test`** unless a
  specific task explicitly and in writing authorizes otherwise.

If there is any doubt about which database a command will touch, stop and verify
the target before executing.

---

## 2. How the target database is chosen

### Selection order (Flask app factory, `app/config.py`)
1. `APP_ENV=testing` **or** `FLASK_ENV=testing` selects `TestingConfig`
   (see `config_map` at `app/config.py:471-478` and `get_config()` at
   `app/config.py:480-491`).
2. `TestingConfig` resolves the database URL
   (`app/config.py:421-442`) in this precedence order:
   1. `TEST_DATABASE_URL` env var (if set).
   2. `DATABASE_URL` env var — transformed by appending `_test` to the database
      name. **This is a hazard:** if `.env` exports `DATABASE_URL` pointing at
      `afcon360_prod`, the test run silently uses `afcon360_prod_test`, not
      `afcon360_test`.
   3. Default `postgresql://localhost:5432/afcon360_test`.
3. The base `Config` reads `DATABASE_URL`, then `DB_USER/DB_PASS/DB_NAME`
   (default `DB_NAME=afcon360_prod`, `app/config.py:114-124`).

### Required environment for every session
```powershell
Remove-Item Env:DATABASE_URL        -ErrorAction SilentlyContinue
Remove-Item Env:SQLALCHEMY_DATABASE_URI -ErrorAction SilentlyContinue
Remove-Item Env:DB_NAME             -ErrorAction SilentlyContinue
$env:APP_ENV   = "testing"
$env:FLASK_ENV = "testing"
```
This forces `TestingConfig` to fall through to the
`postgresql://localhost:5432/afcon360_test` default and makes `DATABASE_URL`
not present in `app.py`'s startup banner.

### Built-in safety guard
`migrations/env.py:56-85` `assert_testing_database()` runs only when
`APP_ENV`/`FLASK_ENV == testing`. It **raises `RuntimeError`** unless:
- the backend is PostgreSQL, **and**
- the database name ends with `_test`, **and**
- if `TEST_DATABASE_URL` is set, it matches the connection's host/port/db.

This guard is the last line of defense preventing a migration from targeting a
non-test database while `APP_ENV=testing`.

---

## 3. Base schema is NOT built by migrations

The first migration `ab6dd422c152_initial_schema` (`down_revision = None`,
created 2026-06-03) does **not** create the base tables. Its upgrade path
only:
- creates 3 standalone tables: `idempotency_keys`, `event_host_registrations`,
  `ledger_entries`;
- `ALTER`s tables that already exist (`users`, `organisations`, `events`,
  `event_registrations`, `event_assignments`, `accommodation_properties`, etc.).

Consequence: a from-scratch `flask db upgrade` on an **empty** database can
never build the schema, because the base tables are produced outside Alembic
(e.g. `db.create_all()` against a snapshot, or a `pg_dump` restore).

### What this means for Kilo
- Before running any migration or test against the test DB, the database must
  be restored from its snapshot/dump. This is a **human-owned** operation
  (migrations and DB lifecycle are human-owned per root `AGENTS.md:141-146`).
- After the snapshot restore, `flask db upgrade` applies only the incremental
  migrations from the snapshot's recorded `alembic_version` up to `(head)`.
- Kilo MUST inspect `flask db current` against the **restored** test DB and
  confirm it ends on `afcon360_test` before any further action.

---

## 4. Permitted vs. prohibited commands

### Inspect only (read-only, no DB mutation) — permitted
```powershell
$env:APP_ENV="testing"; $env:FLASK_ENV="testing"
.venv\Scripts\python.exe -m flask db heads
.venv\Scripts\python.exe -m flask db history
```
(`flask` is not on PATH; use `.venv\Scripts\python.exe -m flask`. These do not
connect to the database.)

### Connect to DB (target verification) — permitted only after restore
```powershell
.venv\Scripts\python.exe -m flask db current
```
Verify the resolved URL ends in `afcon360_test`.

### Mutations — NEVER executed by Kilo
- `flask db migrate` / `flask db upgrade` / `flask db downgrade` /
  `flask db stamp` — human-owned.
- Restoring `afcon360_test` from snapshot/dump — human-owned.

If a migration or schema change is required, Kilo reports the exact command and
the human executes it.

---

## 5. Running the test suite

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:DB_NAME -ErrorAction SilentlyContinue
$env:APP_ENV   = "testing"
$env:FLASK_ENV = "testing"
.venv\Scripts\python.exe -m pytest tests/<target>
```
`conftest.py:6` already sets `FLASK_ENV=testing` for pytest, but the env vars
above are set defensively so no inherited `DATABASE_URL`/`DB_NAME` can divert
the run to a non-test database.

---

## 6. Verifying the target

Before any DB-touching command, confirm:
```powershell
.venv\Scripts\python.exe -c "from app import create_app; a=create_app(); print('DB:', a.engine.url)"
```
The printed URL **must** end in `afcon360_test`. If it shows `afcon360_prod`
(or any non-`_test` name), stop: a stray `DATABASE_URL`/`DB_NAME`/
`SQLALCHEMY_DATABASE_URI` env var is overriding `TestingConfig`.

---

## 7. Quick checklist (every Kilo DB session)
1. Clear `DATABASE_URL`, `SQLALCHEMY_DATABASE_URI`, `DB_NAME`.
2. Set `APP_ENV=testing` and `FLASK_ENV=testing`.
3. Run `flask db heads` — confirm exactly one head.
4. Confirm `create_app().engine.url` ends in `afcon360_test`.
5. Only after the human restores `afcon360_test` from snapshot does
   `flask db current` / `flask db upgrade` become usable.
