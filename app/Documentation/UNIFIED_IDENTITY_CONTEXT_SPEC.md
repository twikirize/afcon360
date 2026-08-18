# Unified Identity and Operating Context Specification

**Status:** Assessment and implementation contract  
**Date:** 2026-08-14  
**Applies to:** authentication, identity, organisation, events, transport, accommodation, dashboards, and audit

## 1. Purpose

AFCON360 has one authenticated person identity and several independent sources of
eligibility. This specification defines how the application will let one logged-in
user select an eligible operating workspace without changing the authenticated user,
permanent assignments, booking ownership, or domain authority.

The governing model is:

```text
one authenticated User
    + persistent database assignments and eligibility
    + one selected operating context in the current session
```

Context selection is a UI and request-routing choice. It is not authentication
switching, role assignment, impersonation, or a permission snapshot.

## 2. Current architecture assessment

### 2.1 Authentication and session state

- Flask-Login is configured by the application factory in `app/__init__.py` and
  loads users by `public_id`. The authenticated principal is therefore the `User`
  represented by `current_user`; the internal numeric primary key remains a
  database-only value.
- Login and logout are implemented in `app/auth/routes.py`. Login initializes
  legacy navigation/session values including `current_context` and
  `current_org_id`; logout explicitly removes those values along with other
  session state.
- Flask-Session/Redis is configured by the application factory when available.
  The session is shared by browser tabs according to the configured Flask-Session
  backend, so a context selection is intentionally last-write-wins across tabs.
- `active_global_role` is a separate legacy persona selector handled by
  `app/auth/helpers.py`. It must not be treated as a replacement for the selected
  organisation, event, driver, host, or personal context.
- The current post-login helper, `_dashboard_for_user`, first applies owner and
  highest-role routing and then checks the legacy organisation context. This makes
  dashboard selection dependent on role hierarchy rather than a normalized active
  context.

### 2.2 Global authorization

`app/identity/models/roles_permission.py` provides the existing global authorization
records:

- `Role` stores named role definitions and their scope/level.
- `UserRole` assigns a global role to a user.
- `Permission` stores dot-namespaced capabilities.
- `RolePermission` links global roles to permissions.

`app/auth/helpers.py` provides global role and permission helpers, including the
owner bypass and database-backed permission checks. `app/auth/policy.py` exposes
`can(user, permission, org_id=...)`, which currently selects either global or
organisation checks. It derives an organisation from the legacy session when no
organisation argument is supplied; it does not yet resolve event, driver, host,
or active-context authority.

### 2.3 Organisation authorization

- `Organisation` in `app/identity/models/organisation.py` inherits `BaseModel`,
  has the externally usable unique `org_id` string, and separately has an internal
  primary key. Organisation lifecycle, `is_active`, `is_operational`, verification,
  and soft-delete state are all relevant to eligibility.
- `OrganisationMember` links a user and organisation through internal foreign keys,
  has `is_active`, and owns one-to-many `OrgUserRole` assignments and direct
  permission overrides. Its effective permissions are derived from live role and
  direct-permission records.
- Organisation dashboards and helpers currently accept/select the public-looking
  `org_id`, but legacy session values also carry display data such as
  `current_org_name`. The active organisation is consequently represented in more
  than one place.
- The existing organisation membership is the source of truth. Selecting an
  organisation must never create or mutate a membership or `OrgUserRole`.

### 2.4 Event authorization

- `Event` in `app/events/models.py` has a public `public_id`, unique `slug`, event
  status, organiser ownership, organisation ownership, suspension/deactivation
  fields, and BaseModel soft deletion.
- `EventRole` links an event, user, optional organisation, role name, permissions,
  and assigning user. It has a uniqueness constraint over `(event_id, user_id,
  role)` and an `is_active` lifecycle flag.
- `app/events/permissions.py` combines platform roles, organisation roles,
  organiser ownership, event roles, and event lifecycle state. It intentionally
  keeps creator, owner, organiser, organisation, and staff concepts distinct.
- Event routes perform their own domain checks. They must continue to do so while
  the context resolver supplies a normalized event descriptor and fresh eligibility
  information; context selection must not replace event ownership checks.

### 2.5 Transport eligibility

- `DriverProfile` in `app/transport/models.py` is associated with a user through an
  internal foreign key and has a unique `driver_code`, verification tier,
  compliance status, soft-delete state, availability, and operational flags.
- `app/user/routes.py` currently finds a driver by internal `user_id` and accepts
  only platform-verified or event-certified tiers for dashboard presentation.
  Transport API routes and decorators add further module and operational checks.
- The inspected driver model does not expose a canonical `public_id` field like
  `User`, `Event`, and `Property`. `driver_code` may be a candidate external
  identifier, but its contract must be confirmed before it is used at a context
  boundary. No internal driver primary key may be exposed as a workaround.

### 2.6 Accommodation eligibility

- `AccommodationIdentityService` is the accommodation module's identity boundary.
  It checks that individual hosts are active and eligible, including account,
  verification, and profile requirements. It separately checks organisation host
  eligibility, organisation lifecycle, verification, operational status, and
  business category.
- `HostProfile` and `HostOrganisationProfile` track host onboarding and active or
  suspended state. These records are eligibility inputs, not replacement identity
  records.
- `Property` has a public `public_id`, owner-user and owner-organisation foreign
  keys, status, verification, `is_active`, and soft-delete state. Property-level
  selectors can therefore use the existing public identifier when a later adapter
  needs one.
- Booking creator, booking owner, guest, property owner, host, and service provider
  remain accommodation domain concepts. An active context must not rewrite any of
  those relationships.

### 2.7 Dashboard, templates, and duplicated presentation logic

- `app/user/routes.py` assembles the universal dashboard, wallet data, modules,
  driver data, host eligibility, registrations, role labels, and organisation
  data in separate helpers.
- `app/__init__.py` adds several context processors. They expose profile state,
  highest role, wallet information, legacy organisation state, and module links
  independently. Some processors perform database work before rendering.
- `templates/shell/dashboard_shell.html` reconstructs Personal and organisation
  choices from `current_context`, `current_org_id`, and `user_organisations`, then
  renders separate role dashboard links. The template also contains inline styles
  and inline JavaScript for the switcher and pane controller.
- `templates/user/` and `templates/fan/` provide additional entry points and role
  presentation. The current contract is not one normalized `active_context`,
  `available_contexts`, and request-time capability object.
- The existing switch endpoint accepts both `GET` and `POST`, mutates legacy
  session values directly, and accepts an organisation identifier without a
  normalized role/context request. It checks membership, but does not implement a
  single cross-domain contract or privileged transition audit.

### 2.8 Audit and persistence

`ForensicAuditService` in `app/audit/forensic_audit.py` already provides
`log_attempt`, `log_completion`, and `log_blocked`. It captures actor/effective
identity where available and can attach IP address, user agent, session ID,
correlation ID, risk score, and structured details. Context switching can reuse
this service; a new context-audit table is not required.

No effective permission set, assignment row, or permission snapshot may be stored
in Flask session. Only the selected context identity and validated role belong in
the session.

## 3. Current gaps and risks

1. Legacy `current_context`, `current_org_id`, `current_org_name`, and related
   values are read and written by login, onboarding, helpers, redirects, context
   processors, user dashboard code, and templates.
2. Global role switching and operating-context switching are separate UI concepts
   without a common contract, making highest-role routing easy to confuse with the
   user's selected workspace.
3. Organisation context is checked by the current policy bridge, but event,
   driver, and host eligibility are resolved by unrelated route/service paths.
4. The shell infers available contexts from model-shaped template variables and
   duplicated role links rather than receiving one server-normalized list.
5. The current switch route accepts `GET` and has no single fail-closed public
   identifier/role contract for all context types.
6. Revocation after selection is not represented by a canonical active-context
   revalidation operation.
7. The driver model lacks a confirmed canonical public identifier. This is a
   reviewed schema/API-boundary issue, not permission to expose an internal ID.
8. Existing model ENUM usage is outside this feature's scope. The context work
   adds no schema or PostgreSQL ENUM and must not use this feature to bypass the
   database scalability migration policy.

## 4. Formal behavioral contract

### 4.1 Affected entities and state

The resolver reads, but does not duplicate, these authorities:

| Capacity | Eligibility records | Resource state |
|---|---|---|
| Personal | Authenticated active `User` | User is authenticated and not deleted/deactivated |
| Platform | `UserRole` → `Role` → permission records | Assigned role is current; user is active |
| Organisation | `OrganisationMember`, `OrgUserRole`, direct overrides | Membership active; organisation active, operational as required, and not deleted |
| Event | `EventRole`, organiser/organisation relationship, domain policy | Role active; event status permits the operation; event not deleted, suspended, or deactivated |
| Driver | `DriverProfile` and transport verification/operational rules | Profile not deleted/suspended; verification/compliance and required availability rules pass |
| Accommodation host | `HostProfile` or `HostOrganisationProfile`, identity service, host ownership | Host active and not suspended; user/organisation and property lifecycle checks pass |

### 4.2 Inputs and outputs

The browser may submit only a normalized request:

```text
ContextRequest:
  type: personal | organisation | event | driver | accommodation_host | platform
  id: public identifier, or null for personal
  role: optional requested role label
  next: optional same-origin return target
```

The resolver returns a normalized descriptor containing only safe boundary data:

```text
ContextDescriptor:
  type
  public_id
  label
  role
  workspace_url
  permission_lookup_metadata (server-side only)
```

`public_id` means the existing public boundary for that resource. Internal
numeric IDs are query-only and never appear in descriptors, URLs, templates,
audit details intended for users, or API responses.

### 4.3 Valid transitions

| Transition | Preconditions | Result |
|---|---|---|
| No valid selection → Personal | User is authenticated | Canonical Personal context is selected; Flask-Login state is unchanged |
| Any context → requested context | Type, public identifier, role, assignment, ownership, and active resource all resolve for `current_user` | Session selection is replaced; no persistent assignment changes |
| Any context → invalid/unassigned/revoked context | Any eligibility, identifier, role, CSRF, or lifecycle check fails | Request is rejected or selection is cleared to Personal; no authority is granted |
| Selected context → protected operation after revocation | Fresh database resolution finds assignment/resource inactive or revoked | Operation is denied and stale selection is invalidated or falls back to Personal |

### 4.4 Invariants and authority boundaries

- `current_user` and its Flask-Login session remain the same across every switch.
- Requested type, ID, and role are hints only; the database establishes eligibility.
- Switching never inserts, updates, deletes, or reassigns `UserRole`,
  `OrgUserRole`, `OrganisationMember`, `EventRole`, host, driver, booking, or
  ownership records.
- Effective permissions are resolved from current database/domain policy on each
  protected operation. They are never persisted in Flask session.
- The selected context affects workspace navigation and context-aware policy
  lookup; it does not replace domain ownership, booking ownership, guest identity,
  service delegation, or wallet ledger authorization.
- After a successful switch, the descriptor's validated `workspace_url` is the
  primary landing target. A submitted same-origin `next` value is only a
  compatibility fallback when no workspace URL can be resolved; it must not
  send a valid context back to the generic Personal dashboard.
- Session-wide tab behavior is intentional. It is a convenience selection, not an
  authorization boundary; every protected operation revalidates authority.
- Invalid, inactive, suspended, soft-deleted, or revoked resources fail closed.
- Safe redirects are same-origin and allowlisted; an arbitrary submitted `next`
  value cannot create an open redirect.

### 4.4.1 Organisation operating workspace

An eligible organisation context lands at `/org/{organisation.public_id}/dashboard`.
The organisation workspace is a read/navigation boundary for the selected
organisation and must expose only resources owned by that organisation:

The user-facing hierarchy is deliberately explicit:

```text
HUMAN
  └── USER (current_user; one authenticated person)
      ├── PERSONAL CONTEXT (“Me”)
      └── ORGANISATION CONTEXT (“Hotel ABC”)
          └── Organisation role/authority (for example, Hotel Manager)
              ├── Operations
              └── Bookings
```

`HUMAN` is a conceptual person boundary, not a second database identity.
`USER` is the single Flask-Login principal. `Personal` and `Organisation` are
selected operating contexts, while the organisation role is resolved from the
current membership and role assignments; a display label such as “Hotel
Manager” never grants authority by itself. Operations and Bookings are
navigation areas whose protected requests must continue to enforce the live
organisation permissions and the accommodation domain policy.

| Workspace view | Organisation ownership predicate | User-visible result |
|---|---|---|
| Events | `Event.organization_id`, organisation creator, or current organisation owner | Events belonging to the selected organisation |
| Properties | `Property.owner_org_id` | Properties listed by the selected organisation |
| Bookings | Booking property joins to `Property.owner_org_id` | Bookings for the selected organisation's properties |

The resolver may use internal organisation IDs for database joins only. The
browser receives the organisation `org_id` public identifier in URLs and links.
Selecting an organisation does not change the authenticated user, create a
membership, grant permissions, change a booking owner, or authorize a workflow
that the current organisation policy does not allow. Booking mutations and the
final organisation authority matrix remain separate follow-up work.

### 4.5 Failure conditions

The switch is rejected for an unknown type, malformed or unassigned public ID,
role mismatch, another user's organisation/event/service, inactive membership,
inactive or deleted resource, revoked event role, suspended host, ineligible
driver, missing CSRF token, unauthenticated request, or unsafe redirect.

When a previously selected context fails fresh resolution, the resolver clears only
the active-context selection and returns Personal. It does not log the user out or
change permanent roles.

## 5. Approved target architecture

### 5.1 Resolver with adapters

The implementation will add `app/auth/context.py` as a canonical normalization
layer. It will use lazy imports or small adapters so domain modules retain ownership
of their assignment and lifecycle rules and identity/domain circular imports are
avoided.

The service API is:

- `get_available_contexts(user)` — enumerate only currently eligible descriptors.
- `get_active_context(user=None)` — read minimal session selection and re-resolve
  it from the database; clear invalid selections.
- `validate_context(user, requested)` — fail-closed public-boundary validation.
- `switch_context(user, requested)` — validate, audit where required, and write
  only the minimal selection.
- `resolve_effective_permissions(user, context)` — delegate to existing global,
  organisation, event, transport, and accommodation policy services.
- `clear_active_context()` — clear selection and establish Personal behavior.

Adapters will cover Personal/global, organisation, event, driver,
accommodation-host, and platform-administration descriptors. No context registry,
second RBAC table, automatic highest-role selection, or duplicate account is
introduced.

### 5.2 Session contract

The canonical selection contains only:

```text
active_context_type
active_context_id
active_role
```

The legacy `current_context`/`current_org_id` values may be read temporarily by a
compatibility layer while concrete consumers migrate, but new code must not write
legacy values or use them as authority. No permissions, assignments, internal IDs,
or resource snapshots are stored in session.

### 5.3 Policy and template contract

Existing `can()` and domain policy functions remain compatible. A context-aware
entry point will provide the selected descriptor to policy resolution while
preserving owner, global-role, organisation, event, transport, accommodation, and
module guards.

Authenticated templates receive:

```text
active_context
available_contexts
effective_permissions
can(permission)
```

Jinja must not query ORM models, infer role hierarchy, or expose internal IDs.
There is one persistent “Operating as” control; entries appear only when returned
by the resolver.

### 5.4 Endpoint and audit contract

The switch endpoint becomes one authenticated `POST` contract with CSRF
protection, public identifiers, role validation, same-origin redirect validation,
safe JSON/redirect responses, and fail-closed errors. `GET` must not mutate
context.

Privileged or operational transitions use `ForensicAuditService` attempt,
completion, and blocked records. Details include previous/new public context,
role, resource label or public identifier, request metadata, and correlation ID;
internal database IDs are not placed in user-facing details.

## 6. Database and migration position

This feature requires no new table or planned schema migration. Existing
assignments and lifecycle fields remain authoritative. Before implementing any
adapter, confirm that its resource has a safe existing external identifier:

- organisation: existing unique `org_id` boundary;
- event: existing `public_id` boundary;
- user: existing `public_id` boundary;
- property: existing `public_id` boundary;
- driver/vehicle/service records: use an existing reviewed public code only when
  its API contract is confirmed.

If a missing public identifier makes an adapter unsafe, stop that adapter slice and
document a separately reviewed model/constraint, expand-contract migration, and
rollback plan. Do not expose a `BigInteger` and do not run `flask db migrate` or
`flask db upgrade` automatically.

## 7. Security and revocation model

The server flow is:

```text
browser POST with CSRF and public context
  → Flask-Login current_user
  → resolver adapter
  → persistent assignment and resource lifecycle checks
  → existing domain policy
  → minimal session selection
```

A forged organisation, event, property, vehicle, driver, role, or redirect value
cannot establish authority because it is resolved against the authenticated user's
live assignments. A role or membership revoked after selection is denied on the
next fresh resolution even if an old session value remains. The stale selection is
then cleared safely.

Context switching does not touch wallet models, balances, ledger entries,
transaction ownership, idempotency, or AML decisions.

## 8. Verification contract and boundaries

Focused tests must prove:

- one user can receive distinct Personal, global, organisation, event, driver,
  host, and platform descriptors;
- Personal → organisation → event → driver → Personal preserves login identity;
- organisation A/B and event A/B switches require the user's own assignments;
- malformed, forged, inactive, revoked, suspended, and unassigned contexts fail;
- fresh revocation invalidates a selected context;
- session writes contain only the three canonical selection keys;
- CSRF-less mutations and unsafe redirects fail;
- templates consume normalized context data without ORM queries or internal IDs;
- privileged transitions emit expected forensic audit attempt/completion/blocked
  records;
- application startup remains import-safe and existing module ownership checks are
  preserved.

The implementation must report separately which adapters/routes are migrated,
which tests are passing, which verification is blocked by database/environment
state, which identifiers need product/schema review, and which domain routes remain
on their existing guards. It must not claim that all domain routes consume the
canonical context until each migrated route has test evidence.
