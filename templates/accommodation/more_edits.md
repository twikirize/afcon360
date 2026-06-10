# Accommodation Booking Implementation Status

## Source of Truth
- Primary requirements: `templates/accommodation/booking.md`
- Supporting context: existing accommodation templates, routes, models, and services

---

## ✅ Implemented

### 1. Database Schema Enhancements
**File:** `app/accommodation/models/booking.py`
- Added new columns to `AccommodationBooking`:
  - `primary_guest_id` (FK to users.id, nullable)
  - `primary_guest_name` (String 255, nullable)
  - `primary_guest_email` (String 255, nullable)
  - `primary_guest_phone` (String 50, nullable)
  - `booked_by_user_id` (FK to users.id, NOT NULL)
  - `booking_type` (String 30, default `'self'`)
  - `group_booking_id` (String 100, nullable, indexed)
  - `group_size` (Integer, nullable)
  - `room_number` (Integer, nullable)
  - `guest_instructions` (Text, nullable)
- Added database indexes:
  - `idx_booking_primary_guest` on (`primary_guest_id`, `primary_guest_email`)
  - `idx_booking_booked_by` on `booked_by_user_id`
  - `idx_booking_group` on `group_booking_id`
  - `idx_booking_type` on `booking_type`
- Made `guest_user_id` nullable to support unregistered third-party guests

### 2. Booking Service Updates
**File:** `app/accommodation/services/booking_service.py`
- Extended `BookingService.create_booking()` signature with new parameters:
  - `booked_by_user_id`
  - `primary_guest_id`
  - `primary_guest_name`
  - `primary_guest_email`
  - `primary_guest_phone`
  - `booking_type`
  - `group_booking_id`
  - `room_number`
  - `guest_instructions`
- New fields are persisted on the `AccommodationBooking` record during creation

### 3. Routes Implementation
**File:** `app/accommodation/routes.py`
- Added imports: `User`, `EventAssignment`, `Event`, `EventHostRegistration`, `or_`, `and_`, `uuid`
- **New route:** `my_accommodation()` (`/my-accommodation`)
  - Unified dashboard with two sections:
    - **Where I'm Staying (Guest View):**
      - Self-booked stays
      - Third-party bookings where current user is the guest
      - Event-assigned stays (hotel bookings via `EventAssignment.accommodation_booking_id`)
      - Community host assignments (`EventAssignment.community_host_id`)
    - **What I Booked (Booker View):**
      - All bookings where `booked_by_user_id == current_user.id`
      - Shows guest info, group booking summaries, payment status
  - Supports `?_pane=1` for dashboard embedding
- **Enhanced route:** `guest_checkout()` (`/guest/checkout`)
  - Supports three booking types via `booking_type` form field:
    - `self` — user books for themselves
    - `third_party` — user books for someone else (looks up existing user by email or allows non-registered guest)
    - `group` — multi-room booking with `group_booking_id`, `room_number`, `total_rooms`
  - Validates required fields per booking type
  - Passes all new fields to `BookingService.create_booking()`
  - Handles payment and confirmation flow
  - Group booking flow: redirects to book next room until all rooms are booked
  - Third-party notification: logs intent to notify guest (email integration placeholder)

### 4. Template Updates
**File:** `templates/accommodation/guest/checkout.html`
- Added booking type selector (Myself / Someone Else / Multiple Rooms)
- Conditional sections:
  - Third-party guest details form (name, email, phone, special instructions)
  - Group booking details (total rooms, room number, guests per room)
- JavaScript for dynamic form behavior:
  - `selectBookingType()` toggles sections
  - Generates `group_booking_id` for group bookings
  - Updates room number and guest count displays

**File:** `templates/accommodation/my_accommodation.html` (created)
- Full-page tabbed dashboard:
  - Tab 1: "Where I'm Staying" — guest view across all sources
  - Tab 2: "What I Booked" — booker view with group summaries
- Displays:
  - Property images, dates, guest count, nights
  - Host contact info (name, phone, email)
  - House rules and special instructions
  - Cancellation buttons for eligible bookings
  - Event assignment context (event name, organizer)
  - Group booking room indicators
- JavaScript:
  - `cancelBooking()` — POST to cancel endpoint with CSRF
  - `contactHost()` — mailto link
- Supports `?_pane=1` mode (skips `base.html` layout when embedded)

**File:** `templates/accommodation/my_accommodation_pane.html` (created)
- Minimal wrapper that includes `my_accommodation.html` for dashboard pane embedding

### 5. Navigation Updates
**File:** `templates/base.html`
- Added "My Accommodation" and "My Bookings" to authenticated user dropdown menu
- Added "My Accommodation" and "My Bookings" to mobile drawer navigation (visible when authenticated)

**File:** `templates/user/base_user_dashboard.html`
- Added sidebar nav items:
  - "My Accommodation" linking to `accommodation.my_accommodation`
  - "My Bookings" linking to `accommodation.guest_my_bookings`

---

## ⚠️ Partial / Needs Follow-up

### 1. Email Notification for Third-Party Bookings
**Current state:** Logged as `logger.info()` in `guest_checkout()`
**What's needed:** Actual email sending integration using the project's existing mail infrastructure (see `app/events/tasks.py` for `mail.send()` pattern)
**Risk:** Low — placeholder is safe, but guests won't receive booking confirmations until implemented

### 2. Database Migration
**Current state:** Model columns added directly to Python code
**What's needed:** Generate and apply Alembic migration for the new columns and indexes
**Risk:** Medium — app will fail on fresh DB or if columns don't exist in production
**Command to generate:** `flask db migrate -m "Add multi-guest booking fields"` then `flask db upgrade`

### 3. EventAssignment Model Confirmation
**Current state:** Assumed fields exist per `booking.md` notes
**Verified:** `EventAssignment` has `accommodation_booking_id`, `community_host_id`, `attendee_id`, `assigned_by_id` — confirmed in `app/events/models.py`
**Risk:** Low — fields are present

### 4. `my_accommodation_pane.html` Rendering
**Current state:** Created as a simple include wrapper
**Potential issue:** When `?_pane=1` is used, `my_accommodation.html` already skips `base.html` via the `is_pane` check. The separate pane template may be redundant but is included per the spec.
**Risk:** Low — no functional breakage

---

## ❌ Missing / Not Implemented

### 1. `Accomodation_module.md` Review
**Status:** Not reviewed against current implementation
**Action needed:** Cross-reference `templates/accommodation/Accomodation_module.md` with implemented features to ensure no gaps

### 2. Admin / Moderation Templates
**Status:** Existing templates (`moderate_booking.html`, `moderate_property.html`, `moderate_review.html`, `moderate.html`) were not modified
**Action needed:** Verify if admin moderation views need updates to display new booking types (`third_party`, `group`, `event_assigned`)

### 3. `guest/my_bookings.html` Integration
**Status:** Existing template not modified to show new booking type indicators
**Action needed:** Consider adding booking type badges or grouping to the existing "My Bookings" page

### 4. `guest/confirmation.html` Updates
**Status:** Not modified
**Action needed:** May need to display third-party guest info or group booking details on confirmation page

### 5. `home.html` and `explore.html` Integration
**Status:** Not modified
**Action needed:** Verify if search/explore pages need updates for group booking CTAs

---

## 🔍 Verification Notes

- All modified Python files compile successfully (`py_compile` passed)
- Imports resolve correctly in test environment
- `EventHostRegistration` model confirmed to have required fields (`max_guests`, `is_free`, `price_per_night`, `special_instructions`, `currency`)
- Existing `EventAssignment` model confirmed to have required FK fields
- Navigation links use `safe_url()` pattern consistent with codebase
- Pane embedding pattern matches `fan/dashboard.html` convention (`?_pane=1` skips base layout)

---

## Recommended Next Steps

1. **Generate Alembic migration** for new booking columns and indexes
2. **Implement email notification** for third-party bookings using existing mail patterns
3. **Review `Accomodation_module.md`** for any additional requirements
4. **Test end-to-end flows:**
   - Self-booking → confirmation → my_accommodation view
   - Third-party booking → guest lookup → notification
   - Group booking → sequential room booking → group summary
   - Event assignment → community host display
5. **Verify admin/moderation views** handle new booking types correctly
