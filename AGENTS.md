# AFCON360 Agent Constitution

**Status:** AUTHORITATIVE
**Scope:** Entire repository
**Audience:** All AI agents, automation, developers, and code-generation tools
**Last Updated:** August 2026

## Fast routing rule

This constitution is authoritative, but agents must not load every section for
every task. Classify the task first, use memory to route the relevant sections,
and inspect only the affected subtree and applicable references. `TRIVIAL`
work should normally need only the target and a focused check; `LOCAL` work
needs targeted implementation evidence; `BEHAVIORAL`, `ARCHITECTURAL`, and
`HIGH_RISK` work require progressively deeper specification, code, and test
verification. This routing rule does not weaken any security, identity,
financial, migration, or public-contract invariant.

The root `AGENTS.md` defines how an agent operates. It does not attempt to
contain every fact about the application. Detailed knowledge lives in the
referenced specifications, ADRs, module documentation, skills, workflows,
rules, and the code itself.

Agent-specific rules, skills, and workflows may extend this document, but they
MUST NOT contradict it.

When an agent-specific instruction conflicts with this document, this document
wins.

---

# 0. Purpose

This document is the authoritative repository-level contract for all agents
working on AFCON360.

It defines:

- architectural invariants
- ownership boundaries
- safety constraints
- identity rules
- database rules
- financial rules
- testing requirements
- documentation requirements
- agent behavior
- graph behavior
- context-loading behavior
- memory behavior
- handoff requirements
- deferred-work requirements
- tool-adapter boundaries

It does NOT attempt to contain every workflow or implementation detail.

Detailed domain knowledge belongs in the appropriate:

- specifications
- ADRs
- module documentation
- rules
- skills
- workflows
- implementation
- tests

Reusable execution procedures are distributed under `rules/`, `.junie/rules/`,
agent skills, and workflows. Agents must route to those resources rather than
loading unrelated procedures. The shared adaptive procedure is
`rules/agent-governance-rules.md`; this constitution retains only repository
authority, non-delegable invariants, ownership boundaries, and escalation
requirements.

---

# 1. Authority & Precedence

When instructions conflict, use this order:

1. Explicit current-task user instruction — defines requested scope and
   objective
2. Approved behavioral specification, ADR, or formal contract
3. Repository root `AGENTS.md`
4. Current graph-node or task contract
5. Applicable module/domain rules
6. Applicable workflow
7. Applicable skill
8. Tool-specific agent instructions
9. Existing implementation
10. Existing tests
11. Agent inference

A user instruction determines what the user wants the agent to do, but does not
silently rewrite an approved specification, security invariant, financial
control, or architectural decision.

If the user intentionally wants to change such a constraint, treat that as a
specification, architecture, security, financial, or policy change requiring
the appropriate decision process. Do not silently override the governing rule.

A lower-level instruction MUST NOT silently violate a higher-level security,
financial, architectural, identity, authorization, or public-contract
constraint.

Existing code and passing tests are evidence of current behavior. They are NOT
automatic authorization to preserve or extend behavior that conflicts with an
approved specification or architectural decision.

---

# 2. Agent Operating Model

AFCON360 uses a graph-based engineering workflow.

AI coding tools are workers inside that workflow, not independent owners of:

- product requirements
- business rules
- architecture
- ownership boundaries
- financial rules
- security boundaries
- public contracts
- graph transitions

The engineering system is conceptually:

    User / Product Decision
             |
             v
        Agent Graph
             |
             v
        Current Node
             |
       +-----+-----+
       |           |
     Junie       Kilo
     Worker     Worker
       |           |
       +-----+-----+
             |
             v
      Repository State

Workers execute the current authorized node.

They do not independently redefine the product or architecture.

---

## 2.1 Graph Nodes

Every substantial engineering task should be treated as a graph node.

A node may represent:

- exploration
- audit
- analysis
- specification
- planning
- implementation
- testing
- verification
- review
- debugging
- migration review
- release preparation

Where a graph node exists, establish:

- node ID
- objective
- authorized scope
- exclusions
- inputs
- expected outputs
- constraints
- required evidence
- verification requirements
- completion criteria

The current node determines what the worker may do.

---

## 2.2 Node Modes

### `EXPLORER`

Inspect and map the relevant system.

Do not modify application behavior unless explicitly authorized.

### `AUDIT`

Inspect, analyze, test, compare, classify, and report.

An audit is read-only unless the node contract explicitly grants
implementation authority.

An audit agent MUST NOT silently:

- fix findings
- modify application code
- modify tests
- modify migrations
- change schemas
- refactor adjacent code

An audit may produce:

- evidence reports
- findings
- classifications
- recommendations
- proposed next-node definitions

### `SPECIFICATION`

Formalize intended behavior and resolve ambiguities.

Do not silently implement the specification.

### `PLANNER`

Determine implementation steps, dependencies, risks, verification strategy,
and affected files.

Do not modify implementation unless explicitly authorized.

### `IMPLEMENTATION`

Modify approved code, add required tests, and verify the result.

Do not redesign unrelated architecture.

### `VERIFIER`

Inspect, test, compare implementation against specification, and report
evidence.

A verification node may discover defects but MUST NOT silently remediate them
unless remediation is explicitly included in the node contract.

### `DIAGNOSTICIAN`

Investigate failures and identify root causes.

Do not broaden into unrelated fixes.

### `REVIEWER`

Review the implementation against its specification, node contract,
architecture, security rules, and verification evidence.

### `MIGRATION_REVIEWER`

Review schema state, model metadata, migration requirements, migration history,
and migration safety.

Workers may recommend the next graph node.

Workers do not own graph transitions unless explicitly instructed.

---

# 3. Task Classification & Adaptive Execution

Before broad inspection, classify the task by scope and risk.

## 3.1 Task Classes

### `TRIVIAL`

Examples:

- documentation wording
- formatting
- comments
- isolated presentation-only changes

Process:

- inspect target
- make minimal change
- perform focused verification

Do not load the entire project context.

### `LOCAL`

A single-file or tightly scoped code change with no cross-module contract.

Process:

- identify affected module
- load local rules
- inspect affected implementation
- make minimal change
- run targeted verification

### `BEHAVIORAL`

A change involving:

- business rules
- lifecycle
- authorization
- permissions
- API behavior
- state transitions
- ownership
- externally observable behavior

Process:

- identify governing specification
- inspect affected implementation
- inspect relevant tests
- inspect ownership boundaries
- implement only after the behavior is understood and authorized
- verify transitions and negative cases

### `ARCHITECTURAL`

Cross-module, schema, ownership, public-contract, or architectural work.

Process:

- establish dependencies
- establish invariants
- identify ownership boundaries
- identify affected contracts
- establish required specifications
- plan before implementation
- verify cross-module effects

### `HIGH_RISK`

Includes:

- wallet
- identity
- authentication
- authorization
- security
- compliance
- financial operations
- migrations
- destructive operations
- public-contract changes

Use the complete evidence and verification process.

Memory may reduce exploration but NEVER replaces:

- current-code inspection
- specification inspection
- invariant verification
- test verification

---

# 3.2 Progressive Context Loading

Context is loaded progressively, not indiscriminately.

Use:

    task → graph node → memory/routing → affected module → applicable rules
    → applicable skills/workflows/specifications → current code/tests
    → proportional verification

Start with:

1. task description
2. current graph node
3. relevant repository memory/index if available
4. affected module
5. risk classification

Then load only:

- relevant rules
- relevant skills
- relevant workflows
- relevant ADRs
- relevant specifications
- relevant documentation

Expand context only when evidence reveals:

- dependency
- contradiction
- ownership boundary
- architectural consequence
- security concern
- financial consequence
- public-contract impact

DO NOT load every skill, workflow, ADR, historical report, or module document
merely because it exists.

---

# 3.3 Minimal Execution Principle

Agents MUST prefer the smallest safe inspection and implementation path that
can establish correctness.

Agents SHOULD NOT:

- scan the entire repository for a local task
- load unrelated skills
- load unrelated workflows
- read historical reports that cannot affect the decision
- run the entire test suite for an isolated change unless required
- perform broad refactoring merely because related code is imperfect
- repeatedly inspect the same files without new evidence

Verification must be proportional to:

- task class
- risk
- scope
- changed behavior
- affected contracts

The objective is:

    minimum necessary context
    +
    minimum necessary inspection
    +
    minimum necessary implementation
    +
    sufficient verification

Safety MUST NOT be sacrificed for token or time savings.

---

# 4. Change Authority

Before modifying anything, the agent MUST establish:

- active graph node
- node type
- whether modification is authorized
- authorized files/subtrees
- excluded files/subtrees
- governing specifications
- required verification
- applicable risks

The existence of a defect does NOT itself grant permission to fix it.

The existence of a convenient refactoring opportunity does NOT grant
permission to perform it.

The existence of a failing test does NOT automatically authorize changing the
test or implementation.

The existence of related work does NOT authorize scope expansion.

---

# 5. Scope Discipline & Controlled Helpfulness

Agents MUST implement ONLY the approved change.

Do not perform unrelated:

- refactors
- renames
- architecture migrations
- dependency upgrades
- formatting sweeps
- test rewrites
- database cleanup
- public API changes

unless explicitly authorized.

When exploring a module, prefer the relevant subtree.

---

## 5.1 Scope Expansion

If implementation reveals a dependency outside the authorized scope, the agent
must choose one:

1. Resolve it only if the current node explicitly permits dependency changes.
2. Record it as deferred work.
3. Stop with `NEEDS_DECISION` if the dependency changes:
   - architecture
   - ownership
   - security
   - financial behavior
   - public contracts
   - specification

Agents MUST NOT silently expand scope because doing so appears technically
convenient.

---

# 6. Specification Law

AFCON360 behavior MUST be specified before implementation whenever a change
introduces or alters:

- business rules
- invariants
- workflows
- lifecycle
- state transitions
- permission boundaries
- ownership rules
- financial guarantees
- compliance obligations
- externally observable contracts

Before implementation, establish:

- affected entities
- state variables
- inputs
- outputs
- invariants
- failure conditions
- valid transitions
- ownership
- authority
- initiator
- approver
- rejector
- retry authority
- reversal authority
- observation/read authority

Resolve conflicting interpretations before implementation.

Do NOT use:

- legacy behavior
- convenience
- agent preference
- passing tests
- implementation simplicity

as implicit authorization.

If the specification is:

- missing
- contradictory
- ambiguous
- materially incomplete

STOP and return:

    STATUS: NEEDS_DECISION

Relevant specifications should be linked from owning module documentation.

Cross-module rules should be documented appropriately in repository
documentation.

Tests should cover:

- transitions
- invariants
- authorization
- negative cases
- important failure paths

---

# 7. Evidence-First Engineering

For non-trivial work, maintain the following evidence chain:

    Requirement
        ↓
    Specification
        ↓
    Current implementation
        ↓
    Current tests
        ↓
    Gap
        ↓
    Proposed change
        ↓
    Verification

Do not implement from assumptions when repository evidence is available.

Every completed graph node must provide evidence appropriate to its purpose.

Evidence may include:

- files inspected
- specifications reviewed
- relevant models
- relevant routes
- relevant services
- relevant tests
- commands executed
- test results
- contract checks
- invariant checks
- risks
- unresolved assumptions
- deferred work

Do not report success merely because code was written.

---

# 8. Completion Status

Use one of these statuses:

### `PASS`

Authorized work is complete and required verification passed.

### `PARTIAL`

Some authorized work or required verification remains incomplete.

### `BLOCKED`

Work cannot proceed because a required:

- dependency
- environment
- file
- migration state
- test
- service
- evidence

cannot be obtained or verified.

### `NEEDS_DECISION`

A human/product/architecture/security/finance/compliance decision is required.

### `FAIL`

The implementation or verification did not satisfy the node contract.

---

# 9. Tests Are Evidence, Not Specification

Passing tests establish evidence about current behavior.

They do NOT automatically establish that the behavior is correct.

If tests conflict with an approved specification:

1. identify the conflict
2. report the conflict
3. determine whether the specification or tests require an approved change
4. do not silently alter behavior merely to satisfy tests

Similarly, do not change tests merely to make a new implementation pass unless the
test itself is demonstrably inconsistent with the approved behavior.

---

# 10. Memory & Knowledge Policy

## 10.1 Memory as a Routing Cache

Repository memory, graph state, prior reports, and agent-maintained summaries
are routing and context aids.

They are NOT authoritative evidence of current implementation state.

Use this model:

    Memory = routing/index
    Current repository = implementation truth
    Tests = behavioral evidence
    Specifications/ADRs = intended authority

Agents SHOULD consult relevant memory before expensive exploration when it can
identify:

- affected files
- previous decisions
- known constraints
- unresolved work
- previous verification results
- relevant graph nodes
- likely ownership boundaries

For `TRIVIAL` and `LOCAL` tasks, relevant memory may substantially reduce
exploration.

For `BEHAVIORAL`, `ARCHITECTURAL`, and `HIGH_RISK` tasks, memory may narrow the
search but MUST NOT replace verification of current source and governing
contracts.

Memory MUST NOT be treated as proof that a file or behavior is unchanged.

---

## 10.2 Memory Updates

Do NOT update memory after every task.

Update durable project memory, ADRs, specifications, or `BACKLOG.md` only when
the task:

- creates reusable knowledge
- changes an invariant
- resolves an architectural decision
- discovers a reusable constraint
- changes ownership
- resolves deferred work
- creates important operational knowledge
- changes a durable workflow
- establishes a significant implementation decision

Do NOT create memory entries for:

- routine implementation details
- temporary debugging observations
- one-off commands
- information already represented clearly by code
- trivial documentation edits

The goal is to make memory more useful over time, not larger after every task.

---

# 11. Deferred Work

All identified but incomplete work that belongs in the system MUST be recorded
in:

    BACKLOG.md

Do not silently leave unfinished work in conversation history.

Record work when:

- requested but out of scope
- partially implemented
- blocked
- awaiting migration
- awaiting another team
- awaiting external dependency
- awaiting security review
- awaiting finance/compliance review
- explicitly deferred

Reference concrete:

- files
- models
- routes
- services
- specifications
- graph nodes

Do NOT delete historical backlog entries.

Resolved items should be marked:

    Status: Done
    Resolved: YYYY-MM-DD

---

# 11.5 Architecture at a Glance

This section is a productivity map, not a new contract. Every rule below is
already binding elsewhere in this document; read the cited section for the
authoritative wording.

## 11.5.1 Entry point and factory

- `app.create_app(config_object=None)` in `app/__init__.py` is the Flask
  application factory. It is large (~1800 lines) and uses deep lazy loading
  to keep startup time low. Do not flatten the lazy imports without cause.
- `app.py` is the development launcher (`python app.py`); it calls
  `create_app()` and wires a few template filters and context processors.
- Blueprints are registered centrally inside `create_app()`. Routes inside
  gated modules are wrapped with the module guard (see §28 — Module
  Toggles). A disabled module must fail safely without crashing unrelated
  modules or creating partial state.

## 11.5.2 Model registration

- All models inherit `app.models.base.BaseModel` (or an approved protected
  variant) — see §13.
- Models are registered via `app/core/model_registry.py`, which
  `create_app()` invokes during startup. A model that is not registered is
  incomplete (see §19.2). New models must also be exported from the
  relevant domain `__init__.py` when other modules import them.

## 11.5.3 Configuration (layered environment)

- `app/config.py:_load_env()` loads `.env` first, then `.env.{APP_ENV}`.
  `APP_ENV` selects the overlay:

    local  → `.env` + `.env.local`
    docker → `.env` + `.env.docker`
    prod   → `.env` + `.env.prod`

- `get_config()` returns the matching config class. Never print or log
  secret values (see §25). The `ENCRYPTION_KEY` guard runs inside
  `create_app()` only after the overlay is loaded — do not move it back to
  module level.

## 11.5.4 Async, cache, and sessions

- Celery is exposed as `app.celery_app`. Worker and beat handle webhooks,
  media processing, notifications, reconciliation, and scheduled jobs
  (see §37 for run commands).
- Redis is used for caching (Flask-Caching), sessions (Flask-Session),
  rate limiting (Flask-Limiter), and the Celery broker/backend. Set
  `DISABLE_REDIS=true` only for a limited local run; gated features must
  degrade, not crash (see §28).

## 11.5.5 Testing

- The canonical pytest runner is `tests/conftest.py`; the root `conftest.py`
  only filters collection to the `tests/` directory. Plain `pytest`
  auto-builds the schema via `db.create_all()` + `stamp head` (see §21.1).
- PostgreSQL is the only supported application and test database. SQLite,
  in-memory fallbacks, raw SQL strings, and test-time schema creation or
  repair are not supported (see §20, §21).

## 11.5.6 Module ownership and cross-module contracts

- See §17 for ownership boundaries and the README "Modules" table for the
  per-domain responsibility map.
- Cross-module work uses explicit contracts, e.g.
  `app/accommodation/AFCON360_SEAMLESS_BOOKING_SPEC.md` and
  `app/events/events.md`. A module must continue to function when an
  optional integration is unavailable (see §17, §18).

---

# 11.6 Distilled Quick Reference

Productivity pointers distilled from the project's agent skills and rules
(`.junie/`, `.kiro/steering/`, `.windsurf/`). These repeat no invariant;
they name the concrete utilities, files, and gotchas an agent needs fast.
Authoritative wording stays in the cited section.

## 11.6.1 Standard utilities (prefer over custom code)

- `app/utils/id_guard.py` — prevents incorrect internal-ID assignment/exposure
- `app/utils/module_guard.py` — `@module_required('name')` route guard (§28)
- `app/utils/idempotency.py` — idempotency keys for wallet/booking confirms
  (§18.1)
- `app/utils/validators.py` — common data-validation patterns
- `app/utils/audit.py` — log sensitive actions to the audit trail (§29)

## 11.6.2 Auth decorators and key files

- Decorators: `@login_required`, `@admin_required`, `@require_role('x')`,
  `@owner_only`; runtime checks `current_user.has_role(...)` and
  `current_user.is_super_admin`.
- Files: `app/auth/decorators.py`, `app/auth/roles.py`, `app/auth/policy.py`,
  `app/auth/delegation.py`, `app/auth/ownership.py`.
- The full ranked role hierarchy is NOT in this constitution — see
  `app/Documentation/IDENTITY_POLICIES.md` (§18.2).

## 11.6.3 Migration quick reference (Alembic gotchas)

§20 is authoritative. Concrete fixes:

| Problem | Fix |
|---|---|
| Multiple heads | `flask db merge heads -m "merge_<date>"` |
| Revision ID too long | set `revision = 'short_id'` (< 32 chars — Postgres identifier limit) |
| Create a revision | `python scripts/create_migration.py "<desc>"` (keeps IDs short) |
| Migration fails / stuck state | `flask db current` / `flask db heads`; `flask db stamp <head_id>` only after fixing the root cause |
| CHECK-constraint drift (Alembic blind spot — see §20.2) | `python scripts/sync_check_constraints.py --dry-run` → `--accept-model-truth --message "<desc>"` → `flask db upgrade` |

`flask db migrate` does NOT detect CHECK-constraint changes. Any work that
adds, removes, or edits a `CheckConstraint` (named `ck_*`), including
enum-driven ones like `app/notifications/models.py`, MUST go through
`scripts/sync_check_constraints.py`. See §20.2.

Never patch a migration file as a workaround — fix the model/source first.

## 11.6.4 Wallet sub-architecture map

§18.1 is authoritative. File layout:

- `app/wallet/models/` — ledger and account models (DO NOT modify without
  authorization)
- `app/wallet/services/` — business logic layer
- `app/wallet/repositories/` — data access layer
- `app/wallet/payments/` — gateway integrations (Flutterwave, Paystack,
  Mobile Money MTN/Airtel, PayPal, Alipay, WeChat Pay, Visa) — match the
  existing provider pattern, do not invent a new one
- `app/wallet/api/` — wallet API endpoints
- `app/wallet/middleware/` — wallet-specific middleware
- `app/wallet/routes_pin.py` — PIN lockout logic (do not touch unless asked)
- Async: `app/tasks/webhook_processor.py` (webhooks),
  `app/tasks/reconcile.py` (reconciliation) — extra care on changes
- FX rates UI: `templates/wallet/fx_rates.html`

## 11.6.5 Forensic audit and compliance concrete

§29 is authoritative. Concrete handles:

- Service: `app/audit/forensic_audit.py` — `log_attempt()`,
  `log_completion()`, `log_blocked()`, `get_audit_timeline()`,
  `get_pending_reviews()`, `get_suspicious_patterns()`.
- Audit columns: `attempted_at`, `status`, `reviewed_by_user_id`,
  `reviewed_at`, `review_notes`, `ip_address`, `user_agent`, `session_id`,
  `correlation_id`, `risk_score`.
- Schedules: suspicious-pattern detection hourly; stale-review escalation
  every 4 hours; daily compliance reports (Celery).
- Thresholds: FIA Uganda — transactions > UGX 20M must be flagged; Bank of
  Uganda — KYC timelines must be enforced.
- `app/compliance/aml_service.py` changes require compliance review — flag,
  do not proceed silently.
- Known issue: `owner_audit_logs.is_deleted` may be absent — wrap queries on
  that table in try/except.

## 11.6.6 Testing extras

§21 is authoritative. Additional handles:

- Flags: `pytest -k "impersonation"` (filter by name),
  `pytest --cov=app tests/` (coverage), `pytest --tb=short` (shorter
  tracebacks).
- Reset/rebuild: `python scripts/reset_test_db.py`,
  `python scripts/setup_test_db_schema.py`.
- Role/permission tests use `tests/setup_owner.py` helpers.
- Mock external payment gateways — never call real Flutterwave/Paystack.
- Mock Redis in unit tests — do not test against live Redis.
- Wallet tests use isolated DB transactions and rollback after each test.

## 11.6.7 Code conventions (crisp)

Only items not already stated elsewhere; §22 covers frontend.

- Log with `current_app.logger` — never `print()`.
- Use absolute imports from the project root
  (e.g. `from app.auth.models import User`).
- Check existing `backref` names before adding relationships — duplicate
  backrefs crash on startup. Never rename an existing `backref`.
- A `@property` must not shadow a Column name — use `_flag` / `_status` /
  `_computed` suffixes.
- All new routes need CSRF protection (Flask-WTF) unless `@csrf.exempt` is
  explicitly justified.
- Use `db.session.rollback()` explicitly in route error handlers.
- Extend `base.html` for user-facing pages; use `url_for()` (never hardcode
  URLs); include `{{ form.hidden_tag() }}` / CSRF token in forms.

## 11.6.8 Shell and environment

- The default project terminal is PowerShell on Windows — chain with `;`,
  not `&&`. CodeBuddy Code's Bash tool runs Git Bash and accepts `&&`; match
  the shell you are actually running.
- Mind CRLF vs LF, especially in `docker-entrypoint.sh`.
- Activate the venv with `.venv\Scripts\Activate.ps1` (PowerShell) or
  `source .venv/bin/activate` (bash).

## 11.6.9 Context-pollution ignore list

Do not read unless explicitly needed:

    **/__pycache__/, **/.venv/, **/backups_today/, **/model_backups/,
    **/templates_backup/, **/flask_session/, **/*.pyc, **/node_modules/,
    backup_*.json, *.backup,
    migrations/versions/*.py (unless reviewing schema history)

## 11.6.10 Standard workflow checklists

Reusable procedural checklists live in `.junie/workflows/` and
`.windsurf/workflows/`. Consult the matching one before common tasks:

- `add-endpoint` — scaffold an API route (dual ID, role check, module guard)
- `add-model` — scaffold a model (BaseModel, dual ID, soft delete, registry)
- `db-migration` — safe Alembic protocol (single head, short IDs, propose only)
- `new-async-task` — scaffold a Celery task (idempotency, retry, JSON
  serialization)
- `wallet-change-review` — pre-flight checklist for `app/wallet` changes
- `post-change-report` — end-of-task report + quality checklist (§39)

---

# 12. Core Architectural Invariants

These rules are non-negotiable unless the governing architecture/specification is
explicitly changed.

---

## 12.1 Dual ID System

Every database entity uses two identifiers:

- `id` — internal `BigInteger`
- `public_id` — external UUID/approved public identifier representation

### Internal ID

Used only for:

- database relations
- foreign keys
- joins
- persistence

NEVER expose it externally.

### Public ID

Used for:

- APIs
- URLs
- external references
- human-visible identifiers
- approved external identity operations

### Rules

- Internal foreign keys use `id`.
- External input should resolve through `public_id`.
- API responses use `public_id`.
- URLs use `public_id`.
- Never serialize raw internal `id`.
- Never expose `user.id` in APIs, logs, or templates.
- Never introduce another public identifier scheme without approved
  specification.

**See:**

    /app/identity/models/user.py:25-45

---

# 13. Base Models

All models MUST inherit from:

    app.models.base.BaseModel

or an approved derived class such as:

    ProtectedModel

Do not introduce direct `db.Model` inheritance without explicit architectural
approval.

Verify repository conventions before treating any exception as intentional.

---

# 14. PostgreSQL ENUM Policy

Do NOT introduce new PostgreSQL ENUM types.

Use:

- `String`
- application-level validation
- CHECK constraints where appropriate

Existing ENUM migrations must follow the approved expand-contract strategy.

**See:**

    DATABASE_SCALABILITY_ROADMAP.md

---

# 15. Property Naming Safety

Never define a Python `@property` with the same name as a SQLAlchemy
`Column`.

Use suffixes such as:

- `_flag`
- `_status`
- `_computed`

Example:

    @property
    def is_verified_status(self):
        return self.email_verified and self.phone_verified

---

# 16. Import Style

Use absolute imports from the project root.

Example:

    from app.identity.models.user import User
    from app.wallet.models.transaction import Transaction

Be especially careful with circular imports around:

- identity
- events
- accommodation
- wallet
- services
- model registration

Verify startup where appropriate:

    python -c "from app import create_app"

---

# 17. Ownership Boundaries

Cross-module operations MUST respect domain ownership.

A module MUST NOT silently become the owner of another module's domain state.

| Domain | Owns |
|---|---|
| Identity | Users, organisations, identity relationships |
| Auth | Authentication and session entry |
| Events | Events, registrations, event lifecycle |
| Accommodation | Properties, inventory, availability, reservations |
| Transport | Vehicles, drivers, routes, transport assignments |
| Wallet | Ledger, balances, financial transactions |
| KYC | Identity verification workflows |
| Compliance | Compliance rules and AML checks |
| Audit | Forensic audit records |

Cross-module operations MUST use explicit contracts.

Do not directly manipulate another module's internal state merely because the
database makes it technically possible.

---

# 18. High-Risk Areas

## 18.1 Wallet

The wallet is a high-risk financial subsystem.

Treat wallet changes as:

    CRITICAL

unless explicitly classified otherwise by the governing process.

Rules:

- Preserve double-entry accounting.
- Every debit must have a corresponding credit.
- Do not mutate balances outside the ledger model.
- Maintain idempotency.
- Preserve transaction integrity.
- Roll back failed database transactions.
- Preserve audit trails.
- Preserve reconciliation behavior.
- Do not modify `app/wallet/models/` without explicit authorization.
- Preserve compliance controls.
- Preserve transaction references and idempotency keys.

Wallet changes may require:

- compliance review
- financial review
- additional tests
- reconciliation verification

---

## 18.2 Identity, Roles & Personas

Identity and authorization rules are governed by the approved identity
specification and role/permission policy.

Agents MUST NOT infer authority from role names alone.

Where AFCON360 supports:

- multiple roles
- personas
- organizational contexts
- active-role switching
- user/organization context

authorization MUST respect the currently active authorized context.

Role changes must be audit-logged.

Owner cannot be:

- deleted
- impersonated
- self-modified

Super admin cannot modify:

- another super admin
- owner

Do not introduce, remove, reorder, merge, or reinterpret roles without an
approved identity/authorization specification.

The detailed role matrix belongs in identity documentation, not this
constitution.

---

# 19. Database Rules

## 19.1 PostgreSQL Requirement

PostgreSQL is the only supported production and test database.

Do NOT introduce:

- SQLite fallbacks
- in-memory persistence fixtures

---

## 19.2 Model Registration

When adding a model:

1. Inherit from `BaseModel` or approved derived class.
2. Define table/index/constraint requirements.
3. Register it in `app/core/model_registry.py`.
4. Export it from the relevant domain `__init__.py` when required.
5. Verify Alembic can detect it.

A model that is not correctly registered is incomplete.

**See:**

    app/core/model_registry.py
    app/__init__.py:579-580

---

## 19.3 Soft Delete

Where the model uses the standard soft-delete architecture, queries should
exclude deleted records.

Example:

    Model.query.filter(Model.is_deleted == False)

Use the repository's established soft-delete helper/query patterns where they
exist.

---

# 20. Migration Law

Schema changes are HIGH RISK.

Agents MUST NOT create, patch, or apply migrations without explicit
authorization.

Agents MAY inspect:

    flask db current
    flask db heads
    flask db history

Agents MAY NOT create/apply migrations unless explicitly authorized:

    flask db migrate
    flask db upgrade
    flask db downgrade
    flask db merge

The user controls migration execution.

Agents MAY:

- identify required schema changes
- inspect migration state
- inspect migration history
- verify model metadata
- propose exact commands

Before proposing a new migration:

1. inspect current migration state
2. run `flask db heads`
3. identify whether multiple heads exist
4. verify model registration
5. identify the intended schema delta
6. review affected constraints
7. propose commands without executing prohibited migration operations

Never patch generated migrations as a workaround for a model/source problem.

Known defect — missing baseline migration (RESOLVED):

- `ab6dd422c152_initial_schema` (down_revision=None) was the effective root of
  the migration graph but never created `users`, `events`, `accounts`,
  `transactions`, or `accommodation_properties`, so `flask db upgrade` could
  not build a database from scratch in ANY environment.
- RESOLVED: it has been retired to `migrations/_retired_versions/` and replaced
  by `migrations/versions/8a0deccce6f6_initial_full_schema_baseline.py` — a
  single root migration (`down_revision=None`) that builds the entire schema
  from the current SQLAlchemy models via `db.metadata.create_all()`, which
  resolves FK ordering (including circular dependencies) automatically.
- Verified: `flask db upgrade` from an EMPTY database now builds all 182
  tables including `users`/`events`/`accounts`/`transactions`/
  `accommodation_properties`, with `alembic_version` stamped at the new head
  `8a0deccce6f6`.
- The test environment still bootstraps via `db.create_all()` + `stamp head`
  (see §21.1 / `scripts/setup_test_db_schema.py` / `tests/conftest.py`); both
  paths use the same model metadata, so the resulting schema is identical.

## 20.2 CHECK-constraint sync (Alembic blind spot)

Alembic autogenerate (`flask db migrate`) does NOT detect CHECK-constraint
changes — adding, dropping, or editing a `CheckConstraint` in a model is
invisible to autogenerate. This is a hard Alembic limitation, not a bug.

The project ships `scripts/sync_check_constraints.py` to close that gap.
It compares SQLAlchemy model metadata (source of truth) against the live
PostgreSQL database and emits a normal Alembic migration that reconciles
them. It NEVER applies anything itself — it only writes a migration file
for review; the user runs `flask db upgrade`.

Any managed CHECK constraint has a name beginning `ck_`. Enum-driven
constraints are generated from the model's enum classes, e.g.
`app/notifications/models.py` builds `ck_notifications_type`,
`ck_notifications_channel`, `ck_notifications_module`,
`ck_notifications_status` from the `NotificationType` /
`NotificationChannel` / `NotificationModule` / `NotificationStatus`
enums. Adding a new enum value therefore changes a managed constraint and
requires a sync.

Agents MUST:

1. Treat any task that adds, removes, or edits a `CheckConstraint`
   (including enum-driven ones — a new enum value, a renamed enum value,
   or a removed enum value) as requiring the CHECK-constraint sync path,
   NOT `flask db migrate`.
2. Tell the user explicitly that Alembic will not detect this change and
   that the sync script must be run. Surface this the same way a pending
   schema migration is surfaced — do not let the change ship silently.
3. Propose (do not execute) the exact commands, in order:

       python scripts/sync_check_constraints.py --dry-run
       python scripts/sync_check_constraints.py --accept-model-truth --message "<desc>"
       # review the file written to migrations/versions/
       flask db upgrade

4. After the user runs `flask db upgrade`, recommend a verification run
   so the user can see the database is now in sync:

       python scripts/sync_check_constraints.py --dry-run

   The expected result is "No CHECK constraint migration required."

Agents MUST NOT run the sync script's migration-generation
(`--accept-model-truth`) or `flask db upgrade` themselves — the user
controls migration execution, same as §20.

When a CHECK-constraint change is pending or has been made in the model
but not yet synced to the DB, the task is not done. State this plainly to
the user, e.g. "model changed but the DB CHECK constraint has not been
synced yet — run the sync script (§20.2) before this is live."

A "representation-only" difference reported by the script (same
semantics, different SQL form — e.g. `= ANY(ARRAY[...])` vs `IN (...)`)
is NOT drift and needs no migration. Only `ADD` / `REPLACE` / `ORPHANED`
(with `--prune-db`) require a migration.

---

# 21. Testing Contract

PostgreSQL is the only supported database backend for application and
persistence tests.

Do NOT introduce:

- SQLite test fallbacks
- in-memory database fixtures

Tests should use:

- shared `TestingConfig`
- project pytest fixtures
- dedicated migration-managed `TEST_DATABASE_URL`

Tests must fail fast when:

- PostgreSQL is unavailable
- schema is stale
- required migrations are missing

Application and test code should use SQLAlchemy models/Core expressions rather
than handwritten SQL strings.

Direct SQL persistence tests are not supported.

## 21.1 Test Database Bootstrap (canonical, always-on)

The PostgreSQL test database is bootstrapped **automatically by `tests/conftest.py`**
every time `pytest` runs. Agents and developers MUST NOT perform any manual
migration step before running tests; plain `pytest` is sufficient and is the
only supported entry point.

`tests/conftest.py` is the **single canonical pytest runner** (the root
`conftest.py` only filters collection to `tests/`). The legacy root
`_conftest.py` was removed — it is a dead duplicate and must not be revived.

Why the test bootstrap uses `db.create_all()` + `stamp head` (and the
migration baseline is now correct):

- The migration history previously had a **missing baseline**:
  `ab6dd422c152_initial_schema` (down_revision=None) never created `users`,
  `events`, `accounts`, `transactions`, or `accommodation_properties`, so
  `flask db upgrade` from an empty database failed.
- **RESOLVED:** `ab6dd422c152_initial_schema` was retired to
  `migrations/_retired_versions/` and replaced by
  `migrations/versions/8a0deccce6f6_initial_full_schema_baseline.py` — a single
  root migration (`down_revision=None`) that builds the entire schema from the
  current models via `db.metadata.create_all()`, resolving FK ordering
  automatically. `flask db upgrade` from an EMPTY database now builds all 182
  tables in ANY environment (verified on a throwaway DB).
- The test bootstrap still uses `db.create_all()` + `stamp head` because it is
  fast, idempotent, and test-only. Both paths use the same model metadata, so
  the resulting schema is identical. For a fresh database in a NON-test
  environment, `flask db upgrade` is now the correct, supported path.

What `tests/conftest.py` does (test-only, sanctioned):

1. Creates the test database if it does not exist.
2. If the schema is incomplete (no `users` table), builds it from the current
   SQLAlchemy models via `db.create_all()`. This reflects model changes
   including `use_alter` foreign keys, and correctly defers circular FKs.
3. Stamps Alembic head so `tests/postgres_contract.py`'s check and any
   `flask db upgrade` treat the DB as fully migrated.
4. If the schema already exists, it is reused (fast path); no rebuild occurs.

Canonical commands:

    # Run the suite — conftest auto-builds/verifies the test DB:
    pytest

    # Force a clean rebuild of the test DB (drops + recreate + create_all + stamp):
    python scripts/setup_test_db_schema.py

Do NOT run `flask db upgrade` to provision the *test* database; `pytest`
does it via `db.create_all()` + `stamp head` (idempotent, test-only). If the
test DB is stale after a model/schema change, run
`scripts/setup_test_db_schema.py` (which drops and rebuilds) rather than
relying on migrations. For a fresh *non-test* database (new env, disaster
recovery), `flask db upgrade` from empty now builds the full schema via the
`8a0deccce6f6` baseline.

**See:**

    docs/POSTGRES_TESTING_CONTRACT.md
    scripts/setup_test_db_schema.py
    tests/postgres_contract.py
    tests/conftest.py

---

# 22. Frontend Rules

Frontend changes MUST preserve mobile-first behavior.

Requirements:

- no unintended horizontal overflow
- touch targets ≥44×44px
- responsive grids
- fluid typography using `clamp()`
- safe-area handling where required
- no inappropriate fixed widths
- no inline layout styles where prohibited

Templates:

- Use `{{ csrf_token() }}` for forms requiring CSRF protection.
- Preserve `?_pane=1` behavior where used.
- Avoid `overflow: hidden` on containers holding dropdowns unless safe.

---

## 22.1 JavaScript & CSP

Use external scripts where possible.

Do not use:

- inline event handlers
- unnecessary inline executable scripts

Inline executable scripts require the application's appropriate CSP nonce.

JSON-LD blocks must follow the application's CSP requirements.

---

## 22.2 Frontend Documentation

When HTML, Jinja, or CSS changes, assess:

    static/MOBILE_OPTIMIZATION.md

Update it when the frontend change affects its documented:

- file tree
- responsive behavior
- styling
- branding
- verification state
- isolation plan

A content-only change that does not affect documented scope does not require a
no-op documentation update.

---

# 23. Security Rules

Agents MUST:

- never expose internal database IDs
- validate ownership before returning sensitive data
- preserve authentication boundaries
- preserve authorization boundaries
- preserve CSRF protections
- preserve CSP requirements
- never commit secrets
- use database-safe/parameterized queries
- preserve idempotency for critical operations
- audit sensitive operations
- avoid weakening security controls for convenience

---

# 24. Environment & Project Stack

AFCON360's known project environment is:

- **OS:** Windows / PowerShell
- **Python:** 3.13.x
- **Backend:** Flask 3.1.2
- **Database ORM:** SQLAlchemy 2.0.44
- **Database:** PostgreSQL
- **Migrations:** Alembic / Flask-Migrate
- **Async:** Celery 5.4.0
- **Broker/cache:** Redis 7.1.0
- **Authentication:** Flask-Login
- **RBAC:** application role/permission system
- **Caching:** Flask-Caching + Redis
- **Rate Limiting:** Flask-Limiter + Redis
- **Validation:** Pydantic 2.10.0
- **Testing:** pytest 8.3.0

External services include:

- AWS S3/OCR
- Flutterwave
- Paystack
- PayPal
- NIRA
- OCI storage
- mobile money integrations
- other approved payment and verification providers

These values are maintained as project reference information.

---

## 24.1 Project Stack Freshness

Agents MUST NOT verify dependency versions on every task.

The stack information above should be periodically checked against the
repository's actual dependency configuration.

A stack-version review should normally occur approximately every **6 months**,
or earlier when:

- a dependency upgrade is intentionally performed
- a major environment change occurs
- a compatibility problem is discovered
- the project explicitly changes its supported versions

When a periodic review occurs, update this section and the `Last Updated`
metadata if the actual supported versions changed.

For ordinary feature work, agents may rely on this section without repeatedly
inspecting dependency files merely to confirm versions.

The goal is:

    current enough to be useful
    +
    stable enough to avoid unnecessary context cost

---

# 25. Environment Configuration

AFCON360 uses layered configuration.

Conceptually:

    .env
       ↓
    .env.{APP_ENV}
       ↓
    application configuration

Common environments include:

    APP_ENV=local
    APP_ENV=docker
    APP_ENV=prod

Key variables include:

    APP_ENV
    FLASK_ENV
    DATABASE_URL
    REDIS_URL
    ENCRYPTION_KEY
    DISABLE_REDIS

Do not expose secrets.

Do not inspect or print secret values merely for verification.

Encryption/configuration values must be loaded according to the application's
configuration lifecycle.

---

# 26. Async Tasks

Celery handles long-running and asynchronous operations such as:

- webhooks
- media processing
- reconciliation
- notifications
- scheduled operations

Important principles:

- idempotency
- retry safety
- application context
- transaction integrity
- bounded retries
- safe serialization
- correct task registration

Do not introduce non-idempotent retry behavior into financial operations.

---

# 27. Middleware & Request Lifecycle

The application may use middleware/hooks for:

- module toggles
- session lifecycle
- rate limiting
- security headers
- ID guard validation

Do not remove or bypass existing middleware protections without authorization.

Module toggles must continue to prevent disabled modules from causing unrelated
parts of the application to fail.

---

# 28. Module Toggle System

Modules may be enabled or disabled at runtime.

Examples include:

- events
- accommodation
- transport
- wallet
- tourism
- tournament

Use the established module guard:

    @module_required('module_name')

State is stored through the application's system configuration/toggle system.

ALWAYS preserve existing module guards unless explicitly instructed otherwise.

New routes within gated modules must inherit the applicable module guard.

Disabled modules should fail safely without crashing unrelated modules.

---

# 29. Forensic Audit & Compliance

Sensitive operations must use the established forensic audit architecture.

Sensitive actions include:

- role changes
- wallet transactions
- KYC changes
- security-sensitive administrative operations
- other operations required by compliance policy

Use the existing forensic audit service and established audit mechanisms.

Preserve:

- correlation IDs
- timestamps
- actor information
- status
- risk information
- relevant request context

Do not bypass audit logging for convenience.

---

# 30. Directory & Subtree Usage

When working on a specific module, prefer staying within that subtree.

Examples:

    app/events/
    app/wallet/
    app/accommodation/
    app/transport/
    app/identity/

This minimizes:

- context pollution
- unintended side effects
- unrelated refactoring
- unnecessary token consumption

Expand beyond the subtree only when evidence shows a dependency.

---

# 31. Context-Polluting Paths

Ignore these during ordinary exploration unless explicitly required:

    **/__pycache__/**
    **/.venv/**
    **/backups_today/**
    **/model_backups/**
    **/templates_backup/**
    **/flask_session/**
    **/*.pyc
    **/node_modules/**
    **/docker/nginx/*.conf
    backup_*.json
    app.py.backup
    docker-compose.yml.backup

Migration history under:

    migrations/versions/*.py

may be inspected when migration analysis specifically requires it.

---

# 32. Standard Utilities

Prefer existing AFCON360 utilities instead of creating duplicate solutions.

Important utilities include:

| Utility | Purpose |
|---|---|
| ID Guard | Incorrect ID assignment protection |
| Module Guard | Module-level access control |
| Idempotency | Critical operation protection |
| Validators | Shared validation |
| Audit | Audit logging |

Before creating a new utility, check whether an existing one already provides
the required behavior.

---

# 33. Role System

The project may support a hierarchical role and permission system.

Current role definitions and ordering are governed by the identity/authorization
implementation and approved identity specifications.

Agents MUST NOT assume that a role name automatically grants authority.

Where active personas or contexts exist:

    active context → permission evaluation → authorized operation

The active authorized context must be respected.

Do not introduce or reinterpret roles without approval.

---

# 34. Prohibited Actions

Unless explicitly authorized, agents MUST NOT:

- change `BaseModel`
- change shared base classes
- modify `app/wallet/models/`
- create PostgreSQL ENUM types
- expose internal `id`
- run destructive database commands
- silently change public API contracts
- bypass authorization
- create migrations
- patch migrations
- apply migrations
- introduce SQLite testing fallbacks
- perform unrelated refactors
- delete deferred-work records
- weaken security controls
- invent unspecified business rules
- silently expand graph-node scope
- silently fix audit findings
- silently remediate verification findings

---

# 35. Command Success Evaluation

For Python/Flask verification commands:

- Exit code `0` means success unless the command's explicit contract says
  otherwise.
- Treat as failure when exit code != 0.
- Also treat output containing `ERROR`, `Exception`, or `Traceback` as failure
  evidence.
- INFO/WARNING/DEBUG output does not automatically indicate failure.

Agents should interpret command output in context rather than treating all
stderr as failure.

---

# 36. Canonical Database Verification

Use:

    & .venv/Scripts/python.exe verify_db.py

Success requires:

- output contains `DB_VERIFY_OK`
- exit code is `0`

This command does not authorize migrations.

---

# 37. Common Commands

Application (dev server):

    python app.py
    # or: flask run   (with APP_ENV / FLASK_ENV set)

Startup import sanity check (no server started):

    python -c "from app import create_app"

Celery worker + beat (dev):

    celery -A app.celery_app worker --loglevel=info
    celery -A app.celery_app beat  --loglevel=info

Tests (conftest auto-bootstraps the PostgreSQL test DB; no manual step):

    pytest                                              # full suite
    pytest tests/notifications                          # a directory
    pytest tests/test_accommodation_checkout_processes.py                       # one file
    pytest tests/test_accommodation_checkout_processes.py::TestClass::test_method  # one test

Force a clean test-DB rebuild (drops + recreate + create_all + stamp head):

    python scripts/setup_test_db_schema.py

Database verification (does NOT authorize migrations; success = exit 0
AND output contains `DB_VERIFY_OK`):

    python verify_db.py            # or: .venv/Scripts/python.exe verify_db.py

Database inspection only (agents must still obey migration restrictions):

    flask db current
    flask db heads
    flask db history

Seed / setup helpers (run only after a reviewed migration, by the operator):

    python scripts/seed_roles.py
    python scripts/seed_system_configs.py   # or scripts/init_settings.py

ID-usage inspection (do not expose internal ids — see §12.1):

    python scripts/check_id_usage.py
    python scripts/db_audit.py

Linting / formatting:

    No project linter or formatter is configured. `.pre-commit-config.yaml`
    runs only trailing-whitespace, end-of-file-fixer, check-yaml, and
    check-added-large-files. Do not assume `ruff` / `flake8` / `black` /
    `mypy` / `isort` are available unless they are explicitly added to
    `requirements.txt` and the pre-commit config.

Agents must still obey migration restrictions (see §20). Do NOT run
`flask db upgrade` to provision the test database; `pytest` does it via
`db.create_all()` + stamp. Do NOT use `flask db migrate` as an unattended
workaround.

---

# 38. Post-Change Verification

Verification must be proportional to task class and changed scope.

### TRIVIAL

Use focused checks.

### LOCAL

Use targeted tests or focused validation.

### BEHAVIORAL

Verify:

- behavior
- relevant transitions
- authorization
- negative cases
- affected tests

### ARCHITECTURAL

Verify:

- affected contracts
- cross-module boundaries
- integration points
- relevant test suites
- architecture invariants

### HIGH_RISK

Verify:

- invariants
- security controls
- financial correctness
- identity correctness
- migration implications
- relevant tests
- failure/recovery behavior
- audit behavior

Do not automatically run the entire repository test suite for every small
change unless required by the task or affected contract.

---

# 39. Post-Change Report

After implementation, provide a structured completion report.

Use:

    STATUS: PASS | PARTIAL | BLOCKED | NEEDS_DECISION | FAIL
    NODE: <graph-node-id>
    SCOPE: <authorized scope>

Then report:

- **Files changed:** every modified file
- **Behavior change:** what actually changed
- **Migration:** required yes/no; if yes, propose exact commands but do not
  execute them automatically
- **Manual steps:** environment changes, restarts, seeds, etc.
- **Verification:** tests and manual verification performed
- **Risks:** potential regressions or conflicts
- **Deferred work:** anything identified but not completed
- **Documentation:** relevant documentation updated or not required
- **Memory updated:** yes/no, and what changed

For audits, report:

- evidence inspected
- findings
- severity/classification
- missing coverage
- affected files
- recommended next node
- confirmation that no implementation was performed unless authorized

Do not report `PASS` merely because code was written.

---

# 40. Reference Discovery

Agents should consult the relevant document rather than loading everything.

Important references include:

    DATABASE_SCALABILITY_ROADMAP.md
    docs/POSTGRES_TESTING_CONTRACT.md
    app/Documentation/IDENTITY_POLICIES.md
    app/accommodation/AFCON360_SEAMLESS_BOOKING_SPEC.md
    static/MOBILE_OPTIMIZATION.md
    BACKLOG.md

Additional domain specifications and ADRs take precedence for their specific
domain.

Agents MUST discover and use relevant:

- skills
- workflows
- rules
- ADRs
- specifications
- module documentation

when applicable.

Do NOT assume that only the documents explicitly named in this constitution
exist.

---

# 41. Tool Adapters

The repository root:

    AGENTS.md

is the single engineering constitution.

Tool-specific files under:

    .junie/
    .kilocode/
    .aider/
    other agent-specific directories

are adapters.

They define:

- how the tool discovers context
- how the tool invokes workflows
- how skills are loaded
- how rules are selected
- how commands are executed
- tool-specific limitations

They MUST NOT redefine or contradict:

- ownership boundaries
- wallet rules
- identity rules
- migration authority
- security requirements
- specification law
- graph authority
- prohibited actions
- memory principles
- scope rules

If a tool adapter conflicts with this document, this document wins unless the
current task explicitly establishes a higher-priority approved change.

---

# 42. Junie & Kilo Interoperability

Junie and Kilo may have different:

- skills
- rule systems
- workflows
- context mechanisms
- command interfaces
- agent execution models

These differences MUST NOT create different AFCON360 architectural rules.

Both must operate against the same:

    root AGENTS.md
          ↓
    specifications / ADRs
          ↓
    current repository
          ↓
    current graph node

A Junie skill MUST NOT create a rule that Kilo is forbidden to follow when the
root constitution permits it.

A Kilo rule MUST NOT create behavior that Junie would be prohibited from
performing under the root constitution.

Tool-specific adapters may be more restrictive than the root constitution when
necessary for the tool, but may not weaken root protections.

---

# 43. Agent Handoff

When work moves from one agent/tool to another, the handoff should contain:

- graph node
- current status
- authorized scope
- files changed
- files inspected
- relevant specification
- tests run
- verification results
- unresolved issues
- deferred work
- decisions required

The next agent MUST NOT assume that conversation history is sufficient evidence.

Durable decisions belong in the repository's appropriate documentation,
specification, ADR, graph state, or backlog.

---

# 44. Periodic Constitution & Project-Fact Review

The root `AGENTS.md` should be reviewed periodically rather than rewritten
during ordinary development tasks.

A review should normally occur approximately every **6 months**, or earlier
when a major architectural or infrastructure change occurs.

The review should check:

- project stack versions
- important paths
- architectural invariants
- reference documents
- tool adapters
- security rules
- migration policy
- testing contract
- module ownership
- command conventions

Agents should not modify this constitution merely because a temporary
implementation detail differs from it.

A constitution update should reflect an intentional project-level change or
verified durable fact.

---

# 45. Quality Principles

All AFCON360 agent work should follow these principles:

### Correctness over convenience

Do not choose an easier implementation that violates architecture or
specification.

### Evidence over assumption

Inspect the relevant evidence before making consequential decisions.

### Minimal scope over opportunistic refactoring

Fix what the node authorizes.

### Memory for routing, repository for truth

Use memory to find the right place. Verify against the current repository.

### Specification over legacy behavior

Legacy behavior is evidence, not authority.

### Verification over confidence

Do not report success without appropriate evidence.

### Safety over speed

For high-risk changes, additional verification is justified.

### Proportionality over bureaucracy

Small tasks should remain small.

Do not apply high-risk process to trivial work unnecessarily.

---

# 46. Final Agent Execution Loop

For ordinary work:

    1. Read task
       ↓
    2. Identify graph node / task scope
       ↓
    3. Classify risk
       ↓
    4. Consult memory/routing information when useful
       ↓
    5. Identify affected module/subtree
       ↓
    6. Load only applicable rules/skills/workflows/specifications
       ↓
    7. Inspect current implementation
       ↓
    8. Inspect relevant tests
       ↓
    9. Determine smallest safe change
       ↓
    10. Implement only authorized work
       ↓
    11. Run proportional verification
       ↓
    12. Record deferred work if required
       ↓
    13. Update durable memory only if knowledge changed
       ↓
    14. Produce evidence-based completion report

For audits:

    task
      ↓
    graph node
      ↓
    scope
      ↓
    evidence
      ↓
    implementation/test inspection
      ↓
    findings
      ↓
    report
      ↓
    recommend next node

For high-risk work:

    task
      ↓
    specification
      ↓
    ownership/invariants
      ↓
    current implementation
      ↓
    current tests
      ↓
    implementation
      ↓
    targeted + high-risk verification
      ↓
    evidence report
      ↓
    human/graph decision

---

# 47. Final Rule

When uncertain:

    DO NOT GUESS.

Instead:

    inspect
      ↓
    identify the governing rule/specification
      ↓
    determine authority
      ↓
    determine scope
      ↓
    verify the current state
      ↓
    act only when authorized
      ↓
    report evidence

AFCON360 agents are workers inside an engineering system.

They are expected to be:

- precise
- conservative where risk is high
- efficient where risk is low
- evidence-driven
- scope-aware
- specification-driven
- interoperable across tools

They MUST NOT become independent architects merely because they can modify the
codebase.

---

## 48. Email & Phone Verification (AFCON360)

Two verification mechanisms are offered per channel, so users can verify
either by clicking a link in the message or by typing a code in the app.

- **Magic-link (one-click):** a signed, single-use token embedded in the
  email/SMS "Verify" button. Handled by `GET /verify?token=<signed>` →
  `verify_email()` in `app/auth/services.py`. The token is purpose-bound
  (`verify`), carries a `nonce` (single-use — cleared on success), and expires
  after `EMAIL_VERIFY_EXPIRY` (1 hour).
- **OTP code (fallback):** a 6-digit code the user types on the in-app form.
  Email: `POST /verify-email` (GET renders the form) →
  `verify_email_code()` in `app/auth/email.py`. Phone: `GET/POST /verify-phone`
  → `PhoneVerificationService`. Codes are stored with a TTL (email
  `EMAIL_OTP_TTL` = 30 min; SMS `sms_verification` = 5 min).

Design rules:

- Email/SMS templates MUST contain BOTH the code and a verify link. For email
  the link MUST be the magic-link token URL (`url_for('auth.verify',
  token=...)`); for phone it is the channel verify page (`/verify-phone`).
- Expiry copy in templates MUST match the real TTL — do **not** hardcode 24h.
  The email context provides `expires_in_minutes` (derived from
  `EMAIL_OTP_TTL`).
- `verify_email()` sets `is_verified`, `email_verified`, and
  `email_verified_at`; it is idempotent for already-verified accounts.
- Magic-link tokens are bearer credentials: keep `EMAIL_VERIFY_EXPIRY` short
  and ensure the nonce is regenerated on each send.
- The token is generated in `app/auth/otp_service.py`
  `send_email_otp_checked()` (sets `email_verify_nonce` + commits, then builds
  the link). `app/auth/email.py send_verification_email()` is the caller for
  existing-account resends.
- Altering this lifecycle (adding magic links, changing expiry, merging the
  two mechanisms) is a BEHAVIORAL change — specify before implementing (§6).

---

**Last Updated:** August 2026
**AFCON360 Version:** v0.1.0

**Status:** AUTHORITATIVE