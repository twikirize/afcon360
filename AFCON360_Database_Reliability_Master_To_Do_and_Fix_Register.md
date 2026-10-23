# AFCON360 — Database Reliability — Master To-Do & Fix Register

**Snapshot: 23 October 2026 · reconciled to the owner-approved support policy, H3-A active-chain verification, the physical-schema investigation, and the local migration round-trip evidence; statuses reflect acceptance evidence, not deployment readiness.**

**Status: 24 closed · 9 advanced · 1 partial · 0 open · 0 gated · 5 not started (39 top-level items)**

**Architecture: H2′ approved and implemented as the interim fresh-install repair · H3/N-squash remains the durable destination · H3-A is the active static baseline and a snapshot of `afcon360_h2p_replay_20261018_test` at `df55cbe3f516`; its replay and current-head idempotence have been verified on PostgreSQL 18.4. This reproduces the captured H2-prime physical state (49 enums, 224 tables), not yet the B0 47-enum target. The 49-vs-47 scope decision is pending · H3-B existing-database transition remains unauthorized**

**Permanent fixes implemented: 2 (H2′ interim fresh-install repair; Design 2 model-bootstrap path)**

**Clean-install verification completed: 2 (H2′ empty-database migration replay to `df55cbe3f516`; Design 2 live bootstrap PASS on `afcon360_d2_bootstrap_fix_20261018_test`)**

**H3-A replay verification completed: 1 (the static baseline executes and is idempotent at head on PostgreSQL 18.4 against the captured H2-prime physical state; this does not establish that the 49-enum baseline matches B0's 47-enum target)**

**Not verified: full test suite · genuinely fresh-clone replay · PostgreSQL 15 / Docker-pinned replay · historical/intermediate-state upgrades · populated-state safety · existing-database transition readiness · 49-vs-47 H3-A target-scope decision · H3-A object-ownership proof against B0 final-schema inventory · source-declared application table candidate disposition**

**Current-status rule:** Phases 1–11 retain dated historical evidence. Where an earlier phase describes the H3 root as not yet created/applied or Item 13 as awaiting approval, the 23 October 2026 reconciliation in Phase 12 is the current status record. Historical wording is retained for chronology, not as a live status claim.

---

## Overall status summary

| Status | Count |
|---|---:|
| CLOSED | 24 |
| ADVANCED | 9 |
| PARTIAL | 1 |
| OPEN | 0 |
| NOT STARTED | 5 |
| GATED | 0 |
| **Total** | **39** |

### Top-level status table (IDs 1–39, each exactly once)

| Item | Description | Expected test / acceptance evidence | Status |
|---:|---|---|---|
| 1 | First observed installation failure: missing `transactiontype` | Preserve the original failure evidence; the repaired clean replay must create the type exactly once, with no competing creator. | CLOSED |
| 2 | Enum ownership investigation | Reconcile the USED, REFERENCED-only and orphan inventory against model declarations, migration references and catalog evidence. | CLOSED |
| 3 | Map Alembic history and 27-revision chain | Verify every revision and edge, one base and one head; retain fresh-clone replay as a separate Item 31 acceptance check. | CLOSED |
| 4 | Identify root-baseline design problem | Use commit-level source evidence to establish the baseline/child ownership problem, without confusing source predictions with observed runtime failures. | CLOSED |
| 5 | Identify repeated migration operations | Retain the conflict matrix and distinguish confirmed declaration duplication from conditional/source-predicted conflicts; reconcile against replay evidence. | CLOSED |
| 6 | Investigate competing schema-creation paths | Trace Alembic and model-bootstrap/`create_all` paths separately; verify no false Alembic-head stamp is used for bootstrap. | CLOSED |
| 7 | Recover historical evidence | Tie historical claims to exact commits, logs or durable evidence artifacts and identify unsupported claims explicitly. | CLOSED |
| 8 | Agree the engineering destination | Record the owner-approved position: H2′ interim fresh-install repair, H3/N-squash durable destination; no implied cutover authorization. | CLOSED |
| 9 | Reconstruct original baseline history | Compare the historical root/declaration source at key commits and keep historical reconstruction separate from current replay proof. | CLOSED |
| 10 | Verify the historical “182 tables from EMPTY” claim | Locate contemporaneous replay evidence or explicitly record the owner’s decision that the exact historical claim is superseded; do not substitute the 224-table H2′ replay. | PARTIAL |
| 11 | Trace enum declaration changes | Verify the introduction/removal of enum-creation flags and related changes from Git history; preserve the corrected `create_type`/`checkfirst` contract. | CLOSED |
| 12 | Establish deployed migration states | Use read-only, per-environment revision/catalog evidence and complete the Docker census; do not modify production or test databases. | ADVANCED |
| 13 | Define supported starting revisions | Owner-approved four-case policy recorded 2026-10-21; H3-A clean-install and normal Flask-Migrate workflow verified on local PostgreSQL 18.4. Existing databases remain conditional on per-database parity and a reviewed transition plan; older revisions require explicit enumeration and tests; unknown/divergent states fail closed. Closure is policy-only and does not authorize H3-B. | CLOSED |
| 14 | Compare H2′ with existing database states | Complete the independent Reference/Prod/Test normalized-schema comparison and record measured differences and distinct hashes; same Alembic revision must not be treated as proof of identical schema. Comparison complete; divergence remains unresolved. | CLOSED |
| 15 | Design the H3 transition procedure | Complete the state-by-state runbook for empty, root-stamped, intermediate, at-head and unknown states, with parity-gated stamping and tested recovery/rollback. A reversible H3 probe-migration rehearsal passed; other states and cutover gates remain unproven. | ADVANCED |
| 16 | Classify architecture-specific conflicts | Keep root-vs-child and child-vs-child conflicts distinct and tie classifications to source/graph evidence, not assumed runtime failures. | CLOSED |
| 17 | Compare H2′ and H3 architectures | Retain a reasoned comparison of fresh-install behavior, old/intermediate states, enum ownership, immutability and rollback implications. | CLOSED |
| 18 | Approve one architecture | Preserve the owner decision selecting H2′ as interim and H3 as durable target; confirm this is not permission to cut over. | CLOSED |
| 19 | Approve and execute isolated PostgreSQL verification plan | Replay the full H2′ migration chain in an approved empty disposable PostgreSQL database and verify the final head and resulting catalog counts. | CLOSED |
| 20 | Establish canonical schema-creation architecture | Verify Design 2 bootstrap creates its schema, completes and validates its marker/fingerprint, and does not falsely create `alembic_version`; keep it distinct from Alembic. | CLOSED |
| 21 | Repair enum creation ownership | Define one creator for each enum required by the approved fresh schema, with exact labels; preserve existing database type representations and record legacy objects/defaults without conversion, dropping or relabeling. Python enum-object identity alone is insufficient. | ADVANCED |
| 22 | Eliminate repeated `window_mode_enum` creation | The H2′ clean-install replay must create `window_mode_enum` exactly once; test historical/intermediate paths separately after support policy is settled. | CLOSED |
| 23 | Resolve duplicate slug migrations | The H2′ clean-install replay must create each slug object once and preserve the required constraints; historical/intermediate behavior remains a separate test. | CLOSED |
| 24 | Resolve remaining confirmed and conditional conflicts | Reconcile the 324-row matrix against successful replay evidence and record explicit dispositions for conditional conflicts, orphan types and divergent `org_business_category` copies. | ADVANCED |
| 25 | Correct foreign-key assumptions | Read-only Item 25 inventory covers 411 FKs per Reference/Prod/Test/H3-A state (410 distinct relationship signatures). Source review now reproduces two defects: Test's legacy `organisation_types.category_code` CASCADE conflicts with the model/baseline/application guard's RESTRICT, and `DriverProfile.user_id` declares both a column FK and named CASCADE table FK, matching the contradictory duplicate constraints found physically. Complete the full source/migration/model mapping and state-specific qualification before disposition. | ADVANCED |
| 26 | Make data-sensitive migrations safe | Run populated-state tests for NOT NULL additions, backfills, unique indexes, CHECKs and FKs; prove existing data preservation and invalid-data rejection. | NOT STARTED |
| 27 | Resolve `df55cbe3f516` and coupled model changes | Revision tracking/reachability is satisfied. Source review now confirms the duplicate `DriverProfile.user_id` FK cause; independently complete the remaining FK/model coupling review and separate physical-parity/transition-qualification evidence for Production and Test. No constraint repair or database transition is authorized by this finding. | ADVANCED |
| 28 | Consolidate schema-creation procedures | Document the supported installation route and enforce separation between bootstrap and migration paths; disposition the 145 server-default differences and resolve the unregistered source-table candidates before convergence. Runtime H3-A metadata now matches its physical tables exactly. | ADVANCED |
| 29 | Establish permanent database engineering rules | Verify the rules and their mirror agree: ordinary migrations are regenerated from corrected source/configuration, hand-patching is prohibited except for the narrowly authorized baseline-reconstruction exception. | CLOSED |
| 30 | Create approved disposable PostgreSQL verification environment | Retain the authorized disposable replay/bootstrap databases and their evidence; verify that production/test databases were not used as scratch targets. | CLOSED |
| 31 | Pass clean-install migration test | Replay from an empty database to `df55cbe3f516` and verify the resulting schema; extend separately to a genuinely fresh clone and supported/pinned PostgreSQL versions. | CLOSED |
| 32 | Verify physical schema completeness independently | Completed normalized Reference/Prod/Test extraction and recorded hashes, diff sizes, object counts, timestamp differences, FK-action differences, triggers, functions, indexes, enums and defaults. The comparison is complete; physical divergences are not thereby resolved. | CLOSED |
| 33 | Verify model/schema parity | H3-A runtime audit on PostgreSQL 18.4 confirms 223 physical app tables = 223 runtime ORM metadata tables, with zero mismatches in either direction and zero model-registration failures. Three `agent_onboarding` server defaults have now been aligned in the local model worktree and pass a focused four-test regression suite (33b); this is not Prod/Test parity. The 49-vs-47 target decision, disposition of source-declared but unregistered table classes, the 145 Prod/Test server-default differences and broader schema parity remain unresolved. | ADVANCED |
| 34 | Verify current-head behavior | CLOSED 2026-10-23: second ordinary `flask db upgrade` at `h3a20261020` on `afcon360_chain_verify_test` exited 0; before/after normalized snapshots were both 886,434 bytes and SHA-256 `8577c2a975d5846c3b99567a2c1d59d47b3686d893dbf23531adb9dcf40753d7`; diff exit 0, 0 bytes, 0 lines, first 10 lines blank. | CLOSED |
| 35 | Test upgrades from supported historical states | For every owner-approved supported historical revision, upgrade a separate disposable database with representative data and validate the resulting schema and data. | NOT STARTED |
| 36 | Verify data and constraints | Prove row/value/relationship preservation, enum-label preservation and rejection of invalid data using populated disposable databases. | NOT STARTED |
| 37 | Compare fresh and upgraded results | After dispositioning the 145 Prod/Test server-default differences and resolving the H3-A target/table-scope decisions, compare fresh-install and upgraded snapshots and explain every exception. The runtime H3-A ORM/physical-table comparison is complete with zero table-set differences. | NOT STARTED |
| 38 | Verify failure recovery | Induce a controlled migration failure in a disposable database and test/document recovery, transaction behavior and backup restoration where needed. | NOT STARTED |
| 39 | Establish automated regression gates and close the work | Keep focused database-guarded tests green and add the full suite, PostgreSQL integration/replay, fresh-clone, schema-diff and conflict checks; see Phase 8 for exact guarded-run evidence and limits. | ADVANCED |

---

## Marking legend

- [CLOSED] — item's stated acceptance evidence exists and has been recorded
- [PARTIAL] — verdict reached; specific sub-evidence outstanding
- [ADVANCED] — substantively progressed; a specific input or verification still required
- [OPEN] — unchanged from the original register
- [GATED] — awaiting decision or prerequisite (none remain at this snapshot)
- [NOT STARTED] — no substantive work recorded
- [PREREQ] — prerequisite to other items, not downstream
- [REVISED] — scope corrected by evidence (wording state; implementation not started unless separately marked)
- [CLARIFIED] — finding restated without scope change (wording state only)
- [NEW] — added since the original register was authored
- [SPECIFIED]/[DELIVERED]/[RECORDED] — subordinate finding recorded under its parent
- [HISTORICAL] — superseded statement retained only as pre-replay evidence; no longer a current status claim

---

## Canonical corrections (do not re-derive)

- **C1** — bookingstatus 12-label state is consistent with past-11; downgrade-rename mechanism indicated, execution unproven.
- **C2** — Types present in dev but absent in test are unclassified, not disposable. Use "unclassified", not "ghost".
- **C3** — CONFIRMED in the 324-row matrix denotes declaration duplication (source-proven), not observed failure. The original observed empty-replay failure was missing `transactiontype`; the revised H2′ chain passed a fresh replay on 2026-10-18. Source-predicted conflicts must not be described as runtime failures.
- **C4** — `df55cbe3f516` is tracked on GitHub `main`, and the current clean replay reaches it. The earlier claim that this revision is untracked and prevents clean-checkout graph resolution is superseded. Independent physical FK/model parity and coupling checks remain open (items 16d and 32).

---

## Architecture position (the tracks must not be conflated)

| Track | State at this snapshot |
|---|---|
| **H2′ interim fresh-install repair** | **Implemented and committed.** Four previously modified migration files repaired; a full empty-database replay passed on local **PostgreSQL 18.4**, reaching `public.alembic_version = df55cbe3f516`. This is an *interim* repair, not the durable destination. |
| **Design 2 model-bootstrap path** | **Committed** in `ff5fe53` (implementation + contract suite) and `96636f2` (`%`-placeholder fix + 5 regression tests). Source-level tests pass (33 standard, 38 in the isolated no-connection run). Live PostgreSQL runtime verification PASSED on 2026-10-18 against `afcon360_d2_bootstrap_fix_20261018_test` (217 tables, 47 enums, marker `complete`, no `alembic_version`). Read-only `validate_model_bootstrap()` returns `model_bootstrap_complete`. The pre-fix failure database `afcon360_b0_design2_rt_20261018` is preserved as historical evidence of the `%`-placeholder defect. Not interchangeable with the migration path. |
| **H3 / N-squash** | **Selected durable destination.** In the owner-reported local checkout, `migrations/versions/h3a20261020_static_baseline.py` is the active single root/head. The normal Flask-Migrate baseline path and a reversible follow-up migration round trip were verified on local PostgreSQL 18.4. H3-B remains unauthorized and blocked by Docker census, FK/model coupling, existing-database parity, populated-state safety and transition/recovery evidence. The active baseline docstring is stale; see 13c. |
| **Existing production and test databases** | **Not upgraded and not modified in this work.** `afcon360_prod` and `afcon360_test` remain read-only evidence sources. |
| **Physical-schema comparison and broader parity** | **Comparison recorded; differences unresolved.** Reference/Prod/Test hashes and diff counts are available (Items 14/32). Model/schema parity is only partially evidenced on H3-A; Prod/Test transition qualification, historical/intermediate upgrades, defaults, model-less tables and FK/model coupling remain open. |

---

## Working policies

- Retain native PostgreSQL enums.
- Migration history is immutable by default.
- Stamps require independent schema verification.
- The `create_type` option governs whether SQLAlchemy automatically emits PostgreSQL enum creation and drop DDL; `checkfirst` controls existence checking during applicable create/drop operations, including enum type operations. (Corrected per item 11c; the earlier checkfirst-only-tables claim is withdrawn.)
- `alembic_version` alone is insufficient as a schema fingerprint — an independently recorded parity artifact is required before any stamp or upgrade over an old-dynamic body.
- `db.create_all()` is never a substitute for the approved migration path on a non-test database, and must never be followed by a false Alembic head stamp.
- Do not infer schema identity from identical Alembic revision IDs or empty redirected diff output. Identity claims require byte size, exit code and inspected diff evidence.
- Preserve existing PostgreSQL type representations and the production-only `pgcrypto` extension until a separately reviewed, explicitly authorized state-specific disposition is approved.

---

# Phase 1 — Findings established (items 1–8, all closed)

**[CLOSED] 1. First observed installation failure: missing `transactiontype`.**
The only quantified empty-replay failure on record. It is the seed evidence for the whole register.
**Next action:** preserve as regression evidence and assert that `transactiontype` is created exactly once in the frozen root, with no second creator anywhere in the chain.

**[CLOSED] 2. Enum ownership investigation.**
Enum references without creation paths were identified and inventoried: 48 USED names, 3 REFERENCED-only names, 16 dev-only orphans, plus `bookingstatus` and the divergent `org_business_category`.
**Next action:** retain the inventory; resolve the remaining legacy enum and orphan dispositions under item 21 rather than re-deriving the census.

**[CLOSED] 3. Map Alembic history and 27-revision chain.**
The chain including `df55cbe3f516` is mapped and, since the H2′ repair, fully resolvable from a clean checkout.
**Next action:** verify graph resolution from a genuinely fresh clone and on the PostgreSQL version pinned by Docker — both still unverified.

**[CLOSED] 4. Identify root-baseline design problem.**
The baseline design, not a single revision, produced the repeated-creation and ownership defects.
**Next action:** keep H2′ as the interim repair and H3/N-squash as the durable target; do not reopen the diagnosis.

**[CLOSED] 5. Identify repeated migration operations.**
Repeated object creation across the chain was identified mechanically.
**Next action:** reconcile the 324-row conflict matrix against the now-successful fresh replay; continue to treat the 0 PREDICTED rows as source prediction, not observed failure.

**[CLOSED] 6. Investigate competing schema-creation paths.**
Two independent schema producers exist: the Alembic chain and the model-bootstrap/`create_all` route.
**Next action:** preserve the distinction between migration-built and model-bootstrap schemas; never let one silently substitute for the other.

**[CLOSED] 7. Recover historical evidence.**
Commit-level evidence was recovered for the enum, slug and baseline behaviours.
**Next action:** keep every historical claim tied to its specific commit and evidence artifact.

**[CLOSED] 8. Agree the engineering destination.**
The destination is H3/N-squash; H2′ is the interim path that makes a clean install possible now.
**Next action:** continue toward H3 without confusing its status with the implemented H2′ repair.

---

# Phase 2 — Evidence for the architecture decision (items 9–17)

**[CLOSED] 9. Reconstruct the original baseline history.**
Evidence: at `449bdcd` (2026-08-23) both `app/audit/comprehensive_audit.py` and `app/transport/models.py` carry plain `SQLEnum(...)` declarations; the root body `db.metadata.create_all(op.get_bind())` is byte-identical to HEAD. Under plain `SQLEnum`, Postgres derives the type name from the Python class and `checkfirst=True` creates the type if absent.
Narrowed claim: the enum declarations supported native type creation via SQLAlchemy defaults. Whether the complete chain reached head from empty is a separate question, answered for the *current* chain by item 19, not by this reconstruction.
**Next action:** reuse the established history; reopen only if new contradictory evidence appears.

**[PARTIAL] 10. Verify the historical "182 tables from EMPTY" claim.**
Evidence: the claim first appears at `449bdcd` — the same commit that authored the baseline. No committed `flask db upgrade` transcript exists. The one quantified log at that commit records the *test bootstrap path* (`create_all` + stamp head against `afcon360_test`).
Verdict: claim made, unsubstantiated by committed evidence. Mechanism was correct at `449bdcd`; became incorrect at `174b625`.
Reconciliation: the historical investigation (10a) is complete; the empirical reproduction (10b) is a separate deliverable. This item is **PARTIAL, not CLOSED** — and it must not be confused with the new 224-table H2′ replay, which is a different and separately evidenced claim (item 31).
**Next action:** decide whether the historical 182-table claim still requires its own empirical reproduction (10b) or is formally superseded; keep it explicitly distinct from the 2026-10-18 replay evidence.

**[CLOSED] 11. Trace when enum declarations changed.**
Broad `create_type=False` introduced at `174b625` (2026-10-13 05:39), empty commit body.

| Commit | Date | Effect |
|---|---|---|
| `449bdcd` | 2026-08-23 | Zero `create_type=False` |
| `a1a490b` | 2026-10-12 | One legitimate reference; writes README promising `ensure_all_enums()` |
| `76a518b` | 2026-10-13 04:01 | Deletes the README paragraph |
| `174b625` | 2026-10-13 05:39 | 43 columns with the flag, inline |
| `39266d2` | 2026-10-13 07:35 | 5 wallet columns |
| `5ef3014` | 2026-10-14 | Reformat only |

Subordinate 11a/11b/11c confirm that `ensure_all_enums()` never existed, that the README paragraph was written at `a1a490b` and deleted at `76a518b`, and that the corrected native-enum contract is `create_type` = automatic enum DDL, `checkfirst` = existence checking.
**Disposition (2026-10-20):** the corrected `create_type`/`checkfirst` contract is recorded in the permanent database rules; Item 29 remains CLOSED by owner confirmation. The narrowly scoped ordinary-migration versus baseline-reconstruction wording refinement is handled as a documentation harmonization task and does not reopen Item 29.

**[ADVANCED] 12. Establish deployed migration states.**
Local census complete:

| Env | `alembic_version` | Tables | Enum types | State |
|---|---|---:|---:|---|
| `afcon360_prod` (local) | `df55cbe3f516` | 224 | 68 | Physically divergent from test |
| `afcon360_test` | `df55cbe3f516` | 224 | 49 | Stale physical schema |
| Docker / local preflight | — | — | — | `docker` command not found; census not obtained; container state unknown |

Deployment evidence (repo-only): zero tags — no release boundary. Only in-repo migration executor: `docker-entrypoint.sh:47` `flask db upgrade` (web role only). **Update 2026-10-18:** a separate disposable database passed the current H2′ empty-database replay. `afcon360_prod` and `afcon360_test` were not upgraded or modified.
**Next action:** run the Q1–Q4 census from an approved Docker-enabled host or after Docker CLI availability is restored. The local command-not-found result does not establish whether containers are running. Preserve read-only per-environment evidence.

**[NEW] 12a. Deployment evidence ledger.** Recorded. Canonical for future contributors.

**[OPEN] 12b. Docker census.** The 2026-10-20 local PowerShell preflight could not invoke `docker` (`CommandNotFoundException`), so no container census or container-state result was obtained. This blocks H3 until the Q1–Q4 read-only census is run from an approved Docker-enabled host. The local failure does not prove that the containers are down.

**[CLOSED] 13. Define supported starting revisions.**
The owner-approved support policy (2026-10-21) defines the state categories and acceptance rules. The policy's closure means the support boundaries have been decided; it does not mean every existing database is ready to transition.
- **Empty database:** qualify only after clean replay on each approved server/version. H3-A's local PostgreSQL 18.4 baseline/workflow path is now verified; fresh-clone and other-version acceptance remains under item 31.
- **Existing DB at `df55cbe3f516`:** eligible for consideration only after independent, per-database physical-schema parity and a reviewed transition plan. Treat Prod and Test as distinct states until each qualifies independently.
- **Older/intermediate revision:** unsupported unless the exact revision is explicitly enumerated and independently tested on a disposable database.
- **Unknown revision, conflicting Alembic state or unrecognized/divergent physical schema:** fail closed and require manual assessment; no automatic stamping or upgrading.
**Closure boundary:** this is policy-definition closure only. It does not establish populated-database safety or authorize H3-B, stamping, rebuilding or cutover.

**Case 2 extension-preservation requirement — production-only `pgcrypto`:** The saved catalog records `pgcrypto` in production only. A transition plan must explicitly state whether the existing database is reused or a replacement is created. An in-place transition must not assume extension loss merely because the H3-A baseline omits it. If the database is rebuilt, assess whether to recreate the extension and document the approved action. Do not add production-only `pgcrypto` to the shared H3-A baseline by default. This requirement does not authorize H3-B or any database change.

**Next action:** complete state-specific transition rules once the Docker census (12b), per-database parity, FK/model verification (27), and associated evidence gates are resolved.

**[CLOSED] 14. Compare H2′ with existing database states.**
The physical-schema comparison is complete; its conclusion is **divergence**, not alignment. The owner-confirmed extraction script `scripts/h3/extract_physical_evidence.py` records normalized size/hash data and measured pairwise diffs for Reference, Prod and Test, all at `df55cbe3f516`.

| Database | Bytes | Lines | Normalized SHA-256 |
|---|---:|---:|---|
| Reference | 919,891 | 28,367 | `0701c42dda041f3725c59d2b8081fd4534b5f8d3359f67839aad98c8d53198da` |
| Prod | 929,285 | 28,702 | `4485e14f910a16be1a766be355e27ed4724e744eca90faba428e522b71396c3e` |
| Test | 921,768 | 28,411 | `0326f5d7b8891cfa344c74d5b3805565b80f68e2e9f1f4ca44829249954d4c5b` |

Measured diff sizes: Reference/Prod 2,273 lines (93,910 bytes); Reference/Test 711 lines (35,664 bytes); Prod/Test 2,311 lines (93,240 bytes). The investigation records enum-count differences (68 Prod vs 49 Reference/Test), 29 agent indexes in Prod/Test vs 14 Reference, triggers 2/2/0, live routines 39/2/0, Prod-only `pgcrypto`, 12 timestamp-type differences, 4–6 FK-action differences per pair, and 145 server-default differences.

Same-ID/different-schema hazard is proven: `afcon360_test` at `df55cbe3f516` carries `org_business_category` as a live-used 39-label uppercase enum; `afcon360_prod` at the same revision carries the column as `varchar(40) NULL`, with a separate 4-label lowercase orphan enum. Prod and Test remain distinct transition cases.

**Closure boundary:** Item 14 closes the physical-comparison and divergence-recording work. It does not mean Prod/Test align or qualify for an H3 transition. Subordinate 14d's `pgcrypto` dependency/disposition review remains open. Preserve all type representations; no conversion, drop, rename, relabel, normalization, stamp or cutover is authorized by this comparison.

**[ADVANCED] 15. Design the H3 transition procedure.**
The planned procedure uses the H3 N-squash root, retires old active migration files under the authorized architecture change, rejects merge revisions, defines state-specific commands (empty / root-stamped / intermediate / at-head / unknown), gates any stamp on parity, and documents re-track/re-stamp recovery. Under H3, `f91075478868` is retired, removing its fourfold `window_mode_enum` emit issue from the active chain; H2′ would still require its own exception/conditionalizing repair.

**Additional rehearsal evidence (2026-10-23):** in the verified local H3-A chain, the standard Flask-Migrate flow generated migration `c6c0034e7439` from `h3a20261020`; inspection confirmed the sole operation was adding nullable `String(32)` column `agent_onboarding_approvals.h3_workflow_probe`. Upgrade created the column, downgrade returned to `h3a20261020` and removed it, and final `flask db check` reported no new operations with exit code 0. See subordinate 34a. This proves a reversible migration round trip on the disposable H3 workflow database, not every transition state or current-head idempotence.

**Next action:** finish the state-specific runbook and review it against the Docker census (12b), per-database physical evidence, FK/model coupling (25/27), populated-state safety (26), extension preservation (14d) and failure recovery (38). Item 13's policy is closed; operational transition gates remain.

**[CLOSED] 16. Classify architecture-specific conflicts.**
Class separation confirmed: root-vs-child conflicts (e.g. `booking_flow_type`, slug objects) are potentially removed by freezing the root under H2′; child-vs-child conflicts (the slug pair, `offerings.code` double-unique) require a history exception under either architecture. Live evidence: `slug` is NOT NULL in both databases — consistent with the second duplicate never having executed (indicated, not proven).
**Next action:** apply the conflict plan; keep the coupled FK/model verification independently evidenced under item 27.

**[CLOSED] 17. Compare H2′ and H3 architectures.**

| Criterion | H2′ | H3 |
|---|---|---|
| Fresh install | Deterministic frozen root | Same; smaller replay set |
| Old-dynamic bodies | Same-ID/different-schema → parity + rewrite exception | Same hazard → parity + stamp per DB |
| Intermediates | No mapping (topology preserved) | Per-revision map + upgrade-then-stamp |
| Unknown revisions | Halt-and-map | Blocked until census |
| Enum ownership content | Identical label sets | Identical |
| Enum ownership location | Frozen root + `f91075` exception | N-squash body; `f91075` retired |
| Data preservation | No stamps; repairs conditional | Stamp-gated |
| Immutability | Violates once, explicitly | Preserves old files |
| Rollback | Downgrade chain | Re-track + re-stamp |
| Future authoring | Unchanged | Clean lineage; retired-ID ban |

Asymmetry surfaced by Phase 2: H2′ carries strictly more repair surface than H3 for the same enum-content outcome.
Subordinate 17a records compatibility conditions (i)–(vi); 17b resolves the 101/48 phantom and documents the 145 default-differences.
**Next action:** preserve H3 as the selected durable target and H2′ as the interim repair; do not let either be described as the only option.

---

# Phase 3 — Decisions and authorization (items 18–19)

**[CLOSED] 18. Approve one architecture.**
H2′ is approved and **implemented** as the interim fresh-install repair: the four previously modified migration files were repaired and committed, and the empty-database replay passed. H3/N-squash remains the **selected** durable destination; its H3-A root is now authored and active in the local review checkout, with fresh-install/workflow evidence recorded in Phase 12.
This item is closed as a *decision* item. It does **not** authorize H3-B or any existing-database cutover.
**Next action:** preserve the architecture decision and do not perform H3-B work until the Docker census, per-database transition gates, populated-state safety and reviewed transition/recovery procedure pass.

**[CLOSED] 19. Approve and execute isolated PostgreSQL verification plan.**
The plan was approved and **executed** on local PostgreSQL 18.4 against the disposable database `afcon360_h2p_replay_20261018_test`. The full empty-database replay passed, reaching `df55cbe3f516` (`flask db current` → `df55cbe3f516 (head)`, exit code 0).
Scope of this closure: the **migration** replay. The Design 2 model-bootstrap runtime verification is a separate deliverable — authorized and executed successfully (see item 20 and the 2026-10-18 reconciliation).
**Next action:** preserve the replay database as evidence and do not reuse, reset or drop it; the Design 2 bootstrap defect has been resolved and the live verification passed.

---

# Phase 4 — Implement the approved permanent repair (items 20–29)

**[CLOSED] 20. Establish canonical schema-creation architecture.**
Design 2 (`app/core/model_bootstrap.py`) is committed (`ff5fe53` + `96636f2`) with a marker row, loud registration and no false Alembic stamp. The **percent-placeholder defect has been fixed** by:

1. `_ensure_group_a_types()` now calls `connection.exec_driver_sql(sql, execution_options={"no_parameters": True})` so psycopg2 no longer rejects the `%` placeholders in `RAISE EXCEPTION`.
2. `read_persisted_enum_labels()` now filters on `sa.func.current_schema()` instead of hard-coded `"public"`, aligning with the schema-scoped `build_enum_type_block()`.

The source-level contract suite has been expanded to **38 tests** (5 new regression tests covering the `%` placeholders, the `no_parameters` execution option, schema-scope consistency, and a real import-failure path) and **all 38 pass in an isolated run that blocks any SQLAlchemy engine connection** (`pytest --noconftest`, exit code 0).

**Live PostgreSQL runtime verification** was executed on 2026-10-18 against a fresh disposable database `afcon360_d2_bootstrap_fix_20261018_test`. The first invocation of `bootstrap_model_schema()` created 217 tables, 47 enum types, left the marker row status `complete` with a matching fingerprint, and did **not** create an `alembic_version` table. The initial verification script incorrectly reported FAIL because it expected `result.state_code == "model_bootstrap_complete"` on the first run; the implementation returns `STATE_EMPTY` on a fresh creation and records completion in the marker. A subsequent read-only call to `validate_model_bootstrap()` returns `model_bootstrap_complete` (PASS). The earlier failed database `afcon360_b0_design2_rt_20261018` (pre-fix) is retained as historical evidence of the `%`-placeholder defect.
**Owner-confirmed closure (2026-10-20):** Design 2's recorded runtime and read-only validation results satisfy this item's accepted scope. Keep the migration-built and model-bootstrap routes explicitly non-equivalent. This closure does not authorize H3 implementation or database cutover.
**Next action:** no further item-20 work; broader integration and installation-contract verification remain under items 28 and 39.

**[ADVANCED] 21. Repair enum creation ownership.**
**H3-A target discrepancy (2026-10-23):** the active static baseline has 49 enum DDL statements, including `bookingstatus` (11 labels) and `org_business_category` (39 labels); the frozen B0 final-model inventory describes a 47-model-enum fresh target and excludes those two types. The successful replay and `flask db check = 0` do not resolve the scope gap: unused physical types can exist without triggering model-mismatch errors. The owner decision remains pending: (A) retain H3-A as a faithful static snapshot of `df55cbe3f516`, or (B) regenerate/review H3-A to match B0's 47-enum target. No option is selected in this register. Preserve the current artifact and provenance hash pending that decision; do not delete or convert either type.
Content (fresh-schema ownership target, with existing-state preservation): define one `CREATE TYPE` owner per enum required by the approved fresh schema, with exact approved label sets; do not create `bookingstatus` by that name in the forward fresh-install path. Preserve existing enum and String/VARCHAR representations, including test's live-used 39-label `org_business_category`, prod's distinct observed `varchar(40)` state and 4-label orphan, and the 16 dev-only orphan types. Record the three referenced legacy defaults and their observed behavior; do not convert, drop, rename, relabel or normalize these existing objects under the current policy.
Location: H2′ — frozen `8a0deccce6f6` body plus an exception or conditionalizing repair for `f91075478868`; H3 — N-squash body, where `f91075478868` retires.
**Scope clarification (2026-10-20 review branch):** the separate source change in `app/transport/models.py` removes duplicate Python enum class declarations that shadowed canonical objects imported from `app/utils/enums.py`; a database-free regression test asserts the public aliases retain canonical object identity. This is Python enum-registry ownership/identity only. It does **not** implement PostgreSQL `CREATE TYPE` ownership, resolve the H2′/H3 migration-location decision, or provide live enum/schema evidence. Item 21 therefore remains **ADVANCED**, not implemented/closed.

**Next action:** obtain the explicit owner decision recorded as subordinate 21a before changing the baseline or declaring enum ownership complete. Then prove H3-A object ownership against the chosen target. Keep PostgreSQL type-creation decisions scoped to that approved fresh schema. For existing-state evidence, preserve the 16 dev-only orphans, `bookingstatus`, both `org_business_category` representations and the three referenced legacy defaults. Do not plan or perform drops, conversions, renames, relabeling or normalization under the current preservation policy.

**[CLOSED] 22. Eliminate repeated `window_mode_enum` creation.**
Content: a single `CREATE TYPE window_mode_enum AS ENUM ('CALENDAR', 'ROLLING')`. The H2′ chain was corrected and the empty-database replay created the type once; live databases already converge.
**Scope limitation, stated explicitly:** this closure covers the **current H2′ fresh-install chain only**. No historical or intermediate-state upgrade has been verified, so the repeated-creation behaviour under those paths is untested. **H3-A fresh-install evidence (Phase 12):** the H3-A replay also created `window_mode_enum` exactly once; the resulting schema contains 49 enum types.
**Next action:** confirm the fix also behaves correctly in any supported historical/intermediate-state upgrade test once item 13 defines those states.

**[CLOSED] 23. Resolve duplicate slug migrations.**
Confirmed child-vs-child duplication: `71893e3a42a2` and `bd9d3bb673aa` create the same three objects. The H2′ chain was neutralized and the empty-database replay passed; `slug` is NOT NULL in both live databases, consistent with the second duplicate never having executed.
**Scope limitation, stated explicitly:** closure covers the **current H2′ fresh-install chain only**. Historical/intermediate-state upgrades remain unverified. **H3-A fresh-install evidence (Phase 12):** the H3-A replay also created each slug object exactly once; the resulting schema contains 224 tables with no duplicate-slug error.
**Next action:** verify supported historical-state upgrades separately under items 13 and 35.

**[ADVANCED] 24. Resolve remaining confirmed and conditional conflicts.**
The 324-row mechanical matrix is delivered: 74 CONFIRMED (declaration duplication), 229 CONDITIONAL, 21 NOT A CONFLICT, 0 PREDICTED.

**H3-A scope reconciliation (2026-10-23):** the 324-row matrix describes the retired 27-revision chain and remains historical evidence for that chain and the H2′ repair. Do not mechanically rerun all 229 CONDITIONAL rows against H3-A's single static baseline. The H3-A successful replay establishes that the baseline executes on a fresh target; it does not alone prove every object has exactly one intended creator or that the baseline matches the approved final H3 target. The remaining Item 24 work is to record explicit preservation/dependency evidence for the 16 dev-only orphan types, `bookingstatus`, and each observed `org_business_category` state, and to review any conflict findings that still apply to H3-A. No conversion, drop, rename, relabel or normalization is authorized.

| Category | Count | Action |
|---|---:|---|
| USED enum names | 48 | Create in frozen DDL, exact labels |
| REFERENCED enums | 3 | Record current default expressions and dependencies; preserve behavior unless a separately approved policy changes it. |
| ORPHAN enums (dev-only) | 16 | Preserve existing objects; record dependency evidence. No drops under the current preservation policy. |
| `bookingstatus` | 1 | Historical/legacy type in the captured snapshot; preserve pending the explicit H3-A/B0 target decision |
| `org_business_category` | — | Record test's live 39-label enum and prod's `varchar(40)` plus 4-label orphan as separate observed states; preserve both representations. No conversion or drop under the current policy. |
| CONDITIONAL rows | 229 | Historical matrix for the retired multi-revision chain; do not mechanically rerun against H3-A |

**Next action:** treat the 324-row matrix as historical evidence for the retired multi-revision chain. For current H3-A, complete the distinct object-ownership proof against the B0 final-schema inventory (subordinate 24a) and record explicit preservation/dependency evidence for the 16 orphans, `bookingstatus` and each `org_business_category` state. Do not mechanically rerun the 229 CONDITIONAL rows against the single static baseline. No drop, conversion or relabeling is authorized under the current preservation policy.

**[ADVANCED] 25. Correct foreign-key assumptions.**
The read-only Item 25 physical inventory (2026-10-23) records 411 constraints in each Reference/Production/Test/H3-A state, representing 410 distinct `(source table, local columns, target table, referenced columns)` signatures. It reports two duplicate `driver_profiles.user_id` FK definitions in every state and one semantic ON DELETE action divergence: Test's legacy `organisation_types_category_code_fkey` uses CASCADE while Reference/Production/H3-A use canonical `fk_org_types_category_code` RESTRICT.

**Source/model cross-reference (2026-10-23):** `app/identity/models/organisation_catalogues.py` declares `fk_org_types_category_code` with `ondelete="RESTRICT"`; the H3-A baseline and application classification guard agree. Retired migration `df55cbe3f516_reconcile_organisation_classification_.py` explicitly replaces the old Test-style CASCADE object with RESTRICT in upgrade and restores CASCADE in downgrade. This supports classifying Test's legacy object as superseded/defective, but is not authorization to run that retired migration or change Test.

`app/transport/models.py` declares both a column-level `db.ForeignKey("users.id")` on `DriverProfile.user_id` (implicit NO ACTION) and table-level `ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_driver_user")`. The saved physical inventory contains both `driver_profiles_user_id_fkey` (NO ACTION) and `fk_driver_user` (CASCADE) in all four states, confirming the model declaration explains the duplicate/contradictory pair. The report classifies both rows as DEFECT; which single constraint should survive remains an owner/architecture decision.

**Still outstanding:** finish the full FK-to-model/relationship/migration mapping across the relevant states, reconcile all legacy names, and qualify constraint validation status (`convalidated` was not included in saved evidence). Physical inventory and the two source-level defect explanations do not prove transition safety. Do not alter constraints until the intended disposition and state-specific parity are reviewed.
**Next action:** complete the evidence-backed mapping and cross-reference Item 27; no database repair or normalization is authorized by this finding.

**[NOT STARTED] 26. Make data-sensitive migrations safe.**
The source audit has already identified concrete populated-state hazards: `71893e3a42a2_add_organisation_slug.py` adds `organisations.slug` as NOT NULL without a default; `5e80dc4ac345_transport_reservation_obligation_and_.py` adds `transport_reservations.request_fingerprint` as NOT NULL without a default. Unique-index, CHECK-constraint and foreign-key changes also need representative-data review. These source findings identify risk; they do not prove failure or safety. No complete operation inventory, approved safe-migration design or populated-state test is recorded.
**Next action:** use these identified revisions in the complete operation inventory, then test applicable operations against representative populated data in approved disposable databases, including invalid-data rejection and preservation checks. Do not repeat the completed source discovery.

**[ADVANCED] 27. Resolve `df55cbe3f516` and coupled model changes.**
Advanced by evidence: the revision is **tracked** and reached by the clean H2′ replay; `flask db current` returned `df55cbe3f516 (head)` with exit code 0. The 2026-10-23 source review now independently confirms the duplicated `DriverProfile.user_id` FK cause and corroborates the intended `organisation_types.category_code` RESTRICT semantics. These targeted findings advance the coupling investigation but do not finish all FK/model mappings.
Not closed: remaining FK/model coupling, physical-parity and transition qualification for Production and Test remain incomplete. No database write or transition is authorized by this record.
**Next action:** complete source-to-physical mapping and state-specific parity/transition evidence for `afcon360_prod` and `afcon360_test` before closing Item 27.

**[ADVANCED] 28. Consolidate schema-creation procedures.**
Design 2 is committed (`ff5fe53` + `96636f2`). The **percent-placeholder and schema-scope defects have been fixed** and the source-level suite now comprises **38 tests, all passing** in an isolated, database-free run (exit code 0). Live runtime verification on a disposable database has **passed** (item 20): `bootstrap_model_schema()` created 217 tables and 47 enums, marker `complete`, no `alembic_version`; read-only `validate_model_bootstrap()` also passes. The 145 server-default differences (subordinate 28a) remain unresolved.
Consequence: no fresh-vs-upgraded convergence test (item 37) can pass until those defaults are normalized or explicitly declared intentional exceptions. This is a precondition, not a footnote.
**Next action:** define the official installation route; ensure `lazy_table_creator` and the test setup scripts remain test-only; normalize or formally except the server-side defaults before any parity comparison.

**[ADVANCED] 28a. Classify and disposition the 145 server-default differences.**
The 145 default differences comprise 132 Prod-only, 12 Test-only and one Both-differ case. Each must be classified against evidence and assigned an intended disposition before the fresh-versus-upgraded convergence requirement under item 37 can pass.
Principles: a physical difference is not proof that prod or test is correct; do not normalize defaults simply to make the two environments match; preserve exact observed expressions in the evidence; distinguish observations from corroborated explanations and unresolved intent; document exceptions or required schema-owner decisions. Keep the `organisations.business_category` physical type divergence visible in the convergence evidence without planning a conversion. Cross-reference items 20, 29 and 37.
The item 28a investigation may record the observed comparison as complete, but the disposition work remains outstanding.

**[CLOSED] 29. Establish permanent database engineering rules.**
**Owner-confirmed CLOSED (2026-10-20).** The owner confirmed this item closed. Retain the accepted permanent database rules, enum-creation contract, parity-evidence requirements and bootstrap-safety findings as the completed outcome. The newly requested clarification distinguishing strict ordinary Alembic autogeneration from a narrowly authorized H3 baseline-replacement exception is a scoped documentation refinement, not a reopening of Item 29.
The supplied preflight snapshot shows `.opencode/rules/afcon360-constitution.md` modified but root `AGENTS.md` not listed as modified. Therefore, do not claim that the newly requested root-rule clarification was already implemented or verified by this capture.
**Boundary:** this closure records the owner's accepted permanent-rules work; it does not authorize migration execution, H3 implementation or database cutover.
---

# Phase 5 — Prove the result and prevent recurrence (items 30–39)

**[CLOSED] 30. Create approved disposable PostgreSQL verification environment.**
Two environments were authorized and created on local PostgreSQL 18.4 and both are retained: `afcon360_h2p_replay_20261018_test` (H2′ migration replay) and `afcon360_d2_bootstrap_fix_20261018_test` (Design 2 runtime verification post-fix). Neither `afcon360_prod` nor `afcon360_test` was used as a scratch database. The pre-fix failure database `afcon360_b0_design2_rt_20261018` is also retained as historical evidence.
**Next action:** preserve all three as evidence — do not reuse, reset, drop or automatically clean them up, and keep the other pre-existing scratch databases in place.

**[CLOSED] 31. Pass clean-install migration test.**
A full empty-database replay of the entire migration path passed on **local PostgreSQL 18.4**, reaching `df55cbe3f516`; observed counts were 224 public tables, 49 public enum types, 2 non-internal triggers, 2 public functions.
**Scope limitation, stated explicitly:** this closure is scoped to the tested server version and the tested chain. Reproduction from a genuinely fresh clone and verification on the PostgreSQL version pinned by Docker are **future actions, not completed evidence**.
**Next action:** reproduce from a genuinely fresh clone and verify on the Docker-pinned PostgreSQL version; record both as separate evidence artifacts.

**[CLOSED] 32. Verify physical schema completeness independently.**
The Phase 7 extraction and pairwise comparison artifacts now record and compare the physical-schema evidence categories in scope: normalized schema output, tables, enums and label differences, agent indexes, triggers, live routines/functions, timestamp representations, foreign-key actions, and server defaults. The hashes, byte sizes, line counts and pairwise diff counts are recorded under Phase 7 and Item 14.

**Closure boundary:** the completeness/comparison investigation and divergence inventory are complete. The observed physical differences are not resolved; extension/enum/default disposition, FK/model alignment and convergence remain assigned to 14d, 21/24/25/27, 28a, 33e and 37. The three selected agent-column model defaults have focused local regression evidence recorded under 33b; this does not resolve the broader Prod/Test default differences. This closure does not authorize normalization, rebuild or cutover.

**[ADVANCED] 33. Verify model/schema parity.**
A focused H3-A parity check passed after the temporary probe field was removed: `flask db check` returned `No new upgrade operations detected.` and exit code `0` with the H3 baseline at current/head. This is model-to-physical parity evidence for the disposable H3-A physical snapshot derived from `df55cbe3f516`, not proof that H3-A matches B0's intended 47-enum fresh target and not proof of parity with `afcon360_prod` or `afcon360_test`. Subordinate 21a's target decision determines what this parity result licenses.

The 145 Prod/Test server-default differences remain unresolved. A new read-only audit (2026-10-23) against both `afcon360_h2p_replay_20261018_test` and `afcon360_chain_verify_test` confirms the exact H3/H2-prime defaults for three agent columns and identifies `accounts.owner_type` as `varchar(20)` with no server default; the two probed `event_transfer_logs` column names were absent. See subordinate 33b/33d.

The source regex scan reported three application-table candidates (`activity_logs`, `analytics_page_views`, `server_sessions`) with source class declarations absent from H3-A physical schema. The subsequent runtime audit now establishes that, after full app factory/model registration, H3-A has 223 physical app tables and 223 runtime metadata tables, zero physical-without-metadata, zero metadata-without-physical, and zero registration failures. Those three candidate classes are absent from both runtime metadata and the physical H3-A schema. This resolves the physical-table-versus-metadata comparison for H3-A and does not reproduce the prior six-table/model mismatch for this target; it does not decide whether those source classes are intentionally inactive, stale, lazily registered, or an omitted product capability. See 33c–33e.
**Next action:** prioritize confirming the intended support contract and actual deployment reachability of `server_sessions` and the analytics flush job. Then decide whether to restore supported schema/model ownership or intentionally retire/disable those paths with appropriate tests. `ActivityLog` requires a separate usage/ownership disposition. No table creation, registry change or baseline edit is authorized by this audit. Keep Item 33 ADVANCED while enum target scope, these table-feature decisions, and the broader Prod/Test default/schema parity remain unresolved.

**[CLOSED] 34. Verify current-head behavior.**
Two executions on 2026-10-23 independently repeated the ordinary second `flask db upgrade` at `h3a20261020` on `afcon360_chain_verify_test`; both exited `0`. For each run, normalized before/after schema snapshots were 886,434 bytes and 28,384 lines, with identical SHA-256 `8577c2a975d5846c3b99567a2c1d59d47b3686d893dbf23531adb9dcf40753d7`; `git diff --no-index` returned `0`, with 0 diff bytes and 0 diff lines. Evidence folders: `%LOCALAPPDATA%\Temp\afcon360_h3_head_idempotence_d1vtdvql` and `%LOCALAPPDATA%\Temp\afcon360_h3_head_idempotence_qgy09k5j`. This closes only current-head idempotence, not historical/intermediate-state, populated-state, convergence, or existing-database transition gates.

**[NOT STARTED] 35. Test upgrades from supported historical states.**
No historical or intermediate-state upgrade has been verified. Items 22 and 23 are closed for the fresh-install chain only, which does not substitute for this work.
**Next action:** agree the supported states under item 13, then replay each in a separate disposable database with representative existing data.

**[NOT STARTED] 36. Verify data and constraints.**
No data-preservation, enum-label-preservation, relationship or invalid-data-rejection verification exists.
**Next action:** validate that existing values retain their meaning, enum labels and relationships survive, and invalid data is rejected, using disposable databases with representative data.

**[NOT STARTED] 37. Compare fresh and upgraded results.**
Blocked by the 145 server-default differences (132 Prod-only, 12 Test-only, 1 Both-differ) and unresolved table ownership/model parity. The previous six-table claim still needs confirmation against runtime ORM metadata; the new regex scan did not inspect metadata and identified three application table candidates present in source but absent from H3-A physical tables.
**Next action:** disposition the defaults and obtain a runtime ORM-metadata versus physical-table diff; then independently compare fresh-install and upgraded results and explain every exception.

**[NOT STARTED] 38. Verify failure recovery.**
No recovery procedure is documented or tested for a migration failing partway through.
**Next action:** specify and test the recovery procedure, including backup restoration where necessary; do not assume every downgrade can safely undo every change.

**[ADVANCED] 39. Establish automated regression gates and close the work.**
Latest focused regression evidence: at `4a689915d58a73c79bd5483bb51477c2821a8c4e`, the owner-reported guarded selection covering nine files passed **90 tests in 4.79s** with exit code 0. The temporary guard replaced SQLAlchemy `Engine.connect`, `Engine.raw_connection` and `psycopg2.connect` with raising functions. The focused Design 2 bootstrap contract suite separately passed 38 tests in an isolated no-connection run. `python -m py_compile migrations/env.py` and `git diff --check origin/main...HEAD` passed; the synchronized working tree is clean at `c13c5a9ad59e2d1b720725f4e7298a12ab5e59e1`. That latest commit is register-only, so the tested implementation code was unchanged.
**Scope limit:** these are focused source/regression results, not the full suite or proof of PostgreSQL schema parity, migration safety, fresh-clone replay, Docker-pinned PostgreSQL replay or deployment readiness. Those remain outstanding, along with committed PostgreSQL integration gates.
**Next action:** extend the regression gate to the full suite and the outstanding PostgreSQL integration/replay, migration-graph, conflict-detection and physical-schema-verification checks. Close Item 39 only when its defined acceptance evidence passes and the final record is approved.
---

## Subordinate findings (own evidence; NOT counted in the 39)

- **10a** — Historical investigation of the "182 tables" claim complete. [RECORDED]
- **10b** — The current H2′ fresh replay recorded as PASS on PostgreSQL 18.4 (2026-10-18); historical exact 182-table claim remains unverified. [RECORDED]
- **11a** — `ensure_all_enums()` never-existed finding. [CLOSED]
- **11b** — README write/delete commits (`a1a490b` / `76a518b`). [CLOSED]
- **11c** — Native-enum creation contract corrected. [CLOSED]
- **12a** — Deployment evidence ledger recorded. [RECORDED]
- **12b** — Local 2026-10-20 preflight: Docker CLI command not found; no container-state/census result. Run from an approved Docker-enabled host; blocks H3-B. [OPEN]
- **12c** — Socket.IO/CLI-disable accommodation noted in the review as a separate uncommitted local change; confirm and record it through the normal source-review/commit process. This register update did not inspect or change Git state. [OPEN]
- **13a** — H3-A clean-install path: the active baseline was applied through the normal Flask-Migrate path on the verified local PostgreSQL 18.4 disposable target and reached `h3a20261020`. Fresh-clone and other-version reproduction remain under Item 31. [RECORDED; LOCAL PASS]
- **13b** — `_SCHEMA_SQL` search-path reset recorded as an H3-A implementation correction; retain its source review/test evidence with the H3-A record. No H3-B or existing-database transition is implied. [RECORDED]
- **13c** — Active baseline docstring is stale: `migrations/versions/h3a20261020_static_baseline.py` still says the file is isolated under `migrations/h3_candidate` and not the active chain. `scripts/h3/build_h3_candidate.py` writes its generated candidate to `migrations/h3_candidate/versions/h3a20261020_static_baseline.py`; that candidate path does not describe the active tracked file. Correct the active file's docstring to identify its actual path and sole-active-head status in a separately reviewed documentation-only change; do not alter the baseline SQL or `_SCHEMA_SQL` provenance hash. [OPEN]
- **13d** — H3-A build provenance (verified 2026-10-23): `scripts/h3/build_h3_candidate.py` read `afcon360_h2p_replay_20261018_test` at `df55cbe3f516`, PostgreSQL 18.4 / UTF8, 223 table DDL statements plus `alembic_version` (224 tables total), 49 enum DDL statements; normalized `_SCHEMA_SQL` SHA-256 `0701c42dda041f3725c59d2b8081fd4534b5f8d3359f67839aad98c8d53198da` matched the approved H2-prime capture. The builder wrote to the candidate path, not the active path, and reported `active_migration_chain_changed: false`. This confirms provenance/faithful H2-prime capture, not alignment with B0's 47-enum target. [RECORDED]
- **14a** — Stamp-timing distinction: a database stamped `8a0deccce6f6` before the enum regression has a different schema from one stamped after; same ID, no timestamp in `alembic_version`. [ADVANCED]
- **14b** — Divergent-schema preservation evidence: retain the recorded test 39-label UPPER enum and the distinct prod `varchar(40)` column plus 4-label orphan as separate states; document dependencies for the 16 dev-only orphan candidates. No conversion, drop or relabeling under the current preservation policy. [ADVANCED]
- **14c** — `org_business_category` preservation ruling (2026-10-21): production remains documented as `varchar(40)` with the separate four-label lowercase orphan enum; test remains documented as a live-used 39-label uppercase enum. Preserve each physical state independently. No conversion, drop, rename, relabel, normalization, or forced convergence is authorized. Existing-database alignment requires a separate explicit decision after per-database parity evidence. [POLICY DECIDED; PARITY OPEN]
- **14d** — Production-only `pgcrypto` extension: the saved catalog records the extension only in production, with 37 extension-backed routines (two additional production routines are deletion guards). The clean tracked-source search at `main` / `0e52802` found no direct application/migration call sites for the searched pgcrypto functions, but this is not proof that dynamic SQL, operational flows, or all database-side dependencies are absent. Preserve the existing production state while disposition remains open; do not drop it or add it to the common H3-A baseline by default. Any approved rebuild plan must explicitly assess and record whether to recreate the extension. [RECORDED; DEPENDENCY/DISPOSITION REVIEW OPEN]
- **16a** — Root-vs-child and child-vs-child classes separated. [CLOSED]
- **16b** — 324-row mechanical conflict matrix delivered (74 / 229 / 21 / 0). [DELIVERED]
- **16c** — `df55cbe3f516` vs committed HEAD FK coupling proven via `git diff`. [CLOSED]
- **16d** — Atomic tracking of `df55cbe3f516` with coupled diffs: **tracking satisfied** by the H2′ repair commit; coupled FK/model verification remains with item 27. [PREREQ — partially satisfied]
- **17a** — Compatibility conditions (i)–(vi). [RECORDED]
- **17b** — Column parity: the 101/48 gap resolved as a phantom; 1 type-diff + 145 default-diffs documented; enum inventory reconciled (prod 47+1+3+16+1 = 68; test 48+1 = 49). [CLOSED]
- **21a** — H3-A 49-vs-47 target-scope decision. H3-A currently reproduces the `df55cbe3f516` H2-prime physical state, including `bookingstatus` and `org_business_category`; B0's frozen fresh-target inventory describes 47 model-declared enum types and excludes those two. Owner must choose whether H3-A remains a faithful `df55cbe3f516` snapshot or should be regenerated/reviewed against B0. No choice is made by the evidence alone. Keep baseline/hash unchanged until an explicit decision is recorded. This decision determines how Items 21, 24 and 33 can close. [OPEN]
- **24a** — H3-A object-ownership proof against B0 final-schema inventory. Verify which of the 49 baseline enum types belong to the 47 model-declared target set and explicitly classify `bookingstatus`, `org_business_category`, and any other extras; separate this current-baseline exercise from the historical 324-row conflict matrix. Depends on the 21a scope decision. [OPEN]
- **22a** — bookingstatus root-era verification: 11 members at `449bdcd`; `NO_MATCH` added at `5322c63` in the same commit as the `SQLEnum` → `String(30)` flip. [CLOSED]
- **28a** — The 145 server-default differences (132 Prod-only, 12 Test-only, 1 Both-differ) require classification and disposition before item 37 can pass. A physical difference is not proof that either environment is correct; do not normalize merely to force a match. [OPEN]
- **33a** — Agent model alignment under `app/wallet/models/agent_float.py` and `app/wallet/models/agent_onboarding.py` is recorded; the final H3-A `flask db check` passed after removing the temporary probe. This supports H3-A metadata parity only and does not prove Prod/Test parity or the desirability of every index choice. [RECORDED; H3-A PARITY CHECK PASS]
- **33b** — Read-only physical-default probe (2026-10-23) against both H2-prime replay and H3-A verification DBs (PostgreSQL 18.4 / UTF8, `default_transaction_read_only=on`) returned the same results: `agent_onboarding_approvals.is_deleted` = `boolean NOT NULL DEFAULT false`; `agent_onboardings.is_deleted` = `boolean NOT NULL DEFAULT false`; `agent_onboardings.status` = `varchar(30) NOT NULL DEFAULT 'submitted'::character varying`. The local working-tree model now declares matching `server_default="false"` for both `is_deleted` columns and `server_default="submitted"` for `status`, retaining the Python-side defaults. The new `tests/test_agent_onboarding_server_defaults.py` passed **4/4 tests**; `git diff --check` reported no whitespace errors and only an LF-to-CRLF warning. The focused changes and test remain **uncommitted** at local `HEAD=508c7838788db56b91604a7f25cfdce3a06104b3`; other pre-existing/untracked worktree paths were also reported, so this does not represent a clean or committed repository state. `accounts.owner_type` = `varchar(20) NOT NULL` with no server default. The queried `event_transfer_logs.created_by_type` and `event_transfer_logs.current_owner_type` columns were absent in both audited schemas, so this run establishes no default for those names. Prod/Test's 145 differing defaults remain a separate unresolved audit. [CLOSED FOR THE THREE SELECTED AGENT MODEL DEFAULTS IN LOCAL WORKTREE; NOT COMMITTED; 145 PROD/TEST DIFFERENCES STILL OPEN]
- **33c** — H3-A runtime ORM/physical-table inventory (2026-10-23): the read-only audit instantiated the app, confirmed `READ_ONLY_DEFAULT=on` and `READ_ONLY_TRANSACTION=on`, and compared `db.metadata.tables` with the physical H3-A schema. Both sets contained 223 public application tables; `PHYSICAL_TABLES_WITHOUT_RUNTIME_METADATA=0`, `RUNTIME_METADATA_TABLES_WITHOUT_PHYSICAL=0`, and `MODEL_REGISTRATION_FAILURES=0`. The previously reported six-model-less-physical-table discrepancy was not reproduced for H3-A and is closed within this target/snapshot scope; this does not establish Prod/Test parity or settle older historical-state comparisons. [CLOSED FOR H3-A TABLE INVENTORY]
- **33e** — Three source-declared table classes are absent from both H3-A runtime metadata and physical schema: `ActivityLog` / `activity_logs`, `PageViewAggregate` / `analytics_page_views`, `ServerSession` / `server_sessions`.
  - `server_sessions` is referenced by authentication services/routes on login and logout. `start_server_session()` attempts a database commit, catches a storage exception, rolls back, and still returns a session ID; logout catches errors from `revoke_session()`. Because this table is absent on H3-A, the persistent-session path may fail silently on this schema. No failing login/logout run was performed in this read-only source review.
  - `analytics_page_views` is referenced by `AnalyticsService.flush_hourly_to_db()`, which adds `PageViewAggregate` rows and deletes each Redis hour key before the final database commit. If the job runs against a schema without this table, a commit failure could lose those counters. Actual task/cron scheduling was not verified.
  - `ActivityLog` is declared and covered by an import test, but this review did not find an application call site; it may be a legacy duplicate audit model, not proven obsolete.
  Treat these as code-to-schema risks requiring a focused owner decision. Do not create/drop tables or change model registration/baseline without an authorized plan. [OPEN; POTENTIAL FUNCTIONAL/DATA-LOSS RISK, NOT YET REPRODUCED]
- **33d** — Read-only H2-prime/H3-A follow-up audit (2026-10-23): both targets reported PostgreSQL 18.4, UTF8, 224 public base tables and `READ_ONLY=on`; the selected column facts are recorded under 33b. Source-level regex comparison: `LITERAL_DECLARED_TABLE_NAMES=230`, `H3_PHYSICAL_BASE_TABLES_EXCLUDING_ALEMBIC_VERSION=223`, `PHYSICAL_TABLES_WITHOUT_LITERAL_DECLARATION=0`, `LITERAL_DECLARATIONS_ABSENT_FROM_H3=7`. It did not change databases and explicitly does not close 33c. [RECORDED; RUNTIME-METADATA FOLLOW-UP REQUIRED]
- **34a** — H3-A migration workflow round trip: migration `c6c0034e7439` (`down_revision=h3a20261020`) contained only the nullable `String(32)` `agent_onboarding_approvals.h3_workflow_probe` addition. Upgrade created the expected column; downgrade returned to `h3a20261020` and removed it; final `flask db check` was clean (exit code 0), and final heads/current/history showed the single H3 baseline. This round-trip artifact alone did not prove current-head idempotence; separate subordinate 34b supplies that proof. [PASS]
- **34b** — Current-head idempotence (2026-10-23; repeated twice): on `afcon360_chain_verify_test`, PostgreSQL 18.4 / UTF8, at sole head/current `h3a20261020`, both ordinary second `flask db upgrade` executions exited `0`. For each execution, normalized before/after schema dumps measured 886,434 bytes / 28,384 lines and had identical SHA-256 `8577c2a975d5846c3b99567a2c1d59d47b3686d893dbf23531adb9dcf40753d7`; each diff exited `0` with 0 bytes and 0 lines. Evidence folders: `%LOCALAPPDATA%\Temp\afcon360_h3_head_idempotence_d1vtdvql` and `%LOCALAPPDATA%\Temp\afcon360_h3_head_idempotence_qgy09k5j`. [PASS]


Temporary evidence artifacts (`col_diff.py`, `col_diff_out.txt`, `cols_prod.txt`, `cols_test.txt` under `%TEMP%\opencode`) are **not** version-controlled; the counts recorded above are the durable record.

---

## Corrections applied since the original register

| Correction | Source |
|---|---|
| prod holds 68 enum types, not 69 | Enum dependency census |
| `organisations.slug` is NOT NULL in both DBs | Enum dependency census |
| `bookingstatus` is an orphan, not a live column type | Enum dependency census |
| "Only label divergence is `org_business_category`" withdrawn — 1 type-diff + 145 default-diffs | Phase 2 Final Reconciliation |
| Legacy-known orphan count is 12, not 10 | Phase 2 Final Reconciliation |
| 101/48 gap was a phantom — arithmetic closes as 58+43 vs 59+44 | Phase 2 Final Reconciliation |
| `ensure_all_enums()` never existed | Enum flag archaeology |
| `create_type=False` introduced at `174b625`, not `a1a490b` | Enum flag archaeology |
| `e6f319ffc8c8` is a name mismatch, not duplication | Worker 2 matrix |
| `df55cbe3f516` untracked — **superseded**; the revision is now tracked and reached by the clean replay | H2′ repair commit, 2026-10-18 |
| "No replay authorized / no clean-install evidence" — **superseded**; the isolated replay passed on PostgreSQL 18.4 | Item 19, 2026-10-18 |
| "Architecture undecided / both unapprovable" — **superseded**; H2′ approved and implemented as interim, H3 selected as destination | Item 18, 2026-10-18 |
| Design 2 runtime verification — **superseded**; first run FAILED (percent-placeholder defect), post-fix run PASS on `afcon360_d2_bootstrap_fix_20261018_test` | Item 20, 2026-10-18 |
| Group-count expression corrected: 119 + 14 − 1 = 132 (extra +1 at term 18 removed) | Default-difference audit |
| `checkfirst`-only-tables claim withdrawn; `create_type` governs enum DDL | Item 11c correction |
| `org_business_category` counted once across the union inventory | Item 17b reconciliation |
| 2026-10-23 source regex scan suggested three application-table candidates, but runtime H3-A audit subsequently showed exact 223-to-223 table-set parity with zero differences. The prior six-model-less-table claim was not reproduced on H3-A; three source-declared classes absent from both metadata and schema remain an explicit scope decision | Subordinates 33c–33e, read-only owner-supplied audit |

---

## Evidence reconciliation — 2026-10-18

### Recorded on this date

**H2′ migration replay (item 19 / item 31).** Executed on local PostgreSQL 18.4 against the disposable database `afcon360_h2p_replay_20261018_test`. Follow-up read-only queries observed:

| Observation | Value |
|---|---|
| Public tables | 224 |
| Public enum types | 49 |
| Non-internal triggers | 2 |
| Public functions | 2 |
| `public.alembic_version` | `df55cbe3f516` |
| `flask db current` | `df55cbe3f516 (head)`, exit code 0 |

**Design 2 source-level suite (item 39).** Two runs are recorded:

1. **Standard run** `python -m pytest -q tests/test_model_bootstrap_contract.py` → **33 passed**, three Flask-Session deprecation warnings.
2. **Isolated contract run** `pytest --noconftest -p no:warnings tests/test_model_bootstrap_contract.py` with `Engine.connect`/`Engine.raw_connection` blocked → **38 passed**, exit code 0, no warnings reported.

**Design 2 live PostgreSQL runtime verification (item 20).** Two separate runs are recorded:

1. **Pre-fix run** against `afcon360_b0_design2_rt_20261018` — **FAIL** (0 of 39 Group-A enums, marker `building`, no `alembic_version`). Root cause: `build_enum_type_block()` emits `RAISE EXCEPTION` with `%` placeholders; `Connection.exec_driver_sql()` rejects them. This database is retained as historical evidence.

2. **Post-fix run** against a fresh disposable database `afcon360_d2_bootstrap_fix_20261018_test` — **PASS**.

| Check | Result |
|---|---|
| First invocation of `bootstrap_model_schema()` | PASS — 217 tables created, 47 enum types created, marker status `complete`, fingerprint matches, no `alembic_version` |
| `validate_model_bootstrap()` read-only call | PASS — returns `model_bootstrap_complete`, same fingerprint, no `alembic_version` |
| Enum label validation (wrong membership / wrong order / wrong case) | PASS — 8 of 8 |
| Schema isolation vs the active-schema read path | PASS — 6 of 6 |
| Import-failure gate | PASS — 0 DB statements on failure vs 3 on control |
| Focused source-level cases | PASS — 38 of 38 |

The initial verification script incorrectly reported FAIL for the post-fix run because it expected `result.state_code == "model_bootstrap_complete"` on the first invocation; the implementation returns `STATE_EMPTY` on a fresh creation and records completion in the marker. The marker status `complete` and the subsequent read-only validation are the true completion evidence. The pre-fix database `afcon360_b0_design2_rt_20261018` is preserved as historical evidence of the `%`-placeholder defect.

### Remaining verification gaps

1. Complete test suite — not run.
2. Fresh-clone replay — not verified.
3. PostgreSQL 15 / Docker-pinned replay — not verified.
4. Historical and intermediate-state upgrades — none verified (items 22 and 23 are closed for the fresh-install chain only).
5. Full physical-schema parity against an approved expected schema — not proven (item 32).
6. Model-versus-physical parity — not run (item 33).
7. Per-database parity artifacts for `afcon360_prod` and `afcon360_test` — not produced (items 14, 27).
8. 145 server-default differences — unresolved (subordinate 28a).
9. Six model-less tables in the migration-built schema — disposition outstanding (items 28, 37).
10. FK/model coupling for `df55cbe3f516` — not independently verified (item 27).
11. Second upgrade at head with before/after comparison — not recorded (item 34).
12. Design 2 bootstrap defect fix and re-verification — **resolved** (item 20 live PASS, read-only validation PASS).
13. H3/N-squash root — does not yet exist.

---

## What is blocking us today

- **Docker census** (subordinate 12b) — the local preflight could not find the Docker CLI, so container state is unknown. Run the read-only Q1–Q4 census from an approved Docker-enabled host before H3-B planning advances.
- **State-by-state H3 transition procedure** (item 15) — the H3 probe round trip passed, but root-stamped/intermediate/at-head/unknown cases and the full recovery/runbook rules remain unverified. Subordinate 13c also records the stale baseline docstring.
- **FK/model coupling and per-database transition qualification** (items 25 and 27) — FK-action differences are now recorded, but complete name/column/target/action/model mapping and per-database transition evidence remain prerequisites before any stamp or existing-database upgrade.
- **Default and table dispositions** (28a, 33e) — the 145 Prod/Test server-default differences remain open; the three selected `agent_onboarding` model defaults are aligned to the read-only H2-prime/H3-A facts in local worktree evidence under 33b. H3-A runtime ORM/physical table-set comparison passed with zero mismatches. `server_sessions` is called by authentication login/logout code and `analytics_page_views` by a flush routine whose scheduling remains unverified; decide whether to restore their schema/model ownership or intentionally retire/disable those paths before Item 37 can pass.
- **Populated-state safety and data/constraint preservation** (items 26 and 36), historical/intermediate-state upgrades (35), failure recovery (38), and full automated/integration gates (39) remain outstanding. Item 34's current-head idempotence proof is CLOSED.
- **Production-only `pgcrypto`** (14d) — keep the observed production extension intact; any future in-place or rebuild plan must state its extension decision explicitly. No H3-B or database change is authorized.

Resolved/closed by evidence: Item 13's support-policy definition; Item 14's physical-schema comparison work; Item 32's comparison inventory; Item 19's H2′ disposable replay; `df55cbe3f516` tracking (16d tracking portion); and the Design 2 bootstrap defect. Item 13's closure is policy-only and neither it nor Items 14/32 authorizes H3 cutover.

---

## Status summary by phase

| Phase | Items | Status mix |
|---|---|---|
| Phase 1 — Findings established | 1–8 | 8 closed |
| Phase 2 — Evidence for the architecture decision | 9–17 | 6 closed (9, 11, 13, 14, 16, 17) · 2 advanced (12, 15) · 1 partial (10) |
| Phase 3 — Decisions and authorization | 18–19 | 2 closed |
| Phase 4 — Implement the approved permanent repair | 20–29 | 4 closed (20, 22, 23, 29) · 5 advanced (21, 24, 25, 27, 28) · 1 not started (26) |
| Phase 5 — Prove the result and prevent recurrence | 30–39 | 4 closed (30, 31, 32, 34) · 2 advanced (33, 39) · 4 not started (35, 36, 37, 38) |

Parent totals: **24 closed + 9 advanced + 1 partial + 0 open + 0 gated + 5 not started = 39.** Subordinates (10a/10b, 11a–c, 12a–c, 13a–d, 14a–d, 15a, 16a–d, 17a/17b, 21a, 22a, 24a, 28a, 33a–d, 34a/34b) are counted separately and never added to the 39.

---

## Definition of complete

The approved installation path passes a clean PostgreSQL replay **on every supported server version and from a genuinely fresh clone**; supported upgrades preserve data; the resulting schemas independently match an approved expected schema; model/physical parity and per-database parity are evidenced; the server-default and model-less-table dispositions are closed; and automated checks guard against recurrence. A successful fresh-install replay on one server version is necessary but not sufficient.

---

## Safety

`afcon360_prod` and `afcon360_test` remain protected from further write operations. The intended `c6c0034e7439` H3 workflow round trip was positively target-verified against the disposable `afcon360_chain_verify_test` on local PostgreSQL 18.4: it was upgraded and downgraded, the probe column was confirmed absent afterward, and the database returned to `h3a20261020`. The temporary model probe and generated test migration were removed; final `flask db check` returned exit code 0 with no new operations. **Separate target-attribution caveat:** an earlier transcript in this same investigation showed `flask db upgrade` reporting `h3a20261020 -> be66d9e12e0a` for `system_configs.cycle_probe_note`, before the effective database for that command was recorded. A later read-only diagnostic on `afcon360_chain_verify_test` showed `h3a20261020` and no `cycle_probe_note` column, but that does not identify the earlier command target or prove its disposition. Therefore this register does not claim that the earlier `be66d9e12e0a` attempt did or did not touch any other database; reconcile its target from existing command/configuration evidence before making that assertion, and do not rerun migrations as an investigative shortcut. No database was created, dropped or reset as part of the verified `c6c0034e7439` round trip, and no pytest suite was run as part of it. Existing dirty/untracked work must be preserved; Git status was not checked or changed for this register update, and no commit is claimed. The H2′/Design 2 verification databases and all pre-existing scratch databases remain retained; do not automatically clean them up. `df55cbe3f516` and its coupled changes remain preserved. The original DOCX is retained as reference at `C:\Users\OBED\Desktop\AFCON360_Database_Reliability_Master_To_Do_and_Fix_Register.docx`; this Markdown file is the working register.

---

## Next action

**Precondition — close out the working tree before starting the dependency-ordered list.** The 23 October review directed that the three bodies of work be committed in this order, re-running `flask db check` as the canary immediately before each commit: (1) **model alignment** — `app/wallet/models/agent_float.py`, `app/wallet/models/agent_onboarding.py`; (2) **Stage C** — the 27 retirements under `migrations/_retired_versions/`, `migrations/versions/h3a20261020_static_baseline.py` (with the 13c docstring correction applied first), deletion under `migrations/h3_candidate/versions/`, and the staged CLI hunks of `app/production_console/streaming.py`; (3) **Socket.IO CLI disable** — `app/__init__.py`, `app/config.py`, `app/realtime.py`, the remaining streaming/route changes, and templates.

Read-only Git inspection for this amendment finds all three bodies already present in the single commit `bd289ac` (current `main` and `origin/main`), so the requested three-commit sequence is superseded; do not rewrite the pushed history to recreate it. The remaining uncommitted state is the post-round-trip cleanup — removal of the temporary `h3_workflow_probe` from `app/wallet/models/agent_onboarding.py` and deletion of `migrations/versions/c6c0034e7439_verify_h3_migration_workflow.py`. Commit that cleanup first, with `flask db check` as the canary. This amendment changes no Git state and claims no commit.

The next actions, ordered by dependency:

1. **Complete the Docker census** (subordinate 12b) from an approved Docker-enabled host; the local command-not-found result does not establish container state. Review subordinate 12c separately.
2. **Complete FK/model coupling and transition qualification** (items 25 and 27) using the newly recorded physical comparison and state-specific evidence. Item 14/32 comparison work is closed, but the databases remain physically divergent.
3. **Complete populated-state migration-safety tests** (item 26) and data/constraint preservation (36) in approved disposable databases; no Prod/Test writes.
4. **Disposition the 145 Prod/Test server-default differences and review the source-to-schema status of `server_sessions`, `analytics_page_views` and `activity_logs**` (28a, 33e). The three selected agent-column model defaults have local regression evidence recorded under 33b, but H3-A runtime table-set parity does not excuse an active source path without its table. Then complete fresh-vs-upgraded convergence (37).
5. **Complete Item 15's state-by-state transition runbook, Item 35 historical-state tests, Item 38 failure recovery and Item 39 expanded regression/integration gates.** Item 34's second-upgrade/head-snapshot criterion is already CLOSED on two runs; it need not be repeated unless source changes invalidate its evidence. Correct the stale H3 baseline docstring recorded by subordinate 13c through the appropriate review process.

Item 13's policy definition is closed. Do not reopen it merely because operational transition gates remain. The H3-A rehearsal does not authorize H3-B, database rebuilding, stamping, or any transition to `afcon360_prod` or `afcon360_test`.

---

## Phase 6 — Evidence and status reconciliation (2026-10-18)

This section is the current evidence snapshot. Where earlier sections contain "outstanding", "not authorized", "no migration executed", or "no evidence" language from the pre-replay snapshot, use this dated reconciliation for current status. Historical claims about the exact 182-table schema produced at the original commit are not silently rewritten.

### Published commits

The owner reported a successful push of `main` from `f0c41e7` to `6c0683793ad186024b863db494860cafc7eef1d6`. The remote comparison confirms four commits ahead of the prior base. The pushed commits include:

- `ff5fe53` — Design 2 model-bootstrap marker, loud model-registration checks, removal of false Alembic-head stamping, and source-level contract tests.
- `ef8ddd2` — H2′ explicit frozen root DDL plus downstream enum/check/slug reconciliations.
- `6c06837` — B0 enum inventory/plan evidence artifact.
- The fourth commit, `fbd54e1`, predates the two database-specific commits and includes wallet/admin work; its inclusion was visible in the remote comparison. It is not a database-reliability fix and should not be conflated with H2′ evidence.

A follow-up commit `96636f2` (after this snapshot was drafted) contains the Design 2 `%`-placeholder fix, 5 additional regression tests (33 → 38 in isolated run), and updates to this register's status lines to reflect Design 2 having moved from "uncommitted" to "committed".

**Known defect in `96636f2`:** the register file committed in this push contains unresolved Git merge-conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) inherited from merge commit `0abb8d0`. The version of this document you are now reading is the reconciled clean version superseding that conflicted copy.

### Empty-database replay evidence

Target: `afcon360_h2p_replay_20261018_test`, created from `template0` with UTF-8 after an initial empty-state query reported zero public tables. On local PostgreSQL 18.4, `flask db upgrade head` logged the full current migration chain and ended at `df55cbe3f516`. Read-only follow-up queries recorded:

- 224 public tables;
- 49 public enum types;
- 2 non-internal triggers;
- 2 public functions;
- `public.alembic_version = df55cbe3f516`;
- `flask db current` returned `df55cbe3f516 (head)` and exit code 0.

The target database was empty before the successful replay. This is a PASS for the **current H2′ empty-database replay on this PostgreSQL 18.4 instance**. It is not evidence that either existing production/test database was upgraded, that a fresh clone has been tested, that PostgreSQL 15 passes, or that the resulting schema fully matches existing databases or SQLAlchemy metadata.

### Design 2 source-level verification

Standard run `python -m pytest -q tests/test_model_bootstrap_contract.py` returned `33 passed, 3 warnings`. Isolated run `pytest --noconftest -p no:warnings tests/test_model_bootstrap_contract.py` with `Engine.connect`/`Engine.raw_connection` blocked returned `38 passed`, exit code 0. The warnings in the standard run were Flask-Session filesystem-backend deprecations.

### Design 2 live PostgreSQL verification

Executed 2026-10-18 against `afcon360_d2_bootstrap_fix_20261018_test` (fresh, empty). First invocation created 217 tables, 47 enums, marker `complete` with matching fingerprint, no `alembic_version`. The subsequent read-only `validate_model_bootstrap()` returned `model_bootstrap_complete`. The earlier pre-fix database `afcon360_b0_design2_rt_20261018` remains preserved as historical evidence of the `%`-placeholder defect.

### Open decisions and evidence boundaries

- The H3 N-squash root does not exist yet. H3 is the selected durable target; H2′ is the interim repair to the existing chain, not a replacement for H3.
- The 145 server-default differences remain observed and unresolved: 132 Prod-only, 12 Test-only, and one Both-differ. Do not normalize them without per-column intent/disposition.
- Six tables in the migration-built schema lack current SQLAlchemy models; their retain/model/drop disposition remains open.
- Legacy enum/orphan types, referenced enum/default handling, `organisations.business_category` divergence, and the coupled FK/model parity remain unresolved for existing databases.
- The full pytest suite, fresh-clone replay, PostgreSQL 15/Docker replay, supported historical-state upgrades, current-head repeat-upgrade comparison, full schema parity, data/constraint behavior, and failure recovery have not yet been verified.
- `afcon360_prod` and `afcon360_test` were not upgraded or modified during the work described here. Preserve the replay and investigation databases until evidence review; no automated cleanup is authorized by this register update.

---

## Phase 7 — Local read-only preflight reconciliation (2026-10-20)

This section records the owner-supplied PowerShell output from the local checkout. The capture made no database connections, ran no migrations, did not stamp a revision, and did not execute tests. It supplements rather than replaces earlier physical-schema evidence.

### Local repository state

- `HEAD`: `e3f4c4f9719f555d277b0d79b5f99601c67fd72e`, matching the source snapshot used by this register.
- At the time of this capture, before the WIP checkpoint commit, seven tracked files were modified and nothing was staged: `.opencode/rules/afcon360-constitution.md`, `AFCON360_ID_Architecture_and_Aider_Plan.md`, `DATABASE_SCALABILITY_ROADMAP.md`, `app/transport/services/booking_service.py`, `docs/POSTGRES_TESTING_CONTRACT.md`, `docs/enum-workstream-closeout.md`, and `scripts/migrate_enums_to_strings.py`.
- `enum_query.py` was untracked at that time. The later WIP checkpoint `decf23f149c7a6f00029ebda8dafb54cfb336b8b` committed those eight files; root `AGENTS.md` was not included and remained a local modification. That local rule diff has since been recreated on this review branch and must be reconciled before syncing the local checkout. This is chronology, not acceptance of the original utility implementation.
- `git diff --check` returned exit code 0. Git emitted LF/CRLF conversion warnings for several modified text files; these were warnings, not reported whitespace errors.
- The local existence check for `docs/transport/reference/CONSTITUTION-ARCHIVE.md` returned `False`. Track this separately as a documentation/governance discrepancy; do not reopen Items 20 or 29.

### Static migration graph

The no-database Alembic parser returned 27 revisions, one base (`8a0deccce6f6`) and one head (`df55cbe3f516`). This confirms the static graph is single-base/single-head in this checkout; it does not prove fresh-clone replay, physical-schema parity, or support for any particular existing starting state.

### Docker census

The preflight raised `CommandNotFoundException` because `docker` was not recognized. No container census was collected and no container status was observed. Item 12b remains OPEN and H3-blocking until the read-only Q1–Q4 census is obtained from an approved Docker-enabled host. Do not translate command-not-found into a claim that containers are down.

### Autogeneration hooks

The local source search reconfirmed that `migrations/env.py` contains the stale comment saying enums were converted to String columns; `skip_enum_create()` returns the operation unchanged, and `include_object()` returns `True` for all objects. Record this as a source/comment/configuration review finding. Do not infer a proven runtime defect or change behavior without a separately authorized review.

### H3 and physical-schema boundary

The local H3 plan describes the N-squash as documentation/review only; the H3 root does not exist yet. The preflight did not connect to `afcon360_prod`, `afcon360_test`, or a disposable database. Existing recorded table/enum/default discrepancies remain prior evidence and were not freshly measured. H3 remains blocked by the supported-starting-state decision, Docker census, coupled FK/model verification, and per-state physical-parity evidence.

### Follow-up review of governance and branch updates (2026-10-20)

- **`4a7af1130d57c8047aa6297c53ee604ac3f65edc` — AGENTS.md §8 consolidation:** the reviewed 18-line deletion removed the older duplicate rendition of “One-time authorized baseline reconstruction (H3/N-squash)”; the newer single §8 remains. The surviving section still restricts the exception to an explicitly owner-authorized baseline/history-replacement operation and does not relax the ordinary-migration autogeneration rule. This is a verified deduplication, not unexplained policy loss.
- **`9a8d19b0ac611feeabd053ff803b4bebe8552d53` — Item 13 register-only update:** records the recovered starting-state proposal and explicitly says approval was not found. It changed no application code, migrations or databases.
- **Guarded 90-test evidence:** retain the “owner-reported” label. The result and exact test selection/guard are recorded in Phase 8, but no separate raw terminal transcript artifact was added to the repository. Do not represent the concise result record as an independently archived raw log.
- **Shared WIP commit history:** `decf23f` and `d8ce306` remain in the already-pushed branch. They are deliberately not reworded in place here: doing so would rewrite shared ancestry and require a force update. If a clean commit narrative is a merge requirement, prepare and review a separate integration branch from the approved base; do not rewrite this shared branch without explicit authorization.
- **Preservation-policy wording:** active Item 21/24 and subordinate 14b/28a guidance has been corrected in this update to describe preservation records and separate physical states, not conversion/drop plans. Older dated findings remain historical evidence, not current authorization to alter database types.

---

## Phase 7 — Physical-schema investigation resolved (2026-10-21)

Three independent investigations produced contradictory claims. Two (Reports
B and C) claimed "byte-identical schemas" while listing different SHA-256
values — an internal contradiction. Report A was substantively correct.

Ground truth (script `scripts/h3/extract_physical_evidence.py`):

  Database    Bytes     Lines    SHA-256 (normalized)
  Reference   919,891   28,367   0701c42dda041f3725c59d2b8081fd4534b5f8d3359f67839aad98c8d53198da
  Prod        929,285   28,702   4485e14f910a16be1a766be355e27ed4724e744eca90faba428e522b71396c3e
  Test        921,768   28,411   0326f5d7b8891cfa344c74d5b3805565b80f68e2e9f1f4ca44829249954d4c5b

  Diff line counts (proven, not inferred):
    Reference vs Prod: 2,273 lines (93,910 bytes)
    Reference vs Test:   711 lines (35,664 bytes)
    Prod vs Test:      2,311 lines (93,240 bytes)

Confirmed divergences (all three databases at df55cbe3f516):
  - Enums:    prod has 68 (19 more than ref/test's 49)
  - Agent indexes: prod and test each have 29 (15 more than ref's 14)
  - Triggers: ref 2, prod 2, test 0 (guard triggers missing from test)
  - Functions (live catalog): prod 39 (2 guards + 37 pgcrypto),
                              ref 2, test 0
  - pgcrypto: installed only in prod
  - Agent timestamps: 12 columns differ between ref and prod/test
                      (ref=timestamptz, prod/test=timestamp without tz)
  - FK actions: 4-6 FKs differ per pair (incl. organisation_types.category_code
                RESTRICT vs CASCADE)
  - 145 server-default differences (per Item 28a)

pgcrypto follow-up — now recorded under subordinate finding 14d:
  The saved catalog records pgcrypto only in production. The production
  routine definitions identify 37 routines backed by $libdir/pgcrypto, plus
  two deletion-guard routines (39 production routines total). The tracked
  repository search on clean main at 0e52802 found no direct application or
  migration call sites for the searched pgcrypto SQL functions. Search hits
  included this investigation note, an unrelated btree_gist backlog item,
  H3 guard-tool queries of pg_catalog.pg_extension, and pg_depend inventory
  field names; these are not direct pgcrypto application calls.
  This is evidence that direct tracked-source use was not found, not proof
  that all dynamic-SQL, operational, or database-side dependencies are absent.
  The H3-A baseline omits pgcrypto. That does not by itself mean an in-place
  transition will remove the extension. If a new/rebuilt target is selected,
  the transition plan must explicitly assess and decide whether to recreate it.
  Do not add it to the canonical H3-A baseline or drop/align it without a
  separate reviewed and authorized decision. No database change is authorized.

Report methodology note (record for future reference):
  "Empty console output" from a redirected `diff` command is NOT evidence of
  identical files. Two independent agents (B and C) made this error and
  concluded "byte-identical" while their own SHAs proved otherwise. Going
  forward, any identity claim must show: file size in bytes (must be 0),
  exit code (must be 0), and first 10 lines of the diff file (must be blank).

Implications for Item 13 Case 2:
  The 2,273-line reference-vs-prod diff confirms that an existing database at
  df55cbe3f516 requires independent physical parity and a reviewed transition
  plan; the approved support policy remains in force.
  The plan must explicitly disposition production-only pgcrypto. For an
  in-place path, verify preservation rather than assuming the H3-A baseline
  implicitly removes or recreates the extension. For a rebuilt target, decide
  explicitly whether it must be recreated after reviewing dependency and
  operational evidence. Do not add it to the shared H3-A baseline by default.
  This clarification does not authorize H3-B, a rebuild, or database changes.

Artifacts: %TEMP%\afcon360_physical_schema_investigation\manual_inspection\
  (regenerable; SHAs above are the durable evidence).

---

## Phase 8 — Checkpoint source review and remote remediation (2026-10-20)

This section records the additional owner-supplied read-only query output for checkpoint `decf23f149c7a6f00029ebda8dafb54cfb336b8b` and the subsequent source-only corrections prepared on `work/db-reliability-harmonization-2026-10-20`. No database connection, migration, or test execution was performed by these edits.

### `enum_query.py` — hard-coded database target removed

The checkpoint version contained a literal `postgresql://postgres@localhost:5432/afcon360_test` DSN and connected without explicitly setting a read-only session. Its query was SELECT-only, but the hard-coded target made the utility environment-specific and insufficiently guarded. The attempted secret scan used `Select-String -SimpleMatch` with a regex-like pattern, so its empty output did not prove the patterns were absent.

The full 99-line review-branch source was read. It has no hard-coded DSN or credential literal; it reads only `TEST_DATABASE_URL`, accepts only `localhost`, `127.0.0.1`, or `::1`, requires a database name ending in `_test`, enables PostgreSQL read-only mode at connection and session levels, issues only a catalog `SELECT`, rolls back/closes the connection, and reports only the exception type rather than printing the DSN. The placeholder DSNs in `tests/test_enum_query_guard.py` are test inputs only; that test module calls only `validate_local_test_dsn()` and does not connect. The helper's `--execute` mode is rejected before output generation. The source was inspected for these constraints; this is not a repository-wide secret scan.

### `booking_service.py` — change provenance and shared enum identity

The diff for checkpoint `decf23f` changes a small set of remaining `BookingStatus` references to the already-imported `BookingStatusPy` alias; the rest of the `BookingStatusPy` usage was already present in its parent. The subsequent read-only inspection exposed a source inconsistency: `app/transport/models.py` assigned public shared enum aliases near the imports and then redeclared eight of those enum classes later, shadowing the shared aliases despite the file's stated re-export contract.

The review branch removes those duplicate local definitions for `VerificationTier`, `ComplianceStatus`, `BookingStatus`, `PaymentStatus`, `VehicleClass`, `IncidentSeverity`, `Currency`, and `ProviderType`, leaving transport-specific `PassengerStatus` intact. The `app/utils/enums.py` header now describes the actual shared-definition contract rather than falsely claiming all database columns use String plus CHECK. A database-free identity contract test was added for the eleven shared public enum exports. The owner then synchronized the follow-up commits and reran the nine-file selection at `4a689915d58a73c79bd5483bb51477c2821a8c4e` with a temporary pytest plugin that replaces `Engine.connect`, `Engine.raw_connection`, and `psycopg2.connect` with functions that raise. The guarded selection passed all 90 tests in 4.79s, exit code 0. This supports the focused suite's behavior under those connection guards; it is not proof that every possible database-driver or subprocess connection path is universally blocked, and it does not establish physical PostgreSQL schema parity or migration replay correctness.

### Root migration rule and mirror

The query confirmed that the local `AGENTS.md` edit was not included in checkpoint `decf23f`. The review branch now carries the permanent rule in root `AGENTS.md`, with strict autogeneration for ordinary migrations and one bounded baseline-reconstruction exception in its single subsection 8. The mirrored constitution references its detailed exception in §20.3.1 rather than duplicating it at §20.1. An aggregate source review at checkpoint `e27e7b8b144723e6de7837e811032ecc0612dfe8` confirmed that the duplicate subsection 8 was removed and the root/mirror preserve the strict ordinary-migration rule; no weakening was found.

### Alembic environment comments

The source review found a stale claim that all enums had been converted to String, an unused `skip_enum_create` rewriter, and an allow-all `include_object`. The branch removes the unused rewriter/imports, accurately documents the allow-all callback, and later removes the inaccurate `user_module_prefix` comment that had implied it prevents enum type drops. No enum suppression or other autogeneration filtering behavior was introduced. `python -m py_compile migrations/env.py` passed on the tested checkout. No dedicated live Alembic autogeneration or migration-replay test was run; runtime schema-diff behavior remains unverified.

### Branch-history and attribution boundary

At review checkpoint `e27e7b8b144723e6de7837e811032ecc0612dfe8`, the review branch was 32 commits ahead of `main` across 17 changed files; the subsequent reviewed/tested checkpoint `4a689915d58a73c79bd5483bb51477c2821a8c4e` was 33 commits ahead across the same 17 files before this register-only evidence update. The earlier `decf23f` and `d8ce306` WIP checkpoint messages remain in the shared branch history. They have **not** been rewritten or force-pushed; there is no PR or merge. If a clean commit narrative is required before integration, prepare a separate integration branch from the approved `main` base and consolidate the reviewed final diff there rather than rewriting this pushed branch. GitHub author metadata for commits created through the connected GitHub integration reflects the configured account and is not independent proof of who manually authored each change; this register is the change/provenance record.

### Verification boundary

**Owner-reported local evidence (2026-10-20):**
- Most recent tested checkout: `4a689915d58a73c79bd5483bb51477c2821a8c4e`; it was synchronized to `origin/work/db-reliability-harmonization-2026-10-20`.
- `git status --short`: clean before and after the guarded run.
- `git diff --check origin/main...HEAD`: PASS, no output.
- `python -m py_compile migrations/env.py`: PASS.
- Focused command: `python -m pytest --noconftest -p no:warnings -p afcon360_no_db_guard -q` across `test_enum_query_guard.py`, `test_migrate_enums_to_strings_cli.py`, `test_transport_enum_registry_identity.py`, `test_check_constraints.py`, `test_model_bootstrap_contract.py`, `test_enums.py`, `test_audit_log_import.py`, `test_org_default_users_relationship.py`, and `test_audit_enum_writers.py`.
- Guard supplied from the user's temporary directory replaced SQLAlchemy `Engine.connect`, `Engine.raw_connection`, and `psycopg2.connect` with a raising function. Result: **90 passed in 4.79s; guarded pytest exit code 0**.
- The earlier unguarded focused run also passed 90 in 10.83s; the guarded run supersedes it for connection-guard evidence.

**Scope limit:** this was a focused regression selection with `--noconftest`, not the full test suite. The temporary guard blocked SQLAlchemy engine connection/raw-connection entrypoints and `psycopg2.connect`; all 90 selected tests passed under that guard. This is stronger evidence than the earlier unguarded run, but it is not a universal proof against every conceivable connection path (for example, a separate subprocess or unpatched driver could have its own path). The tests did not run an actual PostgreSQL query, execute migrations, inspect physical schema, or conduct a Docker census. Therefore they do not establish schema parity, clean-install replay, existing-database transition safety, or production readiness. The guarded **focused-source regression gate is PASS**; database and deployment gates remain separate.

After the initially tested commit `aa911d07f0e22c7c5b5523d0f83f77ab71387544`, the branch received documentation/comment-only follow-ups: the duplicate baseline-exception heading was consolidated in `AGENTS.md`; a stale `flask db stamp head` quick-reference command and an overbroad autogeneration claim were corrected in the historical roadmap; the enum-storage comment in `app/transport/models.py` was clarified; and this register was reconciled with the review findings. The owner then synchronized checkpoint `4a689915d58a73c79bd5483bb51477c2821a8c4e`, reran the guarded suite successfully, verified `migrations/env.py` compilation and the diff check, and reported a clean tree. No model declaration, executable Python statement, migration operation, or database schema changed in those follow-ups.

Preserve the existing enum-representation policy and H3 readiness gates; do not infer database readiness from the focused test result.


---

## Phase 9 — Master-list and status reconciliation (2026-10-20)

**Historical snapshot:** the status counts and Item 13 assessment in this section describe the 2026-10-20 state. The 2026-10-23 Phase 12 reconciliation supersedes those current-status claims.

The top-level register has been restored to an actionable four-column format: **Item, Description, Expected test / acceptance evidence, Status**. Every one of the 39 top-level items is represented once. The status tally is reconciled to **20 CLOSED, 11 ADVANCED, 1 PARTIAL, 0 OPEN and 7 NOT STARTED**; subordinate entries remain outside the 39-item count.

Item 13 is **ADVANCED, not CLOSED**. The updated 2026-10-20 readiness tree supplies a concrete proposed support matrix, but explicitly says owner approval remains outstanding. The proposal is recorded under Item 13; confirm/amend it before treating the policy as decided or running historical-state tests.

Item 39's main entry reflects the guarded 90-test run and its evidence limits. The follow-up governance review also verified the duplicate §8 consolidation and the Item 13 commit, retained the owner-reported evidence boundary, and corrected active Item 21/24/14b/28a guidance to match the no-conversion/no-drop preservation policy. WIP commit messages were not rewritten on the shared branch. No migration, database write, H3 root creation or cutover authorization is implied by this register update.


### Item 13 recovery outcome

The earlier readiness-tree artifact was recovered and read. It contains a proposed state-support policy—not evidence of owner approval. The policy is now reproduced in Item 13 with each case and its acceptance condition. No approval is inferred, and no migration or database action followed from this review.

---

## Phase 10 — Preservation wording and branch review closeout (2026-10-20)

This consolidated documentation update records the inspected `4a7af11` §8 deduplication and register-only `9a8d19b` Item 13 change, preserves the honest owner-reported label on the guarded 90-test result, and removes active conversion/drop recommendations that conflicted with the locked preservation policy. The existing WIP commits remain unchanged because this branch is already pushed; any cleaned integration narrative must be produced on a separate integration branch, not by rewriting shared history. This documentation update does not unblock H3 or satisfy the missing constitution-archive reference, Docker census, per-database parity, FK/model, populated-state or failure-recovery gates.

---

## Phase 11 — H3-A authorization, version choice and isolated apply tooling (2026-10-21)

**Historical snapshot:** this section records the state as of 2026-10-21. Its statements that the active baseline had not yet been applied and H3-A was not yet PASS are superseded by the 2026-10-23 Phase 12 evidence; the remaining H3-B safety restrictions remain in force.

The owner explicitly authorized H3-A authoring and disposable verification. The approved Item 13 policy is now recorded in the top-level row: support a clean database only after a successful replay; consider an existing database at `df55cbe3f516` only after independent per-database physical-schema parity and a reviewed transition plan; support older revisions only if exact revisions are explicitly enumerated and tested; fail closed for unknown/divergent states. This is not H3-B authorization.

**Version decision:** PostgreSQL 18.4 is the H3-A reproducibility target because it is the working environment used for the approved H2-prime replay. The H3 tooling now requires 18.4 and UTF8 for this first replay. The later move to the current 18.x minor is deferred to a separate compatibility/security step; it must not be confused with baseline correctness.

**H3-A tooling changes on the review branch (through `74eb1ecc4ec29dbc1f8f0523a354c01ec3776e09`):**
- Added `scripts/h3/apply_h3_candidate.py`: default read-only preflight; explicit `--create-database` and `--apply` actions; strict candidate database-name allowlist; no auto-drop/reset; candidate SQL provenance-hash validation; isolated Alembic registration check; read-only post-apply revision/table/enum checks; and sanitized failure output.
- Pinned the builder to the recorded normalized source-schema hash `514b392f9b8a812b95c9e9681f713cfde86c726ee8a9eff36db2750123068825`. A different source dump or edited candidate now fails closed pending review.
- Extended the candidate Alembic environment to require loopback PostgreSQL, the approved disposable name pattern, an empty target, and PostgreSQL 18.4. Candidate creation additionally checks source/target server version and encoding before creating the disposable database.
- Added source-only tests for database-name protection, candidate hash/revision validation and CLI import paths; updated the workflow to install Alembic and include those tests.
- Updated the runbook to use both package/module and direct-script-safe CLI invocations and to document the separate `org_business_category` preservation ruling.

**Evidence boundary at this snapshot:** the owner-reported builder run generated a local untracked candidate at `migrations/h3_candidate/versions/h3a20261020_static_baseline.py` with source hash `514b392f9b8a812b95c9e9681f713cfde86c726ee8a9eff36db2750123068825`; its eight builder tests passed, and `py_compile` passed. The newly added apply tests and wrapper have **not yet been reported as executed on the owner's synchronized local checkout**. The candidate has not yet been applied and compared on a fresh disposable database, so H3-A is not PASS and its candidate file must not be committed/promoted yet.

`org_business_category` is recorded separately as subordinate 14c, not as a rule that permits conversion. Neither `afcon360_prod` nor `afcon360_test` was accessed or modified by these repository source changes. H3-B remains unauthorized; per-database parity, populated-state safety, backup/recovery evidence and an explicit later cutover decision are still required. The missing `CONSTITUTION-ARCHIVE.md` reference remains a separate governance discrepancy and was not fabricated or silently resolved in this phase.

---

## Phase 12 — H3-A activation, physical-schema reconciliation, and migration-workflow verification (2026-10-23)

This is the current status reconciliation. It supersedes the earlier status counts and any earlier snapshot statements that H3-A had not yet been activated/applied or that the Item 13 support policy remained unapproved. Phases 6–11 remain as dated historical evidence. This phase records owner-supplied local results; it does not claim that the assistant independently accessed the Windows checkout or PostgreSQL instance.

### Accepted top-level status changes

| Item | Previous status | Current status | Acceptance boundary |
|---:|---|---|---|
| 13 — Define supported starting revisions | ADVANCED | **CLOSED** | Owner-approved four-case support policy is defined and recorded. This closes policy definition only; any existing database still must pass its own physical-parity and reviewed-transition gates. |
| 14 — Compare H2′ with existing database states | ADVANCED | **CLOSED** | Reference/Prod/Test physical comparison completed; measured differences and hashes are recorded. The comparison result is divergence, not alignment. |
| 25 — Correct foreign-key assumptions | NOT STARTED | **ADVANCED** | Physical investigation surfaced 4–6 FK-action differences per pair, including `organisation_types.category_code` RESTRICT vs CASCADE. Full FK/model mapping is still required. |
| 32 — Verify physical schema completeness independently | ADVANCED | **CLOSED** | The physical evidence extraction/comparison and divergence inventory are complete within the reported scope. Object differences and their dispositions remain open elsewhere. |
| 33 — Verify model/schema parity | NOT STARTED | **ADVANCED** | H3-A `flask db check` returned exit code 0 with no new operations after cleanup; this is limited to the H3-A schema and does not prove Prod/Test parity or resolve default/model-less-table differences. |
| 34 — Verify current-head behavior | ADVANCED | **CLOSED** | On 2026-10-23, a second ordinary `flask db upgrade` against `afcon360_chain_verify_test` at `h3a20261020` exited 0; normalized schema snapshots before/after were both 886,434 bytes with identical SHA-256 `8577c2a975d5846c3b99567a2c1d59d47b3686d893dbf23531adb9dcf40753d7`; diff exit 0, 0 bytes and 0 lines, first 10 lines blank. |

The resulting top-level totals after the Item 34 closure are **24 CLOSED, 9 ADVANCED, 1 PARTIAL, 0 OPEN, 0 GATED, and 5 NOT STARTED = 39**. The current ledger contains all IDs 1–39 exactly once; subordinate IDs do not affect the 39-item count. The separate earlier `be66d9e12e0a` `cycle_probe_note` upgrade transcript has no effective-database identity in the evidence provided and is tracked as subordinate 15a; it is not conflated with the later target-verified `c6c0034e7439` round trip.

### H3-A active chain and clean-install evidence

- The local active migration file is `migrations/versions/h3a20261020_static_baseline.py`. `flask db heads --verbose`, `flask db current`, and `flask db history --verbose` reported only `h3a20261020` as the active head/current revision.
- The ordinary application workflow uses `flask db upgrade`; the local H3-A baseline path reached `h3a20261020` on PostgreSQL 18.4. This is H3-A fresh-install evidence, distinct from the prior H2′ replay ending at `df55cbe3f516`.
- The baseline's docstring has not been corrected in this evidence capture. It still says that the file is isolated under `migrations/h3_candidate` and is not the active application chain, despite the actual active path and Alembic history. Track that documentation mismatch under subordinate 13c; do not edit the baseline SQL/hash as part of this status update.
- The `_SCHEMA_SQL` search-path reset is recorded as subordinate 13b. Retain the source-level review/test evidence; it does not authorize existing-database changes.

### Migration round-trip evidence — subordinate 34a

Target identity was checked immediately before the migration: `EFFECTIVE_DATABASE=afcon360_chain_verify_test`, host `localhost`, port `5432`; the target-check exit code was `0`. No credentials were printed.

1. `flask db migrate -m "verify H3 migration workflow"` generated `c6c0034e7439_verify_h3_migration_workflow.py` with `down_revision = 'h3a20261020'`.
2. The reviewed migration contained exactly one upgrade operation: add nullable `agent_onboarding_approvals.h3_workflow_probe` as `String(32)`. Its downgrade dropped only that same column.
3. `flask db upgrade` reported `Running upgrade h3a20261020 -> c6c0034e7439`; the recorded revision became `c6c0034e7439`, and the column query returned `('character varying', 32, 'YES')`. Diagnostic exit code was `0`.
4. `flask db downgrade h3a20261020` reported `Running downgrade c6c0034e7439 -> h3a20261020`. `flask db current` returned `h3a20261020`; a read-only catalog query confirmed `PROBE_COLUMN_EXISTS=False` on `afcon360_chain_verify_test`.
5. The temporary model field and generated migration were removed. Final `flask db check` reported `No new upgrade operations detected.` with `FLASK_DB_CHECK_EXIT=0`. `flask db heads --verbose`, `flask db current`, and `flask db history --verbose` each showed the single H3 baseline.

**Result:** the familiar Flask-Migrate path and a reversible one-column migration were proven on the disposable H3 workflow database. Together with the separately recorded second-upgrade-at-head snapshot PASS, Item 34 is now CLOSED. These results do **not** prove historical/intermediate-state upgrades (35), populated-state safety (26/36), full physical/model parity (32/33 for existing DBs), or an H3-B transition. Redis/`.env.local` startup warnings were observed during local CLI runs; this rehearsal is not a production Redis/Socket.IO configuration test.

### Physical-schema investigation outcome and method correction

The Phase 7 investigation is accepted as the durable comparison record. Reports B/C claimed byte-identical schemas while giving different hashes, contradicting that claim; Report A's measured results are used. Current identity-check rule: **empty redirected diff output alone does not prove identity**. A claimed identity must include diff-file size (zero bytes), exit code (`0`), and inspection of the first 10 lines confirming they are blank.

| Comparison | Diff lines | Diff bytes |
|---|---:|---:|
| Reference vs Prod | 2,273 | 93,910 |
| Reference vs Test | 711 | 35,664 |
| Prod vs Test | 2,311 | 93,240 |

The previously recorded SHA-256 hashes and schema metrics remain under Phase 7 and Item 14. The three databases share `df55cbe3f516` but are physically different. Closing Items 14 and 32 closes the comparison/evidence work only; it does not authorize forced convergence, type conversion, object deletion, stamping, rebuild or cutover.

### Subordinate follow-ups

- **12c [OPEN]** — The review reports a separate Socket.IO/CLI-disable change that still needs its own source-control closeout. Git status was not inspected or changed as part of this register update; this entry records the supplied review finding, not a new Git verification.
- **13a [RECORDED; LOCAL PASS]** — H3-A fresh-install path through ordinary Flask-Migrate reaches `h3a20261020` on local PostgreSQL 18.4. Fresh-clone replay and other supported versions remain outstanding under Item 31.
- **13b [RECORDED]** — `_SCHEMA_SQL` search-path reset is recorded as an H3-A correction; preserve the source review/runtime boundary.
- **13c [OPEN]** — Correct stale `migrations/versions/h3a20261020_static_baseline.py` docstring that still identifies the file as isolated/inactive. Do not modify its baseline SQL or provenance hash as part of this documentation correction.
- **15a [OPEN; TARGET ATTRIBUTION]** — An earlier transcript reported an upgrade from `h3a20261020` to `be66d9e12e0a` adding `system_configs.cycle_probe_note`, but the command's effective database was not captured. Later inspection of `afcon360_chain_verify_test` found baseline revision and no such column, which does not prove where the earlier command ran. Reconcile using existing configuration/log evidence before claiming its target/disposition; do not rerun migrations to investigate.
- **33a [RECORDED; H3-A PARITY CHECK PASS]** — The agent model alignment in `agent_float.py` / `agent_onboarding.py` is supported by the clean final H3-A `flask db check`. This does not resolve every index-design decision or establish existing-database parity.
- **33b [CLOSED FOR SELECTED MODEL DEFAULTS; LOCAL WORKTREE, NOT COMMITTED]** — Both `AgentOnboarding.is_deleted` and `AgentOnboardingApproval.is_deleted` declare `server_default="false"`; `AgentOnboarding.status` declares `server_default="submitted"`. The focused regression file passed 4/4 tests, `git diff --check` had only the LF/CRLF warning, and local `HEAD` remains `508c7838788db56b91604a7f25cfdce3a06104b3`. The working-tree changes are not committed. This closes only these three selected model defaults; the 145 Prod/Test differences under 28a and unrelated unresolved Item 33 gates remain open.
- **33c [CLOSED FOR H3-A TABLE INVENTORY]** — Actual runtime `db.metadata.tables` versus H3-A physical schema matched exactly (223 application tables each; zero differences either direction; zero registration failures). The older six-table/model claim was not reproduced on this H3-A target; no broad Prod/Test parity claim is implied.
- **33e [OPEN]** — Source-to-schema risk review for classes absent from H3-A metadata and physical schema: `server_sessions` is called in login/logout and the code swallows persistence/revocation errors; `analytics_page_views` is used by a flush routine that deletes Redis counters before database commit (actual scheduling unverified); `activity_logs` has a model/import test but no application caller located in this review. Confirm intended support, reachability and ownership, then obtain an explicit remediation/retirement decision before touching the model registry or baseline. No table creation/drop or app-code change is authorized by this finding.
- **34a [PASS; ITEM 34 CLOSED 2026-10-23]** — The probe migration upgrade/downgrade round trip and final clean parity check are recorded above. The separate second-upgrade-at-head test now also passes: `afcon360_chain_verify_test` remained at `h3a20261020`; before/after normalized schema snapshots each measured 886,434 bytes with SHA-256 `8577c2a975d5846c3b99567a2c1d59d47b3686d893dbf23531adb9dcf40753d7`; diff exit `0`, bytes `0`, lines `0`, first 10 lines blank. Item 34's stated acceptance criterion is satisfied.
- **14d remains open for dependency/disposition review** — `pgcrypto` was recorded only in Prod, with 37 extension-backed routines plus two deletion-guard functions. A clean tracked-source search found no direct call sites for the searched pgcrypto functions, but does not prove dynamic SQL, operational or all database-side dependencies absent. Preserve existing Prod state. For an in-place plan, verify extension preservation; for a rebuild, explicitly decide whether to recreate it. Do not add it to the common H3-A baseline or drop/align it by default.

### Remaining gates and prohibitions

1. Complete subordinate 12b Docker census from an approved Docker-enabled host; local `docker` command-not-found is not evidence of container state.
2. Finish FK-name/column/target/action/model mapping (25/27) and maintain separate physical-state decisions for Prod and Test. Items 14/32 compare the schemas; they do not qualify either for transition.
3. Complete populated-state safety/data-constraint validation (26/36), historical/intermediate-state tests (35), and failure recovery (38). Item 34's current-head idempotence criterion is CLOSED by the 2026-10-23 evidence above.
4. Disposition the 145 Prod/Test server-default differences (28a) and decide the three source-declared but unregistered table candidates (33e) before fresh-vs-upgraded convergence (37). The three selected agent-column model defaults have been dispositioned with local regression evidence under 33b; that work is not committed and does not resolve the broader default differences. H3-A runtime table-set parity itself has passed; this does not close top-level Item 33.
5. Extend automated and integration gates as required by Item 39; the existing guarded 90-test source selection is not the full suite or proof of database integration safety.

`afcon360_prod` and `afcon360_test` remain off-limits for writes. No H3-B authorization, rebuild, stamp, production/test upgrade, forced schema normalization, enum conversion, drop, rename, or relabel is granted by this register update. Preserve the protected backups and all disposable/scratch databases; no automatic cleanup is authorized.
