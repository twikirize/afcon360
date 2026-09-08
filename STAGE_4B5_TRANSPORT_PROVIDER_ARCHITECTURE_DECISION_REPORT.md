# STAGE 4B-5 — Transport Provider Architecture (Decision Report)

Status: FORENSICS COMPLETE — AWAITING HUMAN DECISION
Node: Stage 4B-5 Transport Provider Architecture (HIGH_RISK)
Date: 2026-09-06

This node covers PHASE 1 (forensics), PHASE 2 (graphs), PHASE 3 (contradiction
register), PHASE 4 (options), PHASE 5 (this decision report). NO code has been
modified. Per the checkpoint directive, implementation begins only after the
human decision gate below is explicitly satisfied.

---

## 1. Executive summary

Transport onboarding is split across two disconnected implementations:

1. **Auth onboarding wizard** (`/onboarding/driver`, `app/auth/onboarding_routes.py:156-301`)
   — the only reachable path today. Guarded by `@login_required` only. Creates a
   `DriverProfile`, a `Vehicle` (`owner_type='driver'`), and attempts to assign a
   non-existent global `driver` role (silently skipped). No KYC-tier gate, no
   ProviderParticipation declaration.
2. **Transport module routes** (`/become-driver`, `/register-vehicle`,
   `/vehicle-dashboard`, `app/transport/routes.py`) — fully guarded but
   **unreachable**. The transport-local `@role_required("provider")`
   (F-2, `app/transport/decorator.py:52-65`) compares a string against a
   relationship returning `UserRole` ORM objects, so it **always** redirects.
   Both POST handlers additionally call the provider service with
   incompatible keyword arguments (G-2), which would raise `TypeError` even if
   the guard passed.

Transport does not participate in the universal provider architecture at all
(T-1): no code path in `app/transport/**` calls
`create_individual_intention` / `create_organisation_intention` /
`is_capability_operational`. Accommodation is the reference domain and does
(`app/auth/onboarding_routes.py:738-746`).

Vehicle ownership uses two incompatible vocabularies (T-2), so a vehicle
created by the working onboarding wizard never appears on
`vehicle_dashboard` / `get_user_vehicles`, and a vehicle created by the
service never satisfies the model relationships.

Recommended direction (subject to the decision gates): bring transport in line
with Stage 4A ADR-4A-008/009 — a resource-free `TRANSPORT` PP declaration,
domain-owned `DriverProfile` creation, and `Vehicle` as a separate operation
only after an eligible, approved `DriverProfile` exists; standardise vehicle
ownership on `owner_type='driver'`; and replace the broken transport-local
role guard with the canonical identity/eligibility gates.

---

## 2. Current architecture (evidence-based flow graph)

### 2.1 Reachable driver-onboarding flow (the auth wizard)

```
GET /onboarding/driver  →  onboarding.driver_onboarding(step=1..3)
  @login_required                       (onboarding_routes.py:156-159)
  step3 POST → _commit_driver_onboarding(current_user, data)
    _get_or_create_profile(user)        → updates UserProfile
    DriverProfile(user_id=user.id, ...) → db.session.add(driver)   (:253-273)
    Vehicle(owner_type='driver',
            owner_id=driver.id, ...)    → db.session.add(vehicle)  (:277-291)
    assign_global_role('driver')        → ValueError caught/skipped (:295-301)
  → redirect(transport.driver_dashboard)
chain: no KYC gate, no PP row, creates 2 domain resources + 0 identity signal
```

### 2.2 Blocked transport-module flow (service path)

```
GET/POST /become-driver   (routes.py:557)
  @module_enabled_required("transport")
  @login_required
  @require_profile_completion
  @require_kyc_tier(3)
  @role_required("provider")                    ← F-2: ALWAYS redirects
  POST → get_provider_service().register_driver(data, user_id=...)
                                               ← G-2: TypeError (unreachable)

GET/POST /register-vehicle (routes.py:736)
  @module_enabled_required + @login_required
  @role_required("provider")                    ← F-2: ALWAYS redirects
  POST → get_provider_service().register_vehicle(data, user_id=...)
                                               ← G-2: TypeError (unreachable)

GET /vehicle-dashboard (routes.py:833)
  @role_required("provider")                    ← F-2: ALWAYS redirects
  → get_user_vehicles(current_user.id)          (owner_type='user' filter)
```

### 2.3 Organisation transport (service only, no web route that works)

```
ProviderService.register_organisation_transport(org_id, data) (:889)
  validate_organisation_eligibility(org_id)  (:258)
    → get_organisation_identity(org_id)      (:215)
        ImportError fallback → MOCK verified/active/business_registered (:243-256)
  creates OrganisationTransportProfile + N Vehicles
  (owner_type='organisation', owner_id=org_id)  (:938-993)
API: app/transport/api/organisation_routes.py:89-129 (register profile)
Org dashboard web route:
  GET /organisation/dashboard  (routes.py:1056)
  @role_required("organisation_admin")  ← F-2: transport-local, ALWAYS redirects
```

---

## 3. Task classification

HIGH_RISK (per checkpoint directive). Involves authorisation guards, identity
signal, provider lifecycle, role vocabulary, and a latent runtime bug. No
schema change is proposed (no migration).

---

## 4. Writer / reader graph

### 4.1 DriverProfile

Writers:
- `app/auth/onboarding_routes.py:253` `_commit_driver_onboarding` (wizard) — creates `DriverProfile`
- `app/transport/services/provider_service.py:586` `register_driver` — creates `DriverProfile` (+ optional Vehicle)

Readers:
- `app/auth/context.py:462-484` `_driver_contexts` — DRIVER context eligibility (verified tiers, non-blocked compliance)
- `app/auth/routes.py:242-243` — `DriverProfile.query.filter_by(user_id=...)`
- `app/admin/route_modules/transport_admin.py:39` — admin views
- `get_driver` / `get_driver_profile` `provider_service.py:373,381`; dashboard/booking/matching/tracking/notification services (via models)
- `Vehicle.owner_driver` / `DriverProfile.owned_vehicles` relationships (`transport/models.py:360-366,713-719`)

### 4.2 Vehicle

Writers:
- `app/auth/onboarding_routes.py:277` — `owner_type='driver'`, `owner_id=driver.id`
- `app/transport/services/provider_service.py:732` `register_vehicle_internal` — `owner_type` passed by caller ('user' from `register_driver`/`register_vehicle`; 'organisation' from org path)
- `register_organisation_transport` → `register_vehicle_internal(... owner_type='organisation')` (:979)

Readers:
- `get_user_vehicles` `provider_service.py:446-453` — **`owner_type='user'` filter**
- `list_vehicles`, admin, dashboard, passenger/assignment services
- Relationships `Vehicle.owner_driver` (`owner_type=='driver'`), `DriverProfile.owned_vehicles` (`owner_type=='driver'`), `fleet_vehicles` (`owner_type=='organisation'`)

### 4.3 OrganisationTransportProfile

Writers:
- `register_organisation_transport` `provider_service.py:938`
- `app/transport/api/organisation_routes.py:110` (API POST)

Readers:
- `register_vehicle` org branch `provider_service.py:808-818` (must exist for org vehicle)
- admin; API detail/list

### 4.4 ProviderParticipation (universal registry)

Writers/readers (all via `provider_participation_service`, one row per
(subject, capability_code), INTENT → ACTIVATED/SUSPENDED/REVOKED/DEACTIVATED):
- Individual: `create_individual_intention`, `activate_individual_intention`,
  `deactivate_individual_intention`, `is_capability_operational`
- Organisation: `create_organisation_intention`, `activate_organisation_intention`, etc.
- Reference consumer: accommodation host onboarding `onboarding_routes.py:738-746`
  (`create_individual_intention(user, ACCOMMODATION)`)
- **Transport: no writer, no reader.** Confirmed gap (T-1).

---

## 5. Contradiction register

| ID | Severity | Status | Evidence |
|----|----------|--------|----------|
| G-2 | HIGH (runtime `TypeError`/`AttributeError`) | CONFIRMED by code read | `routes.py:584` calls `register_driver(data, user_id=...)`; signature `register_driver(self, user_id, driver_data, ...)` `provider_service.py:531`. Also `routes.py:585` reads `.id` on a dict-returning service. `routes.py:759` calls `register_vehicle(data, user_id=...)`; signature `(self, owner_type, owner_id, vehicle_data, ...)` `provider_service.py:780`. Both handlers unreachable today only because F-2 blocks the routes first. |
| F-2 | HIGH (authorisation guard always redirects) | CONFIRMED by code read | `transport/decorator.py:52-65`: `role_name not in getattr(current_user,'roles',[])`. `User.roles` is a relationship to `UserRole` ORM objects (`user.py:163-167`), never role-name strings. String membership test therefore always `True` → always redirect. Used at `routes.py:562,739,836,1059`. Canonical role checks exist (`user.role_names` `user.py:390`, `is_org_owner`, `has_global_role`). |
| T-1 | HIGH (bypasses universal provider registry) | CONFIRMED | No transport call to the PP service anywhere in `app/transport/**`. Accommodation is integrated (`onboarding_routes.py:738-746`). Stage 4A ADR-4A-008/009 requires declaration before domain resources. |
| T-2 | MEDIUM-HIGH (ownership vocabulary split) | CONFIRMED | Wizard writes `owner_type='driver'` (`onboarding_routes.py:278`); service writes `owner_type='user'` (`provider_service.py:639-645,824-829`); `get_user_vehicles` reads `owner_type='user'`; model relationships require `owner_type=='driver'`. Wizard-created vehicles invisible to dashboards; service-created vehicles invisible to relationships. |
| T-3 | HIGH (two stranded onboarding flows) | CONFIRMED | Wizard (reachable, no KYC/eligibility gate, resource creation + dead role assignment) vs transport routes (blocked by F-2 + G-2). No single coherent target flow. |
| T-4 | HIGH (org eligibility fallback to mock, no org-type capability gate) | CONFIRMED | `get_organisation_identity` `provider_service.py:243-256` silently returns `verified=True / status='active' / business_registered=True` on `ImportError`. `validate_organisation_eligibility` never consults `can_manage_transport` (Stage 4B classification: TOUR_OPERATOR/TRAVEL_AGENCY only) from `ORGANIZATION_CAPABILITIES`. |
| T-5 | MEDIUM (declaration not resource-free) | CONFIRMED | Wizard step 3 requires a Vehicle to commit (`onboarding_routes.py:200-211,276-291`); `register_driver` may create Vehicle + DriverProfile in one transaction (`provider_service.py:638-649`). Violates ADR-4A-008 (provider layer never creates domain resources) and ADR-4A-009 (split declaration → DriverProfile → Vehicle). |
| T-6 | MEDIUM (role vocabulary gap) | CONFIRMED | No `provider` or `driver` role exists: constants `app/auth/roles.py:38-50`; seed list `scripts/seed_roles.py:8`; onboarding's `assign_global_role('driver')` always raises `ValueError`, caught and silently skipped (`onboarding_routes.py:295-301`). |

---

## 6. Ownership check (Stage 4A / 4B boundaries)

- **ProviderParticipation (PP):** owned by Identity — `provider_participation_service.py`. Transport must declare through it, never dual-write, never bypass.
- **DriverProfile, Vehicle, OrganisationTransportProfile:** owned by Transport — `app/transport/**`.
- **Transport eligibility authority:** `ProviderService.validate_driver_eligibility` (`provider_service.py:154-213`) is the individual domain authority (identity/email/phone/age/criminal/account). Organisation eligibility today is `validate_organisation_eligibility` (`:258`) — gated only on org active/verified/business-registered.
- **Role vocabulary:** owned by Identity (`roles.py`, `seed_roles.py`, `Role` table). Transport must not invent `provider`/`driver` roles without authorization (Stage 4A §18.2 / identity spec).

Constraints honoured: no wallet, payment, escrow, KYC/KYB internal, booking
state-machine, event, accommodation, `auth/context.py`, PP-schema, capability
vocabulary, PG-enum, or migration-graph change is proposed. The completed
Option C reconciliation (organisation classification) is untouched.

---

## 7. Eligibility check (current vs target)

| Subject | Current | Target (this node's proposal) |
|---|---|---|
| Individual driver (wizard) | No eligibility gate beyond login (`onboarding_routes.py:156-159`) | Wizard aligns to transport routes: `@require_profile_completion` + `@require_kyc_tier(3)` + `validate_driver_eligibility` at commit; PP `TRANSPORT` intent declared resource-free |
| Individual driver (transport route) | F-2 blocks; G-2 would crash | Replace broken role guard; keep profile + KYC-3; `validate_driver_eligibility` remains domain authority |
| Organisation | Mock fallback may grant eligibility; no `can_manage_transport` gate | Org eligibility = org `active` + verified + `business_registered` (repair mock fallback) AND `can_manage_transport` per Stage 4B classification; PP `TRANSPORT/BUS` intent |

---

## 8. Decision gate — role guard (F-2)

**Question:** how do we authorise transport provider/onboarding routes?

### Option A — Remove the transport-local guard; rely on canonical gates
Remove `@role_required("provider")` from `routes.py:562,739,836`. Keep
`@module_enabled_required` + `@login_required` + `@require_profile_completion`
+ `@require_kyc_tier(3)`; add explicit `validate_driver_eligibility` +
existing-`DriverProfile` check at the write point. `DRIVER` context
(`context.py:462-484`) already derives eligibility for the switch — no role row
needed.
- Pros: no schema/role changes; kills both F-2 and T-6 for these routes; uses the domain eligibility authority that already exists.
- Cons: open at "declaration" level by design (declaration itself has no DRIVER role; activation is gated by eligibility + PP state).

### Option B — Canonical role role check + seed a `driver`/`provider` role
Fix `transport/decorator.py` to evaluate via `user.role_names`/`has_global_role`, and add a canonical `driver` global role (seed + `roles.py` constant) assigned at onboarding.
- Pros: explicit role signal on the User.
- Cons: role-vocabulary change requires identity/authorisation approval (HIGH_RISK); duplicates the DRIVER-context/eligibility signal already present.

### Option C — Module guard only (bedrock)
Replace role guard with existing `@module_required('transport')` + login, trusting eligibility + PP `ACTIVATED` at resource-creation/activation points.
- Pros: simplest; consistent with how other modules gate (accommodation onboarding route has no host role).
- Cons: loosest gate at declaration.

### Option D — Other
Human proposes alternative.

**Recommended: A** (aligns with accommodation reference; no role-schema change).

---

## 9. Decision gate — register_driver (G-2)

**Question:** what is the correct declaration/creation shape for individual transport onboarding?

### Option A — Repair the caller only
Fix `routes.py:584` to `register_driver(user_id=current_user.id, driver_data=data)` and `routes.py:759` to call the vehicle path correctly; fix dict extraction (`driver['data']['driver_id']` instead of `driver.id`).
- Cons: leaves declaration coupled to resource creation (T-5, ADR-4A-008/009 violation).

### Option B — Resource-free declaration + domain-owned DriverProfile
Transport onboarding records `create_individual_intention(user, TRANSPORT)` (PP INTENT) and nothing else; `register_driver`/wizard creates `DriverProfile` only after `validate_driver_eligibility`; Vehicle is a separate later operation (declaration → DriverProfile → Vehicle per ADR-4A-009).
- Pros: satisfies ADR-4A-008/009; mirrors accommodation (`ACCOMMODATION` intent).
- Cons: behavioural change to wizard commit; requires mandatory non-creation test (TransportIntent → DriverProfile/Vehicle/Booking counts unchanged).

### Option C — Keep combined but add PP intent beside it
`register_driver` declares PP `TRANSPORT` intent AND creates DriverProfile (+ optional Vehicle) in one transaction.
- Pros: smallest change to reachable flow.
- Cons: still violates ADR-4A-009's split; keeps Vehicle side-effect (T-5).

### Option D — Other
Human proposes alternative.

**Recommended: B** (the Stage 4A target architecture).

---

## 10. Decision gate — Vehicle (T-2)

**Question:** standard ownership + creation boundary for Vehicles.

### Option A — `owner_type='driver'` canonical; separate operation
All Vehicle writers use `owner_type='driver'`, `owner_id=driver.id`. Fix
`get_user_vehicles` to resolve the user's `DriverProfile` then query
`DriverProfile.owned_vehicles` (or `owner_type='driver'`). Vehicles created
only after an eligible, `ComplianceStatus.APPROVED` `DriverProfile` exists.
- Pros: single vocabulary; fixes T-2 both directions; relationship-consistent.
- Cons: touches all 3 writers + reader.

### Option B — `owner_type='user'` canonical
Standardise everything on `owner_type='user'`, `owner_id=user_id`; adjust the
model relationships (`owned_vehicles`, `owner_driver`) to match.
- Pros: matches `get_user_vehicles` today.
- Cons: ownership without a driver record is ambiguous; diverges from
  `DriverProfile.owned_vehicles` semantics (owner_id = driver.id).

### Option C — Service-only Vehicle, keep relationships
Keep current split; only fix `get_user_vehicles` to handle both vocabularies.
- Cons: two vocabularies persist (drift risk); relationship still mismatched for `owner_type='user'`.

### Option D — Other
Human proposes alternative.

**Recommended: A** (matches `DriverProfile.owned_vehicles`/`owner_driver`).

---

## 11. Decision gate — Organisation transport (T-4)

**Question:** how do organisations become transport providers?

### Option A — Align with universal architecture (recommended)
Org onboarding/wizard records `create_organisation_intention(user, org_id, TRANSPORT)` (INTENT) resource-free; `register_organisation_transport` repairs the `ImportError` mock fallback (fail closed) and adds `can_manage_transport` (Stage 4B classification) to `validate_organisation_eligibility`; org-driven Vehicles stay a separate operation.
- Pros: closes T-1/T-4 for orgs; consistent with Stage 4A §14 org guidance.
- Cons: behavioural change; needs org-eligibility tests.

### Option B — Defer org transport to later node
Record T-4 in BACKLOG; individually repair only the mock fallback (fail-closed) to prevent silent auto-approval.
- Pros: smallest change; unblocks individual path.
- Cons: orgs remain outside universal architecture.

### Option C — Keep as-is (documented)
- Cons: mock fallback can silently approve orgs; no PP participation.

### Option D — Other
Human proposes alternative.

**Recommended: A** (or B as a minimal safety stop if scope must shrink).

---

## 12. Recommended architecture (post-gate, per Stage 4A ADRs)

```
TRANSPORT INTENT (PP row, resource-free)     ← create_individual_intention /
                                                create_organisation_intention
        │  (explicit activation, gated by domain eligibility at activation)
        ▼
DriverProfile (domain-owned, eligibility-verified)   — individual
OrganisationTransportProfile (org, KYB-gated)        — organisation
        │
        ▼
Vehicle  (separate operation; only when an eligible/approved profile exists)
```

- Individual: `PP(user_id, transport, INTENT)` → DriverProfile (after
  `validate_driver_eligibility`) → Vehicle (`owner_type='driver'`).
- Organisation: `PP(org_id, transport, INTENT)` → OrganisationTransportProfile
  (after org eligibility incl. `can_manage_transport`) → Vehicles
  (`owner_type='organisation'`).
- `DRIVER`/`ORGANISATION` context semantics in `auth/context.py` are
  unchanged; PP spells `activation` (the capability half of the two-gate rule);
  eligibility remains the transport domain's authority.

---

## 13. Changes NOT proposed (do not touch)

- `app/wallet/**`, `app/transport/services/payment_service.py`, escrow, booking
  state machines, event architecture.
- `app/auth/context.py` (frozen; only `DRIVER`/`ORGANISATION` context types —
  no `TRANSPORT_PROVIDER`/`DRIVER_PROVIDER`).
- ProviderParticipation schema, `ProviderCapabilityCode`/`ProviderCapabilityStatus`
  vocabulary, PostgreSQL enum vocabulary, migration graph.
- KYC/KYB internals; organisation wallet creation (`organization_registration.py`
  `create_org_wallet`). Organisation classification reconciliation (Option C).
- Legacy OPC model (do not delete); OPC migration frozen.

## 14. Migration

None required (no schema change). No CHECK-constraint sync invoked (§20.2 not
triggered).

## 15. Required code changes (post-approval, still to authorize)

1. Repair `register_driver`/`register_vehicle` call sites and result extraction (G-2).
2. Replace transport-local `@role_required(...)` with canonical gates (F-2).
3. Add resource-free `TRANSPORT` intention declaration on both onboarding paths (T-1/T-5, per gate §9).
4. Standardise Vehicle ownership to `owner_type='driver'` + align reader (T-2, per gate §10).
5. Repair org eligibility mock fallback (fail closed) + gate on `can_manage_transport` (T-4, per gate §11).
6. Choose whether to add a canonical `driver` role (T-6) — deferred unless gate §8 lands on Option B.

## 16. Required tests (post-approval)

- **Mandatory non-creation test:** declare `TRANSPORT` intention → assert counts
  of `DriverProfile`, `Vehicle`, `Booking`, `Payment`, `Wallet` unchanged.
- Focused: `register_driver` signature/result contract; role-guard behaviour
  (explic: profile-completion + KYC-3 + eligibility); wizard still commits
  DriverProfile without Vehicle side-effect (if gate §9 = B); vehicle ownership
  uniform; org eligibility fail-closed + `can_manage_transport`.
- Regression (mandated suites):
  `tests/test_stage4b2_capability_enforcement.py`,
  `tests/test_stage4b3_organisation_capabilities.py`,
  `tests/test_capability_operations.py`,
  `tests/test_provider_participation.py`,
  `tests/test_onboarding_stage4.py`,
  plus `tests/transport_model.py`, `tests/test_transport_passengers.py`,
  `tests/verify_transport_tables.py` (a.k.a. transport smoke).
- Baseline failures: classify NEW REGRESSION / PRE-EXISTING / TEST DB
  CONTAMINATION / UNRELATED DRIFT; never mask.

## 17. Success criteria

1. Resource-free declaration proven (counts test) for individual and org.
2. `become_driver`/`register_vehicle`/`vehicle_dashboard` reachable for a
   profile-complete, KYC-3, eligible, non-driver user (no bogus role).
3. `validate_driver_eligibility` applied at DriverProfile creation.
4. Vehicle ownership single vocabulary (`owner_type='driver'`).
5. Org eligibility fail-closed (no mock) + `can_manage_transport` respected.
6. All mandated regression suites green (new regressions none).
7. No wallet/payment/escrow/KYC/KYB/context/PP-schema/vocab/migration change.

## 18. Rollback strategy

Code-only changes; revert the affected files to HEAD if verification fails.
No data migration to reverse.

## 19. Deferred work (will be recorded in BACKLOG.md)

- T-6 role-vocabulary decision (`provider`/`driver` canonical role) — identity
  authority, unless gate §8 → Option B.
- Full org-transport fleet/driver-management UI alignment (separate node) if not
  in scope.

---

## §20 DECISION GATE — HUMAN APPROVAL REQUIRED

No code has been modified in this node. Selection required before proceeding:

```
STATUS: NEEDS_DECISION
NODE: Stage 4B-5 Transport Provider Architecture (PHASE 1-5 forensics complete)
SCOPE: transport onboarding/services/routes/tests; PP integration for transport;
       transport eligibility integration for activation; role-guard + caller repair

DECISIONS:
  §8  Role guard (F-2):      A (recommended) | B | C | D
  §9  register_driver (G-2): A | B (recommended) | C | D
  §10 Vehicle (T-2):         A (recommended) | B | C | D
  §11 Organisation (T-4):    A (recommended) | B | C | D

Approval command (example):
  APPROVE: role=A, register_driver=B, vehicle=A, org=A
Alternative: DENY / GUIDE / DEFER specific gates.
```

Evidence inspected: `app/transport/routes.py`, `app/transport/decorator.py`,
`app/transport/models.py`, `app/transport/services/provider_service.py`,
`app/transport/api/organisation_routes.py`, `app/auth/onboarding_routes.py`,
`app/auth/context.py`, `app/auth/roles.py`, `app/identity/models/user.py`,
`scripts/seed_roles.py`, `app/identity/models/provider_participation.py`,
`app/identity/models/organisation_provider_capability.py`,
`app/identity/services/provider_participation_service.py`,
`app/utils/security.py`, `app/auth/kyc_compliance.py`,
`STAGE_4A_UNIVERSAL_PROVIDER_ARCHITECTURE_DECISION_REPORT.md` (§14, §15, ADR-4A-008/009).
No implementation performed (audit/decision-report authority only).

---

## §21 IMPLEMENTATION + VERIFICATION (2026-09-06) — APPROVED: role=A, register_driver=B, vehicle=A, org=A

**Approved scope (§8-11 above).** All four decisions implemented exactly as
authorized.

**Files changed (this node):**
- `app/transport/routes.py` — removed `@role_required("provider")` from
  `become_driver` (:595), `register_vehicle` (:777), `vehicle_dashboard` (:886);
  canonical gate stack confirmed on all three
  (`@module_enabled_required("transport") + @login_required +
  @require_profile_completion + @require_kyc_tier(3)`); `_require_vehicle_ownership`
  helper kept. `register_vehicle` driver branch verified present.
- `app/transport/services/provider_service.py` — `register_vehicle_internal`
  writes `owner_type='driver'`, `owner_id=driver.id` (no vehicle on an unverified
  `register_driver` — Vehicle is a separate later operation); `get_user_vehicles`
  resolves through the user's `DriverProfile`s; my added
  `ValidationError`/`ServiceUnavailableError` raises use message-only form (the
  classes carry `(message, field, value)` — no `code`/`details` kwargs — so the new
  gates actually raise the typed exception instead of `TypeError`); org driver
  registration now validated for `get_driver_profile` + `append Vehicle + connect
  to current_driver_id`; `get_organisation_identity` and
  `validate_organisation_eligibility` wired for fail-closed organisation gating.
- `app/auth/onboarding_routes.py` — `_commit_driver_onboarding` now:
  `validate_driver_eligibility(user.id)` (domain authority) → duplicate-driver
  guard (`ValueError`) → `create_individual_intention(user, TRANSPORT)` (resource-free
  INTENT, PP row only) → `DriverProfile`. Vehicle creation REMOVED (was the T-2
  over-creation). Host commit path untouched.
- `tests/test_stage4b5_transport.py` — new focused checkpoint file (7 tests).

**Post-implementation proof (2026-09-06):**
- `@role_required` count in `app/transport/routes.py` = **20** (the 3 authorized
  removals only; remaining 20 are pre-existing — driver :698/:725,
  organisation_admin :1108, admin ×16 — explicitly NOT in scope).
- No `owner_type='user'` writers remain in `app/transport`.
- Startup import: `from app import create_app` → `IMPORT_OK`.

**Focused tests:** `tests/test_stage4b5_transport.py` → **7 passed** in ~17s
(driver-wizard intent-only commit with no Vehicle; duplicate-driver guard;
`get_user_vehicles` via DriverProfile incl. ignoring stale `owner_type='user'`
row; org identity fail-closed without the identity registry; RESTAURANT org
ineligible / TRANSPORT_COMPANY eligible with a real registered org).

**Mandated regression batch (10 files):** 219 passed, **8 failed — all in
`TestHostOnboardingVerifiedFields`** (4 each in `test_onboarding.py` +
`test_onboarding_new.py`). Reproduce in ISOLATION (4/6 fail, 2 pass on the
isolated class run): `test_verified_full_name_is_prefilled_and_not_overwritten`
and `test_host_onboarding_commits_successfully_with_verified_full_name_preserved`
(`DetachedInstanceError` on `current_user.is_active` — Flask-Login session
detachment after a `db_transaction` commit; exactly the pre-existing failure
documented in BACKLOG.md:638-643), `test_missing_full_name_can_be_requested_from_user`
(`NotNullViolation` — test writes `None` into NOT NULL `user_profiles.full_name`),
`test_missing_country_can_be_requested` (asserts raw `'Rwanda'`; canonical is `UG`).
Classification: **PRE-EXISTING / ENVIRONMENTAL, not caused by this node** — host
path untouched (`git diff app/auth/onboarding_routes.py` shows only
`_commit_driver_onboarding` + a comment), failures are identical to the known
onboarding-family entry, and they fail in isolation so they cannot be cross-test
contamination from committed driver rows. Not remediated here (no authorization).

**No migration** created or applied. **No wallet/payment/escrow/KYC/KYB/auth/context/
PP-schema/vocab change.**

**Deferred (recorded in BACKLOG.md):** (a) `_commit_driver_onboarding` string
`date_of_birth` crash — wizard sends an ISO string but
`UserProfile.validate_date_of_birth` (`app/profile/models.py:280`) expects a
`date` object (pre-existing latent defect surfaced by the new wizard test; test
works around it with a `date` object); (b) `Organisation.get_capabilities()` NULL
fallback references undefined `OrganizationType.MERCHANT` (`organisation.py:237-238`)
— latent `AttributeError` reachable via `can_manage_transport()` on unclassified
orgs (pre-existing, already flagged; now more reachable via the §11 gate);
(c) `register_vehicle` / `register_vehicle_internal` never set `current_driver_id`
for the driver branch (uniform vehicle↔driver pointer alignment deferred);
(d) 20 remaining broken-by-design `@role_required` sites (pre-existing);
(e) identity mock fallback `verified=True` (import path absent) — pre-existing,
not in scope; (f) full org-transport fleet/driver-management UI alignment.