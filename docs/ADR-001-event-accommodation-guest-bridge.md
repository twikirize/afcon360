# ADR-001: Event → Accommodation Guest Bridge

Status: Accepted
Date: 2026-08-20
Modules: Events, Accommodation, Notifications, Auth
Risk: Behavioral / Cross-module

---

## 1. Context

Events and Accommodation are independent modules. Today:

- An event organiser can assign a confirmed attendee to an existing AccommodationBooking via `GuestCoordinationService.assign_accommodation` (`app/events/guest_coordination_service.py`) or `EventService.assign_service_to_attendee` (`app/events/services.py`). This only writes `EventAssignment.accommodation_booking_id`.
- Accommodation already has the building blocks for account-free guest self-registration:
  - `BookingRegistrationLink` (`app/accommodation/models/booking_registration_link.py`) — one booking-scoped, token-backed, multi-use link.
  - `GuestRegistration` (`app/accommodation/models/guest_registration.py`) — per-booking guest slot with name, email, phone, nationality, id-document fields, and status (`pending` / `in_progress` / `completed` / `skipped`).
  - Public redemption route `/accommodation/r/<token>` (`app/accommodation/routes.py:2553`) and template `registration_link.html`.
  - `BookingRegistrationLinkService` (`app/accommodation/services/booking_registration_link_service.py`) — token generation (`secrets.token_urlsafe(32)`), hash-only persistence, `find_by_token`.

Gap:
1. Assignment does not pre-fill the booking's guest list with the attendee's details.
2. No invite link is emailed to the attendee (even when they have an email) so they can complete missing fields before check-in.
3. Account-free guests (no AFCON360 account) have no prompt to provide identity details.
4. The existing redemption route always creates a new `GuestRegistration`, so a pre-filled event slot would be duplicated.

Module-independence constraint (constitution §17, §42):
- Accommodation must remain the sole owner of its state (`GuestRegistration`, `BookingRegistrationLink`).
- Events must never write accommodation tables directly.

---

## 2. Decision

Introduce a **thin Events-owned orchestration bridge** that connects assignment to accommodation via an **Accommodation-owned public contract**.

### 2.1 Accommodation contract (write authority)

File: `app/accommodation/services/coordination_contract.py`
Class: `AccommodationCoordinationContract`

Public methods:
- `ensure_event_guest_slot(booking_reference, *, full_name, email, phone, nationality, user_id)` — idempotent upsert of a `GuestRegistration` pre-filled from event attendee data. Status set to `in_progress` when name+email present, else `pending`. `registration_source = 'event_coordination'`. `is_placeholder = True` when email missing (host fills in person).
- `ensure_registration_link(booking_reference, token_hash, *, max_registrants, expires_at)` — upsert of a `BookingRegistrationLink` for the booking. If one already exists, its `token_hash` is rotated to the new value. Accommodation never stores the raw token; only the SHA-256 hash.

### 2.2 Events bridge (orchestration only)

File: `app/events/accommodation_bridge.py`
Function: `issue_accommodation_for_assignment(event, registration, booking, assignment)`

Flow:
1. Call contract to create/update the guest slot.
2. Generate a 32-byte URL-safe token (`secrets.token_urlsafe(32)`) — this is the **Events-owned secret**.
3. Persist the token in `EventAssignment.schedule_json` keyed by booking reference so it can be re-sent without re-deriving it.
4. Compute `token_hash = sha256(token)`. Call contract to persist the link hash.
5. Build absolute URL `/accommodation/r/<token>` and send the attendee an email via `NotificationService.send` (channel `email`, `force_external=True`, `module=NotificationModule.ACCOMMODATION`).
6. Best-effort: email failures are logged but never fail the assignment.

### 2.3 Hook point

Call the bridge after a successful assignment commit in:
- `GuestCoordinationService.assign_accommodation` (`app/events/guest_coordination_service.py`) — covers canonical and bulk flows.
- The `/api/<slug>/accommodation/assign` route (`app/events/routes_accommodation.py`) and `/<event_ref>/accommodation/assign` (`app/events/assignment.py`) both route into `GuestCoordinationService.assign_accommodation`, so the bridge is invoked automatically.

### 2.4 Redemption route update

File: `app/accommodation/routes.py` (`shared_registration`)
Change: before creating a new `GuestRegistration`, look for an existing active slot in the booking whose `guest_email` matches the submitted email and whose `registration_source == 'event_coordination'`. If found, update it with submitted fields (name, phone, id_document_type) and mark `status = 'completed'`, `is_placeholder = False`. Otherwise fall back to `RegistrationService.create` (existing behaviour). Idempotent: a second submission for the same email returns the "registered" view.

### 2.5 Re-assignment / cancellation safety

- On reassignment to a different booking, the old `GuestRegistration` slot stays in history (`is_active=False` is handled by `RegistrationService.remove`).
- The old `BookingRegistrationLink` token is rotated when the new assignment issues its own token; old links stop working because their hash no longer matches.
- On cancellation, no additional guest-state cleanup is required because the slot remains valid in the booking (host decides what to do with it).

---

## 3. Security analysis and controls

| Risk | Control |
|------|---------|
| **Token guessing** | `secrets.token_urlsafe(32)` → 192 bits of entropy. Never logged. Stored only as SHA-256 hash in accommodation DB. Raw token stored only in `EventAssignment.schedule_json` (Events-owned) and emailed once. |
| **PII in URL / Referrer** | Only the token appears in the public URL. No attendee name/email is put in the query string. HTTPS required; CSP prevents leakage. |
| **Scope on redemption** | The link resolves to a booking only. Submission must submit an email that matches a pre-filled `GuestRegistration` slot in that booking. A guest cannot fill another guest's slot without knowing that guest's email. |
| **Privilege escalation** | Completion of the link only writes to the matched `GuestRegistration`. It cannot change booking status, payment, or other guests. It cannot create or elevate a User account. |
| **Account-free → account linking** | `guest_user_id` on `GuestRegistration` stays `None`. If the guest later creates an AFCON360 account with the same email, link via confirmed-email match only. The invite token grants no account privileges. |
| **Email bombing / privacy** | Email is sent only after `validate_email_address` passes (syntax, disposable, MX, role-account block). One send per assignment. Responses are generic — no confirmation whether an address exists in the system. Organiser consent applies (attendee data disclosure to third-party). |
| **Replay / reuse** | A completed event-coordination slot is returned as "registered" on repeat submission. `BookingRegistrationLinkService.find_by_token` checks `is_active` + `is_expired`. |
| **Concurrency** | The existing `BookingRegistrationLinkService.find_by_token(lock=True)` and `RegistrationService.create` already lock the booking row. The route-level update path reads the existing slot before the shared link lock; acceptable because the slot is row-identified by email, not a capacity counter. |
| **Cross-module data leakage** | Accommodation returns only the booking reference / slot status to Events. Events never sees accommodation internals beyond the contract return values. |

---

## 4. Module independence boundary

```
Events (owner)                  Accommodation (owner)
──────────────────              ──────────────────
EventRegistration               AccommodationBooking
EventAssignment.schedule_json   GuestRegistration  ← contract write
raw invite token                BookingRegistrationLink ← contract write (hash only)
         │                              │
         │  AccommodationCoordinationContract.ensure_*
         └──────────────────────────────►
```

Events does not import `GuestRegistration`, `BookingRegistrationLink`, or any accommodation write path. It imports only the contract (lazy import inside functions). This mirrors the existing read-only pattern already used for `AccommodationBooking` in `_resolve_accommodation_booking`.

---

## 5. Implementation checklist

- [x] ADR drafted and accepted.
- [x] `app/accommodation/services/coordination_contract.py` created.
- [x] `app/events/accommodation_bridge.py` created.
- [x] `app/events/guest_coordination_service.py` — bridge wired after `_commit_assignment`.
- [x] `app/accommodation/routes.py` — `shared_registration` updated to update event-coordination slots by email.
- [ ] Verify imports / syntax (py_compile).
- [ ] Verify DB state: `flask db current`, `flask db heads`.
- [ ] Manual test: assign attendee → slot appears in booking guest list → email arrives with token → redemption pre-fills and marks completed → re-assignment invalidates previous token.

---

## 6. Deferred / hardening

- Per-guest scoped token (1 token per `GuestRegistration`) — requires a new column / FK on `BookingRegistrationLink`. Deferred because the current booking-scoped link + email self-identification already satisfies the requirement for MVP.
- Automatic host notification when an event-assigned guest completes their details via the link.
- Account linking on guest signup: when a later AFCON360 account is created with the same email, backfill `guest_user_id` on the `GuestRegistration`.
