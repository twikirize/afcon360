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
