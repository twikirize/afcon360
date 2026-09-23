# AUTH-REDIRECT-INDEX — Evidence (dangling `url_for("auth.index")` repair)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23
Scope:           `grant_transport_permission` + `revoke_transport_permission`
                 redirect targets only (+ the audit call on the same two
                 paths, required for a clean response — see §5)
BL-23:           untouched, remains PASS (cross-referenced, not reopened)

## 1. UNDERSTAND

- `app/auth/routes.py` (HEAD) contained 8x `url_for("auth.index")`:
  4 in `grant_transport_permission`, 4 in `revoke_transport_permission`.
- The auth blueprint registers 33 endpoints (`auth.login`,
  `auth.grant_transport_permission`, `auth.revoke_transport_permission`,
  ...); there is NO `auth.index` (proven via `app.url_map` listing).
- Replacement targets verified registered before use:
  `user.dashboard` -> `/user/dashboard`,
  `admin.transport_admin_dashboard` -> `/admin/transport-admin`.

## 2. MAP — every `auth.index` hit classified

| Hit | Classification |
|-----|----------------|
| HEAD `app/auth/routes.py` x8 (grant/revoke redirects) | REAL BROKEN ENDPOINT (fixed) |
| `tests/test_bl23_transport_permission_guards.py:137` comment | COMMENT (repair note, kept) |
| `tests/test_bl23_transport_permission_guards.py:196` docstring | DOCUMENTATION (class purpose, kept) |

No other live route references `auth.index`. Post-fix grep: zero live
references; the two remaining hits are comment/docstring by design.

## 3. TRACE — intended destinations

- Deny paths (ordinary user fails owner/super_admin guard) ->
  `user.dashboard`: the ordinary-user surface; grant/revoke UI lives on
  the admin side, so a denied user returns to their own dashboard.
- Data-error / not-found / success paths (authorized actor) ->
  `admin.transport_admin_dashboard`: the canonical surface already
  serving the transport-admin workflow the mutation belongs to.
- No new page created; both targets pre-exist and resolve.

## 4. PROVE — BEFORE FIX

- HEAD source: `git show HEAD:app/auth/routes.py` contains 8x
  `url_for("auth.index")`.
- Live probe (`create_app()` + `test_request_context`):
  `url_for("auth.index")` raises
  `BuildError: Could not build url for endpoint 'auth.index'`
  -> every grant/revoke request reaching a redirect returns 500.
- Replacement probe (same context): `user.dashboard` -> `/user/dashboard`,
  `admin.transport_admin_dashboard` -> `/admin/transport-admin`.
- Before-fix HTTP behavior was not re-probed live: the worktree already
  carried the concurrent redirect fix, and stash/reset is prohibited.
  The BL-23 test NOTE contemporaneously documented "500 AFTER the
  mutation commits" on the success path.

## 5. MINIMAL CHANGE (+ required second 500 cause)

Redirect fix (already present as concurrent uncommitted work, verified
not re-done): 8x `auth.index` -> `user.dashboard` (2 deny paths) /
`admin.transport_admin_dashboard` (6 data-error/success paths).

Second 500 cause found during VERIFY (this node, same two routes):
after the redirect fix, authorized grant AND revoke still returned 500.
Root cause: `from app.audit.forensic_audit import log_attempt` raises
ImportError — no module-level name exists; the API is
`ForensicAuditService.log_attempt(entity_type, entity_id, action, ...)`
(proven: import fails; established pattern at `app/auth/routes.py:1317`
and `app/auth/kyc_routes.py:33`). The old call also passed an invalid
`status=` kwarg and omitted the required `entity_type`/`entity_id`.
The ImportError fires AFTER the mutation commits, exactly matching the
BL-23 "500 after mutation" observation — the dangling redirect was the
second, latent 500 behind it. Fixed both call sites to the established
`ForensicAuditService.log_attempt(...)` shape with
`entity_type="transport_permission"`,
entity_id = created perm id (grant) / permission_id (revoke),
plus `ip_address`/`user_agent` per the in-file pattern. No new audit
semantics, no authorization/schema/wallet/KYC/GEO/ride-matching change.

## 6. TESTS

`tests/test_bl23_transport_permission_guards.py` (13 tests):
TestDecoratorMatrix x5 (BL-23, untouched), TestGrantRoute x2
(deny: no row; allow: row created), TestRevokeRoute x2
(deny: row remains; allow: row revoked), TestRedirectIntegrity x4:
grant deny -> 302 `/user/dashboard`, grant allow -> 302
`/admin/transport-admin` + row created, revoke deny -> 302
`/user/dashboard`, revoke allow (added this node) -> 302
`/admin/transport-admin` + row revoked. Every test asserts the
security result AND the response/redirect integrity together.

## 7. VERIFY — AFTER FIX (exact totals)

- tests/test_bl23_transport_permission_guards.py: 13 passed
- tests/test_auth_require_role.py: 7 passed
- tests/test_transport_service_integrity.py: 49 passed
- Full regression suite NOT run (per scope; totals above are exact).

## 8. STARTUP

- `create_app()` completes (`App factory completed`, endpoint
  validator: `All known endpoint references validated successfully`).
- `auth.grant_transport_permission` + `auth.revoke_transport_permission`
  registered (url_map listing).
- `url_for("user.dashboard")`, `url_for("admin.transport_admin_dashboard")`
  resolve; `url_for("auth.index")` raises BuildError (endpoint absent
  by design — nothing references it anymore).

## 9. GATE

AUTH REDIRECT INTEGRITY: PASS — all 12 gate conditions hold
(§10 of task): dangling refs identified; replacement routes proven;
unauthorized grant/revoke remain denied with clean 302s; authorized
grant/revoke mutate correctly with clean 302s; no redirect- or
audit-caused 500; BL-23 behavior intact (its 9 tests green, security
fix untouched); focused tests pass; startup succeeds; audit complete.
