# AFCON360 — Database Reliability — Master To-Do & Fix Register

<<<<<<< HEAD
**Status (2026-10-18): 18 closed · 12 advanced · 1 partial · 1 open · 0 gated · 7 not started**
**Architecture: H3/N-squash selected as the durable target; H2′ fresh-install correction committed and pushed as an interim repair to the existing chain**
**Implementation now committed: H2′ fresh-install correction and Design 2 no-false-stamp test contract; H3 remains unimplemented**
**Clean-install verification: one empty-database replay passed on local PostgreSQL 18.4; fresh-clone, PostgreSQL 15, full-suite, and full physical-parity gates remain open**
=======
**Snapshot: 18 October 2026 · Statuses reflect current evidence, not deployment readiness.**
**Status: 18 closed · 12 advanced · 1 partial · 1 open · 0 gated · 7 not started (39 top-level items)**
**Architecture: H2′ approved and implemented as the interim fresh-install repair · H3/N-squash selected as the durable destination, root not yet created**
**Permanent fixes implemented: 1 (H2′ interim fresh-install repair, committed)**
**Clean-install verification completed: 1 (local PostgreSQL 18.4, empty-database replay to `df55cbe3f516`)**
**Not verified: full test suite · fresh-clone replay · PostgreSQL 15 / Docker-pinned replay · historical/intermediate-state upgrades · full-schema parity**

---

## Overall status summary

| Status | Count |
|---|---:|
| CLOSED | 18 |
| ADVANCED | 12 |
| PARTIAL | 1 |
| OPEN | 1 |
| NOT STARTED | 7 |
| GATED | 0 |
| **Total** | **39** |

### Top-level status table (IDs 1–39, each exactly once)

| ID | Status | Title |
|---:|---|---|
| 1 | CLOSED | First observed installation failure: missing `transactiontype` |
| 2 | CLOSED | Enum ownership investigation |
| 3 | CLOSED | Map Alembic history and 27-revision chain |
| 4 | CLOSED | Identify root-baseline design problem |
| 5 | CLOSED | Identify repeated migration operations |
| 6 | CLOSED | Investigate competing schema-creation paths |
| 7 | CLOSED | Recover historical evidence |
| 8 | CLOSED | Agree the engineering destination |
| 9 | CLOSED | Reconstruct original baseline history |
| 10 | PARTIAL | Verify the historical "182 tables from EMPTY" claim |
| 11 | CLOSED | Trace enum declaration changes |
| 12 | ADVANCED | Establish deployed migration states |
| 13 | OPEN | Define supported starting revisions |
| 14 | ADVANCED | Compare H2′ with existing databases |
| 15 | ADVANCED | Design H3 transition procedure |
| 16 | CLOSED | Classify architecture-specific conflicts |
| 17 | CLOSED | Compare H2′ and H3 architectures |
| 18 | CLOSED | Approve one architecture |
| 19 | CLOSED | Approve and execute isolated PostgreSQL verification plan |
| 20 | ADVANCED | Establish canonical schema-creation architecture |
| 21 | ADVANCED | Repair enum creation ownership |
| 22 | CLOSED | Eliminate repeated `window_mode_enum` creation |
| 23 | CLOSED | Resolve duplicate slug migrations |
| 24 | ADVANCED | Resolve remaining confirmed and conditional conflicts |
| 25 | NOT STARTED | Correct foreign-key assumptions |
| 26 | NOT STARTED | Make data-sensitive migrations safe |
| 27 | ADVANCED | Resolve `df55cbe3f516` and coupled model changes |
| 28 | ADVANCED | Consolidate schema-creation procedures |
| 29 | ADVANCED | Establish permanent database engineering rules |
| 30 | CLOSED | Create approved disposable PostgreSQL verification environment |
| 31 | CLOSED | Pass clean-install migration test (scoped to the tested server) |
| 32 | ADVANCED | Verify physical schema completeness independently |
| 33 | NOT STARTED | Verify model/schema parity |
| 34 | ADVANCED | Verify current-head behavior |
| 35 | NOT STARTED | Test upgrades from supported historical states |
| 36 | NOT STARTED | Verify data and constraints |
| 37 | NOT STARTED | Compare fresh and upgraded schemas |
| 38 | NOT STARTED | Verify failure recovery |
| 39 | ADVANCED | Establish automated regression gates and close the work |

**Subordinate entries are NOT part of the 39-item total:** 10a, 10b, 11a, 11b, 11c, 12a, 12b, 14a, 14b, 16a, 16b, 16c, 16d, 17a, 17b, 22a, 28a. They carry their own evidence and their own open/advanced state and are listed under *Subordinate findings*.

---
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

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
<<<<<<< HEAD
- **C3** — CONFIRMED in the 324-row matrix denotes declaration duplication (source-proven), not observed failure. The original observed empty-replay failure was missing `transactiontype`; the revised H2′ chain passed a fresh replay on 2026-10-18. Source-predicted conflicts must not be described as runtime failures.
- **C4 (corrected 2026-10-18)** — `df55cbe3f516` is tracked on GitHub `main`, and the current clean replay reaches it. The earlier claim that this revision is untracked and prevents clean-checkout graph resolution is superseded. Independent physical FK/model parity and coupling checks remain open (items 16d and 32).
=======
- **C3** — CONFIRMED in the 324-row matrix denotes declaration duplication (source-proven), not observed failure. Only one empty-replay failure is on record: the original missing `transactiontype`.
- **C4 [HISTORICAL — resolved 2026-10-18]** — the earlier finding that `df55cbe3f516` was untracked (breaking clean-checkout graph resolution) is superseded. The revision is now tracked in the H2′ repair commit, and the current clean replay reaches it. Retained only as pre-replay evidence.
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

---

## Architecture position (the four tracks must not be conflated)

| Track | State at this snapshot |
|---|---|
| **H2′ interim fresh-install repair** | **Implemented and committed.** Four previously modified migration files repaired; a full empty-database replay passed on local **PostgreSQL 18.4**, reaching `public.alembic_version = df55cbe3f516`. This is an *interim* repair, not the durable destination. |
| **Design 2 model-bootstrap path** | **Locally changed (uncommitted), with source-level tests passing (38 passed + 3 Flask-Session deprecation warnings) and live PostgreSQL runtime verification now executed — result PASS.** The first invocation on `afcon360_d2_bootstrap_fix_20261018_test` created 217 tables, 47 enums, marker `complete`, no `alembic_version`. A prior run on `afcon360_b0_design2_rt_20261018` failed due to the `%` placeholder defect; that database is preserved as historical evidence. The initial verification script incorrectly reported FAIL because it expected `result.state_code == "model_bootstrap_complete"` on the first run, whereas the implementation returns `STATE_EMPTY` and records completion in the marker. A subsequent read-only `validate_model_bootstrap()` call returns `model_bootstrap_complete`. Not interchangeable with the migration path. |
| **H3 / N-squash** | **Selected durable destination. Its root does not yet exist.** Not implemented, not authorized for cutover, and blocked by items 12b, 13 and per-database parity evidence. |
| **Existing production and test databases** | **Not upgraded and not modified in this work.** `afcon360_prod` and `afcon360_test` remain read-only evidence sources. |
| **Full-schema parity and historical-state support** | **Unresolved.** No historical or intermediate-state upgrade has been verified; no per-database physical parity artifact exists. |

---

<<<<<<< HEAD
[PARTIAL] 10. Verify the "182 tables from EMPTY" claim.
Evidence: The claim first appears at 449bdcd — the same commit that authored the baseline. No committed flask db upgrade transcript exists. The one quantified log at that commit records the test bootstrap path (create_all + stamp head against afcon360_test).
Verdict: Claim made, unsubstantiated by committed evidence. Mechanism was correct at 449bdcd; became incorrect at 174b625. The narrower reconstruction of the historical claim is complete.
Reconciliation note: a prior snapshot marked this item CLOSED. It is PARTIAL, not CLOSED: the historical investigation (subordinate 10a) is complete, but the empirical clean-install reproduction (subordinate 10b) is a separate deliverable gated on item 19. Do not count item 10 as CLOSED.
[RECORDED] 10a. Historical investigation complete (claim provenance, same-commit introduction, test-bootstrap log identification).
[RECORDED] 10b. The current H2′ chain replayed successfully from an empty disposable PostgreSQL 18.4 database on 2026-10-18, reaching `df55cbe3f516` after the full migration chain. This confirms the current replay path, not the historical exact “182 tables” claim at `449bdcd`; item 10 remains PARTIAL.
=======
## Working policies
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

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
**Next action:** record the corrected `create_type`/`checkfirst` contract in permanent engineering rules under item 29.

**[ADVANCED] 12. Establish deployed migration states.**
Local census complete:

| Env | `alembic_version` | Tables | Enum types | State |
|---|---|---:|---:|---|
| `afcon360_prod` (local) | `df55cbe3f516` | 224 | 68 | Physically divergent from test |
| `afcon360_test` | `df55cbe3f516` | 224 | 49 | Stale physical schema |
| docker | unreachable | — | — | Containers down |

<<<<<<< HEAD
Both local DBs are stamped at untracked df55cbe3f516. Clean checkouts cannot resolve that ID.
Deployment evidence (repo-only): zero tags — no release boundary. Only in-repo migration executor: docker-entrypoint.sh:47 flask db upgrade (web role only). Doctrine split between docs/POSTGRES_TESTING_CONTRACT.md (migrate-then-test) and constitution :691,705 + tests/conftest.py:254-262 (conditional create_all + stamp).
Closure still requires the Docker census (item 12b) and remaining deployment-state evidence. **Update 2026-10-18:** a separate disposable database passed the current H2′ empty-database replay. `afcon360_prod` and `afcon360_test` were not upgraded or modified.
[NEW] 12a. Deployment evidence ledger.
Recorded. Canonical for future contributors.
[OPEN] 12b. Docker census.
Re-execute Q1–Q4 probe against the container's Postgres when available. Blocks H3.
=======
Deployment evidence (repo-only): zero tags — no release boundary. Only in-repo migration executor: `docker-entrypoint.sh:47` `flask db upgrade` (web role only).
**Next action:** bring the container up and re-execute the Q1–Q4 census probe against the container's PostgreSQL (subordinate 12b); retain read-only state evidence per environment.
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

**[OPEN] 13. Define supported starting revisions.**
A human product decision. It cannot be advanced from source evidence.
**Next action:** obtain the owner's ruling on which starting revisions and database states must be supported for upgrade; this gates items 15 and 35.

**[ADVANCED] 14. Compare H2′ with existing database states.**
Same-ID/different-schema hazard is field-proven: `afcon360_test` at `df55cbe3f516` carries `org_business_category` as a live-USED 39-label UPPER enum; `afcon360_prod` at the same revision carries the same column as `varchar(40) NULL`, with `org_business_category` existing as a 4-label lowercase orphan. Same revision ID, different physical schema, different repair operation required per database.
Corrections carried: prod holds 68 types (not 69); `organisations.slug` is NOT NULL in both databases.
**Next action:** produce separate physical-parity artifacts for production and for test; preserve their differences rather than averaging them; obtain the history-rewrite exception ruling needed for H2′.

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

<<<<<<< HEAD
[CLOSED] 18. Approve one architecture.
Owner direction (2026-10-17): H3/N-squash is the durable target. H2′ is an interim repair to the existing 27-revision chain, not the H3 replacement. This closes the architecture-choice decision only; H3 authoring/cutover remains blocked by items 12b, 13, 16d, per-database parity, and outstanding dispositions.
[CLOSED] 19. Approve and execute the isolated PostgreSQL verification plan.
The owner authorized the disposable replay. On 2026-10-18, `afcon360_h2p_replay_20261018_test` was created empty and the committed H2′ chain reached `df55cbe3f516`. This provides current fresh-install evidence; it does not close all 229 conditional matrix rows or historical-state upgrade testing.
=======
**[CLOSED] 18. Approve one architecture.**
H2′ is approved and **implemented** as the interim fresh-install repair: the four previously modified migration files were repaired and committed, and the empty-database replay passed. H3/N-squash is **selected** as the durable destination, with its root not yet created.
This item is closed as a *decision* item. It does **not** authorize an H3 authoring or cutover.
**Next action:** respect the H3 decision, but do not author or cut over H3 before items 12b, 13, 16d/27 and per-database parity artifacts pass.
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

**[CLOSED] 19. Approve and execute isolated PostgreSQL verification plan.**
The plan was approved and **executed** on local PostgreSQL 18.4 against the disposable database `afcon360_h2p_replay_20261018_test`. The full empty-database replay passed, reaching `df55cbe3f516` (`flask db current` → `df55cbe3f516 (head)`, exit code 0).
Scope of this closure: the **migration** replay. The Design 2 model-bootstrap runtime verification is a separate deliverable — authorized, and now executed with a FAIL result (item 20 and the 2026-10-18 reconciliation).
**Next action:** preserve the replay database as evidence and do not reuse, reset or drop it; the Design 2 bootstrap defect has been resolved and the live verification passed (see items 20, 28, 39).

---

<<<<<<< HEAD
[ADVANCED] 20. Establish canonical schema-creation architecture.
Current fresh-install route: Alembic/H2′ chain, now replay-tested and published. Design 2 is a distinct model-bootstrap path, never represented as Alembic `head`. Durable target: H3/N-squash, selected but not authored. Existing-database cutover and H3 readiness remain gated by per-DB parity and supported starting-state decisions.
[ADVANCED] 21. Repair enum creation ownership.
The H2′ root now contains frozen explicit DDL and creates enum types before dependent tables; the full current chain passed the empty-database replay with 49 public enum types. This fixes the observed `transactiontype` fresh-install failure for the tested PostgreSQL 18.4 path. It does not settle existing-database legacy enum dispositions, all referenced/orphan type decisions, org_business_category conversion, or prod/test parity. H3/N-squash remains the durable target and has not been authored.
[CLOSED] 22. Eliminate repeated window_mode_enum creation on the current H2′ fresh-install path.
`f91075478868` now creates `window_mode_enum` once and declares dependent columns with `create_type=False`. The current full empty-database replay passed through this revision to head. This closes the observed fresh-chain duplicate-emission defect; historical intermediate-state upgrades and broader schema parity remain separate gates.
[CLOSED] 23. Resolve duplicate slug creation in the current H2′ chain.
`bd9d3bb673aa` has been neutralized as the duplicate of `71893e3a42a2`, which owns `organisations.slug`, `ix_org_slug_unique`, and `uq_org_slug`. The fresh empty-database chain passed. Upgrades from supported historical/intermediate states are not thereby certified; see item 35.
[ADVANCED] 24. Resolve remaining confirmed and conditional conflicts.
Deliverable complete: 324-row matrix.
Disposition space:
=======
# Phase 4 — Implement the approved permanent repair (items 20–29)

**[ADVANCED] 20. Establish canonical schema-creation architecture.**
Design 2 (`app/core/model_bootstrap.py`) is committed with a marker row, loud registration and no false Alembic stamp. The **percent-placeholder defect has been fixed locally** (2026-10-18) by:

1. `_ensure_group_a_types()` now calls `connection.exec_driver_sql(sql, execution_options={"no_parameters": True})` so psycopg2 no longer rejects the `%` placeholders in `RAISE EXCEPTION`.
2. `read_persisted_enum_labels()` now filters on `sa.func.current_schema()` instead of hard-coded `"public"`, aligning with the schema-scoped `build_enum_type_block()`.

The source-level contract suite has been expanded to **38 tests** (5 new regression tests covering the `%` placeholders, the `no_parameters` execution option, schema-scope consistency, and a real import-failure path) and **all 38 pass in an isolated run that blocks any SQLAlchemy engine connection** (`pytest --noconftest`, exit code 0).

**Live PostgreSQL runtime verification** was executed on 2026-10-18 against a fresh disposable database `afcon360_d2_bootstrap_fix_20261018_test`. The first invocation of `bootstrap_model_schema()` created 217 tables, 47 enum types, left the marker row status `complete` with a matching fingerprint, and did **not** create an `alembic_version` table. The initial verification script incorrectly reported FAIL because it expected `result.state_code == "model_bootstrap_complete"` on the first run; the implementation returns `STATE_EMPTY` on a fresh creation and records completion in the marker. A subsequent read-only call to `validate_model_bootstrap()` returns `model_bootstrap_complete` (PASS). The earlier failed database `afcon360_b0_design2_rt_20261018` (pre-fix) is retained as historical evidence of the `%`-placeholder defect.
**Next action:** define the supported division of responsibility between the migration path and the bootstrap path; the live bootstrap gate is satisfied.

**[ADVANCED] 21. Repair enum creation ownership.**
Content (identical for both architectures): one `CREATE TYPE` per USED/REFERENCED type with exact live label sets; no `bookingstatus` creation by that name; conversion path (not drop) for test's live-USED 39-label `org_business_category`; preserve-or-migrate the 3 legacy column defaults.
Location: H2′ — frozen `8a0deccce6f6` body plus an exception or conditionalizing repair for `f91075478868`; H3 — N-squash body, where `f91075478868` retires.
**Next action:** implement ownership at the chosen location once authorized, and resolve the remaining legacy enum/default dispositions (including the 16 dev-only orphans and prod's `org_business_category` orphan) as explicit rulings rather than silent drops.

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
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

| Category | Count | Action |
|---|---:|---|
| USED enum names | 48 | Create in frozen DDL, exact labels |
| REFERENCED enums | 3 | Preserve defaults or migrate |
| ORPHAN enums (dev-only) | 16 | Drop-candidate pending ruling |
<<<<<<< HEAD
| bookingstatus | 1 | Retain unless downgrade abandoned |
| org_business_category (prod orphan copy) | — | Covered by the USED-name count above; prod copy is a drop-candidate pending ruling, test copy needs conversion |
| 229 CONDITIONAL rows | 229 | The current empty-database replay passed after H2′ edits; reconcile individual matrix rows against that evidence. Supported historical-state coverage and existing-database parity remain open. |

[CLARIFIED] 25. Correct foreign-key assumptions.
`e6f319ffc8c8` is a name mismatch, not duplication. The current chain reaches tracked revision `df55cbe3f516`; the replay counts do not independently prove all FK names, targets, or delete/update actions match current model intent. Keep those checks under items 16d and 32.
[NOT STARTED] 26. Make data-sensitive migrations safe.
request_fingerprint NOT NULL-without-default confirmed as data-dependent.
[ADVANCED] 27. Resolve `df55cbe3f516` and coupled model changes.
The migration revision is tracked on `main`, and the current empty-database chain reaches it. This supersedes the register's earlier “untracked revision” claim. Independent verification of coupled FK/model assumptions, the two existing databases' physical schemas, and state-specific compatibility remains outstanding; item 16d is not closed.
[ADVANCED] 28. Consolidate schema-creation procedures.
The committed Design 2 changes remove unconditional Alembic-head stamping from the model-bootstrap setup, add a separate marker/state, and amend the PostgreSQL testing contract. The current supported fresh-install route is the Alembic migration chain; model-bootstrap output must never be represented as migration-equivalent or Alembic `head`. Runtime verification of `bootstrap_model_schema()`, full pytest, and fresh-clone reproduction remain open.
The 145 default-diffs (132 Prod-only, 12 Test-only, 1 Both-differ) remain an independent convergence blocker. Do not normalize them without per-column intent and disposition.
[ADVANCED] 28a. Classify and disposition the 145 server-default differences.
The 145 default differences comprise 132 Prod-only, 12 Test-only and one Both-differ case. Each must be classified against evidence and assigned an intended disposition before the fresh-versus-upgraded convergence requirement under item 37 can pass.
Principles: a physical difference is not proof that prod or test is correct; do not normalize defaults simply to make the two environments match; preserve exact observed expressions in the evidence; distinguish observed differences from corroborated explanations and unresolved intended behavior; explicitly document any intentional exception or required schema-owner decision; keep the separate organisations.business_category type conversion visible in the convergence requirements. Cross-reference items 20, 29 and 37.
The item 28a investigation may record the observed comparison as complete, but the disposition work remains outstanding.
[ADVANCED] 29. Establish permanent database engineering rules.
`docs/POSTGRES_TESTING_CONTRACT.md` now documents the separate model-bootstrap path and prohibits false Alembic-head claims. Still outstanding: complete permanent rules in the relevant engineering constitution/agent instructions, the full enum ownership/autogenerate contract, parity-artifact requirements, state-divergence case study, and disposition handling for the 145 defaults.
=======
| `bookingstatus` | 1 | Retain unless downgrade abandoned |
| `org_business_category` | — | Test copy needs conversion; prod copy is a drop-candidate pending ruling |
| CONDITIONAL rows | 229 | Await reconciliation against replay evidence |

**Next action:** reclassify the 229 CONDITIONAL rows against the now-successful fresh replay — do not treat source predictions as observed failures — and obtain explicit rulings for the 16 orphans, `bookingstatus` and both `org_business_category` copies.
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

**[NOT STARTED] 25. Correct foreign-key assumptions.**
Explicit clarification: the earlier `[CLARIFIED]` entry in this register was a **wording clarification only** — it restated that `e6f319ffc8c8` is a name mismatch rather than a duplication and that `df55cbe3f516` FK names match the dirty working tree rather than committed HEAD. **No substantive verification work has been performed.** Nothing has been compared against the physical schema.
**Next action:** compare FK names, targets, `ON DELETE`/`ON UPDATE` actions, and SQLAlchemy model coupling against the physical schema for the H2′ root and the coupled files, and record the result as evidence rather than as wording.

<<<<<<< HEAD
[CLOSED] 30. Create the approved disposable PostgreSQL test environment.
On 2026-10-18, `afcon360_h2p_replay_20261018_test` was created using `template0`/UTF-8 after confirming the name was available and the database was empty. Protected production/test databases were not upgraded or modified.
[CLOSED] 31. Pass the clean-install test — current H2′ path on PostgreSQL 18.4.
`flask db upgrade head` ran from the empty disposable database through the full current migration chain to `df55cbe3f516`, with no error shown in the captured log. Follow-up PostgreSQL queries confirmed 224 public tables, 49 public enum types, 2 non-internal triggers, 2 public functions, and `public.alembic_version = df55cbe3f516`; `flask db current` exited 0 and reported `(head)`. This is local PG 18.4 evidence, not a fresh-clone or PostgreSQL 15 result.
[ADVANCED] 32. Verify physical schema completeness independently.
The replay database's top-level physical counts and Alembic revision were verified. This is not a full completeness/parity audit: columns, ordered enum labels, defaults, indexes, constraints, FK semantics, sequences, and all model-less tables have not yet been reconciled against an independently approved expected schema.
[NOT STARTED] 33. Verify model/schema parity. Run the supported schema-comparison checks, including flask db check where appropriate, and account for every intentional exception.
[ADVANCED] 34. Verify current-head behavior.
`flask db current` on the replay database returned `df55cbe3f516 (head)` with exit code 0. A second `flask db upgrade head` at the already-current head plus before/after schema comparison has not yet been recorded.
[NOT STARTED] 35. Test upgrades from supported historical states. Use disposable databases or fixtures representing the agreed supported revisions, with representative existing data.
[NOT STARTED] 36. Verify data and constraints. Check that existing values retain their meaning, invalid data is rejected, and native enums and relationships behave correctly.
[NOT STARTED] 37. Compare fresh and upgraded results. Independently compare the resulting schemas to prove both paths converge on the same intended structure.
[NOT STARTED] 38. Verify failure recovery. Document and test the approved recovery procedure, including what happens if a migration fails partway through. Do not assume every downgrade can safely undo every change.
[ADVANCED] 39. Establish automated regression gates and close the work.
Design 2 source-level contract tests are committed; `python -m pytest -q tests/test_model_bootstrap_contract.py` produced `33 passed, 3 warnings` (Flask-Session filesystem-backend deprecations). This is not the full test suite and does not execute bootstrap behavior end-to-end on PostgreSQL. The authorized Design 2 runtime verification and full-suite/fresh-clone checks remain open.
Preconditions added by Phase 2: item 37 (fresh-vs-upgraded convergence) requires normalization of the 145 default-diffs first (see item 28 subordinate). All other items unchanged. Gates A–F remain the acceptance framework.
=======
**[NOT STARTED] 26. Make data-sensitive migrations safe.**
`request_fingerprint` NOT NULL without a default is confirmed as data-dependent. No safe-migration design or test exists.
**Next action:** enumerate every data-dependent operation in the chain, then test each with representative existing data in a disposable database, including the invalid-data rejection paths.
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

**[ADVANCED] 27. Resolve `df55cbe3f516` and coupled model changes.**
Advanced by evidence: the revision is now **tracked** (it ships with the H2′ repair commit) and is **reached by the current clean replay**; `flask db current` returns `df55cbe3f516 (head)` with exit code 0. Subordinate 16d's *tracking* prerequisite is therefore satisfied.
Not closed: independent FK/model coupling verification and per-database physical parity remain unverified. Satisfying 16d's tracking prerequisite alone does **not** close this item.
**Next action:** verify FK/model coupling and produce per-database physical-parity artifacts for `afcon360_prod` and `afcon360_test` before closing prerequisite 16d/27.

<<<<<<< HEAD
- 10a — Historical investigation of the "182 tables" claim complete.
- 10b — current H2′ fresh replay recorded as PASS on PostgreSQL 18.4 (2026-10-18); historical exact 182-table claim remains unverified.
- 11a — ensure_all_enums() never-existed finding.
- 11b — README write/delete commits.
- 11c — Native-enum creation contract (corrected wording above).
- 12a — Deployment evidence ledger (recorded).
- 12b — Docker census pending.
- 14a — Same-ID/different-schema hazard field-proven.
- 14b — Per-DB repair operations required; 1 type-diff + 145 default-diffs.
- 16d — [PREREQ] the revision file is tracked on `main` and reached by the current clean replay; independent FK/model coupling and physical-schema evidence remain required before this H3 prerequisite closes.
- 17a — Compatibility conditions (i)–(vi).
- 17b — Column parity: 101/48 phantom resolved; 145 default-diffs documented.
- 22a — bookingstatus root-era verification complete.
- 28a — 145 default-diff normalization (new precondition under item 28).
=======
**[ADVANCED] 28. Consolidate schema-creation procedures.**
Design 2 is committed. The **percent-placeholder and schema-scope defects have been fixed locally** (2026-10-18) and the source-level suite now comprises **38 tests, all passing** in an isolated, database-free run (exit code 0). Live runtime verification on a disposable database has **passed** (item 20): `bootstrap_model_schema()` created 217 tables and 47 enums, marker `complete`, no `alembic_version`; read-only `validate_model_bootstrap()` also passes. The 145 server-default differences (subordinate 28a) remain unresolved.
Consequence: no fresh-vs-upgraded convergence test (item 37) can pass until those defaults are normalized or explicitly declared intentional exceptions. This is a precondition, not a footnote.
**Next action:** define the official installation route; ensure `lazy_table_creator` and the test setup scripts remain test-only; normalize or formally except the server-side defaults before any parity comparison.
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

**[ADVANCED] 29. Establish permanent database engineering rules.**
Partially incorporated in local engineering guidance: the enum ownership contract, the no-false-stamp rule, the parity-artifact requirement and the migration-generation rules are recorded. Outstanding: the 145-default-diff case study, the same-ID/different-schema divergence case study, and the 2026-10-18 Design 2 runtime-defect finding.
**Next action:** complete the incorporation of the `ensure_all_enums()` finding, the corrected `create_type`/`checkfirst` contract (item 11c), the parity-artifact requirement (item 17a condition 5), the local divergence case study, the 145-default-diff example, and the `exec_driver_sql`/`%` bootstrap defect.

---

# Phase 5 — Prove the result and prevent recurrence (items 30–39)

**[CLOSED] 30. Create approved disposable PostgreSQL verification environment.**
Two environments were authorized and created on local PostgreSQL 18.4 and both are retained: `afcon360_h2p_replay_20261018_test` (H2′ migration replay) and `afcon360_b0_design2_rt_20261018` (Design 2 runtime verification). Neither `afcon360_prod` nor `afcon360_test` was used as a scratch database.
**Next action:** preserve both as evidence — do not reuse, reset, drop or automatically clean them up, and keep the other pre-existing scratch databases in place.

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
Advanced by evidence: the local (uncommitted) Design 2 source-level contract suite now passes **38 tests** (5 new regression tests added for the `%` placeholder handling, `no_parameters` execution option, schema-scope consistency, and real import-failure coverage). A standard run reports three Flask-Session deprecation warnings (33 passed + 3 warnings). An isolated contract run using `pytest --noconftest -p no:warnings` with `Engine.connect`/`Engine.raw_connection` blocked exits 0 with **38 passed** and no warnings reported. **Live PostgreSQL bootstrap verification has passed** (item 20): `bootstrap_model_schema()` succeeded on a fresh disposable database, marker `complete`, 217 tables, 47 enums, no `alembic_version`; read-only `validate_model_bootstrap()` also passes. Outstanding: the complete test suite, fresh-clone replay, PostgreSQL 15/Docker replay, and committed PostgreSQL integration gates.
**Next action:** run the full test suite; add empty-database replay, migration-graph, conflict-detection and schema-verification checks to the ongoing review process. Close the work only when that acceptance evidence passes and the final record is approved.

---

## Subordinate findings (own evidence; NOT counted in the 39)

- **10a** — Historical investigation of the "182 tables" claim complete. [RECORDED]
- **10b** — Empirical clean-install reproduction of that historical claim outstanding. [OPEN]
- **11a** — `ensure_all_enums()` never-existed finding. [CLOSED]
- **11b** — README write/delete commits (`a1a490b` / `76a518b`). [CLOSED]
- **11c** — Native-enum creation contract corrected. [CLOSED]
- **12a** — Deployment evidence ledger recorded. [RECORDED]
- **12b** — Docker census pending; blocks H3. [OPEN]
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
<<<<<<< HEAD
| ensure_all_enums() never existed | Enum flag archaeology |
| create_type=False introduced at 174b625, not a1a490b | Enum flag archaeology |
| e6f319ffc8c8 is a name mismatch, not duplication | Worker 2 matrix |
| `df55cbe3f516` is tracked and the clean replay reaches it; FK/model coupling remains a separate open parity gate | 2026-10-18 remote-tree check and fresh replay |
| bookingstatus 11 members at 449bdcd; NO_MATCH added at 5322c63 | Phase 2 Final Reconciliation |
| window_mode_enum introduced by f91075478868 (via fbc7491) | Phase 2 Final Reconciliation |
=======
| `ensure_all_enums()` never existed | Enum flag archaeology |
| `create_type=False` introduced at `174b625`, not `a1a490b` | Enum flag archaeology |
| `e6f319ffc8c8` is a name mismatch, not duplication | Worker 2 matrix |
| `df55cbe3f516` coupled to dirty tree, not committed HEAD | Worker 2 §B1 |
| bookingstatus had 11 members at `449bdcd`; `NO_MATCH` added at `5322c63` | Phase 2 Final Reconciliation |
| `window_mode_enum` introduced by `f91075478868` (via `fbc7491`) | Phase 2 Final Reconciliation |
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)
| Group-count expression corrected: 119 + 14 − 1 = 132 (extra +1 at term 18 removed) | Default-difference audit |
| `checkfirst`-only-tables claim withdrawn; `create_type` governs enum DDL | Item 11c correction |
| `org_business_category` counted once across the union inventory | Item 17b reconciliation |
| `df55cbe3f516` untracked — **superseded**; the revision is now tracked and reached by the clean replay | H2′ repair commit, 2026-10-18 |
| "No replay authorized / no clean-install evidence" — **superseded**; the isolated replay passed on PostgreSQL 18.4 | Item 19, 2026-10-18 |
| "Architecture undecided / both unapprovable" — **superseded**; H2′ approved and implemented as interim, H3 selected as destination | Item 18, 2026-10-18 |
| Design 2 runtime verification — **superseded**; first run FAILED (percent-placeholder defect), post-fix run PASS on `afcon360_d2_bootstrap_fix_20261018_test` | Item 20, 2026-10-18 |

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

<<<<<<< HEAD
- **H3/N-squash is selected but not authored.** H3 readiness remains blocked by the Docker census (12b), supported starting revisions (13), verified FK/model coupling (16d), per-database parity artifacts (14/17b), and state-specific transition procedures (15).
- **Existing database convergence remains unresolved.** Item 28a's 145 server-default differences still need per-column disposition; six model-less tables and legacy enum/orphan candidates still need explicit disposition. Item 37 cannot pass until intended differences are resolved or documented.
- **Design 2 runtime verification is pending.** The owner authorized one additional uniquely named disposable PostgreSQL database for testing the committed `bootstrap_model_schema()` path. Do not claim a runtime PASS before the evidence report arrives.
- **Broader deployment verification remains open.** The full pytest suite has not been run against the migration-built replay DB; a fresh-clone replay has not been recorded; PostgreSQL 15/Docker census has not been done.
- `afcon360_prod` and `afcon360_test` remain untouched. No production upgrade is authorized by the fresh-install result.
=======
- **Supported starting revisions** (item 13) — human product decision; gates items 15 and 35.
- **Docker census** (subordinate 12b) — H3 remains blocked until this closes.
- **FK/model coupling and per-database parity** (item 27) — required before any stamp (H3) or upgrade over an old-dynamic body (H2′).
- **28a default dispositions** and the **six model-less tables** — item 37 convergence cannot pass until both are dispositioned.
- **Historical/intermediate-state support** — no such upgrade has been verified; items 22 and 23 do not cover it.
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

Resolved on 2026-10-18 and no longer blocking: scratch-replay authorization (item 19), `df55cbe3f516` tracking (subordinate 16d), and Design 2 bootstrap defect (item 20).

<<<<<<< HEAD
| Phase | Status |
|---|---|
| Phase 1 | 8 / 8 closed |
| Phase 2 | 4 closed (9, 11, 16, 17) · 3 advanced (12, 14, 15) · 1 partial (10 + subordinates 10a/10b) · 1 open (13) |
| Phase 3 | 2 closed (18, 19) |
| Phase 4 | 2 closed (22, 23) · 6 advanced (20, 21, 24, 27, 28, 29) · 2 not started (25, 26) |
| Phase 5 | 2 closed (30, 31) · 3 advanced (32, 34, 39) · 5 not started (33, 35–38) |

Parent totals: 18 closed + 12 advanced + 1 partial + 1 open + 0 gated + 7 not started = 39. Subordinates (10a/10b, 11a–c, 12a, 14a, 16d, 17a/b, 22a, 28a) counted separately.
=======
---

## Status summary by phase

| Phase | Items | Status mix |
|---|---|---|
| Phase 1 — Findings established | 1–8 | 8 closed |
| Phase 2 — Evidence for the architecture decision | 9–17 | 4 closed (9, 11, 16, 17) · 3 advanced (12, 14, 15) · 1 partial (10) · 1 open (13) |
| Phase 3 — Decisions and authorization | 18–19 | 2 closed |
| Phase 4 — Implement the approved permanent repair | 20–29 | 2 closed (22, 23) · 6 advanced (20, 21, 24, 27, 28, 29) · 2 not started (25, 26) |
| Phase 5 — Prove the result and prevent recurrence | 30–39 | 2 closed (30, 31) · 3 advanced (32, 34, 39) · 5 not started (33, 35, 36, 37, 38) |

Parent totals: **18 closed + 12 advanced + 1 partial + 1 open + 0 gated + 7 not started = 39.** Subordinates (10a/10b, 11a–c, 12a/12b, 14a/14b, 16a–d, 17a/17b, 22a, 28a) are counted separately and never added to the 39.

---
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)

## Definition of complete

The approved installation path passes a clean PostgreSQL replay **on every supported server version and from a genuinely fresh clone**; supported upgrades preserve data; the resulting schemas independently match an approved expected schema; model/physical parity and per-database parity are evidenced; the server-default and model-less-table dispositions are closed; and automated checks guard against recurrence. A successful fresh-install replay on one server version is necessary but not sufficient.

---

## Safety

<<<<<<< HEAD
Snapshot updated 2026-10-18. The H2′ replay database `afcon360_h2p_replay_20261018_test` is a migrated disposable evidence database; preserve it until evidence review and do not reuse or automatically drop it. Design 2 PostgreSQL runtime verification has been authorized against one additional unique disposable database but remains pending until Agent 2 reports. `afcon360_prod` and `afcon360_test` were not upgraded or modified. Other investigation scratch databases still exist and must not be automatically cleaned up. The four H2′ migration changes and Design 2 changes are pushed to GitHub `main`. Original DOCX remains the reference at `C:\Users\OBED\Desktop\AFCON360_Database_Reliability_Master_To_Do_and_Fix_Register.docx`; this Markdown file is the working register.

## Next action

The next actions, in order:

1. Complete Agent 2's authorized PostgreSQL runtime verification of `bootstrap_model_schema()` on one new, uniquely named disposable database. Do not touch or reuse existing scratch/protected databases.
2. Run the full pytest suite against the migrated disposable replay database and record failures without assuming they are caused by the H2′ changes.
3. Perform a fresh-clone replay of the pushed `main` branch, then run the same clean-install verification on the PostgreSQL version pinned by Docker. Keep these separate from the unresolved H3/per-database parity work.

Do not upgrade production or start H3 authoring until the applicable architecture, parity, and transition gates are explicitly cleared.

 
## Phase 6 — Evidence and status reconciliation (2026-10-18)

This section is the current evidence snapshot. Where earlier sections contain “outstanding”, “not authorized”, “no migration executed”, or “no evidence” language from the pre-replay snapshot, use this dated reconciliation for current status. Historical claims about the exact 182-table schema produced at the original commit are not silently rewritten.

### Published commits

The owner reported a successful push of `main` from `f0c41e7` to `6c0683793ad186024b863db494860cafc7eef1d6`. The remote comparison confirms four commits ahead of the prior base. The pushed commits include:
- `ff5fe53` — Design 2 model-bootstrap marker, loud model-registration checks, removal of false Alembic-head stamping, and source-level contract tests.
- `ef8ddd2` — H2′ explicit frozen root DDL plus downstream enum/check/slug reconciliations.
- `6c06837` — B0 enum inventory/plan evidence artifact.
- The fourth commit, `fbd54e1`, predates the two database-specific commits and includes wallet/admin work; its inclusion was visible in the remote comparison. It is not a database-reliability fix and should not be conflated with H2′ evidence.

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

`python -m pytest -q tests/test_model_bootstrap_contract.py` returned `33 passed, 3 warnings`. The warnings were Flask-Session filesystem-backend deprecation warnings. These are source-level contract tests; they do not constitute live PostgreSQL execution of the committed `bootstrap_model_schema()` path. The separate, explicitly authorized Design 2 PostgreSQL runtime gate is still pending its report.

### Open decisions and evidence boundaries

- The H3 N-squash root does not exist yet. H3 is the selected durable target; H2′ is the interim repair to the existing chain, not a replacement for H3.
- The 145 server-default differences remain observed and unresolved: 132 Prod-only, 12 Test-only, and one Both-differ. Do not normalize them without per-column intent/disposition.
- Six tables in the migration-built schema lack current SQLAlchemy models; their retain/model/drop disposition remains open.
- Legacy enum/orphan types, referenced enum/default handling, `organisations.business_category` divergence, and the coupled FK/model parity remain unresolved for existing databases.
- The full pytest suite, fresh-clone replay, PostgreSQL 15/Docker replay, supported historical-state upgrades, current-head repeat-upgrade comparison, full schema parity, data/constraint behavior, and failure recovery have not yet been verified.
- `afcon360_prod` and `afcon360_test` were not upgraded or modified during the work described here. Preserve the replay and investigation databases until evidence review; no automated cleanup is authorized by this register update.
=======
All existing dirty and untracked work in the checkout is preserved. `afcon360_prod` and `afcon360_test` remain off-limits for write operations and were not upgraded or modified. Disposable verification databases (`afcon360_h2p_replay_20261018_test`, `afcon360_b0_design2_rt_20261018`) and all pre-existing scratch databases are retained and must not be automatically cleaned up. `df55cbe3f516` and its coupled working-tree changes are preserved. No migration was run, no database was created, dropped or reset, and no test suite was executed as part of this documentation update. The original DOCX is retained as reference at `C:\Users\OBED\Desktop\AFCON360_Database_Reliability_Master_To_Do_and_Fix_Register.docx`; this Markdown file is the working register. No GitHub write operation was performed and this change is not staged or committed.

---

## Next action

The four immediate next actions, in order of leverage:

1. **Define the supported division of responsibility between the migration path and the bootstrap path** (item 20). The live bootstrap gate is satisfied; items 28 and 39 remain advanced pending broader integration gates.
2. **Obtain the supported-starting-revisions decision** (item 13). Unblocks items 15 and 35 and the whole historical-state track.
3. **Verify FK/model coupling and produce per-database parity artifacts** (item 27). Prerequisite to any H3 stamp or H2′ upgrade over an old-dynamic body.
4. **Bring up the docker container and run the census probe** (subordinate 12b). Unblocks H3.

Items 3 and 4 are mechanical. Item 2 is a decision. Item 1 is defect remediation with the verification already authorized and its database already provisioned.
>>>>>>> 0abb8d0 (Model bootstrap contract, favicon assets, and DB reliability register update)
