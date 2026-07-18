# Code Mode — AFCON360 Specific Instructions

## Before You Write Any Code
1. Identify which module is being touched (events, wallet, transport, etc.)
2. Check if the task involves wallet — if yes, treat as HIGH RISK and be extra conservative
3. Confirm the model inherits from `BaseModel`, not `db.Model`
4. Confirm any new FK references use `BigInteger` and reference `user.id` not `user.public_id`

## Implementation Style
- Fix root causes in model/source files — never patch migration files as workarounds
- One focused change at a time — do not refactor adjacent code unless instructed
- Preserve existing `backref` names — conflicts crash the app on startup
- When adding relationships, check for existing `backref` names in the same model file first

## After Implementing
ALWAYS provide a comprehensive post-change report. The report must include:

- **Files changed:** list every file modified
- **What was done:** 2–3 sentence summary of the implementation
- **What changed / improved:** explicitly state what behavior changed, what bug was fixed, or what feature was added
- **Migration needed?** yes/no — if yes: propose the exact `flask db migrate` / `flask db upgrade` commands, but do NOT run them automatically
- **Manual steps:** anything that cannot be automated (env vars, server restarts, seed scripts, etc.)
- **Risks/conflicts:** flag anything that could break existing behavior, circular imports, or convention violations
- **Verification:** how to confirm the fix works (test command, manual steps, or both)

This report format is mandatory after every code change, no matter how small.

## What NOT to Do
- NEVER create, generate, write, or patch migration files manually
- NEVER run `flask db migrate` or `flask db upgrade` automatically
- The user is responsible for running all migrations manually
- Propose the exact migration commands in the post-change report, but do not execute them
- Let Alembic auto-generate migration files when the user runs `flask db migrate`
- Do not run `flask db migrate` automatically — always ask first
- Do not modify `wallet/models/` without explicit instruction
- Do not change `BaseModel` or any shared base classes
- Do not add new ENUMs as PostgreSQL types — use String columns
- Do not use `overflow: hidden` on any container that holds a dropdown
