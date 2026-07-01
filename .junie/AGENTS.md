# AFCON360 Project Guidelines

This file provides persistent guidance for AI agents working on the AFCON360 codebase. Treat this as the authoritative source for all implementation decisions. Agents must read and follow these rules without exception.

## Key Reference Documents

Before implementing any feature or fix, consult these documents:
- **`DATABASE_SCALABILITY_ROADMAP.md`** — Complete ENUM migration plan, current database state, and scalability principles
- **`app/Documentation/IDENTITY_POLICIES.md`** — Identity separation rules, BIGINT vs UUID enforcement, and security requirements
- **`app/Documentation/`** — Additional architectural documentation
- **`Readme's/`** — Implementation reports and system analysis

## Project Overview

AFCON360 is a modular Flask application using a modular architecture for managing events, wallets, transport, and identity.

## Tech Stack
- **Backend:** Flask 3.1.2
- **Database:** SQLAlchemy 2.0.44 (PostgreSQL)
- **Migrations:** Alembic / Flask-Migrate
- **Task Queue:** Celery 5.4.0 with Redis 7.1.0
- **Validation:** Pydantic 2.10.0
- **Testing:** pytest 8.3.0
- **Environment:** Windows / PowerShell (Ensure commands are compatible)

## Core Architectural Rules
- **Base Models:** All models MUST inherit from `app.models.base.BaseModel`, not `db.Model` directly.
- **Identities:** 
    - Internal references/FKs: Use `user.id` (BigInteger).
    - External/API references: Use `user.public_id` (UUID).
    - **CRITICAL:** Never expose `user.id` externally. See `app/Documentation/IDENTITY_POLICIES.md` for complete identity separation rules. All agents must enforce this without exception.
- **Wallet Logic:** Treat any changes to `app/wallet` as **HIGH RISK**. Be extremely conservative and ensure double-entry ledger constraints are maintained.
- **PostgreSQL Types:** Do NOT use PostgreSQL ENUM types. Use `db.String` columns with application-level validation. Existing ENUM columns must be migrated to String columns using the expand-contract pattern. See `DATABASE_SCALABILITY_ROADMAP.md` for the full migration plan.
- **Circular Imports:** Be cautious of circular imports, especially between `identity` and feature modules.

## Coding Standards
- **Imports:** Use absolute imports (e.g., `from app.auth.models import User`).
- **Relationships:** When adding relationships, explicitly check for existing `backref` names in the same model file to avoid startup crashes.
- **Migrations:** 
    - Never patch migration files as workarounds. Fix root causes in model/source files.
    - Do NOT run `flask db migrate` automatically; always propose it to the user first.
- **UI/Templates:**
    - Use `{{ csrf_token() }}` for CSRF protection in forms.
    - For AJAX/Pane loads, check for `?_pane=1` conditionals in `base.html`.
    - Avoid `overflow: hidden` on containers that hold dropdowns.

## Directory Structure & Subtree usage
- **Subtree focus:** When working on a specific module (e.g., `app/events`), ALWAYS prefer staying within that subtree to minimize context pollution and avoid unintended side effects in other modules. Use the `--subtree-only` flag if using Aider.
- **Documentation:** Key architectural docs are in `app/Documentation/` and `Readme's/`.
- **Scripts:** Utility scripts for database audits, migrations, and setup are in `scripts/`.

## Environment Specifics
- **Shell:** Current terminal is PowerShell. Use `;` instead of `&&` for command chaining.
- **Line Endings:** Be careful with CRLF vs LF, especially in `docker-entrypoint.sh`.

## Prohibited Actions
- Do NOT change `BaseModel` or shared base classes without explicit approval.
- Do NOT modify `app/wallet/models/` without explicit instructions.
- Do NOT add new PostgreSQL ENUM types.
- Do NOT run destructive database commands without verification.
- Do NOT expose `user.id` (BIGINT) in API responses, logs, or templates. Use `user.public_id` (UUID) instead.

## Standard Utilities
Prefer using existing utilities in `app/utils/` instead of rolling custom solutions:
- **ID Guard:** Use `app.utils.id_guard` to protect against incorrect ID assignments.
- **Module Guard:** Use `app.utils.module_guard` to enforce module-level access control.
- **Idempotency:** Use `app.utils.idempotency` for critical operations like wallet transactions or booking confirms.
- **Validators:** Check `app.utils.validators` for common data validation patterns.
- **Audit:** Use `app.utils.audit` to log sensitive actions.

## Quality Standards
Agents must deliver exceptionally high quality code. Before submitting any work:
- [ ] All models inherit from `BaseModel` (not `db.Model`)
- [ ] All internal IDs use `BigInteger`; external IDs use `UUID`
- [ ] No `user.id` exposed in API responses, templates, or logs
- [ ] No PostgreSQL ENUM types in new code
- [ ] All migrations tested on copy of production-like data
- [ ] Rollback plan documented for every schema change
- [ ] CHECK constraints added for String columns replacing ENUMs
- [ ] All tests pass before considering work complete
- [ ] Code follows existing patterns in the module (subtree focus)

## Pre-Implementation Checklist
Before writing any code:
1. Read the relevant section of `DATABASE_SCALABILITY_ROADMAP.md` if touching database schema
2. Read `app/Documentation/IDENTITY_POLICIES.md` if working with user/organisation data
3. Check for existing `backref` names in the target model file
4. Verify the module's existing patterns and conventions
5. Confirm no circular imports will be introduced
6. Plan migration strategy if schema changes are needed

## Post-Implementation Verification
After completing work:
1. Run the full test suite for the affected module
2. Verify no `user.id` exposure in API responses
3. Confirm all new models inherit from `BaseModel`
4. Check that no new ENUM types were introduced
5. Validate that migrations are reversible
6. Ensure code follows the module's existing patterns

## Blueprint Map
Key modules and their locations — stay within the relevant subtree:
- `app/auth/` — login, registration, onboarding, KYC routes, role decorators
- `app/admin/` — admin, super_admin, owner, moderator, support, auditor sub-blueprints
- `app/events/` — event lifecycle, registrations, attendee payments
- `app/wallet/` — double-entry ledger, transfers, withdrawals, webhooks (**HIGH RISK**)
- `app/accommodation/` — property listings, bookings, state machine
- `app/transport/` — drivers, vehicles, routes, fleet management
- `app/identity/` — organisations, KYB, individual verification
- `app/profile/` — user profiles, KYC immutable fields
- `app/kyc/` — KYC submissions, document verification
- `app/audit/` — forensic audit service, compliance logging
- `app/compliance/` — AML service
- `app/fan/` — fan-specific models and routes
- `app/tasks/` — Celery tasks (webhook processor, reconciliation)

## Role System (15 Roles, Strictly Hierarchical)
From highest to lowest: `owner` → `super_admin` → `admin` → `auditor` → `compliance_officer` → `moderator` → `support` → `event_manager` → `transport_admin` → `wallet_admin` → `accommodation_admin` → `tourism_admin` → `org_admin` → `org_member` → `user`

Key files:
- `app/auth/decorators.py` — `@admin_required`, `@require_role('name')`, `@owner_only`
- `app/auth/roles.py` — role definitions and hierarchy
- `app/auth/policy.py` — permission policy enforcement

Constraints:
- Owner cannot be deleted, impersonated, or self-modified
- Super admin cannot modify other super admins or the owner
- All role changes must be audit-logged
- Global Persona Switcher: session tracks `active_role` — all permission checks must respect it

## Module Toggle System
Modules (events, accommodation, transport, wallet, tourism, tournament) can be enabled/disabled at runtime:
- Guard decorator: `@module_required('module_name')` in `app/utils/module_guard.py`
- Toggle service: `app/services/module_toggle_service.py`
- State stored in `SystemConfig` model (`app/models/system_config.py`)
- **Always preserve** `@module_required` on existing routes — never remove it without instruction
- New routes in gated modules must inherit the module guard

## Forensic Audit & Compliance
All sensitive actions must be logged using the forensic audit service:
- Service: `app/audit/forensic_audit.py` — `log_attempt()`, `log_completion()`, `log_blocked()`
- Audit tables carry: `attempted_at`, `status`, `ip_address`, `user_agent`, `session_id`, `correlation_id`, `risk_score`
- **What to log:** role changes → `OwnerAuditLog`; wallet transactions → `ForensicAuditService`; KYC changes → `ForensicAuditService`
- **Known issue:** `owner_audit_logs.is_deleted` may be absent — always wrap queries on this table in try/except
- Compliance requirements: Bank of Uganda (KYC timelines) + FIA Uganda (transactions > UGX 20M)

## Wallet Rules (HIGH RISK)
- Double-entry ledger — every debit must have a matching credit
- NEVER modify `app/wallet/models/` without explicit user approval
- All transactions require idempotency keys via `app.utils.idempotency`
- Always `db.session.rollback()` in wallet error handlers
- AML checks: `app/compliance/aml_service.py` — changes require compliance review
- Webhook processing is async Celery — changes to `app/tasks/webhook_processor.py` need extra care

## Post-Change Report Format
After every implementation, always provide:
- **Files changed:** list every file modified
- **What was done:** 2–3 sentence summary
- **Migration needed?** yes/no — if yes: `flask db migrate -m 'description'` ; `flask db upgrade`
- **Manual steps:** env vars, server restarts, seed scripts
- **Risks/conflicts:** anything that could break existing behavior

## Ignore List (Context Management)
When exploring the project, please ignore the following directories and patterns to avoid context pollution:
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
