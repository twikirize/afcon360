# AFCON360 Agent Governance Rules

This file contains reusable execution procedures. The repository root
`AGENTS.md` remains the authority for architecture, security, identity,
financial, ownership, and migration invariants.

Use `rules/agent-context-index.md` as the first routing lookup after task
classification. It identifies the smallest relevant context set; it is not a
replacement for current-code inspection on behavioral or high-risk work.

## Adaptive execution

Classify the task before loading broad context:

- `TRIVIAL`: documentation, wording, formatting, or isolated presentation edits.
- `LOCAL`: one-module implementation with no cross-module contract change.
- `BEHAVIORAL`: business rules, lifecycle, authorization, or observable API/UI behavior.
- `ARCHITECTURAL`: cross-module, ownership, schema, or public-contract work.
- `HIGH_RISK`: wallet, identity, authentication, authorization, security,
  compliance, migrations, or destructive operations.

Use project memory and the task graph to route context, not as proof of current
implementation. Load only the affected subtree, applicable rule, workflow,
skill, specification, ADR, and tests. Read `README.md` when the task is
behavioral, architectural, high-risk, or otherwise unfamiliar; it is not a
mandatory full read for a trivial isolated edit.

## Proportional work

- `TRIVIAL`: inspect the target, make the minimal change, and perform a focused
  diff or syntax check. Do not run unrelated tests or update memory.
- `LOCAL`: inspect the affected module, implement narrowly, and run targeted
  verification.
- `BEHAVIORAL`/`ARCHITECTURAL`: establish the governing specification, inspect
  implementation and tests, verify negative paths and boundaries, then report
  evidence.
- `HIGH_RISK`: verify current code against specifications, invariants, tests,
  ownership, authorization, failure/recovery behavior, and audit requirements.

Escalate if the change reveals missing authority, contradictory requirements,
scope expansion, or a security, financial, identity, migration, or public
contract consequence not authorized by the current node.

## Durable knowledge

Do not update memory, `BACKLOG.md`, or project documentation for routine edits.
Update them only when durable knowledge changes: a reusable decision,
invariant, ownership boundary, hazard, unresolved handoff, required approval,
or specification. Frontend documentation changes are conditional on an actual
HTML/Jinja/CSS change affecting its documented scope.

## Completion routing

Use the concise report for `TRIVIAL` and `LOCAL` work. Use the full root
completion contract for `BEHAVIORAL`, `ARCHITECTURAL`, and `HIGH_RISK` work.
Every report states status, files changed, behavior, verification, migration
impact, manual steps, risks, and deferred work when applicable.

## References

- Domain invariants: `AGENTS.md`, module specifications, and ADRs.
- Context routing: `rules/agent-context-index.md`.
- Reusable procedures: `.junie/workflows/` and applicable agent workflows.
- File-pattern restrictions: `rules/` and `.junie/rules/`.
- Specialized knowledge: `.junie/skills/` and other agent skill directories.
- PostgreSQL testing: `docs/POSTGRES_TESTING_CONTRACT.md`.
- Identity: `app/Documentation/IDENTITY_POLICIES.md`.
- Schema policy: `DATABASE_SCALABILITY_ROADMAP.md`.