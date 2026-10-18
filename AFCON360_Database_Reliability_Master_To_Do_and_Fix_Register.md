# AFCON360 — Database Reliability — Master To-Do & Fix Register

**Status (2026-10-18): 18 closed · 12 advanced · 1 partial · 1 open · 0 gated · 7 not started**
**Architecture: H3/N-squash selected as the durable target; H2′ fresh-install correction committed and pushed as an interim repair to the existing chain**
**Implementation now committed: H2′ fresh-install correction and Design 2 no-false-stamp test contract; H3 remains unimplemented**
**Clean-install verification: one empty-database replay passed on local PostgreSQL 18.4; fresh-clone, PostgreSQL 15, full-suite, and full physical-parity gates remain open**

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
- **C3** — CONFIRMED in the 324-row matrix denotes declaration duplication (source-proven), not observed failure. The original observed empty-replay failure was missing `transactiontype`; the revised H2′ chain passed a fresh replay on 2026-10-18. Source-predicted conflicts must not be described as runtime failures.
- **C4 (corrected 2026-10-18)** — `df55cbe3f516` is tracked on GitHub `main`, and the current clean replay reaches it. The earlier claim that this revision is untracked and prevents clean-checkout graph resolution is superseded. Independent physical FK/model parity and coupling checks remain open (items 16d and 32).

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
[RECORDED] 10b. The current H2′ chain replayed successfully from an empty disposable PostgreSQL 18.4 database on 2026-10-18, reaching `df55cbe3f516` after the full migration chain. This confirms the current replay path, not the historical exact “182 tables” claim at `449bdcd`; item 10 remains PARTIAL.

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
Closure still requires the Docker census (item 12b) and remaining deployment-state evidence. **Update 2026-10-18:** a separate disposable database passed the current H2′ empty-database replay. `afcon360_prod` and `afcon360_test` were not upgraded or modified.
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

[CLOSED] 18. Approve one architecture.
Owner direction (2026-10-17): H3/N-squash is the durable target. H2′ is an interim repair to the existing 27-revision chain, not the H3 replacement. This closes the architecture-choice decision only; H3 authoring/cutover remains blocked by items 12b, 13, 16d, per-database parity, and outstanding dispositions.
[CLOSED] 19. Approve and execute the isolated PostgreSQL verification plan.
The owner authorized the disposable replay. On 2026-10-18, `afcon360_h2p_replay_20261018_test` was created empty and the committed H2′ chain reached `df55cbe3f516`. This provides current fresh-install evidence; it does not close all 229 conditional matrix rows or historical-state upgrade testing.

Working policies:
- Retain native PostgreSQL enums.
- Migration history is immutable by default.
- Stamps require independent schema verification.
- The `create_type` option governs whether SQLAlchemy automatically emits PostgreSQL enum creation and drop DDL; `checkfirst` controls existence checking during applicable create/drop operations, including enum type operations. (Corrected per item 11c; the earlier checkfirst-only-tables claim is withdrawn.)
- alembic_version alone is insufficient as a schema fingerprint — an independently recorded parity artifact is required before any stamp or upgrade over an old-dynamic body.

## Phase 4 — Implement the approved permanent repair

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

| Category | Count | Action |
|---|---|---|
| USED enum names | 48 | Create in frozen DDL, exact labels |
| REFERENCED enums | 3 | Preserve defaults or migrate |
| ORPHAN enums (dev-only) | 16 | Drop-candidate pending ruling |
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

## Phase 5 — Prove the result and prevent recurrence

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

## Subordinate findings

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
| `df55cbe3f516` is tracked and the clean replay reaches it; FK/model coupling remains a separate open parity gate | 2026-10-18 remote-tree check and fresh replay |
| bookingstatus 11 members at 449bdcd; NO_MATCH added at 5322c63 | Phase 2 Final Reconciliation |
| window_mode_enum introduced by f91075478868 (via fbc7491) | Phase 2 Final Reconciliation |
| Group-count expression corrected: 119 + 14 − 1 = 132 (extra +1 at term 18 removed) | Default-difference audit |
| checkfirst-only-tables claim withdrawn; create_type governs enum DDL | Item 11c correction |
| org_business_category counted once across the union inventory | Item 17b reconciliation |

## What is blocking us today

- **H3/N-squash is selected but not authored.** H3 readiness remains blocked by the Docker census (12b), supported starting revisions (13), verified FK/model coupling (16d), per-database parity artifacts (14/17b), and state-specific transition procedures (15).
- **Existing database convergence remains unresolved.** Item 28a's 145 server-default differences still need per-column disposition; six model-less tables and legacy enum/orphan candidates still need explicit disposition. Item 37 cannot pass until intended differences are resolved or documented.
- **Design 2 runtime verification is pending.** The owner authorized one additional uniquely named disposable PostgreSQL database for testing the committed `bootstrap_model_schema()` path. Do not claim a runtime PASS before the evidence report arrives.
- **Broader deployment verification remains open.** The full pytest suite has not been run against the migration-built replay DB; a fresh-clone replay has not been recorded; PostgreSQL 15/Docker census has not been done.
- `afcon360_prod` and `afcon360_test` remain untouched. No production upgrade is authorized by the fresh-install result.

## Status summary

| Phase | Status |
|---|---|
| Phase 1 | 8 / 8 closed |
| Phase 2 | 4 closed (9, 11, 16, 17) · 3 advanced (12, 14, 15) · 1 partial (10 + subordinates 10a/10b) · 1 open (13) |
| Phase 3 | 2 closed (18, 19) |
| Phase 4 | 2 closed (22, 23) · 6 advanced (20, 21, 24, 27, 28, 29) · 2 not started (25, 26) |
| Phase 5 | 2 closed (30, 31) · 3 advanced (32, 34, 39) · 5 not started (33, 35–38) |

Parent totals: 18 closed + 12 advanced + 1 partial + 1 open + 0 gated + 7 not started = 39. Subordinates (10a/10b, 11a–c, 12a, 14a, 16d, 17a/b, 22a, 28a) counted separately.

## Definition of complete

The approved installation path passes a clean PostgreSQL replay, supported upgrades preserve data, the resulting schemas independently match expectations, and automated checks guard against recurrence.

## Safety

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
