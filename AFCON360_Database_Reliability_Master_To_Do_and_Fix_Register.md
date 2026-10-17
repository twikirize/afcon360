# AFCON360 — Database Reliability — Master To-Do & Fix Register

**Status: 12 closed · 5 advanced · 1 partial · 1 open · 2 gated · 18 not started**
**Architecture: undecided (H2′ and H3 both unapprovable today)**
**Permanent fixes implemented: 0**
**Clean-install verification completed: 0**

## Marking legend

- [CLOSED] — item's investigation complete; evidence recorded
- [PARTIAL] — verdict reached; specific sub-evidence outstanding
- [ADVANCED] — substantively progressed; specific input still required
- [OPEN] — unchanged from original register
- [GATED] — awaiting decision or prerequisite
- [PREREQ] — prerequisite to other items, not downstream
- [REVISED] — scope corrected by evidence (wording state; implementation not started unless separately marked)
- [CLARIFIED] — finding restated without scope change (wording state; implementation not started unless separately marked)
- [NEW] — added since original register was authored
- [SPECIFIED]/[DELIVERED]/[RECORDED] — subordinate finding recorded under its parent

## Canonical corrections (do not re-derive)

- **C1** — bookingstatus 12-label state is consistent with past-11; downgrade-rename mechanism indicated, execution unproven.
- **C2** — Types present in dev but absent in test are unclassified, not disposable. Use "unclassified", not "ghost".
- **C3** — CONFIRMED in the 324-row matrix denotes declaration duplication (source-proven), not observed failure. Only one empty-replay failure is on record: the original missing transactiontype.
- **C4** — df55cbe3f516 untracked breaks clean-checkout graph resolution; does not affect SELECT version_num FROM alembic_version. Working-tree/record inconsistency, not a DB malfunction.

## Phase 1 — Findings established (8 / 8 complete, unchanged)

- [x] 1. First observed installation failure — missing transactiontype.
- [x] 2. Enum ownership investigation — references without creation paths identified.
- [x] 3. Alembic history mapped — 27-revision chain including df55cbe3f516.
- [x] 4. Root-baseline design problem identified.
- [x] 5. Repeated migration operations identified.
- [x] 6. Competing schema-creation methods investigated.
- [x] 7. Historical evidence recovered.
- [x] 8. Engineering destination agreed.

## Phase 2 — Evidence for the architecture decision

[CLOSED] 9. Reconstruct the original baseline history.
Evidence: At 449bdcd (2026-08-23) both app/audit/comprehensive_audit.py and app/transport/models.py carry plain SQLEnum(...) declarations. Root body db.metadata.create_all(op.get_bind()) byte-identical to HEAD. Under plain SQLEnum, Postgres derives the type name from the Python class and checkfirst=True creates the type if absent.
Narrowed claim: The enum declarations supported native type creation via SQLAlchemy defaults. Whether the complete chain reached head from empty is unproven (gated on item 19).

[PARTIAL] 10. Verify the "182 tables from EMPTY" claim.
Evidence: The claim first appears at 449bdcd — the same commit that authored the baseline. No committed flask db upgrade transcript exists. The one quantified log at that commit records the test bootstrap path (create_all + stamp head against afcon360_test).
Verdict: Claim made, unsubstantiated by committed evidence. Mechanism was correct at 449bdcd; became incorrect at 174b625. The narrower reconstruction of the historical claim is complete.
Reconciliation note: a prior snapshot marked this item CLOSED. It is PARTIAL, not CLOSED: the historical investigation (subordinate 10a) is complete, but the empirical clean-install reproduction (subordinate 10b) is a separate deliverable gated on item 19. Do not count item 10 as CLOSED.
[RECORDED] 10a. Historical investigation complete (claim provenance, same-commit introduction, test-bootstrap log identification).
[GATED] 10b. Empirical reproduction outstanding — gated on item 19.

[CLOSED] 11. Trace when enum declarations changed.
Evidence: Broad create_type=False introduced at 174b625 (2026-10-13 05:39). Empty commit body.

| Commit | Date | Effect |
|---|---|---|
| 449bdcd | 2026-08-23 | Zero create_type=False |
| a1a490b | 2026-10-12 | One legitimate reference; writes README promising ensure_all_enums() |
| 76a518b | 2026-10-13 04:01 | Deletes the README paragraph |
| 174b625 | 2026-10-13 05:39 | 43 columns with the flag, inline |
| 39266d2 | 2026-10-13 07:35 | 5 wallet columns |
| 5ef3014 | 2026-10-14 | HEAD, reformat only |

[CLOSED] 11a. Confirm ensure_all_enums() never existed.
Zero definitions across all refs; zero call sites at HEAD. The README paragraph was written at a1a490b, deleted at 76a518b, ninety minutes before 174b625.
[CLOSED] 11b. Confirm README paragraph write/delete commits.
Written a1a490b; deleted 76a518b.
[CLOSED] 11c. Correct native-enum creation contract.
The `create_type` option governs whether SQLAlchemy automatically emits PostgreSQL enum creation and drop DDL. When automatic creation is disabled, the enum type must have an explicit creation owner. The `checkfirst` option controls existence checking during applicable create/drop operations, including enum type operations; it is not the switch that suppresses automatic enum DDL. To be recorded in item 29.

[ADVANCED] 12. Establish deployed migration states.
Local census complete:

| Env | alembic_version | Tables | Enum types | State |
|---|---|---:|---:|---|
| afcon360_prod (local) | df55cbe3f516 | 224 | 68 | Untracked revision; physically divergent |
| afcon360_test | df55cbe3f516 | 224 | 49 | Untracked revision; stale physical schema |
| docker | unreachable | — | — | Containers down |

Both local DBs are stamped at untracked df55cbe3f516. Clean checkouts cannot resolve that ID.
Deployment evidence (repo-only): zero tags — no release boundary. Only in-repo migration executor: docker-entrypoint.sh:47 flask db upgrade (web role only). Doctrine split between docs/POSTGRES_TESTING_CONTRACT.md (migrate-then-test) and constitution :691,705 + tests/conftest.py:254-262 (conditional create_all + stamp).
Closure requires: docker census (item 12b).
[NEW] 12a. Deployment evidence ledger.
Recorded. Canonical for future contributors.
[OPEN] 12b. Docker census.
Re-execute Q1–Q4 probe against the container's Postgres when available. Blocks H3.

[OPEN] 13. Define the supported starting revisions.
Human product decision. Cannot advance from source.

[ADVANCED] 14. Compare H2′ against existing database states.
Same-ID/different-schema hazard field-proven: afcon360_test at df55cbe3f516 carries org_business_category as a live-USED 39-label UPPER enum; afcon360_prod at the same revision carries the same column as varchar(40) NULL with org_business_category existing as a 4-label lowercase orphan. Same revision ID, different physical schema, different repair operations required per DB.
Corrections carried: prod holds 68 types (not 69); organisations.slug is NOT NULL in both DBs.
Closure requires: per-DB parity artifacts + history-rewrite exception ruling for H2′.
[NEW] 14a. Stamp-timing distinction for H2′.
A database stamped 8a0deccce6f6 before the enum regression has one schema; one stamped after has another. Same ID, no timestamp in alembic_version. Auxiliary evidence (deploy logs, backups) required. Hard compatibility condition.
[SPECIFIED] 14b. Divergent-schema dispositions.
The two DBs require different repair operations under one revision ID: test needs a conversion path for org_business_category (39-label UPPER → varchar(40)); drop is not an option (USED). Prod needs a disposition ruling for org_business_category (4-label lowercase orphan). Both need disposition rulings for the 16 dev-only orphan candidates.
Refuted over-claim: org_business_category is not the only physical-schema difference. The Phase 2 reconciliation established 1 type-diff + 145 default-diffs. See item 17b.

[ADVANCED] 15. Design the H3 transition procedure.
Procedure defined: new root N-squash; old files retired in same commit; merge revisions rejected; per-state commands (empty / root-stamped / intermediate / at-head / unknown); stamp only after parity; rollback via re-track + re-stamp.
New refinement from Phase 2: under H3, f91075478868 retires, dissolving its 4× window_mode_enum emit defect. Under H2′, f91075478868 remains, and its emit defect requires either an in-place history exception or a conditionalizing repair.
Closure requires: docker census (12b) + per-DB parity artifacts + item 16d.

[CLOSED] 16. Architecture-specific conflict plan.
Class separation confirmed: root-vs-child (e.g., booking_flow_type, slug objects) is potentially removed by freezing the root under H2′. Child-vs-child (slug pair, offerings.code double-unique) requires a history exception under either architecture.
Slug pair: 71893e3a42a2 and bd9d3bb673aa both create the same three objects. Live evidence: slug is NOT NULL in both DBs — consistent with the second duplicate never having executed. Strongly indicated, not proven.
[CLOSED] 16a. Separate root-vs-child and child-vs-child classes.
Recorded.
[DELIVERED] 16b. 324-row mechanical conflict matrix.

| Class | Count |
|---|---:|
| CONFIRMED (declaration duplication) | 74 |
| CONDITIONAL | 229 |
| NOT A CONFLICT | 21 |
| PREDICTED (replay failure) | 0 |
| Total | 324 |

229 CONDITIONAL rows collapse to CONFIRMED only via approved scratch replay.
[CLOSED] 16c. df55cbe3f516 vs committed HEAD FK coupling.
Proven via git diff: df55cbe3f516's FK names match the dirty working tree, not committed HEAD. One atomic unit.
[PREREQ] 16d. Track df55cbe3f516 atomically with coupled diffs.
Both live DBs are stamped at this ID; a clean checkout cannot resolve it. Prerequisite to either architecture.

[CLOSED] 17. Architecture comparison.

| Criterion | H2′ | H3 |
|---|---|---|
| Fresh install | Deterministic frozen root | Same; smaller replay set |
| Old-dynamic bodies | Same-ID/different-schema → parity + rewrite exception | Same hazard → parity + stamp per DB |
| Intermediates | No mapping (topology preserved) | Per-revision map + upgrade-then-stamp |
| Unknown revs | Halt-and-map | Blocked until census |
| Enum ownership content | Identical label sets | Identical |
| Enum ownership location | Frozen root + f91075 exception | N-squash body; f91075 retired |
| Data preservation | No stamps; repairs conditional | Stamp-gated |
| Immutability | Violates once, explicitly | Preserves old files |
| Rollback | Downgrade chain | Re-track + re-stamp |
| Future authoring | Unchanged | Clean lineage; retired-ID ban |

Asymmetry surfaced by Phase 2: H2′ carries strictly more repair surface than H3 for the same enum-content outcome. Not a disqualifier, but a real cost.
[RECORDED] 17a. Compatibility conditions (i)–(vi).
1. Enum-owner set complete; 4× window_mode_enum deduped; every creator-less type given one creator.
2. Slug duplicate reconciled.
3. e6f319ffc8c8 and df55cbe3f516 name-assumptions made state-conditional.
4. df55cbe3f516 tracked atomically with coupled FK-name diffs.
5. Parity artifact before any stamp (H3) or upgrade over old-dynamic body (H2′).
6. alembic_version census before cutover.
[CLOSED] 17b. Column-level parity and enum count reconciliation.
The 101/48 gap was a phantom — prior figures compared unlike quantities. Corrected: prod Q1 = 101 rows = 58 table-attribute + 43 index-attribute rows (47 distinct enums); test Q1 = 103 rows = 59 + 44 (48 distinct enums). Deltas close exactly: +1 table row (organisations.business_category enum-typed in test, varchar in prod) and +1 index row (its index). The distinct-enum delta (47 vs 48) is the same single object.
Column diff (mechanical): Only-prod 0; Only-test 0; Type-differs 1; Nullability-differs 0; Default-differs 145.
145 default-diffs are a new finding: 132 Prod-only + 12 Test-only + 1 Both-differ (`119 + 14 − 1 = 132`; the extra `+1` at original term 18 was unmappable and removed). 132 columns carry DB-side defaults in prod and NULL in test; 12 reversed; `system_configs.created_at` differs on both sides (`CURRENT_TIMESTAMP` vs `now()`). The pattern is consistent with test having been create_all-built rather than migration-built (corroborated by the bootstrap evidence in §I; the diff alone does not prove provenance): server-side defaults appear only when migrations emit them explicitly.
Enum inventory reconciled (unique type names — org_business_category counted once): 48 USED names (47 shared table-column types + org_business_category, which is USED in test and an orphan candidate in prod) + 3 REFERENCED (account_owner_type_enum, creatortype, ownertype, via live column defaults) + 16 dev-only orphans (12 legacy-known: 6 retired-era zero-dependency + 6 accommodation remnants; 4 unknown-origin) + bookingstatus (orphan in both DBs, downgrade-referenced). Per-database check: prod 47 + 1 + 3 + 16 + 1 = 68 ✓; test 48 + 1 = 49 ✓.
Evidence artifacts (temporary, not version-controlled): `C:\Users\OBED\AppData\Local\Temp\opencode\col_diff.py`, `col_diff_out.txt`, `cols_prod.txt`, `cols_test.txt`. Future readers must not assume these files are permanently preserved; the counts above are the durable record.
Register-level consequence: item 37 (fresh-vs-upgraded convergence) cannot pass until the 145 default-diffs are normalized or explicitly declared intentional exceptions. See item 28 subordinate.

[CLOSED] 22a. bookingstatus root-era verification.
Source-verified, no inference. At 449bdcd: class BookingStatus exists with 11 members (DRAFT…DISPUTED, no NO_MATCH). git log -S "NO_MATCH" → only 5322c63. Parent 5322c63~1: status = db.Column(SQLEnum(BookingStatus), …). At 5322c63: status = db.Column(db.String(30), default=BookingStatus.DRAFT.value, …). The SQLEnum → String(30) flip and the 12th member are atomic in one commit.
Conclusion: H2′'s frozen root would create an 11-label native bookingstatus (or none, if frozen post-5322c63) — never a 12-label one. The 12-label live state is producible in-repo only by 20260930_1335:80-86's downgrade; execution unproven per C1. The type has no current direct column dependency in either database, but the downgrade path references it: disposition (retain, drop with downgrade-path retirement, or recreate) depends on the selected history strategy. No drop or creation decision is authorized.

## Phase 3 — Decisions and authorization

[GATED] 18. Approve one architecture.
Neither H2′ nor H3 is approvable today. Both require items 12b, 13, 16d, and per-DB parity artifacts.
[GATED] 19. Approve the isolated PostgreSQL verification plan.
Highest-leverage single decision. Would collapse 229 CONDITIONAL rows and produce the first honest fresh-install evidence.

Working policies:
- Retain native PostgreSQL enums.
- Migration history is immutable by default.
- Stamps require independent schema verification.
- The `create_type` option governs whether SQLAlchemy automatically emits PostgreSQL enum creation and drop DDL; `checkfirst` controls existence checking during applicable create/drop operations, including enum type operations. (Corrected per item 11c; the earlier checkfirst-only-tables claim is withdrawn.)
- alembic_version alone is insufficient as a schema fingerprint — an independently recorded parity artifact is required before any stamp or upgrade over an old-dynamic body.

## Phase 4 — Implement the approved permanent repair

[NOT STARTED] 20. Establish canonical schema-creation architecture.
Depends on item 18.
[REVISED] 21. Repair enum creation ownership.
Content (identical for both architectures): one CREATE TYPE per USED/REFERENCED type with exact live label sets. No bookingstatus creation by that name. Conversion path (not drop) for test's live-USED 39-label org_business_category. Preserve-or-migrate the 3 legacy column defaults.
Location: H2′ — frozen 8a0deccce6f6 body plus an exception or conditionalizing repair for f91075478868's enum declarations. H3 — N-squash body; f91075478868 retires and its defect dissolves.
[REVISED] 22. Eliminate repeated window_mode_enum creation.
Content: single CREATE TYPE window_mode_enum AS ENUM ('CALENDAR', 'ROLLING'). Live DBs already converge — no-op there.
Location: H2′ — f91075478868 remains; the 4× emit at :23,:24,:53,:54 is predicted to fail under either architecture and requires an in-place exception or a conditionalizing repair. H3 — f91075478868 retires; emission occurs once in N-squash.
Note: no empty-DB runtime confirmation. The failure is predicted by source inspection, not observed.
[NOT STARTED] 23. Resolve duplicate slug migrations.
Confirmed child-vs-child. Requires a history exception under either architecture. bd9d3bb673aa nullability differs; live evidence shows slug NOT NULL in both DBs, consistent with the second duplicate never having executed.
[ADVANCED] 24. Resolve remaining confirmed and conditional conflicts.
Deliverable complete: 324-row matrix.
Disposition space:

| Category | Count | Action |
|---|---|---|
| USED enum names | 48 | Create in frozen DDL, exact labels |
| REFERENCED enums | 3 | Preserve defaults or migrate |
| ORPHAN enums (dev-only) | 16 | Drop-candidate pending ruling |
| bookingstatus | 1 | Retain unless downgrade abandoned |
| org_business_category (prod orphan copy) | — | Covered by the USED-name count above; prod copy is a drop-candidate pending ruling, test copy needs conversion |
| 229 CONDITIONAL rows | 229 | Await scratch replay |

[CLARIFIED] 25. Correct foreign-key assumptions.
e6f319ffc8c8 is a name mismatch, not duplication. df55cbe3f516 FK names match the dirty tree, not committed HEAD.
[NOT STARTED] 26. Make data-sensitive migrations safe.
request_fingerprint NOT NULL-without-default confirmed as data-dependent.
[ADVANCED] 27. Resolve df55cbe3f516 and coupled model changes.
Elevated to prerequisite (item 16d). Both live DBs are stamped at df55. Atomic landing required.
[REVISED] 28. Consolidate schema-creation procedures.
Subordinate finding (new) — 145 default-diffs: the Phase 2 column diff is consistent with test having been create_all-built (132 columns carry DB-side defaults in prod that test lacks; 12 reversed; 1 Both-differ). Server-side defaults appear only when migrations emit them explicitly.
Consequence: no fresh-vs-upgraded convergence test (item 37) can pass until these defaults are either normalized or explicitly declared intentional exceptions. This is a precondition, not a footnote.
Action: define the official installation route; ensure lazy_table_creator and test setup scripts are test-only; normalize server-side defaults between create_all-built and migration-built databases before any parity comparison.
[NEW] 28a. Classify and disposition the 145 server-default differences.
The 145 default differences comprise 132 Prod-only, 12 Test-only and one Both-differ case. Each must be classified against evidence and assigned an intended disposition before the fresh-versus-upgraded convergence requirement under item 37 can pass.
Principles: a physical difference is not proof that prod or test is correct; do not normalize defaults simply to make the two environments match; preserve exact observed expressions in the evidence; distinguish observed differences from corroborated explanations and unresolved intended behavior; explicitly document any intentional exception or required schema-owner decision; keep the separate organisations.business_category type conversion visible in the convergence requirements. Cross-reference items 20, 29 and 37.
The item 28a investigation may record the observed comparison as complete, but the disposition work remains outstanding.
[NOT STARTED] 29. Establish permanent database engineering rules.
Scope additions: record the ensure_all_enums() finding and the correct native-enum creation contract (item 11c — `create_type` governs automatic enum DDL; `checkfirst` governs existence checking); document that create_type=False does not affect autogenerate output — the flag was never a suppression mechanism; document the parity-artifact requirement (item 17a condition 5); document the local DB schema divergence under identical df55cbe3f516 stamps as a case study; document the 145-default-diff finding as a canonical example of create_all vs migration divergence.

## Phase 5 — Prove the result and prevent recurrence

[NOT STARTED] 30. Create the approved disposable PostgreSQL test environment. This happens only after explicit authorization and must never use afcon360_prod or afcon360_test as the scratch database.
[NOT STARTED] 31. Pass the clean-install test. Run the supported installation command against a genuinely empty PostgreSQL database, replaying the entire required migration path.
[NOT STARTED] 32. Verify physical schema completeness independently. Check tables, columns, enum types, indexes, constraints, foreign keys, and other required schema objects against an independently established expected schema.
[NOT STARTED] 33. Verify model/schema parity. Run the supported schema-comparison checks, including flask db check where appropriate, and account for every intentional exception.
[NOT STARTED] 34. Verify current-head behavior. Confirm the approved upgrade process behaves correctly when the database is already at the current head and does not introduce new differences.
[NOT STARTED] 35. Test upgrades from supported historical states. Use disposable databases or fixtures representing the agreed supported revisions, with representative existing data.
[NOT STARTED] 36. Verify data and constraints. Check that existing values retain their meaning, invalid data is rejected, and native enums and relationships behave correctly.
[NOT STARTED] 37. Compare fresh and upgraded results. Independently compare the resulting schemas to prove both paths converge on the same intended structure.
[NOT STARTED] 38. Verify failure recovery. Document and test the approved recovery procedure, including what happens if a migration fails partway through. Do not assume every downgrade can safely undo every change.
[NOT STARTED] 39. Establish automated regression gates and close the work. Make empty-database replay, migration-graph checks, conflict detection, schema verification, and appropriate existing-data tests part of the ongoing review process. Close the task only when the acceptance evidence passes and the final record is approved.
Preconditions added by Phase 2: item 37 (fresh-vs-upgraded convergence) requires normalization of the 145 default-diffs first (see item 28 subordinate). All other items unchanged. Gates A–F remain the acceptance framework.

## Subordinate findings

- 10a — Historical investigation of the "182 tables" claim complete.
- 10b — Empirical clean-install reproduction outstanding, gated on item 19.
- 11a — ensure_all_enums() never-existed finding.
- 11b — README write/delete commits.
- 11c — Native-enum creation contract (corrected wording above).
- 12a — Deployment evidence ledger (recorded).
- 12b — Docker census pending.
- 14a — Same-ID/different-schema hazard field-proven.
- 14b — Per-DB repair operations required; 1 type-diff + 145 default-diffs.
- 16d — df55cbe3f516 tracking prerequisite to either architecture.
- 17a — Compatibility conditions (i)–(vi).
- 17b — Column parity: 101/48 phantom resolved; 145 default-diffs documented.
- 22a — bookingstatus root-era verification complete.
- 28a — 145 default-diff normalization (new precondition under item 28).

## Corrections applied since original register

| Correction | Source |
|---|---|
| prod holds 68 enum types, not 69 | Enum dependency census |
| organisations.slug is NOT NULL in both DBs | Enum dependency census |
| bookingstatus is an orphan, not a live column type | Enum dependency census |
| "Only label divergence is org_business_category" withdrawn — 1 type-diff + 145 default-diffs | Phase 2 Final Reconciliation |
| Legacy-known orphan count is 12, not 10 | Phase 2 Final Reconciliation |
| 101/48 gap was a phantom — arithmetic closes as 58+43 vs 59+44 | Phase 2 Final Reconciliation |
| ensure_all_enums() never existed | Enum flag archaeology |
| create_type=False introduced at 174b625, not a1a490b | Enum flag archaeology |
| e6f319ffc8c8 is a name mismatch, not duplication | Worker 2 matrix |
| df55cbe3f516 coupled to dirty tree, not committed HEAD | Worker 2 §B1 |
| bookingstatus 11 members at 449bdcd; NO_MATCH added at 5322c63 | Phase 2 Final Reconciliation |
| window_mode_enum introduced by f91075478868 (via fbc7491) | Phase 2 Final Reconciliation |
| Group-count expression corrected: 119 + 14 − 1 = 132 (extra +1 at term 18 removed) | Default-difference audit |
| checkfirst-only-tables claim withdrawn; create_type governs enum DDL | Item 11c correction |
| org_business_category counted once across the union inventory | Item 17b reconciliation |

## What is blocking us today

- Docker census (item 12b) — H3 blocked until this closes.
- df55cbe3f516 tracking (item 16d) — prerequisite to either architecture.
- Supported starting revisions (item 13) — human product decision.
- Scratch-replay authorization (item 19) — highest-leverage single decision; collapses 229 CONDITIONAL rows.
- Per-DB parity artifacts — required before any stamp (H3) or upgrade over old-dynamic body (H2′).
- 28a default dispositions outstanding; 37 convergence gated on them.

## Status summary

| Phase | Status |
|---|---|
| Phase 1 | 8 / 8 closed |
| Phase 2 | 4 closed (9, 11, 16, 17) · 3 advanced (12, 14, 15) · 1 partial (10 + subordinates 10a/10b) · 1 open (13) |
| Phase 3 | 2 gated (18, 19) |
| Phase 4 | 2 advanced (24, 27) · 8 not started incl. wording-revised 21, 22, 25(CLARIFIED), 28 |
| Phase 5 | 10 not started (30–39) · new precondition under 37 |

Parent totals: 12 closed + 5 advanced + 1 partial + 1 open + 2 gated + 18 not started (implementation) = 39. Subordinates (10a/10b, 11a–c, 12a, 14a, 16d, 17a/b, 22a, 28a) counted separately.

## Definition of complete

The approved installation path passes a clean PostgreSQL replay, supported upgrades preserve data, the resulting schemas independently match expectations, and automated checks guard against recurrence.

## Safety

All existing dirty and untracked work preserved. Both protected databases off-limits for write operations. No implementation or scratch replay authorized. df55cbe3f516 and coupled working-tree changes preserved. Original DOCX retained as reference at `C:\Users\OBED\Desktop\AFCON360_Database_Reliability_Master_To_Do_and_Fix_Register.docx`; this Markdown file is the working register.

## Next action

The three immediate next actions, in order of leverage:

1. Authorize item 19 — the scratch replay. Highest-leverage single decision. Collapses 229 CONDITIONAL rows.
2. Track df55cbe3f516 atomically (item 16d). Prerequisite to either architecture.
3. Bring up the docker container and run the census probe (item 12b). Unblocks H3.

Items 2 and 3 are mechanical. Item 1 is the decision that unblocks Phase 3.
