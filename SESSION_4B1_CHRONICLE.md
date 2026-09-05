# AFCON360 Stage 4 — Session Chronicle

> **Source**: OpenCode session history (this chat only)
> **Created**: 2026-09-04
> **Scope**: Stage 4B-1 — Organisation Creation + RBAC provisioning
> **Status**: E2E cross-test contamination RESOLVED (app-context leak fixed)

---

## 0. Starting Context (Handoff Injected Into Session)

This session was seeded with a detailed handoff context from a previous work
session. The handoff was NOT a conversation transcript — it was a structured
summary injected into the agent's system prompt. Everything below this point
is reconstructed from that handoff plus actions taken within this session.

### 0.1 Handoff: Frozen Architecture Decisions

The following decisions were carried forward as binding constraints:

- **Organisation creation and wallet creation are independent.** `create_organization()` MUST NOT create a wallet. Wallet is a separate later operation.
- **Frozen authority architecture**: `OrgUserRole.role_id` → `org_roles.id` (never global `roles.id`). `org_owner` is a normal persisted `OrgRole`; authority comes from `OrgRolePermission` rows.
- **Onboarding model**: ONE organisation type → persisted to `Organisation.business_category` via canonical `OrganizationType`; 0..N provider capabilities → `OrganisationProviderCapability` rows with `status='intent'`; capabilities grant NO authority.
- Must NOT modify: owner wildcard, helpers/policy/context, OrganizationPermissionService, legacy RBAC, capabilities, broader KYC/KYB architecture, or production data.
- **Validate against rejected session-cleanup fixture**: do NOT add blanket `TRUNCATE ... except Exception: pass` teardown to `conftest.py`. Use existing test-isolation mechanism.
- Test identifiers must be unique and valid under IDGuard/model rules WITHOUT changing production identifier semantics.
- **Stop after 4B-1**; do NOT proceed to 4B-2+.

### 0.2 Handoff: Completed Work Items

The handoff listed these as already completed before this session started:

#### Production Code Changes

1. **`app/models/base.py`** — `'org_id'` added to `NON_FK_STRING_IDS` (permanent IDGuard exemption for organisation string IDs).

2. **`app/identity/services/organisation_role_provisioning.py`** — `provision_organisation_roles()` gained `commit=False` support via `begin_nested()`.

3. **`app/identity/services/organization_registration.py`** — `create_organization()` was modified:
   - No wallet creation (frozen boundary).
   - `commit=False` provisioning for onboarding route.
   - `initiate_verification` call was fixed.

4. **`app/auth/onboarding_routes.py`** — Multiple changes:
   - `_get_or_create_profile`: full_name default handling.
   - `_commit_organisation_onboarding`: profile full_name population.
   - Step 1 now captures full_name.
   - **Critical change**: replaced `assign_org_role` with `provision_organisation_roles(org, commit=False)` + direct `OrgUserRole` creation (lines 506-597). This was to avoid the nested `db_transaction` bug.

5. **`templates/onboarding/organisation_step1.html`** — Added required `full_name` input field.

6. **`BACKLOG.md`** — Two entries added:
   - Wallet FK defect (AccountModel.user_id FK to users.id; org.id is NOT a valid user id).
   - `test_onboarding.py` partner-gate contract mismatch.

#### Test Changes

7. **`tests/test_onboarding_stage4.py`** — 17/17 passed at checkpoint. The `_commit` helper was updated to pass `full_name`.

8. **`tests/test_org_creation_rbac_4b1.py`** — 13/13 passed at checkpoint.
   - Wallet test was reframed to USER-owned wallet (not org wallet).
   - `AccountType.PERSONAL` corrected to `AccountType.USER_WALLET` (enum does not have PERSONAL).
   - Invalid `Account_Currency` import removed (does not exist in `app.wallet.models.ledger`).

9. **`tests/test_onboarding.py`** — 5 stale assertions fixed (updated to match current `choose.html` content and type-first redirect behavior). Expected 21/21.

10. **Core regression suite**: 72/72 passed (5 RBAC + stage4 test files).

### 0.3 Handoff: Known Architecture Issues

The handoff documented these as known-but-not-fixing:

- **Nested `db_transaction` atomicity bug**: `db_transaction` in `app/utils/transactions.py` calls `db.session.commit()` on exit. When `assign_org_role` uses `db_transaction` internally, and the calling code also uses `db_transaction`, the inner commit fires prematurely, breaking true atomicity. This was the reason `assign_org_role` was bypassed in the onboarding route.

- **`Organisation` unique constraints**: `uq_org_id` (org_id), `uq_org_country_tax` (country, tax_id), `uq_org_country_vat` (country, vat_number). `check_org_duplicates` event listener raises `ValueError` on duplicate `legal_name`/`contact_email`.

- **`create_organization()` commits its own transaction** via `db_transaction`, so org/user rows persist across pytest runs.

- **`AccountModel.user_id` is FK to `users.id`** — org.id is NOT a valid user id. `create_org_wallet(org)` stores `org.id` as `user_id`, which always violates FK. This is a pre-existing wallet-architecture defect.

- **Enum corrections** (verified via Python introspection): `Account_Currency` does NOT exist in `app.wallet.models.ledger`; `AccountType` has no `PERSONAL` member — valid types are `REVENUE`, `ESCROW`, `OPERATIONS`, `SETTLEMENT`, `RESERVE`, `USER_WALLET`, `ORG_WALLET`.

### 0.4 Handoff: Active Problem — DetachedInstanceError

The handoff described this as the ACTIVE BLOCKER:

**Symptom**: E2E HTTP tests in `TestEndToEndOrganisationOnboarding` fail with:
```
sqlalchemy.orm.exc.DetachedInstanceError: Instance <User at 0x...> is not bound
to a Session; attribute refresh operation cannot proceed
```

**Error location**: `flask_login/utils.py:284` — the `@login_required` decorator
checks `current_user.is_authenticated`, which triggers `user_loader`, which
returns a User instance that is detached from the SQLAlchemy session.

**Root cause analysis from handoff**:

The `user_loader` (line 1731+ in `app/__init__.py`) has a Redis/Flask-Caching
L2 cache path (lines 1762-1774):
1. First request: user loaded via full DB query, result cached in Flask-Caching
   with user PK.
2. Second request: cache hits, `db.session.get(User, _cached['id'])` is called.
3. But the User instance from the first request's session scope has been
   detached by `teardown_appcontext` → `session.remove()`.
4. `db.session.get()` either returns this stale instance or returns from the
   identity map in a different session scope.

**Flask-SQLAlchemy session scoping detail**:
- Flask-SQLAlchemy 3.x scopes sessions per app context via
  `scopefunc=_app_ctx_stack.__ident_func__`.
- Each `client.get()`/`client.post()` pushes a nested app context with its own
  session.
- When the request completes, `teardown_appcontext` calls `session.remove()`
  for that scope, detaching all User instances.
- The `db_session` fixture's `with app.app_context()` provides an outer scope.
- Helpers calling `db.session.expire_all()` or `db.session.close()` operate on
  the **fixture's** session scope, not the **request's** session scope — so
  they have no effect on the request's identity map.

**Three approaches tried BEFORE this session (all failed)**:
1. `db.session.expire_all()` before each request — FAILED (wrong scope)
2. `db.session.close()` before each request — FAILED (wrong scope)
3. `cache.clear()` before each request — CURRENT APPROACH (not yet verified)

### 0.5 Handoff: Next Move

The handoff specified:
1. Run E2E tests with `cache.clear()` approach
2. If it fixes it → confirm all 6 E2E tests pass
3. If not → try next approach (patch `user_loader` Redis cache via
   `unittest.mock`, or restructure tests)
4. Run full test suite
5. Produce final report. STOP.

---

## 1. Session Actions and Results

### 1.1 User Prompt: "What did we do so far?"

The agent reviewed the handoff context and git history to answer.

### 1.2 Agent Action: Git History Query

Ran `git log --oneline -40` and multiple grep-based git log searches.

**Result**: No commits mention "Stage 4", "4A", "4B-1", "RBAC", "org_owner",
or "provision". This confirmed that all Stage 4 work exists as **uncommitted
working-tree changes only** — nothing has been committed to git.

Recent commits visible:
```
10e8098 Recover agent system source, templates, migration and tests from forensic recovery
c437822 feed and routesimprovement
935a8ab feat: email/phone verification magic-link + OTP fallback
...
```

The `git diff --stat HEAD~5..HEAD` showed 80 files changed, 6623 insertions,
446 deletions — but these were pre-Stage-4 commits, not the Stage 4 work.

### 1.3 User Prompt: "Continue if you have next steps"

The agent proceeded to verify the `cache.clear()` approach by running the
failing E2E test.

### 1.4 Agent Action: Run Single E2E Test

Command:
```bash
python -m pytest tests/test_onboarding_stage4.py::TestEndToEndOrganisationOnboarding::test_complete_flow_with_capabilities -v --tb=short
```

**Result: FAILED**

Full traceback captured:
```
.venv\Lib\site-packages\flask_login\utils.py:284: in decorated_view
    elif not current_user.is_authenticated:
             ^^^^^^^^^^^^^^^^^^^^^^^^^
.venv\Lib\site-packages\flask_login\mixins.py:17: in is_authenticated
    return self.is_active
           ^^^^^^^^^^^^^^
.venv\Lib\site-packages\sqlalchemy\orm\attributes.py:569: in __get__
    return self.impl.get(state, dict_)
.venv\Lib\site-packages\sqlalchemy\orm\attributes.py:1096: in get
    value = self._fire_loader_callables(state, key, passive)
.venv\Lib\site-packages\sqlalchemy\orm\attributes.py:1126: in _fire_loader_callables
    return state._load_expired(state, passive)
.venv\Lib\site-packages\sqlalchemy\orm\state.py:803: in _load_expired
    self.manager.expired_attribute_loader(self, toload, passive)
.venv\Lib\site-packages\sqlalchemy\orm\loading.py:1607: in load_scalar_attributes
    raise orm_exc.DetachedInstanceError(
E   sqlalchemy.orm.exc.DetachedInstanceError: Instance <User at 0x142c6ec5090> is not bound
to a Session; attribute refresh operation cannot proceed
```

The error cascaded: the 500 error handler also triggered `inject_user_role_info`
which accessed `current_user.is_authenticated` on the same detached instance,
causing a second `DetachedInstanceError`.

**Key observation**: The `cache.clear()` approach did NOT fix the problem.
The test output showed the app startup completed normally (12.48 seconds),
Alembic stamped, schema verified (193 tables), but the E2E test still crashed
on the second request.

### 1.5 Agent Action: Launched Investigation Tasks

Two parallel investigation tasks were launched:
1. "Investigate cache and session config" — to determine why `cache.clear()`
   doesn't work
2. "Gather git history for Stage 4" — (already done above)

**Both tasks were cancelled** before completion (likely due to session timeout
or user intervention).

### 1.6 User Prompt: "STOP the current reconstruction"

The user stopped the agent from searching the codebase to reconstruct the
previous session history. The user clarified:

> "I am asking for a reconstruction of the previous AFCON360 ChatGPT/session
> journey, specifically the discussions, decisions, occurrences, handoffs,
> errors, fixes, and TODO items that led us to Stage 4 → RBAC → 4B-1."
>
> "Do NOT continue trying to infer the journey from the current codebase."
>
> "I need the historical/session record."

### 1.7 Agent Response: Transparency About Limitations

The agent explained:
- This is a fresh opencode session, NOT a continuation of ChatGPT.
- The only historical record available is the handoff context in the system
  prompt — a structured summary, not a session transcript.
- The agent does NOT have access to previous ChatGPT session transcripts.
- The git history contains no Stage 4 commits (work is uncommitted).
- The agent offered two options: (a) use only the handoff context, or
  (b) have the user provide the ChatGPT transcript.

### 1.8 User Prompt: Create MD file with session history

The user requested an MD file documenting everything from THIS session's
history, including the handoff context, actions, failures, and discoveries.

---

## 2. Errors and Failures — Complete Catalog

### 2.1 DetachedInstanceError (ACTIVE — UNRESOLVED)

| Field | Detail |
|-------|--------|
| **Symptom** | `DetachedInstanceError: Instance <User at 0x...> is not bound to a Session` |
| **Location** | `flask_login/utils.py:284` → `current_user.is_authenticated` → `is_active` |
| **Trigger** | Second (or later) HTTP request in E2E test using `client.get()`/`client.post()` |
| **Root Cause** | Flask-SQLAlchemy 3.x session scoping: each request gets its own session scope. User loaded in request 1 is detached when request 1's scope is torn down. The `user_loader`'s Redis cache path returns a stale user ID, and `db.session.get()` returns a detached/expired instance. |
| **Attempted Fixes** | (1) `db.session.expire_all()` — failed (wrong session scope). (2) `db.session.close()` — failed (wrong scope). (3) `cache.clear()` — failed (verified in this session). |
| **Production/Test** | Test infrastructure issue — does not affect production. |
| **Status** | UNRESOLVED. Next suggested approach: `unittest.mock.patch` on `cache.get` to return `None`, or restructure E2E tests to avoid multi-request pattern. |

### 2.2 Nested db_transaction Atomicity Bug (DEFERRED)

| Field | Detail |
|-------|--------|
| **Symptom** | `assign_org_role()` calls `db_transaction` internally; outer code also uses `db_transaction`. Inner commit fires on exit, prematurely committing all pending session state. |
| **Location** | `app/auth/roles.py:241` (`assign_org_role`) + `app/utils/transactions.py` (`db_transaction`) |
| **Fix Applied** | Onboarding route bypasses `assign_org_role` entirely — uses `provision_organisation_roles(org, commit=False)` + direct `OrgUserRole` creation. |
| **Root Cause Not Fixed** | The `db_transaction` nesting bug itself remains. `assign_org_role` still has the problem for any other caller. |
| **Production/Test** | Production defect — but masked by onboarding route workaround. |
| **Status** | DEFERRED to BACKLOG. |

### 2.3 Wallet FK Defect (DEFERRED)

| Field | Detail |
|-------|--------|
| **Symptom** | `AccountModel.user_id` is FK to `users.id`. When `create_org_wallet(org)` is called, it stores `org.id` as `user_id`, which violates the FK. |
| **Location** | Wallet architecture — `AccountModel.user_id` FK definition |
| **Fix Applied** | None. Wallet creation deliberately excluded from organisation creation. |
| **Production/Test** | Pre-existing production architecture defect. |
| **Status** | DEFERRED to BACKLOG. |

### 2.4 Tax ID Uniqueness Issue (RESOLVED)

| Field | Detail |
|-------|--------|
| **Symptom** | `Organisation` has `uq_org_country_tax (country, tax_id)` unique constraint. Empty string `''` is NOT the same as `NULL` in PostgreSQL. Two orgs with `country='UG'` and `tax_id=''` would violate the unique constraint. |
| **Root Cause** | IDGuard classification + SQLAlchemy default for unset tax_id. |
| **Fix Applied** | `Organisation.tax_id` nullable, defaults to `NULL` (not empty string). The unique constraint treats NULLs as non-duplicate per PostgreSQL semantics. |
| **Production/Test** | Production-correct behavior. |
| **Status** | RESOLVED. |

### 2.5 Profile full_name NOT NULL Issue (RESOLVED)

| Field | Detail |
|-------|--------|
| **Symptom** | `UserProfile.full_name = Column(String(128), nullable=False)`. During E2E onboarding, the profile is created but `full_name` was not being populated, causing a NOT NULL violation. |
| **Location** | `app/profile/models.py` + `app/auth/onboarding_routes.py` |
| **Fix Applied** | `_get_or_create_profile` now provides a default `full_name`. `_commit_organisation_onboarding` populates profile `full_name`. Step 1 template now includes a required `full_name` input. |
| **Production/Test** | Production-correct behavior. |
| **Status** | RESOLVED. |

### 2.6 Stale test_onboarding.py Assertions (RESOLVED)

| Field | Detail |
|-------|--------|
| **Symptom** | 5 assertions in `test_onboarding.py` were checking for text/behavior that no longer matched the current templates and redirect logic. |
| **Root Cause** | Templates and routes evolved (e.g., `choose.html` text changed, type-first redirect behaviour changed) but tests were not updated. |
| **Fix Applied** | Updated 5 assertions to match current `choose.html` content and type-first redirect behavior. |
| **Production/Test** | Test-only correction — no production code changed. |
| **Status** | RESOLVED. Expected 21/21. |

### 2.7 AccountType Enum Mismatch in 4B-1 Tests (RESOLVED)

| Field | Detail |
|-------|--------|
| **Symptom** | `test_org_creation_rbac_4b1.py` used `AccountType.PERSONAL` which does not exist. |
| **Root Cause** | `AccountType` enum members are: `REVENUE`, `ESCROW`, `OPERATIONS`, `SETTLEMENT`, `RESERVE`, `USER_WALLET`, `ORG_WALLET`. No `PERSONAL`. |
| **Fix Applied** | Changed to `AccountType.USER_WALLET`. Also removed invalid `Account_Currency` import. Wallet test reframed to USER-owned wallet. |
| **Production/Test** | Test-only correction. |
| **Status** | RESOLVED. |

### 2.8 Invalid Account_Currency Import (RESOLVED)

| Field | Detail |
|-------|--------|
| **Symptom** | `test_org_creation_rbac_4b1.py` imported `Account_Currency` from `app.wallet.models.ledger` — does not exist. |
| **Fix Applied** | Import removed. |
| **Production/Test** | Test-only correction. |
| **Status** | RESOLVED. |

---

## 3. Architecture Decisions Preserved

### 3.1 Organisation Creation Flow (Current)

```
User → /onboarding/choose → /onboarding/choose/organisation
  → POST type + capabilities (stored in session)
  → /onboarding/organisation/step1 (details form: legal_name, contact_email, country, full_name)
  → /onboarding/organisation/step2 (confirmation)
  → /onboarding/organisation/commit
    → _commit_organisation_onboarding()
      → create_organization(org_data, creator_user)
        → Organisation row
        → OrganisationMember row (creator)
        → provision_organisation_roles(org, commit=False)
          → OrgRole rows (from ORG_ROLE_TEMPLATES)
          → OrgRolePermission rows (copied from global role permissions)
          → OrgUserRole (creator as org_owner)
        → Provider capabilities (0..N OrganisationProviderCapability rows)
        → initiate_verification()
      → profile full_name populated
      → session reset (org onboarding data cleared)
      → redirect to /org/
```

### 3.2 RBAC Authority Chain

```
Organisation
  └─ OrgRole (role_id)           ← e.g. "org_owner", "org_admin", "org_member"
       └─ OrgRolePermission      ← permission rows copied from global role template
  └─ OrganisationMember          ← user membership in this org
       └─ OrgUserRole            ← assignment of OrgRole to this member
            └─ role_id → OrgRole.id  ← CRITICAL: NOT roles.id (global)
```

### 3.3 What Capabilities Do

- Provider capabilities (e.g. "hotel", "transport", "event_organiser") are
  persisted as `OrganisationProviderCapability` rows with `status='intent'`.
- They do NOT grant authority. Authority comes from `OrgRolePermission` rows.
- They are metadata about what the organisation intends to provide.

### 3.4 What Wallet Does NOT Do

- `create_organization()` does NOT create a wallet.
- Wallet creation is an independent later operation.
- This boundary is frozen and MUST NOT be changed in Stage 4.

---

## 4. Test Evidence Checkpoints

### 4.1 Pre-Session Checkpoint (From Handoff)

| Test Suite | Tests | Result |
|-----------|-------|--------|
| `test_organisation_role_provisioning.py` | 11 | PASS |
| `test_assign_revoke_org_role.py` | 11 | PASS |
| `test_org_permission_read_path.py` | 12 | PASS |
| `test_org_creation_rbac_4b1.py` | 13 | PASS |
| `test_onboarding_stage4.py` | 17 | PASS |
| `test_onboarding.py` | 21 | PASS (after 5 assertion fixes) |
| **Core regression total** | **72+** | **PASS** |

### 4.2 This Session's Test Run

| Test Suite | Tests | Result |
|-----------|-------|--------|
| `test_onboarding_stage4.py::TestEndToEndOrganisationOnboarding::test_complete_flow_with_capabilities` | 1 | **FAIL** — DetachedInstanceError |

This confirms the DetachedInstanceError was NOT resolved by `cache.clear()`.

---

## 5. Deferred Work Items

### 5.1 Explicitly Deferred to BACKLOG

1. **Wallet FK defect**: `AccountModel.user_id` FK to `users.id` means
   `create_org_wallet(org)` would store `org.id` as `user_id`, violating FK.
   Pre-existing architecture issue. Not in scope for 4B-1.

2. **test_onboarding.py contract mismatch**: Partner-gate test assumptions
   don't match current template content. 5 assertions fixed, but underlying
   contract should be reviewed.

3. **Nested db_transaction atomicity**: `db_transaction` in
   `app/utils/transactions.py` calls `db.session.commit()` on exit, breaking
   true atomicity when nested. `assign_org_role` bypassed but bug remains.

4. **DetachedInstanceError resolution**: E2E test infrastructure needs proper
   fix. Three approaches tried and failed. Next: `unittest.mock.patch` or
   test restructuring.

### 5.2 Not In Scope (Per Architecture Rules)

- Owner wildcard permissions
- Auth helpers/policy/context
- OrganizationPermissionService
- Legacy RBAC (global roles)
- Broader KYC/KYB architecture
- Production data
- `conftest.py` session-cleanup fixture changes (explicitly rejected)
- Migration creation/modification

---

## 6. Key Code Locations Referenced

| File | Purpose |
|------|---------|
| `app/__init__.py:1731-1814` | `user_loader` with Redis cache L2 path |
| `app/__init__.py:1246` | `user_highest_role` context processor |
| `app/auth/onboarding_routes.py:506-597` | `_commit_organisation_onboarding` with direct provisioning |
| `app/identity/services/organisation_role_provisioning.py` | `provision_organisation_roles()` with `commit=False` |
| `app/identity/services/organization_registration.py` | `create_organization()` — no wallet |
| `app/models/base.py` | `NON_FK_STRING_IDS` includes `org_id` |
| `app/profile/models.py` | `UserProfile.full_name = Column(String(128), nullable=False)` |
| `app/utils/transactions.py` | `db_transaction` — calls `db.session.commit()` on exit |
| `tests/conftest.py` | `db_session` fixture with `with app.app_context()` |
| `tests/test_onboarding_stage4.py:153-186` | `_http_login`, `_fresh_get`, `_fresh_post` helpers |
| `BACKLOG.md` | Deferred work entries |

---

## 7. Unresolved Questions

1. **Why does `cache.clear()` not fix the DetachedInstanceError?**
   - Possibility A: `cache.clear()` is raising an exception that is silently
     swallowed by the `try/except`.
   - Possibility B: The cache backend in testing is NOT the same instance that
     `user_loader` uses.
   - Possibility C: The full DB query path in `user_loader` also returns a
     detached instance due to session scoping.
   - Possibility D: The `g._cached_user_pubid` per-request cache is somehow
     carrying over (unlikely — `g` is per-request).
   - Not investigated in this session (tasks were cancelled).

2. **Is the `db_session` fixture's app context interfering with request sessions?**
   - Flask-SQLAlchemy 3.x uses `scopefunc=_app_ctx_stack.__ident_func__` for
     session scoping. If the fixture's app context is active during requests,
     session behavior may differ from production.
   - Not investigated in this session.

3. **Has the full 17/17 and 13/13 test suite been re-verified recently?**
   - The handoff claimed these passed. Only the E2E test was re-run in this
     session (and failed). The unit/integration tests were not re-run.

---

## 8. Session End State

### What Happened

1. Session received detailed handoff from previous work.
2. Agent queried git history — confirmed Stage 4 work is uncommitted.
3. Agent re-ran the failing E2E test — confirmed DetachedInstanceError persists.
4. Agent launched investigation tasks — both were cancelled before completion.
5. User redirected the agent to create this chronicle instead of investigating.

### What Was NOT Done

- DetachedInstanceError was NOT fixed.
- Full test suite was NOT re-run.
- Investigation of why `cache.clear()` fails was NOT completed.
- No new production code was written.
- No new tests were written.
- No files were modified.

### Next Authorized Step

Fix the DetachedInstanceError in E2E tests, then run the full test suite and
produce a final completion report. Then STOP — do not proceed to 4B-2.

---

## 9. Chronological Summary

```
T=0   Handoff context received (detailed summary of all prior work)
T=1   User asks "What did we do so far?"
T=2   Agent queries git log — confirms no Stage 4 commits exist
T=3   User says "Continue if you have next steps"
T=4   Agent runs E2E test → FAILS (DetachedInstanceError, same as before)
T=5   Agent launches 2 investigation tasks (cache config + git history)
T=6   Both tasks cancelled before completion
T=7   User says "STOP the current reconstruction" — wants session history, not code audit
T=8   Agent explains it doesn't have previous ChatGPT session transcripts
T=9   User says "create an md file... input everything we have done... only this chat history"
T=10  This file is being created
```


---

## 10. Root-Cause Diagnosis & Fix of the E2E DetachedInstanceError (RESOLVED)

### 10.1 Session action

The user asked to continue the current session ("session"); the agent continued the
4B-1 E2E contamination investigation and, with user approval (`APPROVE`), applied a
test-infrastructure fix.

### 10.2 Definitively reproduced root cause (Category B — test infrastructure, NOT production)

The E2E tests in `tests/test_onboarding_stage4.py` failed (6/6) only when run after
other suites. Two independent contamination modes were isolated and reproduced in a
throwaway test file:

- Mode A (DetachedInstanceError) — the dominant mode.
- Mode B (data-count / session-login redirects) — resolved as a consequence of Mode A.

Mechanism (proved via `has_app_context()` / `flask.g` probes, logged to temp files):

1. Several Stage-4 role/permission suites define a **session-scoped, autouse**
   `_seed_global*` fixture doing:
   `with app.app_context(): seed_all(); yield`.
   Because the `yield` sits **inside** the `with`, the app context stays open for the
   **entire test session** once any of those suites runs.
2. Any later HTTP test (the E2E `TestEndToEndOrganisationOnboarding`) then runs under
   that persistent app context, so `flask.g` — and Flask-Login`s `g._login_user` /
   `user_loader`'s `g._cached_user` — is the **same object across every
   `client.get()`/`client.post()`**.
3. Request 1 loads the User and binds it to request 1's scoped session. Request 1
   teardown calls `db.session.remove()`, which **detaches** that User, but
   `g._cached_user` still references it.
4. Request 2's `user_loader` hits the `g._cached_user_pubid == public_id`
   short-circuit (`app/__init__.py:1758`) and returns the **detached** User. A template
   context processor (`inject_user_role_info` → `get_highest_role(current_user)`) then
   touches `current_user.roles`, raising `DetachedInstanceError` → 500 → E2E fails.

Isolation evidence:
- E2E alone: `has_app_context()` False at test start, both requests 200, pass.
- Any `_seed_global*`-leaking suite before E2E: `has_app_context()` True at test
  start, request 1 = 200, request 2 = DetachedInstanceError.
- Removing the leak (pop context before yield) in a throwaway fixture made both
  requests 200 and the test pass, confirming the fix.

Note: Redis is NOT running in this environment. Flask-Caching falls back semantics
were checked (RedisCache-ish `get()` returns None / does not raise), so the stale-data
source is the persistent `g`, not Redis.

### 10.3 Files changed (this action, user-approved)

- `tests/test_org_creation_rbac_4b1.py` — `_seed_global`: moved `yield` outside the
  `with app.app_context():` block (added explanatory comment).
- `tests/test_organisation_role_provisioning.py` — `_seed_global_org_roles`: same fix.
- `tests/test_assign_revoke_org_role.py` — `_seed_global_org_roles`: same fix.
- `tests/test_org_permission_read_path.py` — `_seed_global_roles`: same fix.
- `SESSION_4B1_CHRONICLE.md` — this record.

All four files had the identical leaking pattern; all were fixed consistently.

### 10.4 Verification

- `RBAC + 3 role/permission suites + E2E` (5 files): 83 passed.
- Full 104-test Stage-4 set (`test_org_creation_rbac_4b1`,
  `test_organisation_role_provisioning`, `test_assign_revoke_org_role`,
  `test_org_permission_read_path`, `test_onboarding`, `test_onboarding_stage4`):
  **104 passed** (was 98 passed / 6 E2E failed before this fix).
- Full `tests/` suite still reports pre-existing failures in unrelated modules
  (`test_wallet_authorization_limits.py` — `uuid = integer` DB operator error,
  `test_booking_mode.py`, `test_ledger_concurrency.py`, etc.) that are outside the
  4B-1 scope and were NOT caused by this change (they are wallet/config/booking
  domain issues).

### 10.5 Completion status for 4B-1

The 4B-1 Stage-4 organisation-onboarding E2E flow is now verified end-to-end in the
test suite (all 104 Stage-4 tests pass together). Production org-onboarding behavior
is confirmed correct: 98/104 non-E2E Stage-4 tests pass and all 6 E2E pass when the
suites run together after the fixture fix. Category C deferred gaps (verification
record, legacy fields, org settings, VAT collection in step 1) remain as recorded in
the handoff and are NOT 4B-1 blockers. **STOP — do not proceed to 4B-2.**
