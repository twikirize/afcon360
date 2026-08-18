JUNIE PROMPT — AFCON360 Events Authorization & Ownership Restructure
# AFCON360 EVENTS — CONTROLLED AUTHORIZATION / OWNERSHIP RESTRUCTURE


## ROLE


You are working as a senior backend architect and migration engineer on AFCON360.


This is NOT a greenfield implementation.


The Events module already contains working functionality, models, routes, services, registrations, ticketing, moderation, check-in, statistics, notifications/signals, and integrations with other AFCON360 services.


Your job is to evolve the Events authorization/ownership architecture WITHOUT breaking existing functionality.


============================================================
0. ABSOLUTE RULE — DO NOT DESTROY WORKING FUNCTIONALITY
============================================================


This is a controlled architectural migration.


DO NOT:


- rewrite the Events module from scratch
- delete existing models simply because they are imperfect
- remove existing endpoints
- remove existing event workflows
- remove ticketing/registration functionality
- remove moderation functionality
- remove check-in functionality
- remove notifications/signals
- remove accommodation/transport integration
- perform broad unrelated refactoring
- change database semantics without an explicit migration plan
- create a second parallel authorization system
- replace existing behavior with untested assumptions


Existing behavior is valuable.


FIRST understand what exists.


THEN design the migration.


THEN implement incrementally.


Every existing behavior that remains valid must be preserved.


============================================================
1. PRIMARY ARCHITECTURAL PROBLEM
============================================================


The current Events implementation mixes several concepts that need to be separated:


1. Person/User
2. Organisation
3. Acting context / principal
4. Event creator
5. Event owner
6. Organisation operating an event
7. Event venue/host
8. Event staff
9. Event participants
10. Permissions


These concepts must NOT be treated as interchangeable.


AFCON360 supports both:


- individual users
- organisations


A person may belong to one or more organisations and may act:


- personally
- on behalf of an organisation
- in a particular resource/event context


This must work consistently across AFCON360.


============================================================
One thing I'd add specifically for Junie

Because of what we've already seen in your current code, I'd put this at the very top of the task:

Do not interpret this prompt as permission to redesign the entire AFCON360 identity/organisation system. First discover the existing identity, organisation, and authorization architecture and integrate Events into it. Events must be a consumer of the platform authorization model, not the owner of a new competing authorization model.

That's important because otherwise Junie could solve the Events problem beautifully while accidentally creating a second RBAC system, which would come back to hurt us when Accommodation, Transport, Tourism and Events all need the same person/context switching.

And I would have Junie work in this order
CURRENT CODE
     │
     ▼
PHASE 0: AUDIT
     │
     ▼
ARCHITECTURE / MIGRATION PLAN
     │
     ▼
REVIEW
     │
     ▼
AUTHORIZATION ABSTRACTION
     │
     ▼
OWNERSHIP / RELATIONSHIPS
     │
     ▼
PERMISSION MIGRATION
     │
     ▼
ROUTE/SERVICE MIGRATION
     │
     ▼
REGRESSION TESTS
     │
     ▼
DEPRECATE OLD MODEL
     │
     ▼
REMOVE ONLY WHEN SAFE

That is the safe way to do this. We're not throwing away what Junie has built; we're putting a better foundation underneath it and migrating the existing behavior onto that foundation.

And I would absolutely make Phase 0 mandatory. Given the amount of existing Events functionality in services.py, routes.py, models, signals and integrations, letting an agent immediately "refactor the roles" is too risky.

# AFCON360 EVENTS — PHASE 1 ARCHITECTURAL REFINEMENT
# DO NOT REWRITE — CONSOLIDATE WHAT ALREADY EXISTS

Phase 0 audit is accepted.

The audit has revealed that the Events module already contains several of the architectural foundations we were considering:

- app/events/permissions.py
- contextual permission functions
- resolve_user_roles(user, event)
- platform/global authorization
- organisation authorization
- EventRole
- organisation-scoped EventRole assignments
- polymorphic event creator
- polymorphic current owner
- EventTransferRequest
- EventTransferLog
- moderation logging

Therefore, DO NOT implement a second authorization system.

This is now a REFINEMENT AND CONSOLIDATION project, not a rewrite.

============================================================
1. PRIMARY OBJECTIVE
============================================================

Determine whether the existing architecture can be evolved into the following conceptual model:

    PERSON / USER
          |
          +----------------------+
          |                      |
       PERSONAL             ORGANISATION
       CONTEXT                 CONTEXT
          |                      |
          +----------+-----------+
                     |
                  EVENT
                     |
       +-------------+-------------+
       |             |             |
     OWNER        OPERATOR      VENUE HOST
       |             |             |
       +-------------+-------------+
                     |
                PERMISSIONS

The existing implementation should be preserved wherever possible.

============================================================
2. DO NOT CREATE NEW AUTHORIZATION INFRASTRUCTURE
============================================================

The existing:
    app/events/permissions.py

(Continue building on the existing centralized permissions.py, organization-aware authorization, event-level roles, individual/organization ownership, ownership transfer, creator tracking, moderation tracking).

The biggest thing we're fixing is the semantic confusion where `organizer` is currently doing too many jobs. 
We want to clearly separate OWNER, OPERATOR, and VENUE, while preserving CREATOR (audit/history) and PARTICIPANT.

Do not create new database tables yet. Answer the Phase 1 questions first to see if EventRole + organisation_id + permissions.py can already represent an organisation operating an event on behalf of another owner. If so, we make a small change instead of massive rewrite.