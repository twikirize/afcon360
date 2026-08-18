AFCON360 — Event Host Guest Allocation, Accommodation & Transport Integration
Role

You are the implementation agent working directly inside the existing AFCON360 Flask application in PyCharm.

Do not build this as a standalone feature or a parallel subsystem.

Your job is to inspect the existing AFCON360 architecture, understand the current Events, Accommodation, Transport, Identity/Auth, Booking, and Notification implementations, and then implement a complete cross-module workflow that connects them through the existing domain models and ownership rules.

The target outcome is:

An authorized Event Owner/Host can view the attendees registered for an event and coordinate their accommodation and transport using the existing AFCON360 accommodation inventory/bookings and transport providers/drivers.

The feature must be implemented end-to-end:

database → models → services → routes → authorization → validation → templates → static assets → notifications → tests → migrations

Do not stop at adding UI fields or database tables.

1. Core Business Scenario

AFCON360 allows an authorized person to create/manage an event as an:

Event Owner
Event Host / authorized event representative

The event can receive a list of registered attendees.

Example:

An event has 100 registered attendees.

The event host must be able to:

Open the event.
View all registered attendees.
See their registration status and relevant identity information.
Select one or more attendees.
Assign accommodation to them.
Use accommodation already booked/reserved by the event, including:
rooms from the same hotel,
rooms from multiple hotels,
different room types,
different dates where permitted.
Assign an individual guest to a specific accommodation unit/room or accommodation allocation.
Assign transport to attendees using the existing AFCON360 transport ecosystem.
Select from available/approved transport providers, vehicles, and/or drivers according to the existing transport rules.
Track who has been assigned, who remains unassigned, and what remains available.
Notify the relevant people through the existing notification system.
Maintain a complete audit trail of who made each assignment.

The system must therefore become a coordination layer over the existing domain capabilities, not a replacement for them.

2. Critical Architectural Principle

Follow the existing AFCON360 domain ownership rules.

Accommodation owns accommodation capacity

The Accommodation Service owns capacity, room inventory, room availability, room types, units, and accommodation booking state.

The Event module may request or coordinate accommodation allocation.

The Event module must never invent, duplicate, or directly manipulate accommodation capacity.

Do NOT create something like:

EventGuest.room_count
Event.room_inventory
EventBooking.total_rooms

as a second source of truth.

Instead, connect Event participants to the existing accommodation booking/allocation structures.

The existing accommodation domain remains authoritative.

3. Existing Accommodation Architecture Must Be Reused

Before modifying anything, inspect the current Accommodation implementation.

You previously established the following architectural layers:

LAYER 1
Inventory
    ↓
How many rooms/units exist?
    ✅ Accommodation owns this

LAYER 2
Occupancy
    ↓
How many people can those rooms accommodate?
    ✅ Accommodation owns this

LAYER 3
Booking / Reservation
    ↓
Which inventory is committed for which dates?
    ✅ Accommodation owns this

Your new feature must build on these existing layers.

Do not bypass them.

The Event module should effectively say:

"For attendee X, allocate/associate an existing valid accommodation booking/allocation."

It should not say:

"Event X has 100 rooms."

unless that information already comes from a real accommodation booking/reservation.

4. Event Guest Concept

Inspect the existing event registration/attendee implementation.

Determine the existing entity representing:

event registration
event attendee
participant
guest
ticket holder
registration record

Reuse that entity where possible.

Do not create a duplicate guest identity table unless the existing architecture genuinely requires it.

The system should distinguish between:

User
    ↓
Event Registration / Attendee
    ↓
Accommodation Assignment
    ↓
Transport Assignment

An attendee may exist as an event participant even when they have:

no accommodation assignment,
no transport assignment,
only accommodation,
only transport,
both accommodation and transport.
5. Booking Ownership Must Be Respected

Continue using the booking ownership principles already established in AFCON360.

Do not confuse:

User
Creator
Booking Owner
Guest

The Event Host is not automatically the accommodation guest.

For example:

Event Owner
     ↓
Organizes event
     ↓
Registers attendees
     ↓
Coordinates accommodation
     ↓
Accommodation booking belongs to appropriate Booking Owner
     ↓
Individual attendees become Guests / occupants

Implement the relationship without changing the legal meaning of the existing booking ownership model.

6. Recommended Domain Relationship

Design the integration around an explicit assignment/coordination entity.

For example, conceptually:

Event
   |
   +---- EventAttendee
            |
            +---- AccommodationAssignment
            |
            +---- TransportAssignment

The exact model names must follow the existing project conventions.

Do not blindly create these exact names if equivalent models already exist.

The assignment entity should preserve references to the authoritative domain objects.

For accommodation, for example:

event_attendee
    ↓
accommodation_assignment
    ↓
accommodation_booking / booking / allocation
    ↓
property
    ↓
room_type
    ↓
room/unit

For transport:

event_attendee
    ↓
transport_assignment
    ↓
transport booking / trip / vehicle / driver

Use the actual existing AFCON360 model structure.

7. Accommodation Assignment Requirements

The Event Host must be able to see the accommodation resources that are legitimately available to the event.

Examples:

Event Booking
    Hotel A
        Room 101
        Room 102
        Room 103

    Hotel B
        Room 201
        Room 202

    Hotel C
        Room 301

The Event Host should be able to assign:

Attendee A → Hotel A / Room 101
Attendee B → Hotel A / Room 102
Attendee C → Hotel B / Room 201
Attendee D → Hotel C / Room 301

The implementation must support multiple hotels.

It must also support more than one room/unit per booking where the existing accommodation booking model permits it.

8. Capacity and Occupancy Validation

This is critical.

When assigning a guest to accommodation, validate against the real accommodation data.

Never simply check:

if room:
    assign()

Validate at minimum:

booking exists,
booking is valid,
booking belongs to or is authorized for the event coordination context,
room/unit exists,
room/unit belongs to the correct property,
room/unit is not already fully occupied,
guest assignment does not exceed allowed occupancy,
date range is compatible,
room status permits assignment,
booking/allocation has sufficient remaining capacity,
duplicate assignment is prevented.

Where the accommodation system already calculates occupancy/availability, reuse that service instead of duplicating its calculations.

9. Do Not Break Accommodation Availability Logic

The previous accommodation work established that inventory and occupancy must be treated separately.

Therefore:

Inventory
≠
Occupancy
≠
Event Guest Assignment

An event assignment must consume/affect the appropriate existing occupancy/allocation mechanism.

Do not introduce hard-coded values such as:

RoomType.total_units = 1

or assume one unit per room type.

Do not introduce event-specific shortcuts that bypass real room availability.

10. Group Accommodation Allocation

The Event Host should also be able to manage a bulk allocation workflow.

Example:

100 Event Attendees

Hotel A → 40 available guest capacity
Hotel B → 35 available guest capacity
Hotel C → 25 available guest capacity

The interface should allow the host to allocate attendees across those properties.

However, the allocation must still be validated against the real accommodation inventory and occupancy rules.

Provide useful views such as:

Assigned:      72
Unassigned:    28

Hotel A:       35 / 40
Hotel B:       25 / 35
Hotel C:       12 / 25

These values must come from live authoritative data.

11. Guest-Level Accommodation Detail

For each attendee, provide a clear status.

Example:

Guest	Accommodation	Room	Status
John Doe	Hotel A	101	Assigned
Mary Doe	Hotel B	204	Assigned
Peter Doe	—	—	Unassigned

The user should be able to open an attendee and see:

Attendee
Name
Registration number
Contact
Event
Registration status

Accommodation
Property
Room type
Room/unit
Check-in
Check-out
Assignment status

Transport
Vehicle
Driver
Pickup
Drop-off
Assignment status
12. Transport Integration

The same event attendee should be assignable to transport.

Reuse the existing AFCON360 Transport module.

Do not create a second driver database.

The Event Host should be able to select from drivers/vehicles/providers that the transport system already recognizes as:

registered,
approved,
active,
available,
eligible for the requested transport.

The exact eligibility rules must come from the existing transport implementation.

13. Transport Assignment Example

Example:

Attendee A
    ↓
Transport Assignment
    ↓
Vehicle UAA 123A
    ↓
Driver John
    ↓
Pickup: Entebbe Airport
    ↓
Drop-off: Hotel A

Another attendee could be assigned to:

Vehicle UBB 456B
Driver Peter
Pickup: Hotel B
Drop-off: Event Venue

Support the existing transport concepts rather than inventing new ones.

14. Driver and Vehicle Availability

Before assignment, validate:

driver exists,
driver is approved,
driver is active,
driver is available,
vehicle exists,
vehicle is active,
vehicle is approved where required,
vehicle capacity is sufficient,
date/time does not conflict,
assignment does not exceed capacity,
the attendee is not double-booked for conflicting transport,
existing transport constraints are respected.

Do not allow an event host to assign an unavailable or unauthorized driver simply because the driver exists in the database.

15. Event Host Authorization

This feature must be permission-controlled.

An arbitrary authenticated user must NOT be able to manipulate attendee accommodation or transportation.

Determine the project's existing authorization approach and reuse it.

Possible authorization chain:

Authenticated User
      ↓
Event membership / ownership
      ↓
Event Owner / Host permission
      ↓
Assignment permission
      ↓
Accommodation / Transport operation

Support the existing AFCON360 roles/permissions rather than creating an unrelated permission framework.

At minimum, distinguish:

Can view attendees
Can assign accommodation
Can assign transport
Can change assignments
Can cancel assignments

where practical.

16. Database Design

First inspect the existing SQLAlchemy models and relationships.

Then design the minimum number of new fields/tables required.

Potential concepts include:

EventAttendee
AccommodationAssignment
TransportAssignment

but reuse equivalent existing models where possible.

Every relationship must have:

proper foreign keys,
indexes where appropriate,
uniqueness rules,
check constraints where appropriate,
cascade behavior explicitly considered,
created/updated timestamps where project conventions use them,
audit information where required.

Do not use free-text fields for relationships that should be foreign keys.

For example, avoid:

hotel_name
room_number
driver_name
vehicle_registration

when the actual entities already exist.

17. Prevent Duplicate Assignments

The database must help enforce domain integrity.

Examples:

An attendee should not have two active accommodation assignments for the same stay.

A room/unit should not be assigned beyond its permitted occupancy.

A driver should not receive conflicting assignments when the transport domain prohibits it.

A vehicle should not be oversubscribed.

Use database-level uniqueness/check constraints where appropriate and application-level validation where the rule requires more complex logic.

18. Transaction Safety

Accommodation and transport assignments are operationally important.

Use proper database transactions.

A request such as:

Assign attendee → room

must either:

succeed completely

or

fail without leaving partial state

Use the project's existing SQLAlchemy transaction pattern.

Handle race conditions where two authorized users try to assign the same remaining capacity at the same time.

Do not assume frontend checks are sufficient.

19. Services Layer

Do not put complex assignment logic directly into Flask routes.

Create/reuse domain services.

Conceptually:

AccommodationAssignmentService
TransportAssignmentService
EventGuestCoordinationService

Use the existing service architecture if one already exists.

The Event service should coordinate domains but must not take ownership away from Accommodation or Transport.

For example:

EventGuestCoordinationService
        |
        +---- Accommodation service
        |
        +---- Transport service

not:

Event module directly manipulates all accommodation tables
20. Routes

Inspect the existing event blueprint and add routes according to its existing conventions.

Possible route structure:

/events/<event_id>/attendees
/events/<event_id>/attendees/<attendee_id>

/events/<event_id>/attendees/<attendee_id>/accommodation
/events/<event_id>/attendees/<attendee_id>/transport

/events/<event_id>/accommodation
/events/<event_id>/transport

These are examples only.

Use the existing project's URL structure and blueprint organization.

Support:

GET views
POST assignment actions
PUT/PATCH where project architecture uses APIs
DELETE/cancel where appropriate

Do not duplicate API and HTML logic unnecessarily.

21. Templates

Implement complete templates using the existing AFCON360 design system.

Do not create visually disconnected pages.

The Event Host should have an attendee management page containing:

EVENT
────────────────────────────────

Event Name
Event Date
Venue

ATTENDEES

Total: 100
Assigned Accommodation: 72
Unassigned Accommodation: 28
Transport Assigned: 64
Transport Unassigned: 36

Then a table/grid:

[ ] Guest
    Registration
    Accommodation
    Transport
    Status
    Actions

Provide useful filters:

All
Accommodation Assigned
Accommodation Unassigned
Transport Assigned
Transport Unassigned
Both Assigned
Needs Attention
22. Accommodation Assignment UI

Provide a dedicated assignment interface.

The host should be able to select:

Guest
    ↓
Property
    ↓
Booking / allocation
    ↓
Room type
    ↓
Room/unit

Show real-time availability information.

For example:

Hotel A
3 rooms available
8 remaining guest capacity

Hotel B
1 room available
2 remaining guest capacity

Hotel C
5 rooms available
11 remaining guest capacity

Do not display stale or fabricated availability values.

23. Transport Assignment UI

Provide a similar flow:

Guest
    ↓
Transport date/time
    ↓
Available provider
    ↓
Available driver
    ↓
Available vehicle
    ↓
Pickup
    ↓
Drop-off

Only show eligible options according to transport rules.

24. Bulk Assignment

Support efficient management of large events.

For 100+ attendees, do not force the host to repeat unnecessarily expensive operations.

Allow:

multi-select attendees,
bulk accommodation assignment where appropriate,
bulk transport assignment where appropriate,
filtering,
search,
sorting,
pagination.

However, bulk operations must individually validate capacity and eligibility.

One invalid guest should not silently corrupt the remaining assignments.

Return clear success/failure results.

Example:

Successfully assigned: 18

Failed: 2

Guest A
Reason: Room capacity exceeded

Guest B
Reason: Transport vehicle unavailable
25. Notifications

Integrate with the existing AFCON360 Unified Notification & Communication Platform.

Do not create another notification mechanism.

When an accommodation assignment is created or changed, trigger the appropriate existing notification workflow.

When transport is assigned, notify the appropriate party where the current notification architecture supports it.

Potential recipients include:

Guest
Booking Owner
Event Host
Transport Driver
Property / accommodation operator

Do not assume every recipient should receive every notification.

Use the existing notification preferences, templates, channels, and event framework.

26. Audit Trail

Every assignment/change should be auditable.

Record enough information to answer:

Who assigned this guest?
When?
What was assigned?
What was the previous assignment?
What was the new assignment?
Why was it changed, if reason capture exists?

Use the existing AFCON360 audit/event logging architecture where available.

Do not build a completely separate audit subsystem unless absolutely necessary.

27. Status Model

Avoid using random strings throughout the application.

Use the existing project conventions for statuses.

Conceptually, accommodation assignment may have:

UNASSIGNED
ASSIGNED
CANCELLED
REASSIGNING

Transport may have:

UNASSIGNED
ASSIGNED
CANCELLED
COMPLETED

Use project enums/constants where appropriate.

28. Security

Treat all assignment endpoints as protected operations.

Validate:

authentication,
authorization,
event ownership/host role,
CSRF for browser form operations where applicable,
object-level access,
input validation,
rate limiting where appropriate,
safe error handling.

Never trust:

event_id
attendee_id
room_id
booking_id
driver_id
vehicle_id

supplied by the browser.

Always confirm that the object belongs to the permitted domain/context.

For example, an event host must not be able to modify:

another event's attendee
another property's booking
another company's driver

merely by changing an ID in the URL.

29. Module Independence

Respect AFCON360's modular architecture.

If Accommodation or Transport is disabled, the rest of AFCON360 must continue functioning according to the existing module-toggle architecture.

The Event module should degrade gracefully.

For example:

Accommodation disabled
    ↓
Event still works
    ↓
Guest registration still works
    ↓
Accommodation assignment UI reports:
"Accommodation service is currently unavailable."

Do not cause application-wide startup or runtime failures because a dependent module is disabled.

Likewise:

Transport disabled
    ↓
Event still works
    ↓
Transport assignment becomes unavailable

Use the existing centralized module settings/configuration and database-backed source-of-truth mechanisms.

30. Notifications and Disabled Services

Do not enqueue jobs against unavailable modules blindly.

Check the existing module service state before invoking dependent functionality.

For example:

Accommodation assignment
        ↓
Check Accommodation module
        ↓
Enabled?
   ├── Yes → perform operation
   └── No  → return controlled unavailable state
31. Database Migration

Create proper Alembic migration(s).

Do not modify production schema manually.

The migration must:

create required tables,
add indexes,
add foreign keys,
add uniqueness constraints,
add check constraints where necessary,
handle existing data safely,
be reversible where the project's migration policy requires it.

Run:

upgrade
downgrade
upgrade

in a safe test environment.

32. Existing Data Compatibility

Inspect the current production/development schema before changing it.

Do not assume the database is empty.

Identify:

existing events,
attendees,
accommodation bookings,
room/unit records,
transport records,
users,
roles,
permissions.

The feature must not break existing records.

33. API / JSON Endpoints

If AFCON360 already exposes JSON APIs for its modules, implement the integration consistently.

Possible responses should include structured information such as:

{
  "success": true,
  "assignment_id": "...",
  "attendee_id": "...",
  "status": "assigned"
}

For failures:

{
  "success": false,
  "error": "ROOM_CAPACITY_EXCEEDED",
  "message": "The selected room has no remaining guest capacity."
}

Use the project's existing response conventions.

Do not introduce a second response format.

34. Frontend JavaScript / Static Assets

Inspect the current event/accommodation static architecture.

Implement JavaScript only where required for:

filtering,
dynamic selection,
availability refresh,
bulk assignment,
modal/dialog handling,
confirmation,
asynchronous assignment requests.

Keep business logic on the backend.

The browser must never be the authority for:

room capacity,
availability,
driver availability,
vehicle capacity,
authorization.
35. Testing Requirements

Do not consider this feature complete until automated tests exist.

At minimum test:

Event authorization
authorized Event Owner can manage attendees,
unauthorized user cannot,
host from another event cannot access the event's attendees.
Accommodation
valid room assignment succeeds,
invalid room fails,
room capacity is enforced,
duplicate assignment is prevented,
wrong booking/event context is rejected,
multiple hotels work,
reassignment works,
cancellation works.
Transport
valid driver/vehicle assignment succeeds,
unapproved driver fails,
unavailable vehicle fails,
capacity is enforced,
conflicting assignment is rejected.
Integration
accommodation assignment appears on attendee record,
transport assignment appears on attendee record,
event dashboard counts update correctly,
notifications are triggered correctly,
audit record is created.
Module states
Event works with Accommodation disabled,
Event works with Transport disabled,
disabled services do not crash the application.
36. Static Analysis and Code Quality

Run the project's normal:

tests
lint
type checks
migration checks

where available.

Check for:

circular imports,
N+1 queries,
missing indexes,
missing eager loading,
transaction problems,
authorization bypasses,
inconsistent naming,
duplicated service logic,
dead code.
37. Performance

The event host may manage:

100
500
1,000+

attendees.

Do not load all related hotel, room, driver, vehicle, and booking objects blindly for every attendee.

Use appropriate:

joins,
eager loading,
pagination,
filtering,
indexed queries.

Avoid N+1 query patterns.

38. User Experience

The host should be able to understand immediately:

How many attendees are registered?
How many have accommodation?
How many still need rooms?
How many have transport?
How many still need transport?
What hotels are being used?
Which rooms are assigned?
Which drivers are assigned?
What requires attention?

Make the feature operationally useful, not merely technically connected.

39. Example End-to-End Workflow

Implement this scenario successfully.

Step 1 — Create Event
Event:
AFCON Executive Conference

Host:
John Doe
Step 2 — Register Attendees
100 attendees registered
Step 3 — Accommodation

Existing accommodation bookings include:

Hotel A
40 rooms

Hotel B
35 rooms

Hotel C
25 rooms

The host can use the existing legitimate accommodation booking/allocation records.

Step 4 — Assign Guests

Example:

Guest 001 → Hotel A / Room 101
Guest 002 → Hotel A / Room 102
Guest 003 → Hotel B / Room 201
Guest 004 → Hotel C / Room 301
Step 5 — Validate

The system checks:

room exists
booking valid
dates valid
capacity available
not already occupied beyond limit
event host authorized
Step 6 — Transport

The host assigns:

Guest 001
→ Driver John
→ Vehicle UAA 123A
→ Pickup Entebbe Airport
→ Drop-off Hotel A
Step 7 — Notification

The appropriate existing notification workflows are triggered.

Step 8 — Dashboard

The event now shows:

Attendees                100
Accommodation Assigned    96
Accommodation Pending      4
Transport Assigned        82
Transport Pending         18

These figures must be calculated from actual assignments.

40. Important: Do Not Invent Architecture

Before writing code:

Inspect the existing Events module.
Inspect the Accommodation module.
Inspect the Transport module.
Inspect Identity/Auth/roles.
Inspect Notification services.
Inspect existing booking ownership models.
Inspect existing database constraints.
Inspect module enable/disable architecture.
Inspect existing templates and static assets.
Identify existing services that can be reused.

Then produce a concise implementation map.

Do not immediately start creating models.

41. Required Investigation Before Modification

Search the project for concepts such as:

Event
EventHost
EventOwner
EventRegistration
Attendee
Guest
Booking
Reservation
Accommodation
RoomType
Room
Unit
Occupancy
Property
Transport
Driver
Vehicle
Trip
Assignment
Notification
Permission
Role
Audit
Module
Settings

Also inspect:

app/
models/
services/
events/
accommodation/
transport/
templates/
static/
migrations/
tests/

Use the actual repository structure rather than assuming these exact paths exist.

42. Deliverables

When implementation is complete, provide a technical summary containing:

A. Files changed

List every created/modified file.

B. Database changes

Explain:

new tables,
new columns,
constraints,
indexes,
foreign keys,
migrations.
C. Domain relationships

Show:

Event
 ↓
Attendee
 ↓
Accommodation Assignment
 ↓
Existing Accommodation Booking / Allocation

and:

Event
 ↓
Attendee
 ↓
Transport Assignment
 ↓
Existing Transport Booking / Driver / Vehicle
D. Routes

List all new/changed routes.

E. Templates

List all new/changed templates.

F. Services

List all new/changed services.

G. Authorization

Explain who can perform each operation.

H. Notifications

Explain what events trigger notifications.

I. Tests

List the tests added and their results.

J. Migration

State the migration revision and whether upgrade/downgrade was tested.

43. Implementation Rules

Follow these rules strictly:

DO NOT create a parallel accommodation system.

DO NOT create a parallel transport system.

DO NOT duplicate users, drivers, vehicles, rooms, or bookings.

DO NOT store room capacity independently inside Event.

DO NOT bypass accommodation availability/occupancy logic.

DO NOT bypass transport eligibility/availability logic.

DO NOT allow unauthorized event hosts to manipulate unrelated bookings.

DO NOT put complex business logic directly into Flask routes.

DO NOT trust browser-supplied IDs.

DO NOT rely only on frontend validation.

DO NOT break the app when Accommodation or Transport is disabled.

DO NOT hard-code availability.

DO NOT skip migrations.

DO NOT skip tests.

DO NOT overwrite or silently redesign existing domain logic.

Instead:

REUSE existing domain models.

REUSE existing services.

REUSE existing authorization.

REUSE existing notifications.

REUSE existing booking ownership.

REUSE existing module enable/disable architecture.

ADD only the missing integration layer.

KEEP each domain authoritative over its own data.
44. Final Architectural Goal

The resulting AFCON360 architecture should conceptually look like:

                         AFCON360
                            |
                     +------+------+
                     |             |
                   EVENTS        OTHER MODULES
                     |
              Event Owner / Host
                     |
              Event Attendees
                     |
          +----------+-----------+
          |                      |
          v                      v
  Accommodation             Transport
  Coordination              Coordination
          |                      |
          v                      v
 Existing Accommodation     Existing Transport
 Booking/Inventory/         Provider/Driver/
 Occupancy/Units            Vehicle/Trip logic
          |                      |
          +----------+-----------+
                     |
                 Notifications
                     |
                   Audit

The key architectural principle is:

Events coordinates people; Accommodation owns accommodation; Transport owns transport; Identity owns identity; Notifications owns communication; each domain remains the authoritative source for its own data.

Implement the missing connections between these domains so that an Event Host can operationally manage the entire attendee journey without creating a second source of truth.

45. Execution Mode

Work incrementally and safely.

Phase 1

Inspect and map the existing implementation.

Phase 2

Design the integration and identify the minimum schema changes.

Phase 3

Implement models and migration.

Phase 4

Implement domain services.

Phase 5

Implement authorization.

Phase 6

Implement routes/API endpoints.

Phase 7

Implement templates and static behavior.

Phase 8

Integrate notifications and audit logging.

Phase 9

Add automated tests.

Phase 10

Run the application and test the complete workflow end-to-end.

At every phase, preserve existing functionality.

Before modifying an existing model or service, explain briefly why the change is required and reuse the existing pattern whenever possible.

Do not make speculative architectural rewrites.

The objective is a production-quality AFCON360 Event Host Guest Coordination workflow fully integrated with the existing Accommodation and Transport systems.

#=================================

