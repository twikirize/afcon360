# AFCON360 Constitutional Rules for OpenCode

> **Source**: AGENTS.md (authoritative) + referenced specifications
> **Purpose**: Single-file reference for OpenCode agent — no information loss
> **Last Updated**: August 2026

---

## §1 Authority & Precedence (AGENTS.md §1)

When instructions conflict, use this order:

1. Explicit current-task user instruction — defines requested scope and objective
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

A user instruction determines what the user wants the agent to do, but does not silently rewrite an approved specification, security invariant, financial control, or architectural decision.

A lower-level instruction MUST NOT silently violate a higher-level security, financial, architectural, identity, authorization, or public-contract constraint.

Existing code and passing tests are evidence of current behavior. They are NOT automatic authorization to preserve or extend behavior that conflicts with an approved specification or architectural decision.

---

## §2 Agent Operating Model (AGENTS.md §2)

AFCON360 uses a graph-based engineering workflow. AI coding tools are workers inside that workflow, not independent owners of product requirements, business rules, architecture, ownership boundaries, financial rules, security boundaries, public contracts, or graph transitions.

### Graph Nodes (AGENTS.md §2.1)

Every substantial engineering task should be treated as a graph node with: node ID, objective, authorized scope, exclusions, inputs, expected outputs, constraints, required evidence, verification requirements, completion criteria.

### Node Modes (AGENTS.md §2.2)

- **EXPLORER**: Inspect and map. Do not modify application behavior unless explicitly authorized.
- **AUDIT**: Inspect, analyze, test, compare, classify, report. Read-only unless node contract grants implementation authority. MUST NOT silently fix findings, modify code/tests/migrations/schemas, refactor adjacent code.
- **SPECIFICATION**: Formalize intended behavior. Do not silently implement.
- **PLANNER**: Determine steps, dependencies, risks, verification strategy. Do not modify implementation unless explicitly authorized.
- **IMPLEMENTATION**: Modify approved code, add required tests, verify result. Do not redesign unrelated architecture.
- **VERIFIER**: Inspect, test, compare against specification. May discover defects but MUST NOT silently remediate unless explicitly included in node contract.
- **DIAGNOSTICIAN**: Investigate failures, identify root causes. Do not broaden into unrelated fixes.
- **REVIEWER**: Review against specification, node contract, architecture, security rules, verification evidence.
- **MIGRATION_REVIEWER**: Review schema state, model metadata, migration requirements, history, safety.

Workers may recommend next graph node. Workers do not own graph transitions unless explicitly instructed.

---

## §3 Task Classification & Adaptive Execution (AGENTS.md §3)

### Task Classes (AGENTS.md §3.1)

| Class | Examples | Process |
|-------|----------|---------|
| **TRIVIAL** | docs, formatting, comments, presentation-only | Inspect target → minimal change → focused verification |
| **LOCAL** | Single-file, no cross-module contract | Identify module → load local rules → inspect → minimal change → targeted verification |
| **BEHAVIORAL** | Business rules, lifecycle, auth, API behavior, state transitions, ownership | Identify spec → inspect impl/tests/ownership → implement only after understood/authorized → verify transitions/negative cases |
| **ARCHITECTURAL** | Cross-module, schema, ownership, public-contract | Establish dependencies/invariants/ownership/contracts/specs → plan → verify cross-module effects |
| **HIGH_RISK** | Wallet, identity, auth, security, compliance, financial, migrations, destructive ops, public-contract changes | Complete evidence + verification process |

Memory may reduce exploration but NEVER replaces: current-code inspection, specification inspection, invariant verification, test verification.

### Progressive Context Loading (AGENTS.md §3.2)

```
task → graph node → memory/routing → affected module → applicable rules
→ applicable skills/workflows/specifications → current code/tests
→ proportional verification
```

Start with: task description, current graph node, relevant memory/index, affected module, risk classification.

Then load ONLY: relevant rules, skills, workflows, ADRs, specifications, documentation.

Expand context only when evidence reveals: dependency, contradiction, ownership boundary, architectural consequence, security concern, financial consequence, public-contract impact.

DO NOT load every skill, workflow, ADR, historical report, or module document merely because it exists.

### Minimal Execution Principle (AGENTS.md §3.3)

Agents MUST prefer smallest safe inspection/implementation path that establishes correctness.

Agents SHOULD NOT: scan entire repo for local task, load unrelated skills/workflows, read historical reports that cannot affect decision, run entire test suite for isolated change unless required, perform broad refactoring merely because related code is imperfect, repeatedly inspect same files without new evidence.

Verification proportional to: task class, risk, scope, changed behavior, affected contracts.

Objective: minimum necessary context + minimum necessary inspection + minimum necessary implementation + sufficient verification.

Safety MUST NOT be sacrificed for token or time savings.

---

## §4 Change Authority (AGENTS.md §4)

Before modifying anything, agent MUST establish:
- Active graph node
- Node type
- Whether modification is authorized
- Authorized files/subtrees
- Excluded files/subtrees
- Governing specifications
- Required verification
- Applicable risks

Existence of defect does NOT grant permission to fix it.
Existence of convenient refactoring does NOT grant permission to perform it.
Existence of failing test does NOT automatically authorize changing test or implementation.
Existence of related work does NOT authorize scope expansion.

---

## §5 Scope Discipline & Controlled Helpfulness (AGENTS.md §5)

Agents MUST implement ONLY the approved change.

Do not perform unrelated: refactors, renames, architecture migrations, dependency upgrades, formatting sweeps, test rewrites, database cleanup, public API changes unless explicitly authorized.

When exploring a module, prefer the relevant subtree.

### Scope Expansion (AGENTS.md §5.1)

If implementation reveals dependency outside authorized scope, agent must choose:
1. Resolve only if current node explicitly permits dependency changes
2. Record as deferred work in BACKLOG.md
3. Stop with `NEEDS_DECISION` if dependency changes: architecture, ownership, security, financial behavior, public contracts, specification

Agents MUST NOT silently expand scope because technically convenient.

---

## §6 Specification Law (AGENTS.md §6)

AFCON360 behavior MUST be specified before implementation whenever a change introduces or alters: business rules, invariants, workflows, lifecycle, state transitions, permission boundaries, ownership rules, financial guarantees, compliance obligations, externally observable contracts.

Before implementation, establish: affected entities, state variables, inputs, outputs, invariants, failure conditions, valid transitions, ownership, authority, initiator, approver, rejector, retry authority, reversal authority, observation/read authority.

Resolve conflicting interpretations before implementation.

Do NOT use as implicit authorization: legacy behavior, convenience, agent preference, passing tests, implementation simplicity.

If specification is missing, contradictory, ambiguous, or materially incomplete: STOP and return `STATUS: NEEDS_DECISION`.

Tests should cover: transitions, invariants, authorization, negative cases, important failure paths.

---

## §7 Evidence-First Engineering (AGENTS.md §7)

For non-trivial work, maintain evidence chain:
```
Requirement → Specification → Current implementation → Current tests → Gap → Proposed change → Verification
```

Do not implement from assumptions when repository evidence is available.

Every completed graph node must provide evidence appropriate to its purpose.

Evidence may include: files inspected, specifications reviewed, relevant models/routes/services/tests, commands executed, test results, contract checks, invariant checks, risks, unresolved assumptions, deferred work.

Do not report success merely because code was written.

---

## §8 Completion Status (AGENTS.md §8)

Use one of:
- **PASS**: Authorized work complete, required verification passed
- **PARTIAL**: Some authorized work or required verification incomplete
- **BLOCKED**: Cannot proceed — required dependency/environment/file/migration state/test/service/evidence unavailable
- **NEEDS_DECISION**: Human/product/architecture/security/finance/compliance decision required
- **FAIL**: Implementation/verification did not satisfy node contract

---

## §9 Tests Are Evidence, Not Specification (AGENTS.md §9)

Passing tests establish evidence about current behavior. They do NOT automatically establish correctness.

If tests conflict with approved specification: 1) identify conflict, 2) report conflict, 3) determine whether spec or tests require approved change, 4) do not silently alter behavior merely to satisfy tests.

Similarly, do not change tests merely to make new implementation pass unless test is demonstrably inconsistent with approved behavior.

---

## §10 Memory & Knowledge Policy (AGENTS.md §10)

### Memory as Routing Cache (AGENTS.md §10.1)
Memory = routing/index. Current repository = implementation truth. Tests = behavioral evidence. Specifications/ADRs = intended authority.

Agents SHOULD consult relevant memory before expensive exploration when it can identify: affected files, previous decisions, known constraints, unresolved work, previous verification results, relevant graph nodes, likely ownership boundaries.

For TRIVIAL/LOCAL tasks, memory may substantially reduce exploration. For BEHAVIORAL/ARCHITECTURAL/HIGH_RISK, memory may narrow search but MUST NOT replace verification of current source and governing contracts.

Memory MUST NOT be treated as proof that a file or behavior is unchanged.

### Memory Updates (AGENTS.md §10.2)
Do NOT update memory after every task.

Update durable project memory, ADRs, specifications, or BACKLOG.md only when task: creates reusable knowledge, changes invariant, resolves architectural decision, discovers reusable constraint, changes ownership, resolves deferred work, creates important operational knowledge, changes durable workflow, establishes significant implementation decision.

Do NOT create memory entries for: routine implementation details, temporary debugging observations, one-off commands, information already represented clearly by code, trivial documentation edits.

Goal: make memory more useful over time, not larger after every task.

---

## §11 Deferred Work (AGENTS.md §11)

All identified but incomplete work that belongs in the system MUST be recorded in `BACKLOG.md`.

Do not silently leave unfinished work in conversation history.

Record work when: requested but out of scope, partially implemented, blocked, awaiting migration/another team/external dependency/security review/finance-compliance review, explicitly deferred.

Reference concrete: files, models, routes, services, specifications, graph nodes.

Do NOT delete historical backlog entries.

Resolved items marked: `Status: Done`, `Resolved: YYYY-MM-DD`

---

## §12 Core Architectural Invariants (AGENTS.md §12)

### Dual ID System (AGENTS.md §12.1)

Every database entity uses two identifiers:
- `id` — internal `BigInteger` (database relations, foreign keys, joins, persistence) — NEVER expose externally
- `public_id` — external UUID/approved public identifier (APIs, URLs, external references, human-visible identifiers, approved external identity operations)

Rules:
- Internal foreign keys use `id`
- External input resolves through `public_id`
- API responses use `public_id`
- URLs use `public_id`
- Never serialize raw internal `id`
- Never expose `user.id` in APIs, logs, or templates
- Never introduce another public identifier scheme without approved specification

See: `/app/identity/models/user.py:25-45`

---

## §13 Base Models (AGENTS.md §13)

All models MUST inherit from `app.models.base.BaseModel` or approved derived class (e.g., `ProtectedModel`).

Do not introduce direct `db.Model` inheritance without explicit architectural approval.

Verify repository conventions before treating any exception as intentional.

---

## §14 PostgreSQL ENUM Policy (AGENTS.md §14)

Do NOT introduce new PostgreSQL ENUM types.

Use: `String`, application-level validation, CHECK constraints where appropriate.

Existing ENUM migrations must follow approved expand-contract strategy.

See: `DATABASE_SCALABILITY_ROADMAP.md`

---

## §15 Property Naming Safety (AGENTS.md §15)

Never define a Python `@property` with the same name as a SQLAlchemy `Column`.

Use suffixes: `_flag`, `_status`, `_computed`.

Example:
```python
@property
def is_verified_status(self):
    return self.email_verified and self.phone_verified
```

---

## §16 Import Style (AGENTS.md §16)

Use absolute imports from project root.

Example:
```python
from app.identity.models.user import User
from app.wallet.models.transaction import Transaction
```

Be careful with circular imports around: identity, events, accommodation, wallet, services, model registration.

Verify startup: `python -c "from app import create_app"`

---

## §17 Ownership Boundaries (AGENTS.md §17)

Cross-module operations MUST respect domain ownership. A module MUST NOT silently become owner of another module's domain state.

| Domain | Owns |
|--------|------|
| Identity | Users, organisations, identity relationships |
| Auth | Authentication and session entry |
| Events | Events, registrations, event lifecycle |
| Accommodation | Properties, inventory, availability, reservations |
| Transport | Vehicles, drivers, routes, transport assignments |
| Wallet | Ledger, balances, financial transactions |
| KYC | Identity verification workflows |
| Compliance | Compliance rules and AML checks |
| Audit | Forensic audit records |

Cross-module operations MUST use explicit contracts. Do not directly manipulate another module's internal state merely because database makes it technically possible.

---

## §18 High-Risk Areas (AGENTS.md §18)

### Wallet (AGENTS.md §18.1) — CRITICAL

Treat wallet changes as CRITICAL unless explicitly classified otherwise.

Rules:
- Preserve double-entry accounting
- Every debit must have corresponding credit
- Do not mutate balances outside ledger model
- Maintain idempotency
- Preserve transaction integrity
- Roll back failed database transactions
- Preserve audit trails
- Preserve reconciliation behavior
- Do not modify `app/wallet/models/` without explicit authorization
- Preserve compliance controls
- Preserve transaction references and idempotency keys

Wallet changes may require: compliance review, financial review, additional tests, reconciliation verification.

See: `app/wallet/models/` (ledger/account), `app/wallet/services/`, `app/wallet/repositories/`, `app/wallet/payments/` (Flutterwave, Paystack, Mobile Money MTN/Airtel, PayPal, Alipay, WeChat Pay, Visa), `app/wallet/api/`, `app/wallet/middleware/`, `app/wallet/routes_pin.py`, `app/tasks/webhook_processor.py`, `app/tasks/reconcile.py`, `templates/wallet/fx_rates.html`

### Identity, Roles & Personas (AGENTS.md §18.2)

Governed by approved identity specification and role/permission policy.

Agents MUST NOT infer authority from role names alone.

Where AFCON360 supports: multiple roles, personas, organizational contexts, active-role switching, user/organization context — authorization MUST respect currently active authorized context.

Role changes must be audit-logged.

Owner cannot be: deleted, impersonated, self-modified.

Super admin cannot modify: another super admin, owner.

Do not introduce, remove, reorder, merge, or reinterpret roles without approved identity/authorization specification.

Detailed role matrix in `app/Documentation/IDENTITY_POLICIES.md`.

---

## §19 Database Rules (AGENTS.md §19)

### PostgreSQL Requirement (AGENTS.md §19.1)

PostgreSQL is the only supported production and test database.

Do NOT introduce: SQLite fallbacks, in-memory persistence fixtures.

### Model Registration (AGENTS.md §19.2)

When adding a model:
1. Inherit from `BaseModel` or approved derived class
2. Define table/index/constraint requirements
3. Register in `app/core/model_registry.py`
4. Export from relevant domain `__init__.py` when required
5. Verify Alembic can detect it

A model not correctly registered is incomplete.

See: `app/core/model_registry.py`, `app/__init__.py:579-580`

### Soft Delete (AGENTS.md §19.3)

Where model uses standard soft-delete architecture, queries should exclude deleted records.

Example: `Model.query.filter(Model.is_deleted == False)`

Use repository's established soft-delete helper/query patterns where they exist.

---

## §20 Migration Law (AGENTS.md §20)

Schema changes are HIGH RISK.

Agents MUST NOT create, patch, or apply migrations without explicit authorization.

Agents MAY inspect: `flask db current`, `flask db heads`, `flask db history`

Agents MAY NOT create/apply migrations unless explicitly authorized:
- `flask db migrate`
- `flask db upgrade`
- `flask db downgrade`
- `flask db merge`

The user controls migration execution.

Agents MAY: identify required schema changes, inspect migration state/history, verify model metadata, propose exact commands.

Before proposing new migration:
1. Inspect current migration state
2. Run `flask db heads`
3. Identify whether multiple heads exist
4. Verify model registration
5. Identify intended schema delta
6. Review affected constraints
7. Propose commands without executing prohibited operations

Never patch generated migrations as workaround for model/source problem.

Known defect — missing baseline migration (RESOLVED):
- `ab6dd422c152_initial_schema` retired to `migrations/_retired_versions/`
- Replaced by `migrations/versions/8a0deccce6f6_initial_full_schema_baseline.py` — single root migration (`down_revision=None`) building entire schema via `db.metadata.create_all()`
- Verified: `flask db upgrade` from EMPTY database builds all 182 tables

---

## §21 Testing Contract (AGENTS.md §21)

PostgreSQL is the only supported database backend for application and persistence tests.

Do NOT introduce: SQLite test fallbacks, in-memory database fixtures.

Tests should use: shared `TestingConfig`, project pytest fixtures, dedicated migration-managed `TEST_DATABASE_URL`.

Tests must fail fast when: PostgreSQL unavailable, schema stale, required migrations missing.

Application and test code should use SQLAlchemy models/Core expressions rather than handwritten SQL strings.

Direct SQL persistence tests are not supported.

### Test Database Bootstrap (AGENTS.md §21.1)

PostgreSQL test database bootstrapped **automatically by `tests/conftest.py`** every time `pytest` runs. Agents/developers MUST NOT perform manual migration step before running tests; plain `pytest` is sufficient and only supported entry point.

`tests/conftest.py` is the **single canonical pytest runner** (root `conftest.py` only filters collection to `tests/`). Legacy root `_conftest.py` removed.

Test bootstrap uses `db.create_all()` + `stamp head` because fast, idempotent, test-only. Both paths use same model metadata, so resulting schema identical. For fresh non-test database, `flask db upgrade` is correct path.

What `tests/conftest.py` does:
1. Creates test database if not exists
2. If schema incomplete (no `users` table), builds from current SQLAlchemy models via `db.create_all()` (reflects model changes including `use_alter` FKs, defers circular FKs)
3. Stamps Alembic head so `tests/postgres_contract.py` check and any `flask db upgrade` treat DB as fully migrated
4. If schema exists, reused (fast path); no rebuild

Canonical commands:
```bash
pytest                                              # full suite (conftest auto-builds/verifies test DB)
python scripts/setup_test_db_schema.py              # force clean rebuild (drops + recreate + create_all + stamp)
```

Do NOT run `flask db upgrade` to provision test database; `pytest` does it via `db.create_all()` + stamp. If test DB stale after model/schema change, run `scripts/setup_test_db_schema.py`. For fresh non-test database, `flask db upgrade` from empty now builds full schema via `8a0deccce6f6` baseline.

See: `docs/POSTGRES_TESTING_CONTRACT.md`, `scripts/setup_test_db_schema.py`, `tests/postgres_contract.py`, `tests/conftest.py`

---

## §22 Frontend Rules (AGENTS.md §22)

Frontend changes MUST preserve mobile-first behavior.

Requirements: no unintended horizontal overflow, touch targets ≥44×44px, responsive grids, fluid typography using `clamp()`, safe-area handling where required, no inappropriate fixed widths, no inline layout styles where prohibited.

Templates: Use `{{ csrf_token() }}` for forms requiring CSRF protection. Preserve `?_pane=1` behavior where used. Avoid `overflow: hidden` on containers holding dropdowns unless safe.

### JavaScript & CSP (AGENTS.md §22.1)

Use external scripts where possible. Do not use: inline event handlers, unnecessary inline executable scripts. Inline executable scripts require application's appropriate CSP nonce. JSON-LD blocks must follow application's CSP requirements.

### Frontend Documentation (AGENTS.md §22.2)

When HTML, Jinja, or CSS changes, assess `static/MOBILE_OPTIMIZATION.md`. Update when frontend change affects its documented: file tree, responsive behavior, styling, branding, verification state, isolation plan.

---

## §23 Security Rules (AGENTS.md §23)

Agents MUST:
- Never expose internal database IDs
- Validate ownership before returning sensitive data
- Preserve authentication boundaries
- Preserve authorization boundaries
- Preserve CSRF protections
- Preserve CSP requirements
- Never commit secrets
- Use database-safe/parameterized queries
- Preserve idempotency for critical operations
- Audit sensitive operations
- Avoid weakening security controls for convenience

---

## §24 Environment & Project Stack (AGENTS.md §24)

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

External services: AWS S3/OCR, Flutterwave, Paystack, PayPal, NIRA, OCI storage, mobile money integrations, other approved payment/verification providers.

---

## §25 Environment Configuration (AGENTS.md §25)

Layered configuration: `.env` → `.env.{APP_ENV}` → application configuration.

Common environments: `APP_ENV=local`, `APP_ENV=docker`, `APP_ENV=prod`.

Key variables: `APP_ENV`, `FLASK_ENV`, `DATABASE_URL`, `REDIS_URL`, `ENCRYPTION_KEY`, `DISABLE_REDIS`.

Do not expose secrets. Do not inspect or print secret values merely for verification. Encryption/configuration values must be loaded according to application's configuration lifecycle.

---

## §26 Async Tasks (AGENTS.md §26)

Celery handles: webhooks, media processing, reconciliation, notifications, scheduled operations.

Principles: idempotency, retry safety, application context, transaction integrity, bounded retries, safe serialization, correct task registration.

Do not introduce non-idempotent retry behavior into financial operations.

---

## §27 Middleware & Request Lifecycle (AGENTS.md §27)

Middleware/hooks for: module toggles, session lifecycle, rate limiting, security headers, ID guard validation.

Do not remove or bypass existing middleware protections without authorization.

Module toggles must continue to prevent disabled modules from causing unrelated parts to fail.

---

## §28 Module Toggle System (AGENTS.md §28)

Modules may be enabled/disabled at runtime: events, accommodation, transport, wallet, tourism, tournament.

Use established module guard: `@module_required('module_name')`.

State stored through application's system configuration/toggle system.

ALWAYS preserve existing module guards unless explicitly instructed otherwise.

New routes within gated modules must inherit applicable module guard.

Disabled modules should fail safely without crashing unrelated modules.

---

## §29 Forensic Audit & Compliance (AGENTS.md §29)

Sensitive operations must use established forensic audit architecture.

Sensitive actions: role changes, wallet transactions, KYC changes, security-sensitive administrative operations, other operations required by compliance policy.

Use existing forensic audit service and established audit mechanisms.

Preserve: correlation IDs, timestamps, actor information, status, risk information, relevant request context.

Do not bypass audit logging for convenience.

See: `app/audit/forensic_audit.py` (`log_attempt()`, `log_completion()`, `log_blocked()`, `get_audit_timeline()`, `get_pending_reviews()`, `get_suspicious_patterns()`), `app/compliance/aml_service.py` (changes require compliance review), audit columns: `attempted_at`, `status`, `reviewed_by_user_id`, `reviewed_at`, `review_notes`, `ip_address`, `user_agent`, `session_id`, `correlation_id`, `risk_score`.

---

## §30 Directory & Subtree Usage (AGENTS.md §30)

When working on specific module, prefer staying within that subtree: `app/events/`, `app/wallet/`, `app/accommodation/`, `app/transport/`, `app/identity/`.

Minimizes: context pollution, unintended side effects, unrelated refactoring, unnecessary token consumption.

Expand beyond subtree only when evidence shows dependency.

---

## §31 Context-Polluting Paths (AGENTS.md §31)

Ignore during ordinary exploration unless explicitly required:
`**/__pycache__/**`, `**/.venv/**`, `**/backups_today/**`, `**/model_backups/**`, `**/templates_backup/**`, `**/flask_session/**`, `**/*.pyc`, `**/node_modules/**`, `**/docker/nginx/*.conf`, `backup_*.json`, `*.backup`, `app.py.backup`, `docker-compose.yml.backup`

Migration history under `migrations/versions/*.py` may be inspected when migration analysis specifically requires it.

---

## §32 Standard Utilities (AGENTS.md §32)

Prefer existing AFCON360 utilities:

| Utility | Purpose |
|---------|---------|
| ID Guard (`app/utils/id_guard.py`) | Incorrect ID assignment protection |
| Module Guard (`app/utils/module_guard.py`) | Module-level access control |
| Idempotency (`app/utils/idempotency.py`) | Critical operation protection |
| Validators (`app/utils/validators.py`) | Shared validation |
| Audit (`app/utils/audit.py`) | Audit logging |

Before creating new utility, check whether existing one already provides required behavior.

---

## §33 Role System (AGENTS.md §33)

Project may support hierarchical role and permission system. Current definitions/ordering governed by identity/authorization implementation and approved identity specifications.

Agents MUST NOT assume role name automatically grants authority.

Where active personas/contexts exist: `active context → permission evaluation → authorized operation`.

Active authorized context must be respected.

Do not introduce or reinterpret roles without approval.

---

## §34 Prohibited Actions (AGENTS.md §34)

Unless explicitly authorized, agents MUST NOT:
- Change `BaseModel` or shared base classes
- Modify `app/wallet/models/`
- Create PostgreSQL ENUM types
- Expose internal `id`
- Run destructive database commands
- Silently change public API contracts
- Bypass authorization
- Create, patch, or apply migrations
- Introduce SQLite testing fallbacks
- Perform unrelated refactors
- Delete deferred-work records (BACKLOG.md)
- Weaken security controls
- Invent unspecified business rules
- Silently expand graph-node scope
- Silently fix audit findings
- Silently remediate verification findings

---

## §35 Command Success Evaluation (AGENTS.md §35)

For Python/Flask verification commands:
- Exit code `0` = success unless command's explicit contract says otherwise
- Treat as failure when exit code != 0
- Also treat output containing `ERROR`, `Exception`, or `Traceback` as failure evidence
- INFO/WARNING/DEBUG output does not automatically indicate failure

Interpret command output in context rather than treating all stderr as failure.

---

## §36 Canonical Database Verification (AGENTS.md §36)

Use: `& .venv/Scripts/python.exe verify_db.py`

Success requires: output contains `DB_VERIFY_OK` AND exit code is `0`.

This command does not authorize migrations.

---

## §37 Common Commands (AGENTS.md §37)

Application (dev server):
```bash
python app.py
# or: flask run (with APP_ENV / FLASK_ENV set)
```

Startup import sanity check:
```bash
python -c "from app import create_app"
```

Celery worker + beat (dev):
```bash
celery -A app.celery_app worker --loglevel=info
celery -A app.celery_app beat  --loglevel=info
```

Tests (conftest auto-bootstraps PostgreSQL test DB):
```bash
pytest                                              # full suite
pytest tests/notifications                          # directory
pytest tests/test_accommodation_checkout_processes.py  # one file
pytest tests/test_accommodation_checkout_processes.py::TestClass::test_method  # one test
```

Force clean test-DB rebuild:
```bash
python scripts/setup_test_db_schema.py
```

Database verification:
```bash
python verify_db.py
# or: .venv/Scripts/python.exe verify_db.py
```

Database inspection only (agents must still obey migration restrictions):
```bash
flask db current
flask db heads
flask db history
```

Seed / setup helpers (run only after reviewed migration, by operator):
```bash
python scripts/seed_roles.py
python scripts/seed_system_configs.py   # or scripts/init_settings.py
```

ID-usage inspection (do not expose internal ids — see §12.1):
```bash
python scripts/check_id_usage.py
python scripts/db_audit.py
```

Linting/formatting: No project linter/formatter configured. `.pre-commit-config.yaml` runs only trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files. Do not assume `ruff`/`flake8`/`black`/`mypy`/`isort` available unless explicitly added to `requirements.txt` and pre-commit config.

---

## §38 Post-Change Verification (AGENTS.md §38)

Verification proportional to task class and changed scope.

- **TRIVIAL**: Focused checks
- **LOCAL**: Targeted tests or focused validation
- **BEHAVIORAL**: Verify behavior, relevant transitions, authorization, negative cases, affected tests
- **ARCHITECTURAL**: Verify affected contracts, cross-module boundaries, integration points, relevant test suites, architecture invariants
- **HIGH_RISK**: Verify invariants, security controls, financial correctness, identity correctness, migration implications, relevant tests, failure/recovery behavior, audit behavior

Do not automatically run entire repository test suite for every small change unless required by task or affected contract.

---

## §39 Post-Change Report (AGENTS.md §39)

After implementation, provide structured completion report:

```
STATUS: PASS | PARTIAL | BLOCKED | NEEDS_DECISION | FAIL
NODE: <graph-node-id>
SCOPE: <authorized scope>
```

Then report:
- **Files changed:** every modified file
- **Behavior change:** what actually changed
- **Migration:** required yes/no; if yes, propose exact commands but do not execute automatically
- **Manual steps:** environment changes, restarts, seeds, etc.
- **Verification:** tests and manual verification performed
- **Risks:** potential regressions or conflicts
- **Deferred work:** anything identified but not completed
- **Documentation:** relevant documentation updated or not required
- **Memory updated:** yes/no, and what changed

For audits, report: evidence inspected, findings, severity/classification, missing coverage, affected files, recommended next node, confirmation no implementation performed unless authorized.

Do not report `PASS` merely because code was written.

---

## §40 Reference Discovery (AGENTS.md §40)

Agents should consult relevant document rather than loading everything.

Important references: `DATABASE_SCALABILITY_ROADMAP.md`, `docs/POSTGRES_TESTING_CONTRACT.md`, `app/Documentation/IDENTITY_POLICIES.md`, `app/accommodation/AFCON360_SEAMLESS_BOOKING_SPEC.md`, `static/MOBILE_OPTIMIZATION.md`, `BACKLOG.md`.

Additional domain specifications and ADRs take precedence for their specific domain.

Agents MUST discover and use relevant: skills, workflows, rules, ADRs, specifications, module documentation when applicable.

Do NOT assume only documents explicitly named in this constitution exist.

---

## §41 Tool Adapters (AGENTS.md §41)

Repository root `AGENTS.md` is the single engineering constitution.

Tool-specific files under `.junie/`, `.kilocode/`, `.aider/`, other agent-specific directories are adapters.

They define: how tool discovers context, invokes workflows, loads skills, selects rules, executes commands, tool-specific limitations.

They MUST NOT redefine or contradict: ownership boundaries, wallet rules, identity rules, migration authority, security requirements, specification law, graph authority, prohibited actions, memory principles, scope rules.

If tool adapter conflicts with this document, this document wins unless current task explicitly establishes higher-priority approved change.

---

## §42 Junie & Kilo Interoperability (AGENTS.md §42)

Junie and Kilo may have different: skills, rule systems, workflows, context mechanisms, command interfaces, agent execution models.

These differences MUST NOT create different AFCON360 architectural rules.

Both must operate against same: root AGENTS.md → specifications/ADRs → current repository → current graph node.

A Junie skill MUST NOT create a rule that Kilo is forbidden to follow when root constitution permits it.

A Kilo rule MUST NOT create behavior that Junie would be prohibited from performing under root constitution.

Tool-specific adapters may be more restrictive than root constitution when necessary for tool, but may not weaken root protections.

---

## §43 Agent Handoff (AGENTS.md §43)

When work moves from one agent/tool to another, handoff should contain: graph node, current status, authorized scope, files changed, files inspected, relevant specification, tests run, verification results, unresolved issues, deferred work, decisions required.

Next agent MUST NOT assume conversation history is sufficient evidence.

Durable decisions belong in repository's appropriate documentation, specification, ADR, graph state, or backlog.

---

## §44 Periodic Constitution & Project-Fact Review (AGENTS.md §44)

Root `AGENTS.md` should be reviewed periodically (~every 6 months) or earlier when major architectural/infrastructure change occurs.

Review should check: project stack versions, important paths, architectural invariants, reference documents, tool adapters, security rules, migration policy, testing contract, module ownership, command conventions.

Agents should not modify this constitution merely because temporary implementation detail differs from it.

Constitution update should reflect intentional project-level change or verified durable fact.

---

## §45 Quality Principles (AGENTS.md §45)

- **Correctness over convenience**: Do not choose easier implementation that violates architecture/specification
- **Evidence over assumption**: Inspect relevant evidence before consequential decisions
- **Minimal scope over opportunistic refactoring**: Fix what the node authorizes
- **Memory for routing, repository for truth**: Use memory to find right place; verify against current repository
- **Specification over legacy behavior**: Legacy behavior is evidence, not authority
- **Verification over confidence**: Do not report success without appropriate evidence
- **Safety over speed**: For high-risk changes, additional verification justified
- **Proportionality over bureaucracy**: Small tasks should remain small; do not apply high-risk process to trivial work unnecessarily

---

## §46 Final Agent Execution Loop (AGENTS.md §46)

### Ordinary Work:
```
1. Read task → 2. Identify graph node/task scope → 3. Classify risk
4. Consult memory/routing → 5. Identify affected module/subtree
6. Load ONLY applicable rules/skills/workflows/specifications
7. Inspect current implementation → 8. Inspect relevant tests
9. Determine smallest safe change → 10. Implement only authorized work
11. Run proportional verification → 12. Record deferred work if required
13. Update durable memory only if knowledge changed → 14. Produce evidence-based completion report
```

### Audits:
```
task → graph node → scope → evidence → implementation/test inspection → findings → report → recommend next node
```

### High-Risk Work:
```
task → specification → ownership/invariants → current implementation → current tests → implementation → targeted + high-risk verification → evidence report → human/graph decision
```

---

## §47 Final Rule (AGENTS.md §47)

When uncertain: **DO NOT GUESS.**

Instead: inspect → identify governing rule/specification → determine authority → determine scope → verify current state → act only when authorized → report evidence.

AFCON360 agents are workers inside an engineering system. Expected to be: precise, conservative where risk is high, efficient where risk is low, evidence-driven, scope-aware, specification-driven, interoperable across tools.

They MUST NOT become independent architects merely because they can modify the codebase.

---

## Consolidation Mapping (Zero Information Loss)

| Original Reference | Consolidated Into Section |
|-------------------|--------------------------|
| AGENTS.md (full) | All sections above |
| .junie/rules/00-core-always-on.md | §2, §3, §4, §5, §7, §8, §10, §46 |
| .junie/rules/10-database-models.md | §12, §13, §14, §15, §19 |
| .junie/rules/20-wallet-critical.md | §18.1, §11.6.4 |
| .junie/rules/30-api-routes.md | §16, §22, §28 |
| .junie/rules/40-identity-admin.md | §18.2, §33 |
| .junie/rules/50-async-tasks.md | §26, §11.6.2 |
| .junie/rules/60-compliance-audit.md | §29, §11.6.5 |
| .kilocode/rules/code-module-rules.md | §30, §31 |
| .kiro/steering/coding-rules.md | §11.6.7 |
| .kiro/steering/wallet-rules.md | §18.1 |
| .kiro/steering/role-system.md | §18.2 |
| .kiro/steering/testing.md | §21, §11.6.6 |
| rules/agent-governance-rules.md | §3.2, §3.3, §46 |
| DATABASE_SCALABILITY_ROADMAP.md | §14, §20, §11.6.3 |
| docs/POSTGRES_TESTING_CONTRACT.md | §21.1 |
| app/Documentation/IDENTITY_POLICIES.md | §18.2 |
| app/accommodation/AFCON360_SEAMLESS_BOOKING_SPEC.md | §17, §11.5.6 |
| static/MOBILE_OPTIMIZATION.md | §22 |
| BACKLOG.md | §11 |
| clarification-protocol.md | Separate file (referenced by agent) |