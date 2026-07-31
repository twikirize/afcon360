# 🏨 AFCON360 Accommodation Module

A production-ready accommodation booking system for AFCON360, featuring property listings, availability management, booking engine with temporary holds, state machine, and anti-abuse protection.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Module Structure](#module-structure)
- [Database Schema](#database-schema)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
- [API Endpoints](#api-endpoints)
- [Testing](#testing)
- [Security](#security)
- [Performance](#performance)
- [Troubleshooting](#troubleshooting)
- [Phase Status](#phase-status)
- [Contributing](#contributing)

---

## 🎯 Overview

The AFCON360 Accommodation Module is a complete booking system that allows:
- **Guests** to search, view, and book properties
- **Hosts** to manage their properties and bookings
- **Admins** to oversee the platform

Built with Flask, SQLAlchemy, PostgreSQL, and Redis, it follows enterprise-grade patterns with proper separation of concerns.

---

## 🏗️ Architecture
┌─────────────────────────────────────────────────────────────┐
│ PRESENTATION LAYER │
│ Routes: guest_routes.py | host_routes.py | admin_routes.py │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ APPLICATION LAYER │
│ Services: booking_service.py | availability_service.py │
│ pricing_service.py | abuse_prevention_service.py │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ DOMAIN LAYER │
│ State Machine: booking_states.py │
│ Business Rules: cancellation policies, pricing strategies │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ INFRASTRUCTURE LAYER │
│ Models: property.py | booking.py | availability.py │
│ review.py | payout.py | message.py │
│ Database: PostgreSQL with namespaced enums │
└─────────────────────────────────────────────────────────────┘

text

---

## 📁 Module Structure
app/accommodation/
├── init.py # Blueprint registration, master switch
├── models/
│ ├── init.py # Model exports
│ ├── property.py # Property, PropertyPhoto, Amenity
│ ├── booking.py # AccommodationBooking, BookingStatusHistory
│ ├── availability.py # BlockedDate, AvailabilityRule
│ ├── review.py # Review, ReviewStatus
│ └── payout.py # HostPayout
├── services/
│ ├── init.py # Service exports
│ ├── booking_service.py # Core booking logic
│ ├── availability_service.py # Date availability checks
│ ├── pricing_service.py # Price calculation, refunds
│ ├── search_service.py # Property search
│ ├── wallet_service.py # Wallet integration (placeholder)
│ ├── identity_service.py # User/organisation host checks
│ └── abuse_prevention_service.py # Rate limiting, fraud detection
├── state_machine/
│ └── booking_states.py # Booking state machine
├── routes/
│ ├── init.py # Blueprint definitions
│ ├── guest_routes.py # Public: search, detail, booking
│ ├── host_routes.py # Host dashboard (Phase 3)
│ └── admin_routes.py # Admin oversight (Phase 5)
├── templates/
│ └── accommodation/
│ ├── guest/
│ │ ├── search.html # Property search page
│ │ ├── detail.html # Property details with booking form
│ │ ├── checkout.html # Guest information form
│ │ ├── confirmation.html # Booking confirmation
│ │ └── my_bookings.html # User's booking history
│ ├── host/ # (Phase 3)
│ └── admin/ # (Phase 5)
└── static/
└── accommodation/ # CSS, JS, images

text

---

## 🗄️ Database Schema

### Core Tables

| Table | Description |
|-------|-------------|
| `accommodation_properties` | Property listings with location, pricing, policies |
| `accommodation_bookings` | Booking records with pricing snapshot |
| `accommodation_blocked_dates` | Blocked dates (temporary holds + permanent bookings) |
| `accommodation_booking_history` | Audit trail of all status transitions |
| `accommodation_reviews` | Guest reviews with ratings |
| `accommodation_amenities_master` | Master list of amenities |
| `accommodation_property_amenities` | Junction table for property amenities |
| `accommodation_photos` | Property images |
| `accommodation_rules` | House rules per property |
| `accommodation_availability_rules` | Recurring availability rules |

### Namespaced Enums (PostgreSQL)

| Enum | Values |
|------|--------|
| `accommodation_propertytype` | entire_place, private_room, shared_room, hotel_room |
| `accommodation_cancellationpolicy` | flexible, moderate, strict, super_strict |
| `accommodation_propertystatus` | draft, pending_review, active, suspended, archived |
| `accommodation_verificationstatus` | unverified, pending, verified, rejected |
| `accommodation_bookingstatus` | pending, confirmed, checked_in, checked_out, cancelled, refunded, no_show |
| `accommodation_paymentstatus` | pending, deposit_paid, full_paid, failed, refunded, partial_refund |
| `accommodation_paymentmethod` | wallet, card, mobile_money, bank_transfer |
| `accommodation_blockedreason` | booked, temporary_hold, owner_blocked, maintenance, seasonal |
| `accommodation_reviewstatus` | pending, approved, rejected, flagged |

---

## 🔄 Booking State Machine
┌─────────────────┐
│ PENDING │ ← Temporary hold (15 min)
└────────┬────────┘
│
┌────────────────┼────────────────┐
│ │ │
▼ ▼ ▼
┌───────────┐ ┌───────────┐ ┌───────────┐
│ CONFIRMED │ │ CANCELLED │ │ (expire)│
└─────┬─────┘ └─────┬─────┘ └───────────┘
│ │
▼ ▼
┌───────────┐ ┌───────────┐
│CHECKED_IN │ │ REFUNDED │
└─────┬─────┘ └───────────┘
│
▼
┌───────────┐
│CHECKED_OUT│
└───────────┘

text

---

## ✨ Features

### Phase 1: Foundation ✅ (COMPLETE)
- ✅ Property models with namespaced enums
- ✅ Database migrations
- ✅ Search and property detail pages
- ✅ Guest routes and templates

### Phase 2: Booking Engine ✅ (COMPLETE)
- ✅ Availability service with date blocking
- ✅ Pricing service with fee calculation
- ✅ Booking service with:
  - Idempotency (prevents duplicates)
  - Temporary holds (15 min pending)
  - Automatic date blocking
  - Cancellation with refund calculation
- ✅ State machine with valid transitions
- ✅ Anti-abuse protection:
  - Rate limiting (max 3 bookings/min)
  - User hold limits (max 5 pending)
  - Property hold limits (max 10 pending)
  - Suspicious behavior detection
- ✅ Guest booking flow:
  - Checkout with guest details
  - Booking confirmation page
  - My Bookings list
  - Cancel with refund calculation

### Phase 3: Host Dashboard 🔄 (IN PROGRESS)
- Property management (CRUD)
- Calendar management
- Booking inbox
- Earnings dashboard

### Phase 4: Admin Dashboard 📋 (PLANNED)
- Platform oversight
- Host approval queue
- Analytics

### Phase 5: Polish ✨ (PLANNED)
- Reviews and ratings
- Guest messaging
- Dynamic pricing (AFCON surge)

---

## 🛠️ Installation

### 1. Run Migrations

```bash
flask db upgrade
2. Enable Module
In config.py:

python
FEATURE_FLAGS = {
    'accommodation': {
        'enabled': True,  # Set to True to enable
        'dependencies': ['wallet', 'identity'],
        'version': '1.0.0'
    }
}
3. Seed Amenities
bash
flask seed-accommodation-amenities
4. Create Test Property
python
from app.accommodation.models import Property, AccommodationPropertyType, AccommodationPropertyStatus
from app.extensions import db

property = Property(
    owner_user_id=1,
    title="Central Hotel",
    slug="central-hotel",
    description="Modern hotel in the city center",
    property_type=AccommodationPropertyType.HOTEL_ROOM,
    address_line1="123 Main Street",
    city="Kampala",
    country="UG",
    max_guests=2,
    bedrooms=1,
    beds=1,
    bathrooms=1,
    base_price_per_night=85.00,
    status=AccommodationPropertyStatus.ACTIVE,
    is_verified=True
)
db.session.add(property)
db.session.commit()
⚙️ Configuration
Feature Toggles
python
# config.py
FEATURE_FLAGS = {
    'accommodation': {
        'enabled': False,  # Master switch
        'version': '1.0.0'
    }
}

ACCOMMODATION_SETTINGS = {
    'max_photos_per_property': 20,
    'max_guests_per_property': 50,
    'default_currency': 'USD',
    'service_fee_percentage': 10.0,
    'booking_expiry_minutes': 15,
    'enable_reviews': True,
    'enable_messaging': True
}
📖 Usage Guide
Guest Flow
Search Properties

text
GET /accommodation/guest/?city=Kampala&check_in=2026-04-10&check_out=2026-04-13
View Property Details

text
GET /accommodation/guest/central-hotel
Check Availability (automatically in detail page)

Select dates → Click "Check Availability"

System shows price breakdown

Book Property

Click "Proceed to Checkout"

Enter guest details

Accept terms → "Confirm and Pay"

View Booking Confirmation

Booking reference generated

Email confirmation sent

Manage Bookings

text
GET /accommodation/guest/my-bookings
View all bookings

Cancel eligible bookings

Host Flow (Phase 3)
Dashboard

text
GET /accommodation/host/dashboard
Create Listing

text
POST /accommodation/host/listings/create
Manage Calendar

text
GET /accommodation/host/calendar
Booking Inbox

text
GET /accommodation/host/bookings
🔌 API Endpoints
Guest Endpoints
Endpoint	Method	Description
/accommodation/guest/	GET	Search properties
/accommodation/guest/api/search	GET	JSON search API
/accommodation/guest/<identifier>	GET	Property details
/accommodation/guest/checkout	POST	Create booking
/accommodation/guest/confirmation/<reference>	GET	Booking confirmation
/accommodation/guest/my-bookings	GET	User's bookings
/accommodation/guest/booking/<reference>/cancel	POST	Cancel booking
Host Endpoints (Phase 3)
Endpoint	Method	Description
/accommodation/host/dashboard	GET	Host dashboard
/accommodation/host/listings/create	POST	Create listing
/accommodation/host/listings/<id>/edit	POST	Edit listing
/accommodation/host/listings/<id>/delete	POST	Delete listing
/accommodation/host/calendar	GET	Availability calendar
/accommodation/host/bookings	GET	Booking inbox
Admin Endpoints (Phase 4)
Endpoint	Method	Description
/accommodation/admin/dashboard	GET	Admin dashboard
/accommodation/admin/listings	GET	Manage listings
/accommodation/admin/hosts	GET	Manage hosts
🧪 Testing
Flask Shell Tests
python
from app.accommodation.services.booking_service import BookingService
from datetime import date, timedelta

# Create booking
booking, error = BookingService.create_booking(
    property_id=1,
    guest_user_id=1,
    host_user_id=1,
    check_in=date.today() + timedelta(days=30),
    check_out=date.today() + timedelta(days=33),
    num_guests=2,
    guest_name="Test User",
    guest_email="test@example.com"
)
print(f"Booking: {booking.booking_reference}")

# Confirm booking
success, error = BookingService.confirm_booking(booking.id)
print(f"Confirmed: {success}")

# Cancel booking
success, msg, refund = BookingService.cancel_booking(booking.id, cancelled_by_user_id=1)
print(f"Cancelled: {success}, Refund: ${refund}")

# Get user bookings
bookings = BookingService.get_user_bookings(1)
print(f"Total bookings: {len(bookings)}")
Browser Tests
Page	URL	Expected
Search	/accommodation/guest/	Property list
Detail	/accommodation/guest/central-hotel	Property info, booking form
Checkout	After clicking "Book Now"	Guest details form
Confirmation	After booking	Booking reference
My Bookings	/accommodation/guest/my-bookings	Booking list
🔐 Security Features
Feature	Description
Idempotency	idempotency_key prevents duplicate bookings
Temporary Holds	Dates locked for 15 minutes during payment
Rate Limiting	Max 3 booking attempts per minute
Hold Limits	Max 5 pending bookings per user, 10 per property
State Machine	Ensures valid status transitions only
Audit Trail	Complete history in booking_status_history
Soft Delete	Data preserved, never truly deleted
Namespaced Enums	No conflicts with transport module
⚡ Performance
Optimizations
Database indexes on frequently queried fields:

idx_booking_property_dates

idx_booking_guest_status

idx_property_city_country

Redis caching for search results (planned)

Pagination for booking lists

JSON fields for flexible data storage

Query Examples
sql
-- Efficient date range availability check
SELECT * FROM accommodation_bookings
WHERE property_id = 1
  AND status IN ('confirmed', 'checked_in')
  AND check_in < '2026-04-13'
  AND check_out > '2026-04-10';
🐛 Troubleshooting
Common Issues
Issue	Solution
"Too many requests"	Rate limit reached. Wait 60 seconds.
"Dates not available"	Check existing bookings or blocked dates
"Booking expired"	Complete payment within 15 minutes
"Invalid state transition"	Booking cannot transition from current state
"Property not found"	Verify property ID exists and is active
Database Queries
sql
-- Check all blocked dates
SELECT * FROM accommodation_blocked_dates;

-- Check bookings by user
SELECT * FROM accommodation_bookings WHERE guest_user_id = 1;

-- Check pending bookings
SELECT * FROM accommodation_bookings WHERE status = 'pending';

-- Check expired pending bookings
SELECT * FROM accommodation_bookings
WHERE status = 'pending'
  AND expires_at < NOW();
Debug Mode
Enable debug logging:

python
import logging
logging.getLogger('app.accommodation').setLevel(logging.DEBUG)
📊 Phase Status
Phase	Description	Status
Phase 1	Foundation (Models, Migrations, Search)	✅ COMPLETE
Phase 2	Core Booking Engine	✅ COMPLETE
Phase 3	Host Dashboard	🔄 IN PROGRESS
Phase 4	Admin Dashboard	📋 PLANNED
Phase 5	Polish & Enhancements	📋 PLANNED

---

## 🧪 Recent Fixes & Testing Checklist

### Room Type Validation & Checkout Hardening

**Problem:** `room_type_id` was sometimes submitted as the string `"None"`, causing `ValueError: invalid literal for int() with base 10: 'None'` during checkout.

**Fix applied:**

- Backend validation in `guest_checkout()` rejects missing, empty, `"None"`, and non-numeric `room_type_id` values before booking creation.
- Enhanced warning logging captures invalid attempts with user ID and property ID.
- Frontend form in `detail.html` conditionally renders the hidden `room_type_id` field only when a room type is selected.
- Inline client-side validation intercepts form submission and blocks invalid requests with an alert.
- Conditional UI indicator displays the selected room type name and nightly rate in the booking card.

**Test scenarios:**

| Scenario | Expected Result |
|----------|-----------------|
| No room type selected | Flash message; redirect back to property detail |
| `room_type_id="None"` sent | Flash message; redirect back to property detail |
| Valid room type selected | Proceed to checkout successfully |
| JavaScript disabled | Backend still blocks invalid `room_type_id` |
| Malformed manual request | Blocked + logged at WARNING level |

**Log example:**

```text
[WARNING] app.accommodation.routes: Checkout attempted with invalid room_type_id: None by user 1 for property 5
```


### Frontend Date Validation & Feedback

**Problem:** The property detail page did not prevent users from selecting past dates or invalid date ranges before form submission, and there was no real-time feedback when dates were changed.

**Fix applied:**

- Date inputs now have dynamic `min` attributes tied to today''s date.
- Inline JavaScript validates `check_in` and `check_out` on `change` and `blur` events.
- A dedicated feedback alert shows immediate warnings for past dates, invalid ranges, and checkout before check-in.
- The checkout minimum date is automatically updated based on the selected check-in date.

**User-facing behavior:**

- Selecting a past check-in date shows an immediate danger alert: "Check-in date cannot be in the past."
- Selecting a check-out date on or before check-in shows: "Check-out must be after check-in date."
- The form submit handler also re-validates dates before sending the request.


### Optional `room_type_id` for Single Properties

**Problem:** `guest_checkout()` previously required `room_type_id` for all properties, causing failures for single properties or homes that do not use room types.

**Fix applied:**

- Backend now counts active `RoomType` records for the property.
- If the property has active room types, `room_type_id` is required and verified to belong to the property.
- If the property has no active room types, `room_type_id` is set to `None` and the booking proceeds without it.
- Frontend booking form always includes a `room_type_id` hidden input so the value is explicitly submitted.

**User-facing behavior:**

- Single properties / homes: book without selecting a room type.
- Hotels with multiple room types: must select a room type before checkout.
- Hotels with one room type: auto-selected with an info alert.

**Files changed:**

- `app/accommodation/routes.py`
- `templates/accommodation/guest/detail.html`

---

**Files changed:**

- `templates/accommodation/guest/detail.html`

---

**Files changed:**

- `app/accommodation/routes.py`
- `templates/accommodation/guest/detail.html`

---


---

## 🏗️ Room Management & Operations

### Individual Room Management

The accommodation module now supports individual room management for hotels with 100+ rooms.

**Models:**

- `RoomType` - Groups rooms by type (VIP Suite, Deluxe King, Standard Twin)
- `Room` - Individual physical rooms with room numbers, floors, maintenance status, linked to a `RoomType`
- `RoomBooking` - Assignment records linking bookings to specific rooms

**Features:**

- Individual room numbering (101, A-12, Suite-1)
- Room types with per-room-type pricing
- Per-room maintenance tracking
- Room availability status (available, booked, maintenance, cleaning)
- Bulk room creation support

### Check-in / Check-out Flow

Hosts can now perform check-in and check-out operations:

- **Check-in:** Assigns an available room, marks booking as `CHECKED_IN`, creates `RoomBooking` record
- **Check-out:** Releases the assigned room, marks booking as `CHECKED_OUT`
- Automatic room assignment from available pool during check-in
- Full audit trail with `checked_in_by` / `checked_out_by` user tracking

**Routes:**

- `POST /host/booking/<id>/check-in`
- `POST /host/booking/<id>/check-out`

### Host Payout & Earnings

- `host_earnings` route now renders a functional earnings dashboard
- Revenue summary, occupancy rate, and total bookings displayed
- Integration with `HostService.get_dashboard_data()` for analytics

### Broken Routes Fixed

- `host_bookings` → `templates/accommodation/host/bookings.html` ✅ Created
- `host_earnings` → `templates/accommodation/host/earnings.html` ✅ Created

### ENUM Convention Fixes

- Converted `db.Enum` columns to `db.String` with `CheckConstraint` in `Property` model
- Converted `db.Enum` in `InventoryBlock.reason` to `db.String`
- All enum validations now use application-level CHECK constraints

### Database Changes Required

Run the following Alembic commands after reviewing the model changes:

```bash
flask db migrate -m 'add room management and check-in/out fields'
flask db upgrade
```

New tables:

- `accommodation_room_types`
- `accommodation_rooms`
- `accommodation_room_bookings`

New columns on `accommodation_bookings`:

- `assigned_room_id`
- `checked_in_by`
- `checked_out_by`
- `is_checked_in`
- `is_checked_out`

---

## 🛠️ Recent Fixes & Improvements

### Admin Moderation Workflow

**Problem:** The admin property list (`/accommodation/admin/properties`) only showed a "Toggle Active" button, which didn't provide the full moderation workflow (approve/reject/request changes).

**Fix applied:**

- Added missing `GET /accommodation/moderate/property/<property_id>` route in `app/accommodation/routes.py`
- Updated `templates/accommodation/admin/properties.html` to show:
  - **Review** button linking to the moderation page
  - **Edit** button linking to host edit listing
  - **Approve** and **Reject** buttons for pending properties
  - Status badges with proper conditional styling
  - CSRF protection on all POST forms
- Fixed `templates/accommodation/moderate_property.html`:
  - Corrected `property.status.value` and `property.property_type.value` to handle String columns
  - Fixed `property.max_capacity` → `property.max_guests`
  - Fixed `property.base_price` → `property.base_price_per_night`
  - Added **Suspend** button for active properties
  - Added property photos display
  - Added CSRF tokens to all moderation forms

**Files changed:**

- `app/accommodation/routes.py`
- `templates/accommodation/admin/properties.html`
- `templates/accommodation/moderate_property.html`

### Enum Comparison Fixes

**Problem:** `Property.status` is a `String` column, but several routes were comparing it directly to `AccommodationPropertyStatus` enum members (e.g., `Property.status == AccommodationPropertyStatus.ACTIVE`), causing `can't adapt type 'AccommodationPropertyStatus'` errors.

**Fix applied:**

- `app/accommodation/routes.py`: Changed `admin_properties()` to use `enum_value(status_filter)` helper
- `app/admin/route_modules/settings.py`: Added `.value` to enum comparisons in `moderation_settings()`
- `app/events/assignment.py`: Added `.value` to enum comparison in `check_available_properties()`
- `app/admin/moderator/routes.py`: Added `.value` to enum comparison in stats builder

**Rule:** Always compare `String` columns to string literals or enum `.value`, never to raw enum members.

---

## Appendix A — Accommodation Architecture (Single Source of Truth)

> All other accommodation architecture documents have been deprecated.
> This appendix consolidates the architecture from `ACCOMMODATION_MODULE_SPEC.md`.

### A.1 Data Model Architecture

The accommodation data model follows a three-layer shape used by every major OTA
(Booking.com, Expedia, Marriott):

```
Property (the physical building / listing)
  └─ RoomType (the sellable SKU: "Deluxe King", "Standard Twin")
       └─ Inventory (how many of this SKU exist, and how many are free per date)
```

**Property** — the container, not the sellable thing.
- Keeps identity, location, policies, media, ownership
- `property_kind`: `single_unit` (1 implicit RoomType) or `multi_unit` (multiple RoomTypes)
- Stripped of `max_guests`, `base_price_per_night` (moved to RoomType)

**RoomType** (replaces former `RoomCategory`) — the actual sellable SKU.
- `name`, `max_guests`, `bedrooms`, `beds`, `bathrooms`
- `base_price_per_night`, `currency`
- `total_units` — count of interchangeable rooms of this type
- `property_id` FK → `accommodation_properties`
- Relationship: `Property.room_types`, `RoomType.rooms`, `RoomType.inventory_blocks`

**Room** — physical room instance (optional)
- `room_type_id` FK → `accommodation_room_types` (previously `category_id` → `accommodation_room_categories`)
- Room number, floor, housekeeping status, out-of-service flag
- Only needed for large operators tracking individual units

**InventoryBlock** — sparse table for off-book dates (maintenance, seasonal, owner block)
- `room_type_id`, `date_range_start`, `date_range_end`, `units_blocked`, `reason`
- Availability = `total_units − confirmed_bookings − blocked_units` (range-query, not per-day rows)

**Booking** targets a `RoomType`; physical `Room` assignment (if used) happens after confirmation via `RoomBooking` junction.

### A.2 Trust & Identity Architecture (Four-Layer Model)

| Layer | Question it answers | Controls |
|---|---|---|
| **Identity KYC/KYB** | "Who is this person or organisation?" | Identity verification, KYC/KYB gatekeeper |
| **Property Verification** | "Is this accommodation listing legitimate and safe?" | Property verification engine, moderator review |
| **Event Host Badge** | "Is this property allowed to participate in this event?" | Badge system, event organiser approval |
| **Event Accommodation Matching** | "Which accommodation options should this event audience see?" | Discovery layer, combines all three layers |

**Key rule:** No layer owns another layer's responsibility.
- KYC does not approve properties
- Property verification does not decide event participation
- Event hosts do not verify identities
- Badges do not replace accommodation approval

**Property lifecycle:** DRAFT → SUBMITTED → UNDER_REVIEW → ACTIVE → SUSPENDED → ARCHIVED
**Badge lifecycle:** CREATED → INVITED → ACCEPTED → VERIFIED → ACTIVE → EXPIRED

### A.3 Implementation History

Key completed phases:
- Property model lifecycle expansion (visibility, trust_score, readiness_score)
- Trust, readiness & automated verification engines
- Event accommodation module (EventBadge, EventAccommodationOpportunity, EventVisibility)
- Moderation & event host decoupling
- Admin moderation dashboard redesign
- Room/Property restructuring: RoomCategory → RoomType migration

---

## Appendix B — Payment System Integration & Key Fixes

> Future reference: do NOT create a duplicate `BookingPayment` model in accommodation.
> The wallet module owns `PaymentMethodConfig`; accommodation consumes it.
> Transport already has `BookingPayment`; accommodation must use `AccommodationBookingPayment` or lazy imports.

### B.1 Payment Architecture Alignment

- `PaymentMethodConfig` lives in `app/wallet/models/payment_method.py`
- Accommodation must import it via `from app.wallet import PaymentMethodConfig` (or via `app.events.payment_config` backward-compat shim, but direct wallet import is preferred)
- `PropertyPaymentMethod` is the per-property mapping table: `property_id + wallet_method_id`
- `PaymentPolicyService.get_allowed_options()` builds the final guest-facing options dict

### B.2 Two Policy Layers (Do Not Merge)

| Model | Scope | Purpose |
|-------|-------|---------|
| `PropertyBookingPolicy` | Property-level | per-listing rules: cancellation, deposit %, payment timing |
| `PlatformBookingPolicyOverride` | Platform-level | admin rails: min deposit %, max pay-on-arrival days, AFCON restrictions |

Both must remain separate. `PlatformBookingPolicyOverride` is now enforced inside `get_allowed_options()`.

### B.3 Recent Checkout & Payment Fixes

1. **Enum-to-string persistence bug** (`AccommodationBlockedReason`): fixed at the model layer with `@validates('reason')` on `BlockedDate` so Enum values are converted to strings automatically.

2. **Property-detail booking form bridge**: `detail.html` posts to `/accommodation/guest/checkout` without `payment_method`. The route now detects the missing field, stores booking data in `session['pending_booking']`, and redirects to the full checkout page instead of creating a hold and immediately releasing it.

3. **Template type safety**: `checkout.html` and the GET checkout handler now coerce session price fields to `Decimal`/`int`, preventing `TypeError: must be real number, not str` when the template uses `"%.2f"|format(...)`.

4. **Host booking-policy template**: fixed `policy.property_payment_methods` → `property.payment_methods` so payment-method checkboxes pre-check correctly.

5. **Auto-seed property payment methods**: `HostService.create_property()` now creates a default `PropertyPaymentMethod` row for the globally-enabled `wallet` method, so every new property is bookable from creation.

6. **Payment event ledger**: `BookingService.create_booking()` now creates an `AccommodationBookingPayment` pending record; `confirm_booking()` and checkout update it to `success`. This provides full audit trail for reconciliation.

### B.4 Database Seeding for Property 2

Property 2 had zero payment methods. To fix:

```python
from app import create_app
from app.wallet.models.payment_method import PaymentMethodConfig
from app.accommodation.models.property_payment_method import PropertyPaymentMethod
from app.extensions import db

app = create_app()
with app.app_context():
    PaymentMethodConfig.initialize_defaults()
    db.session.commit()

    wallet = PaymentMethodConfig.query.filter_by(method_id='wallet', is_enabled=True, is_active=True).first()
    if wallet:
        pm = PropertyPaymentMethod(property_id=2, wallet_method_id=wallet.id, enabled=True)
        db.session.add(pm)
        db.session.commit()
```

Global defaults seeded: `wallet` (enabled/active), `cash` (active but disabled by default), plus 5 mobile-money entries (disabled by default).

**Current state:**
- `payment_method_configs`: wallet=enabled/active, cash=disabled/active, mobile money entries=disabled/inactive
- `property_booking_policy` for property 2: `allow_pay_now=True`, `allow_pay_on_arrival=True`, `allow_deposit_payment=True`
- `accommodation_property_payment_methods` for property 2: wallet=enabled

**To enable cash for property 2:**
1. Owner enables `cash` globally via `/owner/settings/wallet` → Payment Methods
2. Host enables cash for property 2 via `/host/property/2/booking-policy` → check Cash under Accepted Payment Methods

Guest checkout then shows 2 methods (Wallet + Cash) and 3 timings (Pay Now, Deposit, Pay on Arrival).

### B.5 IDGuard / Windows Console Note

- `IDGuard._log_violation()` no longer emits Unicode emojis on Windows, preventing `cp1252` `UnicodeEncodeError`.
- `method_id`, `booking_reference`, `payment_reference`, `idempotency_key` are added to `NON_FK_STRING_IDS` because they are business identifiers, not UUIDs.

### B.6 Migration Guidance (Do Not Run Automatically)

If you need the new ledger table and any wallet-related columns in production:

```bash
flask db migrate -m "add accommodation_booking_payments"
flask db upgrade
```

Per project rules, migrations are proposed, not executed automatically.

---

## Appendix C — Quick Decision Tree for Payment Issues

```
Guest sees no payment methods on checkout?
├── Is there a PropertyPaymentMethod row for this property?
│   ├── No → create one, preferably auto-seeded on property creation
│   └── Yes ↓
├── Is wallet_method_id enabled AND is_active in payment_method_configs?
│   ├── No → enable it in admin or seed defaults
│   └── Yes ↓
├── Is payment_method in allowed_methods list?
│   ├── No → check host booking policy + platform override
│   └── Yes ↓
└── Check PaymentPolicyService.get_allowed_options() logs for platform override stripping
```

---

🤝 Contributing
Code Standards
Layered Architecture: Routes → Services → Models

Namespaced Enums: Always use accommodation_ prefix

Audit Trail: Log all state changes

Idempotency: Use keys for write operations

Soft Delete: Never hard delete records

Pull Request Checklist
Tests pass

New enums namespaced

Audit logging added

Documentation updated

No circular imports

extend_existing=True for tables

📄 License
Copyright © 2025 AFCON360. All rights reserved.

🚀 Quick Links
AFCON360 Main Repository

Transport Module Documentation

Wallet Module Documentation

Phase 2 Complete! Ready for Phase 3: Host Dashboard 🎉

text

This README is comprehensive and ready to be saved as `app/accommodation/README.md`. It covers:

- ✅ Complete architecture overview
- ✅ Module structure
- ✅ Database schema and enums
- ✅ All features by phase
- ✅ Installation and configuration
- ✅ Usage guide for guests
- ✅ API endpoints
- ✅ Testing guide
- ✅ Security features
- ✅ Performance optimizations
- ✅ Troubleshooting
- ✅ Phase status

Would you like me to add or modify any sections?
