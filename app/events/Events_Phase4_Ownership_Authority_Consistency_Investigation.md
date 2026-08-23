# Phase 4 Ownership Authority Consistency Investigation

**Date:** 2026-08-18  
**Scope:** Event creation, mutation, transfer, and legacy ownership authority  
**Status:** Evidence-only; no production, test, schema, migration, or data changes made

## Evidence boundary

This report describes the current repository implementation and existing test
coverage. It does not infer intended behavior from field names or from the
Phase 1 conceptual model. PostgreSQL evidence previously recorded for the
certification run found `0` events where `current_owner_id IS NULL` and
`organizer_id IS NOT NULL`; no data was changed during this investigation.

## 1. Field authority matrix

| Field | Actual FK/type and nullability | Current code semantics | Authoritative for ownership? | Authoritative for authorization? |
|---|---|---|---|---|
| `organizer_id` | `BigInteger`, `ForeignKey("users.id")`, `nullable=False`; `organizer` relationship targets `User` | Model documents it as the public-facing contact; constructor/default-owner logic and legacy permission fallback retain it | Only legacy fallback when both canonical owner values are absent | `_is_event_owner()` consults it only when canonical owner is absent; contact route uses it as a defensive recipient fallback |
| `organization_id` | `BigInteger`, `ForeignKey("organisations.id", ondelete="SET NULL")`, `nullable=True` | Organization relationship/boundary for organization-created events; used by `_is_org_member_of_event()` | No; ownership uses `current_owner_*` | Organization membership/role checks use it for event-scoped organization authority |
| `original_creator_id` | `BigInteger`, `ForeignKey("users.id", ondelete="SET NULL")`, `nullable=True` | Original user associated with creation; contact route uses it as a fallback; `can_delete_event()` grants a 24-hour creator grace path | No | Only the specific creator grace rule in `can_delete_event()`; not canonical owner authority |
| `current_owner_type` | `String(20)`, `nullable=False`, default individual | Owner discriminator; mutable through transfer service; system owner constrained to ID `0` | Yes when populated | `_is_event_owner()` uses it with `current_owner_id`; role/permission paths also rely on canonical ownership |
| `current_owner_id` | `BigInteger`, `nullable=False` in the model; no polymorphic FK constraint | Current owner entity ID; user, organization, or system ID according to `current_owner_type` | Yes when populated | Individual owner checks use it; organization membership checks separately use `organization_id`; no DB FK enforces polymorphic target |

### Organization creation code path

`EventService.create_event()` at `app/events/services.py:576-580`
requires `organization_id` and checks `has_org_role(user, organization_id,
'org_owner', 'org_admin')` for `creator_type == 'organization'`.

The `Event(...)` assignment at `app/events/services.py:629-651` is:

- `organizer_id=user_id`;
- `created_by_type=creator_type`;
- `created_by_entity_id=organization_id` for organization creation;
- `organization_id=organization_id` for organization creation;
- `original_creator_id=user_id`;
- `current_owner_type=creator_type`;
- `current_owner_id=organization_id` for organization creation.

Therefore the current implementation does **not** assign the organization ID
to the `users.id`-typed `organizer_id` in this path. The organizer value is the
authenticated creating user, while organization ownership and association use
the organization fields. This specific assignment is **CONSISTENT** with the
declared FK types, although the model's non-null public-contact contract and
the polymorphic owner contract remain separate concerns.

For `creator_type == 'individual'`, the same path assigns the authenticated
user to `organizer_id`, `original_creator_id`, and `current_owner_id`, with
individual owner type. For `creator_type == 'system'`, creation is restricted
to platform roles, assigns `organizer_id=user_id` and `original_creator_id=user_id`,
and assigns system owner type with owner ID `0`.

## 2. Operation authority matrix

| Operation | Individual event | Organization event | System event | Transferred event | Legacy event |
|---|---|---|---|---|---|
| Create | `create_event()` allows the authenticated user; owner becomes that user | Requires `has_org_role()` for the supplied organization; owner becomes organization ID and creator/contact fields remain user-based | Requires a global platform role; owner becomes `system/0` | Not applicable at creation | Constructor can derive individual owner from `organizer_id` when canonical owner is absent |
| Update (`EventService.update_event`) | `_is_event_owner()` requires canonical individual owner; legacy fallback only if both canonical owner values are absent | `_is_event_owner()` does not grant organization-member authority; it only checks individual ownership or legacy user fallback | No system owner user match is possible through `_is_event_owner()` | Current canonical individual owner can update; former owner is denied by canonical precedence | User matching `organizer_id` can update only when both canonical owner values are absent |
| Delete route | `can_delete_event()` permits canonical owner; route then calls `change_event_status()` | `can_delete_event()` permits matching org roles using `organization_id`; status service does not repeat that org check for archive | Platform moderation permission is required by `change_event_status()` for terminal deletion; owner check cannot match system/0 | Canonical current individual owner is used; stale organizer cannot pass `_is_event_owner()` | `can_delete_event()` can permit legacy organizer through `_is_event_owner()` when canonical owner is absent |
| Delete service (`EventService.delete_event`) | `_is_event_owner()` required | Organization membership is not checked by this service | System owner cannot match a user through `_is_event_owner()` | Canonical owner precedence applies | Legacy organizer fallback applies when canonical owner is absent |
| Status mutation (`change_event_status`) | Publishing checks `_is_event_owner()` or global approval permission | Publishing does not directly grant organization membership; route-level `require_event_permission()` may allow org roles before service call | Approval/moderation permissions govern protected transitions | Publishing uses canonical owner; stale organizer cannot override it | Publishing may use legacy fallback only through `_is_event_owner()` when canonical owner is absent |
| Transfer request | `_is_event_owner()` or `requester.is_super_admin()` | Organization owner cannot be recognized by `_is_event_owner()` because it checks users; no separate organization-owner authorization is present in this method | System owner cannot initiate via owner predicate; super-admin method is the separate path | Current canonical owner is the source for request `from_*` fields | Legacy organizer can initiate only while canonical owner fields are absent |
| Transfer approval | `approve_event_transfer()` loads the approver but performs no target-owner/admin authorization check before `req.approve()` | Same missing approver authorization check; target organization is written from request | Same missing check | Writes new canonical owner and logs previous canonical owner | Does not alter `organizer_id`; legacy field remains unchanged |

## 3. Exact mutation-path findings

### Update

`EventService.update_event()` (`app/events/services.py:712-754`) obtains the
user and requires `_is_event_owner(user, event)`. It does not call
`_is_org_member_of_event()`, `can_manage_event()`, or an EventRole check.
Consequently, an organization-owned event (`current_owner_type ==
'organization'`) is not updateable through this service by an organization
member unless another path bypasses the service. The route delegates directly
to this method at `app/events/routes.py:469`.

**Classification:** `INCONSISTENT` for organization-owner/operator update
authority; individual canonical-owner and legacy fallback behavior is
consistent with `_is_event_owner()`.

### Delete

The public delete route first calls `can_delete_event()` at
`app/events/routes.py:1522`. That dispatcher allows an organization member
with `org_owner` or `org_admin` for `event.organization_id` at
`app/events/permissions.py:507-514`. It then calls
`change_event_status()` with `ARCHIVED` for non-super-admin users. The shown
status service authorization branches enforce global moderation permission for
`DELETED` and owner/global approval permission for `PUBLISHED`, but do not
repeat the organization-member check for `ARCHIVED`.

Separately, `EventService.delete_event()` at `app/events/services.py:862-880`
requires `_is_event_owner()` and has no organization-member branch. These are
two distinct deletion paths with different authority contracts.

**Classification:** `INCONSISTENT` across deletion entry points. The route's
organization authorization is broader than the service's direct deletion
method; the route's second status call does not establish a single centralized
organization authority contract.

### Transfer

`request_event_transfer()` (`app/events/services.py:757-803`) requires
`_is_event_owner()` or `requester.is_super_admin()`, then derives the
`from_*` fields from canonical ownership. `approve_event_transfer()`
(`app/events/services.py:806-859`) loads `approver`, computes the requested
target, calls `req.approve(approver_id)`, logs the transition, and writes
`current_owner_type/current_owner_id`.

The code comment at `services.py:831-832` says approver authority should be
verified in a real system, but the current function contains no such check.
Any existing pending request can therefore reach the mutation block with an
authenticated existing `User` as approver; target-owner membership or platform
administration is not verified here.

**Classification:** `DEFECT_CONFIRMED` for missing approval authorization;
`COMPATIBILITY_REQUIRED` for leaving `organizer_id` unchanged during transfer.

### Other discovered status paths

The routes for reject, suspend, reactivate, pause, resume, and delete first
call `require_event_permission()` or `can_delete_event()`, then delegate the
state write to `change_event_status()`. `change_event_status()` uses global
permissions for moderation/approval transitions and canonical owner checks for
publishing. This is a split authority design: route dispatchers and the service
do not uniformly apply the same predicate for every transition.

## 4. Safety-invariant assessment

Invariant under review:

> Once `current_owner_type/current_owner_id` is populated, stale `organizer_id`
> must never grant greater authority than the canonical owner.

| Path | Result | Code evidence |
|---|---|---|
| `_is_event_owner()` permission predicate | **PROVEN** | `permissions.py:107-123` checks canonical owner first and returns `False` when either canonical field is present and does not match; fallback runs only when both are absent |
| `EventService.update_event()` | **PROVEN for stale-organizer precedence** | Delegates to `_is_event_owner()` at `services.py:719-721`; organization authority is separately incomplete |
| `EventService.delete_event()` | **PROVEN for stale-organizer precedence** | Delegates to `_is_event_owner()` at `services.py:868-870`; organization authority is separately incomplete |
| Delete route | **PROVEN for its owner branch; not a complete authority proof** | `can_delete_event()` uses `_is_event_owner()` for owner branch but also has platform, event-manager, organization, and creator-grace branches |
| Publish/status mutation | **PROVEN for owner-based publishing** | `change_event_status()` at `services.py:520-523` uses `_is_event_owner()`; other status transitions use global permission policies |
| Transfer request | **PROVEN for owner-based request initiation** | `request_event_transfer()` at `services.py:776-782` uses `_is_event_owner()` or super-admin path |
| Transfer approval | **NOT_PROVEN as a complete authorization contract** | Canonical owner fields are written and organizer is not changed, but approver authorization is not checked |

The stale organizer cannot override a populated canonical owner in the
owner-predicate paths inspected. However, the broader invariant that *every
mutation path uses one complete authority contract* is disproven by the
organization update/delete differences and the missing transfer-approval
authorization.

## 5. Existing tests, runtime qualifications, and gaps

### Existing coverage

- `tests/test_events_ownership_characterization.py:52-145` covers individual
  organizer/current-owner behavior, creator-not-owner behavior, canonical
  owner precedence over a stale organizer, and legacy fallback without
  canonical owner fields.
- `tests/test_events_ownership_characterization.py:146` onward covers an
  organization operator/EventRole context path, but does not exercise
  `EventService.update_event()` or the public delete route for an
  organization-owned event.
- `tests/test_event_transfer_lifecycle.py:62-146` covers transfer request
  success/unauthorized behavior, organization target transfer, transfer log
  contents, and blocking ownership payload changes through ordinary update.
- The inspected transfer tests do not prove that an unauthorized authenticated
  user cannot approve an otherwise valid pending request.
- No inspected test covers system-event update/delete/status authority as a
  complete matrix.
- No inspected test covers the organization-created `create_event()` persisted
  assignments end-to-end against the PostgreSQL schema.

### Runtime/database qualifications

- The certification regression selection previously completed with exit code
  `0`, `28 passed`, and `13 warnings` after the ASCII-only Windows fixture
  output correction.
- The database query for records with missing canonical ownership and a
  non-null organizer returned `0`; this is current database evidence only and
  does not prove all historical or future creation paths are safe.
- The prior command counting `LEGACY CONSTRUCTOR FALLBACK` matched `16` log
  lines and exited `1` because `Select-String` found no matching output under
  that exact command pipeline; this is test-log instrumentation evidence, not
  production-consumer evidence.
- External production traffic is unavailable or unestablished because the
  module remains in development; no zero-production-consumer claim is made.

## 6. Unresolved conflicts and dispositions

| Finding | Classification | Disposition |
|---|---|---|
| Organization creation passes organization ID to `current_owner_id` but user ID to `organizer_id` | `CONSISTENT` with declared FK targets; semantics remain separate | Retain; no fix in this node |
| Populated canonical owner outranks stale organizer in owner predicate | `CONSISTENT` / `PROVEN` in inspected owner paths | Retain compatibility fallback for legacy records |
| Organization-owned update authority differs from organization-aware delete route | `INCONSISTENT` | Requires an authorized correction/design node before coverage can be treated as complete |
| Direct delete service and delete route use different authority boundaries | `INCONSISTENT` | Requires an authorized authority-contract reconciliation node |
| Transfer approval lacks target-owner/platform authorization check | `DEFECT_CONFIRMED` | Requires a separately authorized security/authority correction; not fixed here |
| `organizer_id` public-contact and legacy fallback semantics | `COMPATIBILITY_REQUIRED` / `NOT_READY` | Retain; do not map to canonical owner by assumption |
| System-event mutation coverage | `INSUFFICIENT_EVIDENCE` | Requires targeted evidence after authority contract is resolved |

## 7. Recommended graph transition

`OWNERSHIP_AUTHORITY_CORRECTION_REQUIRED`

The smallest safe next boundary is an explicitly authorized authority-contract
correction/design node covering: (1) one canonical organization-owner/operator
policy for update and delete; (2) one approval-authorization policy for
`approve_event_transfer()`; and (3) preservation of canonical-owner precedence
and legacy organizer compatibility. Test-only coverage should follow that
correction decision; no schema, data, compatibility-field removal, or creator
field change is authorized by this report.