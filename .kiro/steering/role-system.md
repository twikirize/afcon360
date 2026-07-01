# AFCON360 — Role & Permission System

## Role Hierarchy (highest → lowest)
1. owner
2. super_admin
3. admin
4. auditor
5. compliance_officer
6. moderator
7. support
8. event_manager
9. transport_admin
10. wallet_admin
11. accommodation_admin
12. tourism_admin
13. org_admin
14. org_member
15. user

## Key Auth Files
- `app/auth/decorators.py` — `@admin_required`, `@require_role`, `@owner_only`
- `app/auth/roles.py` — role definitions and hierarchy logic
- `app/auth/policy.py` — permission policy enforcement
- `app/auth/delegation.py` — delegation of authority patterns
- `app/auth/ownership.py` — ownership checks

## Impersonation (Owner Only)
- Impersonate: `POST /admin/owner/master-key/act-as/<role_name>`
- Exit: `POST /admin/owner/master-key/exit`
- Tracked in session — check impersonation state before owner-only actions
- Owner cannot impersonate themselves or be impersonated

## Global Role Switcher (Persona System)
- Users with multiple roles switch active persona via `templates/auth/switch_role.html`
- Session tracks `active_role` — all permission checks must respect this
- Self-healing: if active role is revoked, session resets to default privileges

## Constraints
- Owner cannot be deleted or impersonated (self-protection enforced)
- Super admin cannot modify other super admins or the owner
- All role changes are audit-logged
- Role seeding: `python scripts/seed_roles.py`
