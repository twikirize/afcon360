# Reconciliation Contract — Manifesto Part XIX Register

**Author:**      Human (Obed)
**Date:**        2026-09-24
**Scope:**       docs/transport/00-MANIFESTO-EDITION-2.0.md, Part XIX only
**Basis:**       §18.1, docs/transport/02-OPERATING-SYSTEM.md

## Rows to transcribe

| Row | From    | To   | Source of truth |
|-----|---------|------|-----------------|
| 2.2 | PENDING | PASS | Fix-2.2-record.md — PASS attested in ## Gate section (no Status: header line; Gate section is authoritative) |
| 2.3 | PENDING | PASS | Fix-2.3-record.md — Status: PASS; commit f1a3a82 in HEAD |
| 2.4 | PENDING | PASS | Fix-2.4-record.md — Status: PASS |
| 2.5 | PENDING | PASS | Fix-2.5-record.md — Status: PASS (subject to human confirmation); this directive is the confirmation |
| 2.6 | PENDING | PASS | Fix-2.6-record.md — Status: PASS (subject to human confirmation); this directive is the confirmation |

## Rows to leave unchanged

1.1 (already PASS) · 1.2 · 1.3 · 1.4 · 1.5 · 2.1 · 3.1–3.6

## Evidence column values

- 2.2 — "Fix-2.2-record.md (Gate: PASS)"
- 2.3 — "f1a3a82; Fix-2.3-record.md"
- 2.4 — "Fix-2.4-record.md"
- 2.5 — "Fix-2.5-record.md"
- 2.6 — "Fix-2.6-record.md"

Do not invent commit hashes or artifact paths.

## Numbering note (insert verbatim under the Part XIX table)

> **Numbering reconciliation (2026-09-24):** The implemented Fix IDs
> 2.4, 2.5, and 2.6 do not match their original Part VII listing.
> Implementation order was:
> - 2.4 = tile provider migration
> - 2.5 = booking request points extraction
> - 2.6 = public endpoint rate limiting
>
> Part VII retains its original listing for historical reference.
> This note reconciles the two. Future Fix IDs will follow
> implementation order.

## Reviewer's note (insert verbatim under the numbering note)

> **Reviewer's note (2026-09-24):** The book's Tier 2 register
> originally listed six items. Five are now closed on disk:
> 2.2, 2.3, 2.4, 2.5, 2.6. Only 2.1 (geographic demand-aware
> surge) remains open, with no contract on disk. An earlier
> reconciliation attempt marked 2.3 as "not closed in this fix
> programme"; this was incorrect — Fix-2.3-record.md on disk records
> Status: PASS, commit f1a3a82, dated 2026-09-22, with evidence from
> test_reservation_callback_idempotency.py showing 3 passed. The
> register update below reflects the correct state.

## Proof of Done

Run and paste raw:

1. `git diff -- docs/transport/00-MANIFESTO-EDITION-2.0.md`
2. `git status --short -- docs/transport/00-MANIFESTO-EDITION-2.0.md`
3. `git status --short -- docs/transport/fixes/RECONCILIATION-Part-XIX-contract.md`

## Human review checklist

- [ ] Contract file created verbatim
- [ ] Five rows show PASS in Part XIX
- [ ] Evidence column populated per above
- [ ] Two notes inserted verbatim
- [ ] No other row, section, or file changed
- [ ] No commit made by agent
