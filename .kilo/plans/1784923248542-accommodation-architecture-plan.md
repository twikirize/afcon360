# F360 Accommodation Architecture Plan
## Property Lifecycle, Badge System, Discovery Layer, and Admin Intelligence

**Date:** 2026-07-25
**Status:** Draft — Architecture Only (No Code)
**Source Documents:**
- `app/accommodation/accomodation_property.md` — Current state analysis and vision
- `app/accommodation/boundaries.md` — Four trust layer boundaries
- `app/accommodation/models/property.py` — Current Property model
- `app/accommodation/models/moderation.py` — Current PropertyModerationHistory
- `app/accommodation/routes.py` — Current admin/moderation routes
- `app/events/models.py` — EventHostRegistration model
- `app/events/routes_community_hosts.py` — Current community host flow
- `app/events/routes_accommodation.py` — Current event accommodation assignment

---

## 1. Current Pain Points

### 1.1 Property Visibility Gap
- Properties move `draft → pending_review → active` but the public home page (`/accommodation/`) filters on `status=active AND is_verified=True AND is_active=True`.
- There is **no intermediate visibility state** — a property is either fully public or completely hidden.
- Admins cannot see WHY a property is not visible (missing KYC? unverified? not yet submitted?).

### 1.2 Lifecycle Is Too Flat
- Current statuses: `draft, pending_review, active, suspended, archived`
- No distinction between "approved but needs more info" vs "rejected" vs "awaiting submission"
- No `NEEDS_INFORMATION` state — moderators must choose reject (which resets to draft) or approve

### 1.3 Community Host Is a Property Type (Wrong Abstraction)
- `AccommodationPropertyType.COMMUNITY_HOST` conflates property identity with event participation
- A hotel is the same property whether it hosts for an event or not
- Badge/participation should be a separate layer, not a property category

### 1.4 Event Host Approval Mutates Property State
- In `routes_community_hosts.py:234`, approving a community host registration sets `property.status = ACTIVE` and `property.is_verified = True`
- This means event participation approval contaminates property moderation state
- A property approved for one event should not be automatically approved for all others

### 1.5 No Discovery/Layer Concept
- There is no separation between "public marketplace" and "event marketplace"
- All properties that pass moderation appear in the same public listing
- No mechanism for event-specific property visibility

### 1.6 No Trust/Verification Prior to Listing
- KYC/KYB status is not checked before allowing property creation
- No property trust score
- No automated readiness check before making a property bookable

---

## 2. Core Architectural Principles

### 2.1 Four Trust Layers (from `boundaries.md`)
Each layer answers a different question and owns a different responsibility:

| Layer | Question | Owner |
|-------|----------|-------|
| **Identity KYC/KYB** | "Who is this person or organisation?" | Identity module |
| **Property Verification** | "Is this accommodation listing legitimate and safe?" | Accommodation + Admin moderator |
| **Event Host Badge** | "Is this property allowed to participate in this particular event?" | Event owner + Moderator |
| **Event Accommodation Matching** | "Which accommodation options should this event audience see?" | Discovery engine |

**Critical rule:** No layer owns another layer's responsibility. KYC does not approve properties. Badges do not replace accommodation approval.

### 2.2 Dual ID System (AFCON360 Standard)
- All internal FK references use `BigInteger` (`user.id`, `property.id`)
- All external/API references use `public_id` (UUID)
- Never expose raw `id` in APIs or templates

### 2.3 Property Identity ≠ Participation Identity
- A `Property` is a permanent accommodation asset
- `EventHostRegistration` is a participation credential linking Property ↔ Event
- A property can participate in many events; an event can have many properties

### 2.4 Visibility Is a Permission Decision
A property can have different visibility across channels:
- **Public marketplace** — visible to all guests
- **Event marketplace** — visible only to event attendees
- **Admin dashboard** — always visible
- **Host dashboard** — visible to owner
- **Private invitation** — visible only to invited guests

---

## 3. Proposed Architecture

### 3.1 Property Lifecycle (Redesigned)

```
DRAFT
  | (host submits)
  v
SUBMITTED
  | (automated checks pass)
  v
UNDER_REVIEW
  |                     |
  v                     v
APPROVED          NEEDS_INFORMATION
  |                     |
  v                     |
ACTIVE                (owner updates)
  |                     |
  v                     v
SUSPENDED         UNDER_REVIEW  (back to review)
  |
  v
ARCHIVED
```

**New statuses added:**
- `SUBMITTED` — host has finished editing and clicked submit
- `UNDER_REVIEW` — moderator is inspecting
- `NEEDS_INFORMATION` — moderator wants more docs/data, not a rejection
- `APPROVED` — moderator approved (intermediate step before ACTIVE)

**Modified statuses:**
- `ACTIVE` — now only set after approval + readiness check
- `DRAFT` — unchanged
- `SUSPENDED` — unchanged
- `ARCHIVED` — unchanged

**Key change:** `APPROVED` is now a distinct status between `UNDER_REVIEW` and `ACTIVE`. This means a property can be approved by a moderator but not yet publicly visible (e.g., hotel requesting publication next week).

---

### 3.2 Property Readiness Service (NEW)

**File:** `app/accommodation/services/readiness_service.py`

Before a property becomes `ACTIVE` and bookable, it must pass a readiness check:

```python
class AccommodationReadinessService:
    @staticmethod
    def check_readiness(property) -> Tuple[bool, List[str]]:
        """Returns (can_be_booked, failures)"""
```

Checks:
- Address is complete
- Photos are uploaded (min count)
- Pricing is set
- Rooms are configured (if hotel)
- Availability is set
- Payment methods are configured
- Policies are set (cancellation, check-in/out)
- Owner KYC/KYB is verified
- No moderation notes requiring action

Only when ALL pass: `can_be_publicly_booked()` returns `True`.

**This decouples approval from publishability.** A property can be `APPROVED` but not yet bookable if the host hasn't finished setup.

---

### 3.3 Property Trust Score (NEW)

**File:** `app/accommodation/services/trust_service.py`

A computed score (0-100) built from:

**Identity signals (from KYC/KYB):**
- Owner KYC verified: +25
- Owner KYB verified: +25
- Government ID verified: +15
- Phone verified: +10
- Email verified: +10
- Address verified: +15

**Property signals:**
- Photos complete: +10
- Location verified (geocoding): +5
- Description complete: +5
- Documents verified: +10
- No duplicate detection flags: +5

**Risk signals (negative):**
- New account: -10
- Duplicate address: -15
- Suspicious pricing: -10
- Fraud signals: -25

**Thresholds:**
- Score >= 80: Auto-approve (no moderator review needed)
- Score 50-79: Normal moderator review queue
- Score < 50: Priority review + fraud investigation

---

### 3.4 Badge System (NEW)

**New files:**
- `app/event_accommodation/models/badge.py`
- `app/event_accommodation/models/host_registration.py`
- `app/event_accommodation/models/opportunity.py`
- `app/event_accommodation/services/badge_service.py`
- `app/event_accommodation/services/discovery_service.py`
- `app/event_accommodation/services/matching_service.py`
- `app/event_accommodation/services/invitation_service.py`

**Badge Model (`EventBadge`):**

```python
class EventBadge(BaseModel):
    __tablename__ = "event_badges"
    
    event_id = Column(BigInteger, ForeignKey("events.id"), nullable=False)
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id"), nullable=False)
    badge_type = Column(String(50), nullable=False)  # COMMUNITY_HOST, EVENT_PARTNER, VIP_HOST, etc.
    visibility = Column(String(50), default="event_guests")  # event_guests, public, private
    approval_status = Column(String(30), default="pending")  # pending, approved, rejected
    approved_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(30), default="requested")  # requested, invited, accepted, active, expired, revoked
```

**Event Accommodation Opportunity Model (`EventAccommodationOpportunity`):**

```python
class EventAccommodationOpportunity(BaseModel):
    __tablename__ = "event_accommodation_opportunities"
    
    event_id = Column(BigInteger, ForeignKey("events.id"), nullable=False)
    created_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    required_beds = Column(Integer, nullable=True)
    location = Column(String(100), nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    accepted_property_types = Column(JSON, nullable=True)  # ["hotel", "apartment", "lodge", "home"]
    accepted_host_types = Column(JSON, nullable=True)  # ["permanent", "community"]
    status = Column(String(30), default="draft")  # draft, active, closed
```

**EventHostRegistration (Existing — to be refactored):**

The existing `EventHostRegistration` in `app/events/models.py` already links `event_id → property_id → host_user_id`. It should be extended/complemented by the badge system so that:
- `EventHostRegistration` tracks the **application** (who applied, what status)
- `EventBadge` tracks the **credential** (what badge was issued, when it expires, visibility scope)

---

### 3.5 Event Accommodation Matching / Discovery (NEW)

**File:** `app/event_accommodation/services/discovery_service.py`

The discovery engine answers: "Which accommodation options should this event audience see?"

It queries three layers simultaneously:

1. **Identity:** Is the owner trusted? (from KYC/KYB)
2. **Property:** Is the accommodation legitimate? (from Property Verification — status=ACTIVE, is_verified, readiness passed)
3. **Event:** Does it have a valid participation credential? (from Event Badge — badge active, not expired)

Then produces ranked results based on:
- Location match
- Capacity match
- Date availability
- Trust score
- Host response rate
- Rating

**Visibility rules:**
- Properties with no badge are visible in the public marketplace (if they pass verification)
- Properties with a badge are additionally visible in the event marketplace (if badge is active and valid for the event dates)
- Properties can be set to `visibility=hidden` to not appear in public search at all

---

### 3.6 Host Onboarding with KYC/KYB Gates (MODIFY)

**Changes to `app/accommodation/routes.py` and `app/accommodation/services/identity_service.py`:**

Before a host can create a property, they must have:
- **Individual:** Email verified + Phone verified + Government ID verified + Basic profile completed
- **Organisation:** Legal name + Registration info + TIN + Registration documents + Authorised representative verified

**KYC Score threshold** determines what a host can do:
- Score >= required_threshold → Can create properties
- Score < required_threshold → Blocked from listing, shown what to complete

---

### 3.7 Admin Moderation Dashboard Redesign (MODIFY)

**Target route:** `/accommodation/admin/properties` (existing)

**New template:** Replace `properties.html` with a **Property Moderation Dashboard**

**New filters (beyond status):**
- **Workflow stage:** Draft, Awaiting Submission, Pending Review, Approved, Needs Information, Rejected, Active, Suspended, Archived
- **Verification:** Verified, Not Verified
- **Publication:** Public, Hidden
- **Property Type:** Hotel, Apartment, Villa, Guest House, Lodge, Hostel
- **Country / City**
- **Host** (by owner name)
- **Date Submitted** (range)
- **Missing Information:** No photos, No rooms, No amenities, Missing pricing

**New columns in property table:**
- Property ID (public_id)
- Title
- Host (owner display name)
- Type
- Location (city, country)
- Workflow Stage (current lifecycle phase)
- Verification Status
- Trust Score
- Public Visibility toggle
- Event Participation (badge count / active badge)
- Next Action (what needs to happen next)
- Timestamps (created, submitted, reviewed, approved)

**Admin actions become workflow-aware:**
- **View** — inspect property details
- **Inspect** — deep dive with verification checklist
- **Approve** — move from UNDER_REVIEW to APPROVED
- **Reject** — move to REJECTED (with reason)
- **Request Changes** — move to NEEDS_INFORMATION (with specific requested items)
- **Suspend** — move to SUSPENDED (with reason)
- **Publish** — make visible in public marketplace (only if approved + readiness passed)
- **Unpublish** — hide from public marketplace (property stays active)
- **Archive** — move to ARCHIVED

---

### 3.8 Event Host Invitation Flow (NEW)

Two flows for event hosts:

**Flow A: Event Invites Properties**
1. Event owner creates `EventAccommodationOpportunity`
2. System searches eligible properties (by location, capacity, type, trust score)
3. Event owner invites selected properties
4. Property owner receives invitation notification
5. Property owner accepts/declines
6. On acceptance: `EventBadge` is created with `visibility=event_guests`
7. Property becomes visible in event accommodation marketplace

**Flow B: Owner Applies to Events**
1. Property owner sees available opportunities
2. Owner clicks "Apply" on a matching opportunity
3. Application creates `EventHostRegistration` with status=pending
4. Event owner reviews and approves/rejects
5. On approval: `EventBadge` is created

**Key difference from current flow:** The event owner can assign visibility to specific guest groups, and the badge is time-bound and event-specific.

---

### 3.9 Property Visibility Permission System (NEW)

Add `visibility` field to Property model:

```python
visibility = Column(String(30), default="public")  # public, event_only, hidden, private_invite
```

And a new `EventVisibility` model:

```python
class EventVisibility(BaseModel):
    __tablename__ = "event_visibility"
    
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id"), nullable=False)
    event_id = Column(BigInteger, ForeignKey("events.id"), nullable=True)  # NULL = all events
    visible = Column(Boolean, default=True)
    discovered_by = Column(String(50), default="badge")  # badge, invitation, search
```

---

## 4. Detailed Change Map

### 4.1 Model Changes

| File | Change |
|------|--------|
| `app/accommodation/models/property.py` | Add `visibility` column, remove `COMMUNITY_HOST` from `AccommodationPropertyType`, add `trust_score` column, add `readiness_score` column, add `is_publicly_visible` column |
| `app/accommodation/models/moderation.py` | Add `stage` field to `PropertyModerationHistory` to track lifecycle phase |
| `app/events/models.py` | Extend `EventHostRegistration` with `invited_by_id` and `invitation_message` fields |
| **NEW:** `app/event_accommodation/models/badge.py` | `EventBadge` model |
| **NEW:** `app/event_accommodation/models/opportunity.py` | `EventAccommodationOpportunity` model |
| **NEW:** `app/event_accommodation/models/visibility.py` | `EventVisibility` model |

### 4.2 New Files

| File | Purpose |
|------|---------|
| `app/event_accommodation/__init__.py` | Blueprint registration |
| `app/event_accommodation/models/__init__.py` | Model exports |
| `app/event_accommodation/models/badge.py` | EventBadge model |
| `app/event_accommodation/models/opportunity.py` | EventAccommodationOpportunity model |
| `app/event_accommodation/models/visibility.py` | EventVisibility model |
| `app/event_accommodation/services/badge_service.py` | Badge issuance, expiry, validation |
| `app/event_accommodation/services/discovery_service.py` | Event accommodation matching |
| `app/event_accommodation/services/matching_service.py` | Property-to-event matching logic |
| `app/event_accommodation/services/invitation_service.py` | Invite flow for event owners |
| `app/accommodation/services/readiness_service.py` | Readiness checks before publish |
| `app/accommodation/services/trust_service.py` | Property trust score computation |
| `app/accommodation/services/verification_engine.py` | Automated property verification checks |

### 4.3 Modified Files

| File | Change |
|------|--------|
| `app/accommodation/models/property.py` | Remove `COMMUNITY_HOST` from `AccommodationPropertyType`, add `visibility`, `trust_score`, `readiness_score`, `is_publicly_visible` columns, update `__table_args__` check constraints |
| `app/accommodation/routes.py` | Update `admin_properties` route with new filters, add badge/discovery admin routes, update moderation endpoints |
| `app/accommodation/services/moderation_service.py` | Add `NEEDS_INFORMATION` and `APPROVED` status handling, add readiness check before activation |
| `app/accommodation/services/identity_service.py` | Add KYC/KYB gate before property creation |
| `app/events/routes_community_hosts.py` | Stop setting `property.status = ACTIVE` on event approval; use badge system instead |
| `app/events/routes_accommodation.py` | Integrate with new discovery service |
| `app/events/models.py` | Extend `EventHostRegistration` with invitation fields |
| `app/templates/accommodation/admin/properties.html` | Redesign as Property Moderation Dashboard with new filters and columns |

### 4.4 Migration Notes

- `AccommodationPropertyType.COMMUNITY_HOST` should be migrated away from — existing properties with this type should be reclassified or have a `participation_type` field added
- New columns: `visibility`, `trust_score`, `readiness_score`, `is_publicly_visible` should have defaults to avoid breaking existing data
- New tables: `event_badges`, `event_accommodation_opportunities`, `event_visibility`
- **All migrations must be created manually by the user** via `flask db migrate`

---

## 5. Implementation Order

### Phase 1: Foundation (Weeks 1-2)
1. Fix `COMMUNITY_HOST` property type issue — remove from `AccommodationPropertyType`, add `participation_type` field to Property
2. Add `visibility`, `trust_score`, `readiness_score`, `is_publicly_visible` columns to Property
3. Add `visibility` field to `PropertyModerationHistory`
4. Extend `EventHostRegistration` with invitation fields
5. Update check constraints on Property model
6. Update `moderation_service.py` to handle new statuses (`NEEDS_INFORMATION`, `APPROVED`)
7. Update `routes_community_hosts.py` to stop mutating property status on event approval

### Phase 2: Trust & Verification (Weeks 3-4)
8. Create `AccommodationReadinessService`
9. Create `PropertyTrustService`
10. Create `AutomatedVerificationEngine`
11. Update Property lifecycle transitions to include readiness check
12. Update public home page to use `can_be_publicly_booked()` instead of simple status check
13. Add KYC/KYB gate to host registration and property creation

### Phase 3: Badge System (Weeks 5-6)
14. Create `app/event_accommodation/` module with models
15. Create `EventBadge` model and migration
16. Create `EventAccommodationOpportunity` model and migration
17. Create `EventVisibility` model and migration
18. Create `BadgeService` — issuance, validation, expiry
19. Create `InvitationService` — event owner invites properties
20. Update `EventHostRegistration` to integrate with badge system
21. Add admin routes for badge management

### Phase 4: Discovery & Matching (Weeks 7-8)
22. Create `MatchingService` — property-to-event matching logic
23. Create `DiscoveryService` — event accommodation marketplace
24. Build event-specific accommodation search endpoint
25. Build badge validation middleware for event context
26. Update guest search to include event discovery when appropriate

### Phase 5: Admin Dashboard Redesign (Weeks 9-10)
27. Redesign `admin_properties` template as Property Moderation Dashboard
28. Add new filters (workflow stage, verification, publication, property type, missing info)
29. Add new columns (trust score, readiness, visibility, event participation)
30. Add workflow-aware action buttons (view, inspect, approve, reject, request changes, publish, unpublish, archive)
31. Add property history timeline to property detail view
32. Add admin command center with pipeline summaries (submitted today, pending, approved, rejected)
33. Add event participation admin panel (badge requests, invitations, active hosts, expired)

### Phase 6: Integration & Polish (Weeks 11-12)
34. Integrate all pieces — end-to-end property lifecycle from creation to event discovery
35. Add notification system for badge invitations, moderation requests, readiness failures
36. Write tests for all new services
37. Update API documentation
38. Performance optimization (indexes, query optimization)

---

## 6. Key Design Decisions (Requiring User Confirmation)

### 6.1 COMMUNITY_HOST Removal
**Decision:** Remove `COMMUNITY_HOST` from `AccommodationPropertyType` and replace with a `participation_type` field on Property.
**Impact:** Existing properties with `COMMUNITY_HOST` type need a data migration to set `participation_type = 'community_host'`.
**Risk:** Medium — affects property creation forms and any code that filters by `property_type`.

### 6.2 READY vs ACTIVE Distinction
**Decision:** A property must be `APPROVED` by moderator AND pass `ReadinessService` checks to become `ACTIVE` and bookable.
**Impact:** Property that is approved but missing photos or pricing stays in APPROVED state, not visible for booking.
**Risk:** Low — this is the intended behavior; prevents half-baked properties from being bookable.

### 6.3 Auto-Approval Threshold
**Decision:** Individual hosts with KYC score >= 80 and complete listings get auto-approved (no moderator queue).
**Impact:** Reduces moderator workload for trusted hosts.
**Risk:** Medium — requires accurate trust score algorithm. Start with conservative thresholds and adjust.

### 6.4 Badge vs EventHostRegistration
**Decision:** Keep `EventHostRegistration` as the application record and add `EventBadge` as the issued credential. They are separate tables linked by the same `event_id + property_id`.
**Impact:** More tables but cleaner separation. `EventHostRegistration` = "applied", `EventBadge` = "approved and active".
**Risk:** Low — adds complexity but is architecturally correct.

### 6.5 Public Visibility Gate
**Decision:** Add `visibility` column to Property. Default is `public` for verified+active properties. Can be toggled by admin or automatically set by readiness.
**Impact:** Properties exist and are active but may not appear in public search until visibility is granted.
**Risk:** Low — backward compatible if default is `public`.

### 6.6 Event Accommodation Matching Scope
**Decision:** The matching engine is a query layer, not a separate microservice. It lives in `app/event_accommodation/services/discovery_service.py` and is called from existing routes.
**Impact:** Simple to implement now. Can be extracted to a separate service later if performance demands it.
**Risk:** Low — this is the right granularity for v1.

---

## 7. Success Criteria

### 7.1 Property Lifecycle
- [ ] Property can move through full lifecycle: Draft → Submitted → Under Review → (Approved or Needs Information) → Active → Suspended → Archived
- [ ] `NEEDS_INFORMATION` state allows moderator to request specific items without rejecting
- [ ] `APPROVED` state is distinct from `ACTIVE` — approved does not mean bookable yet

### 7.2 Visibility System
- [ ] Property visibility can be `public`, `event_only`, `hidden`, or `private_invite`
- [ ] Public home page shows only properties that pass readiness check AND are visible
- [ ] Event marketplace shows properties with valid event badges

### 7.3 Badge System
- [ ] Event owner can create an opportunity and invite properties
- [ ] Property owner can accept/reject invitations
- [ ] Badges have expiry dates and can be revoked
- [ ] A property with an active badge for Event X is visible in Event X's accommodation marketplace

### 7.4 Trust & Verification
- [ ] KYC/KYB gate blocks property creation for unverified owners
- [ ] Trust score is computed and displayed in admin dashboard
- [ ] Properties with trust score >= 80 skip moderator queue (with audit log)

### 7.5 Admin Dashboard
- [ ] New filters work (workflow stage, verification, publication, property type, missing info)
- [ ] Property table shows trust score, readiness, visibility, and event participation
- [ ] Action buttons are workflow-aware (show only valid actions for current state)
- [ ] Command center shows pipeline summaries

### 7.6 Separation of Concerns
- [ ] Event organiser approval does NOT change property moderation status
- [ ] Badge issuance does NOT make property publicly visible
- [ ] KYC verification does NOT approve properties
- [ ] Property readiness check does NOT verify identity

---

## 8. Open Questions

1. **What is the current public accommodation query exactly?** — Need to confirm the exact WHERE clause used by the public home page and the search/autocomplete endpoints. The current code shows `status=active AND is_verified=1 AND is_active=1 AND is_deleted=0` but there may be additional filters.

2. **What is the `host_id` field on Property?** — The `Property` model references `owner_user_id` and `owner_org_id`, but `ModerationService.approve_property()` at line 35 uses `prop.host_id` which does not exist on the current Property model. Need to confirm if `host_id` is a legacy field or if it should be `owner_user_id`.

3. **Should `EventHostRegistration` be replaced or extended?** — The existing model already links event → property → host. The badge system can either extend it or replace it entirely. Decision needed.

4. **What is the exact `COMMUNITY_HOST` property type usage in the wild?** — Need to audit existing data to understand how many properties use `COMMUNITY_HOST` type before deciding on the migration path.

5. **Should readiness checks be automated or manual?** — The readiness service could auto-check or require admin/manual confirmation. Decision needed.

6. **What is the notification infrastructure?** — The `ModerationService` currently uses `NotificationService.send()` — need to confirm this service exists and works, and whether it supports the new notification types (badge invitation, readiness failure, trust score alerts).
