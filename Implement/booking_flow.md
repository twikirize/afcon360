AFCON360 Accommodation Booking System — Hardened Production Specification v2.0
Status: 🟢 Architecture‑Hardened, Implementation‑Ready
Constitutional Baseline: ADRs D‑001 through D‑040 (frozen)
Triple‑Lock Workflow: Active – every change must update design, code, and audit.

Table of Contents
System Overview

Constitutional Principles

Roles & Authority Matrix

Booking Lifecycle & Progressive Commitments

Guest Manifest & Registration

Guest Verification

Check‑in Readiness Gate

Check‑in Process

Stay Management

Check‑out & Financial Closure

Payment Responsibilities

Deposits & Guarantees

Cancellation & Refunds

No‑show Management

Room Assignment & Inventory

Availability Engine

Property Structure & Policies

Staff Roles & Permissions

Audit & Compliance

Enterprise & Ecosystem

Detailed Phases (Original Booking Flow)

Exception Paths

Domain State Machines

Domain Events

Decision Points Summary

Implementation Sprints

Triple‑Lock Workflow

Final Checklist

1. System Overview
text
GUEST ──► SEARCH ──► INVENTORY ──► PRICING ──► BOOKING ──► PAYMENT ──► CONFIRMED
                  │            │            │            │            │
                  ▼            ▼            ▼            ▼            ▼
              Results     Available     Price       Booking      Guarantee
                         Rooms        Breakdown     Created       Satisfied

STAY ──► REVIEW
  │          │
  ▼          ▼
Check‑in   Post‑Stay
Check‑out  (Audit)
Key Domains: Search, Inventory, Pricing, Booking, Payment, Guest, Stay, Review,
Cross‑cutting: Identity, Authority, Policies, Audit, Channel Distribution, Revenue.

2. Constitutional Principles (from ADRs D‑001–D‑004)
Progressive Commitment – A booking is a legal agreement that evolves from Exploration → Reservation Hold → Booking Commitment → Contract → Stay.

Inventory, not people – A reservation reserves rooms for dates; the Guest Manifest collects identities separately.

Roles – Every interaction involves a User (logged‑in identity), a Creator (who made the booking), a Booking Owner (contractual party), and one or more Guests (occupants).

Authority follows ownership – Only the Booking Owner (or an explicit delegate) may cancel, modify, or refund a booking. Guests have occupancy rights, not contractual authority.

3. Roles & Authority Matrix
Role	Description	Rights
User	Authenticated platform identity	Browse, create bookings, manage profile
Creator	User who performed the booking action	Recorded for accountability; no ongoing authority
Booking Owner	Individual or organisation holding the contract	Cancel, modify dates/rooms, add/remove guests, refund, receive invoices
Guest	Person occupying a room	Check in/out, receive room access, report issues; cannot cancel or refund
Delegate	Someone authorised by the Owner	Acts on behalf of the Owner without owning the contract
Default rule: If you create a booking for yourself, you are Owner and Guest. If you book for your company, the company is Owner, you are Creator. If you book for your spouse, you are Owner, your spouse is Guest.

4. Booking Lifecycle & Progressive Commitments
Phase	State	Guest’s Binding Promise	Hotel’s Binding Promise
Exploration	DRAFT → HELD	None	“I won’t sell this room for 15 min”
Commitment	HELD → PENDING_PAYMENT	“I intend to stay, I accept terms, I commit to pay”	“I’ll hold this room at this price while payment verifies”
Contract	PENDING_PAYMENT → CONFIRMED	Payment/guarantee verified	“This room is yours. I won’t cancel or overbook.”
Fulfilment	CONFIRMED → CHECKED_IN → CHECKED_OUT → CLOSED	Physical stay	Service delivered
Instant Book: PENDING_PAYMENT → CONFIRMED (payment verified automatically)

Request‑to‑Book: HELD → PENDING_APPROVAL → (host accepts) → PENDING_PAYMENT → CONFIRMED

No‑show occurs if gate stays closed past check‑in deadline without arrival.

5. Guest Manifest & Registration
At CONFIRMED, a Guest Manifest is created with placeholder slots equal to the number of expected guests.

The Booking Owner is accountable for filling slots. Slots can be filled by the owner, a delegate, or the guest themselves via a self‑registration link (single‑use, time‑limited).

Registration collects: full name, phone, email, ID type/number (optional per property policy), DOB, nationality.

Each slot has status unregistered → registered once minimum required fields are complete.

Deadlines: default to check‑in start time; reminders at 72h and 24h before.

Incomplete manifest at deadline blocks the Check‑in Readiness gate.

Guest replacement is allowed before check‑in (slot updated, audit trail preserved).

6. Guest Verification
Separate from registration. A verification level is configured per property:

None – no verification needed.

Basic Identity – name + self‑declared ID number.

Document Upload – guest uploads ID image; platform or host reviews.

Biometric/Liveness – KYC provider integration.

Third‑party Attestation – trusted external source (e.g., UN delegation list).

Verification status per slot: unverified → verified.

Platform may force a higher level for cash‑on‑arrival or high‑risk bookings.

Unverified guests block the readiness gate.

7. Check‑in Readiness Gate (Computed)
READY_FOR_CHECKIN = (booking.status == CONFIRMED AND payment_guarantee_satisfied AND today >= check_in_date AND manifest.fully_registered AND all_required_guests_verified AND property_specific_conditions_met AND no_active_block)

The gate is evaluated in real time at check‑in. A readiness summary is visible to the owner and guests.

If gate is closed, check‑in is refused. Booking remains CONFIRMED.

Host may override only in exceptional circumstances (audited).

8. Check‑in Process
Pre‑condition: gate open.

Host (or self‑service kiosk) confirms identity of at least one guest against the manifest.

Room assignment: specific physical room(s) are assigned to the booking (if not pre‑assigned).

Key/access issued.

Host confirms check‑in → booking transitions to CHECKED_IN; timestamp recorded.

Inventory marks room as occupied. Post‑check‑in operational messages sent.

Early/late check‑in handled per property policy.

9. Stay Management (D‑009)
Any modification during stay (extension, room change, guest count adjustment, incidentals) is recorded as a stay modification with author and timestamp.

Guest may request extensions; system checks availability and applies additional charges.

Requests for housekeeping or maintenance are linked to the booking.

10. Check‑out & Financial Closure (D‑010)
Guest or host initiates check‑out.

System computes final bill: accommodation charges + incidentals − deposits − payments made.

Any outstanding balance is charged immediately or via the selected payment method.

Host confirms room condition; damage claims or extra cleaning fees may be added (linked to booking).

Booking transitions to CHECKED_OUT. Room status → dirty → triggers cleaning.

Guest can leave a review. After review period (7 days), booking → CLOSED.

11. Payment Responsibilities (D‑011)
The Payer is the entity responsible for paying, which may differ from the Booking Owner (e.g., corporate invoice, sponsor, government).

Multiple payment instruments per booking are allowed (deposit from wallet, balance from company account).

For off‑system payments (cash, direct MoMo), the host declares receipt; the guest confirms within a dispute window. Both are audited.

12. Deposits & Guarantees (D‑012)
A deposit (percentage or fixed) may be required at booking time. It is applied to the total.

Security deposits for incidentals/damages are separate and held as a pre‑authorisation; not part of the accommodation fare.

13. Cancellation & Refunds (D‑013)
Cancellation can only be initiated by the Booking Owner (or delegate).

Each property selects a cancellation policy (Flexible, Moderate, Strict, or custom) that determines refund percentage based on days before check‑in.

Refunds are auto‑calculated and returned to the original payment source.

Cancellation after check‑in is treated as early departure with a separate policy.

14. No‑show Management (D‑014)
System auto‑detects no‑show: if READY_FOR_CHECKIN was true but no check‑in occurred by the deadline.

Owner gets a grace period (24h) before penalties apply (forfeiture of deposit/full charge per policy).

Host may override if the guest actually arrived.

15. Room Assignment & Inventory
Bookings are made against Room Types, not specific physical rooms.

Physical room assignment happens at check‑in (or pre‑assigned, but guaranteed only at check‑in).

RoomHold entity (15‑min timer) prevents double‑booking; expired holds return inventory to available.

Only one active hold per inventory/date combination.

Occupancy rules enforced: max adults/children per type, infant policies, extra‑person charges.

16. Availability Engine (D‑022)
available = physical_rooms_per_type − booked − held − out_of_service + overbooking_allowance
Real‑time computation for each night in the requested range. Expired holds are automatically released.

17. Property Structure & Policies
Hierarchy: Property → Room Type → Physical Room.

Each property configures:

Registration fields and deadline (D‑005)

Verification level (D‑006)

Cancellation policy template (D‑013)

Check‑in/out windows

House rules (D‑024)

Policies are presented at checkout; guest must accept them before confirmation.

Changes to policies affect only future bookings.

18. Staff Roles & Permissions (D‑023)
Property staff (owner, manager, front desk, housekeeping) have role‑based permissions.

Sensitive actions (cancellation, refund, walk, gate override) require specific permissions.

All staff actions are logged with user ID and timestamp.

19. Audit & Compliance (D‑025)
Append‑only audit log for every state transition, payment, consent event, and override.

Consent records (policy acceptance, data sharing) include timestamp and IP.

Financial transactions are individually auditable and linked to the booking.

Data retention follows local regulations; guests can request data deletion.

20. Enterprise & Ecosystem (D‑026–D‑040)
Multi‑Property & Chain Management: Property Groups with centralised policies, shared guest profiles, cross‑property reporting.

Channel Manager: Unified inventory pool synced with OTAs (Booking.com, Expedia) and GDS via standardised APIs.

Revenue Management: Base rates, derived rate plans, dynamic pricing rules, corporate negotiated rates.

Loyalty Programme: Points and tier status across chain properties.

Multi‑Currency & Tax: Property‑base currency, guest‑preferred display, configurable tax rules (VAT, city tax), compliant invoicing.

Dispute Resolution: Structured lifecycle (OPEN→EVIDENCE→REVIEW→RESOLVED) with automatic chargeback evidence.

Accessibility & i18n: WCAG 2.1 AA, multi‑language support.

API‑First: RESTful APIs with OAuth2, webhooks, versioned, developer portal.

Security: PCI DSS Level 1, risk‑based authentication, step‑up for sensitive operations.

PMS Integration: Standard connector framework for external property management systems.

Cross‑Domain Bundles: Accommodation + event ticket/transport via Cart; each domain maintains its own inventory.

Sustainability: Property eco‑profiles, carbon footprint display.

Disaster Recovery: Multi‑AZ replication, tested backups, defined RPO/RTO.

21. Detailed Phases (Original Booking Flow)
(This section reproduces and enriches the original 13‑phase booking flow from v1.1, preserving every step, input, decision, output, and exception, while integrating the constitutional rules above.)

Phase 1: SEARCH
Input: Destination, check‑in, check‑out, adults, children, infants, rooms (optional).

Decision: Which properties match the search criteria?

Output: Candidate properties list.

Guest Actions: Enter search criteria, click “Search”.

System Actions: Query property index by destination, dates, guest count; return candidate properties with basic info.

Exception: No properties found → suggest different dates/location; query failed → retry.

Phase 2: RESULTS
Input: Candidate properties.

Decision: Which property to view?

Output: Selected property.

Guest Actions: View cards, apply filters, sort, map view, click “View Property”.

System Actions: Display properties with trust signals, quick availability, proximity to event venues.

Exception: Filters empty → suggest different filters.

Phase 3: PROPERTY
Input: Selected property.

Decision: Is this property right?

Output: Selected property with full details.

Guest Actions: View photos, description, amenities, reviews, map, house rules, host info; click “Show Available Rooms”.

System Actions: Display full details, trust signals, highlights.

Exception: Property not found → return to Search.

Phase 4: ROOMS
Input: Property, dates, guests, rooms needed.

Decision: Which room type(s) to select?

Output: Selected room type(s) with quantity.

Guest Actions: View available room types, compare configurations, select type and quantity, mixed types for groups.

System Actions: Query per‑date availability, display units, validate capacity, suggest recommended type, calculate base price.

Exception: No rooms → suggest alternatives; guest count exceeds capacity → suggest multiple rooms.

Phase 5: HOLD
Input: Selected room(s), dates, guests.

Decision: Is inventory available?

Output: RoomHold created (15‑minute hold).

Guest Actions: View hold timer, proceed to Checkout.

System Actions: Check inventory, create RoomHold, update inventory status to HELD, set expiration.

Exception: Inventory unavailable → suggest alternatives; hold expires → auto‑release.

Phase 6: PRICING
Input: Room(s), dates, nights, guests, discounts.

Decision: Calculate total price.

Output: Price breakdown + total.

Guest Actions: View breakdown, apply promo/loyalty/wallet credit.

System Actions: Calculate base price, taxes, service fee, cleaning fee, apply discounts; show trust signals.

Exception: Invalid promo → error; insufficient wallet balance → prompt other method.

Phase 7: CHECKOUT (4‑Step Wizard)
Step 1: Guest Details

Input: Primary guest, booking type.

Decision: Who is staying?

Output: Guest details + booking type (self, someone else, group).

Guest Actions: Enter/modify details; select booking type.

System Actions: Pre‑fill from profile, validate email/phone.

Exception: Invalid email/phone → error.

Step 2: Special Requests

Input: Guest preferences.

Decision: What special arrangements are needed?

Output: Special requests list.

Guest Actions: Select common requests, free text.

System Actions: Save for host.

Step 3: Payment

Input: Payment method, timing, amount.

Decision: How will the guest pay?

Output: Payment instruction/transaction.

Guest Actions: Choose method (Wallet, Cash, MoMo, Card), timing (Pay Now, Deposit, Pay on Arrival), apply discounts.

System Actions: Validate method availability, calculate deposit, process payment, create transaction, check cash eligibility.

Exception: Insufficient balance, gateway error, cash not eligible → fallback.

Step 4: Review & Confirm

Input: All selections.

Decision: Confirm booking?

Output: Confirmed booking.

Guest Actions: Review property, dates, rooms, guests, price, cancellation policy; accept terms; click “Confirm Booking”.

System Actions: Create booking, update inventory to BOOKED, send confirmation email/SMS, notify host, update analytics.

Exception: Payment failed → release hold, offer retry; inventory changed → re‑check.

Phase 8: CONFIRMED
Input: Confirmed booking.

Decision: What are the next steps?

Output: Booking summary + next actions.

Guest Actions: View summary, booking reference, property details, amount paid; click “Register Guests”, “Add Transport”, etc.

System Actions: Display confirmation page, send emails/SMS, show statuses (Booking, Payment, Guest Registration, Refund).

Phase 9: GUESTS (Post‑Booking Registration)
Input: Primary guest + additional guests.

Decision: Are all guests registered?

Output: Verified guest list (manifest).

Guest Actions: Provide primary details, add additional guests (adults/children/infants), upload IDs, skip initial registration.

System Actions: Store details, validate ID uploads, track registration status, send reminders (24h after booking, 48h before check‑in).

Exception: ID missing → warning, allow skip; host can override incomplete registration.

Phase 10: MY BOOKING (Pre‑Arrival)
Input: Confirmed booking.

Decision: What does the guest need before arrival?

Output: Updated booking / actions completed.

Guest Actions: View details, update guests, special requests, pay remaining balance, cancel booking, download invoice, contact property, get directions, check‑in instructions.

System Actions: Calculate balance, process cancellation with refund, show cancellation policy.

Exception: Cancellation fee → confirm; balance due exceeded → request payment.

Phase 11: CHECK‑IN
Input: Booking + registered guests.

Decision: Is the guest eligible to check in?

Output: Checked‑in guest.

Guest Actions: Arrive, present ID, receive keys/access.

System Actions: Host verifies IDs, payment status; system evaluates READY_FOR_CHECKIN; transition to CHECKED_IN.

Exception: Guests not registered → host override; payment incomplete → error; ID mismatch → reject.

Phase 12: STAY
Input: Checked‑in guest.

Decision: Does the guest need anything?

Output: Requests / extensions / check‑out.

Guest Actions: Request room service, report issues, extend stay, check‑out early.

System Actions: Handle extensions, check inventory, process additional charges.

Exception: Extension unavailable → alternatives; issue reported → notify host.

Phase 13: CHECK‑OUT & REVIEW
Input: Checked‑in guest.

Decision: Is the stay complete?

Output: Checked‑out guest + review.

Guest Actions: Check out (host confirms), review property, tip, download invoice.

System Actions: Transition to CHECKED_OUT, release inventory, calculate final charges, send invoice, transition to CLOSED after review.

Exception: Damage charges → process payment; missing items → process payment.

22. Exception Paths
text
HOLD ──► EXPIRED (15 minutes) ──► Inventory Released

CONFIRMED ──► CANCELLED (guest cancels) ──► REFUND_PENDING ──► REFUNDED
                           │
                           └──► NO_REFUND (non‑refundable)

CONFIRMED ──► NO_SHOW (guest doesn't arrive) ──► NO_REFUND

PENDING_PAYMENT ──► PAYMENT_FAILED ──► Hold Released

PENDING_APPROVAL ──► REJECTED (host rejects) ──► Cancelled

CHECKED_OUT ──► DISPUTE (guest complaint) ──► INVESTIGATION
23. Domain State Machines
Booking Status:
DRAFT → HELD → PENDING_PAYMENT → (PENDING_APPROVAL) → CONFIRMED → (READY_FOR_CHECKIN computed) → CHECKED_IN → CHECKED_OUT → CLOSED
Exceptions: CANCELLED, NO_SHOW, EXPIRED.

Payment Status (independent):
UNPAID → PENDING → PROCESSING → PAID / PARTIALLY_PAID / FAILED → REFUND_PENDING → REFUNDED

Guest Manifest Slot Status:
UNREGISTERED → REGISTERED

Verification Status:
UNVERIFIED → VERIFIED

Inventory Status:
AVAILABLE → HELD → BOOKED → AVAILABLE

24. Domain Events
Event	Trigger	Side Effects
BookingCreated	Guest confirms booking	Send confirmation email, SMS, notify host, update analytics
HoldExpired	Hold timer expires	Release inventory
PaymentReceived	Payment processed	Update booking status, release commission
GuestRegistered	Guest completes registration	Update registration status
BookingCancelled	Guest cancels	Release inventory, process refund, notify guest
CheckedIn	Host verifies guest	Notify housekeeping, update occupancy
CheckedOut	Guest checks out	Release room inventory, calculate final charges
ReviewSubmitted	Guest leaves review	Update property rating, host reputation
25. Decision Points Summary
#	Phase	Decision	Output
1	Search	Which properties match?	Candidate properties
2	Results	Which property to view?	Selected property
3	Property	Is this property right?	Selected property with details
4	Rooms	Which room type(s)?	Selected room(s)
5	Hold	Inventory available?	RoomHold (15 min)
6	Pricing	Calculate total price	Price breakdown
7	Checkout – Guest	Who is staying?	Guest details
8	Checkout – Requests	What special arrangements?	Special requests
9	Checkout – Payment	How will they pay?	Payment transaction
10	Checkout – Confirm	Confirm booking?	Confirmed booking
11	Guests	Are all guests registered?	Verified guest list
12	My Booking	What does guest need?	Updated booking
13	Check‑in	Guest eligible?	Checked‑in guest
14	Stay	Does guest need anything?	Requests/extensions
15	Check‑out	Stay complete?	Checked‑out + review
26. Implementation Sprints
Sprint 1 (P0): Search → Booking journey (search, results, property, rooms, hold, pricing, checkout wizard, confirmation).
Sprint 2 (P1): Booking management (My Booking dashboard, guest registration, guest verification, booking modifications, cancellation, payment completion).
Sprint 3 (P2): Stay & Post‑stay (check‑in, stay management, check‑out, review).
Sprint 4 (P3): Notifications, reminders, audit logging, trust signals.
Sprint 5 (Enterprise): Multi‑property chains, channel manager, revenue management, corporate rates, loyalty, multi‑currency, invoicing.
Sprint 6 (Ecosystem): API gateway, developer portal, PMS integration, security hardening, accessibility, disaster recovery.

27. Triple‑Lock Workflow
Every change must update:

Lock 1 – Design: Implement/booking_flow.md (this document)

Lock 2 – Code: app/accommodation/ source files

Lock 3 – Audit: Implement/report.md

No task is complete until all three locks are satisfied.

28. Final Checklist (v2.0 Complete)
✅ Progressive commitment model with legal promises
✅ Guest Manifest with placeholder slots and self‑registration
✅ Four‑role identity model (User, Creator, Booking Owner, Guest)
✅ Authority delegation and ownership transfer
✅ Configurable Guest Verification levels
✅ Computed Check‑in Readiness gate
✅ Atomic Check‑in with identity confirmation and room assignment
✅ Full Stay management with incidentals
✅ Check‑out with final bill, damage claims, and review
✅ Payer distinct from Booking Owner, multi‑instrument payments
✅ Deposit and security deposit separation
✅ Cancellation policy templates (Flexible, Moderate, Strict, Custom)
✅ No‑show auto‑detection and grace period
✅ Room Type vs Physical Room abstraction
✅ Availability engine with overbooking allowance
✅ Property policies configurable per property
✅ Staff roles and permissions
✅ Immutable audit trail for all operations
✅ Multi‑property chains, channel manager, revenue management
✅ Loyalty, multi‑currency, tax, and invoicing
✅ API‑first, security (PCI DSS), PMS integration, accessibility
✅ Sustainability, disaster recovery
✅ Original 13‑phase booking flow preserved and enriched
✅ Triple‑Lock protocol active