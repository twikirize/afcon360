# STAGE 4A — UNIVERSAL PROVIDER ARCHITECTURE DECISION REPORT

**Node:** 4A (Architecture Decision Gate)
**Status:** PASS — decisions finalized, no code changed
**Date:** 2026-09-05
**Confidentiality:** Internal — engineering decision record

---

## §1 Executive Summary & Verdict

**Verdict: Option A — ProviderParticipation is the single universal provider-participation
table; OrganisationProviderCapability is consolidated into it (data migrated, API/JSON shape
preserved), then retired.**

Rationale:

- `ProviderParticipation` (`app/identity/models/provider_participation.py`) already implements
  the universal subject model (user_id XOR organisation_id with a single-subject CHECK
  constraint) that Option A requires — the schema already exists, is registered, and is under
  migration head `3a73c6e6cf29`.
- The lifecycle vocabulary is already shared: `ProviderCapabilityCode` / `ProviderCapabilityStatus`
  live in `organisation_provider_capability.py` and are reused by the PP service; transition
  semantics are identical (INTENT/ACTIVATED/DEACTIVATED/SUSPENDED/REVOKED).
- Today PP is service-layer + test-only (no routes, no production callers) while OPC is the live
  org write path with full HTTP endpoints. This split is the root contradiction: two competing
  org authorities with a "no dual-write" guard that is enforced by tests, not by architecture.
- Option B (keep both, formal contract) preserves needless duplication and a permanent divergence
  risk — rejected.
- Option C (string-typed polymorphic subject) loses FK integrity — rejected.

**Net change:** one source of truth (`provider_participations`), one lifecycle service, one
capability endpoint set (org + individual), eligibility computed independently, capability
activations never auto-create resources, transport onboarding decoupled from resource creation.

**No migration was created or applied. No schema was changed. No code was changed.**

---

## §2 Scope & Non-Goals

In scope (decisions only):

- subject representation
- org ownership authority
- multiple capabilities
- lifecycle semantics
- eligibility vs capability boundary
- provider context
- domain onboarding contract
- domain resource boundary
- transport architecture
- org provider migration strategy

Out of scope / don't-touch (see §22):

- wallet, KYC/KYB scoring internals, booking/payment flows, events ownership, BaseModel,
  `app/wallet/models/`, PostgreSQL ENUMs, migration graph head.

---

## §3 Task Classification

- ARCHITECTURAL / HIGH-RISK (cross-module ownership + migration implications).
- Decision-only node: no implementation performed.

---

## §4 Evidence Inspected (forensic inventory)

Models & services:

- `app/identity/models/provider_participation.py`
- `app/identity/models/organisation_provider_capability.py`
- `app/identity/services/provider_participation_service.py`
- `app/identity/services/capability_service.py`
- `app/core/model_registry.py` (both models registered: lines 17-18)
- `app/identity/models/__init__.py` (both exported)

Routes / onboarding / transport:

- `app/identity/routes.py` (org_bp capability endpoints: `list_capabilities` ~570, `activate_capability` ~591, through ~745; NO ProviderParticipation blueprint exists)
- `app/auth/onboarding_routes.py` (`_commit_organisation_onboarding` ~497, `_commit_host_onboarding` ~691, driver wizard `_commit_driver_onboarding` ~211, event-organiser onboarding ~799)
- `app/transport/services/provider_service.py` (`register_driver` ~526+, `register_organisation_transport`)
- `app/transport/routes.py` (`become_driver` ~557-586)
- `app/auth/context.py` (ContextType ~19-25, `_host_contexts` ~487, `_driver_contexts` ~462)
- `app/accommodation/services/identity_service.py` (`can_host` ~28-52, `can_org_host` ~55-69)
- `app/accommodation/services/host_service.py` (`create_property` ~80-91)
- `app/accommodation/routes.py` (`_ensure_host_identity` ~4049-4077, `host_create_listing` ~4355)
- `app/auth/kyc_compliance.py` (`calculate_kyc_tier` ~188-314)

Tests:

- `tests/test_provider_participation.py` (lifecycle + no-dual-write assertion + `participation_to_dict` internal-id safety)
- `tests/test_org_provider_capability.py`
- `tests/test_onboarding_new.py` (lines ~631-661 back-compat behavior)
- transport register-driver tests

Migrations:

- linear chain, head `3a73c6e6cf29` (no competing heads):
  `8a0deccce6f6 → 20260830_1420 → f91075478868 → c2f495a06ed4 → 20260902_2255 → 9f75675b5e52 → 3a73c6e6cf29`
- both new tables present (`provider_participations`, `org_provider_capabilities`)

Prior-stage documentation:

- `EXECUTIVE_SUMMARY.md` (DetachedInstanceError baseline failure root cause — Redis user_loader cache)
- `STAGE_4B2_DISCOVERY_REPORT.md` (baseline 121 passed / 4 failed; cross-test DB contamination)
- `SESSION_4B1_CHRONICLE.md` (frozen decisions)
- `BACKLOG.md` (4 known baseline failures, transport remediation items)
- `flow_trace.md` (documents a `save_as_intent_only` query-param read + "Property listed
  successfully" flash that do NOT exist in current code — stale doc, see §19)

Verification executed:

- `git status` / `git log` (repo snapshot, no destructive git operations)
- `& .venv/Scripts/python.exe -c "from app import create_app; print('IMPORT_OK')"` → `IMPORT_OK`
- `rg` unavailable on this shell — searches used PowerShell `Select-String` / Grep

---

## §5 Required Question #1 — ProviderParticipation vs OrganisationProviderCapability

**Question:** Is ProviderParticipation the "universal provider" table, or is OPC the retained
org representation?

**Answer: Option A — ProviderParticipation is the single source of truth for BOTH subjects.**

### Option A — Universal ProviderParticipation (chosen)

| Property | PP today | Gap to close |
|---|---|---|
| Schema universal subject | YES — `user_id` XOR `organisation_id` + CHECK | none |
| Canonical code/status vocabulary | reuses OPC enums | relocate/mirror onto PP; keep `ProviderCapabilityCode` symbols import-compatible |
| Org lifecycle service fns | YES (create/activate/deactivate/suspend/revoke org) | wire to routes + onboarding |
| Org HTTP API | none | re-point OPC endpoints onto PP; identical JSON shape |
| Org onboarding writer | OPC (via `_commit_organisation_onboarding`) | write PP org rows only |
| No-dual-write | enforced by test only (`pp_org_rows == 0`) | enforced by code (single writer) |
| Data retention | individual rows only today | migrate existing OPC rows → PP |

### Option B — Keep both, formal contract (rejected)

- Two semantic twins (same vocabulary, same transitions, same meaning) → artificial split.
- Permanent divergence risk; "no-dual-write" stays a test assertion instead of an invariant.
- Duplicated maintenance (service, routes, serialization).

### Option C — String-typed polymorphic subject (rejected)

- `owner_type`/`owner_id` pattern (cf. transport `Vehicle.owner_type`) loses FK integrity; the
  repo already documents transport `owner_id` FKlessness as debt to fix — do not replicate it.
- Dual nullable FK + single-subject CHECK (already implemented) is the superior, approved-style
  pattern.

---

## §6 Subject Representation (individual vs organisation)

**Decision:** keep dual nullable FK columns with a `ck_provider_participations_single_subject`
CHECK — exactly one of `user_id`, `organisation_id` set.

- individual row: `user_id` set, `organisation_id` NULL
- org row: `user_id` NULL, `organisation_id` set

Alternative (string type discriminator) rejected in §5 (Option C). Dual-FK preserves referential
integrity and queryability.

---

## §7 Organisation Ownership / Authority for Org Rows

- **SUBJECT** = the Organisation. The row belongs to the org, not to the acting user.
- **ACTOR** = authenticated user acting within the organisation.
- **CONTEXT** = actor must be an ACTIVE org member of that organisation at time of operation.
- **AUTHORITY matrix (org rows):**

| Operation | Required actor |
|---|---|
| Declare (INTENT) | any active org member (org onboarding / explicit declaration) |
| Activate | org_owner |
| Deactivate | org_owner |
| Suspend | org_owner or platform super_admin |
| Revoke | org_owner or platform super_admin |

- `user_id` on an org row stays NULL; the actor is recorded in the audit trail, NOT in the row.

---

## §8 Multiple Capabilities per Subject

**Decision:** one row per (subject, capability_code). A subject may hold several rows
(e.g. ACCOMMODATION + TRANSPORT).

- Uniqueness enforced by `uq_provider_participation` (user, code) and (organisation, code) — already present in schema.
- `capability_code` stays on the participation row — no third-layer capability table.

---

## §9 Lifecycle Semantics (canonical state machine)

States: `INTENT`, `ACTIVATED`, `DEACTIVATED`, `SUSPENDED`, `REVOKED` (terminal).

```
                (revoke)              (revoke)
   INTENT ────────────────► REVOKED ──────────► (terminal)
     │
     ├── activate ──► ACTIVATED
     │                 │    │
     │                 │    ├── deactivate ─► DEACTIVATED ─► activate ─► ACTIVATED
     │                 │    └── suspend ────► SUSPENDED ──► activate ─► ACTIVATED
     │                 │                                  └► deactivate ─► DEACTIVATED
     └── deactivate ──► DEACTIVATED
```

- `INTENT` = declared, not operational.
- `ACTIVATED` = operational declaration; **never** auto-creates domain resources, never auto-grants permission.
- `DEACTIVATED` / `SUSPENDED` = non-operational, reversible.
- `REVOKED` = terminal, non-reversible (service-level guard; no state transitions out).
- Both current services (`capability_service._ALLOWED_TRANSITIONS`, PP service) agree on this set — no semantic conflict to resolve; only consolidation.

---

## §10 Eligibility vs Capability (the core separation)

**Decision:** eligibility is COMPUTED and EVIDENCE-BASED; capability is DECLARED and BOOKKEEPING.

| Aspect | Eligibility | Capability |
|---|---|---|
| Nature | derived check | recorded lifecycle row |
| Source | `can_host`, `can_org_host`, `OrganisationKYBService.compute_status`, `calculate_kyc_tier`, transport driver validation | `provider_participations` |
| Persisted in provider layer | NO | YES |
| Auto-updates when KYC changes | recomputed on read | NOT auto-written (bookkeeping) |
| Enforcement point | domain onboarding / operational gates | provider-layer state check |

**Can capability exist before eligibility?** YES — INTENT may precede eligibility (a user/org
may declare intent without yet qualifying).

**Can capability ACTIVATE before eligibility?** NO — activation MUST pass the domain eligibility
check at the moment of activation (authority: accommodation/transport/domain eligibility
services).

**Can capability stay ACTIVATED when eligibility later drops?** YES (bookkeeping) — but
operational enforcement fails because eligibility is re-evaluated at every operational
checkpoint. Auto-suspending capability on KYC drift is NOT done in 4A; a compliance-driven
`suspend`/`revoke` is an explicit, audited action.

**Two-gate enforcement rule:** an operational write (create accommodation listing / driver
vehicle op) requires BOTH:
1. eligibility true at the checkpoint (domain authority), AND
2. capability `ACTIVATED` for that (subject, code).

---

## §11 Provider Context (decisions)

- **Keep the existing session-based, DB-revalidated context system** (`app/auth/context.py`;
  ContextType: PERSONAL, ORGANISATION, EVENT, DRIVER, ACCOMMODATION_HOST, PLATFORM).
- Context descriptors derive from ELIGIBILITY + assignments, NOT from capability rows.
  (Current proof: `_host_contexts` uses `can_host`/`can_org_host`; `_driver_contexts` uses
  DriverProfile compliance state. Preserve this.)
- **Do NOT add** TRANSPORT_PROVIDER / TOURISM_PROVIDER / VENUE_PROVIDER / EVENT_MANAGER context
  types in 4B. Transport uses DRIVER (individual) + ORGANISATION (org) contexts. New domain
  context types are added only when that domain ships onboarding + resources (tourism/venue).
- Capability `ACTIVATED` is NOT required to select a provider context; context = "where you are",
  capability = "what you may operate". Operational writes apply the two-gate rule (§10).

---

## §12 Domain Onboarding Contract

**The provider layer MUST NOT create domain resources.**

- Provider layer scope: assert subject existence, register/order capability rows,
  `intent`/`activate`/`deactivate`/`suspend`/`revoke`, expose capability status to consumers.
- Domain layer scope: resource creation (Property, DriverProfile, Vehicle, Event).
- The provider layer may hand the domain layer: subject identity, capability code + status,
  eligibility decision (from domain authority), actor identity (audit). It never persists domain state.

---

## §13 Domain Resource Boundary Matrix

| Domain | Resource(s) owned | Provider participation | Correct owner |
|---|---|---|---|
| Accommodation | Property | `ACCOMMODATION` (individual) / `ACCOMMODATION` (org) | Accommodation |
| Transport | DriverProfile, Vehicle | `TRANSPORT` (individual) / `TRANSPORT` (org) | Transport |
| Events | Event | event-organiser role + onboarding (no capability row today) | Events |
| Tourism | TourismProvider capability refs | code exists; no domain, no resource | (unowned until shipped) |
| Venue | VenueProvider capability refs | code exists; no domain, no resource | (unowned until shipped) |

**Current violations to record:**
- Transport creates `DriverProfile` + `Vehicle` inside provider onboarding (same commit) — §17.
- Org accommodation listing creation gate uses context-match only; `can_org_host` is not checked
  at creation (see §15) — enforcement gap to close in 4B (not in 4A).

---

## §14 Transport Architecture Decisions

- **Split provider declaration from resource creation:**
  1. declare `TRANSPORT` intent (PP row) — provider layer
  2. domain onboarding creates `DriverProfile` only — transport domain (`register_driver`)
  3. `Vehicle` becomes a separate domain operation after an eligible `DriverProfile` exists
- `become_driver` route guards stay: `login_required` + `require_profile_completion` +
  `require_kyc_tier(3)` + role — but the role guard is questionable (see §18 finding F-2).
- Org transport participants use ORGANISATION context + org KYB eligibility; org-driven vehicles
  are a separate domain operation.

---

## §15 Eligibility & Enforcement Gaps Observed (report, not fix)

- `can_host` gates property creation at `accommodation/routes.py:~4051`; `can_org_host` is only
  consulted in `context.py:~519`, NOT at org listing creation. **Gap G-1:** org-host listing
  creation does not apply `can_org_host` (org-level KYC/KYB) at the write checkpoint.
- `register_driver` signature suspicion: route calls `register_driver(data, user_id=...)`; service
  signature appears `(user_id, driver_data, ...)` — **Gap G-2 (latent transport bug)** to verify
  in 4B before touching transport flows.
- Provider context does not consult participation tables — by design (§11), eligibility-based.
- No ProviderParticipation routes exist → no production individual capability API today. **Gap G-3**
  to close in 4B: wire individual capability endpoints (JSON shape parallel to org endpoints).

These are BEHAVIORAL/ARCHITECTURAL defects records — do NOT fix in 4A, and only fix under
4B-node authorization.

---

## §16 Organisation Provider Migration Strategy (OPC → PP)

**Proposal only — migration is not executed in this node.**

1. Data backfill (`org_provider_capabilities` → `provider_participations`):
   - `organisation_id` → `organisation_id`
   - `capability_code` → `capability_code` (same vocabulary)
   - `status` → `status` (same vocabulary)
   - `activated_at`, `verified_at`, `meta`, `is_deleted`, `created_at`, `updated_at` → 1:1
   - `user_id` = NULL (org rows), satisfying `ck_provider_participations_single_subject`
2. After verified copy: switch all org writers to PP (`_commit_organisation_onboarding`, any
   capability-service callers), switch capability routes to PP service.
3. Keep OPC JSON response shape identical for API compatibility.
4. Retire OPC table/service/route after compat-window verification.
5. No new CHECK constraints → no `sync_check_constraints.py` needed (verify in 4B, §33).

---

## §17 Universal / Individual / Organisation / Accommodation / Transport / Forbidden Flow Graphs

### §17.1 Universal provider flow (all subjects)

```
Subject (user | org, active-org context for org rows)
   │
   ▼
Provider layer: declare INTENT (capability_code)      [provider_participations]
   │
   ▼  (await eligibility? no — INTENT may precede)
Provider layer: activate  (gated: domain eligibility true)
   │
   ▼
ACTIVATED ── operational writes apply two-gate rule ──► Domain resource (owned by domain)
```

### §17.2 Individual flow (accommodation host)

```
User → host onboarding -> create_individual_intention(ACCOMMODATION)         [PP row INTENT]
  → can_host(user) true (KYC/profile)                          [eligibility]
  → activate_individual_intention(user, ACCOMMODATION)          [ACTIVATED]
  → context: ACCOMMODATION_HOST (descriptor, session)
  → host_create_listing (two-gate: can_host + ACTIVATED)        [Property — accommodation owns]
```

### §17.3 Organisation flow (org accommodation = today's OPC path, migrated)

```
Org owner/member → _commit_organisation_onboarding → OPC intent row (MIGRATES to PP org INTENT)
  → can_org_host(org) true (org KYC/KYB)                       [eligibility]
  → org_owner activates                                       [PP org ACTIVATED]
  → context: ORGANISATION / ACCOMMODATION_HOST (descriptor)
  → org listing creation (must ADD can_org_host gate in 4B — G-1)
```

### §17.4 Transport flow (target)

```
User → become_driver (declaration) → PP TRANSPORT INTENT (new; not today)
  → validate_driver_eligibility (KYC tier/provider role; role guard TBD — F-2)
  → activation (explicit, eligibility-gated)
  → register_driver → DriverProfile (transport owns)   [Vehicle = separate op]
```

### §17.5 Forbidden flow (must never happen)

```
A capability activation MUST NOT:
  - create Property / Vehicle / DriverProfile / any domain resource
  - grant a permission/role directly
  - auto-activate due to KYC/KYB changes
```

---

## §18 Legacy / Tech-Debt Findings (recorded, NOT fixed in 4A)

| ID | Finding | Class | Action |
|---|---|---|---|
| F-1 | `save_as_intent_only=True` default in host onboarding; legacy `False` path creates Property (onboarding_routes.py:691, legacy ~789-792). Back-compat test at test_onboarding_new.py:631-661. | decked path | dispose in 4B cleanup after compat window |
| F-2 | `@role_required("provider")` on `become_driver` — no "provider" role constant in roles.py and no seed found via grep. | latent auth gap | verify/decide in 4B (may be delegated-by-name role) |
| F-3 | `flow_trace.md` documents `save_as_intent_only` query-param read + "Property listed successfully" flash that don't exist in code | stale doc | update when behavior finalizes |
| F-4 | `register_driver` signature mismatch suspicion (G-2) | latent bug | verify in 4B before transport edits |
| F-5 | `capability_to_dict` exposes internal `id` / `organisation_id` on the OPC API (dual-ID leak) | security/dual-ID | sanitize in 4B (mirror `participation_to_dict` which is internal-ID-safe and test-covered) |
| F-6 | No PP routes → no live individual capability API (G-3) | feature gap | wire in 4B |
| F-7 | org listing creation lacks `can_org_host` gate (G-1) | enforcement gap | close in 4B |

---

## §19 Documentation / Baseline Test Status (recorded, NOT fixed)

- 4 known baseline test failures on record (BACKLOG / STAGE_4B2): DetachedInstanceError,
  full_name NOT NULL, country normalization, 302-vs-200.
- Baseline: 121 passed / 4 failed (STAGE_4B2_DISCOVERY_REPORT).
- Test-DB contamination root cause known (persistent test DB; committed HTTP data not rolled
  back by `db_session.rollback()`).
- These are evidence of current state, not authorization to alter tests (§9 of constitution).

---

## §20 Data Ownership Matrix

| Data | Owner | Writer(s) | Reader(s) |
|---|---|---|---|
| `provider_participations` | Identity (provider layer) | PP service only (after 4B; today PP service + tests) | onboarding, context, domain onboarding, capability API |
| `org_provider_capabilities` | Identity | OPC service (today) → retired after migration | onboarding / capability API (today) |
| `Property` | Accommodation | `HostService.create_property` | booking flows, listings |
| `DriverProfile` / `Vehicle` | Transport | `register_driver`, `register_vehicle` | transport ops |
| `Event` | Events | event organiser onboarding | ticketing |
| KYC/KYB state | KYC / Compliance | KYC/KYB services | `calculate_kyc_tier`, `can_host`, `can_org_host`, KYB |
| Capability code/status vocabulary | Identity | (enum module) | PP + OPC services (today) |

---

## §21 Reader / Writer Graph (post-4B target)

```
Writer:  PP lifecycle service ─────────► provider_participations
Reader:  identity/routes (capability API)  ◄─────────────────┤
Reader:  onboarding_routes (org/host/driver declaration)      ├─► provider_participations
Reader:  context.py (descriptors use eligibility, NOT PP rows) │   (context intentionally no read)
Reader:  domain onboarding gates (two-gate rule)
Reader:  eligibility authorities (KYC/KYB) — never written by provider layer
```

---

## §22 Do-Not-Touch Areas (verified untouched)

- `app/wallet/models/*`, wallet services/repos/payments — CRITICAL, no authorization.
- `app/models/base.py` / `BaseModel` — unchanged.
- PostgreSQL ENUM types — none introduced.
- Migration graph — no new migrations, no `flask db` execution, no head changes.
- KYC/KYB scoring internals — read-only.
- Technology stack, `.env*`, secrets — untouched.
- No test files modified; no test suite executed (read-only decision node).

---

## §23 Required Question #2 — Human Readable & Workflow Summary

Decision record is written for humans and other agents: this file IS the durable decision
record (§43 handoff/approval). No memory file updated (per §10 memory policy — decisions live
here, memory is not a receipt).

---

## §24 Decision Record (ADR-4A-001 … 010)

### ADR-4A-001 — Universal ProviderParticipation

- **Status:** ACCEPTED
- **Decision:** `provider_participations` is the single provider-participation table for both
  individual and organisation subjects.
- **Context:** PP already implements universal subject schema; OPC duplicates org semantics.
- **Evidence:** PP model CHECK constraint; registry lines 17-18; test asserts org onboarding
  writes 0 PP rows (formalizes today's split).
- **Options:** A (universal PP — chosen) / B (retain both) / C (string polymorphic id).
- **Why:** single source of truth; no divergence; schema already exists.
- **Consequences:** org writers/routes re-point to PP; OPC retired after data migration.
- **Rejected:** B — semantic twin duplication; C — loss of FK integrity.
- **Implementation impact:** §16 migration + §31 blueprint B-4?
- **Verification:** post-migration row counts match; capability API JSON identical; `pp_org_rows == 0` assertion obsolete.

### ADR-4A-002 — Subject representation (dual FK + single-subject CHECK)

- **Status:** ACCEPTED
- **Decision:** keep `user_id` XOR `organisation_id` columns + `ck_provider_participations_single_subject`.
- **Context:** integrity over string discriminators.
- **Evidence:** PP table + migrations; transport `Vehicle.owner_type` FKlessness documented debt.
- **Options:** dual-FK+CHECK (chosen) / owner_type string / separate tables.
- **Why:** FK integrity, queryability, least new work.
- **Consequences:** org rows always have `user_id NULL`; actor only in audit trail.
- **Rejected:** owner_type string (FK loss); separate tables (Option B).
- **Implementation impact:** none (schema exists). **Verification:** existing CHECK tests.

### ADR-4A-003 — Org authority matrix

- **Status:** ACCEPTED
- **Decision:** declare=any active member; activate/deactivate=org_owner; suspend/revoke=org_owner or platform super_admin.
- **Context:** identity/authorization policy from prior stages.
- **Evidence:** OPC route docstrings + PP service authority checks.
- **Options:** (as decided) / platform-admin-only / org_owner-only for all ops.
- **Why:** least-privilege, org autonomy, escalation for compliance actions.
- **Consequences:** suspend/revoke require elevated authority + audit.
- **Rejected:** org_owner-only suspend (blocks compliance), platform-only declare (blocks self-service).
- **Implementation impact:** mirror in PP service + routes. **Verification:** negative tests per actor.

### ADR-4A-004 — Multiple capabilities per subject

- **Status:** ACCEPTED
- **Decision:** one row per (subject, capability_code); uniqueness enforced.
- **Context:** subjects may operate multiple domains.
- **Evidence:** unique constraints in PP/OPC migrations.
- **Options:** one row per subject with set column (rejected) / row-per-code (chosen).
- **Why:** simple lifecycle per code; matches existing schema.
- **Consequences:** list-by-subject APIs return multiple rows.
- **Rejected:** set-column (complex state, poor transitions).
- **Implementation impact:** none. **Verification:** existing uniqueness tests.

### ADR-4A-005 — Lifecycle state machine

- **Status:** ACCEPTED
- **Decision:** INTENT/ACTIVATED/DEACTIVATED/SUSPENDED/REVOKED(terminal) with transitions per §9.
- **Context:** vocabulary already shared; semantics already identical.
- **Evidence:** both service transition tables agree.
- **Options:** as-is (chosen) / add PENDING_KYC (rejected — eligibility is separate).
- **Why:** eligibility is computed, not a capability state; avoids KYC duplication.
- **Consequences:** no new state for KYC; two-gate enforcement rule.
- **Rejected:** PENDING_KYC state.
- **Implementation impact:** one transition module (PP service). **Verification:** state-transition tests.

### ADR-4A-006 — Eligibility derived, capability bookkeeping; separate lifecycle

- **Status:** ACCEPTED
- **Decision:** capability state and eligibility are independent; qualification requirements used
  only where required (activation/operational gates); qualification status never auto-writes capability.
- **Context:** §10.
- **Evidence:** current architecture derives context from eligibility; capability not read by context.
- **Options:** tied lifecycle (auto-acivate/unlink on KYC change) — REJECTED / decoupled (chosen).
- **Why:** avoids capability re-entering KYC; compliance actions remain explicit.
- **Consequences:** capability may remain ACTIVATED while eligibility drifts; enforcement blocks writes.
- **Rejected:** auto-sync/delink.
- **Implementation impact:** two-gate checks at operational points. **Verification:** negative enforcement tests.

### ADR-4A-007 — Provider context stays eligibility-derived, session-based

- **Status:** ACCEPTED
- **Decision:** keep `context.py` as-is; no new provider context types in 4B.
- **Context:** §11.
- **Evidence:** `_host_contexts`/`_driver_contexts` derive from eligibility/assignments.
- **Options:** capability-driven context (rejected) / eligibility-driven (chosen).
- **Why:** context = workspace; capability = permission gate; avoids second capability system.
- **Consequences:** no PP reads from context descriptors.
- **Rejected:** deriving context from capability.
- **Implementation impact:** none. **Verification:** existing context tests.

### ADR-4A-008 — Provider layer never creates domain resources

- **Status:** ACCEPTED
- **Decision:** declaration/activation never create Property/Vehicle/DriverProfile/Event.
- **Context:** §12; frozen prior decision.
- **Evidence:** two-gate + domain ownership invariants; current transport violation (§14).
- **Options:** provider-owned creation (rejected) / domain-owned (chosen).
- **Why:** ownership boundaries (§17 constitution); the transport violation is the counter-example.
- **Consequences:** transport onboarding decoupled; Vehicle becomes separate op.
- **Rejected:** provider-side creation.
- **Implementation impact:** transport boundary refactor in 4B (B-6?). **Verification:** no-resource-on-activation tests.

### ADR-4A-009 — Transport split (declaration → DriverProfile → Vehicle)

- **Status:** ACCEPTED
- **Decision:** PP TRANSPORT intent → register_driver creates DriverProfile only → Vehicle separate op.
- **Context:** §14; current `_commit_driver_onboarding` + `register_driver` create both.
- **Evidence:** onboarding_routes.py:211, provider_service.py:526+.
- **Options:** status-quo single-shot (rejected) / split (chosen).
- **Why:** fixes boundary violation; Vehicle depends on DriverProfile.
- **Consequences:** wizard flow changes; Gate G-2 must be resolved first.
- **Rejected:** single-shot creation.
- **Implementation impact:** transport domain + onboarding changes in 4B. **Verification:** transport onboarding tests.

### ADR-4A-010 — OPC retirement via data migration + API compat

- **Status:** ACCEPTED
- **Decision:** migrate OPC data into PP; re-point writers/routes; keep JSON shape; retire OPC.
- **Context:** §16.
- **Evidence:** 1:1 field mapping; identical vocabulary; no foreign refs to OPC outside its own module/tests.
- **Options:** live dual-write compat (rejected) / migrate-then-retire (chosen).
- **Why:** single-authority invariant; minimal surface change.
- **Consequences:** data backfill migration proposal; OPC service/routes become PP fans or are retired.
- **Rejected:** indefinite dual-write.
- **Implementation impact:** `org_provider_capabilities` retired after compat window. **Verification:** migration row audit + API JSON diff.

---

## §25 Stage 4B Blueprint (grouped, decision-level)

| File | Current responsibility (evidence) | Required change (4B) | Why | Dependencies | Risk | Tests | Migration |
|---|---|---|---|---|---|---|---|
| `app/identity/models/provider_participation.py` | universal subject schema | no schema change; ownership doc (canonical vocabulary import) | decision §5-6 | — | low | existing | none |
| `app/identity/models/organisation_provider_capability.py` | OPC + canonical enums | keep enums importable; retire after ADR-4A-010 | consolidation | ADR-4A-001/010 | med | OPC tests → migrated | data backfill |
| `app/identity/services/provider_participation_service.py` | PP lifecycle | become single lifecycle service; wire routes | ADR-4A-001/003/005 | — | med | expand PP lifecycle | none |
| `app/identity/services/capability_service.py` | OPC lifecycle | fold into PP or fan-out compat; sanitize `capability_to_dict` (F-5) | F-5, ADR-4A-010 | ADR-4A-001 | med | API JSON diff | none |
| `app/identity/routes.py` org_bp capability endpoints | live OPC API | re-point onto PP; add individual capability endpoints (G-3) | G-3 | ADR-4A-001 | med | route tests | none |
| `app/auth/onboarding_routes.py` | `_commit_organisation_onboarding` writes OPC intent | write PP org rows; remove legacy `save_as_intent_only` path (F-1) | ADR-4A-001, F-1 | ADR-4A-010 | med-high | `test_onboarding_new` back-compat | data backfill first |
| `app/transport/services/provider_service.py`, `routes.py` | `register_driver` creates DriverProfile+Vehicle; role guard | split: declaration → DriverProfile → Vehicle; resolve G-2/F-2 | ADR-4A-009, F-2 | G-2 verification | high | transport onboarding | none |
| `app/auth/context.py` | descriptors from eligibility | unchanged (ADR-4A-007); optionally document | — | — | low | context tests | none |
| `app/accommodation/routes.py` host listing | context-match gate only | add `can_org_host` gate at org listing creation (G-1) | enforcement §13 | eligibility services | med | accommodation host tests | none |
| `tests/*` | current baselines | migrate OPC→PP tests; new two-gate/enforcement tests | ADRs | — | med | — | none |
| migrations | head `3a73c6e6cf29` | data-backfill proposal (OPC→PP) only; no new constraint syncs | ADR-4A-010 | — | high | row-audit | YES (proposed) |

---

## §26 Risk Register (architectural, decision-level)

| # | Risk | Likelihood | Impact | Mitigation (4B) |
|---|---|---|---|---|
| R-1 | OPC→PP migration data loss / mismatch | low | high | dry-run row audit, orphan detection, API-JSON diff before switch |
| R-2 | Transport refactor breaks live driver onboarding | med | high | resolve G-2/F-2 first; keep single-shot path under feature/deck flag during transition |
| R-3 | Removing legacy `save_as_intent_only` breaks existing in-flight host flows | low | med | keep compat window; back-compat test until migration verified |
| R-4 | Capability API dual-ID leak (F-5) shipped in new individual endpoints | med | med | reuse internal-ID-safe `participation_to_dict` shape only |
| R-5 | Context/capability coupling regresses back to capability-driven context | low | med | documented decision ADR-4A-007 + context tests |
| R-6 | Test-DB contamination undermines verification graph | high | med | per-test unique subjects; scoped assertions; isolation strategy continues |

---

## §27 Examination and Approval Items for Human Reviewer

Prior to approving 4B, confirm:

1. **Data migration execution** (OPC→PP) requires explicit user authorization under §20 Migration Law — propose exact commands, do not execute.
2. **Transport remediation authorization** (split onboarding) — HIGH_RISK, requires 4B node contract.
3. **Role-guard decision for "provider"/"driver" roles** (F-2) — needs identity/authorization policy confirmation.
4. **Legacy path disposition** (F-1, `save_as_intent_only=False`) — approval to remove after compat window.
5. **Any new capability codes** (tourism/venue) — deferred; do not create without spec (§6).

---

## §28 Next-Graph-Node Recommendation

- **RECOMMENDED NEXT NODE:** 4B-1 (Provider architecture consolidation sprint).
- Immediate prerequisites: explicit approval of this gate + authorization for the OPC→PP data
  migration + G-2 signature verification.

---

## §29 Final Architecture Diagram (target, post-4B)

```
                          ┌─────────────────────────────────────────────┐
                          │          IDENTITY (provider layer)          │
                          │                                             │
   individual  ──────────►│  provider_participations                    │
   user/org    ──────────►│  subject: user_id XOR organisation_id       │
   (org: active            │  state: INTENT/ACTIVATED/DEACTIVATED/      │
    member ctx)            │         SUSPENDED/REVOKED                  │
                          │      ▲                                      │
                          │      │ (only writer)                        │
                          │  PP lifecycle service  ◄── act/act/susp/rev │
                          │      ▲                                      │
                          │   capability API (org+ind, JSON compat)     │
                          └──────┼──────────────────────────────────────┘
                                 │ eligibility decision (read-only, domain authority)
                                 ▼
   ┌──────────┬──────────────────┴──────────┬───────────────┬──────────────┐
   ▼          ▼                             ▼               ▼              ▼
KYC/KYB   can_host/                 can_org_host       transport      (future)
eligibility can_org_host                               eligibility   tourism/venue
 authorities  (accommodation)                          (+ domain)
                                 │
                                 ▼
                    ELIGIBILITY (computed at every operational checkpoint)
                                 │
   OPERATIONAL GATE (two-gate): eligibility TRUE + capability ACTIVATED
                                 │
                    ┌────────────┴─────────────┐
                    ▼                          ▼
        DOMAIN ONBOARDING (owns resources)   CONTEXT (session, derived)
        Property / DriverProfile / Vehicle    ACCOMMODATION_HOST / DRIVER / ...
                    │
                    └──► production flows (bookings, rides) — untouched by 4A
```

---

## §30 Approval Gate

```
STATUS: PASS
NODE: 4A-ARCHITECTURE-DECISION-GATE

Required Question #1 answered:
   Option A — ProviderParticipation is the universal provider table; OPC consolidated into PP.

Required Question #2 answered:
   Decision record: STAGE_4A_UNIVERSAL_PROVIDER_ARCHITECTURE_DECISION_REPORT.md (this file).

File created (single deliverable): STAGE_4A_UNIVERSAL_PROVIDER_ARCHITECTURE_DECISION_REPORT.md
NO CODE CHANGED: [VERIFY via git status / diff — report file only added]
NO MIGRATION CREATED/APPLIED
NO TEST MODIFIED / NO TEST SUITE RUN

APPROVAL REQUIRED to proceed to Stage 4B.
```

---

*End of Stage 4A report. Engineered read-only; consolidated evidence; STOP for approval.*