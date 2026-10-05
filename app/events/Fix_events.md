
Master Issue Register — app/events/
Purpose: the single document you hand to the PyCharm agent, one item at a time, with a verification step and a report back. Nothing in this document is executed by me.

Reading order for you:

§0 — how to use this with the agent (short).

§1 — Priority Track A: unify "event" as one concept (football = concert = conference).

§2 — Priority Track B: notifications boundary ("notify should notify").

§3 — Priority Track C: retire Flask signals in the events domain (close it forever).

§4 — Master register of everything else, categorised A–N.

§5 — Signal usage map (input for Track C).

§6 — Report template the agent returns per item.

No code, no drafts, no execution. Just the register.

§0 How to use this with the agent
Per item, do this cycle:

Copy the item's ID + Fix + Verification into the agent prompt.

Add: "Do not modify files outside the listed scope. Return the report in the §6 template. Do not commit."

The agent proposes a diff. You review.

Run the Verification step yourself.

If green, mark Done; if red, feed the failure back to the agent with the report template again.

One item at a time. Never batch items from different sections in the same agent turn — the report becomes unverifiable.

Recommended tooling conventions for the agent:

git grep over git ls-files for reference sweeps (never read uncommitted files).

Every rename or move: git mv only.

Every behaviour change: must be preceded by a test that fails before and passes after.

§1 Priority Track A — Unify "event" as one concept
Goal: there is exactly one meaning of "event" in the events module — a real-world gathering (match, concert, conference, tournament, festival, boxing card, rugby Test). Football is a category. Nothing in the code, docs, or copy treats football as a sibling domain.

A-1 — Correct the handoff report and any docs calling this the "football domain"
Severity: P2 · Effort: S · Depends on: —

Where: HANDOFF REPORT — Events Folder Identity & Restructure.txt (§1, §2.2, §2.4, §10); any *.md under app/events/ that says "football" or "AFCON".

Problem: the handoff calls app/events/ "the football / AFCON business domain". That framing is inherited by every downstream session and is the origin of the confusion.

Fix: replace "football / AFCON business domain" with "real-world events domain (matches, concerts, conferences, tournaments, festivals — football is one category)". Update the §2.2 diagram labels.

Verification: git grep -i "football\|afcon business" returns matches only in ADRs or historical transcripts explicitly marked as such.

Agent prompt: "Find every doc/comment in the repo that describes app/events/ as football/AFCON. Rewrite to 'real-world events domain' with examples across categories. Do not change code."

A-2 — Remove "football / AFCON / match" language from app/events/ source
Severity: P2 · Effort: S · Depends on: A-1

Where: docstrings, comments, and copy across app/events/**; also app/notifications/events/policy.py welcome copy.

Problem: module-level docstrings and user-facing strings imply a football-specific product.

Fix: neutralise language. User-facing copy that says "events" as a category must be reworded to be category-agnostic or templated from the event's own category.

Verification: git grep -i "football\|afcon\|match" under app/events/** returns only legitimate uses (e.g. a category enum value, an explicit example in a docstring labelled as an example).

Agent prompt: "Sweep app/events/** for football/AFCON/match language. Report every hit with file:line and a suggested neutral rewording. Do not edit yet — return the report first."

A-3 — Decide and record: does the events domain need an EventSession sub-entity?
Severity: P1 · Effort: S (decision) + M (implementation) · Depends on: —

Where: app/events/models.py::Event; also any AFCON-specific fixture I haven't seen.

Problem: the current model has one start_date, one end_date, one venue, one city. That works for a concert and a single-day conference. It does not represent a tournament (AFCON, World Cup) with multiple fixtures across venues, a festival with parallel stages, or a boxing card with multiple bouts. Removing the "football" assumption exposes this.

Fix: first, decide whether the model needs an EventSession / EventProgramme child entity (with start_at, end_at, venue, city, optional TicketType scoping). Record the decision as an ADR. If yes, implement incrementally: model → migration → service → routes.

Verification: ADR exists and names one of: (a) "EventSession added" with the migration path, or (b) "single-venue-single-date is a hard constraint" with the reasoning.

Agent prompt: "Read app/events/models.py::Event. Produce an ADR recommending whether to add an EventSession sub-entity. Enumerate the event types in the codebase it must cover (concert, conference, tournament, festival, boxing card, single match, multi-day conference). Do not write code."

A-4 — Make Event.category a data-driven taxonomy
Severity: P2 · Effort: M · Depends on: A-3

Where: app/events/models.py::Event.category — currently String(50) with default "general".

Problem: for a platform covering every kind of event, a free-text string is not a taxonomy. Different code paths already use "general" and "other" inconsistently.

Fix: introduce an EventCategory reference table (or a validated enum backed by a table), with a data migration to backfill existing rows. Make the create/edit form read from it.

Verification: git grep "category='general'\|category = 'general'" returns zero matches. A DB query shows every non-null events.category maps to a row in the new taxonomy.

Agent prompt: "Propose a data migration and code plan to replace Event.category free-text with a data-driven taxonomy. Include the backfill rule for 'general' and 'other'. Do not implement."

A-5 — Confirm domain event types are category-neutral
Severity: P2 · Effort: S · Depends on: —

Where: app/notifications/events/registry.py::_bootstrap_registry — all EventType.* constants.

Problem: the registry declares event.registered, event.cancelled, etc. These look generic, but the check has not been done. If any event type encodes a football-specific concept, the platform layer is again aware of a category.

Fix: review every event type and every policy binding. Confirm each applies across all event categories. Rename any that don't.

Verification: a one-page table in the ADR listing each event type and the categories it applies to — every row must be "all categories".

Agent prompt: "Read app/notifications/events/registry.py and app/notifications/events/policy.py. Report any event type that assumes a specific category (football, match, AFCON). Return a table; do not edit."

A-6 — Move football-domain event types out of the platform registry
Severity: P2 · Effort: M · Depends on: A-5

Where: app/notifications/events/registry.py::_bootstrap_registry (event., accommodation.guest_, transport.passenger_* definitions); app/notifications/events/policy.py::_bootstrap_policies (event.* policies).

Problem: the platform layer declares the events domain's event types and notification policies. The platform must not know which domains exist.

Fix: create app/events/events_registry.py and app/events/events_policies.py. The events module imports them at package load time and calls register_event(...) / policy_engine.register(...) itself. The platform registry becomes a pure mechanism.

Verification: git grep "event.registered\|event.cancelled" app/notifications/events/ returns zero matches.

Agent prompt: "Extract every events-domain event type and policy from app/notifications/events/{registry,policy}.py into new files under app/events/. Keep the platform layer domain-agnostic. Return the diff; do not commit."

A-7 — Fold app/event_accommodation/ into app/events/accommodation/
Severity: P1 · Effort: M · Depends on: —

Where: app/event_accommodation/ — models (EventBadge, EventAccommodationOpportunity, EventVisibility), services (BadgeService, DiscoveryService, InvitationService, MatchingService), __init__.py.

Problem: a fourth top-level "event_*" folder. Its models FK to events.id. It belongs to the events domain.

Fix: git mv app/event_accommodation app/events/accommodation. Update imports. Keep table names unchanged, so no migration is needed. Update app/core/model_registry.py.

Verification: app boots; alembic check reports no schema drift; event badge issuance still works end-to-end.

Agent prompt: "git mv app/event_accommodation to app/events/accommodation. Sweep imports. Update app/core/model_registry.py. Do not rename tables. Return the full file list changed."

A-8 — Move football-domain models out of models.py when split happens
Severity: P3 · Effort: S · Depends on: §4 A-3 (models split)

Where: app/events/models.py::OrganizerProfile, OrganizerMessage, EventHostRegistration, EventGroup, EventGroupMember — all legitimate events-domain models, but should be grouped under a coach/business subpackage when the split happens.

Fix: during the model split, place coach/community/group entities under domain/models/community/.

Verification: import graph shows no top-level ordering assumptions broken.

Agent prompt: "When splitting models.py, group Organizer*, EventHost*, EventGroup* under a community subpackage. Preserve __init__ re-exports."

§2 Priority Track B — Notifications boundary ("notify should notify")
Goal: notifications deliver messages. They do not own domain logic, event types, or policies for other domains. Every notification originating from events goes through the events domain's published notification policy.

B-1 — Remove football-domain policies from the platform policy engine
Severity: P2 · Effort: M · Depends on: A-6 (same extraction)

Where: app/notifications/events/policy.py::_bootstrap_policies — 40+ policies for EVENT_*, KYC_*, BOOKING_*, PROPERTY_*, TRANSPORT_*, GUEST_*, PASSENGER_*, WALLET_*.

Problem: the platform layer contains the notification policy of every business domain. That is a coupling and a governance problem.

Fix: split _bootstrap_policies() by owning domain. Each domain registers its own policies from its own module. Platform ships only cross-cutting defaults (system announcements).

Verification: git grep "EventType.EVENT_\|EventType.BOOKING_" app/notifications/events/policy.py returns zero. Each domain's *_policies.py registers on import.

Agent prompt: "Split _bootstrap_policies() by domain. Create app/events/events_policies.py, app/wallet/wallet_policies.py, app/accommodation/accommodation_policies.py, app/transport/transport_policies.py. Platform ships only system-wide defaults."

B-2 — Route every events notification through the policy engine
Severity: P1 · Effort: M · Depends on: B-1

Where: direct NotificationService.send(...) call sites inside app/events/:

app/events/accommodation_bridge.py::_email_invite

app/events/guest_management.py::_send_guest_notification

app/events/routes.py::contact_organizer

app/events/routes.py::update_staff / remove_staff

app/events/tasks.py::process_event_registration

Problem: five different code paths deliver notifications outside the policy engine. Preferences, mandatory/optional classification, and channel routing are bypassed.

Fix: each call site either (a) emits a domain event that a registered policy resolves, or (b) is explicitly documented as an exception in app/events/docs/README.md with a reason.

Verification: every remaining direct NotificationService.send inside app/events/ is listed in the README as a documented exception.

Agent prompt: "Enumerate every NotificationService.send and EmailHandler.deliver call in app/events/**. For each, propose (a) an event-emit replacement or (b) a documented exception. Return the table; do not edit yet."

B-3 — Stop sending raw HTML emails from tasks.py
Severity: P1 · Effort: M · Depends on: B-2

Where: app/events/tasks.py::process_event_registration builds inline HTML and calls EmailHandler.deliver(...).

Problem: (i) escapes the policy engine and preferences, (ii) duplicates template logic, (iii) makes rebranding/localisation a code change.

Fix: emit EventType.EVENT_REGISTERED. Let the policy engine resolve the notification; use templates under templates/email/events/.

Verification: git grep "EmailHandler().deliver" app/events/ returns zero.

Agent prompt: "Replace inline EmailHandler().deliver(...) in app/events/tasks.py with emit_event(EventType.EVENT_REGISTERED, ...). Add the corresponding policy in app/events/events_policies.py."

B-4 — Fix guest_management.py hardcoded notification type
Severity: P2 · Effort: S · Depends on: B-2

Where: app/events/guest_management.py::_send_guest_notification uses notification_type='system_alert'.

Problem: loses specificity; the policy engine cannot distinguish guest notifications from system alerts.

Fix: add NotificationType.EVENT_GUEST_NOTIFIED (or the appropriate type) to the notification enum and use it.

Verification: git grep "notification_type='system_alert'" app/events/ returns zero.

Agent prompt: "Add a dedicated notification type for guest notifications and use it in _send_guest_notification."

B-5 — Unify the two notification contracts
Severity: P2 · Effort: M · Depends on: B-1, B-2

Where: app/events/models.py still declares NotificationType / NotificationChannel for older flows; app/notifications/models.py has its own. Confirm both resolve to the same enum.

Problem: two notification type enums in one codebase is exactly the sort of drift this refactor is meant to eliminate.

Fix: one enum, one module. All NotificationType.* and NotificationModule.* references resolve to app.notifications.models.

Verification: git grep "class NotificationType" app/ returns exactly one match.

Agent prompt: "Find all NotificationType, NotificationChannel, NotificationModule declarations. Report duplicates and propose consolidation."

B-6 — Document the events→notifications contract
Severity: P2 · Effort: S · Depends on: B-1..B-5

Where: app/events/docs/README.md (new).

Problem: no single place states how events notifies users.

Fix: one page: "The events module emits these domain events; the notifications module resolves them via these policies; these are the deliberate exceptions and why."

Verification: the page exists, lists every EVENT_* policy and every documented exception, and matches reality.

Agent prompt: "Draft app/events/docs/NOTIFICATIONS_CONTRACT.md listing every events-originated notification, its trigger, its delivery class, and its channels."

§3 Priority Track C — Retire Flask signals in the events domain
Goal: the events domain has exactly one pub/sub mechanism — the platform event backbone. Flask signals are used only for in-process, same-request, synchronous side effects, and even then only where there is a documented reason.

C-1 — Audit every Flask signal usage
Severity: P0 · Effort: S · Depends on: —

Where: app/events/signals.py, app/events/signal_handlers.py, plus every .send(...) call site.

Problem: five signals declared; only one handler is connected inside the module (event_capacity_released). The others are either sent into the void or have external consumers the events module cannot see. Both are defects.

Fix: produce the signal usage map (see §5). Classify each signal as:

(K) keep in-process — synchronous, same-request, no durability needed;

(P) promote to platform event — durable, cross-process, cross-module;

(D) delete — no consumer, no future use.

Verification: the map in §5 is filled in and signed off by you.

Agent prompt: "For each of the 5 signals in app/events/signal_handlers.py: report all .send() call sites in the repo and all .connect() call sites in the repo. Return the table; do not edit."

C-2 — Retire event_registered signal in favour of EventType.EVENT_REGISTERED
Severity: P1 · Effort: M · Depends on: C-1

Where: emitted in services.py::register_for_event_with_payment and services.py::_register_for_event_pessimistic. No in-module consumer.

Problem: duplicate mechanism with the platform event (EventType.EVENT_REGISTERED also exists). Cross-module consumers cannot rely on an in-process signal they cannot see.

Fix: remove the .send() calls. Ensure the corresponding emit_event(EventType.EVENT_REGISTERED, ...) is present at the same point in the flow.

Verification: git grep "event_registered.send" returns zero. A registration still produces a DomainEvent row and any notifications still fire.

Agent prompt: "Replace event_registered.send(...) calls with emit_event(EventType.EVENT_REGISTERED, ...). Confirm no listener in the repo depends on the signal first; return the listener list."

C-3 — Retire event_cancelled signal
Severity: P1 · Effort: S · Depends on: C-1

Where: declared in signal_handlers.py. Emission site needs to be confirmed (not present in the files I read — either dead or emitted from a module I haven't seen).

Problem: same as C-2, plus uncertain producer.

Fix: if unused, delete. If used, promote to EventType.EVENT_CANCELLED.

Verification: git grep "event_cancelled" returns only EventType.EVENT_CANCELLED references.

Agent prompt: "Locate every producer and consumer of the event_cancelled signal. Report; propose deletion or promotion."

C-4 — Retire offer_services_after_registration signal
Severity: P1 · Effort: S · Depends on: C-1

Where: emitted in services.py::_register_for_event_pessimistic. Consumer unknown.

Problem: no visible consumer. If cross-module, it must be a platform event.

Fix: promote to a domain event (EventType.EVENT_UPSELL_OFFERED or similar) or delete.

Verification: git grep "offer_services_after_registration" returns only the promoted event name.

Agent prompt: "Locate every consumer of offer_services_after_registration. Report; propose promotion or deletion."

C-5 — Decide service_provider_data_requested fate
Severity: P2 · Effort: S · Depends on: C-1

Where: sent and received inline in services.py::get_service_provider_dashboard_data. The receiver is created and disconnected inside the same function.

Problem: a signal used as a synchronous same-request event bus to gather data from other modules. It works, but it is a hidden cross-module coupling and cannot be observed.

Fix: replace with a direct call through a contract (accommodation_provider_bridge.get_dashboard_data(user_id) and the transport equivalent).

Verification: the signal is gone; the dashboard still renders the same data.

Agent prompt: "Replace the inline signal-based provider data collection in get_service_provider_dashboard_data with direct contract calls. Report which modules must expose a get_dashboard_data method."

C-6 — Keep event_capacity_released but consider promoting
Severity: P2 · Effort: M · Depends on: C-1

Where: signal_handlers.py::handle_capacity_released; emitted in tasks.py::expire_pending_registrations.

Problem: the only signal with an in-module handler. It is synchronous inside the reaper task and updates the same ticket pool. That is fine, but it duplicates the EventType.EVENT_CAPACITY_RELEASED event type that also exists.

Fix: decide whether capacity release is an intra-module concern (keep signal) or a cross-module fact (promote). Whichever it is, delete the other mechanism.

Verification: only one mechanism remains; git grep "event_capacity_released" returns only the chosen representation.

Agent prompt: "Report every producer and consumer of event_capacity_released and of EventType.EVENT_CAPACITY_RELEASED. Propose which to keep."

C-7 — Delete signals.py re-export shim
Severity: P2 · Effort: S · Depends on: C-2..C-6

Where: app/events/signals.py — a 12-line re-export of signal_handlers.

Problem: two modules with the same symbols. Splits grep results and confuses readers.

Fix: delete once all callers import from the canonical location. Update any caller still using from app.events.signals import ....

Verification: git grep "app.events.signals" returns zero.

Agent prompt: "Delete app/events/signals.py after confirming no imports. Sweep app.events.signals imports."

C-8 — Delete connect_event_signal_handlers once Track C completes
Severity: P2 · Effort: S · Depends on: C-7

Where: app/events/signal_handlers.py::connect_event_signal_handlers, called from app/events/__init__.py::on_load.

Problem: the whole wiring exists only to connect the last surviving signal. Once the signal goes, so does the wiring.

Fix: delete handler, delete wiring block from __init__.py. Simplify the record_once block accordingly.

Verification: app/events/__init__.py no longer imports signal-handler wiring; app boots.

Agent prompt: "After Track C is done, remove the signal-handler wiring from app/events/__init__.py and delete signal_handlers.py."

C-9 — Write a CI guard against new Flask signals in the events domain
Severity: P1 · Effort: S · Depends on: C-1..C-8

Where: test suite.

Problem: without a guard, the pattern will regrow.

Fix: a test that scans app/events/** for from blinker import signal and signal(...) and fails if any are present.

Verification: the test exists and passes; adding a fake signal in a scratch branch makes it fail.

Agent prompt: "Write a pytest that fails if app/events/** imports or instantiates a Flask/Blinker signal. Return the test file only."

§4 Master register — remaining categories
Compact table. Columns: ID · Item · Sev · Effort · Depends on · Verification.

A — Structure & file layout
ID	Item	Sev	Effort	Dep	Verification
A-9	Introduce layered internal package (domain/ application/ infrastructure/ presentation/ accommodation/ docs/)	P1	L	—	New folders exist; __init__.py re-exports keep public API stable
A-10	Split services.py (136KB) into application/*_service.py	P1	L	A-9	No file in application/ > 500 LOC; all imports route via __init__
A-11	Split routes.py (135KB) by audience	P1	L	A-9	Each presentation file < 500 LOC
A-12	Split models.py (60KB) by aggregate	P1	M	A-9	Each domain/model file < 300 LOC
A-13	Move TicketHold from inventory.py to domain/models/	P2	S	A-12	Import graph updated
A-14	Retire payment_config.py shim once callers import from wallet	P3	S	—	git grep "app.events.payment_config" returns zero
A-15	Consolidate 12 markdown files into docs/README.md + docs/adr/	P3	M	A-9	app/events/*.md at top level returns zero
A-16	Confirm which Aider edits are live (phase1.md, start.md, events.md)	P2	S	—	Written confirmation of live vs superseded per edit
A-17	Decide EventService fate (façade vs retirement) and record as ADR	P1	S	—	ADR exists; referenced by A-10
B — Module boundaries & contracts
ID	Item	Sev	Effort	Dep	Verification
B-1	Stop importing accommodation models directly in events	P1	M	B-6	git grep "app.accommodation.models" app/events/ returns only bridge files
B-2	Stop importing transport models directly in events	P1	M	B-6	git grep "app.transport.models" app/events/ returns only bridge files
B-3	Remove write to AccommodationBooking.event_id from events	P0	S	B-1	git grep "acc_booking.event_id =" app/events/ returns zero
B-4	Stop importing BookingService directly	P1	M	B-1	git grep "accommodation.services.booking_service" app/events/ returns zero
B-5	Stop importing WalletService directly	P1	M	B-6	git grep "wallet.services.wallet_service" app/events/ returns zero
B-6	Create contracts.py per owning module	P1	M	—	Each module exposes one contracts file
B-7	CI import-graph test	P1	S	B-1..B-5	Adding a forbidden import fails CI
B-8	Fix search_properties stub in routes.py	P2	S	B-1	Route returns real properties
B-9	Remove direct AccommodationBookingPayment read	P2	S	B-1	git grep "AccommodationBookingPayment" app/events/ returns zero
B-10	Stop creating Property rows from community-host routes	P0	M	B-1	git grep "Property(" app/events/ returns zero
B-11	Document the ports rule in docs/ARCHITECTURE.md	P2	S	B-6	Rule is written and referenced by the CI test
C — Data model & persistence
ID	Item	Sev	Effort	Dep	Verification
C-1	Decide EventRegistration.attendee_user_id future	P2	M	—	Either column dropped with migration or feature shipped
C-2	Ticket inventory single source of truth	P1	M	—	Only inventory.py writes available_seats
C-3	Delete deprecated TicketType.reserve_seat/release_seat	P2	S	C-2	Methods gone; callers migrated
C-4	Decide dual soft-delete representation (is_deleted vs status == DELETED)	P2	M	—	One representation; ADR documents which
C-5	Decide organizer_id public-contact vs ownership fallback	P1	S	—	ADR fixes the semantic; _is_event_owner behaviour matches
C-6	Confirm EventGuest as canonical participant identity; backfill EventRegistration.guest_id	P1	M	—	Every registration row has guest_id populated
C-7	Classify EventAssignment cross-module refs (transitional vs canonical)	P1	S	—	Phase 1 spec updated
C-8	Add CHECK constraint on EventAssignment.status	P2	S	—	Migration adds constraint; invalid values rejected
C-9	Validate EventRole.permissions JSON	P2	M	—	Schema validator or permission-set table
C-10	Unify Event.status enum vs string representation	P1	M	—	Only EventStatus used in code; DB read path validated
C-11	Add CHECK constraints on EventRegistration.status and payment_status	P2	S	—	Migration adds; invalid values rejected
C-12	Move OrganizerProfile / OrganizerMessage under community/ subpackage	P3	S	A-12	Folder exists; imports updated
C-13	Centralise accommodation badge enum values	P2	S	A-7	Enum values defined once
C-14	Decide EventSession sub-entity	P1	S+M	A-3	ADR signed
C-15	Document single-venue/single-date assumption if C-14 says no	P2	S	C-14	Doc exists
C-16	Data-driven Event.category taxonomy	P2	M	A-4	Backfill complete; taxonomy table populated
C-17	Fix organisation_id typo in services.py::get_organizer_event_models	P0	S	—	Org events appear for org admins
D — Authorization & ownership
ID	Item	Sev	Effort	Dep	Verification
D-1	Complete Phase 4: eliminate organizer_id fallback	P2	L	C-5	_resolve_organiser_id deleted; tests pass
D-2	Remove local ALLOWED_TRANSITIONS in services.py	P1	S	—	Import from constants only
D-3	Rename/merge require_event_permission's transitions table	P2	S	D-2	One naming convention
D-4	Add approver-authorization check to approve_event_transfer	P0	M	—	Test: unauthorized user rejected
D-5	Enforce authorization in EventTransferRequest.approve	P1	S	D-4	Model method private or service-enforced
D-6	Fix moderate_action truthiness bug	P0	S	—	Test: unauthorized moderation attempt gets 403
D-7	Route all admin actions through change_event_status	P1	M	D-2	Every admin action writes EventModerationLog
D-8	Remove or redirect legacy approve_event route	P1	S	D-7	Route gone or delegates
D-9	Audit _is_coordination_authority permission grant	P1	S	—	Written review; scope confirmed
D-10	Merge EVENT_STAFF_ACTION_MAP and EVENT_STAFF_ROLE_PERMISSIONS	P2	S	—	One source of role→permission mapping
D-11	Verify Organisation.org_id field in resolve_user_roles	P1	S	—	Test: org admin correctly resolves
D-12	Fix EventStatus import in permissions.py (circular risk)	P1	S	C-10	Import from constants
D-13	Allow booker/organizer to cancel a registration	P2	S	—	Test: booker cancels third-party registration
D-14	Confirm creator 24h grace in can_delete_event	P3	S	—	ADR or code comment
D-15	Confirm EventRole uniqueness scope	P3	S	—	ADR or constraint adjusted
E — Transactions & state machine
ID	Item	Sev	Effort	Dep	Verification
E-1	Replace with_transaction isolation hack	P0	M	—	psycopg2-only code removed; tests pass
E-2	Narrow retry conditions in register_for_event_optimistic	P1	S	—	Only transient errors retried
E-3	Re-check permissions inside update_event	P2	S	D-1	Test: permission revoked mid-request → denied
E-4	Move cross-module write out of events	P1	S	B-3	Same as B-3
E-5	Add compensating record on failed refund	P1	M	—	Test: refund failure leaves an auditable record
E-6	Move discount increment to successful commit	P1	S	—	Test: failed registration does not consume discount
E-7	Consolidate commits in create_event	P2	M	A-10	One commit per request
E-8	Make event cancel → booking cancel transactional or explicitly tolerate	P1	M	B-1	Test: partial cancel path is well-defined
E-9	Emit event_capacity_released on direct cancellation	P2	S	—	Capacity return is consistent across paths
F — Concurrency & inventory
ID	Item	Sev	Effort	Dep	Verification
F-1	Choose one reservation API (decrement vs reserve_hold)	P1	M	—	Documented per use case
F-2	Audit reserve_capacity(commit=...) callers	P1	S	F-1	Every caller documents its commit boundary
F-3	Remove double read in _atomic_decrement	P3	S	—	Single read
F-4	Document unlimited-tier path in _atomic_decrement	P1	S	—	Explicit test for capacity == 0
F-5	Cache event lookup in sale_guard.py	P2	S	—	No DB read when global mode is open
F-6	Emergency cleanup for orphan TicketHold rows	P2	S	G-1	Fallback cleanup exists
F-7	Bulk assign: one transaction or documented per-item commit	P1	M	—	Behaviour explicit in docstring
F-8	Hard fail on event/booking date mismatch	P1	S	—	CoordinationError raised
F-9	Align ownership predicate across accommodation/transport resolvers	P2	S	—	Same predicate used
G — Celery & async
ID	Item	Sev	Effort	Dep	Verification
G-1	Consolidate Celery app onto app.celery_app	P0	M	—	One Celery instance
G-2	Route registration email via NotificationService	P1	M	B-3	Same as B-3
G-3	Fix with_for_update(nowait=True) + autoretry	P2	S	—	No spurious retries
G-4	Make waitlist auto-conversion atomic per entry	P1	M	—	Test: interrupted conversion leaves consistent state
G-5	release_expired_capacity must emit capacity-released event	P1	S	C-6	Signals/events fire consistently
G-6	Batch or short-commit expire_pending_registrations	P2	M	—	No long-running transaction
G-7	Task queue routing by criticality	P2	M	G-1	Payment/registration tasks on dedicated queue
G-8	Extend task idempotency beyond 1h TTL	P2	S	—	Duplicate redelivery is a no-op
G-9	Audit every @celery_app.task for timeouts and retries	P2	S	—	Every task has explicit limits
H — Signals & event publishing
ID	Item	Sev	Effort	Dep	Verification
H-1	Retire in-process signals for cross-module facts	P1	L	Track C	Only Track C-kept signals remain
H-2	Verify emitted signals have receivers	P1	S	C-1	Zero signals emitted without a receiver
H-3	Standardise on emit_event for cross-module facts	P2	S	C-2..C-4	Consistent pattern
H-4	Move events-domain event types out of platform registry	P2	M	A-6	Same as A-6
H-5	Move events-domain policies out of platform registry	P2	M	B-1	Same as B-1
H-6	Decide _email_invite path (policy vs direct)	P2	S	B-2	Documented
H-7	Fix hardcoded system_alert in guest_management	P2	S	B-4	Same as B-4
H-8	Confirm all event types are category-neutral	P2	S	A-5	Same as A-5
J — Security
ID	Item	Sev	Effort	Dep	Verification
J-1	Fix update_staff non-hash password	P0	S	—	Use register_user or mark inactive
J-2	Review @csrf.exempt on staff endpoints	P1	S	—	Written justification per endpoint
J-3	Wire or remove sanitize_html	P2	S	—	Either used or deleted
J-4	Confirm guest account unreachability is intended	P1	S	—	Documented in attendee_accounts.py
J-5	Confirm fail-closed forensic audit policy	P2	S	—	Documented
J-6	Verify webhook EventSubscription.secret is encrypted	P1	S	—	At-rest encryption confirmed
J-7	sale_guard write failure: fail-open vs fail-closed	P1	S	—	Explicit policy documented
K — Observability
ID	Item	Sev	Effort	Dep	Verification
K-1	Heartbeat metric from events tasks	P2	S	G-1	Heartbeat on every task
K-2	Per-event-type lag metric	P2	M	—	Metric emitted
K-3	Move analytics reads to read replica	P1	M	—	Primary not hit by metrics_service
K-4	Fix func.date() index-defeating queries	P2	S	K-3	Range queries or expression index
K-5	Counter for skipped rows in expire_pending_registrations	P2	S	—	Metric emitted
K-6	Structured transition logs in guest_coordination_service	P3	S	—	Machine-parseable log per transition
L — Tests
ID	Item	Sev	Effort	Dep	Verification
L-1	Windows cp1252 fixture fix confirmed not regressed	P1	S	—	Windows test run passes
L-2	Post-transfer stale-organizer denial test	P1	S	—	Test asserts denial
L-3	Contact-organizer recipient chain tests	P1	S	I-2	All three branches covered
L-4	can_manage_registration role matrix tests	P2	M	D-13	All roles covered
L-5	Admin routes produce EventModerationLog	P1	M	D-7	Every route covered
L-6	Refund-failure compensating record test	P1	M	E-5	Test asserts record written
L-7	Org event listing test	P0	S	C-17	Test asserts org events listed
L-8	resolve_user_roles org role test	P1	S	D-11	Test asserts roles resolved
L-9	reserve_capacity concurrency test	P1	M	F-1	Test asserts no overselling
M — Documentation
ID	Item	Sev	Effort	Dep	Verification
M-1	Consolidate 12 markdown files	P3	M	A-15	Same as A-15
M-2	Regenerate route inventory in README	P2	S	—	README matches actual routes
M-3	Reconcile README claim vs services.py reality	P2	S	A-10	README matches code
M-4	Convert assignment.py header into real module README	P2	S	A-9	README exists
M-5	Archive or delete Aider transcripts	P3	S	A-15	Transcripts moved or deleted
M-6	Correct "football domain" language in docs	P2	S	A-1	Same as A-1
N — Dead code & deprecations
ID	Item	Sev	Effort	Dep	Verification
N-1	Delete _register_for_event_pessimistic	P2	S	A-10	Method gone
N-2	Delete deprecated TicketType seat methods	P2	S	C-3	Same as C-3
N-3	Delete EventRegistration.registered_by property	P2	S	—	Property gone; callers migrated
N-4	Remove literal status strings ('active', 'pending')	P2	S	C-10	Only EventStatus used
N-5	Retire payment_config.py shim	P3	S	A-14	Same as A-14
N-6	Delete signals.py re-export	P2	S	C-7	Same as C-7
N-7	Confirm admin_deactivate → PAUSED semantic	P2	S	C-10	ADR or proper status added
N-8	Confirm canonical bulk upload file	P2	S	A-16	Only one file remains
N-9	Confirm canonical attendee identity	P1	S	C-6	Same as C-6
N-10	Review _ACTION_DISPATCH after D-7	P3	S	D-7	Table accurate
§5 Signal usage map (input for Track C)
Fill this in before starting Track C. Columns are set; the agent fills them.

Signal	Declared in	.send() call sites	.connect() call sites	Cross-module?	Durability needed?	Decision (K/P/D)
event_registered	signal_handlers.py	services.py::register_for_event_with_payment, services.py::_register_for_event_pessimistic	(none in module)	?	?	?
event_cancelled	signal_handlers.py	?	(none in module)	?	?	?
event_capacity_released	signal_handlers.py	tasks.py::expire_pending_registrations	signal_handlers.py::connect_event_signal_handlers	no	no	keep (intra-module)
offer_services_after_registration	signal_handlers.py	services.py::_register_for_event_pessimistic	(none in module)	likely yes	likely yes	promote or delete
service_provider_data_requested	signal_handlers.py	services.py::get_service_provider_dashboard_data	inline in same function	yes	no	replace with contract call
Decision legend: K = keep in-process; P = promote to platform event; D = delete.

The agent's first task on Track C is to fill the "?" cells.

§6 Report template the agent returns per item
Ask the agent to return exactly this shape for every item. It makes your verification mechanical.

text
ITEM: <ID>
STATUS: done | partial | blocked | needs-info
FILES TOUCHED: <git mv / edit / create / delete, one per line>
SUMMARY: <2–4 sentences>
DIFF STAT: <files changed, insertions, deletions>
COMMANDS RUN: <the exact shell commands, one per line>
COMMANDS OUTPUT: <verbatim, trimmed to the relevant lines>
TESTS: <tests added/modified, one per line>
VERIFICATION PERFORMED: <what the agent itself checked>
VERIFICATION STEP FOR REVIEWER: <one command the reviewer should run>
UNKNOWNS: <anything the agent could not confirm>
BLOCKERS: <anything preventing completion>
NEXT: <suggested next item ID or action>
Ask for it explicitly in every prompt. Do not accept a report that omits any field.

§7 Suggested starting order
Doing Track A, B, C first closes the "football vs concert" and "signals" questions permanently. The rest can be sequenced after.

C-1 — signal audit. (Pure read, produces the §5 map.)

A-1, A-2 — language corrections in docs and source.

A-3 — decision and ADR on EventSession.

A-5 — event type category-neutrality audit.

A-6 / B-1 — move events-domain event types and policies out of the platform layer.

C-2 … C-8 — retire the signals one by one, closing each with its verification.

C-9 — CI guard so signals never return.

B-2 … B-6 — route every events notification through the policy engine, document the contract.

A-4 / A-7 — category taxonomy and event_accommodation fold.

Then §4 categories by severity: P0s first (D-4, D-6, J-1, B-3, B-10, E-1, G-1, C-17, L-7), then P1s.

§8 Net counts
Track A (domain unification): 8 items (A-1 … A-8).

Track B (notifications boundary): 6 items (B-1 … B-6).

Track C (signals retirement): 9 items (C-1 … C-9).

Category A (structure): 9 items (A-9 … A-17).

Category B (contracts): 11 items (B-1 … B-11 — numbering reuses B-1..B-11 for contracts; distinguished by track vs category).

Category C (data model): 17 items.

Category D (authorization): 15 items.

Category E (transactions): 9 items.

Category F (concurrency): 9 items.

Category G (Celery): 9 items.

Category H (signals & publishing): 8 items.

Category J (security): 7 items.

Category K (observability): 6 items.

Category L (tests): 9 items.

Category M (docs): 6 items.

Category N (dead code): 10 items.

P0 short-list: 9 items (D-4, D-6, J-1, B-3, B-10, E-1, G-1, C-17, L-7).

That is the register. Nothing executed, nothing drafted, nothing renamed. Whenever you're ready, name the item and I will produce the specific verification recipe (exact shell commands, expected outputs, rollback steps) for that item alone.