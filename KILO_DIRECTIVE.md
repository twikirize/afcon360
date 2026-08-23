# Kilo Worker Adapter

The repository root `AGENTS.md` is authoritative for Kilo, Junie, Aider, Kiro,
and every future worker. This file is only a Kilo execution adapter; it must
not redefine identity, security, database, wallet, migration, graph, or
ownership rules.

## Task-adaptive execution

1. Classify the task as `TRIVIAL`, `LOCAL`, `BEHAVIORAL`, `ARCHITECTURAL`, or
   `HIGH_RISK` using `AGENTS.md`.
2. Use memory only to route the smallest relevant context; do not treat it as
   proof of current code.
3. Load only the applicable Kilo rules, skills, workflows, specifications, and
   current graph-node requirements.
4. Inspect the affected files before editing and stay within authorized scope.
5. Verify proportionally: focused diff/check for trivial work, targeted tests
   for local work, and full relevant evidence for behavioral or high-risk work.
6. Update durable memory or `BACKLOG.md` only when reusable knowledge or
   incomplete handoff work actually changed.
7. Return the completion report required by the root constitution.

Internal `id` values remain private; UI-visible, URL, and external identifiers
must use `public_id`. For identity, wallet, migration, security, compliance,
or public-contract work, memory never replaces current-code, specification,
and test verification.

## Kilo-specific context

When the authorized task concerns the dashboard restructuring effort, consult
`DASHBOARD_RESTRUCTURING_PLAN.md` and implement only its explicitly authorized
phase. Do not check off tasks, append implementation-log entries, or wait for
phase verification unless that work is part of the current node or the user
explicitly requests it. Apply the repository's conditional frontend-document
policy; do not create no-op updates.
