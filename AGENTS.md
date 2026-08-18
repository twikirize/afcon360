# AFCON360 Agent Developer Guide

**AUTHORITATIVE SOURCE** for all AI agents and automated engineering workers
working on the AFCON360 codebase. This document is the repository-level
engineering constitution. All agents MUST follow it unless an explicit,
higher-priority instruction for the current task overrides it.

## 0. AFCON360 Agent Operating Model

AFCON360 uses a graph-based engineering workflow. AI coding tools are workers
inside that workflow, not independent owners of product requirements or
architecture. The worker executes the current task and does not independently
redefine product requirements, business rules, ownership boundaries, financial
rules, security boundaries, architecture, public contracts, or graph transitions.

The repository root `AGENTS.md` is the single engineering constitution.
Tool-specific agent files may adapt these rules to their tool, explain
tool-specific execution, define commands, and provide context-loading guidance;
they MUST NOT redefine or contradict this document.

AFCON360 may contain skills, workflows, rules, ADRs, specifications, and
module-specific documents. Agents MUST discover and use relevant resources when
they exist; this document does not define a closed list of skills.

## 1. Authority Hierarchy

When instructions conflict, use this order:

1. Explicit user instruction for the current task
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

A lower-level instruction MUST NOT silently violate a higher-level security,
financial, architectural, or authorization constraint. Existing code and
passing tests are evidence of current behavior, not automatic authority over an
approved specification.

## 2. Graph Engineering Protocol

Every substantial engineering task should be treated as a graph node. A node
may represent exploration, audit, analysis, specification, planning,
implementation, testing, verification, review, debugging, migration review, or
release preparation.

Where a graph node exists, establish its ID, objective, scope, exclusions,
inputs, expected outputs, constraints, required evidence, verification
requirements, and completion criteria. The current node determines what the
worker may do:

- `AUDIT`: inspect, analyze, test, and report; do not implement unless authorized.
- `SPECIFICATION`: formalize behavior and resolve ambiguities; do not silently implement.
- `IMPLEMENTATION`: modify approved code, add required tests, and verify it; do not redesign unrelated architecture.
- `VERIFICATION`: inspect, test, compare against the specification, and report evidence; do not remediate unless authorized.

Workers may recommend the next graph node, but do not own graph transitions
unless explicitly instructed.

## 2.1 Adaptive Context and Execution Cost

Graph discipline is risk-adaptive. Agents MUST NOT load every skill,
workflow, historical report, or architecture document for every task. Use
repository memory and the task description as routing signals, then load only
the context required for the authorized scope.

Classify the task before broad inspection:

- `TRIVIAL`: documentation, wording, formatting, or isolated presentation-only
  changes. Inspect the target, make the minimal change, and perform a focused
  check.
- `LOCAL`: a single-file or tightly scoped code change with no cross-module
  contract. Load local rules, inspect affected code, and run targeted
  verification.
- `BEHAVIORAL`: a business-rule, lifecycle, authorization, or API behavior
  change. Load the relevant specification, ownership nodes, implementation,
  and tests before changing code.
- `ARCHITECTURAL`: cross-module, schema, ownership, or public-contract work.
  Establish dependencies, invariants, and authority boundaries before
  implementation.
- `HIGH_RISK`: wallet, identity, authentication/authorization, security,
  compliance, financial operations, migrations, or destructive operations.
  Use the complete evidence and verification process; memory never replaces
  current-code and specification checks.

The minimum safe path is:

```text
memory/graph lookup → proportional inspection → minimal change
→ proportional verification → memory update only if knowledge changed
```

Project memory answers what should be investigated; the current code and tests
establish what actually exists. Routine fixes do not require memory updates.
Update durable project memory, ADRs, specifications, or `BACKLOG.md` only when
the task creates, changes, resolves, or discovers reusable knowledge, an
invariant, an ownership rule, a decision, or deferred work.

## 3. Agent Modes

Typical modes include `EXPLORER`, `AUDITOR`, `ANALYST`, `SPECIFIER`,
`PLANNER`, `IMPLEMENTER`, `VERIFIER`, `DIAGNOSTICIAN`, `REVIEWER`, and
`MIGRATION_REVIEWER`. The current task determines the mode. A worker MUST NOT
silently assume the authority of another mode.

## 4. Controlled Helpfulness

Agents must not equate helpfulness with scope expansion. If an adjacent issue
is discovered, record it, determine whether it belongs to the current node, and
leave it unchanged when out of scope. Add it to `BACKLOG.md` when appropriate.
Do not refactor unrelated code, redesign architecture, rename unrelated
objects, change public APIs or schemas without authorization, alter financial
behavior without authorization, or remove compatibility behavior without
authorization.

## 5. Stop Conditions

Stop and report `NEEDS_DECISION` when a required business rule is undefined,
specifications conflict, ownership or authority is unclear, an architectural
decision is unapproved, or a financial, security, compliance, identity, or
public-contract boundary would change unexpectedly. Report `BLOCKED` when
required files, dependencies, environment, migration state, or tests cannot be
verified. Report `PARTIAL` when authorized work or verification is incomplete.
Never invent a rule merely to complete a task.

## 6. Formal Specification Law (MANDATORY)

AFCON360 behavior MUST be specified before implementation whenever a change
introduces or alters a business rule, invariant, workflow, lifecycle, state
transition, permission boundary, ownership rule, financial guarantee,
compliance obligation, or externally observable contract.

Before implementation, establish the affected entities, state variables, inputs,
outputs, invariants, failure conditions, valid transitions, ownership and
authority boundaries, initiator, approver, rejector, retry authority, reversal
authority, and observation/read authority. Resolve conflicting interpretations
before implementation; do not use legacy behavior, convenience, agent
preference, or passing tests as implicit authorization. Link relevant
specifications from owning module documentation, update `README.md` for
cross-module rules where appropriate, and add tests for transitions, invariants,
authorization, and negative cases.

## 7. Evidence-First Engineering

Every completed graph node must report evidence appropriate to its purpose:
node and authorized scope, actual files changed, significant behavior or
architectural impact, commands/tests and results, contract or invariant checks,
remaining risks, unverified assumptions, and deferred work. Completion status
must be one of `PASS`, `PARTIAL`, `BLOCKED`, `NEEDS_DECISION`, or `FAIL`.
Do not report `PASS` merely because code was written.

## Architecture Overview

**AFCON360** is a modular Flask application using a modular architecture for managing events, wallets, transport, and identity. It's an enterprise-grade platform for tournament management, accommodation, transport, wallet services, and fan engagement.

### Core Stack
- **Backend:** Flask 3.1.2 with application factory pattern
- **Database:** SQLAlchemy 2.0.44 with PostgreSQL (Alembic migrations)
- **Async:** Celery 5.4.0 with Redis 7.1.0 broker
- **Auth:** Flask-Login with role-based access control (RBAC)
- **Caching:** Redis via Flask-Caching and lazy-loaded LazyRedis client
- **Rate Limiting:** Flask-Limiter with Redis backend
- **Validation:** Pydantic 2.10.0
- **Testing:** pytest 8.3.0
- **External Services:** AWS (S3/OCR), Flutterwave, Paystack, PayPal, NIRA (KYC)
- **Environment:** Windows / PowerShell (use `;` instead of `&&` for command chaining)

---

## 1. The Dual ID System ⚠️ CRITICAL CONCEPT

**This codebase uses TWO IDs for every database entity**:

```python
class User(UserMixin, ProtectedModel):
    id = Column(BigInteger, primary_key=True)        # ← INTERNAL, never expose
    public_id = Column(String(64), unique=True)      # ← UUID, for APIs/URLs
```

### Rule
- **Internal ID (`id`)**: Used ONLY for database relations, foreign keys, joins. Never expose in APIs or URLs.
- **Public ID (`public_id`)**: Used for Flask-Login sessions, REST APIs, URLs, human-visible identifiers.

### Impact on Development
- When writing queries: filter by `public_id` when accepting external input
- When creating relations: use `id` for ForeignKey definitions
- Flask-Login: `current_user.public_id` for session tracking
- URL routes: `/user/<public_id>` pattern
- Never serialize raw `id` in API responses

**See**: `/app/identity/models/user.py:25-45`

---

## 2. Reference Documents (Read First!)

Before implementing a feature or fix, use the task class and affected scope to
load only the relevant reference documents:
- **`DATABASE_SCALABILITY_ROADMAP.md`** — when touching database schema, types, or migrations
- **`static/MOBILE_OPTIMIZATION.md`** — when adding or modifying HTML, Jinja, or CSS
- **`app/Documentation/IDENTITY_POLICIES.md`** — when working with user or organisation data
- **`app/accommodation/AFCON360_SEAMLESS_BOOKING_SPEC.md`** — when changing accommodation checkout, guest roster, payment, or event-assignment code
- **`app/Documentation/`** and **`Readme's/`** — when the affected module or task requires their domain guidance

---

## 3. Core Architectural Rules (NON-NEGOTIABLE)

### Base Models
- All models MUST inherit from `app.models.base.BaseModel`, not `db.Model` directly.
- All internal IDs: `BigInteger`
- All external IDs: `UUID`

### Identity Separation (CRITICAL)
- **Internal references/FKs**: Use `user.id` (BigInteger) for database relations only.
- **External/API references**: Use `user.public_id` (UUID) for all public exposure.
- **RULE**: Never expose `user.id` externally. See `app/Documentation/IDENTITY_POLICIES.md` for complete rules.
- **ENFORCED**: Use `app.utils.id_guard` to protect against incorrect ID assignments.

### Wallet Logic (HIGH RISK)
- **Treat any changes to `app/wallet` as HIGH RISK** — be extremely conservative
- Double-entry ledger — every debit must have a matching credit
- NEVER modify `app/wallet/models/` without explicit user approval
- All transactions require idempotency keys via `app.utils.idempotency`
- Always `db.session.rollback()` in wallet error handlers
- AML checks: `app/compliance/aml_service.py` — changes require compliance review

### Database Types
- **NO PostgreSQL ENUM types** — use `db.String` columns with application-level validation
- Existing ENUM columns must be migrated to String columns using expand-contract pattern
- See `DATABASE_SCALABILITY_ROADMAP.md` for full migration plan
- CHECK constraints must be added for String columns replacing ENUMs

### Circular Imports
- Be cautious of circular imports, especially between `identity` and feature modules
- Test imports with `python -c "from app import create_app"`

### PostgreSQL-only testing and SQLAlchemy query contract
- PostgreSQL is the only supported database backend for application and pytest
  execution; never add SQLite fallbacks or in-memory database fixtures.
- Tests must use the shared `TestingConfig`/pytest fixtures and a dedicated,
  migration-managed `TEST_DATABASE_URL` database.
- Tests must fail fast when PostgreSQL is unavailable or the schema is stale;
  do not hide database failures with skip flags.
- New application and test code must use SQLAlchemy models or expressions,
  never handwritten SQL strings or direct `text()` statements. Schema changes
  belong in reviewed Alembic migrations, not in test setup.
- The formal contract is `docs/POSTGRES_TESTING_CONTRACT.md`; update it when
  changing this behavior.
- Direct SQL tests are not supported. For PostgreSQL-specific behavior, use
  SQLAlchemy model/Core expressions (`select`, `func`, `inspect`, reflected
  tables) so SQL is generated for the configured PostgreSQL dialect. A test
  may be database-free only when marked as a source/parser/configuration check;
  persistence tests must use the PostgreSQL fixture.

---

## 4. Blueprint Map (Module Structure)

Key modules and their locations — stay within the relevant subtree:

| Module | Purpose | Location | Risk Level |
|--------|---------|----------|-----------|
| **auth** | Authentication, OTP, email verification, onboarding | `app/auth/` | Low |
| **identity** | User/Organization identity, roles, permissions, KYB | `app/identity/` | High |
| **wallet** | Double-entry ledger, transfers, withdrawals, webhooks | `app/wallet/` | **CRITICAL** |
| **accommodation** | Property listings, bookings, state machine | `app/accommodation/` | Medium |
| **transport** | Drivers, vehicles, routes, fleet management | `app/transport/` | Medium |
| **events** | Event lifecycle, registrations, attendee payments | `app/events/` | High |
| **admin** | Admin, super_admin, owner, moderator, support, auditor | `app/admin/` | High |
| **kyc** | KYC submissions, document verification | `app/kyc/` | High |
| **profile** | User profiles, KYC immutable fields | `app/profile/` | Medium |
| **compliance** | AML service | `app/compliance/` | High |
| **audit** | Forensic audit service, compliance logging | `app/audit/` | High |
| **media** | File upload/storage (local + OCI) | `app/media/` | Medium |
| **fan** | Fan-specific models and routes | `app/fan/` | Low |
| **tasks** | Celery tasks (webhook processor, reconciliation) | `app/tasks/` | High |

---

## 5. Coding Standards

### Imports
- Use absolute imports: `from app.auth.models import User`
- Test imports with: `python -c "from app import create_app"`

### Relationships
- Explicitly check for existing `backref` names in the same model file to avoid startup crashes
- Use `id` (BigInteger) for ForeignKey definitions, never `public_id`

### Migrations (CRITICAL PROTOCOL)
- **NEVER create, generate, write, or patch migration files manually**
- **NEVER run `flask db migrate` or `flask db upgrade` automatically**
- **The user handles all migrations manually** — propose commands only
- **Let Alembic auto-generate migration files** when the user runs `flask db migrate`
- **Never patch migration files** as workarounds — fix root causes in model/source files
- **Do NOT run `flask db migrate` automatically** — always propose it to the user first
- Follow the **Migration Agent Protocol** below to prevent multiple-head divergence

### Migration Agent Protocol (Alembic Head Management)

To prevent "multiple heads" fragmentation, ALL agents MUST follow this protocol:

#### Core Principles
- **Short revision IDs:** Keep under 32 characters (PostgreSQL limit is 63 bytes). Use timestamp IDs: `20260706_2018`
- **Single-head enforcement:** Before creating any new migration, run `flask db heads`. If >1 head exists, merge first.
- **Auto-merge:** Run `flask db merge heads -m "merge_<date>"` to collapse heads into linear history
- **Never patch migrations:** Fix root causes in models. Never edit a generated migration as workaround.
- **Propose, don't auto-migrate:** `flask db migrate` must be proposed to user. Scripts handle `flask db revision` and head-merging only.

#### Tooling
- `scripts/migration_agent_config.py` — central config: `MAX_REVISION_LENGTH`, `AUTO_MERGE_HEADS`, etc.
- `scripts/create_migration.py` — run `python scripts/create_migration.py "message"` to safely create revision with short ID

#### Pre-Migration Checklist
1. Run `flask db heads` — confirm exactly one head
2. If multiple heads: `flask db merge heads -m "merge_<date>"` then `flask db upgrade`
3. **Register new models in `app/core/model_registry.py`** if any were added
4. Create revision via `python scripts/create_migration.py "description"` (uses short timestamp ID)
5. Review generated migration file for correctness before proposing `flask db upgrade` to user

#### Quick Reference — Common Issues
| Problem | Solution |
|---------|----------|
| Multiple heads | `flask db merge heads -m "merge_branches"` |
| Revision ID too long | Edit file, set `revision = 'short_id'` (under 32 chars) |
| Migration fails | `flask db stamp <head_id>` then fix root cause |
| Confused state | `flask db current` and `flask db heads` to inspect |

---

## 6. Environment Configuration (Layered)

**Critical for running locally vs Docker vs production**:

```
.env              ← Base defaults (shared, safe)
.env.{APP_ENV}    ← Environment overrides (secrets, DB URLs)
```

### Setup
```bash
export APP_ENV=local    # Loads .env + .env.local
export APP_ENV=docker   # Loads .env + .env.docker
export APP_ENV=prod     # Loads .env + .env.prod
```

Key variables:
```
APP_ENV=local|docker|prod           # Controls which .env.X is loaded
FLASK_ENV=development|production    # Flask mode
DATABASE_URL=postgresql://...       # Auto-detected per APP_ENV
REDIS_URL=redis://...               # Caching and Celery broker
ENCRYPTION_KEY=...                  # Set BEFORE app init (in create_app)
DISABLE_REDIS=false                 # Redis is optional; set true to disable
```

**Why it matters**: `config.py` uses `_load_env()` to bootstrap, then `get_config()` returns layered Config class. DO NOT check encrypted values at module level—they load in `create_app()`.

**See**: `/app/config.py:31-67`, `/app/__init__.py:24-43`

---

## 7. Database Conventions

### Base Model Architecture
All entities inherit from `BaseModel` (or `ProtectedModel` which wraps it):

```python
class BaseModel(TimestampMixin, db.Model):
    id = Column(BigInteger, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at = Column(DateTime, onupdate=datetime.utcnow, server_default=func.now())
    is_deleted = Column(Boolean, default=False)      # Soft delete
    deleted_at = Column(DateTime, nullable=True)
```

### Soft Delete Pattern
```python
record.soft_delete()  # Marks is_deleted=True, doesn't remove from DB
record.restore()      # Reverts soft delete
```

**Always filter queries**: `Model.query.filter(Model.is_deleted == False)`

### Model Registration for Alembic Autodetection
**CRITICAL:** Alembic `autogenerate` can only detect schema changes for models that are loaded into SQLAlchemy's `MetaData` before `db.init_app()` is called.

**Required steps when adding ANY new model:**
1. **Register in `app/core/model_registry.py`** — Add an explicit import for the new model in `register_all_models()`. This is the single source of truth for model loading.
2. **Export from domain `__init__.py`** — If the model lives in a domain package (e.g., `app/accommodation/models/`), ensure it is exported from that package's `__init__.py`.
3. **Verify with `flask db migrate`** — After updating the registry, run `flask db migrate` to confirm Alembic detects the new table/column. If it doesn't appear, the model is not properly registered.

**Why this matters:** Models that are only imported lazily inside route handlers or service methods are invisible to Alembic's schema comparison. The `register_all_models()` function runs BEFORE `db.init_app(app)` in `app/__init__.py:579-580`, ensuring all tables are present in `db.metadata` at migration time.

**See**: `app/core/model_registry.py`, `app/__init__.py:579-580`

### Property Naming Safety
**NEVER name a `@property` the same as a Column field**. Use suffixes:
- `_flag` (boolean computed property)
- `_status` (derived status)
- `_computed` (any other computation)

Example ❌ BAD:
```python
@property
def is_verified(self):  # ← Conflicts with Column!
    return self.email_verified and self.phone_verified
```

Example ✅ GOOD:
```python
@property
def is_verified_status(self):  # ← Safe
    return self.email_verified and self.phone_verified
```

**See**: `/app/models/base.py:1-19`

---

## 8. API Endpoint Patterns

Standard Flask blueprint + role-based access:

```python
from flask import Blueprint, jsonify
from flask_login import login_required, current_user

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/wallet/balance', methods=['GET'])
@login_required
def get_balance():
    """Get wallet balance for current user"""
    if not current_user.has_role('owner', 'fan'):
        return jsonify({'error': 'Forbidden'}), 403
    
    wallet = Wallet.query.filter_by(user_id=current_user.id).first()
    return jsonify({'balance': wallet.balance, 'user': current_user.public_id})
```

### Key Patterns
- **Filter by `id` internally, but serialize `public_id`** in responses
- **Use `@login_required`** to enforce authentication
- **Check roles via `current_user.has_role()`** or `current_user.is_super_admin`
- **Always return `public_id` in API responses**, never raw `id`
- **Validate soft-delete status**: Query explicitly with `is_deleted=False`

**See**: `/app/api/health.py`, `/app/routes.py:14-68`

---

## 9. Async Tasks with Celery

Celery tasks handle long-running operations (webhooks, media processing, reconciliation).

### Task Definition Pattern
```python
# app/tasks/webhook_processor.py
from celery import shared_task
from tenacity import retry, stop_after_attempt, wait_exponential

@shared_task(bind=True, max_retries=3)
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def process_webhook_event(self, event_id: int):
    """Process a payment webhook event with idempotency and retry logic"""
    from app.wallet.models import WebhookEvent
    
    event = WebhookEvent.query.filter_by(id=event_id).first()
    if not event or event.is_processed:
        return  # Idempotency check
    
    try:
        # Process payment
        provider_reference = event.data.get('reference')
        if not Transaction.query.filter_by(provider_reference=provider_reference).first():
            # Prevent double-credits
            transaction = Transaction.create(...)
        event.mark_processed()
        db.session.commit()
    except Exception as exc:
        self.retry(exc=exc, countdown=5)
```

### Starting Workers
```bash
# Single worker (dev)
celery -A app.celery_app worker --loglevel=info

# With beat scheduler (periodic tasks)
celery -A app.celery_app beat --loglevel=info

# Combined (dev only)
celery -A app.celery_app worker --beat --loglevel=info
```

### Key Patterns
- **Idempotency**: Check if task already ran (using unique reference IDs like `provider_reference`)
- **Exponential backoff**: Use `tenacity` library for retry logic
- **App context**: Tasks automatically bind Flask app context via `ContextTask` in `make_celery()`
- **Serialization**: Config uses JSON (not pickle) for security
- **Beat schedule**: Defined in `celery_app.py:beat_schedule`

**See**: `/app/celery_app.py`, `/app/tasks/webhook_processor.py`

---

## 10. Middleware & Request Lifecycle

The app registers multiple `@app.before_request` hooks to manage:

1. **Module reloading** (`/app/middleware/reload_modules.py`): Dynamically enable/disable features via `ModuleToggleService`
2. **Session lifecycle**: Flask-Session with Redis backend (layered cookie if Redis fails)
3. **Rate limiting**: Applied via Flask-Limiter decorators
4. **Security headers**: CSP, X-Frame-Options, etc. (consolidated in single `after_request` handler)
5. **ID Guard validation**: Runtime ID mixing protection

### Example: Module Toggle Middleware
```python
@app.before_request
def check_module_toggle():
    """Reload module status on each request (allows hot-disabling)"""
    if request.path.startswith('/api/accommodation/'):
        if not ModuleToggleService.is_module_enabled('accommodation'):
            return jsonify({'error': 'Module disabled'}), 503
```

**See**: `/app/__init__.py:398-420`, `/app/middleware/reload_modules.py`

---

## 11. Critical Developer Workflows

### Local Development Setup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment
export APP_ENV=local
export FLASK_ENV=development

# 3. Initialize database (first time)
flask db upgrade

# 4. Run development server
python app.py

# 5. In another terminal, start Celery worker
celery -A app.celery_app worker --loglevel=info
```

### Database Migrations
```bash
# Create a new migration
flask db migrate -m "add user_tier column"

# Review migration in migrations/versions/
# (Alembic auto-generates, but you should review)

# Apply migration
flask db upgrade

# Rollback one migration
flask db downgrade
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_auth.py

# Coverage report
pytest --cov=app tests/
```

### Debugging
- **Enable path debug**: `export SHOW_PATH_DEBUG=true && python app.py`
- **Log levels**: Set `LOG_LEVEL=DEBUG` in .env to see detailed logs
- **Check Redis connection**: `redis-cli ping` (should return PONG)
- **Check Celery**: `celery -A app.celery_app inspect active`

### Common Issues
| Issue | Solution |
|-------|----------|
| `Redis connection refused` | Set `DISABLE_REDIS=true` or start Redis (`redis-server`) |
| `Encryption key not set` | Add `ENCRYPTION_KEY` to .env or .env.local BEFORE starting |
| `Module toggle not working` | Check `SystemSetting` table in DB for `module_enable_*` keys |
| `Celery tasks not running` | Ensure Redis is running, worker is started, and broker URL matches |
| `ID Guard error: String FK` | Check for non-UUID fields in relationships; may need to add to `NON_FK_STRING_IDS` in `base.py` |

---

## 12. Project-Specific Conventions

### Naming Patterns
- **Table names**: Plural, lowercase (`users`, `accommodations`, `transactions`)
- **Route prefixes**: `/api/<module>/<resource>` or `/<module>/<page>`
- **Blueprints**: Snake_case with `_bp` suffix (`user_bp`, `auth_routes`)
- **Database columns**: Snake_case (`password_hash`, `created_at`, `public_id`)
- **Python vars**: Snake_case for everything

### Role Hierarchy
```python
# Defined in app/identity/models/roles_permission.py
owner = 1           # Highest privilege (system administrator)
super_admin = 2
admin = 3
moderator = 4
organizer = 5
fan = 6
```

### Import Style
Use absolute imports from project root:
```python
from app.identity.models.user import User
from app.wallet.models.transaction import Transaction
from app.extensions import db, cache, redis_client
```

### Error Handling
- Return Flask `jsonify()` for APIs (JSON responses)
- Use `abort()` for standard HTTP errors: `abort(404)`, `abort(403)`, `abort(500)`
- Log errors with context: `logger.error(f"Task failed for user {user_id}: {e}", exc_info=True)`

### Security Rules
1. **NEVER** expose raw `id` in APIs or URLs—use `public_id`
2. **ALWAYS** validate user ownership before returning sensitive data
3. **ALWAYS** set `ENCRYPTION_KEY` before starting the app
4. **Use parametrized queries** (SQLAlchemy ORM prevents SQL injection)
5. **Validate payment idempotency** with `provider_reference` to prevent double-charges

---

## 13. Key Files to Understand

| File | Purpose |
|------|---------|
| `/app/__init__.py` | App factory, extension initialization, middleware setup |
| `/app/config.py` | Layered config system, environment validation |
| `/app/extensions.py` | Shared Flask extensions (db, cache, limiter, redis_client) |
| `/app/celery_app.py` | Celery factory, beat schedule, task routing |
| `/app/models/base.py` | BaseModel, ProtectedModel, soft-delete patterns |
| `/app/identity/models/user.py` | User model (Dual ID system, roles, auth methods) |
| `/app/identity/models/roles_permission.py` | Role/permission helpers |
| `/app/services/module_toggle_service.py` | Dynamic feature flag management |
| `/app/utils/id_guard.py` | Runtime ID mixing protection |
| `/app/routes.py` | Blueprint registration (entry point for all modules) |

---

## 14. External Dependencies & Integrations

### Payment Providers
- **Flutterwave**: Webhook processing, payout management
- **Paystack**: Transaction handling, settlement
- **PayPal / Alipay / WeChat Pay / Mobile Money**: Various payment methods
- **Visa**: Card payments

### Verification Services
- **NIRA**: Ugandan national ID verification for KYC
- **AWS S3**: Media storage and OCR (document processing)
- **OCI (Oracle Cloud Infrastructure)**: Alternative storage backend

### Infrastructure
- **Redis**: Session storage, caching, Celery broker
- **PostgreSQL**: Primary database
- **Alembic**: Migration management

---

## 15. Role System (Strictly Hierarchical, 15 Roles)

From highest to lowest privilege:
`owner` → `super_admin` → `admin` → `auditor` → `compliance_officer` → `moderator` → `support` → `event_manager` → `transport_admin` → `wallet_admin` → `accommodation_admin` → `tourism_admin` → `org_admin` → `org_member` → `user`

### Key Files
- `app/auth/decorators.py` — `@admin_required`, `@require_role('name')`, `@owner_only`
- `app/auth/roles.py` — role definitions and hierarchy
- `app/auth/policy.py` — permission policy enforcement

### Critical Constraints
- **Owner cannot be deleted, impersonated, or self-modified**
- **Super admin cannot modify other super admins or the owner**
- All role changes MUST be audit-logged
- Global Persona Switcher: session tracks `active_role` — all permission checks must respect it

---

## 16. Module Toggle System

Modules (events, accommodation, transport, wallet, tourism, tournament) can be enabled/disabled at runtime:
- **Guard decorator:** `@module_required('module_name')` in `app/utils/module_guard.py`
- **Toggle service:** `app/services/module_toggle_service.py`
- **State stored in:** `SystemConfig` model (`app/models/system_config.py`)
- **ALWAYS PRESERVE** `@module_required` on existing routes — never remove it without instruction
- **New routes** in gated modules must inherit the module guard

---

## 17. Forensic Audit & Compliance

All sensitive actions must be logged using the forensic audit service:

### Key Components
- **Service:** `app/audit/forensic_audit.py` — `log_attempt()`, `log_completion()`, `log_blocked()`
- **Audit tables carry:** `attempted_at`, `status`, `ip_address`, `user_agent`, `session_id`, `correlation_id`, `risk_score`
- **What to log:**
  - Role changes → `OwnerAuditLog`
  - Wallet transactions → `ForensicAuditService`
  - KYC changes → `ForensicAuditService`

### Compliance Requirements
- **Bank of Uganda:** KYC timelines enforcement
- **FIA Uganda:** Transactions > UGX 20M must be flagged

### Known Issues
- `owner_audit_logs.is_deleted` may be absent — always wrap queries on this table in try/except

---

## 18. UI/Templates Standards

### Mobile-First Responsive Design (MANDATORY)
All HTML, Jinja templates, and CSS must be optimized for mobile devices (phones ≤480px, tablets 481px–1024px) before submission. This is not optional.
- **No fixed-width layouts** that overflow on 320px viewports
- **No fixed `min-width` constraints** on interactive components that cause horizontal scroll
- **All touch targets** must be ≥44×44px (WCAG minimum)
- **Use `clamp()`** for fluid typography and spacing instead of fixed `px` values
- **Use `repeat(auto-fit, minmax(...))`** for responsive grids instead of hardcoded column counts
- **Safe-area insets**: Use `env(safe-area-inset-bottom)` on fixed/sticky elements for notched phones
- **Inline styles are forbidden** on layout containers; extract to CSS classes

### Template Conventions
- Use `{{ csrf_token() }}` for CSRF protection in all forms
- For AJAX/Pane loads, check for `?_pane=1` conditionals in `base.html`
- Avoid `overflow: hidden` on containers that hold dropdowns (causes clipping issues)

### Content Security Policy and JavaScript
- The application enforces a per-request Content Security Policy nonce through `app/__init__.py` (`g.csp_nonce` and the `csp_nonce` template variable).
- Put page behavior in external files under `static/js/` and load them with `<script src="{{ url_for('static', filename='...') }}"></script>`; same-origin external scripts are permitted by the CSP without an inline nonce.
- Do not use inline event handlers such as `onclick` or page behavior in inline `<script>` blocks. Use `data-*` attributes and event listeners in the external module instead.
- Inline executable scripts are permitted only when unavoidable and must include `nonce="{{ csp_nonce }}"`; JSON-LD script blocks must also carry the nonce.

### Frontend Documentation Update (CONDITIONAL)
When adding or modifying **any** HTML template, Jinja template, or CSS file,
open `static/MOBILE_OPTIMIZATION.md` and update it only when the frontend
change affects the documented file tree, responsive behavior, styling,
branding, verification state, or isolation plan. A content-only, non-layout
change may require only a focused review and no documentation entry.

If the file is updated, record the changed file under **Change Log by File**;
update **File Tree**, **Verification Checklist**, or **Future Optimization
Isolation Plan** only when those sections actually changed. Failure to assess
the applicable frontend impact is a review issue; an unchanged frontend record
does not require a no-op edit.

---

## 19. Directory Structure & Subtree Usage

### Subtree Focus (IMPORTANT)
When working on a specific module (e.g., `app/events`), ALWAYS prefer staying within that subtree to:
- Minimize context pollution
- Avoid unintended side effects in other modules
- Use the `--subtree-only` flag if using Aider

### Key Directories
- **Architectural docs:** `app/Documentation/` and `Readme's/`
- **Scripts:** `scripts/` — utility scripts for database audits, migrations, setup
- **Tests:** `tests/` — test suite

---

## 20. Standard Utilities (Prefer Over Custom Solutions)

Use existing utilities in `app/utils/` instead of rolling custom:

| Utility | Purpose | Location |
|---------|---------|----------|
| **ID Guard** | Protect against incorrect ID assignments | `app.utils.id_guard` |
| **Module Guard** | Enforce module-level access control | `app.utils.module_guard` |
| **Idempotency** | Critical operations (wallet, bookings) | `app.utils.idempotency` |
| **Validators** | Common data validation patterns | `app.utils.validators` |
| **Audit** | Log sensitive actions | `app.utils.audit` |

---

## 21. Prohibited Actions (NO EXCEPTIONS)

❌ Do NOT change `BaseModel` or shared base classes without explicit approval  
❌ Do NOT modify `app/wallet/models/` without explicit instructions  
❌ Do NOT add new PostgreSQL ENUM types  
❌ Do NOT run destructive database commands without verification  
❌ Do NOT expose `user.id` (BIGINT) in API responses, logs, or templates — use `public_id` instead  

---

## 22. Quality Standards (Pre-Submission Checklist)

Before submitting any work, verify:
- [ ] All models inherit from `BaseModel` (not `db.Model`)
- [ ] All internal IDs use `BigInteger`; external IDs use `UUID`
- [ ] No `user.id` exposed in API responses, templates, or logs
- [ ] No PostgreSQL ENUM types in new code
- [ ] All migrations tested on copy of production-like data
- [ ] Rollback plan documented for every schema change
- [ ] CHECK constraints added for String columns replacing ENUMs
- [ ] All tests pass before considering work complete
- [ ] Code follows existing patterns in the module (subtree focus)
- [ ] No circular imports introduced
- [ ] Wallet logic maintains double-entry ledger constraints
- [ ] **Frontend changes are mobile-responsive** (phones ≤480px, tablets ≤1024px)
- [ ] Frontend impact assessed; update `static/MOBILE_OPTIMIZATION.md` only if the change affects its documented scope

---

## 23. Pre-Implementation Checklist

Before writing code, load only the applicable guidance:
1. Read the relevant section of `DATABASE_SCALABILITY_ROADMAP.md` if touching database schema
2. Read `static/MOBILE_OPTIMIZATION.md` if the frontend change affects documented responsive/layout behavior
3. Read `app/Documentation/IDENTITY_POLICIES.md` if working with user/organisation data
4. Check for existing `backref` names in the target model file
5. Verify the module's existing patterns and conventions
6. Confirm no circular imports will be introduced
7. Plan migration strategy if schema changes are needed

---

## 24. Post-Implementation Verification

After completing work, verify proportionally to the task class and changed
scope. Run the affected module suite for substantive changes; use focused
checks for trivial or local changes. Apply identity, model, ENUM, migration,
frontend, and rollback checks only when those concerns are in scope.

---

## 25. Post-Change Report Format

After every implementation, provide a concise completion report, expanding it
with the full evidence fields below for behavioral, architectural, or
high-risk work:
- **Files changed:** list every file modified
- **What was done:** 2–3 sentence summary
- **What changed / improved:** explicitly state what behavior changed, what bug was fixed, or what feature was added
- **Migration needed?** yes/no — if yes: propose the exact `flask db migrate` / `flask db upgrade` commands, but do NOT run them automatically
- **Manual steps:** anything that cannot be automated (env vars, server restarts, seed scripts, etc.)
- **Risks/conflicts:** flag anything that could break existing behavior, circular imports, or convention violations
- **Verification:** how to confirm the fix works (test command, manual steps, or both)
- **Frontend documentation:** if HTML/CSS/Jinja was touched, report whether its documented scope was affected; do not make a no-op update

---

## 26. Ignore List (Context Management)

When exploring the project, ignore these to avoid context pollution:
- `**/__pycache__/**`
- `**/.venv/**`
- `**/backups_today/**`
- `**/model_backups/**`
- `**/templates_backup/**`
- `**/flask_session/**`
- `**/*.pyc`
- `**/node_modules/**`
- `**/docker/nginx/*.conf` (unless working on infra)
- `**/migrations/versions/*.py` (unless reviewing schema history)
- `backup_*.json`
- `app.py.backup`
- `docker-compose.yml.backup`

---

## 27. Quick Reference: Common Tasks

### Add a New API Endpoint
1. Create route in `app/<module>/routes.py`
2. Filter by `public_id` when accepting external input
3. Serialize response with `public_id`, never raw `id`
4. Add role check with `@login_required` + `current_user.has_role()`

### Add a New Model
1. Inherit from `BaseModel` or `ProtectedModel`
2. Define `__tablename__` and indexes/constraints
3. Add `public_id` field if user-facing
4. Keep `@property` names distinct from columns (use suffixes)

### Add a New Async Task
1. Create in `app/tasks/<module>.py`
2. Use `@shared_task` decorator
3. Add idempotency check (unique reference)
4. Register in `app/celery_app.py:include`

### Add a New Environment Variable
1. Add to `.env` (base defaults, safe)
2. Add to `.env.{APP_ENV}` (overrides)
3. Reference in `app/config.py` via `os.getenv()`
4. Validate in `get_config()` if security-critical

---

## Resources
- Flask docs: https://flask.palletsprojects.com/
- SQLAlchemy docs: https://docs.sqlalchemy.org/
- Celery docs: https://docs.celeryproject.io/
- Alembic docs: https://alembic.sqlalchemy.org/
- agents.md guide: https://agents.md/

---

**Last Updated**: July 2026 | **AFCON360 v0.1.0**

**Note**: This is the authoritative consolidated AGENTS.md. A copy is maintained in `.junie/AGENTS.md` for tool-specific integration. Both reference the same standards.

---

## 28. Command Success Evaluation

When running Python/Flask verification commands:
- **Exit code 0 = SUCCESS**, regardless of stderr content
- Only treat as failure if: exit code != 0, OR stderr contains "ERROR", "Exception", "Traceback"
- INFO/WARNING/DEBUG logs in stderr do not indicate failure

**Canonical database verification command:**
```powershell
& .venv/Scripts/python.exe verify_db.py
```

Success criteria:
- Output contains `DB_VERIFY_OK`
- Exit code is `0`

Ignore all Flask startup INFO/WARNING/DEBUG logs.

---

## 29. Deferred Work Backlog (CONDITIONAL)

**File:** `BACKLOG.md` at the repository root.

Any agent (Code / Ask / Debug mode) MUST record work that is **identified but
NOT completed in the current session** yet still belongs in the system. If no
such work was identified, do not edit `BACKLOG.md`.

**When to add an entry (any of these):**
- Something was discussed/requested but is out of scope for today.
- A change was partially implemented and still needs finishing.
- Work is blocked (needs migration, another team, external sign-off, dependency).
- A feature needs review (e.g., finance/compliance/security sign-off) before go-live.
- You explicitly decide "not for today" (e.g., a larger feature like adding a new status enum).

**Rules:**
- When applicable, create the entry in `BACKLOG.md` (use the template at the top of that file) before ending your turn.
- Reference concrete files/routes/models so the next agent can pick it up.
- Do NOT remove an entry once it is resolved — instead mark its `Status:` as `Done` and add a `Resolved:` date.
- This applies to every agent mode; treat `BACKLOG.md` as an authoritative hand-off artifact alongside this guide.

**Example (already present in `BACKLOG.md`):** the cancellation refund/fine policy for post-check-in cancellations — implemented in logic but explicitly deferred for finance/compliance review.

















