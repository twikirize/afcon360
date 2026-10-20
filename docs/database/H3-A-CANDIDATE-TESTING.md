# H3-A candidate generation and verification

## Scope and safety

H3-A authoring is authorized. This procedure builds an isolated candidate from the existing, validated H2-prime migration replay. It does not modify the active application migration chain or either protected database.

The source is fixed to the approved local disposable database afcon360_h2p_replay_20261018_test at Alembic revision df55cbe3f516 on PostgreSQL 18.4. Source connections and pg_dump are read-only. The builder stops on an unexpected revision, server version, public table count, enum count, or dump contents.

## 1. Fetch and run the source-only tests

From the repository root, in the existing virtual environment, run:

    python -m pytest --noconftest -q tests/test_h3_candidate_builder.py

A GitHub Actions workflow also runs these database-free tests. They do not connect to PostgreSQL.

## 2. Generate the candidate from the current chain output

Run:

    python scripts/h3/build_h3_candidate.py

The builder takes credentials from H3_BASELINE_SOURCE_DATABASE_URL when set. Otherwise it reuses local test connection settings from the existing environment or .env, but retargets the database name to afcon360_h2p_replay_20261018_test. It will only connect to localhost/127.0.0.1/::1 and rejects every database except that approved disposable source.

The builder requires a PostgreSQL 18 pg_dump client. It creates migrations/h3_candidate/versions/h3a20261020_static_baseline.py. It does not print the connection URL and does not put credentials into the generated artifact. If a candidate already exists, generation stops unless --replace is deliberately specified; preserve the prior candidate before regenerating it.

Review the generated source hash, the reported table/type counts, the complete SQL diff, and any extension/function/trigger/constraint statements before testing.

## 3. Test on a new, empty disposable candidate database

Create a new disposable database using the approved local PostgreSQL test procedure. Use a name such as afcon360_h3_candidate_test. Do not use afcon360_prod, afcon360_test, or the source replay database.

The isolated env.py defaults to that candidate name by reusing only local test credentials and changing the database name. An explicit H3_CANDIDATE_DATABASE_URL may be supplied, but it must target localhost and a database matching afcon360_h3_candidate*_test.

Run:

    alembic -c migrations/h3_candidate/alembic.ini upgrade head

The candidate environment checks that the target has no application relations, custom types, routines, extensions or extra schemas before Alembic starts. It refuses a non-empty target and never drops or resets one. If a candidate run fails after creating any objects, preserve that database as evidence and use a separately approved fresh disposable database for a retry; do not clean it automatically.

## 4. Compare the resulting physical schemas

After the candidate reaches head, run:

    python scripts/h3/compare_h3_candidate_schema.py --candidate-database afcon360_h3_candidate_test

The comparator connects read-only to only the approved H2-prime source and the specifically named local H3 candidate database. It verifies both revision IDs, PostgreSQL 18.4, the recorded table/enum counts and the same pg_dump client before comparing schema-only dumps. It excludes public.alembic_version and owner/privilege statements. If the definitions differ, it returns FAIL and writes a unified diff under the local temp directory; it never changes either database.

A PASS requires exact normalized schema text equality. The comparison preserves object definitions, defaults, enum labels/order, constraints, indexes, sequences, functions, triggers and extension/schema statements. A table count by itself is not parity proof.

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

Keep PostgreSQL 18.4 for the first reproduction because it is the recorded working environment. Before release/cutover, test the selected current 18.x minor as a separate compatibility gate. PostgreSQL minor releases are intended to deliver fixes with less risk than continuing to run an older minor, but do not combine that environment update with the first H3 baseline comparison.
