# BL-17 / BL-18 — Role & Authority Boundary Audit: Evidence Artifact

Date: 2026-09-23. Read-only audit; no production behavior changed.
Probe rows used throwaway test-DB users/vehicles (since removed);
dev-DB probe residue from the investigation was fully cleaned
(users, roles links, notifications, logs, vehicles — verified zero remaining).

## 1. Canonical role hierarchy (app/auth/seed_roles.py:50-64, SINGLE SOURCE OF TRUTH)

| Level | Role | Scope |
|-------|------|-------|
| 1 | owner | global |
| 2 | super_admin | global |
| 3 | admin | global |
| 4 | auditor | global |
| 5 | compliance_officer | global |
| 6 | moderator | global |
| 7 | support | global |
| 8 | event_manager | global |
| 9 | transport_admin | global |
| 10 | wallet_admin | global |
| 11 | accommodation_admin | global |
| 12 | tourism_admin | global |
| 13 | user | global |

Notes:
- Role docstring (roles_permission.py:286-288) says "4 moderator, 5 support,
  6 fan" — STALE, contradicts the seed. Doc drift, not a behavior bug.
- transport_admin is a seeded global role (level 9), NOT in the docstring list.
- 61 global permission defs; NO `vehicle:*` grant exists anywhere.
- transport.view / transport.manage granted to owner, super_admin, admin,
  transport_admin (seed_roles.py:138-141). moderator is EXCLUDED.
- content.* permissions include moderator (seed_roles.py:114-118).

## 2. Guard semantics (verified by reading, then by live request)

- require_moderator (= require_moderator_role, auth/decorators.py:669-692):
  allows moderator, admin, super_admin, owner via has_global_role.
  transport_admin is NOT admitted. Unauthenticated -> login redirect.
- require_role(*_MOD) with _MOD=(moderator,admin,super_admin,owner)
  (admin/moderator/routes.py:51): INTENDED to admit the same four, BUT the
  fallback at decorators.py:280 reads `if is_owner(user) or
  user.is_super_admin:` — user.is_super_admin is a BOUND METHOD (always
  truthy, user.py:423) — so ANY authenticated user passes. Live-proven
  below. Pre-existing BACKLOG entry AUTH-REQUIRE-ROLE-FALLBACK covers it.
- _restrict_transport_admin (transport/routes.py:192-201): admits
  owner/super_admin/admin/transport_admin + _PUBLIC_ENDPOINTS (which now
  includes the 5 transport.moderate* endpoints). Pure moderators pass
  the gate ONLY for allowlisted endpoints; require_moderator then governs.
- transport_admin_required (transport/decorator.py:88-103): admits
  owner/super_admin/admin/transport_admin. Not used by either
  moderation surface.

## 3. Surface map

### transport.moderate_action (POST /transport/moderate/<type>/<id>/<action>)
- Owner: transport module (routes.py:2563+). Guards: login_required +
  require_moderator + before_request gate (public-listed).
- Admitted (proven live): moderator, admin. Denied: transport_admin (403),
  plain user (403), anonymous (login redirect).
- Actions: approve/reject/flag. Vehicle approve/reject writes real
  columns directly (status active/rejected + hasattr-guarded
  verified_at/rejection_reason); driver approve/reject delegates to
  ProviderService.update_driver_status (no permission gate on that
  method); booking branch writes real columns; flag via create_flag.
- Audit: none (flashes only). Notifications: none.
- Nav: ZERO inbound links (moderator sidebar has no transport entry;
  templates self-link only). Direct-URL surface.

### admin.moderator.transport_moderate_action
(POST /admin/moderator/transport/action/<type>/<id>/<action>)
- Owner: admin moderator module (routes.py:3436+). Guards:
  login_required + require_role(*_MOD) — INTENDED audience identical to
  above, but the fallback defect admits EVERY authenticated user.
- Admitted (proven live): moderator, transport_admin, admin, AND plain
  user (302 + status persisted to active — full unauthorized state
  change). This is the critical finding.
- Actions: approve/reject/flag/suspend. Writes real columns with
  hasattr guards — EXCEPT suspend writes suspension_reason /
  suspended_at, which exist on NEITHER model (verified): reason and
  timestamp vanish; only is_active/is_available persist. So the twin's
  suspend half-persists.
- Audit: none (flashes only). Notifications: none.
- Nav: linked from admin moderator transport_* templates (15+ forms).

## 4. Live differential matrix (test DB, CSRF-off test config, throwaway rows)

| Caller | transport.moderate_action | admin twin |
|--------|---------------------------|------------|
| moderator | 302, pending->active | 302, pending->active |
| transport_admin | 403, unchanged | 302, pending->active (via defect, NOT by design) |
| admin | 302, pending->active | 302, pending->active |
| plain user | 403, unchanged | 302, pending->active (VULNERABILITY) |
| anonymous | login redirect (by decorator shape; not re-probed) | login redirect (by decorator shape; not re-probed) |

Method notes: first dev-DB probe round was invalid (CSRF 302s + wrong
twin path /moderator/... instead of /admin/moderator/...); reran under
TestingConfig with the correct paths. Dev-DB residue fully removed
afterward (probe users, role links, notifications, logs, vehicles).

## 5. Verdict: Case 1 — TRUE DUPLICATE (intended scope identical)

- Intended audience of both surfaces is the same set
  (moderator/admin/super_admin/owner); neither admits transport_admin
  by design. Same entities, same approve/reject/flag verbs.
- Differences are accidental, not layered authority: (a) twin reaches
  a wider ACTUAL audience only through the require_role fallback
  defect; (b) twin has an extra suspend verb that half-persists;
  (c) transport surface is nav-orphaned while the twin is nav-linked.
- transport_admin — the domain authority — can moderate through
  NEITHER surface (403 on transport surface; twin only via the defect).
  Domain admins moderate via /admin/transport-admin (require_permission
  transport.manage), a THIRD path. There is no "Transport Admin
  moderation surface" today; the hypothesis of intentional layering is
  disproven by the guards as written.

## 6. Recommended next node (do NOT implement in this audit)

1. SECURITY FIRST (separate node, HIGH_RISK): fix the require_role
   fallback defect (decorators.py:280 bound-method truthiness). It
   silently un-gates 100+ moderator-blueprint routes, not just
   transport. BACKLOG AUTH-REQUIRE-ROLE-FALLBACK already records it.
2. Then consolidate to ONE transport moderation surface. Recommended
   canonical: the admin twin (nav-linked, has suspend verb — repair its
   suspend reason/timestamp persistence or drop the fields), and retire
   transport.moderate* routes + templates. Alternative (keep transport
   surface, retire twin usage for transport entities) is weaker: it
   preserves the nav orphan and drops the suspend verb.
3. Decide whether transport_admin should moderate at all. Today it
   cannot (both surfaces exclude it). If yes, add it to the canonical
   surface's gate explicitly — do not rely on fallback defects.
4. BL-17/BL-18 classification: DUPLICATE (Case 1). Close them with the
   consolidation node, not here.
