# AUTH-REDIRECT-INDEX — Record (dangling `url_for("auth.index")` repair)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23
Owner:           [your name]

Files changed:
  - app/auth/routes.py   (this node: 2x broken audit calls ->
                          ForensicAuditService.log_attempt established shape;
                          concurrent work, verified not re-done: 8x auth.index
                          redirects -> user.dashboard / admin.transport_admin_dashboard)
  - tests/test_bl23_transport_permission_guards.py   (new file, concurrent work;
                          this node: +1 revoke-allow redirect test, stale NOTE reworded)
  - docs/transport/fixes/AUTH-REDIRECT-INDEX-evidence.md   (new)

Evidence:
  See docs/transport/fixes/AUTH-REDIRECT-INDEX-evidence.md

Behavior summary:
  Ordinary user -> grant/revoke: denied, no mutation, clean 302 to
  /user/dashboard. Owner/super_admin -> grant: permission row created,
  clean 302 to /admin/transport-admin; revoke: row revoked, clean 302
  to /admin/transport-admin. No 500 on any of the four paths.
  BL-23 security fix untouched (its 9 tests green).

Second-500-cause note:
  The redirect fix alone did not produce clean responses: authorized
  grant AND revoke still 500'd because
  `from app.audit.forensic_audit import log_attempt` raises ImportError
  (no module-level name; API is ForensicAuditService.log_attempt) after
  the mutation commits. Repaired to the established in-file pattern
  (routes.py:1317). The dangling redirect was the second latent 500
  behind it.

Runtime verification:
  test_bl23_transport_permission_guards.py: 13 passed.
  test_auth_require_role.py: 7 passed.
  test_transport_service_integrity.py: 49 passed.
  create_app() factory + endpoint validator green; replacement url_for
  targets resolve; auth.index confirmed unregistered.

Residual risk:
  The concurrent redirect fix (deny -> user.dashboard, success ->
  admin.transport_admin_dashboard) was verified correct but its
  product-intent confirmation rests on trace reasoning, not a written
  human contract for this node; if the product owner prefers a
  different post-action landing surface, only the url_for targets
  change. The `perm.id if hasattr(perm, "id") else perm["id"]`
  duality in tests mirrors the service's dual return shape and is
  unchanged by this node.

Follow-ups:
  - None opened by this node. Pre-existing type-checker noise in the
    BL-23 test file (Column[int] vs int etc.) predates this node and
    is runtime-irrelevant; recorded, not fixed here.

Gate reference:
  AUTH REDIRECT INTEGRITY: PASS
