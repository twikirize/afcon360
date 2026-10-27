# AFCON360 Database Reliability — Remaining Work Only

**Updated:** 27 October 2026  
**Branch:** `sandbox/codespaces-alembic-investigation`  
**Purpose:** A practical work queue containing only unfinished work from the official 39-item Database Reliability Master Register. Closed items are deliberately excluded.

**Canonical source:** [AFCON360 Database Reliability Master Register](../../AFCON360_Database_Reliability_Master_To_Do_and_Fix_Register.md)  
**Docker replay evidence:** [Successful GitHub Actions run #40469733857](https://github.com/twikirize/afcon360/actions/runs/40469733857)

## Current checkpoint

- The 24 checkpoints before Docker were completed according to the owner; the Docker fresh-database replay is operational checkpoint **#25 — PASS for the tested GitHub-hosted environment**.
- The hosted replay built the application image, ran 9 H3-A compatibility tests, migrated a fresh PostgreSQL 18.6 database to Alembic revision `1793013676`, passed its coarse schema guard (226 public tables, 49 enums, 139 CHECK constraints) and returned HTTP 200 from the health endpoint.
- The replay does not prove compatibility with every cloud provider, safety of upgrading a populated database, or readiness of existing Production/Test databases.
- Formal Item 26 in the canonical register is **populated-state migration safety**, not the operational Docker checkpoint. Formal Item 26 remains NOT STARTED.

## Remaining work at a glance

The official register has 15 top-level items that are not CLOSED: Item 10 is PARTIAL; Items 12, 15, 21, 24, 25, 27, 28, 33, 36 and 39 are ADVANCED; Items 26, 35, 37 and 38 are NOT STARTED. This file groups those 15 items into lettered work packages A–O. The letters are practical work IDs only; official item numbers and statuses remain authoritative.

| Work ID | Original item(s) | Work package | Current status |
|---|---|---|---|
| A | 12, 12b, 12c | Complete the remaining Item 12 environment evidence; Codespaces Docker census is recorded, and 12c source-history/test review remains | ADVANCED; 12c review remains |
| B | 21 | Decide and document the 49-versus-47 enum target | ADVANCED |
| C | 24 | Finish remaining migration-conflict and enum-disposition review | ADVANCED |
| D | 25 | Complete foreign-key-to-model mapping | ADVANCED |
| E | 27 | Qualify coupled model/database differences for each existing database | ADVANCED |
| F | 28 | Reconcile the 145 differing server defaults | ADVANCED |
| G | 33 | Finish model/schema parity and runtime-path verification | ADVANCED |
| H | 36 | Resolve pickup-time CHECK semantics and constraint-synchronizer blind spot | ADVANCED |
| I | 15 | Complete the state-by-state H3 transition runbook and gates | ADVANCED |
| J | 26 | Prove migrations preserve data in populated databases | NOT STARTED |
| K | 35 | Test upgrades from approved historical/intermediate states | NOT STARTED |
| L | 37 | Compare fresh-install schema with populated-upgrade schema | NOT STARTED |
| M | 38 | Prove controlled migration failure recovery and restore | NOT STARTED |
| N | 39 | Complete automated regression/integration gates | ADVANCED |
| O | 10 | Resolve or formally supersede the historic “182 tables from EMPTY” claim | PARTIAL |

## Lettered work packages

### A — Complete the read-only environment census
**Official references:** Item 12 and sub-items 12b/12c  
**Status:** Item 12 ADVANCED; sub-item 12b OPEN; sub-item 12c OPEN

**Evidence now captured (27 October):** The Codespaces Docker engine responds (Docker 29.8.0-1; Ubuntu 24.04.5 LTS, containerized). Only afcon360_db (PostgreSQL 18.6, healthy) and afcon360_redis (healthy) were present; the web, Nginx and Celery containers were absent. The active PostgreSQL volume is afcon360_postgres_data_pg18; the old afcon360_postgres_data volume still exists and was preserved. The current database afcon360_sandbox has only public schema, no app tables or Alembic revision table. The database list contains only afcon360_sandbox, postgres and the templates. All supplied inspection commands exited 0. This closes the earlier Docker-CLI-unavailable obstacle for this Codespaces host but does not show the state of remote Production/Test environments. The nested Docker TCP timeout remains a separate environment limitation.

**Work to do**
1. Preserve the captured Codespaces census as evidence; no need to repeat the same commands unless the environment changes.
2. Obtain read-only revision/catalog evidence for the actual deployed environments through their approved connection path; do not use Production/Test as scratch databases.
3. Review sub-item 12c's Socket.IO/CLI-disable source history and focused test evidence. The current checkout reported clean, and the implementation is present in tracked source, so the old wording that it is still uncommitted is stale; do not close 12c until the introducing commit and tests are identified.

**Acceptance evidence:** Exact commands, exit codes, timestamps, environment identity, versions and captured outputs; no database writes. State clearly which environments were observed and which were not.

### B — Decide the 49-versus-47 enum target
**Official reference:** Item 21  
**Status:** ADVANCED

**Why it remains:** H3-A replays with 49 enum types, while the documented B0 target expectation is 47. The target-scope decision and related ownership/disposition are not settled.

**Work to do:** Reconcile each differing enum against model declarations, the approved target schema, historical uses, dependencies, labels and defaults. Record an explicit decision for every discrepancy. Preserve existing type representations unless a separately reviewed and authorized plan says otherwise; do not drop, relabel or convert enums as a shortcut.

**Acceptance evidence:** Owner-approved 49-versus-47 decision and a per-enum inventory showing keep/retire/recreate/legacy disposition, dependencies, exact labels and rationale.

### C — Finish the remaining migration-conflict review
**Official reference:** Item 24  
**Status:** ADVANCED

**Why it remains:** The historical 324-row conflict matrix is not yet fully reconciled against the active H3-A baseline, B0 ownership expectations and remaining enum/orphan cases.

**Work to do:** Close each unresolved conflict row with source evidence, ownership, intended disposition and whether it is reproduced at runtime or only predicted from source. Keep child-versus-child conflicts distinct from root-versus-child conflicts.

**Acceptance evidence:** All applicable rows have explicit dispositions; unresolved decisions are named; the fresh replay remains green; no claim of runtime failure is based only on a source prediction.

### D — Complete foreign-key-to-model mapping
**Official reference:** Item 25  
**Status:** ADVANCED

**Why it remains:** The duplicate `DriverProfile.user_id` model declaration was corrected, but physical duplicate foreign keys remain in recorded states and H3-A baseline. Broader column-level mapping is incomplete. Test also has a `organisation_types.category_code` CASCADE-versus-RESTRICT divergence.

**Work to do:** Map each FK by table, column(s), target table/column(s), name, delete/update action, ORM relationship and migration creator. Compare Reference/Production/Test/H3-A separately. Do not repair existing constraints during the inventory.

**Acceptance evidence:** Complete, reviewed mapping and explicit per-database dispositions for duplicates and action differences, with read-only catalog evidence. Any physical change requires a separate reviewed authorization.

### E — Qualify coupled model/database differences per environment
**Official reference:** Item 27  
**Status:** ADVANCED

**Why it remains:** The source-level FK fix is not the same as database convergence. Recorded physical states and the frozen H3-A baseline still contain the driver-profile duplicate pair; other FK/model coupling and per-database transition qualification remain incomplete.

**Work to do:** Use the results from A and D to document each Production/Test-specific difference and decide the safe treatment independently for each database. Maintain the H3-B authorization gate.

**Acceptance evidence:** A state-by-state parity/qualification artifact for each database, linked to the FK map; no unexplained differences, no false stamping, and no unauthorized database changes.

### F — Reconcile the 145 differing server defaults
**Official reference:** Item 28  
**Status:** ADVANCED

**Why it remains:** There are 145 recorded Production/Test server-default differences: 132 Production-only, 12 Test-only and one where both differ.

**Work to do:** Classify each difference as intended, accidental, historical or unknown. Verify intended behavior against source and actual application use. Do not bulk-normalize defaults to make schemas look equal.

**Acceptance evidence:** A reviewed row-by-row decision ledger with evidence and an explicit disposition for each default; any proposed change has a separate scope, migration plan and tests.

### G — Finish model/schema parity and feature-path checks
**Official reference:** Item 33  
**Status:** ADVANCED

**Why it remains:** The H3-A runtime table-set check matched 223 physical app tables to 223 ORM metadata tables at that snapshot, but that does not establish full schema parity or runtime reliability. End-to-end session persistence and analytics-flush failure safety remain untested; default and enum decisions also remain open.

**Work to do**
1. Prove login/logout paths persist and use `server_sessions` as intended.
2. Test the analytics flush when database insert/commit fails, ensuring Redis counters are not lost before durable persistence.
3. Reconcile model-less tables, model defaults, enum target decisions and other physical differences against B/C/D/F.

**Acceptance evidence:** Targeted end-to-end tests with captured outcomes, complete model/physical inventory, and no unowned schema objects or active application paths that depend on missing tables.

### H — Resolve the pickup-time constraint contract and synchronizer blind spot
**Official reference:** Item 36  
**Status:** ADVANCED

**Why it remains:** Investigation reproduced a strict database-only `chk_pickup_time_future` CHECK that can reject legitimate instant-booking timestamps. The synchronizer filters discovery using the `ck_` prefix and missed a legacy `chk_` constraint. The intended instant-versus-scheduled timestamp contract, durable source correction and a clean regression/cleanup run are still open.

**Work to do**
1. Obtain an explicit product/engineering decision about timestamp authority for instant bookings versus scheduled bookings.
2. Update discovery to inventory all named checks while keeping legacy `chk_*` constraints report-only unless separately authorized; prevent legacy checks from entering automated prune/migration operations.
3. Normalize semantically equivalent CHECK SQL before reporting drift.
4. Correct the focused regression/teardown guard through the approved test helper; do not manually delete residual probe data or alter protected databases without authorization.
5. Run the full acceptance matrix: instant-now, processing delay, stale client timestamp, clock/timezone skew, scheduled future, near-past rejection and response behavior.

**Acceptance evidence:** Approved contract, reviewed minimal source fix, targeted tests passing with pytest exit code 0 and clean authorized teardown, plus fresh replay/schema checks where the migration source changes. No edits to the frozen baseline or Production/Test without separate authorization.

### I — Complete the H3 state-by-state transition runbook
**Official reference:** Item 15  
**Status:** ADVANCED

**Why it remains:** A reversible probe migration passed, but not every starting state, parity gate or failure-recovery path has been rehearsed.

**Work to do:** Define and test procedures for empty, root-stamped, intermediate, at-head and unknown/divergent states. State when to replay, compare, upgrade, stamp or halt. Include Production/Test parity gates, backup/recovery, extension preservation and operator checkpoints.

**Dependencies:** A, B, C, D, E, F, J, K and M as relevant. Do not execute H3-B or perform a production transition while prerequisite gates are unproven.

**Acceptance evidence:** Reviewed runbook with per-state evidence requirements, separate disposable rehearsal results, explicit stop conditions and tested rollback/recovery. The plan itself does not authorize a cutover.

### J — Prove migration safety with existing data
**Official reference:** Item 26  
**Status:** NOT STARTED

**Why it remains:** A fresh empty-database replay does not prove upgrades are safe when tables already contain real rows.

**Work to do:** In approved disposable databases, test representative NOT NULL additions, backfills, unique indexes, CHECK constraints and foreign keys. Include valid and invalid data, duplicates, NULLs, and existing-row distributions.

**Acceptance evidence:** Before/after row-count and data-integrity checks; expected rejection of invalid data; proof existing data is preserved; captured commands, exit codes and database identities. Never use Production/Test as scratch targets.

### K — Test upgrades from supported historical/intermediate states
**Official reference:** Item 35  
**Status:** NOT STARTED

**Why it remains:** The clean-install chain is not a test of every older starting revision.

**Work to do:** Enumerate owner-approved historical/intermediate revisions. Create a separate disposable database per starting state, seed representative data, run the supported upgrade path and validate rows, constraints, enums and final revision.

**Acceptance evidence:** A revision-by-revision matrix with exact starting revision, seed/data profile, command/exit code, resulting revision and integrity assertions. Unsupported or unknown states must fail closed as defined by policy.

### L — Compare clean install with populated upgrade
**Official reference:** Item 37  
**Status:** NOT STARTED

**Why it remains:** No qualifying independent comparison exists yet between a clean installation and an approved populated-state upgrade.

**Work to do:** After J and K pass, extract normalized schema from both results and compare tables, columns, types/enums, defaults, constraints, indexes, foreign keys, triggers, functions and relevant data invariants. Explain each remaining difference; do not rely on matching Alembic IDs or table counts alone.

**Acceptance evidence:** Reproducible normalized snapshots, hashes, diff output/exit codes and an explanation/disposition for every difference. Any target schema used for comparison must be explicitly approved.

### M — Prove migration failure recovery and backup restoration
**Official reference:** Item 38  
**Status:** NOT STARTED

**Why it remains:** There is no complete controlled-failure and restore rehearsal recorded for the acceptance criteria.

**Work to do:** Induce a deliberate failure in a disposable database at a known migration stage. Record transaction/partial-change behavior, restore the approved backup or use the approved recovery route, and confirm the resulting schema/data and Alembic state.

**Acceptance evidence:** Failure reproduction, exact error/exit status, restore/recovery command log, before/after schema and data verification, and confirmation of whether manual intervention was required. Never perform the failure test against Production/Test.

### N — Complete automated regression and integration gates
**Official reference:** Item 39  
**Status:** ADVANCED

**Why it remains:** Focused suites and the hosted Docker replay pass, but the full suite and all required database integration, schema-diff, conflict and cleanup gates have not all passed. The 25 October pickup probe exited 1 due to six teardown errors despite six assertions passing.

**Work to do:** Fix the approved test-isolation/cleanup issue, run the full suite, and make the relevant PostgreSQL replay, revision graph, schema-shape/exact-diff, conflict detection and protected-database guards repeatable in CI.

**Acceptance evidence:** Clean exit code 0, no teardown errors or residual probe records, captured logs, replay and schema gates green, and a reviewed final register. Preserve the existing successful hosted replay as a separate gate.

### O — Resolve the historical “182 tables from EMPTY” claim
**Official reference:** Item 10  
**Status:** PARTIAL

**Why it remains:** The exact old claim has not been fully supported by contemporaneous replay evidence. A later 224/226-table replay cannot be substituted as proof of the historic count.

**Work to do:** Locate the original logs/commands/commit artifacts that specifically prove or refute the historical claim. If the evidence cannot be recovered, record the owner's explicit decision to supersede the exact claim and explain the replacement evidence, while retaining the historical record.

**Acceptance evidence:** Contemporaneous artifact tied to the claim, or an explicit, dated owner disposition that marks the historical count superseded without claiming it was proven.

## Suggested working order

This is a proposed order based on dependencies, not a status change or authorization to modify databases:

1. **A —** Read-only environment census and deployment evidence.
2. **B, C, D —** Resolve the enum target, migration conflict dispositions and FK mapping.
3. **E, F, G —** Qualify per-database differences, defaults and model/schema behavior.
4. **H —** Close the pickup-time contract and focused test/cleanup gate.
5. **J, K, M —** Prove populated-state safety, historical upgrades and failure recovery on disposable databases.
6. **L —** Compare clean and upgraded results after the prerequisite tests pass.
7. **I, N —** Finalize transition runbook and automated regression gates after the underlying evidence exists.
8. **O —** Resolve the historic-count claim when its original artifact is located or formally superseded.

**Safety rules:** Keep `afcon360_prod` and `afcon360_test` read-only. Do not run H3-B, stamp, rebuild, drop/rename/relabel enums, prune legacy constraints, delete probe rows, or remove database volumes without separate explicit authorization. Never use `docker compose down -v` as routine cleanup. Keep all work on the investigation branch until reviewed.

## Completion rule for this backlog

When a package passes, record the evidence and update its status here and in the canonical 39-item register. Do not mark the original master item CLOSED until that item's own stated acceptance criteria are satisfied. The operational Docker replay checkpoint #25 remains a separate PASS; it does not close populated-state Item 26.
