# H3-A candidate generation and verification

## Scope and safety

H3-A authoring is authorized. This procedure builds an isolated candidate from the existing, validated H2-prime migration replay. Owner-approved support policy: a clean database is supported only after successful replay; an existing database at df55cbe3f516 is eligible only after independent per-database physical-schema parity and a reviewed transition plan; older revisions must be explicitly enumerated and tested; unknown or divergent states fail closed. This authorizes H3-A authoring and disposable verification only. It does not authorize H3-B cutover or modify the active application migration chain or either protected database.

The source is fixed to the approved local disposable database afcon360_h2p_replay_20261018_test at Alembic revision df55cbe3f516 on PostgreSQL 18.4. Source connections and pg_dump are read-only. The builder stops on an unexpected revision, server version, public table count, enum count, or dump contents.

## 1. Fetch and run the source-only tests

From the repository root, in the existing virtual environment, run:

    python -m pytest --noconftest -q tests/test_h3_candidate_builder.py tests/test_h3_candidate_apply.py

A GitHub Actions workflow also runs these database-free tests. They do not connect to PostgreSQL.

## 2. Generate the candidate from the current chain output

Run:

    python -m scripts.h3.build_h3_candidate --pg-dump "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"

The builder takes credentials from H3_BASELINE_SOURCE_DATABASE_URL when set. Otherwise it reuses local test connection settings from the existing environment or .env, but retargets the database name to afcon360_h2p_replay_20261018_test. It will only connect to localhost/127.0.0.1/::1 and rejects every database except that approved disposable source.

The builder requires a PostgreSQL 18 pg_dump client. It creates migrations/h3_candidate/versions/h3a20261020_static_baseline.py. It does not print the connection URL and does not put credentials into the generated artifact. If a candidate already exists, generation stops unless --replace is deliberately specified; preserve the prior candidate before regenerating it.

Review the generated source hash, the reported table/type counts, the complete SQL diff, and any extension/function/trigger/constraint statements before testing.

## 3. Create and apply to a new, empty disposable candidate database

Use PostgreSQL **18.4** for this first H3-A reproduction because it is the recorded working version. The future PostgreSQL minor-version update is a separate compatibility gate; do not change the working local version as part of this baseline comparison.

Run the read-only preflight first:

    python -m scripts.h3.apply_h3_candidate --candidate-database afcon360_h3_candidate_test --dry-run

If the database does not exist, create only that explicitly named disposable candidate database:

    python -m scripts.h3.apply_h3_candidate --candidate-database afcon360_h3_candidate_test --create-database

Then repeat the dry run and review the output. Only when it reports that the candidate exists, is empty, and is on PostgreSQL 18.4, apply the static baseline through the isolated Alembic environment:

    python -m scripts.h3.apply_h3_candidate --candidate-database afcon360_h3_candidate_test --apply

The apply wrapper verifies the candidate artifact's embedded SHA-256, root revision metadata, and Alembic registration before it acts. The script can create only a database whose name matches `afcon360_h3_candidate*_test`, through the loopback PostgreSQL server, using the UTF8 encoding recorded by the approved source. It refuses an existing database at creation time, refuses a non-empty database at apply time, and never drops, resets or cleans up a database. The Alembic environment independently enforces the loopback/name/empty-target/18.4 gates. If the local role lacks CREATEDB permission, create a new approved disposable database through the normal local administrator process; do not weaken the allowlist or point the tool at an existing application database.

If application fails after any objects appear, preserve that candidate database as evidence and use a different approved disposable name for a retry. Do not automatically drop or reset it.

## 4. Compare the resulting physical schemas

After the candidate reaches head, run:

    python -m scripts.h3.compare_h3_candidate_schema --candidate-database afcon360_h3_candidate_test --pg-dump "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"

The module-mode command is intentional: direct file execution (python scripts/h3/compare_h3_candidate_schema.py) can fail to resolve the scripts.h3 package import. The comparator connects read-only to only the approved H2-prime source and the specifically named local H3 candidate database. It verifies both revision IDs, PostgreSQL 18.4, the recorded table/enum counts and the same pg_dump client before comparing schema-only dumps. It excludes public.alembic_version and owner/privilege statements. If the definitions differ, it returns FAIL and writes a unified diff under the local temp directory; it never changes either database.

A PASS requires exact normalized schema text equality. The comparison preserves object definitions, defaults, enum labels/order, constraints, indexes, sequences, functions, triggers and extension/schema statements. A table count by itself is not parity proof.

## Separate preservation decision — business_category

Keep the existing `org_business_category` divergence separate from Item 13 support-state policy and track it as subordinate item 14c. Existing evidence records production as `varchar(40)` with a separate four-label lowercase orphan enum, while the test database uses a 39-label uppercase enum. Preserve and document the two physical states independently. No conversion, drop, relabel, normalization, or cross-database alignment is authorized by H3-A. The generated candidate reproduces the approved H2-prime replay only; it is not permission to transform either existing database.

## 5. Acceptance gate

H3-A is not PASS until:
- the candidate is committed as an isolated artifact with reproducible source provenance;
- source-only builder tests pass;
- an empty disposable candidate replay passes;
- full schema-only comparison against the approved H2-prime chain produces no unexplained difference;
- independent code review passes;
- the active migration chain is still untouched;
- no production/test database was accessed for writing.

H3-B remains a separate owner authorization. Existing databases must have per-database parity evidence, reviewed transition steps, backup/restore proof, populated-state migration safety tests, and a recovery plan before any cutover can be considered.

## PostgreSQL version note

PostgreSQL 18.4 is the selected H3-A verification target for this checkpoint, because it is the recorded working environment and the approved H2-prime replay source. PostgreSQL 18.4 is a real PostgreSQL release; the later patch/minor update is deferred, not treated as a defect in this baseline. Before release/cutover, separately confirm the hosting/provider support policy and replay on the then-selected 18.x release. Do not combine that environment update with the first H3 baseline comparison.
