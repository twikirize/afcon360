# AFCON360 Accommodation Module — Implementation Plan

**Status:** Core loop complete, pending activities documented  
**Last updated:** 2026-07-20  
**Scope:** Tuning exercise (not rebuild) — close gaps between existing bones and the envisioned booking marketplace  
**Risk areas:** Wallet logic untouched, BaseModel untouched, no new ENUMs

---

## ✅ Completed Tasks

### P0 — Core Loop (all done)

| Task | Description | Files Modified |
|------|-------------|----------------|
| 1.1 | Sync `RoomType.total_units` to real inventory via `sync_room_type_inventory()` | `host_service.py`, `routes.py` |
| 1.2 | Removed dead create-listing form fields (Bulk Import, Room Type Management, Advanced Inventory) | `templates/.../create_listing.html` |
| 1.3 | Fixed `get_property_by_identifier()` — queries `public_id` first, no hardcoded fallback for real DB errors, added `db` import | `services/search_service.py` |
| 1.4 | Deleted legacy availability functions (`is_date_available`, `get_available_dates`, `block_dates`, `unblock_dates`); removed `Booking.is_available()` | `models/availability.py`, `models/booking.py`, `models/__init__.py` |
| 1.5 | Alembic head status confirmed: **single head** (`20260718_1951`). No merge needed. | — |
| 1.6 | Scoped media dedup to `entity_id` — prevents cross-property false deduplication | `app/media/service.py` |
| 1.7 | Fixed `file.content_length` fallback with stream-based size detection | `app/media/service.py` |
| 1.8 | Cleaned up legacy files: deleted `routes_old.py`, `services.py`, `event_listeners.py` | — |
| 1.9 | Fixed admin Preview link to use `prop.public_id`; extended `get_property_by_identifier` and `guest_detail` to resolve UUID lookups | `templates/.../verification.html`, `routes.py`, `search_service.py` |

### P1 — Marketplace Integration (all done)

| Task | Description | Files Modified |
|------|-------------|----------------|
| 2.1 | Created `BookingCommission` model — tracks total, commission, host_payout, status | `models/commission.py` |
| 2.2 | Created `MarketplaceService` — thin integration layer using real wallet module (`WalletService.transfer` with `platform_fee`) | `services/marketplace_service.py` |
| 2.3 | Wired `WalletProcessor` to use `MarketplaceService.charge_guest()` | `services/payment_processors/wallet_processor.py` |
| 2.4 | Added `host_check_in` payout trigger — releases host payout after check-in | `routes.py` |
| 2.5 | Added `host_earnings` page — released/held/total + payout history | `routes.py`, `templates/.../earnings.html` |
| 2.6 | Added payment method label update in checkout template (wallet/mobile money/card/invoice) | `templates/.../checkout.html` |
| 2.7 | Fixed `payment_options.allowed_methods` and `allowed_timings` in `PaymentPolicyService` | `services/payment_policy_service.py` |

### P2 — Host/Guest/Admin Lifecycle (all done)

| Task | Description | Files Modified |
|------|-------------|----------------|
| 3.1 | Created `HostProfile` / `HostOrganisationProfile` models | `models/host_profile.py` |
| 3.2 | Created `PropertyDocument` model — verification documents with status lifecycle | `models/property_document.py` |
| 3.3 | Implemented `POST /host/register` — real host onboarding with tax ID, payout method, org selection | `routes.py`, `templates/.../host/register.html` |
| 3.4 | Implemented review submission flow — `POST /guest/booking/<id>/review`, `ReviewService`, template with star ratings | `services/review_service.py`, `routes.py`, `templates/.../review_form.html` |
| 3.5 | Added review prompt to confirmation page for checked-out bookings | `templates/.../confirmation.html` |
| 3.6 | Created `GET /host/booking/<id>` — detail page with guest info, payment, payout breakdown | `routes.py`, `templates/.../booking_detail.html` |
| 3.7 | Added `POST /host/booking/<id>/refund` — issue partial/full refunds via marketplace service | `routes.py` |
| 3.8 | Created `GET /host/property/<id>/documents` + `DELETE /host/document/<id>` — upload/manage property docs | `routes.py`, `templates/.../property_documents.html` |
| 3.9 | Created `GET /admin/financials/reconciliation` — platform revenue, commissions, payouts, refunds | `routes.py`, `templates/.../financials.html` |
| 3.10 | Wired `sync_room_type_inventory` into all 5 host room routes (category add/edit, room add/delete/maintenance) | `routes.py`, `host_service.py` |
| 3.11 | Updated host dashboard to link to Documents page | `templates/.../dashboard.html` |
| 3.12 | Updated host bookings list to link to detail page | `templates/.../bookings.html` |
| 3.13 | Updated booking policy template to show actual payment method names/icons | `templates/.../booking_policy.html` |

---

## ⏳ Pending Activities

### High Priority

| # | Task | Description | Estimated Effort |
|---|------|-------------|-----------------|
| P1 | **Guest booking detail page** | Dedicated page for guests to view booking details, download receipt, modify dates/room type, rebook | Medium |
| P2 | **Host-Guest messaging** | In-platform messaging between host and guest for booking coordination | High |
| P3 | **Notification system** | Email/SMS for: booking confirmed, check-in reminder, review request, payout released, property approved/rejected | High |
| P4 | **Admin property verification detail** | Document viewer, photo verification, address check, verification history/audit trail | Medium |

### Medium Priority

| # | Task | Description | Estimated Effort |
|---|------|-------------|-----------------|
| P5 | **Host calendar polish** | Calendar template exists (`host/calendar.html`) but needs JS/CSS polish for block-dates UX | Medium |
| P6 | **Host payout settings** | Page for hosts to manage payout method, tax documents, minimum threshold, schedule | Medium |
| P7 | **Property add-ons model** | `PropertyFacility` / `FacilityBooking` for bookable extras (gym, pool, airport transfer) | Medium |
| P8 | **Admin dispute resolution** | Queue + workflow for booking disputes between host and guest | Medium |
| P9 | **Dynamic pricing UI** | Seasonal/weekend pricing overrides per room type in host dashboard | Medium |

### Low Priority

| # | Task | Description | Estimated Effort |
|---|------|-------------|-----------------|
| P10 | **Map view + filters** | Guest search with map pins, price/rating filters, sorting | Low |
| P11 | **Advanced analytics** | Revenue forecasts, booking velocity, competitive intelligence (data exists, needs UI) | Low |
| P12 | **Channel manager** | iCal sync, multi-platform calendar integration | High |
| P13 | **Automated payout reconciliation** | Celery task for nightly payout batch processing | Medium |
| P14 | **Guest blacklisting** | Flag guests with bad behavior, warn other hosts | Low |

---

## 📊 Current System Status

### What works end-to-end

| Flow | Status |
|------|--------|
| Host registration → onboarding | ✅ |
| Property listing creation → draft/pending_review | ✅ |
| Admin verification queue → approve/reject | ✅ |
| Room category + room management → RoomType sync | ✅ |
| Guest search → property detail → room type selection | ✅ |
| Checkout → payment (wallet/mobile money/card/invoice) → escrow | ✅ |
| Booking confirmation → PENDING → CONFIRMED | ✅ |
| Host check-in → payout release → host earnings | ✅ |
| Host check-out → CHECKED_OUT | ✅ |
| Guest review submission → moderation → publication | ✅ |
| Host refund issuance → marketplace refund | ✅ |
| Admin financial reconciliation | ✅ |
| Property document upload/management | ✅ |

### What's pending

- Guest booking modification/cancellation UI (backend exists, needs template polish)
- Host-Guest messaging
- Notifications (email/SMS)
- Admin property detail with document verification workflow
- Host payout settings
- Property add-ons/bookable facilities

---

## 🔧 Migration Required

```powershell
flask db migrate -m "add_host_profiles_property_documents_reviews"
flask db upgrade
```

New models: `accommodation_host_profiles`, `accommodation_host_org_profiles`, `accommodation_property_documents`, `accommodation_booking_commissions`

---

## ✅ Verification

- `python -c "from app import create_app"` — **OK**
- All 21 key endpoints resolve (host, guest, admin) — **OK**
- Alembic head status: **single head** (`20260718_1951`) — **OK**
- No duplicate endpoint errors — **OK**
- No import errors — **OK**

---

## 🚀 Deployment Readiness

**Ready for:**
- Host onboarding and property creation
- Room inventory management with automatic RoomType sync
- Guest booking, payment, and review flow
- Admin verification and financial oversight
- Host payout release and earnings tracking

**Not ready for (pending activities):**
- Production notifications
- Messaging between parties
- Advanced admin verification tools
- Dynamic pricing configuration
