# AFCON360 Agent Context Index

`AGENTS.md` is the repository constitution. This index is only a routing aid:
it tells workers which additional context to load for a task. It does not
replace or override the constitution, specifications, or approved graph-node
scope.

## Fast route

| Task class | Load first | Verification |
| --- | --- | --- |
| `TRIVIAL` | Target file and applicable file-pattern rule | Focused diff, syntax, or content check |
| `LOCAL` | Target subtree, local rule, and relevant tests | Targeted test or focused check |
| `BEHAVIORAL` | `README.md`, governing specification, implementation, and tests | Positive, negative, and boundary paths |
| `ARCHITECTURAL` | `README.md`, ownership boundaries, ADR/specification, affected modules, and tests | Cross-module contract and integration evidence |
| `HIGH_RISK` | Specification, current implementation, invariants, authorization, failure paths, audit/compliance guidance, and tests | Full relevant evidence; never memory alone |

## Domain routes

- **Identity, users, organisations, roles:** `app/Documentation/IDENTITY_POLICIES.md`,
  `app/identity/`, `app/auth/`, and applicable identity rules.
- **Wallet, payments, balances, escrow:** wallet workflow and rules,
  `app/wallet/`, `app/audit/`, `app/compliance/`, and relevant task tests.
  Do not modify `app/wallet/models/` without explicit authorization.
- **Schema, models, or migrations:** `DATABASE_SCALABILITY_ROADMAP.md`,
  `docs/POSTGRES_TESTING_CONTRACT.md`, model registration guidance, and
  migration state. Migration creation/application remains user-controlled.
- **Frontend templates, HTML, or CSS:** the affected template/style subtree and
  `static/MOBILE_OPTIMIZATION.md` only when the documented scope changes.
- **Events, accommodation, transport, or other modules:** the affected
  module's documentation, specification, rules, and tests; do not load
  unrelated module material.
- **Async tasks:** `.junie/workflows/new-async-task.md`, the affected module
  rules, and task tests; verify idempotency and retry behavior.
- **Reports and handoffs:** `.junie/workflows/post-change-report.md` and
  `rules/agent-governance-rules.md`.

## Durable knowledge route

Do not create a memory, `BACKLOG.md`, or documentation update for a routine
edit. Update durable project knowledge only when the task creates or changes a
reusable decision, invariant, ownership boundary, hazard, unresolved handoff,
required approval, or specification.

## Escalation route

Stop and return `NEEDS_DECISION` when the required specification, authority,
ownership, or public-contract decision is missing or contradictory. Return
`BLOCKED` when required evidence or infrastructure cannot be obtained. Do not
expand a low-cost route silently when inspection reveals security, identity,
financial, migration, compliance, or cross-module consequences.