# PostgreSQL Testing Contract

This repository uses PostgreSQL as the only database backend for tests. Tests
must exercise the same dialect, data types, constraints, transaction behavior,
and migration-managed schema used by the application.

## Behavioral specification

### Entities and inputs

- `TestingConfig` selects the database URL from `TEST_DATABASE_URL`, with the
  configured application database used only to derive a separate `_test`
  database when no explicit test URL is supplied.
- The pytest application fixture owns the SQLAlchemy engine used by database
  tests.
- The database operator owns creation and migration of the test database;
  tests do not create, alter, or repair schema.

### Required outputs and invariants

For every pytest session:

1. The configured SQLAlchemy dialect is `postgresql`.
2. The connection can complete an SQLAlchemy expression equivalent to
   `SELECT 1`.
3. The test database contains the migrated application schema.
4. The database `alembic_version` matches the repository's single migration
   head; a stale or divergent revision fails the session.
5. Database tests use model queries, SQLAlchemy expressions, and the shared
   fixtures; they do not embed SQL strings or use SQLite.
6. A failed connection, wrong dialect, missing schema, schema drift, or
   migration divergence fails
   the session. It must not be hidden with a skip flag or a fallback backend.

### State transitions

| Condition | Result |
|---|---|
| PostgreSQL URL and connectivity check succeed | Test session may run |
| URL uses any other dialect | Test session fails before tests run |
| PostgreSQL is unreachable | Test session fails before tests run |
| Required schema is absent | Test session fails with setup instructions |
| Database revision differs from the single migration head | Test session fails with the expected and actual revisions |
| A test needs schema changes | Add and review a normal Alembic migration; do not mutate schema in the test |

### Authority boundaries

- The application owns persistence behavior and must use SQLAlchemy model or
  expression APIs rather than handwritten SQL strings.
- Tests may create and persist fixture rows through models, but may not issue
  schema DDL or repair production/test schema.
- Operators apply migrations and provision `TEST_DATABASE_URL`; agents may
  propose migration commands but must not run them automatically.

## Running the suite

Set `TEST_DATABASE_URL` to a dedicated PostgreSQL database, apply the normal
Alembic migrations, and then run:

```powershell
$env:APP_ENV = "testing"
$env:FLASK_ENV = "testing"
$env:TEST_DATABASE_URL = "postgresql://postgres:password@localhost:5432/afcon360_test"
& .venv\Scripts\python.exe -m flask --app 'app:create_app()' db current
& .venv\Scripts\python.exe -m flask --app 'app:create_app()' db heads
& .venv\Scripts\python.exe -m flask --app 'app:create_app()' db upgrade
pytest
```

The explicit factory target is required so Alembic and pytest resolve the
same `TestingConfig` and `afcon360_test` database. Review the migration plan
and database backup policy before applying `db upgrade`; agents and tests do
not apply migrations automatically.

When `APP_ENV=testing` or `FLASK_ENV=testing`, the Alembic environment also
rejects non-PostgreSQL URLs, non-`*_test` databases, and a migration target
that differs from `TEST_DATABASE_URL`. Pytest performs the same checks and
also requires the connected database revision to match the repository head.

Do not use `sqlite://`, `db.create_all()`, `db.drop_all()`, raw SQL strings, or
test-only schema repair scripts as substitutes for the migrated PostgreSQL
schema.

## What “SQL tests” means here

Direct SQL tests are not an option for this repository. A PostgreSQL-specific
behavior may be tested with SQLAlchemy constructs such as mapped model
statements, `select()`, `func`, `inspect()`, reflected table objects, and
PostgreSQL dialect compilation; SQLAlchemy generates the PostgreSQL SQL sent
to the configured database. If a test needs a schema change, add and review an
Alembic migration instead of embedding DDL or a SQL string in the test.

Source/parser/configuration checks may use the `no_database` marker because
they intentionally do not assert persistence. Any test that creates, queries,
updates, or deletes database rows must use the PostgreSQL fixture and fail when
the database is unavailable or stale.