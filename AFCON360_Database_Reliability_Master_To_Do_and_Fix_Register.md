# AFCON360 — Database Reliability — Master To-Do & Fix Register

**Snapshot: 20 October 2026 · reconciled to the owner-supplied read-only preflight, the guarded 90-test run and the current review-branch evidence; statuses reflect acceptance evidence, not deployment readiness.**

**Status: 20 closed · 11 advanced · 1 partial · 0 open · 0 gated · 7 not started (39 top-level items)**

**Architecture: H2′ approved and implemented as the interim fresh-install repair · H3/N-squash selected as the durable destination, root not yet created**

**Permanent fixes implemented: 2 (H2′ interim fresh-install repair; Design 2 model-bootstrap path)**

**Clean-install verification completed: 2 (H2′ empty-database migration replay to `df55cbe3f516`; Design 2 live bootstrap PASS on `afcon360_d2_bootstrap_fix_20261018_test`)**

**Not verified: full test suite · fresh-clone replay · PostgreSQL 15 / Docker-pinned replay · historical/intermediate-state upgrades · full-schema parity**

---

## Overall status summary

| Status | Count |
|---|---:|
| CLOSED | 20 |
| ADVANCED | 11 |
| PARTIAL | 1 |
| OPEN | 0 |
| NOT STARTED | 7 |
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
| 13 | Define supported starting revisions | Approve and record the proposed support matrix: empty DB only after replay validation; `df55cbe3f516` only after per-database physical parity; older revisions only when individually enumerated and tested; unknown/divergent states fail closed. Verify the prior owner ruling first. | ADVANCED |
| 14 | Compare H2′ with existing database states | Create independent physical-schema/parity artifacts for prod and test and record each divergence; same Alembic revision must not be treated as proof of identical schema. | ADVANCED |
| 15 | Design the H3 transition procedure | Complete the state-by-state runbook for empty, root-stamped, intermediate, at-head and unknown states, with parity-gated stamping and tested recovery/rollback. | ADVANCED |
| 16 | Classify architecture-specific conflicts | Keep root-vs-child and child-vs-child conflicts distinct and tie classifications to source/graph evidence, not assumed runtime failures. | CLOSED |
| 17 | Compare H2′ and H3 architectures | Retain a reasoned comparison of fresh-install behavior, old/intermediate states, enum ownership, immutability and rollback implications. | CLOSED |
| 18 | Approve one architecture | Preserve the owner decision selecting H2′ as interim and H3 as durable target; confirm this is not permission to cut over. | CLOSED |
| 19 | Approve and execute isolated PostgreSQL verification plan | Replay the full H2′ migration chain in an approved empty disposable PostgreSQL database and verify the final head and resulting catalog counts. | CLOSED |
| 20 | Establish canonical schema-creation architecture | Verify Design 2 bootstrap creates its schema, completes and validates its marker/fingerprint, and does not falsely create `alembic_version`; keep it distinct from Alembic. | CLOSED |
| 21 | Repair enum creation ownership | Demonstrate one PostgreSQL type-creation owner per USED/REFERENCED enum with exact labels and explicit legacy/default dispositions; Python enum-object identity alone is insufficient. | ADVANCED |
| 22 | Eliminate repeated `window_mode_enum` creation | The H2′ clean-install replay must create `window_mode_enum` exactly once; test historical/intermediate paths separately after support policy is settled. | CLOSED |
| 23 | Resolve duplicate slug migrations | The H2′ clean-install replay must create each slug object once and preserve the required constraints; historical/intermediate behavior remains a separate test. | CLOSED |
| 24 | Resolve remaining confirmed and conditional conflicts | Reconcile the 324-row matrix against successful replay evidence and record explicit dispositions for conditional conflicts, orphan types and divergent `org_business_category` copies. | ADVANCED |
| 25 | Correct foreign-key assumptions | Compare physical FK names, columns, targets and `ON DELETE`/`ON UPDATE` actions with migration source and SQLAlchemy relationships. | NOT STARTED |
| 26 | Make data-sensitive migrations safe | Run populated-state tests for NOT NULL additions, backfills, unique indexes, CHECKs and FKs; prove existing data preservation and invalid-data rejection. | NOT STARTED |
| 27 | Resolve `df55cbe3f516` and coupled model changes | The revision must remain tracked and reachable; independently verify the coupled FKs/models and create separate physical-parity evidence for prod and test. | ADVANCED |
| 28 | Consolidate schema-creation procedures | Document the supported installation route and enforce the separation between bootstrap and migration paths; disposition the 145 default differences and six model-less tables before convergence. | ADVANCED |
| 29 | Establish permanent database engineering rules | Verify the rules and their mirror agree: ordinary migrations are regenerated from corrected source/configuration, hand-patching is prohibited except for the narrowly authorized baseline-reconstruction exception. | CLOSED |
| 30 | Create approved disposable PostgreSQL verification environment | Retain the authorized disposable replay/bootstrap databases and their evidence; verify that production/test databases were not used as scratch targets. | CLOSED |
| 31 | Pass clean-install migration test | Replay from an empty database to `df55cbe3f516` and verify the resulting schema; extend separately to a genuinely fresh clone and supported/pinned PostgreSQL versions. | CLOSED |
| 32 | Verify physical schema completeness independently | Export and compare tables, columns, ordered enum labels, defaults, indexes, constraints, FKs, sequences, triggers and functions against an independently approved expected schema. | ADVANCED |
| 33 | Verify model/schema parity | After intentional exceptions and defaults are dispositioned, compare SQLAlchemy metadata with the physical schema and run appropriate Alembic/model parity checks. | NOT STARTED |
| 34 | Verify current-head behavior | Run a second upgrade at head in a disposable database and prove a before/after physical-schema snapshot is unchanged. | ADVANCED |
| 35 | Test upgrades from supported historical states | For every owner-approved supported historical revision, upgrade a separate disposable database with representative data and validate the resulting schema and data. | NOT STARTED |
| 36 | Verify data and constraints | Prove row/value/relationship preservation, enum-label preservation and rejection of invalid data using populated disposable databases. | NOT STARTED |
| 37 | Compare fresh and upgraded results | After dispositioning all 145 default differences and six model-less tables, compare fresh-install and upgraded physical-schema snapshots and explain every exception. | NOT STARTED |
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
| **H3 / N-squash** | **Selected durable destination. Its root does not yet exist.** Not implemented, not authorized for cutover, and blocked by items 12b, 13 and per-database parity evidence. |
| **Existing production and test databases** | **Not upgraded and not modified in this work.** `afcon360_prod` and `afcon360_test` remain read-only evidence sources. |
| **Full-schema parity and historical-state support** | **Unresolved.** No historical or intermediate-state upgrade has been verified; no per-database physical parity artifact exists. |

---

## Working policies

- Retain native PostgreSQL enums.
- Migration history is immutable by default.
- Stamps require independent schema verification.
- The `create_type` option governs whether SQLAlchemy automatically emits PostgreSQL enum creation and drop DDL; `checkfirst` controls existence checking during applicable create/drop operations, including enum type operations. (Corrected per item 11c; the earlier checkfirst-only-tables claim is withdrawn.)
- `alembic_version` alone is insufficient as a schema fingerprint — an independently recorded parity artifact is required before any stamp or upgrade over an old-dynamic body.
- `db.create_all()` is never a substitute for the approved migration path on a non-test database, and must never be followed by a false Alembic head stamp.

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

**[ADVANCED] 13. Define supported starting revisions.**
The H3 transition procedure already defines the broad state categories: empty, root-stamped, intermediate, at-head and unknown. The local static Alembic parser confirms 27 revisions, one base (`8a0deccce6f6`) and one head (`df55cbe3f516`).
**Recovered prior planning evidence (2026-10-20):** `AFCON360_DB_Migration_Readiness_Tree_Updated_2026-10-20.md` proposes the following support matrix but explicitly leaves it awaiting the owner's approval; no approval of the exact matrix was found in the retrieved handover material:
- **Empty database:** support only after clean replay succeeds on each approved PostgreSQL environment/version.
- **Existing DB at `df55cbe3f516`:** support only after read-only physical parity is proven; treat prod and test as distinct states until parity proves otherwise.
- **Older/intermediate revision:** support only if each revision is explicitly listed and covered by a disposable upgrade test.
- **Unknown revision, conflicting Alembic state or unrecognized/divergent physical schema:** fail closed and require manual assessment; no automatic stamp or upgrade.
This is a recovered proposal, **not an owner-approved policy**. The static single-base/single-head graph does not itself define support for populated databases or exact historical revisions.
**Next action:** ask the owner to confirm or amend this specific matrix only after checking any other authoritative decision record. Then record the exact supported revision IDs and test coverage; that ruling gates final H3 transition rules and Item 35.

**[ADVANCED] 14. Compare H2′ with existing database states.**
Same-ID/different-schema hazard is field-proven: `afcon360_test` at `df55cbe3f516` carries `org_business_category` as a live-USED 39-label UPPER enum; `afcon360_prod` at the same revision carries the same column as `varchar(40) NULL`, with `org_business_category` existing as a 4-label lowercase orphan. Same revision ID, different physical schema, different repair operation required per database.
Corrections carried: prod holds 68 types (not 69); `organisations.slug` is NOT NULL in both databases.
**Evidence boundary (2026-10-20):** the supplied local preflight made no database connection and adds no new physical-catalog evidence. The previously recorded production/test differences remain prior evidence; they were not refreshed by this capture.
**Next action:** use existing durable evidence or approved read-only snapshots/clones to produce separate physical-parity artifacts for each supported existing state. Preserve differences instead of averaging or normalizing them; no H3 stamp/cutover is authorized.

**[ADVANCED] 15. Design the H3 transition procedure.**
Procedure defined: new root N-squash; old files retired in the same commit; merge revisions rejected; per-state commands (empty / root-stamped / intermediate / at-head / unknown); stamp only after parity; rollback via re-track + re-stamp. Under H3, `f91075478868` retires, dissolving its 4× `window_mode_enum` emit defect; under H2′ it remains and needs an in-place exception or a conditionalizing repair.
**Next action:** complete the state-specific transition rules once the docker census (12b), the supported-state decision (item 13), the per-database parity artifacts and item 16d/27 evidence exist.

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
H2′ is approved and **implemented** as the interim fresh-install repair: the four previously modified migration files were repaired and committed, and the empty-database replay passed. H3/N-squash is **selected** as the durable destination, with its root not yet created.
This item is closed as a *decision* item. It does **not** authorize an H3 authoring or cutover.
**Next action:** respect the H3 decision, but do not author or cut over H3 before items 12b, 13, 16d/27 and per-database parity artifacts pass.

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
Content (identical for both architectures): one `CREATE TYPE` per USED/REFERENCED type with exact live label sets; no `bookingstatus` creation by that name; conversion path (not drop) for test's live-USED 39-label `org_business_category`; preserve-or-migrate the 3 legacy column defaults.
Location: H2′ — frozen `8a0deccce6f6` body plus an exception or conditionalizing repair for `f91075478868`; H3 — N-squash body, where `f91075478868` retires.
**Scope clarification (2026-10-20 review branch):** the separate source change in `app/transport/models.py` removes duplicate Python enum class declarations that shadowed canonical objects imported from `app/utils/enums.py`; a database-free regression test asserts the public aliases retain canonical object identity. This is Python enum-registry ownership/identity only. It does **not** implement PostgreSQL `CREATE TYPE` ownership, resolve the H2′/H3 migration-location decision, or provide live enum/schema evidence. Item 21 therefore remains **ADVANCED**, not implemented/closed.

**Next action:** implement PostgreSQL type-creation ownership at the authorized migration location only after the relevant architectural/scope gates permit it, and resolve the remaining legacy enum/default dispositions (including the 16 dev-only orphans and prod's `org_business_category` orphan) as explicit rulings rather than silent drops.

**[CLOSED] 22. Eliminate repeated `window_mode_enum` creation.**
Content: a single `CREATE TYPE window_mode_enum AS ENUM ('CALENDAR', 'ROLLING')`. The H2′ chain was corrected and the empty-database replay created the type once; live databases already converge.
**Scope limitation, stated explicitly:** this closure covers the **current H2′ fresh-install chain only**. No historical or intermediate-state upgrade has been verified, so the repeated-creation behaviour under those paths is untested.
**Next action:** confirm the fix also behaves correctly in any supported historical/intermediate-state upgrade test once item 13 defines those states.

**[CLOSED] 23. Resolve duplicate slug migrations.**
Confirmed child-vs-child duplication: `71893e3a42a2` and `bd9d3bb673aa` create the same three objects. The H2′ chain was neutralized and the empty-database replay passed; `slug` is NOT NULL in both live databases, consistent with the second duplicate never having executed.
**Scope limitation, stated explicitly:** closure covers the **current H2′ fresh-install chain only**. Historical/intermediate-state upgrades remain unverified.
**Next action:** verify supported historical-state upgrades separately under items 13 and 35.

**[ADVANCED] 24. Resolve remaining confirmed and conditional conflicts.**
The 324-row mechanical matrix is delivered: 74 CONFIRMED (declaration duplication), 229 CONDITIONAL, 21 NOT A CONFLICT, 0 PREDICTED.

| Category | Count | Action |
|---|---:|---|
| USED enum names | 48 | Create in frozen DDL, exact labels |
| REFERENCED enums | 3 | Preserve defaults or migrate |
| ORPHAN enums (dev-only) | 16 | Drop-candidate pending ruling |
| `bookingstatus` | 1 | Retain unless downgrade abandoned |
| `org_business_category` | — | Test copy needs conversion; prod copy is a drop-candidate pending ruling |
| CONDITIONAL rows | 229 | Await reconciliation against replay evidence |

**Next action:** reclassify the 229 CONDITIONAL rows against the now-successful fresh replay — do not treat source predictions as observed failures — and obtain explicit rulings for the 16 orphans, `bookingstatus` and both `org_business_category` copies.

**[NOT STARTED] 25. Correct foreign-key assumptions.**
Explicit clarification: the earlier `[CLARIFIED]` entry in this register was a **wording clarification only** — it restated that `e6f319ffc8c8` is a name mismatch rather than a duplication and that `df55cbe3f516` FK names match the dirty working tree rather than committed HEAD. **No substantive verification work has been performed.** Nothing has been compared against the physical schema.
**Next action:** compare FK names, targets, `ON DELETE`/`ON UPDATE` actions, and SQLAlchemy model coupling against the physical schema for the H2′ root and the coupled files, and record the result as evidence rather than as wording.

**[NOT STARTED] 26. Make data-sensitive migrations safe.**
The source audit has already identified concrete populated-state hazards: `71893e3a42a2_add_organisation_slug.py` adds `organisations.slug` as NOT NULL without a default; `5e80dc4ac345_transport_reservation_obligation_and_.py` adds `transport_reservations.request_fingerprint` as NOT NULL without a default. Unique-index, CHECK-constraint and foreign-key changes also need representative-data review. These source findings identify risk; they do not prove failure or safety. No complete operation inventory, approved safe-migration design or populated-state test is recorded.
**Next action:** use these identified revisions in the complete operation inventory, then test applicable operations against representative populated data in approved disposable databases, including invalid-data rejection and preservation checks. Do not repeat the completed source discovery.

**[ADVANCED] 27. Resolve `df55cbe3f516` and coupled model changes.**
Advanced by evidence: the revision is now **tracked** (it ships with the H2′ repair commit) and is **reached by the current clean replay**; `flask db current` returns `df55cbe3f516 (head)` with exit code 0. Subordinate 16d's *tracking* prerequisite is therefore satisfied.
Not closed: independent FK/model coupling verification and per-database physical parity remain unverified. Satisfying 16d's tracking prerequisite alone does **not** close this item.
**Next action:** verify FK/model coupling and produce per-database physical-parity artifacts for `afcon360_prod` and `afcon360_test` before closing prerequisite 16d/27.

**[ADVANCED] 28. Consolidate schema-creation procedures.**
Design 2 is committed (`ff5fe53` + `96636f2`). The **percent-placeholder and schema-scope defects have been fixed** and the source-level suite now comprises **38 tests, all passing** in an isolated, database-free run (exit code 0). Live runtime verification on a disposable database has **passed** (item 20): `bootstrap_model_schema()` created 217 tables and 47 enums, marker `complete`, no `alembic_version`; read-only `validate_model_bootstrap()` also passes. The 145 server-default differences (subordinate 28a) remain unresolved.
Consequence: no fresh-vs-upgraded convergence test (item 37) can pass until those defaults are normalized or explicitly declared intentional exceptions. This is a precondition, not a footnote.
**Next action:** define the official installation route; ensure `lazy_table_creator` and the test setup scripts remain test-only; normalize or formally except the server-side defaults before any parity comparison.

**[ADVANCED] 28a. Classify and disposition the 145 server-default differences.**
The 145 default differences comprise 132 Prod-only, 12 Test-only and one Both-differ case. Each must be classified against evidence and assigned an intended disposition before the fresh-versus-upgraded convergence requirement under item 37 can pass.
Principles: a physical difference is not proof that prod or test is correct; do not normalize defaults simply to make the two environments match; preserve exact observed expressions in the evidence; distinguish observed differences from corroborated explanations and unresolved intended behavior; explicitly document any intentional exception or required schema-owner decision; keep the separate organisations.business_category type conversion visible in the convergence requirements. Cross-reference items 20, 29 and 37.
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

**[ADVANCED] 32. Verify physical schema completeness independently.**
Advanced by count-level evidence only: 224 public tables, 49 public enum types, 2 non-internal triggers and 2 public functions were observed. Not yet proven against an approved expected schema: columns, ordered enum labels, defaults, indexes, constraints, foreign keys, sequences, trigger definitions and function bodies.
**Next action:** produce a full physical-parity artifact (tables, columns, enum types and label order, defaults, indexes, constraints, FKs, sequences, triggers, functions) and compare it against an independently established expected schema.

**[NOT STARTED] 33. Verify model/schema parity.**
No model-versus-physical comparison has been run, and the 145 default-differences plus six model-less tables are unresolved inputs.
**Next action:** run the supported schema-comparison checks, including `flask db check` where appropriate, after accounting for every intentional exception and the unresolved defaults.

**[ADVANCED] 34. Verify current-head behavior.**
`flask db current` returned `df55cbe3f516 (head)` with exit code 0, confirming the replayed database sits at the current head. A second upgrade executed at head and a before/after physical-schema snapshot comparison have **not** been recorded.
**Next action:** run a second upgrade at current head in a disposable database and compare physical-schema snapshots before and after to prove idempotence.

**[NOT STARTED] 35. Test upgrades from supported historical states.**
No historical or intermediate-state upgrade has been verified. Items 22 and 23 are closed for the fresh-install chain only, which does not substitute for this work.
**Next action:** agree the supported states under item 13, then replay each in a separate disposable database with representative existing data.

**[NOT STARTED] 36. Verify data and constraints.**
No data-preservation, enum-label-preservation, relationship or invalid-data-rejection verification exists.
**Next action:** validate that existing values retain their meaning, enum labels and relationships survive, and invalid data is rejected, using disposable databases with representative data.

**[NOT STARTED] 37. Compare fresh and upgraded results.**
Blocked by two unresolved inputs: the 145 server-default differences (132 Prod-only, 12 Test-only, 1 Both-differ) and the six tables in the migration-built schema that lack current SQLAlchemy models and need an explicit disposition.
**Next action:** classify, disposition and normalize or formally except both inputs, then independently compare the fresh-install result against the upgraded result to prove convergence.

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
- **12b** — Local 2026-10-20 preflight: Docker CLI command not found; no container-state/census result. Run from an approved Docker-enabled host; blocks H3. [OPEN]
- **14a** — Stamp-timing distinction: a database stamped `8a0deccce6f6` before the enum regression has a different schema from one stamped after; same ID, no timestamp in `alembic_version`. [ADVANCED]
- **14b** — Divergent-schema dispositions: test needs a `org_business_category` conversion path (39-label UPPER → `varchar(40)`); prod needs a disposition ruling for its 4-label orphan; both need rulings for the 16 dev-only orphan candidates. [ADVANCED]
- **16a** — Root-vs-child and child-vs-child classes separated. [CLOSED]
- **16b** — 324-row mechanical conflict matrix delivered (74 / 229 / 21 / 0). [DELIVERED]
- **16c** — `df55cbe3f516` vs committed HEAD FK coupling proven via `git diff`. [CLOSED]
- **16d** — Atomic tracking of `df55cbe3f516` with coupled diffs: **tracking satisfied** by the H2′ repair commit; coupled FK/model verification remains with item 27. [PREREQ — partially satisfied]
- **17a** — Compatibility conditions (i)–(vi). [RECORDED]
- **17b** — Column parity: the 101/48 gap resolved as a phantom; 1 type-diff + 145 default-diffs documented; enum inventory reconciled (prod 47+1+3+16+1 = 68; test 48+1 = 49). [CLOSED]
- **22a** — bookingstatus root-era verification: 11 members at `449bdcd`; `NO_MATCH` added at `5322c63` in the same commit as the `SQLEnum` → `String(30)` flip. [CLOSED]
- **28a** — The 145 server-default differences (132 Prod-only, 12 Test-only, 1 Both-differ) require classification and disposition before item 37 can pass. A physical difference is not proof that either environment is correct; do not normalize merely to force a match. [OPEN]

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

- **Supported starting revisions** (item 13, ADVANCED) — a concrete four-case proposal has been recovered, but the source explicitly leaves it pending owner approval. Confirm/amend that proposal, then enumerate any exact historical revision IDs; this gates items 15 and 35.
- **Docker census** (subordinate 12b) — the local preflight could not find the Docker CLI, so container state is unknown; H3 remains blocked until the census completes on an approved Docker-enabled host.
- **FK/model coupling and per-database parity** (item 27) — required before any stamp (H3) or upgrade over an old-dynamic body (H2′).
- **28a default dispositions** and the **six model-less tables** — item 37 convergence cannot pass until both are dispositioned.
- **Historical/intermediate-state support** — no such upgrade has been verified; items 22 and 23 do not cover it.

Resolved: scratch-replay authorization (item 19), `df55cbe3f516` tracking (subordinate 16d), and the Design 2 bootstrap defect. Items 20 and 29 are owner-confirmed CLOSED in this 2026-10-20 status reconciliation; neither closure authorizes H3 cutover.

---

## Status summary by phase

| Phase | Items | Status mix |
|---|---|---|
| Phase 1 — Findings established | 1–8 | 8 closed |
| Phase 2 — Evidence for the architecture decision | 9–17 | 4 closed (9, 11, 16, 17) · 4 advanced (12–15) · 1 partial (10) · 0 open |
| Phase 3 — Decisions and authorization | 18–19 | 2 closed |
| Phase 4 — Implement the approved permanent repair | 20–29 | 4 closed (20, 22, 23, 29) · 4 advanced (21, 24, 27, 28) · 2 not started (25, 26) |
| Phase 5 — Prove the result and prevent recurrence | 30–39 | 2 closed (30, 31) · 3 advanced (32, 34, 39) · 5 not started (33, 35, 36, 37, 38) |

Parent totals: **20 closed + 11 advanced + 1 partial + 0 open + 0 gated + 7 not started = 39.** Subordinates (10a/10b, 11a–c, 12a/12b, 14a/14b, 16a–d, 17a/17b, 22a, 28a) are counted separately and never added to the 39.

---

## Definition of complete

The approved installation path passes a clean PostgreSQL replay **on every supported server version and from a genuinely fresh clone**; supported upgrades preserve data; the resulting schemas independently match an approved expected schema; model/physical parity and per-database parity are evidenced; the server-default and model-less-table dispositions are closed; and automated checks guard against recurrence. A successful fresh-install replay on one server version is necessary but not sufficient.

---

## Safety

All existing dirty and untracked work in the checkout is preserved. `afcon360_prod` and `afcon360_test` remain off-limits for write operations and were not upgraded or modified. Disposable verification databases (`afcon360_h2p_replay_20261018_test`, `afcon360_d2_bootstrap_fix_20261018_test`, `afcon360_b0_design2_rt_20261018`) and all pre-existing scratch databases are retained and must not be automatically cleaned up. `df55cbe3f516` and its coupled working-tree changes are preserved. No migration was run, no database was created, dropped or reset, and no test suite was executed as part of this documentation update. The original DOCX is retained as reference at `C:\Users\OBED\Desktop\AFCON360_Database_Reliability_Master_To_Do_and_Fix_Register.docx`; this Markdown file is the working register.

---

## Next action

The next actions, ordered by dependency:

1. **Confirm or amend the recovered Item 13 support-matrix proposal** after checking the authoritative owner decision record; then record exact historical revision IDs and their test coverage if any are to be supported.
2. **Complete the Docker census** (subordinate 12b) from an approved Docker-enabled host. The local preflight could not invoke the Docker CLI; it did not observe container state.
3. **Verify FK/model coupling and obtain per-database physical-parity artifacts** (items 14, 25, 27 and 32). These are prerequisites to any H3 stamp or existing-database transition.
4. **Complete populated-state migration-safety tests** (item 26) for the already-identified non-null additions and other data-sensitive operations once the supported-state policy is set; continue default/model-less-table disposition under items 28a/37.

The static graph and local whitespace check have already passed and should not be repeated absent relevant source changes. The outstanding actions now require an owner decision, Docker-capable environment, physical-schema evidence or populated-state tests.

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

The top-level register has been restored to an actionable four-column format: **Item, Description, Expected test / acceptance evidence, Status**. Every one of the 39 top-level items is represented once. The status tally is reconciled to **20 CLOSED, 11 ADVANCED, 1 PARTIAL, 0 OPEN and 7 NOT STARTED**; subordinate entries remain outside the 39-item count.

Item 13 is **ADVANCED, not CLOSED**. The updated 2026-10-20 readiness tree supplies a concrete proposed support matrix, but explicitly says owner approval remains outstanding. The proposal is recorded under Item 13; confirm/amend it before treating the policy as decided or running historical-state tests.

Item 39's main entry now reflects the newer guarded 90-test run and the synchronized register-only commit. The guarded run supports focused regression confidence only; it does not replace full-suite, live PostgreSQL, fresh-clone, pinned-server, physical-schema-parity or historical-upgrade evidence. No migration, database write, H3 root creation or cutover authorization is implied by this register update.


### Item 13 recovery outcome

The earlier readiness-tree artifact was recovered and read. It contains a proposed state-support policy—not evidence of owner approval. The policy is now reproduced in Item 13 with each case and its acceptance condition. No approval is inferred, and no migration or database action followed from this review.
