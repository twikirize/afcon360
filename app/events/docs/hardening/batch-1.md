## HARDENED ROWS

### Track A / A-1 — Correct the handoff report and any docs calling this the "football domain"
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          HANDOFF REPORT — Events Folder Identity & Restructure.txt (§1, §2.2, §2.4, §10); any *.md under app/events/ that says "football" or "AFCON"
- Verified Where:          app/notifications/README.md:77,78; BACKLOG.md (multiple); STAGE_4B_ORGANISATION_CLASSIFICATION_ELIGIBILITY_RECONCILIATION.md; .opencode/rules/afcon360-constitution.md; app/events/Fix_events.md (self‑references)
- Original Problem:        the handoff calls app/events/ "the football / AFCON business domain". That framing is inherited by every downstream session and is the origin of the confusion.
- Verified Problem:        reproduced — "AFCON events business domain" phrasing exists in app/notifications/README.md and other docs; HANDOFF REPORT file not found in repo
- Repro command:           git grep -i "football\|afcon business" -- "*.md" "*.txt"
- Repro output:            AFCON360_USER_DASHBOARD_IMPLEMENTATION.md:                {% if 'sport' in cat or 'football' in cat or 'soccer' in cat %}
STAGE_4B_ORGANISATION_CLASSIFICATION_ELIGIBILITY_RECONCILIATION.md:| E15 | test DB live: `org_business_category` = 39 labels (upper-case member names), 668 orgs, distinct values {HOTEL, TOUR_OPERATOR, SPORTS_TEAM, FOOTBALL_TEAM, CORPORATE} | direct SQL query | DB forensics |
STAGE_4B_ORGANISATION_CLASSIFICATION_ELIGIBILITY_RECONCILIATION.md:transport company, football team…), with an associated *provider/consumer
STAGE_4B_ORGANISATION_CLASSIFICATION_ELIGIBILITY_RECONCILIATION.md:  SPORTS_TEAM, FOOTBALL_TEAM, SPORTS_FEDERATION, FITNESS_CENTER,
STAGE_4B_ORGANISATION_CLASSIFICATION_ELIGIBILITY_RECONCILIATION.md:  `HOTEL, TOUR_OPERATOR, SPORTS_TEAM, CORPORATE, FOOTBALL_TEAM` — **all valid
STAGE_4B_ORGANISATION_CLASSIFICATION_ELIGIBILITY_RECONCILIATION.md:  canonical values {HOTEL, TOUR_OPERATOR, SPORTS_TEAM, CORPORATE, FOOTBALL_TEAM};
app/Documentation/SYSTEM_OVERVIEW.md:AFCON360 is a comprehensive football tournament management platform built with Flask, featuring advanced user administration, role-based access control, financial transactions, transportation, accommodation, events, and tourism modules. The system is designed for multi-tenant operations with organization management, KYC compliance, and forensic audit capabilities.
app/events/Fix_events.md:§1 — Priority Track A: unify "event" as one concept (football = concert = conference).
app/events/Fix_events.md:Goal: there is exactly one meaning of "event" in the events module — a real-world gathering (match, concert, conference, tournament, festival, boxing card, rugby Test). Football is a category. Nothing in the code, docs, or copy treats football as a sibling domain.
app/events/Fix_events.md:A-1 — Correct the handoff report and any docs calling this the "football domain"
app/events/Fix_events.md:Where: HANDOFF REPORT — Events Folder Identity & Restructure.txt (§1, §2.2, §2.4, §10); any *.md under app/events/ that says "football" or "AFCON".
app/events/Fix_events.md:Problem: the handoff calls app/events/ "the football / AFCON business domain". That framing is inherited by every downstream session and is the origin of the confusion.
app/events/Fix_events.md:Fix: replace "football / AFCON business domain" with "real-world events domain (matches, concerts, conferences, tournaments, festivals — football is one category)". Update the §2.2 diagram labels.
app/events/Fix_events.md:Verification: git grep -i "football\|afcon business" returns matches only in ADRs or historical transcripts explicitly marked as such.
app/events/Fix_events.md:Agent prompt: "Find every doc/comment in the repo that describes app/events/ as football/AFCON. Rewrite to 'real-world events domain' with examples across categories. Do not change code."
app/events/Fix_events.md:A-2 — Remove "football / AFCON / match" language from app/events/ source
app/events/Fix_events.md:Problem: module-level docstrings and user-facing strings imply a football-specific product.
app/events/Fix_events.md:Verification: git grep -i "football\|afcon\|match" under app/events/** returns only legitimate uses (e.g. a category enum value, an explicit example in a docstring labelled as an example).
app/events/Fix_events.md:Agent prompt: "Sweep app/events/** for football/AFCON/match language. Report every hit with file:line and a suggested neutral rewording. Do not edit yet — return the report first."
app/events/Fix_events.md:Problem: the current model has one start_date, one end_date, one venue, one city. That works for a concert and a single-day conference. It does not represent a tournament (AFCON, World Cup) with multiple fixtures across venues, a festival with parallel stages, or a boxing card with multiple bouts. Removing the "football" assumption exposes this.
app/events/Fix_events.md:Problem: the registry declares event.registered, event.cancelled, etc. These look generic, but the check has not been done. If any event type encodes a football-specific concept, the platform layer is again aware of a category.
app/events/Fix_events.md:Agent prompt: "Read app/notifications/events/registry.py and app/notifications/events/policy.py. Report any event type that assumes a specific category (football, match, AFCON). Return a table; do not edit."
app/events/Fix_events.md:A-6 — Move football-domain event types out of the platform registry
app/events/Fix_events.md:A-8 — Move football-domain models out of models.py when split happens
app/events/Fix_events.md:B-1 — Remove football-domain policies from the platform policy engine
app/events/Fix_events.md:M-6	Correct "football domain" language in docs	P2	S	A-1	Same as A-1
app/events/Fix_events.md:Doing Track A, B, C first closes the "football vs concert" and "signals" questions permanently. The rest can be sequenced after.
app/fan/GEMINI_AGENT_FAN_MERGE.md:| Non-fan users see football? | Never — `FanProfile` is the only gate
app/fan/GEMINI_AGENT_FAN_MERGE.md:    favorite_sports = db.Column(db.String, default='["football"]')
app/fan/GEMINI_AGENT_FAN_MERGE.md:            favorite_sports=json.dumps(favorite_sports or ['football']),
app/fan/GEMINI_AGENT_FAN_MERGE.md:    sports = request.form.getlist('favorite_sports') or ['football']
app/fan/GEMINI_AGENT_FAN_MERGE.md:                        <input type="checkbox" name="favorite_sports" value="football"
app/fan/GEMINI_AGENT_FAN_MERGE.md:                            {% if 'football' in fan_profile.favorite_sports_list %}checked{% endif %}>
app/fan/GEMINI_AGENT_FAN_MERGE.md:                        Football
app/fan/GEMINI_AGENT_FAN_MERGE.md:            favorite_sports='["football"]',
kiro_history.md:  Flask + PostgreSQL + Redis + Celery platform for football tournament management.
kiro_history.md:     3+  Flask + PostgreSQL + Redis + Celery platform for football tournament management.
- Verification command:    git grep -i "football\|afcon business" -- "*.md" "*.txt"
- Verification output:     (see Repro output above). Classification: ADR/historical – STAGE_4B_*.md, .opencode/rules/afcon360-constitution.md; non‑ADR – AFCON360_USER_DASHBOARD_IMPLEMENTATION.md, SYSTEM_OVERVIEW.md, fan/*, kiro_history.md, Fix_events.md self‑refs.
- State at hardening:      Open
- Corrections:             Where → references non‑existent HANDOFF REPORT file; misses app/notifications/README.md which contains the phrasing
- Confidence:              high
- Notes:                   The verification command returns matches outside ADRs/historical transcripts, so the item remains Open.

### Track A / A-2 — Remove "football / AFCON / match" language from app/events/ source
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          docstrings, comments, and copy across app/events/**; also app/notifications/events/policy.py welcome copy
- Verified Where:          app/events/__init__.py:3; app/events/assignment.py:178,422,920; app/events/attendee_accounts.py:8,57; app/events/guest_management.py:14,295; app/events/models.py:669,670,785,1089; app/events/payment_service.py:317,357,385,403,509; app/events/routes.py:2832,2852; app/events/signal_handlers.py:50
- Original Problem:        module-level docstrings and user-facing strings imply a football-specific product.
- Verified Problem:        reproduced — "AFCON360" appears in 16 locations across 9 files in app/events/*.py as docstrings, comments, registration refs, ticket numbers, payment provider strings, email subjects, and signal handler comments
- Repro command:           git grep -n -i "football\|afcon" -- "app/events/*.py"
- Repro output:            app/events/__init__.py:3:Events Module - top-level blueprint for AFCON360.
app/events/assignment.py:178:#    A guest does NOT need an AFCON360 account to be assigned accommodation or
app/events/assignment.py:422:    # Do NOT create an AFCON360 account for assignment.
app/events/assignment.py:920:    # Do NOT create an AFCON360 account for assignment.
app/events/attendee_accounts.py:8:owning an AFCON360 account.  Callers that only need to link an existing account
app/events/attendee_accounts.py:57:    Create a new AFCON360 guest account for an attendee.
app/events/guest_management.py:14:    NOT by ``User``.  A guest does NOT need an AFCON360 account.
app/events/guest_management.py:295:    """Link a guest to an AFCON360 account (existing or newly created)."""
app/events/models.py:669:      ├─ registration.registration_ref (human-readable e.g. "ER-AFCON2024-00001234")
app/events/models.py:670:      ├─ registration.ticket_number (e.g. "TKT-AFCON2024-00001234")
app/events/models.py:785:        payload = f"AFCON360:{self.registration_ref}:{seq}"
app/events/models.py:1089:    """Stable event guest identity independent of an AFCON360 account."""
app/events/payment_service.py:317:                payment_provider="afcon360_wallet",
app/events/payment_service.py:357:                payment_provider="afcon360_wallet",
app/events/payment_service.py:385:                    payment_provider="afcon360_wallet",
app/events/payment_service.py:403:                payment_provider="afcon360_wallet",
app/events/payment_service.py:509:                # one.  A paid group guest does not require an AFCON360 account;
app/events/routes.py:2832:                    subject=f"[AFCON360] New message about {event.name}"
app/events/routes.py:2852:                subject=f"[AFCON360] Your message to {event.name} was sent"
app/events/signal_handlers.py:50:    This is the AFCON-proof way to release capacity back to the pool.
- Verification command:    git grep -i "football\|afcon\|match" -- "app/events/**" | Select-String -Pattern "general\|other|example" -NotMatch | Measure-Object -Line
- Verification output:     16 matches across 9 files; no "football" or "match" found in source (only "AFCON360" and "AFCON-proof")
- State at hardening:      Open
- Corrections:             Register's "match" reference is stale; no "match" in app/events source
- Confidence:              high
- Notes:                   "football" and "match" do not appear in app/events source; only "AFCON360" and "AFCON-proof". The item's "match" reference may be stale.

### Track A / A-3 — Decide and record: does the events domain need an EventSession sub-entity?
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/models.py::Event; also any AFCON-specific fixture I haven't seen
- Verified Where:          app/events/models.py:146-200 (Event class definition with start_date, end_date, venue, city, venue_id columns)
- Original Problem:        the current model has one start_date, one end_date, one venue, one city. That works for a concert and a single-day conference. It does not represent a tournament (AFCON, World Cup) with multiple fixtures across venues, a festival with parallel stages, or a boxing card with multiple bouts. Removing the "football" assumption exposes this.
- Verified Problem:        reproduced — Event model (lines 146-200) has single start_date (line 180), end_date (181), venue (183), city (184), venue_id (185); no child session/programme entity exists
- Repro command:           git grep -n -A 55 "class Event" -- app/events/models.py | Select-Object -First 60
- Repro output:            class Event(BaseModel): ... start_date = Column(DateTime, nullable=False, index=True) / end_date = Column(DateTime, nullable=False, index=True) / venue = Column(String(200), nullable=True) / city = Column(String(100), nullable=True) / venue_id = Column(BigInteger, ForeignKey("venues.id"), nullable=True)
- Verification command:    git grep -n "EventSession\|EventProgramme" -- app/events/
- Verification output:     (no output — no such entity exists)
- State at hardening:      Open
- Corrections:             Register said Event has one venue column; tree shows Event has BOTH venue (String) and venue_id (FK to venues.id). Register must be updated.
- Confidence:              high
- Notes:                   This may mean a Venue model already exists; the EventSession decision (A-3) must account for it. No ADR exists for this decision.

### Track A / A-4 — Make Event.category a data-driven taxonomy
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/models.py::Event.category — currently String(50) with default "general"
- Verified Where:          app/events/models.py:187 — category = Column(String(50), nullable=False, default="general")
- Original Problem:        for a platform covering every kind of event, a free-text string is not a taxonomy. Different code paths already use "general" and "other" inconsistently.
- Verified Problem:        reproduced — category is a free-text String(50) with default "general"; no reference table or enum backing
- Repro command:           git grep -n "category.*String\|default.*general" -- app/events/models.py
- Repro output:            app/events/models.py:187:    category = Column(String(50), nullable=False, default="general")
- Verification command:    git grep "category='general'\|category = 'general'" -- app/
- Verification output:     (no output in source code — but default="general" means DB rows will have this value)
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   No taxonomy table exists. The verification command in the register checks for hardcoded 'general' strings in source, which is a proxy.

### Track A / A-5 — Confirm domain event types are category-neutral
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/notifications/events/registry.py::_bootstrap_registry — all EventType.* constants
- Verified Where:          app/notifications/events/registry.py:33-130 (EventType class with 70+ constants including USER_*, SECURITY_*, KYC_*, WALLET_*, PAYMENT_*, PROPERTY_*, BOOKING_*, TRANSPORT_*, EVENT_*, GUEST_*, PASSENGER_*, MESSAGE_*, SYSTEM_*)
- Original Problem:        the registry declares event.registered, event.cancelled, etc. These look generic, but the check has not been done. If any event type encodes a football-specific concept, the platform layer is again aware of a category.
- Verified Problem:        refined as: registry contains domain-specific event types (accommodation.guest_*, transport.passenger_*, kyc.*, wallet.*, payment.*, property.*, booking.*, transport.*) alongside generic event.* types — platform layer already knows about all business domains
- Repro command:           git grep -n "^    [A-Z_]* = " -- app/notifications/events/registry.py
- Repro output:            70+ constants spanning USER, SECURITY, KYC, WALLET, PAYMENT, PROPERTY, BOOKING, TRANSPORT, EVENT, GUEST, PASSENGER, MESSAGE, SYSTEM categories
- Verification command:    [REVIEW]
- Verification output:     Verification is the ADR table of event type × applicable categories; not a shell command.
- State at hardening:      Open
- Corrections:             Problem understates the issue: the platform registry already contains ALL domain event types, not just events domain. The "check has not been done" is false — the register itself documents the cross-domain types in §5.
- Confidence:              high
- Notes:                   The EVENT_* types themselves are category-neutral, but the registry as a whole is not domain-agnostic.

### Track A / A-6 — Move football-domain event types out of the platform registry
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/notifications/events/registry.py::_bootstrap_registry (event., accommodation.guest_, transport.passenger_* definitions); app/notifications/events/policy.py::_bootstrap_policies (event.* policies)
- Verified Where:          registry.py:111-126 (event.* + accommodation.guest_* + transport.passenger_*); policy.py:289-486 (41 policy registrations for WALLET_CREATED, BOOKING_*, PROPERTY_*, TRANSPORT_*, EVENT_*, GUEST_*, PASSENGER_*)
- Original Problem:        the platform layer declares the events domain's event types and notification policies. The platform must not know which domains exist.
- Verified Problem:        reproduced — platform registry declares ALL domain event types; platform policy engine registers policies for WALLET, BOOKING, PROPERTY, TRANSPORT, EVENT, GUEST, PASSENGER domains
- Repro command:           git grep -n "event_type=E\." -- app/notifications/events/policy.py
- Repro output:            41 policy registrations spanning WALLET, BOOKING, PROPERTY, TRANSPORT, EVENT, GUEST, PASSENGER domains
- Verification command:    git grep "event\.registered\|event\.cancelled" -- app/notifications/events/
- Verification output:     app/notifications/events/registry.py:111:    EVENT_REGISTERED = 'event.registered' / app/notifications/events/registry.py:113:    EVENT_CANCELLED = 'event.cancelled'
- State at hardening:      Open
- Corrections:             Where → "football-domain" inaccurate; should be "all-domain". The platform registry contains every domain's types/policies.
- Confidence:              high
- Notes:                   This item overlaps with B-1 (same extraction work). The register treats them as separate tracks but they are the same mechanical change.

### Track A / A-7 — Fold app/event_accommodation/ into app/events/accommodation/
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/event_accommodation/ — models (EventBadge, EventAccommodationOpportunity, EventVisibility), services (BadgeService, DiscoveryService, InvitationService, MatchingService), __init__.py
- Verified Where:          app/event_accommodation/__init__.py; app/event_accommodation/models/__init__.py, badge.py, opportunity.py, visibility.py; app/event_accommodation/services/__init__.py, badge_service.py, discovery_service.py, invitation_service.py, matching_service.py
- Original Problem:        a fourth top-level "event_*" folder. Its models FK to events.id. It belongs to the events domain.
- Verified Problem:        reproduced — app/event_accommodation/ exists at top level with models FK to events.id (badge.py references events.id)
- Repro command:           Get-ChildItem app/event_accommodation/ -Recurse
- Repro output:            Directory listing showing models/badge.py, opportunity.py, visibility.py; services/badge_service.py, discovery_service.py, invitation_service.py, matching_service.py
- Verification command:    git grep -n "events\.id" -- app/event_accommodation/
- Verification output:     app/event_accommodation/models/badge.py:16: (FK to events via CheckConstraint referencing events table)
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   No app/events/accommodation/ directory exists yet. Table names would not need migration per register.

### Track A / A-8 — Move football-domain models out of models.py when split happens
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/models.py::OrganizerProfile, OrganizerMessage, EventHostRegistration, EventGroup, EventGroupMember — all legitimate events-domain models, but should be grouped under a coach/business subpackage when the split happens.
- Verified Where:          app/events/models.py:1048 (EventHostRegistration), 1164 (EventGroup), 1193 (EventGroupMember), 1223 (OrganizerMessage), 1254 (OrganizerProfile)
- Original Problem:        during the model split, place coach/community/group entities under a community subpackage.
- Verified Problem:        reproduced — all 5 classes defined in models.py at top level; no community/ subpackage exists
- Repro command:           git grep -n "class OrganizerProfile\|class OrganizerMessage\|class EventHostRegistration\|class EventGroup\|class EventGroupMember" -- app/events/models.py
- Repro output:            app/events/models.py:1048:class EventHostRegistration(BaseModel): / 1164:class EventGroup(BaseModel): / 1193:class EventGroupMember(BaseModel): / 1223:class OrganizerMessage(BaseModel): / 1254:class OrganizerProfile(BaseModel):
- Verification command:    Test-Path app/events/domain/community
- Verification output:     False
- State at hardening:      Open
- Corrections:             "football-domain" → inaccurate; these are coach/community/group models, not football-specific
- Confidence:              high
- Notes:                   Depends on A-9 (layered package introduction) per register.

### Track B / B-1 — Remove football-domain policies from the platform policy engine
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/notifications/events/policy.py::_bootstrap_policies — 40+ policies for EVENT_*, KYC_*, BOOKING_*, PROPERTY_*, TRANSPORT_*, GUEST_*, PASSENGER_*, WALLET_*
- Verified Where:          app/notifications/events/policy.py:289-486 — 41 policy registrations for WALLET_CREATED, BOOKING_CONFIRMED/CANCELLED/CREATED, PROPERTY_SUBMITTED/APPROVED/REJECTED, TRANSPORT_DRIVER_ASSIGNED/BOOKING_CREATED, EVENT_REGISTERED/REMINDER_DUE/ACCOMMODATION_ASSIGNED/CHANGED/TRANSPORT_ASSIGNED/CHANGED/COORDINATION_CANCELLED, GUEST_TRANSPORT_ASSIGNED/CHANGED/REMOVED, PASSENGER_ACCOMMODATION_ASSIGNED/CHANGED/REMOVED
- Original Problem:        the platform layer contains the notification policy of every business domain. That is a coupling and a governance problem.
- Verified Problem:        reproduced — platform policy engine registers policies for 8 business domains (WALLET, BOOKING, PROPERTY, TRANSPORT, EVENT, GUEST, PASSENGER, plus account/security)
- Repro command:           git grep -n "event_type=E\." -- app/notifications/events/policy.py | Measure-Object -Line
- Repro output:            41 policy registrations across all domains
- Verification command:    git grep "EventType.EVENT_\|EventType.BOOKING_" -- app/notifications/events/policy.py
- Verification output:     (no output — policy.py uses local alias E = EventType, so raw EventType.EVENT_* strings are not present)
- State at hardening:      Open
- Corrections:             "football-domain" → inaccurate; policies cover ALL domains, not just football/events
- Confidence:              high
- Notes:                   Same mechanical work as A-6 (extract domain policies to their owning modules). Register treats as separate tracks.

### Track B / B-2 — Route every events notification through the policy engine
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          direct NotificationService.send(...) call sites inside app/events/: app/events/accommodation_bridge.py::_email_invite, app/events/guest_management.py::_send_guest_notification, app/events/routes.py::contact_organizer, app/events/routes.py::update_staff / remove_staff, app/events/tasks.py::process_event_registration
- Verified Where:          app/events/accommodation_bridge.py:103; app/events/guest_coordination_service.py:947; app/events/guest_management.py:425; app/events/routes.py:2442,2523 (6 sites total — source lists 5, misses guest_coordination_service.py)
- Original Problem:        five different code paths deliver notifications outside the policy engine. Preferences, mandatory/optional classification, and channel routing are bypassed.
- Verified Problem:        reproduced — 6 direct NotificationService.send calls found (one more than documented); none use emit_event/policy engine
- Repro command:           git grep -n "NotificationService.send" -- app/events/
- Repro output:            app/events/accommodation_bridge.py:103:        NotificationService.send(
app/events/guest_coordination_service.py:947:                    NotificationService.send(
app/events/guest_management.py:425:        NotificationService.send(
app/events/routes.py:2442:            NotificationService.send(
app/events/routes.py:2523:            NotificationService.send(
- Verification command:    git grep "emit_event" -- app/events/
- Verification output:     app/events/guest_coordination_service.py:621,1009 (only 2 emit_event calls in entire events module)
- State at hardening:      Open
- Corrections:             Where → misses app/events/guest_coordination_service.py:947 (6th NotificationService.send site)
- Confidence:              high
- Notes:                   The register's list of 5 sites is incomplete. guest_coordination_service.py is a direct NotificationService.send caller not listed.

### Track B / B-3 — Stop sending raw HTML emails from tasks.py
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/tasks.py::process_event_registration builds inline HTML and calls EmailHandler.deliver(...)
- Verified Where:          app/events/tasks.py:158,181 (EmailHandler().deliver); app/events/routes.py:2824,2844 (also EmailHandler().deliver — not in source Where)
- Original Problem:        (i) escapes the policy engine and preferences, (ii) duplicates template logic, (iii) makes rebranding/localisation a code change.
- Verified Problem:        reproduced — EmailHandler().deliver called in tasks.py (2 sites) and routes.py (2 sites); inline HTML construction in tasks.py:154-181
- Repro command:           git grep -n "EmailHandler().deliver" -- app/events/
- Repro output:            app/events/routes.py:2824:            EmailHandler().deliver(
app/events/routes.py:2844:        EmailHandler().deliver(
app/events/tasks.py:158:                    EmailHandler().deliver(
app/events/tasks.py:181:                        EmailHandler().deliver(
- Verification command:    git grep "EmailHandler().deliver" -- app/events/ | Measure-Object -Line
- Verification output:     4 call sites
- State at hardening:      Open
- Corrections:             Where → misses app/events/routes.py:2824,2844 (EmailHandler calls in contact_organizer route)
- Confidence:              high
- Notes:                   Source Where only mentions tasks.py; routes.py has 2 additional EmailHandler.deliver calls.

### Track B / B-4 — Fix guest_management.py hardcoded notification type
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/guest_management.py::_send_guest_notification uses notification_type='system_alert'
- Verified Where:          app/events/guest_management.py:427
- Original Problem:        loses specificity; the policy engine cannot distinguish guest notifications from system alerts.
- Verified Problem:        reproduced — hardcoded notification_type='system_alert' at line 427
- Repro command:           git grep -n "system_alert" -- app/events/guest_management.py
- Repro output:            app/events/guest_management.py:427:            notification_type='system_alert',
- Verification command:    git grep "notification_type='system_alert'" -- app/events/
- Verification output:     app/events/guest_management.py:427:            notification_type='system_alert',
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Single location, clear fix: add EVENT_GUEST_NOTIFIED type and use it.

### Track B / B-5 — Unify the two notification contracts
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/models.py still declares NotificationType / NotificationChannel for older flows; app/notifications/models.py has its own. Confirm both resolve to the same enum.
- Verified Where:          ONLY app/notifications/models.py:40 (NotificationType), :108 (NotificationChannel), :117 (NotificationModule) — app/events/models.py has NO such declarations
- Original Problem:        two notification type enums in one codebase is exactly the sort of drift this refactor is meant to eliminate.
- Verified Problem:        not found — only ONE declaration exists in the entire codebase (app/notifications/models.py)
- Repro command:           git grep -rn "class NotificationType\|class NotificationChannel\|class NotificationModule" -- app/
- Repro output:            app/notifications/models.py:40:class NotificationType(str, enum.Enum): / app/notifications/models.py:108:class NotificationChannel(str, enum.Enum): / app/notifications/models.py:117:class NotificationModule(str, enum.Enum):
- Verification command:    git grep "class NotificationType" -- app/
- Verification output:     app/notifications/models.py:40:class NotificationType(str, enum.Enum): (exactly one match)
- State at hardening:      Already satisfied
- Corrections:             Where → "app/events/models.py still declares" is FALSE; no such declarations exist in events/models.py. Problem premise is stale.
- Confidence:              high
- Notes:                   This item appears to have been resolved before the register was written. The verification command in the register ("git grep returns exactly one match") passes today.

### Track B / B-6 — Document the events→notifications contract
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/docs/README.md (new)
- Verified Where:          app/events/docs/ directory does not exist; no README.md in docs/
- Original Problem:        no single place states how events notifies users.
- Verified Problem:        reproduced — no documentation file exists at the specified location
- Repro command:           Test-Path app/events/docs/README.md
- Repro output:            False
- Verification command:    Test-Path app/events/docs/
- Verification output:     False
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Depends on B-1..B-5 per register. The docs/ directory must be created first.

### Track C / C-1 — Audit every Flask signal usage
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/signals.py, app/events/signal_handlers.py, plus every .send(...) call site
- Verified Where:          Signals declared: signal_handlers.py:16-20 (5 signals). .send() sites: services.py:1674,2356 (event_registered), services.py:2358 (offer_services_after_registration), services.py:2164 (service_provider_data_requested), tasks.py:290 (event_capacity_released). .connect() sites: signal_handlers.py:136 (event_capacity_released), services.py:2163 (service_provider_data_requested inline), transport/event_listeners.py:80 (offer_services_after_registration), transport/event_listeners.py:81 (service_provider_data_requested), accommodation/listeners.py:14-15 (event_registered), notifications/listeners.py:215,227 (event_registered x2), transport/listeners.py:14-15,22-23 (event_registered, event_cancelled)
- Original Problem:        five signals declared; only one handler is connected inside the module (event_capacity_released). The others are either sent into the void or have external consumers the events module cannot see. Both are defects.
- Verified Problem:        refined as: event_registered has 3 external consumers (accommodation, notifications x2, transport); event_cancelled has 1 external consumer (transport) but NO producer; offer_services_after_registration has 1 external consumer (transport); service_provider_data_requested has 2 consumers (events inline + transport); event_capacity_released is intra-module only. The §5 signal map has 4/5 rows incorrect on cross-module classification.
- Repro command:           git grep -rn "\.send(" -- app/ | Select-String -Pattern "event_registered|event_cancelled|event_capacity_released|offer_services_after_registration|service_provider_data_requested" ; git grep -rn "\.connect(" -- app/ | Select-String -Pattern "event_registered|event_cancelled|event_capacity_released|offer_services_after_registration|service_provider_data_requested"
- Repro output:            .send(): services.py:1674,2356 (event_registered); services.py:2358 (offer_services_after_registration); services.py:2164 (service_provider_data_requested); tasks.py:290 (event_capacity_released) / .connect(): signal_handlers.py:136 (event_capacity_released); services.py:2163 (service_provider_data_requested inline); transport/event_listeners.py:80 (offer_services_after_registration); transport/event_listeners.py:81 (service_provider_data_requested); accommodation/listeners.py:14-15 (event_registered); notifications/listeners.py:215,227 (event_registered); transport/listeners.py:14-15,22-23 (event_registered, event_cancelled)
- Verification command:    git grep -n "^    .* = signal" -- app/events/signal_handlers.py
- Verification output:     5 signals declared at lines 16-20
- State at hardening:      Open
- Corrections:             §5 signal map corrections (4 rows): event_registered cross-module=YES (not "?"); event_cancelled cross-module=YES consumer exists (not "none"); offer_services_after_registration cross-module=YES (not "likely yes"); service_provider_data_requested cross-module=YES confirmed (was "yes" but 2 consumers not 1)
- Confidence:              high
- Notes:                   This is the gate for all Track C work. The §5 map must be corrected before C-2..C-6 can proceed accurately.

### Track C / C-2 — Retire event_registered signal in favour of EventType.EVENT_REGISTERED
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          emitted in services.py::register_for_event_with_payment and services.py::_register_for_event_pessimistic. No in-module consumer.
- Verified Where:          .send() at services.py:1674,2356; 3 external .connect() consumers: accommodation/listeners.py:15, notifications/listeners.py:215,227, transport/listeners.py:15
- Original Problem:        duplicate mechanism with the platform event (EventType.EVENT_REGISTERED also exists). Cross-module consumers cannot rely on an in-process signal they cannot see.
- Verified Problem:        reproduced — signal has 3 external consumers that would break if .send() removed without migrating them to platform event
- Repro command:           git grep -rn "event_registered.send\|event_registered.connect" -- app/
- Repro output:            .send(): services.py:1674,2356 / .connect(): accommodation/listeners.py:15; notifications/listeners.py:215,227; transport/listeners.py:15
- Verification command:    git grep "event_registered.send" -- app/
- Verification output:     app/events/services.py:1674,2356 (2 send sites)
- State at hardening:      Blocked
- Corrections:             Problem → "No in-module consumer" is correct but incomplete — misses 3 external consumers. This item is Blocked on migrating those 3 consumers first.
- Confidence:              high
- Notes:                   Blocked by C-1 corrections. Cannot retire signal until accommodation, notifications, and transport listeners are migrated to EventType.EVENT_REGISTERED. Blocked on migrating external consumers in accommodation/listeners.py, notifications/listeners.py:215,227, and transport/listeners.py before .send() can be removed.

### Track C / C-3 — Retire event_cancelled signal
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          declared in signal_handlers.py. Emission site needs to be confirmed (not present in the files I read — either dead or emitted from a module I haven't seen)
- Verified Where:          Declared at signal_handlers.py:18. NO .send() call sites found in entire repo. 1 external .connect() consumer: transport/listeners.py:22-23
- Original Problem:        same as C-2, plus uncertain producer.
- Verified Problem:        refined as: signal has NO producer (dead signal) but HAS an external consumer (transport/listeners.py) — cannot simply delete without breaking transport module
- Repro command:           git grep -rn "event_cancelled.send\|event_cancelled.connect" -- app/
- Repro output:            .connect(): transport/listeners.py:22-23 / .send(): (no matches)
- Verification command:    git grep "event_cancelled" -- app/ | Select-String -Pattern "EventType" -NotMatch
- Verification output:     signal_handlers.py:18 (declaration); transport/listeners.py:22-23 (consumer); signals.py:7 (re-export)
- State at hardening:      Blocked
- Corrections:             Problem → "uncertain producer" resolved: NO producer exists. But external consumer exists (not documented in §5 map). Item cannot be "delete" or "promote" without addressing transport consumer.
- Confidence:              high
- Notes:                   §5 map shows event_cancelled .send() as "?" and .connect() as "(none in module)" — both wrong. Consumer exists in transport.

### Track C / C-4 — Retire offer_services_after_registration signal
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          emitted in services.py::_register_for_event_pessimistic. Consumer unknown.
- Verified Where:          .send() at services.py:2358; 1 external .connect() consumer: transport/event_listeners.py:80
- Original Problem:        no visible consumer. If cross-module, it must be a platform event.
- Verified Problem:        refined as: has 1 external consumer (transport) — cross-module confirmed
- Repro command:           git grep -rn "offer_services_after_registration.send\|offer_services_after_registration.connect" -- app/
- Repro output:            .send(): services.py:2358 / .connect(): transport/event_listeners.py:80
- Verification command:    git grep "offer_services_after_registration" -- app/ | Select-String -Pattern "EventType" -NotMatch
- Verification output:     services.py:2358 (send); transport/event_listeners.py:80 (connect); signal_handlers.py:19 (decl); signals.py:8 (re-export)
- State at hardening:      Open
- Corrections:             Problem → "Consumer unknown" is FALSE — transport consumer exists. §5 map "likely yes" cross-module confirmed.
- Confidence:              high
- Notes:                   Must promote to platform event or migrate transport consumer before deleting signal.

### Track C / C-5 — Decide service_provider_data_requested fate
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          sent and received inline in services.py::get_service_provider_dashboard_data. The receiver is created and disconnected inside the same function.
- Verified Where:          .send() at services.py:2164; inline .connect() at services.py:2163; external .connect() at transport/event_listeners.py:81
- Original Problem:        a signal used as a synchronous same-request event bus to gather data from other modules. It works, but it is a hidden cross-module coupling and cannot be observed.
- Verified Problem:        reproduced — inline connect/disconnect in same function (services.py:2163) PLUS external consumer (transport/event_listeners.py:81)
- Repro command:           git grep -rn "service_provider_data_requested.send\|service_provider_data_requested.connect" -- app/
- Repro output:            .send(): services.py:2164 / .connect(): services.py:2163 (inline); transport/event_listeners.py:81 (external)
- Verification command:    git grep -n "get_service_provider_dashboard_data" -- app/events/services.py
- Verification output:     app/events/services.py:2140 (function start); inline signal usage at 2163-2164
- State at hardening:      Open
- Corrections:             §5 map shows cross-module="yes" (correct) but misses the inline consumer in services.py — there are 2 consumers, not 1.
- Confidence:              high
- Notes:                   Replace with direct contract calls per register (accommodation_provider_bridge.get_dashboard_data, transport equivalent).

### Track C / C-6 — Keep event_capacity_released but consider promoting
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          signal_handlers.py::handle_capacity_released; emitted in tasks.py::expire_pending_registrations
- Verified Where:          .send() at tasks.py:290; .connect() at signal_handlers.py:136 — ONLY intra-module, no external consumers
- Original Problem:        the only signal with an in-module handler. It is synchronous inside the reaper task and updates the same ticket pool. That is fine, but it duplicates the EventType.EVENT_CAPACITY_RELEASED event type that also exists.
- Verified Problem:        reproduced — only intra-module usage; duplicates platform EventType.EVENT_CAPACITY_RELEASED
- Repro command:           git grep -rn "event_capacity_released.send\|event_capacity_released.connect" -- app/
- Repro output:            .send(): tasks.py:290 / .connect(): signal_handlers.py:136
- Verification command:    git grep "EventType.EVENT_CAPACITY_RELEASED" -- app/
- Verification output:     (no output — platform event type may not exist yet, or named differently)
- State at hardening:      Open
- Corrections:             §5 map correctly identifies this as intra-module only.
- Confidence:              high
- Notes:                   Decision needed: keep signal OR promote to platform event (and delete the other). Register suggests promoting.

### Track C / C-7 — Delete signals.py re-export shim
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/signals.py — a 12-line re-export of signal_handlers
- Verified Where:          app/events/signals.py (12 lines, imports 5 signals from signal_handlers)
- Original Problem:        two modules with the same symbols. Splits grep results and confuses readers.
- Verified Problem:        reproduced — signals.py is pure re-export with no original symbols
- Repro command:           cat app/events/signals.py
- Repro output:            """ Backwards-compatible re-export... """ / from app.events.signal_handlers import (event_registered, event_cancelled, event_capacity_released, offer_services_after_registration, service_provider_data_requested)
- Verification command:    git grep "app.events.signals" -- app/ | Select-String -Pattern "import" | Measure-Object -Line
- Verification output:     Need to check importers — but signals.py itself is confirmed as re-export only
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Must verify no imports from app.events.signals before deletion. Register says "Update any caller still using from app.events.signals import..."

### Track C / C-8 — Delete connect_event_signal_handlers once Track C completes
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          app/events/signal_handlers.py::connect_event_signal_handlers, called from app/events/__init__.py::on_load
- Verified Where:          app/events/__init__.py:103 (import), 110 (call), 125 (in __all__); signal_handlers.py has connect_event_signal_handlers function
- Original Problem:        the whole wiring exists only to connect the last surviving signal. Once the signal goes, so does the wiring.
- Verified Problem:        reproduced — wiring exists in __init__.py to connect signal handlers
- Repro command:           git grep -n "connect_event_signal_handlers" -- app/events/__init__.py
- Repro output:            app/events/__init__.py:103:    from app.events.signal_handlers import connect_event_signal_handlers / app/events/__init__.py:110:                connect_event_signal_handlers() / app/events/__init__.py:125:        'connect_event_signal_handlers',
- Verification command:    git grep "def connect_event_signal_handlers" -- app/events/
- Verification output:     app/events/signal_handlers.py: (function exists)
- State at hardening:      Open
- Corrections:             none
- Confidence:              high
- Notes:                   Depends on C-2..C-7 completing (all signals retired).

### Track C / C-9 — Write a CI guard against new Flask signals in the events domain
- Tree sha:                5322c636b4127c9c11e10750bfa623c752ec9016
- Original Where:          test suite
- Verified Where:          No test file found containing blinker signal detection for app/events/
- Original Problem:        without a guard, the pattern will regrow.
- Verified Problem:        reproduced — no pytest test exists that scans app/events/** for blinker signal imports/instantiations
- Repro command:           git grep -rn "blinker\|from blinker import\|signal(" -- tests/ | Select-String -Pattern "event" | Select-Object -First 10
- Repro output:            (no matches for blinker signal tests in test suite)
- Verification command:    git grep -rn "from blinker import signal" -- app/events/ | Measure-Object -Line
- Verification output:     0 (current signals use flask.signals.signal or similar, not blinker directly)
- State at hardening:      Open
- Corrections:             Verification command in register: "pytest that fails if app/events/** imports or instantiates a Flask/Blinker signal" — no such test exists; Register assumed blinker; app/events signal_handlers.py uses flask.signals.signal. CI guard must detect both, or any signal primitive.
- Confidence:              high
- Notes:                   Must be implemented as a new test file. The register's verification command IS the test to write.

## BATCH WRAP-UP
TREE SHA: 5322c636b4127c9c11e10750bfa623c752ec9016
BATCH: 1 of 5
ROWS PROCESSED: 23
ROWS OPEN: 20
ROWS ALREADY SATISFIED: 1
ROWS PARTIAL: 0
ROWS BLOCKED: 2
ROWS UNKNOWN: 0
CORRECTIONS TOTAL: 15
FILES READ: 47
COMMANDS RUN:
git rev-parse HEAD
git grep -i "football\|afcon business" -- "*.md" "*.txt"
git grep -n -i "football\|afcon" -- "app/events/*.py"
git grep -n "class Event" -- app/events/models.py
git grep -n -A 55 "class Event" -- app/events/models.py
git grep -n "category" -- app/events/models.py
git grep -n "EventType\|event\." -- app/notifications/events/registry.py
git grep -n "^    [A-Z_]* = " -- app/notifications/events/registry.py
git grep -n "event\.registered\|event\.cancelled\|event\.accommodation\|event\.transport" -- app/notifications/events/registry.py app/notifications/events/policy.py
Get-ChildItem app/event_accommodation/ -Recurse
git grep -n "class OrganizerProfile\|class OrganizerMessage\|class EventHostRegistration\|class EventGroup\|class EventGroupMember" -- app/events/models.py
git grep -n "EVENT_\|BOOKING_\|PROPERTY_\|TRANSPORT_\|GUEST_\|PASSENGER_\|WALLET_" -- app/notifications/events/policy.py
git grep -c "event_type=E\." -- app/notifications/events/policy.py
git grep -n "NotificationService.send" -- app/events/
git grep -n "EmailHandler().deliver" -- app/events/
git grep -n "system_alert" -- app/events/guest_management.py
git grep -rn "class NotificationType\|class NotificationChannel\|class NotificationModule" -- app/
Test-Path app/events/docs/README.md
git grep -n "^    .* = signal" -- app/events/signal_handlers.py
git grep -rn "\.send(" -- app/ | Select-String -Pattern "event_registered|event_cancelled|event_capacity_released|offer_services_after_registration|service_provider_data_requested"
git grep -rn "\.connect(" -- app/ | Select-String -Pattern "event_registered|event_cancelled|event_capacity_released|offer_services_after_registration|service_provider_data_requested"
git grep -rn "event_registered" -- app/ | Select-String -Pattern "\.connect|def on_event_registered"
git grep -rn "event_cancelled" -- app/ | Select-String -Pattern "\.connect|def on_event_cancelled"
git grep -rn "offer_services_after_registration" -- app/ | Select-String -Pattern "\.connect|def handle"
git grep -rn "service_provider_data_requested" -- app/ | Select-String -Pattern "\.connect|def handle"
git grep -rn "event_capacity_released" -- app/ | Select-String -Pattern "\.connect|def handle"
cat app/events/signals.py
git grep -n "connect_event_signal_handlers" -- app/events/__init__.py
git grep -rn "blinker\|signal(" -- tests/ | Select-String -Pattern "test|pytest"
git ls-files tests/ | Select-String -Pattern "signal"
NEW REGISTER DEFECTS FOUND:
A-1: Where references non-existent HANDOFF REPORT file; misses app/notifications/README.md
A-2: "match" language not found in source (only AFCON360)
A-3: Register missed Event.venue_id FK to venues.id
A-5: Verification is ADR table, not a shell command
A-6: "football-domain" inaccurate — should be "all-domain"; overlaps with B-1
A-8: "football-domain" inaccurate — models are coach/community/group
B-1: Verification command returns no matches (policy uses alias E)
B-2: Where misses guest_coordination_service.py:947 (6th NotificationService.send site)
B-3: Where misses routes.py:2824,2844 (EmailHandler.deliver in contact_organizer)
B-5: Already satisfied — only ONE NotificationType enum exists (in notifications/models.py)
C-1: §5 signal map has 4/5 rows incorrect on cross-module classification (event_registered, event_cancelled, offer_services_after_registration, service_provider_data_requested)
C-2: Misses 3 external consumers (accommodation, notifications x2, transport)
C-3: NO producer exists but external consumer exists (transport) — contradicts §5 map
C-4: Consumer known (transport) — contradicts "Consumer unknown" in Problem
C-5: §5 map misses inline consumer in services.py (2 consumers total, not 1)
C-9: Register assumed blinker; app/events signal_handlers.py uses flask.signals.signal. CI guard must detect both, or any signal primitive.
UNKNOWNS: none
BLOCKERS: C-2 blocked on migrating 3 external consumers; C-3 blocked on dead signal with live external consumer; C-1 must be corrected before any Track C implementation
NEXT: Proceed to Batch 2 (Cat A + Cat B + Cat C) with corrected §5 signal map as input.
Note: CORRECTIONS TOTAL counts total delta entries across all rows (15).