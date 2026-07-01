# AFCON360 — Coding Rules (MUST FOLLOW)

## Models
- ALL models inherit from `BaseModel` (`app/models/base.py`) — NEVER use `db.Model` directly
- **Internal FK references**: use `BigInteger` → `user.id`
- **External/API references**: use `user.public_id` (UUID)
- **CRITICAL**: NEVER expose `user.id` (BigInt) in API responses, templates, or logs — always use `user.public_id`. See `app/Documentation/IDENTITY_POLICIES.md`
- NEVER add PostgreSQL ENUM types — use `String` columns with app-level validation + CHECK constraints
- Existing ENUM columns → migrate to String using expand-contract pattern (see `DATABASE_SCALABILITY_ROADMAP.md`)
- NEVER change `BaseModel` or any shared base classes
- When adding relationships, check for existing `backref` names in the same file first — duplicate backref names crash on startup
- Use absolute imports: `from app.auth.models import User` — not relative imports
- Be cautious of circular imports, especially between `identity` and feature modules

## Database / Migrations
- NEVER run `flask db migrate` automatically — always ask the user first
- Fix bugs in model/source files — NEVER patch migration files as workarounds
- NEVER modify `app/wallet/models/` without explicit user instruction (HIGH RISK)
- Migration report format: "Migration needed? yes — `flask db migrate -m 'description'` then `flask db upgrade`"

## Code Style
- One focused change at a time — do not refactor adjacent code unless instructed
- Preserve existing `backref` names — never rename them
- Use `db.session.rollback()` explicitly in route error handlers
- Use `current_app.logger` for logging — not `print()`
- All new routes need CSRF protection via Flask-WTF or `@csrf.exempt` with justification

## Security
- Role decorators: `@admin_required`, `@require_role('role_name')`, `@owner_only`
- NEVER skip permission checks on routes that modify data
- Wallet operations: always use idempotency keys and transaction rollback handling
- Never echo `.env` secrets in responses or logs

## Templates
- Extend `base.html` for all user-facing pages
- Use `url_for()` — never hardcode URLs
- NEVER use `overflow: hidden` on containers that hold dropdowns
- All forms need `{{ form.hidden_tag() }}` or CSRF token

## After Any Change — Always Report
- **Files changed**: list every file modified
- **What was done**: 2–3 sentence summary
- **Migration needed?**: yes/no + command if yes
- **Manual steps**: env vars, server restarts, seed scripts
- **Risks/conflicts**: anything that might break existing behavior

## Standard Utilities (prefer these over custom solutions)
- `app.utils.id_guard` — protect against incorrect ID assignments
- `app.utils.module_guard` — enforce module-level access control
- `app.utils.idempotency` — for wallet transactions and booking confirms
- `app.utils.validators` — common data validation patterns
- `app.utils.audit` — log sensitive actions

## Shell / Environment
- Terminal is **PowerShell** on Windows — use `;` instead of `&&` for command chaining
- Be careful with CRLF vs LF, especially in `docker-entrypoint.sh`
- Virtual env: `venv\Scripts\activate` (not `source venv/bin/activate`)

## Subtree Focus
- When working on a module (e.g. `app/events`), stay within that subtree
- Minimise side effects in unrelated modules unless the task requires cross-module changes

## Ignore (do not read unless explicitly needed)
`**/__pycache__/`, `**/.venv/`, `**/backups_today/`, `**/model_backups/`,
`**/templates_backup/`, `**/flask_session/`, `**/*.pyc`, `backup_*.json`,
`**/migrations/versions/*.py` (unless reviewing schema history)
