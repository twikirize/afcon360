# STAGE 4B — Organisation Classification & Eligibility Authority Reconciliation

**Status:** READ-ONLY FORENSICS COMPLETE — DECISION GATE OPEN
**Agent:** single implementation/architecture agent
**Date:** 2026-09-05
**Gate:** must PASS before Stage 4B-5 (Transport)

---

## 1. Executive summary

A forensic investigation into the pre-existing `can_org_host()` contradiction is
complete. The claim in the task brief ("`can_org_host` returns False for all
valid `OrganizationType` values because it compares against the legacy strings
`service_provider`/`merchant`") is **confirmed**, and its root cause is now fully
explained by the evidence.

**The contradiction is a single orphaned legacy string-comparison** in one
accommodation service method, not a schema split and not a domain-vocabulary
conflict. Findings:

- `Organisation.business_category` is **canonically** the **identity
  classification** (`OrganizationType`) — a single column (`org_business_category`
  PostgreSQL native enum) whose labels are the enum **member names** (uppercase:
  `HOTEL`, `RESTAURANT`, `TOUR_OPERATOR`, …), verified live against the test DB.
- `OrganizationType` **is** the canonical classification vocabulary. All real
  writers (`organization_registration.py`, `onboarding_routes.py`, the
  `OrganizationRegistrationForm`) persist an `OrganizationType` member.
- `service_provider`, `merchant`, `marketplace_seller`, `non_profit` do **not**
  exist in the model enum, in any migration, or in the live test DB enum. They
  survive only in **two legacy templates** — `templates/org/settings_old.html`
  (defunct business_category form) and the admin moderator `users.html`
  filter — and in one string default `'merchant'` for the **free-text**
  `Organisation.org_type` display column in `organization_registration.py:170`.
- `can_org_host`'s `org.business_category not in ['service_provider','merchant']`
  compares an enum member against legacy strings and therefore **can never be
  True** for any persisted value. This is a genuine defect.
- **No database/model drift exists in the test DB** (enum labels and all
  persisted values are current-model members). The "database drift" in the brief
  describes other/legacy databases outside this repository graph.
- The `Organisation.org_type` free-text column and a stale comment in
  `onboarding_routes.py:527-528` are secondary, cosmetic inconsistencies.

Recommended direction (Subject to Decision Gate): **Option C** — treat
`OrganizationType` as a *signal*, not the eligibility authority. Opportunely
repair `can_org_host` by aligning it with the model enum; do **not** make it the
basis for domain eligibility. Retain PP as the capability source and introduce a
small, domain-owned organisation eligibility predicate under the accommodation
module only when the write-gate is wired for organisations in a later step.
No schema migration is required to make `can_org_host` correct, because the enum
and all persisted data are already canonical.

---

## 2. Current architecture

```
Organisation (identity/classification)
   ├── org_id (public, String)
   ├── org_type (String(128) FREE-TEXT display column, legacy)
   ├── business_category (PostgreSQL native enum org_business_category = OrganizationType member NAMES)
   ├── verification_status / is_operational (KYB-style gates)
   └── capabilities helper: Organisation.get_capabilities() -> OrganizationCapability
                                   (ORGANIZATION_CAPABILITIES map, legacy provider ability)

ProviderParticipation (universal capability lifecycle; PP is the capability SOURCE)
   └── provider_participations via provider_participation_service (Stage 4B-3)

Accommodation identity service (accommodation-owned write gate)
   └── can_host(individual)  [Stage 4B-2: eligibility + PP ACTIVATED]
   └── can_org_host(organisation)  [DEFECTIVE legacy string comparison]
```

---

## 3. Evidence inventory

| Id | Evidence | Location | Role |
|----|----------|----------|------|
| E1 | `business_category` column is `Enum(OrganizationType, name="org_business_category")` | `app/identity/models/organisation.py:124-127` | Model classification |
| E2 | `OrganizationType` enum (39 members, incl. HOTEL/TOUR_OPERATOR/…) | `app/identity/models/organization_types.py:13-71` | Canonical vocabulary |
| E3 | writer: `business_category=OrganizationType(data['org_type'])` | `app/identity/services/organization_registration.py:171` | Writer (enum member) |
| E4 | writer default: `org_type=data.get('org_type','merchant')` | `organization_registration.py:170` | Legacy string into free-text `org_type` |
| E5 | writer: `business_category=org_type_member`; comment claims lowercase `.value` | `app/auth/onboarding_routes.py:527-551` | Writer (enum member, correct store; stale comment) |
| E6 | `_validate_organisation_type` returns `OrganizationType(value)` | `onboarding_routes.py:362-374` | Canonical mapper |
| E7 | form choices from `for org_type in OrganizationType` | `app/forms/organization_forms.py:92-94` | UI source |
| E8 | display: `business_category.value.replace('_',' ').title()` in several templates | `templates/org/dashboard.html:230`, `members.html:229`, `settings.html:303`, `selector.html:275` | Display reader (assumes `.value`) |
| E9 | `business_category` compared against legacy strings | `app/accommodation/services/identity_service.py:75` — `not in ['service_provider','merchant']` | **THE DEFECT** |
| E10 | `can_org_host` callers | `app/auth/context.py:519-522` | Read path |
| E11 | PP doc mentions `can_host / can_org_host` eligibility authority | `provider_participation_service.py:381` | Cross-ref |
| E12 | `Organisation.get_capabilities()` and legacy `OrganizationCapability` includes `can_manage_accommodation` | `organisation.py:235-259`, `organization_types.py:366-509` | Org type → provider ability (legacy capability map) |
| E13 | migration graph builds entire schema via `create_all()`; NO business_category migration exists | `migrations/versions/8a0deccce6f6_initial_full_schema_baseline.py`; grep of all versions | Migration history |
| E14 | org capability model doc: capability independent of org type | `organisation_provider_capability.py:17-19` | Architectural contract |
| E15 | test DB live: `org_business_category` = 39 labels (upper-case member names), 668 orgs, distinct values {HOTEL, TOUR_OPERATOR, SPORTS_TEAM, FOOTBALL_TEAM, CORPORATE} | direct SQL query | DB forensics |
| E16 | tests treat business_category as canonical (`.value`) | `tests/test_onboarding_stage4.py` | Test evidence |
| E17 | legacy vocabulary only in `settings_old.html` and moderator `users.html` filter | templates | Template-only |
| E18 | `OrganizationType.MERCHANT` referenced but not defined | `organisation.py:237-238` | **Latent bug** (AttributeError on NULL business_category) |

---

## 4. Organisation classification model

Two classification fields on `Organisation`:

1. **`business_category`** — authoritative classification: native PostgreSQL enum
   `org_business_category`, bound to `OrganizationType`. **This is the canonical
   classification** (E1, E2, E3, E5, E6, E7, E8, E15, E16).
2. **`org_type`** — a redundant/legacy free-text `String(128)` display column,
   not an enum, not unique, written with legacy defaults (`'merchant'`), read in
   a few templates. It is **not** a distinct vocabulary and holds no authority.

`OrganizationType` itself models *kind of organisation* (hotel, restaurant,
transport company, football team…), with an associated *provider/consumer
capability map* (`DUAL_ORGANIZATION_CAPABILITIES`) and a *legacy* capability map
(`ORGANIZATION_CAPABILITIES`) used by `Organisation.get_capabilities()`.

There is **no separate business-category vocabulary** beyond this — the concept
that a `business_category` is a distinct domain axis is not supported by the
model.

---

## 5. Database enum evidence

Live test DB (`postgresql://…@localhost:5432/afcon360_test`, **read-only**):

- `org_business_category` PostgreSQL enum exists with **39 labels**, identical to
  the 39 `OrganizationType` members, stored as the **member names** (upper-case):
  `HOTEL, RESTAURANT, TOUR_OPERATOR, TRAVEL_AGENCY, TOURISM_BOARD,
  EVENT_MANAGEMENT, CONFERENCE_CENTER, VENUE_OPERATOR, EXHIBITION_ORG,
  SPORTS_TEAM, FOOTBALL_TEAM, SPORTS_FEDERATION, FITNESS_CENTER,
  RECREATION_FACILITY, TRANSPORT_COMPANY, AIRLINE, BUS_OPERATOR, TAXI_SERVICE,
  CAR_RENTAL, ACCOMMODATION_PROVIDER, HOSTEL, VACATION_RENTAL, CAMPING_SITE,
  CORPORATE, CONSULTING_FIRM, MARKETING_AGENCY, IT_SERVICES, GOVERNMENT, NGO,
  EDUCATIONAL_INSTITUTION, HEALTHCARE_PROVIDER, BANK, INSURANCE_COMPANY,
  INVESTMENT_FIRM, FINTECH, MEDIA_COMPANY, BROADCASTING, ENTERTAINMENT,
  PUBLISHING`.
- `organisations` has **668** rows; `business_category` distinct non-null values:
  `HOTEL, TOUR_OPERATOR, SPORTS_TEAM, FOOTBALL_TEAM, CORPORATE` — **all valid
  current-model members**.
- No label `merchant`/`service_provider`/`marketplace_seller`/`non_profit` exists
  in the enum or in any persisted value in this database.

**No schema drift in the test DB.** The legacy vocabulary described in the task
brief is not represented anywhere in this database; it is a template-only and/or
external-DB artifact.

---

## 6. Migration history

Alembic versions under `migrations/versions` contain **zero** references to
`business_category`, `org_business_category`, `org_type`, or `OrganizationType`.
Schema is produced by the single root baseline
`8a0deccce6f6_initial_full_schema_baseline.py`, which calls
`db.metadata.create_all()` from the current models. Retirement-checked
`schema/constraint` migrations (e.g. the org capability sync) do not touch the
enum.

**Conclusion:** There is no past or pending migration that alters the meaning of
`business_category`; the enum was effectively always the current `OrganizationType`
set. Any "correction" of the string-comparison defect is a **code** fix, not a
**migration** task.

---

## 7. Writer/reader graph

```
Classification writers (produce OrganizationType member into business_category):
  organization_registration.create_organization()   (E3)
  auth.onboarding_routes organisation boot         (E5)
  [no update route writes business_category today]

Classification readers:
  can_org_host()  business_category not in [legacy strings]   (E9)  ← DEFECT, returns False always
  Organisation.get_capabilities() -> OrganizationCapability    (E12, legacy provider map)
  identity/routes.py: business_category via getattr(...,'value') (member->value for display/role logic)
  organization_permissions.get_available_roles(business_category)  (expects enum member)
  templates: business_category.value.title()  (E8)
  tests: business_category.value             (E16)

Multiple-vocabulary writers (free-text org_type column, legacy):
  organization_registration.py:170  org_type = 'merchant' default  (E4)  — legacy string
  admin moderator users.html filter (serverside org detection unrelated to value)

Capability source (independent of classification):
  ProviderParticipation  provider_participations  (E14)  ← PP is the capability authority
```

**Every real capability-lifecycle read/write goes through PP.** The
`business_category` string-comparison is the **only** code site coupling
accommodation capability writes to the legacy vocabulary.

---

## 8. Eligibility authority graph

```
Organisation.business_category  (classification signal; OrganizationType member)
        ↓ (signal, NOT authority)
domain eligibility predicate  (accommodation-owned)
        ↓
PP capability  (ACCOMMODATION .ACTIVATED)   ← source of the capability itself
        ↓
accommodation write gate  (host_create_listing)
        ↓
accommodation context  (auth/context.py ACCOMMODATION_HOST)
        ↓
domain resource write  (Property/listing)

Authority ownership:
  classification  → Identity (Organisation / OrganizationType)
  capability      → ProviderParticipation (universal)
  domain eligibility → Accommodation module (currently embodied, if defectively, in can_org_host; org variant not yet wired to a hard write gate — see 4B-2 decision: org gate deferred)
```

Per the approved Stage 4A/4B rule: **eligibility is computed & evidence-based;
capability is declared & represented by PP. Capability activation is
eligibility-gated.** PP must not move KYC/KYB/eligibility logic into itself; the
domain owns eligibility.

---

## 9. Contradictions

1. **[Confirmed defect]** `can_org_host` compares an enum member against legacy
   strings `['service_provider','merchant']` (E9). For any canonical
   `business_category` value, `not in [..]` is True → returns False. Contradicts
   the intent that eligible hotel/tour-operator/vacation-rental orgs can host.
   **Category: E (Production defect)** (logic) / see 11 for root cause.

2. **[Cosmetic]** `onboarding_routes.py:527-528` comment claims PostgreSQL enum
   uses lowercase `.value` (`"hostel" not "HOSTEL"`), but the live enum stores
   **member names** (uppercase). The store is correct; only the comment is stale.
   **Category: C/D (comment/reality drift, non-functional).**

3. **[Legacy template vocabulary]** `settings_old.html` (defunct `business_category`
   form) and moderator `users.html` filter offer `merchant/service_provider/
   marketplace_seller/non_profit` values that match **no** model enum member.
   **Category: B (legacy) / C (template artifact).**

4. **[Latent bug]** `Organisation.get_capabilities()` falls back to
   `OrganizationType.MERCHANT`, which is **not defined** in `OrganizationType`
   (E2) → would raise `AttributeError` when `business_category` is NULL.
   Unreachable for non-null orgs because `get_capabilities` guards `if not
   self.business_category` first, but the branch is broken if ever hit.
   **Category: B (legacy latent defect).**

5. **[Redundancy]** `Organisation.org_type` free-text column defaulted to
   `'merchant'` (E4) duplicates classification with a non-enum string.
   **Category: B (legacy redundancy), non-authoritative.**

6. **[Not a contradiction]** There is **no second canonical classification
   vocabularity** in model/db; `business_category` and `OrganizationType` are the
   same concept. The supposed "separate business-category vocabulary" does not
   exist in code.

---

## 10. Root cause

`can_org_host` was written against an **older, since-removed** business-category
vocabulary (`service_provider`/`merchant`/`marketplace_seller`/`non_profit`) that
survives today only as template options and a free-text default. The model enum
was later (re)introduced as the `OrganizationType`-backed `org_business_category`,
with the lowercase `.value` labels replaced by uppercase member-name labels, but
`can_org_host`'s comparison string was **not** migrated to match. The result is a
permanently-False predicate — a stale comparison, not an intentional design.

Secondary: the navigation of `business_category` as "category" (member name) vs
`OrganizationType` as "type" (value) caused the misleading `settings_old` UI and
stale comments. But the **architectural question** in the brief (`OrganizationType`
vs separate `business_category` vocabulary) is answered by the evidence: they are
**the same concept**; the enum value held in `business_category` is exactly the
`OrganizationType` member.

---

## 11. Classification of findings

| Finding | Category |
|---|---|
| `can_org_host` legacy string comparison → always False | **E. Production defect** |
| Stale comment (lowercase `.value`) in onboarding | **C. Test/comment-reality drift (non-functional)** |
| Legacy template vocabulary (settings_old, moderator filter) | **B. Legacy / C. Template artifact** |
| `OrganizationType.MERCHANT` fallback (undefined) | **B. Legacy latent defect** |
| `org_type` free-text legacy column / `'merchant'` default | **B. Legacy redundancy** |
| Absence of any distinct business-category vocabulary | (not a finding; confirms Option A) |

---

## 12. Options considered

### Option A — `OrganizationType` is the canonical classification vocabulary
Keep `Organisation.business_category` = `OrganizationType`. Fix `can_org_host` to
compare against `OrganizationType` members (or a derived set) rather than legacy
strings. Do not introduce a second vocabulary.

### Option B — Introduce a separate business-category vocabulary
Create a new enum/column (`business_category` distinct from `OrganizationType`)
as the classification axis shared across domains.

### Option C — Organisation classification is evidence-derived; `business_category`
is a **signal**, not the eligibility authority
Keep `OrganizationType` as classification. Resolve the `can_org_host` defect, but
treat the resolved check (verified + operational + an eligible classification)
as the (already-existing) domain "eligibility" input, while **PP remains the
capability source** for the write gate. Org eligibility is a predicate owned by
the accommodation module, derived from organisation evidence/classification —
matching the frozen Stage 4A architecture (eligibility computed & evidence-based;
PP represents capability).

### Option D — Other
None backed by repository evidence.

---

## 13. Advantages / disadvantages

| Option | Advantages | Disadvantages |
|---|---|---|
| **A** | Minimal, exact fix; matches model & DB today; no migration; preserves Identity as the single classification owner. | Leaves eligibility logic embedded in `can_org_host`; does not by itself establish a reusable per-domain eligibility predicate. |
| **B** | A "purer" separation of type vs category in theory. | No evidence any such vocabulary exists or was intended; requires a **new enum + migration + data transform**; violates §14 (no new enum without approval); higher risk; invented architecture. |
| **C** | Matches the frozen universal architecture precisely (eligibility computed/evidence-based, capability = PP activated); keeps PP domain-neutral; enables a clean per-domain eligibility predicate later; fixes `can_org_host` opportunistically without scope creep. | Requires an explicit, accommodation-owned eligibility predicate and a deliberate step to wire the org write-gate (deferred per 4B-2 decision); slightly more conceptual surface than A. |

---

## 14. Recommended architecture

**Recommend Option C**, with the minimal defect repair folded in where in-scope:

- Authority: **Identity** owns classification (`OrganizationType` →
  `business_category`). **ProviderParticipation** owns capability. **Accommodation**
  (domain) owns accommodation eligibility.
- The eligibility predicate (verified + operational + eligible classification)
  remains **computed/evidence-based**, exactly as Stage 4A specifies. It must
  **not** be moved into PP.
- The immediate, correct-value fix to `can_org_host` is to stop comparing
  `business_category` to legacy strings and instead validate it against
  `OrganizationType` members that may host accommodation, derived from
  repo-provided capability data (`get_organization_capabilities(...).
  can_manage_accommodation` or an explicit eligible set). This is a **code fix
  only** — no enum change, no migration, no data transform.
- The org write-gate wiring (route-level: org eligible **AND** PP ACCOMMODATION
  ACTIVATED) remains a **deferred, separately-approved step** (per 4B-2 decision),
  *not* part of this reconciliation.

---

## 15. Required code changes (authorization-dependent — NOT yet performed)

If the Decision Gate approves Option C, the candidate minimal change set:

- `app/accommodation/services/identity_service.py` — repair `can_org_host`'s
  classification check to use `OrganizationType`-aware eligibility instead of the
  legacy string list. Keep `can_org_host()`'s signature and remaining gates
  (verified/operational) intact. Do **not** touch `can_host`, `org_type`, or PP.
- Optionally correct the stale comment at `app/auth/onboarding_routes.py:527-528`.
- Optionally narrow the `OrganizationType.MERCHANT` fallback in
  `organisation.py` to a defined member (defensive) — only if explicitly approved.

**No changes** to PP, KYC/KYB, wallet/payment/escrow, transport, events,
`auth/context.py`, capability vocabulary, OPC retirement, or the migration graph.

---

## 16. Required migration changes

**None.** The enum and all persisted data are already canonical (E15). No
migration is required or proposed. The fix is code-only.

---

## 17. Data migration implications

**None.** No persisted value needs transformation. The legacy strings do not
exist in the test DB and are not introduced by any canonical writer.

---

## 18. Compatibility implications

- Fixing `can_org_host` to validate against `OrganizationType` members changes
  `can_org_host` to return `True` for eligible verified/operational orgs
  (previously `False`). This is the intended correction.
- Callers (`auth/context.py` ACCOMMODATION_HOST descriptor, PP doc reference) will
  begin surfacing the correct org accommodation-host context. This is
  consistent with Stage 4B-2 intent (org variant was explicitly deferred from the
  hard write gate, not declined).
- No public API contract of PP changes. `is_capability_operational` unchanged.
- Templates that render `business_category.value` remain correct for non-null
  values.

---

## 19. Security / authorization implications

- The change only relaxes a check that was *incorrectly denying* (False) — it does
  **not** weaken any verification/operational gate: `verification_status`,
  `is_operational`, `is_active` are all still enforced before classification.
- Organisations remain subject to KYC/KYB-style verification before hosting;
  PP ACCOMMODATION must still be ACTIVATED for any write (when the org gate is
  wired) per Stage 4B-2.
- No privilege is granted by capability activation; PP grants no roles (§14).
- No internal IDs exposed; public IDs unchanged.

---

## 20. Test implications

New/updated tests (when authorized):
- `can_org_host` returns True for verified+operational orgs whose
  `business_category` is an accommodation-eligible `OrganizationType` member
  (e.g. `HOTEL`, `TOUR_OPERATOR`); False for ineligible members and for
  unverified/non-operational orgs; never raises on NULL `business_category`.
- Assert no value path uses the legacy strings.
- Keep existing capability/PP/onboarding tests green (they already treat
  `business_category` as canonical enum, `.value`).
- No migration test change.

---

## 21. Rollback strategy

- Code-only change; revert `identity_service.py` (and any optional comment/defensive
  edits) restores prior behaviour. No data/migration rollback needed.
- If the optional org write-gate is later wired, it is an independent,
  separately-reversible step behind its own approval.

---

## 22. Future-domain compatibility

The recommended Option C keeps `ProviderParticipation` universal and
domain-neutral:

```
Organisation ─► PP ACCOMMODATION ─► accommodation eligibility (accommodation-owned)
Organisation ─► PP TRANSPORT      ─► transport eligibility      (transport-owned)
Organisation ─► PP TOURISM/…      ─► per-domain eligibility
```

Classification (`OrganizationType`) remains a single identity-owned signal that
each domain's eligibility predicate may consume. No speculative eligibility
systems are introduced for domains that have none.

---

## 23. Non-goals (explicit)

- Do **not** introduce a new enum / migration for a "separate business-category
  vocabulary".
- Do **not** move KYC/KYB/domain eligibility into PP.
- Do **not** couple PP to Accommodation.
- Do **not** modify `auth/context.py`, `can_host`, `org_type`, wallet/payment/
  escrow, transport, events, OPC retirement, or the migration graph.
- Do **not** wire the org route-level write gate in this reconciliation (deferred,
  separately approved).
- Do **not** perform opportunistic cleanup beyond the approved, minimal set.

---

## 24. Human approval gate

`DECISION REQUIRED` — see the accompanying directive. Do not implement until the
Decision Gate is satisfied.

**Recommendation:** Option C (with option A's minimal `can_org_host` repair folded
in as in-scope code fix).

---

## 25. DECISION — Option C APPROVED (2026-09-05) + Implementation Status

### Decision

Human approval granted **Option C**, including the minimal Option-A-style defect
correction of `can_org_host()`:

- Classification is Identity-owned: `Organisation.business_category` /
  `OrganizationType` is the single canonical organisation-classification signal.
- Domain eligibility is domain-owned: accommodation eligibility is derived from
  the repository-owned organisation capability mapping
  (`Organisation.get_capabilities().can_manage_accommodation`), NOT from a legacy
  string vocabulary.
- `ProviderParticipation` remains the universal provider-participation /
  capability authority. No PP coupling was introduced.
- Enforcement of the org accommodation write-gate (G-1) remains a **separately
  approved** later checkpoint (Stage 4B-6) — NOT wired in this stage.

Authorized as **code-only**: no new enum, no migration, no data transformation,
no new vocabulary, no `OrganizationType` member changes, no `org_type` change.

### Implementation (code-only) — complete

Files changed (this node only):

- `app/accommodation/services/identity_service.py` — repaired `can_org_host()`:
  replaced the defective legacy-string comparison
  (`business_category not in ['service_provider','merchant']` → always False)
  with (a) an explicit NULL-classification guard (`business_category` absent →
  `False, "Organisation type not set"`), then (b) the canonical classification
  check via `org.can_manage_accommodation()` → `get_capabilities()
                  .can_manage_accommodation` over `ORGANIZATION_CAPABILITIES`.
  All prior gates preserved (existence/deleted, active, `verification_status ==
  "verified"`, `is_operational`).
- `app/auth/onboarding_routes.py` — corrected the stale `:527-528` comment that
  claimed lowercase `.value` persistence; `business_category` stores the enum
  MEMBER NAME (uppercase), matching the live enum labels.

Files verified unchanged (post-implementation search): PP model/service,
`auth/context.py`, `can_host` (individual), `organization_permissions.py`,
capability lifecycle/vocabulary, KYC/KYB, wallet/payment/escrow, transport,
events, OPC, migrations, `OrganizationType` members, `org_type` column.

### Tests

New focused file `tests/test_can_org_host.py` (45 tests, all passing):

- eligible verified+operational organisation type → `(True, "OK")` for every
  member the mapping marks accommodation-capable: HOTEL, TOUR_OPERATOR,
  TRAVEL_AGENCY, EVENT_MANAGEMENT, SPORTS_TEAM, CORPORATE (6);
- ineligible verified+operational type → `(False, "...not eligible...")` for ALL
  other OrganizationType members (~33);
- verification failure, operational failure, inactive, deleted, and NULL
  `business_category` → controlled `False` (no AttributeError);
- legacy vocabulary (`merchant`/`service_provider`/`marketplace_seller`/
  `non_profit`) is not a canonical `OrganizationType` value.

Regression (153 tests, all passing):

- `tests/test_stage4b2_capability_enforcement.py`
- `tests/test_stage4b3_organisation_capabilities.py`
- `tests/test_capability_operations.py`
- `tests/test_provider_participation.py`
- `tests/test_onboarding_stage4.py`

### DB proof (no migration)

- No migration created or applied (`git status` shows no `migrations/` change; no
  `flask db` commands run).
- Test DB `afcon360_test` (the DB pytest uses): `org_business_category` enum has
  exactly 39 labels = model `OrganizationType` members; stored org rows only hold
  canonical values {HOTEL, TOUR_OPERATOR, SPORTS_TEAM, CORPORATE, FOOTBALL_TEAM};
  zero legacy vocabulary.
- **Pre-existing finding (flagged, NOT changed):** dev DB `afcon360_prod`
  (default `APP_ENV=local` target) has a stale `org_business_category` enum with
  only the 4 legacy lowercase labels (`merchant`, `service_provider`,
  `marketplace_seller`, `non_profit`) — schema drift that predates this work.
  Its `organisations` table is currently **empty** (0 rows), so no data is at
  risk. Reconciling it requires an approved migration (enum expand-contract) —
  reserved for the user (migration authority). Recorded in BACKLOG.

### Legacy items deferred (unchanged, do not silently fix)

- `Organisation.get_capabilities()` NULL fallback references undefined
  `OrganizationType.MERCHANT` (`organisation.py:237-238`) — latent `AttributeError`
  only for unclassified orgs; NOT on the `can_org_host()` path (NULL guard
  precedes it). Deferred as legacy debt; a defensive default (no capabilities for
  unclassified orgs) can be revisited in a dedicated node.
- `organization_registration.py:170` legacy free-text default `org_type='merchant'`
  (`OrganizationType(value)` would reject) — template/registration-only artifact;
  not eligibility code.
- Legacy vocabulary in templates `templates/org/settings_old.html` (defunct form)
  and `templates/admin/moderator/users.html` (admin filter) — template-only,
  no eligibility effect.

### Security / invariants preserved

- Dual-ID: no internal IDs exposed/added; `org_id` remains the org public
  identifier. No auth/permission weakening. CSRF/capability gates unchanged.
- `can_org_host` caller (`app/auth/context.py:519-522`) behaviour now returns
  True for genuinely eligible verified+operational orgs (was: always False).

### Next gate

Stage 4B-5 (transport split + G-2/F-2) — must NOT begin without explicit
authorization. Stage 4B-6 (G-1 org write-gate) remains the separately-approved
enforcement step for org accommodation listing creation.