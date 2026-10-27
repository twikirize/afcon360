# AFCON360 Database Reliability — Easy-to-Read 39-Item Register

**Updated: 27 October 2026**  
**Technical source of truth:** [Database Reliability Master Register](../../AFCON360_Database_Reliability_Master_To_Do_and_Fix_Register.md)  
**Replay evidence:** [GitHub Actions fresh-database Docker replay #40469733857](https://github.com/twikirize/afcon360/actions/runs/40469733857)  
**Branch:** `sandbox/codespaces-alembic-investigation` — this work has not been merged to `main`.

This is the human-readable companion to the technical register. It keeps the same official item numbers and current statuses, but explains them in everyday language.

## Where we are today

| Status | Count | What it means |
|---|---:|---|
| Closed | 24 | The specific task has the evidence required by its recorded acceptance criteria. This does not automatically mean the whole database project is finished. |
| Advanced | 10 | Good progress and some evidence exist, but important proof or decisions are still missing. |
| Partial | 1 | Some historical evidence exists, but the item is not fully settled. |
| Not started | 4 | The required work has not yet been completed. |
| Open / gated | 0 | No item currently uses those two labels in the reconciled register. Some items marked Advanced or Not started still block later work. |

## The Docker replay we just completed

**PASS — for the tested GitHub-hosted Docker environment.**

The repeated fresh-database replay on GitHub Actions built the application image, started PostgreSQL 18.6 and Redis, passed all **9 H3-A compatibility tests**, ran the regular migration chain to Alembic revision `1793013676`, checked the recorded schema shape (**226 public tables, 49 enums and 139 check constraints**) and received HTTP 200 from the application health endpoint.

That proves the tested clean-install path worked in that environment. It does **not** prove every Oracle Cloud, AWS or other server setup will work unchanged. The Codespaces-local Docker network issue is still unresolved, and the read-only census of existing environments remains outstanding. No production or test database was used as a scratch target by this replay.

**Corrected numbering:** You confirmed that 24 checkpoints had been completed before Docker, so the Docker replay is operational checkpoint **#25**, now **PASS**. In the canonical 39-item *Database Reliability Master Register*, top-level **Item 26** has a different defined meaning: testing migrations against databases that already contain data. That separate item is still **NOT STARTED** because an empty-database replay cannot prove that existing data will survive an upgrade. To avoid corrupting the official item definitions, the Docker replay is recorded under the deployment/replay evidence (Items 12 and 31) and as the separate checkpoint above.

## All 39 items in plain language

| # | Item in everyday language | Status | What it means / what remains |
|---:|---|---|---|
| 1 | Fix the first missing database type | **CLOSED** | The original `transactiontype` creation problem is addressed in the repaired clean-install migration path. Keep the successful replay as regression evidence. |
| 2 | Work out who creates each database enum | **CLOSED** | Enum ownership and references have been inventoried. Remaining enum differences are tracked separately under Item 21. |
| 3 | Map the migration history | **CLOSED** | The migration chain and its relationships are mapped. The hosted fresh-checkout replay now gives additional proof that the active chain can run to its expected head. |
| 4 | Identify the original baseline design problem | **CLOSED** | The baseline design was shown to be the source of repeated-creation/ownership risks; the diagnosis is recorded. |
| 5 | Identify repeated migration operations | **CLOSED** | The conflict inventory exists. Each source-predicted conflict must still be distinguished from an error actually observed during execution. |
| 6 | Separate the two ways the app creates a schema | **CLOSED** | Alembic migrations and model-bootstrap/`create_all` are separate routes and must not be silently substituted for one another. |
| 7 | Recover the historical evidence | **CLOSED** | Evidence was recovered and claims were narrowed where the available records did not prove the larger claim. |
| 8 | Agree the database architecture direction | **CLOSED** | H2′ is the interim fresh-install repair; H3/N-squash is the selected long-term direction. This is not permission to migrate existing databases. |
| 9 | Reconstruct how the original baseline evolved | **CLOSED** | Historical source and commit evidence is recorded separately from today's replay proof. |
| 10 | Verify the old claim of “182 tables from an empty database” | **PARTIAL** | The exact historical claim has not been fully evidenced. Do not substitute counts from a later replay as proof of the old claim. |
| 11 | Trace the enum-declaration changes | **CLOSED** | The relevant enum creation behavior and history are documented. Keep the corrected SQLAlchemy `create_type`/`checkfirst` explanation. |
| 12 | Establish what is deployed in existing environments | **ADVANCED** | The GitHub-hosted clean Docker replay now passes. The read-only census of existing databases/containers and their revisions is still outstanding; existing databases must not be used as scratch targets. |
| 13 | Decide which starting migration states are supported | **CLOSED** | The policy is documented: unknown or divergent states fail closed; existing databases need their own parity checks and a reviewed transition plan. This policy is not permission to upgrade them. |
| 14 | Compare the saved Reference, Production and Test schemas | **CLOSED** | The comparison work is complete and the differences are recorded. “Closed” means the comparison was done, **not** that the schemas are identical. |
| 15 | Write and verify the safe transition plan | **ADVANCED** | A reversible disposable probe migration passed. The full state-by-state runbook and recovery evidence for empty, intermediate, at-head and unknown databases remain incomplete. |
| 16 | Classify the different migration-conflict types | **CLOSED** | Root-versus-child and child-versus-child conflicts are separated, with evidence rather than assumptions. |
| 17 | Compare the interim and long-term architectures | **CLOSED** | The trade-offs are recorded, including fresh installs, old database states, enums and rollback implications. |
| 18 | Record the approved architecture choice | **CLOSED** | The H2′ interim / H3 long-term decision is recorded. It does not authorize the H3-B cutover. |
| 19 | Run the approved isolated H2′ replay | **CLOSED** | The historical disposable replay reached revision `df55cbe3f516` on PostgreSQL 18.4. The newer H3-A replay is separately recorded under Item 31 and the replay log. |
| 20 | Verify the separate model-bootstrap setup | **CLOSED** | The Design 2 bootstrap path passed its own runtime check on a disposable database. Do not confuse this with the Alembic migration path. |
| 21 | Settle remaining enum ownership differences | **ADVANCED** | H3-A contains 49 enums, while the B0 target expectation is 47. The owner-approved 49-versus-47 decision and related dispositions are still pending. Do not casually drop or convert types. |
| 22 | Ensure the window-mode enum is created only once | **CLOSED** | The verified H2′ clean-install path creates it once. Historical/intermediate starting states are a separate test. |
| 23 | Resolve duplicate slug creation on fresh install | **CLOSED** | The duplicate issue is resolved for the verified fresh-install chain. Historical/intermediate-state behavior remains a separate concern. |
| 24 | Finish classifying the remaining migration conflicts | **ADVANCED** | The older 324-row conflict matrix needs its remaining H3-A/B0 ownership and enum-dependency decisions completed. |
| 25 | Verify foreign keys against the models | **ADVANCED** | A duplicate model-side driver-profile FK declaration was corrected and tested. Broader column-level mapping is incomplete, and existing physical schemas still have differences that must not be repaired without authorization. |
| 26 | Test migrations when the database already has real data | **NOT STARTED** | This is **not** the Docker replay checkpoint. We still need populated disposable databases to test data preservation, new required columns, backfills, unique indexes, checks and foreign keys—including rejection of invalid data. |
| 27 | Resolve linked model and database differences | **ADVANCED** | The source fix is recorded, but physical foreign-key differences and database-specific qualification remain. No Production/Test writes or H3-B transition is authorized. |
| 28 | Understand the 145 differing database defaults | **ADVANCED** | Production and Test have 145 recorded server-default differences. Each must be classified for intent; do not force both databases to match by guessing. |
| 29 | Establish the permanent database engineering rules | **CLOSED** | The engineering rules are recorded. Ordinary migrations must come from reviewed source/configuration, and historical evidence must not be silently rewritten. |
| 30 | Keep safe disposable verification databases available | **CLOSED** | The approved replay databases are retained. Production and Test were not used as scratch databases; do not delete evidence volumes or databases. |
| 31 | Prove a clean install works from checkout to running app | **CLOSED** | This now has strong evidence: the hosted Docker run built the app, ran migrations from an empty PostgreSQL 18.6 database to `1793013676`, passed schema-count guards and returned HTTP 200. PostgreSQL 15 and other hosting environments still need their own compatibility verification. |
| 32 | Independently compare the physical schemas | **CLOSED** | Schema extraction and comparison artifacts are recorded. The fact that the comparison is complete does not mean the reported differences are resolved. |
| 33 | Check that application models and database tables match | **ADVANCED** | A scoped H3-A check matched 223 application tables to ORM metadata, but other model/schema differences remain. Session persistence, analytics-flush safety, defaults and the enum-scope decision still need evidence. |
| 34 | Verify a second migration run does not change the schema | **CLOSED** | The recorded repeat-at-head snapshots matched, and a separate disposable migration upgrade/downgrade round trip passed. Re-run the gate if later source changes invalidate its evidence. |
| 35 | Upgrade from supported older migration states | **NOT STARTED** | Each approved historical/intermediate revision needs a separate disposable database, representative data, upgrade tests and post-upgrade checks. |
| 36 | Verify data rules and constraints behave correctly | **ADVANCED** | The pickup-time CHECK conflict and a blind spot in constraint discovery were reproduced. The durable fix, approved instant-versus-scheduled timestamp behavior and a clean regression/cleanup run remain incomplete. |
| 37 | Compare a fresh schema with one upgraded from existing data | **NOT STARTED** | We need an independent physical-schema comparison between a clean install and a safely upgraded populated starting state. |
| 38 | Prove we can recover from a failed migration | **NOT STARTED** | A controlled disposable failure, recovery procedure and backup-restoration proof are still required. |
| 39 | Finish automated regression gates | **ADVANCED** | Some focused tests pass, and the Docker fresh-replay workflow passes. The complete test suite and remaining database integration, schema-diff, migration and cleanup/recovery gates are not yet all green. |

## What we should do next

1. Keep the Docker fresh-replay checkpoint marked **PASS**, linked to its actual GitHub run.
2. Complete the read-only census for Item 12 without changing Production or Test.
3. Continue the populated-data safety work in Item 26; do not count an empty-database replay as proof that this is done.
4. Keep H3-B and any existing-database transition gated until per-database schema parity, data preservation, and recovery requirements are evidenced.

The successful Docker replay is a meaningful milestone. It proves the tested fresh-install path works on the tested hosted runner; it is not a claim that every server or every existing database is already deployment-ready.
