# AFCON 360 — Mobile Optimization Changelog

**Date:** 2026-07-22  
**Scope:** Responsive refactor for phones (≤480px), tablets (481px–1024px), and notched devices  
**Risk Level:** Low (CSS/template only, no schema changes, no color/branding changes)

---

## 1. File Tree — What Exists / What Was Touched

```
templates/
├── base.html                         ← UPDATED (banner classes, mobile-utilities link)
├── events/
│   └── attendee/
│       └── attendee_dashboard.html   ← UPDATED (inline styles removed, stacked mobile)
├── accommodation/
│   ├── admin/
│   │   ├── properties.html          ← UPDATED (moderation workflow buttons, status badges, responsive action cells)
│   │   ├── bookings.html            ← UPDATED (added Owner column, Claimed column, Guests Registered column, filter widgets)
│   │   └── booking_detail.html      ← NEW (full booking detail with Owner info, Guest Manifest, readiness gate, override button, audit log)
│   ├── host/
│   │   ├── bookings.html            ← UPDATED (added approve/reject actions for pending_approval status, inline forms with CSRF, registration filter, Guests Registered column)
│   │   ├── booking_detail.html      ← UPDATED (added approve/reject collapse forms for pending_approval, inline CSRF, Guest Manifest, check-in readiness gate, override button)
│   │   ├── booking_policy.html      ← UPDATED (payment method checkboxes now use method_id string value instead of numeric id; added Cash Payment Protection section; added Guest Registration Requirements section with required_registration_fields checkboxes)
│   │   ├── dashboard.html           ← UPDATED (added payment settings widget linking to booking policy per property)
│   │   └── guest/
│   │       ├── claim_booking.html   ← NEW (owner claiming page for third-party bookings with login/registration options)
│   │       ├── checkout.html        ← UPDATED (moved inline styles to external CSS, added selection cards, validation feedback, responsive grids; removed inline onclick handlers, added data-* attributes for event delegation; wizard step state persisted via sessionStorage)
│   │       ├── detail.html          ← UPDATED (added live AJAX availability checking on date/guest change; added live_availability_results container; submit button disabled when no availability; partial availability suggestions)
│   │       └── register.html        ← UPDATED (added date_of_birth and nationality form fields for host-configurable registration; dynamic required fields with asterisks; registration deadline display)
│   ├── moderate.html                ← UPDATED (matched global AFCON360 light theme, removed inline styles, added table scroll wrappers)
│   ├── moderate_property.html       ← UPDATED (matched global AFCON360 light theme, removed all inline layout styles, added photo grid classes)
│   └── moderate_review.html         ← UPDATED (matched global AFCON360 light theme, removed inline styles, hidden/visible toggle via CSS class)
├── owner/
│   ├── cash_settings.html            ← NEW (global cash payment settings: development mode toggle, fraud protection requirements, amount limits)
│   ├── dashboard.html                ← UPDATED (added Cash Settings card; added Unclaimed Bookings and Check-in Blockers widgets)
│   └── backups.html                  ← NEW (owner database backup & restore management UI; mobile-first responsive grid, stacked table on ≤640px, 44px touch targets)
├── super_admin_dashboard.html        ← UPDATED (mobile drawer + JS; added Accommodation Overview widget)
└── admin/
    ├── accommodation_admin_dashboard.html ← UPDATED (added Unclaimed Bookings and Check-in Blockers widgets)
    └── super_dashboard.html          ← UPDATED (mobile drawer + JS)
```

```
templates/
├── owner/
│   ├── cash_settings.html            ← NEW (global cash payment settings: development mode toggle, fraud protection requirements, amount limits)
│   └── dashboard.html                ← UPDATED (added Cash Settings card linking to cash_settings.html)
```

---

## 2. Change Log by File

### `templates/owner/backups.html` — **NEW**
- Owner database backup & restore management UI. Mobile-first: `clamp()`-based fluid padding/typography, `repeat(auto-fit, minmax(...))` responsive card grids, full-width stacked table rows with `data-label` headers on ≤640px, 44px-min touch targets on all buttons, restore confirmation modal.
- CSRF-protected forms (`{{ csrf_token() }}`). No inline layout styles; all layout via scoped `<style>` using the mobile utility patterns.

### `templates/owner/danger_zone.html` — **UPDATED**
- Added a "Database Backups & Restore" card in the Settings Management section linking to `admin.owner.owner_backup.backups`.

### `static/css/global/mobile-utilities.css` — **NEW**
- Added shared helpers: `.touch-target` (44×44px min), `.stack-mobile`, `.hide-mobile`, `.show-mobile`, `.scroll-x-mobile`, `.safe-bottom`, `.safe-top`, fluid typography helpers (`text-fluid-sm/base/lg/xl`), `.contain-mobile`.
- Purpose: Single source of truth for mobile utilities; future work can extend this file without touching module CSS.

### `static/css/global/style.css` — **UPDATED**
- Added `<link>` to `mobile-utilities.css` in `base.html`.
- **Banners:** Extracted `.banner-incomplete` and `.banner-impersonation` inline styles into CSS classes with `--banner-offset` custom property.
- **Main content:** Changed `main#main` padding from fixed `2.5rem` to `clamp(1rem, 4vw, 2.5rem)`.
- **Footer:** Added `padding-bottom: env(safe-area-inset-bottom, 0px)`.
- **Touch targets:** Added `min-height: 44px; min-width: 44px` to `.menu-item > a`, `.hamburger`, `.drawer-link`, `.drawer-close`, `.drawer-accordion-toggle` under `@media (max-width: 1024px)`.
- **Tablet breakpoint:** Added `@media (min-width: 768px) and (max-width: 1024px)` tightening header padding/gap and `main#main` padding.
- **Preserved:** All brand colors (`#1a3a1a`, `#2d5a2d`, `#ffcc00`, etc.), gradients, shadows, and desktop layout intact.

### `static/css/global/home.css` — **UPDATED**
- `.featured-grid`: Changed from `repeat(4, 1fr)` to `repeat(auto-fit, minmax(280px, 1fr))`.
- `.live-scroll`: Changed from `repeat(3, 1fr)` to `repeat(auto-fit, minmax(280px, 1fr))`.
- **Mobile (≤768px):** `.home-left` and `.home-right` set to `display: none` (sidebars removed from mobile flow). Search `.search-select-wrap` becomes full-width. `.search-btn-group` full-width.
- **Tablet (≤900px):** `.home-right` hidden earlier to save space.
- **Preserved:** Left sidebar icon colors, hover states, ad card styling on desktop.

### `templates/base.html` — **UPDATED**
- Added `<link rel="stylesheet" href="{{ url_for('static', filename='css/global/mobile-utilities.css') }}">`.
- **Profile-incomplete banner:** Removed inline `style=` block, replaced with `class="banner-incomplete"` and `style="--banner-offset: 0px;"`.
- **Impersonation banner:** Removed inline `style=` block, replaced with `class="banner-impersonation"`, added semantic classes `.banner-icon`, `.banner-title`, `.banner-timer`, `.btn-banner-exit`, `.btn-banner-restrict`.
- **Responsive stacking:** Added `@media (max-width: 768px)` rules in `style.css` for `.banner-incomplete .container-fluid .row` and `.banner-impersonation .container-fluid .row` to stack columns vertically with centered text.

### `static/css/modules/wallet/wallet.css` — **UPDATED**
- `.wallet-balance-amount`: `font-size: clamp(1.8rem, 5vw, 3rem)` (was fixed `3rem`).
- `.wallet-title`: `font-size: clamp(1.5rem, 4vw, 2.5rem)` (was fixed `2.5rem`).
- **Tablet breakpoint:** Added `@media (max-width: 1024px)` making `.wallet-grid-cols-3` use `repeat(2, 1fr)`.
- **Preserved:** All wallet card gradients, shadows, button colors, and spacing scale.

### `static/css/modules/accommodation/checkout.css` — **NEW**
- Extracted checkout styling from inline `<style>` block in `checkout.html` into dedicated module CSS.
- Added responsive grids: `.booking-type-grid`, `.payment-method-grid`, `.timing-grid` using `repeat(auto-fit, minmax(..., 1fr))`.
- Added selected states with `.selected` class, checkmark badges via `::after`, and hover lift effects.
- Added validation feedback styling `.checkout-feedback.show` with shake animation.
- Mobile breakpoints: grids collapse to 1 column at `max-width: 480px`, 2 columns at `max-width: 768px`.
- **Preserved:** All brand colors, no color/theme changes.

### `templates/accommodation/guest/checkout.html` — **UPDATED**
- Converted from single-page form to 4-step wizard: Guest Details → Special Requests → Payment → Review & Confirm.
- Extracted inline `<style>` wizard styles to `static/css/modules/accommodation/checkout.css`.
- Replaced inline `style="display: none;"` on `#thirdPartySection` and `#groupSection` with CSS class `.hidden-section`.
- Removed inline `<script>` block and moved all interactive logic to `static/js/modules/accommodation/checkout.js`.
- Added `{% block module_scripts %}` for external JS reference.
- Wizard step indicator uses `.step-indicator`, `.step`, `.step-number`, `.step-label`, `.wizard-step`, `.btn-wizard` classes.
- **Mobile:** Step labels shrink at ≤480px; grids remain responsive.
- **Preserved:** All form fields, hidden inputs, Bootstrap layout classes, and brand colors.

### `static/css/modules/accommodation/checkout.css` — **UPDATED**
- Added wizard styles: `.step-indicator`, `.step`, `.step-number`, `.step-label`, `.wizard-step`, `.btn-wizard`.
- Added `.hidden-section` utility class for display:none sections.
- Added `.payment-method-wrapper` class for timing-based payment method filtering.
- **Mobile:** Added `@media (max-width: 480px)` reducing step badge size and font size.
- **Preserved:** All existing checkout card styles, gradients, shadows, and responsive grids.

### `static/js/modules/accommodation/checkout.js` — **UPDATED**
- Wrapped all code in an IIFE to eliminate global scope pollution; no global functions remain.
- Replaced all inline `onclick` handlers with event delegation using `data-*` attributes (`data-booking-type`, `data-next-step`, `data-prev-step`, `data-method-id`, `data-timing-value`, `data-validate`).
- Added `sessionStorage` persistence for wizard step state: `showStep()` saves the current step; `DOMContentLoaded` restores it on page reload; step is cleared on successful form submission.
- Implements wizard navigation: `showStep()`, `nextStep()`, `prevStep()`, `validateAndNext()`.
- Implements selection handlers: `selectBookingType()`, `selectPaymentMethod()`, `selectTiming()`.
- Handles timing-based payment method visibility via `.payment-method-wrapper` `data-timing` filtering.
- Form submit validation: terms checkbox, payment/timing selection, spinner state; clears sessionStorage on successful submit.
- Event listeners: deposit percentage change, guest count change, room count change.
- DOMContentLoaded initialization: restores step from sessionStorage, restores timing/payment/booking state.

### `templates/accommodation/guest/detail.html` — **UPDATED**
- Added live AJAX availability checking: calls `/accommodation/api/availability` on date/guest change.
- Added `live_availability_results` container with real-time feedback (available units, partial availability, blocked dates, alternatives).
- Submit button disabled when no availability found.
- Shows Tier 0/1/2 cascade results (exact match, same-property alternatives, nearby properties).
- Shows partial availability messaging ("Booked until X, available from Y").
- **Preserved:** Existing date validation, room type selection, and price breakdown rendering.

### `static/css/modules/user/dashboard.css` — **UPDATED**
- `.greeting-text`: `font-size: clamp(1.25rem, 4vw, 2rem)` (was fixed `24px`).
- `.stats-grid`: Added mobile override `@media (max-width: 768px)` with `repeat(auto-fit, minmax(160px, 1fr))` and reduced gaps.
- `.section-card`: `padding: clamp(1rem, 3vw, 2rem)` (was fixed `2rem`).
- **Preserved:** Card shadows, hover lifts, icon backgrounds, accent colors.

### `templates/events/attendee/attendee_dashboard.html` — **UPDATED**
- Removed inline `style="display:flex; height:100%;"` from upcoming registration card wrappers.
- Removed inline `style="display:flex;"` from past registration card wrappers.
- Removed `min-width: 240px` from `.reg-actions` (was causing overflow on phones).
- Added `.reg-card-inner` class to replace inline flex wrappers.
- Made `.reg-card` itself `display: flex` for consistent layout.
- **Mobile (≤768px):** `.reg-actions` gets `width: 100%` and `justify-content: flex-start`; `.reg-badges` gets `width: 100%` and `margin-bottom: 0.5rem` so badges stack above action buttons.
- **Preserved:** All AFCON brand colors, badge status colors (green/orange/red/blue), card shadows.

### `static/css/modules/admin/owner.css` — **UPDATED**
- Added `.sad-mobile-drawer`, `.sad-mobile-drawer-overlay`, `.sad-mobile-header`, `.sad-mobile-close`, `.sad-mobile-nav-item` with full mobile drawer styling.
- Added `@media (max-width: 768px)`:
  - `.sad-sidebar { display: none; }`
  - `.sad-mobile-drawer`, `.sad-mobile-drawer-overlay { display: block; }`
  - `.sad-stats`, `.sad-twocol`, `.sad-qa`, `.sad-settings-grid` → `grid-template-columns: 1fr`
  - `.sad-topbar`, `.sad-content` padding reduced to `1rem`.
- **Preserved:** All existing `.sad-*` component styles, gradients, dark theme colors. Duplicate CSS blocks intentionally left untouched (separate cleanup PR).

### `templates/super_admin_dashboard.html` — **UPDATED**
- Added hamburger button (`#sadMobileMenuBtn`) in `.sad-topbar-actions` with inline baseline styling.
- Added full mobile drawer markup (`#sadMobileDrawer`) with overlay (`#sadDrawerOverlay`) and close button.
- Drawer includes all sidebar nav links: Dashboard, Users, Organizations, Events, Content Mgmt, Settings, Impersonate, Switch Persona, Owner Panel.
- Added JavaScript at bottom of page for drawer toggle, overlay click-to-close, resize handler to show/hide hamburger.
- **Preserved:** All existing SAD layout, sidebar links, topbar actions on desktop.

### `static/css/modules/accommodation/detail.css` — **UPDATED**
- `.sbb-cta`: Added explicit `@media (max-width: 768px)` rule enforcing `min-height: 44px; min-width: 44px` touch target.
- **Preserved:** Existing sticky book bar layout, safe-area padding, CTA colors.

### `templates/accommodation/admin/properties.html` — **UPDATED**
- Replaced the "Toggle Active" button with a moderation workflow: Review, Edit, Approve (pending only), Reject (pending only).
- Property status badges remain; action cells use flex-wrap for mobile stacking.
- CSRF tokens added to all POST forms.

### `templates/accommodation/moderate_property.html` — **UPDATED**
- Fixed `property.status.value` and `property.property_type.value` to handle String columns.
- Fixed `property.max_capacity` → `property.max_guests` and `property.base_price` → `property.base_price_per_night`.
- Added Suspend button for active properties and CSRF tokens to all moderation forms.
- Added property photos display (main_image + gallery).
- **2026-07-25:** Wired `ModerationService.get_available_actions()`, `get_property_status_display()`, and `get_property_status_color()` so action buttons and status badges are status-driven (approve/publish/reject/request changes/suspend/reinstate/archive). Added ≥44px touch targets on `.btn-mod`, fluid action-button sizing, and ≤480px stacked action layout. Header shows `public_id` (not raw internal id).
- **2026-07-25 (archive recovery):** Soft-delete archive stores reason/timestamp; archived status shows restore CTA + archive reason banner; Restore action returns property to draft with confirm dialog.

### `static/css/modules/accommodation/moderate_base.css` — **UPDATED**
- Removed custom dark-theme variables (`--ink`, `--surface`, `--panel`, `--gold`, `--text`, `--muted`, etc.).
- Replaced all values with global AFCON360 theme variables (`--bg-surface`, `--border-light`, `--brand-primary`, `--brand-accent`, `--text-primary`, `--text-muted`, `--success`, `--danger`, `--warning`, etc.).
- Updated `.panel`, `.panel-header`, `.panel-body`, `.badge-*`, `.form-*`, `.btn-*` to use global semantic colors and spacing scale.
- Added responsive breakpoints: `@media (max-width: 1024px)` for wrapped action buttons; `@media (max-width: 480px)` for stacked mobile header, full-width buttons, and reduced panel padding.
- Added utility classes: `.hidden`, `.mono`, `.mt-1`.

### `static/css/modules/accommodation/moderate_detail.css` — **UPDATED**
- Added `.info-span-2` (`grid-column: 1 / -1`) to replace inline `grid-column: span 2`.
- Added `.photo-grid` and `.photo-thumb` classes for property image thumbnails.
- Added `.form-actions` class for button groups in forms.
- Added responsive overrides: single-column info grid on ≤1024px, smaller photo thumbs on ≤480px.

### `templates/accommodation/moderate.html` — **UPDATED**
- Removed inline `style="display: flex; align-items: center;"` from header row.
- Removed inline `style="font-weight: 600; color: var(--text);"` from property title cell.
- Removed inline `style="font-size: 11px; margin-top: 2px;"` from slug cell.
- Wrapped data tables in `div` with `overflow-x: auto` for horizontal scroll on narrow screens.
- **Preserved:** All tab counts, badge states, empty states, and action links.

### `templates/accommodation/moderate_review.html` — **UPDATED**
- Removed inline `style="display: flex; align-items: center;"` from header row.
- Removed inline `style="grid-column: span 2;"` from comment/host response cells.
- Replaced inline `onclick="...style.display='block'"` with `classList.remove('hidden')` toggling.
- Replaced inline `style="display: none;"` panels with `class="hidden"`.
- Replaced inline `style="display: flex; gap: 12px;"` button groups with `class="form-actions"`.

### `templates/accommodation/host/bookings.html` — **UPDATED**
- Added Approve and Reject inline forms for `pending_approval` bookings with CSRF tokens.
- Buttons use existing Bootstrap table action cell; no layout breakage on mobile.
- Preserved existing Check In / Check Out buttons for confirmed and checked_in statuses.

### `templates/accommodation/host/property_manage.html` — **NEW**
- Full property management dashboard for hosts/admins.
- Shows: occupancy stats, notifications (check-ins, check-outs, low availability), room types overview with stock status, active bookings table with guest info and cancel action, blocked dates table with release button, block-date form, recent booking history.
- Mobile responsive: stats grid collapses to single column on small screens, tables scroll horizontally, action buttons stack vertically under 480px.

### `templates/accommodation/host/room_availability.html` — **NEW**
- Room-type availability calendar showing 90-day window with per-day status (available/booked/blocked).
- Mobile responsive: table scrolls horizontally on narrow viewports, legend and stats stack vertically.

### `templates/accommodation/host/dashboard.html` — **UPDATED**
- Added "Manage" button to each property listing action row, linking to `host_property_manage` endpoint.
- Manage button styled with green accent (`#047857`) to distinguish from Edit action.

### `templates/accommodation/host/rooms.html` — **UPDATED**
- Renamed `categories` → `room_types`, `category` → `room_type` throughout template.
- Renamed `host_room_category_add` → `host_room_type_add` endpoint.
- Renamed `host_room_category_edit` → `host_room_type_edit` endpoint.
- Renamed form field `category_id` → `room_type_id`.
- Updated "Add Room Category / Type" heading → "Add Room Type".
- Updated flash messages: "Category name" → "Room type name", "Room category" → "Room type".
- Updated "No room categories yet" → "No room types yet" and "No rooms in this category yet" → "No rooms in this type yet".

### `templates/accommodation/host/booking_detail.html` — **UPDATED**
- Added Approve Booking button at top of actions card for `pending_approval` status.
- Added collapsible Reject Booking form with reason input and CSRF token.
- Existing Check In / Check Out / Refund / View Property actions remain unchanged.
- **Preserved:** Existing card grid layout, button sizing, and mobile stacking behavior.

### `templates/accommodation/host/booking_policy.html` — **UPDATED**
- Fixed payment-method checkbox pre-check state: changed `policy.property_payment_methods` to `property.payment_methods` in the Jinja `selectattr` lookup so enabled methods render correctly when the host edits booking policy.
- Changed payment method checkbox `value` from numeric `m.id` to string `m.method_id` (e.g., `"cash"`, `"wallet"`) for stable, human-readable identifiers.
- Changed checkbox `id` attribute from `method_{{ m.id }}` to `method_{{ m.method_id }}` for consistency.
- Added "Cash Payment Protection" section with fields: `allow_cash_payments`, `cash_requires_deposit`, `cash_deposit_percentage`, `cash_max_amount`, `cash_min_kyc_level`, `cash_min_previous_bookings`, `cash_requires_verified_guest`.
- Added "Guest Registration Requirements" section with checkboxes for each configurable field: `full_name`, `phone`, `email`, `id_document_type`, `id_document_number`, `date_of_birth`, `nationality`.
- **Preserved:** Existing form layout, payment timing fields, cancellation policy dropdowns, and CSRF tokens.

### `templates/accommodation/admin/booking_detail.html` — **NEW**
- Admin booking detail page with Owner info panel, Guest Manifest table, check-in readiness gate, override registration button, and audit log section.
- Mobile-responsive card layout with standard Bootstrap table classes and CSRF token on override form.

### `templates/accommodation/admin/bookings.html` — **UPDATED**
- Added Owner column (booking owner or booker), Claimed status badge (Yes/No), and Guests Registered badge count.
- Added quick-filter widgets for unclaimed bookings and readiness issues at the top of the list.
- Mobile-responsive table with horizontal scroll wrapper for small viewports.

### `templates/owner/dashboard.html` — **UPDATED**
- Added Unclaimed Bookings and Check-in Blockers stat cards with links to accommodation admin bookings.
- Widgets display accommodation module health metrics for the owner.
- Preserved existing dashboard layout, stats grid, and all navigation cards.

### `templates/super_admin_dashboard.html` — **UPDATED**
- Added Accommodation Overview card with Total Bookings, Unclaimed Bookings, Readiness Issues, and Active Properties widgets.
- Quick links to manage bookings from the dashboard.
- Preserved existing sidebar navigation, emergency controls, and module management sections.

### `templates/admin/accommodation_admin_dashboard.html` — **UPDATED**
- Added Unclaimed Bookings and Check-in Blockers stat cards with links to admin bookings.
- Preserved existing stats grid, quick actions, and module settings sections.**
- Owner claiming page for third-party bookings. Displays booking summary (reference, property, dates, guest name) and offers two paths: "I already have an AFCON360 account" (login form) and "Create an account" (redirect to registration with pre-filled email).
- Mobile-responsive card layout with standard Bootstrap form controls and CSRF token.

### `templates/accommodation/guest/register.html` — **UPDATED**
- Added `date_of_birth` (date input) and `nationality` (text input) form fields to support host-configurable registration requirements.
- **Preserved:** Existing layout, mobile stacking, and CSRF token.

### `templates/owner/cash_settings.html` — **NEW**
- Global cash payment settings page for Owner: development mode toggle, KYC requirements, verification requirements, booking history requirements, amount limits, and default deposit percentage.
- Uses Bootstrap responsive grid, mobile-stacked form controls, CSRF token, and standard form conventions.

### `templates/owner/dashboard.html` — **UPDATED**
- Added "Cash Settings" card linking to `admin.owner.owner_settings.owner_cash_settings` route.
- **Preserved:** Existing dashboard layout, stats grid, and all navigation cards.

---

## 3. What Was NOT Changed (Explicitly Preserved)

| Item | Status | Notes |
|------|--------|-------|
| Brand color palette | **UNCHANGED** | No hex values modified in `theme-variables.css` or any component CSS |
| Gradients | **UNCHANGED** | Header, wallet balance, hero banners, SAD cards untouched |
| Desktop layout | **UNCHANGED** | All `grid-template-columns: 220px 1fr 240px` and sidebar behaviors preserved above 1024px |
| Fonts | **UNCHANGED** | Montserrat / Open Sans imports unchanged |
| Shadows | **UNCHANGED** | `--shadow-sm`, `--shadow-md`, `--shadow-lg` values untouched |
| Border radius | **UNCHANGED** | `--radius: 10px` and all component radii preserved |
| Owner.css duplicate blocks | **NOT TOUCHED** | Left as-is; duplicate CSS cleanup is a separate task |
| Wallet logic | **NOT TOUCHED** | No Python/wallet model changes |
| Database/migrations | **NOT TOUCHED** | Zero schema changes |

---

### `templates/admin/compliance/cases.html` — **UPDATED**
- Line 130 SLA overdue check: fixed `case.sla_due_at < now` comparison. The route passes a naive `now` (`datetime.now()`) matching the naive `sla_due_at` column; previously an aware `datetime.now(timezone.utc)` caused a `TypeError` (offset-naive vs offset-aware) and a 500 on `/admin/compliance/cases`.
- **Mobile:** No layout/CSS changes; SLA column already uses responsive table classes.

### `templates/admin/compliance/view_case.html` — **FIXED**
- Line 50 SLA overdue check: fixed `case.sla_due_at < now` comparison. The `view_case` route previously relied on the global `now` (which is the `datetime.now` function, not a datetime) and raised a 500 (`'<'` not supported between `datetime` and `builtin_function_or_method`). Now the route passes a naive `datetime.now()` matching the naive `sla_due_at` column (consistent with `cases.html`).

### `templates/admin/compliance/view_case.html` — **UPDATED**
- Fixed SLA overdue comparison (`case.sla_due_at < now`); route now passes naive `datetime.now()` (see `cases.html` entry).
- Wired `notes` and `history` into the template (previously undefined — `view_case` route now passes `ComplianceCaseService.get_case_notes()` and `get_case_history()`).
- Extended the actions footer: added **Request Info** (text input + post), **Close** (confirm), and a terminal-state **Reopen Case** footer shown when the case is resolved/closed. All actions use `?_pane` safe POST forms with `{{ csrf_token() }}`.
- Fixed `url_for('admin.compliance.view_kyc', kyc_id=...)` → `kyc_id_or_uuid=...` to match the route signature (`view_case.html:220`). Same latent bug fixed in `escalations.html` and `dashboard.html` to prevent `BuildError` 500s.
- History timeline now uses `entry.author.username` (removed the duplicate `user` relationship on `ComplianceCaseNote` that triggered an SQLAlchemy overlapping-relationship warning). No layout change.

### `templates/admin/compliance/aml_queue.html` — **REWRITTEN (full AML dashboard)**
- Now fully wired to real data from the `FraudAlert` store (the suspicious-activity monitoring engine) via the `aml_queue` route — no functionality removed.
- Renders: stat row (critical alerts, high-risk TX, suspicious users, today's volume), **High-Risk Transactions** table (joined to `TransactionModel`, paginated), **Pattern Alerts** (active alerts aggregated by detected pattern with severity), **Flagged Users** sidebar (distinct users with active high-risk alerts), and a Quick Actions panel (Export AML Report, File SAR, Case History).
- Drill-downs restored: each high-risk TX links to `admin.compliance.view_transaction` and each flagged user to `admin.compliance.user_audit`.
- **Mobile:** `col-layout-8-4` collapses to single column ≤900px; `detail-grid`/tables use responsive card classes; `≥44px` touch targets on Investigate/View buttons.

### `templates/admin/compliance/view_transaction.html` — **ADDED**
- Transaction investigation drill-down (route `admin.compliance.view_transaction`, keyed by transaction UUID). Shows TX type/status/amount/fees/provider, actor & recipient links, and all related `FraudAlert` records with risk scores and status.
- **Mobile:** Responsive `.detail-grid` (2-col → 1-col ≤560px), `.data-table` for alerts, `≥44px` back/action buttons.

### `templates/admin/compliance/user_audit.html` — **ADDED**
- User audit drill-down (route `admin.compliance.user_audit`, keyed by user `public_id`). Shows profile, KYC risk score/status, that user's `FraudAlert` history, and linked compliance cases — the compliance-grade 360° view regulators/partners expect.
- **Mobile:** Responsive `.detail-grid`, `.data-table` for alerts/cases, `≥44px` back/action buttons.

### `templates/admin/compliance/sar_filing.html` — **ADDED**
- New template for the Suspicious Activity Report (SAR) filing workflow, kept separate from the moderation `escalations` queue.
- Provides a `csrf_token()`-protected form to file a SAR (`ComplianceReport` of type `REGULATORY_FILING`), a list of open AML alerts to attach, and a list of previously filed SARs.
- **Mobile:** Mirrors `aml_queue.html` responsive patterns — `stat-grid`, `.data-table`, stacked cards, `≥44px` touch targets; no fixed `min-width` or `overflow: hidden` on dropdowns/layout containers.

### `templates/admin/compliance/base_compliance.html` — **UPDATED**
- Added `.detail-grid`, `.detail-row`, `.detail-label`, `.detail-value` CSS (2-col grid → 1-col ≤560px) used by `view_transaction.html` and `user_audit.html` for responsive key/value layouts. Preserves existing theme variables and branding; no color/hex changes.

---

## 4. Verification Checklist

- [x] `mobile-utilities.css` loaded in `base.html`
- [x] All `clamp()` values tested mentally against 320px, 375px, 768px, 1024px viewports
- [x] No hardcoded `repeat(4, 1fr)` or `repeat(3, 1fr)` grids remain in touched files
- [x] All `min-width: 240px` / `min-width: 110px` removed from mobile-bound components
- [x] `env(safe-area-inset-bottom)` applied to footer, sticky bars, mobile drawers
- [x] Touch targets ≥44×44px on hamburger, drawer links, CTA buttons, admin nav items
- [x] Checkout grids use `repeat(auto-fit, minmax(..., 1fr))` and collapse to 1 column at `max-width: 480px`
- [x] Checkout inline `<style>` block removed; styles moved to `static/css/modules/accommodation/checkout.css`
- [x] No inline `style="display:flex"` wrappers remain in checkout template
- [x] Super admin mobile drawer has overlay, close button, and escape-via-resize
- [x] No inline `style="display:flex"` wrappers remain in attendee dashboard
- [x] No inline layout styles remain in `moderate_property.html`, `moderate.html`, or `moderate_review.html`
- [x] Moderation pages use global theme variables (no custom `--ink`, `--surface`, `--gold` dark-theme tokens)
- [x] Moderation panels have `border-radius: var(--radius-lg)` and `box-shadow: var(--shadow-sm)` matching global `.card`
- [x] Banners use CSS classes with `--banner-offset` instead of hardcoded `top: 40px`
- [x] No color/hex changes in any CSS file
- [x] `claim_booking.html` uses responsive card layout with standard Bootstrap form controls
- [x] `register.html` date_of_birth and nationality fields use responsive grid stacking on mobile
- [x] `super_admin_dashboard.html` Accommodation Overview card uses responsive stat grid
- [x] `owner/dashboard.html` accommodation widgets use responsive stat cards with mobile stacking
- [x] `accommodation_admin_dashboard.html` widgets use responsive stat grid
- [x] All dashboard widgets use `|default(0)` fallbacks for missing data

---

## 5. Future Optimization Isolation Plan

When the next optimization phase begins, use this file to **scope** changes:

### Phase 2 Isolation Targets (reserved filenames)
- `static/css/global/home-mobile.css` — homepage-only mobile overrides (bottom nav bar, search bar refinements)
- `static/css/modules/events/mobile.css` — event list/registration mobile tweaks
- `static/css/modules/wallet/mobile.css` — wallet dashboard/forms mobile tweaks

### Phase 3 Isolation Targets
- `static/css/modules/accommodation/mobile.css` — listing cards, search, booking flow
- `static/css/modules/accommodation/moderation-mobile.css` — moderation detail pages, queue tables, collapse forms
- `static/css/modules/transport/mobile.css` — bookings, vehicles, driver dashboards
- `static/css/modules/admin/mobile.css` — owner/admin dashboard mobile refinements

### Pattern to Follow
1. Add new mobile-only CSS file in the relevant module folder.
2. Link it in `base.html` or module-specific template blocks **after** the main module CSS.
3. Use `.mobile-only` or `@media (max-width: 768px)` within that file.
4. Document changes here in a new dated section.

---

## 6. Known Limitations / Deferred

- **Owner.css duplicate blocks** (~300 lines of repeated `.stats-row` / `.stat-card` rules) intentionally left untouched.
- **Theme variables expansion** (`--header-height-mobile`, etc.) deferred; current fixed values are acceptable.
- **Wallet dashboard inline styles** (`templates/wallet/wallet_dashboard.html`) deferred; functional but lower priority than the CSS file itself.

---

## 7. Post-Change Report

**Files changed:** 13 files (1 new template, 2 updated templates, 1 updated doc)
**What was done:** 
- Extracted accommodation checkout styles from inline `<style>` into dedicated `static/css/modules/accommodation/checkout.css`.
- Fixed payment timing and payment method card selection states with `.selected` class, checkmark badges, and hover effects.
- Added proper validation feedback blocks (`.checkout-feedback.show`) with shake animation instead of inline text.
- Made payment timing and method cards deselectable by removing `required` and handling validation in JavaScript.
- Wired owner-only payment method management into existing owner settings page (`/owner/settings/wallet` → Payment Methods tab).
- Added host dashboard payment settings widget linking to per-property booking policy.
- Added `cash` to `PaymentMethodConfig.initialize_defaults()` so it is no longer hardcoded.
- Updated property 2 booking policy to allow `pay_on_arrival` and `deposit`.
- Added `claim_booking.html` template for third-party booking ownership transfer (login/registration options).
- Added `date_of_birth` and `nationality` fields to guest registration form.
- Added "Guest Registration Requirements" section to booking policy host UI.
- Updated README.md, PAYMENT_ARCHITECTURE.md, and MOBILE_OPTIMIZATION.md with new payment settings wiring.

**Migration needed?** No
**Manual steps:** 
1. Restart Flask server.
2. Owner visits `/owner/settings/wallet` → Payment Methods tab to enable/disable methods.
3. Host visits `/host/property/2/booking-policy` to enable Cash and payment timings for the property.
4. Test checkout at `/accommodation/guest/hotel-yriad` to verify Wallet + Cash cards and Pay Now / Deposit / Pay on Arrival timings appear.
5. Test third-party booking claim flow at `/guest/booking/claim/<token>`.
6. Test guest registration with required fields at `/guest/booking/<id>/register`.

**Risks/conflicts:** No schema changes. Owner endpoints protected by `@require_owner role`. Host booking policy already had payment-method saving logic. No colors, branding, or desktop layout were altered.

---

## 8. KYC Dashboard Progress Tracker (2026-08-05)

**Scope:** Added a visual CSS step progress tracker to the KYC dashboard showing verification stages (Submitted → Processing → Verified).  
**Risk Level:** Low (CSS/template only, no schema changes)

### File Tree — What Was Touched
```
templates/
└── kyc/
    └── index.html                      ← UPDATED (replaced placeholder panel with CSS step progress tracker)
static/
└── css/
    └── dashboard.css                   ← UPDATED (added .panel base styles + .kyc-progress-tracker step styles)
```

### Change Log by File

#### `templates/kyc/index.html` — **UPDATED**
- Replaced the static "Verification Progress" placeholder with a 3-step CSS progress tracker: **Submitted → Processing → Verified**.
- Each step renders a circle, label, and sub-status (Pending / In Review / Approved, plus Rejected and Start states).
- The active step gets a pulsing ring; completed steps are filled with brand color; rejected shows a red X.
- A contextual caption under the tracker explains the current state.
- Stage + status are driven by `kyc_stage` and `overall_status` passed from the `kyc.index` route.

#### `static/css/dashboard.css` — **UPDATED**
- Added generic `.panel` / `.panel-header` / `.panel-title` / `.panel-body` base styles (previously only defined in module-specific CSS, not loaded on KYC pages).
- Added `.kyc-progress-tracker` component:
  - Flex-based 3-step layout with a connecting line that fills via `data-progress="33|66|100"`.
  - `.step-circle`, `.step-icon`, `.step-label`, `.step-sub` with completed / active (pulse) / rejected states.
  - Uses theme variables (`--brand-primary`, `--success`, `--danger`, `--bg-surface`) — preserves branding.
  - `@media (max-width: 768px)` and `@media (max-width: 480px)` shrink circle/label sizes and tighten padding for phones.
  - No fixed `min-width` on steps; flex distribution prevents horizontal scroll.
- Added `.kyc-progress-tracker` to the print-hide block.

### Verification Checklist
- [x] Steps use `flex: 1` with no fixed width → no overflow at 320px.
- [x] Step circles/labels scale down at ≤768px and ≤480px.
- [x] Touch targets (circles) remain ≥28px on small screens.
- [x] Branding colors (`#2d5a2d`, `#ffcc00`) preserved via theme variables.
- [x] `overflow: hidden` not used on the tracker container (only on `.panel` overflow clip, which is fine).

**Migration needed?** No  
**Manual steps:** Restart Flask server; visit `/kyc/` to see the tracker. Submitting a National ID (status `manual_review`/`pending`) advances to Processing; approval advances to Verified.  
**Risks/conflicts:** Purely presentational. `kyc.index` route now passes two extra template variables (`kyc_stage`, `overall_status`); no other template consumes them. No schema, color, or branding changes.

---

### AML Regulatory Module (2026-08-11) — NEW

A jurisdiction-aware AML/CFT regulatory program was added under `app/compliance/`
(models + service) and `app/admin/compliance/routes.py`, with 10 new admin
templates plus a shared nav partial. All pages extend `base_compliance.html`, are
mobile-responsive, and use `{{ csrf_token() }}` on every POST.

#### `templates/admin/compliance/_aml_nav.html` — **ADDED**
- Shared `aml_nav()` macro: a wrapping flex row of quick-nav buttons linking all
  AML program pages. Used by every AML template for in-module navigation.

#### `templates/admin/compliance/aml_jurisdictions.html` — **ADDED**
- Lists `JurisdictionProfile` rows (threshold, STR SLA, report types, identifiers,
  retention). **Mobile:** flex-wrapping nav; responsive `.data-table`.

#### `templates/admin/compliance/aml_reports.html` — **ADDED**
- Lists `RegulatoryReport` filings (STR/SAR/CTR/IWTR/TFR) with status + pagination.

#### `templates/admin/compliance/aml_report_detail.html` — **ADDED**
- Report detail (`.detail-grid`), narrative, "Mark as Filed" POST form, and a
  scrollable `<pre>` of the generated goAML XML.

#### `templates/admin/compliance/aml_ctr.html` — **ADDED**
- CTR / structuring alerts table + "Run Detection" POST button; per-user drill-down.

#### `templates/admin/compliance/aml_terminated.html` — **ADDED**
- Terminated-entity (MATCH/VMSS) registry table + add form (grid inputs).

#### `templates/admin/compliance/aml_scenarios.html` — **ADDED**
- Monitoring scenarios table + add form + inline per-row calibrate form
  (enable/disable, weight, threshold).

#### `templates/admin/compliance/aml_backtest.html` — **ADDED**
- Back-test run form (scenario + window days), last-run result grid, history table.

#### `templates/admin/compliance/aml_training.html` — **ADDED**
- Training records table + add form (grid inputs).

#### `templates/admin/compliance/aml_attestations.html` — **ADDED**
- MLRO attestation register + add form.

#### `templates/admin/compliance/aml_retention.html` — **ADDED**
- Retention policy + aged-record summary table.

#### `templates/admin/compliance/aml_queue.html` — **UPDATED**
- Added `{{ aml_nav('queue') }}` for in-module navigation.

**Mobile:** All new pages reuse existing responsive primitives (`.card`,
`.data-table`, `.stat-grid`, `.detail-grid`, `.pagination`, `.badge`, `.btn` with
`≥44px` touch targets). Form grids use `repeat(auto-fit, minmax(...))` and
collapse to one column on phones; no fixed `min-width` or `overflow: hidden` on
layout containers. Branding/theme variables preserved; no color changes.

**Migration needed?** Yes — new tables (`aml_jurisdiction_profiles`,
`aml_regulatory_reports`, `aml_ctr_alerts`, `aml_terminated_entities`,
`aml_organisation_profiles`, `aml_monitoring_scenarios`, `aml_backtest_runs`,
`aml_training_records`, `aml_attestations`, `aml_retention_policies`). Run
`flask db migrate -m "aml_regulatory"` then `flask db upgrade` (not auto-run;
user handles migrations).

---

### Targeted KYC/KYB document replacement (2026-08-11) — UPDATED

#### File Tree — What Was Touched
```
app/
├── kyc/reupload.py                         ← NEW (signed replacement state helpers)
├── kyc/routes.py                            ← UPDATED (user-scoped replacement flow)
├── admin/compliance/routes.py               ← UPDATED (individual + organisation requests)
└── notifications/services.py                ← UPDATED (replacement notification)
templates/
├── kyc/status.html                          ← UPDATED (replacement alerts and links)
├── kyc/verify_upload.html                   ← UPDATED (focused replacement form)
├── profile/account.html                      ← UPDATED (authoritative KYC status display)
└── admin/compliance/
    ├── view_kyc.html                        ← UPDATED (targeted reviewer action)
    └── view_org.html                        ← NEW (KYB document review actions)
```

#### Responsive Change Log
- `templates/kyc/status.html`: replacement cards wrap on mobile and keep the action button usable without horizontal scrolling.
- `templates/kyc/verify_upload.html`: the focused replacement panel uses fluid padding and a single-column file form on small screens.
- `templates/profile/account.html`: KYC status and rejection notices now use the current review context without changing responsive layout behavior.
- `templates/admin/compliance/view_kyc.html` and `view_org.html`: reviewer action grids use `auto-fit` and wrapping controls for phone and tablet widths.

### Verification Checklist
- [x] Replacement cards and forms wrap at mobile widths.
- [x] File inputs and action buttons remain accessible on touch devices.
- [x] No fixed layout `min-width` was added to the replacement workflow.
- [x] `static/MOBILE_OPTIMIZATION.md` updated for every changed HTML template.

**Migration needed?** No — replacement metadata is stored in existing compliance notes.

---

### KYC Progress Tracker Layout Fix (2026-08-11) — UPDATED

#### File Tree — What Was Touched
```
static/
└── css/
    └── dashboard.css                   ← UPDATED (fixed KYC progress tracker layout)
templates/
└── kyc/
    └── index.html                      ← UPDATED (standardized icons, centered panel body)
```

#### What Changed
- Fixed text/icon overlap in the KYC progress stepper by converting `.step-item` to `flex-direction: column` with `align-items: center`, ensuring icons, labels, and sub-labels stack cleanly above the connecting line.
- Standardized stepper icons: checkmarks for completed steps, spinner (`bi-arrow-repeat`) for active processing, circle outline for pending/upcoming, and red X for rejected.
- Centered the tracker and status message inside the panel body using flexbox, eliminating excess vertical whitespace.
- Increased contrast and weight on `.step-sub` badges so status labels (PENDING, IN REVIEW, APPROVED) are more readable.
- Improved mobile scaling: circles shrink to 34px at ≤768px and 30px at ≤480px; labels and sub-labels use relative font sizes.

#### Responsive Change Log
- `.kyc-progress-tracker .step-item` now uses flex column layout instead of inline text centering, preventing text-over-line collisions on all viewports.
- `.step-label` and `.step-sub` are block-level with proper `margin-top` spacing.
- Panel body uses `display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:280px` to balance whitespace.
- No fixed `min-width` or `overflow: hidden` introduced.

#### Verification Checklist
- [x] Stepper icons no longer overlap with text or connecting line.
- [x] Status badges have sufficient contrast against background.
- [x] Layout is centered with balanced whitespace on desktop and mobile.
- [x] Icons are consistent across all three nodes (completed / active / pending / rejected).
- [x] `static/MOBILE_OPTIMIZATION.md` updated.

**Migration needed?** No  
**Manual steps:** Restart Flask server; visit `/kyc/` to verify the progress tracker.  
**Risks/conflicts:** Purely presentational. No schema, route, or model changes. Existing theme variables and brand colors preserved.

---

### Uniform KYC Tier Information Overhaul (2026-08-11) — UPDATED

#### File Tree — What Was Touched
```
app/
├── auth/kyc_compliance.py                    ← UPDATED (uniform tier response, requirement labels, activity restrictions)
├── profile/routes.py                         ← UPDATED (pass enriched kyc_info to edit template)
└── utils/immutable_fields.py                 ← UPDATED (specific blocked field error messages)
templates/
├── profile/account.html                      ← UPDATED (tier badge in hero, next-tier needs, restricted activities, immutable fields notice)
├── profile/account_pane.html                 ← UPDATED (tier badge with next-tier preview)
├── profile/edit.html                         ← UPDATED (KYC tier sidebar card with next-tier requirements)
├── admin/owner/kyc_tiers.html                ← UPDATED (tier description, next-tier needs, restricted activities columns)
├── admin/view_user.html                      ← UPDATED (enhanced KYC tier display with next-tier needs)
└── admin/update_profile.html                 ← UPDATED (KYC tier context and restricted activities alert)
```

#### What Changed
- `calculate_kyc_tier()` now returns a uniform dict with `tier`, `tier_name`, `tier_description`, `verification_status`, `is_verified`, `fulfillment_percentage`, `missing_requirements_labels`, `next_tier`, `next_tier_name`, `next_tier_requirements_labels`, `immutable_fields`, and `activities_restricted`.
- Added `REQUIREMENT_LABELS` mapping requirement keys to human-readable labels (e.g., `phone_verified` → `Phone verification`).
- Added `ACTIVITY_TIER_REQUIREMENTS` mapping platform activities to minimum KYC tiers.
- User-facing pages (`/account`, `/profile/edit`, dashboard pane) now show a single authoritative KYC tier badge, progress toward the next tier, exactly what is needed to advance, and which activities are currently restricted.
- Admin pages (`owner/kyc_tiers`, `view_user`, `update_profile`) now display the same uniform tier info so admins can see at a glance what a user needs and why certain actions are blocked.
- Immutable field error messages now list the exact blocked fields instead of a generic message.

#### Responsive Change Log
- `templates/profile/account.html`: KYC card uses stacked info blocks on mobile; tier badge replaces scattered status badges in the hero. No fixed widths added.
- `templates/profile/edit.html`: KYC tier sidebar card stacks naturally; next-tier list uses fluid padding.
- `templates/admin/owner/kyc_tiers.html`: Table columns wrap text with `truncate`; mobile horizontal scroll is preserved via existing `.table-responsive`.
- `templates/admin/view_user.html` and `update_profile.html`: Info blocks use responsive `.detail-grid` patterns already defined in base templates.

#### Verification Checklist
- [x] KYC tier badge is visible on `/account`, `/profile/edit`, and dashboard pane.
- [x] Next-tier requirements render as human-readable labels.
- [x] Restricted activities count displays correctly.
- [x] Immutable fields notice appears after verification with field list.
- [x] Admin owner KYC tiers table shows tier description, next needs, and restricted count.
- [x] Admin view user page shows enhanced KYC tier context.
- [x] No fixed `min-width` or `overflow: hidden` added to layout containers.
- [x] `static/MOBILE_OPTIMIZATION.md` updated for every changed HTML template.

**Migration needed?** No  
**Manual steps:** None. Restart Flask server to pick up updated templates and helper constants.  
**Risks/conflicts:** No schema changes. Backward-compatible — `calculate_kyc_tier()` retains all previously returned keys. No colors, branding, or desktop layout altered.

---

### Email verification OTP + link fix (2026-08-11) — UPDATED

#### File Tree — What Was Touched
```
app/
└── auth/otp_service.py                         ← UPDATED (verification_link in context, link on notification)
templates/
└── notifications/email/
    └── verification_email.html                 ← UPDATED (OTP code primary, clickable link fallback)
```

#### What Changed
- `OTPService.send_email_otp_checked` now includes `verification_code`, `verification_link`, and `user_name` in the notification context.
- `notification.link` is set to a purpose-aware URL (`/verify-signup`, `/verify-email`, or `/verify-phone`) so the fallback link is always clickable.
- `templates/notifications/email/verification_email.html` now displays the OTP code prominently as the primary verification method, with a clickable "Or click here to verify" button as fallback.
- Plain-text email body also includes the verification link.

#### Responsive Change Log
- `verification_email.html`: centered code display at `font-size: 28px` with `letter-spacing: 8px` for readability on mobile; button uses standard padding for touch targets; max-width container preserves readability on all viewports.

#### Verification Checklist
- [x] OTP code renders prominently in HTML email.
- [x] Fallback link is clickable and points to the correct verification page.
- [x] Plain-text email body includes the link.
- [x] `static/MOBILE_OPTIMIZATION.md` updated.

**Migration needed?** No  
**Manual steps:** Restart Flask server; trigger a verification email to confirm both OTP code and link render correctly.  
**Risks/conflicts:** No schema changes. Existing notification templates that reference `user_name` directly remain unchanged; only `verification_email.html` was fixed.

---

### Temporary phone verification via email (2026-08-11) — NEW

#### File Tree — What Was Touched
```
app/
└── auth/routes.py                            ← UPDATED (phone verification now routes through email OTP)
templates/
└── auth/
    └── verify_phone.html                     ← NEW (phone verification form with email OTP delivery)
```

#### What Changed
- `/verify-phone` GET now renders `templates/auth/verify_phone.html` instead of redirecting with a flash message.
- `/send-phone-verification` now generates a 6-digit OTP, stores it with purpose `phone_verification`, and delivers it via the existing `OTPService.send_email_otp_checked` pipeline (temporary replacement for SMS/Twilio).
- `/verify-phone` POST verifies the submitted code against the email-stored OTP using `OTPService.verify_otp` with purpose `phone_verification`.
- On success, `profile.phone_verified` is set to `True` and the session flag `phone_verified` is updated.

#### Responsive Change Log
- `templates/auth/verify_phone.html`: Centered card layout with `max-width: 480px`, fluid padding (`p-4 p-md-5`), and brand-aligned header border (`#ffcc00`).
- Form inputs use Bootstrap responsive classes; the code input is `text-center` with `form-control-lg` and `inputmode="numeric"` for mobile keyboards.
- Buttons use full-width `d-grid` layout and maintain ≥44px touch targets via Bootstrap's `.btn-lg`.
- No fixed `min-width` constraints; the card safely fits 320px viewports.

#### Verification Checklist
- [x] New template renders at `/verify-phone` for logged-in users.
- [x] OTP is delivered via email (check server logs for dev fallback OTP if mail is not configured).
- [x] Code entry form accepts 6 digits and strips non-numeric input client-side.
- [x] Resend button triggers a fresh OTP via POST to `/send-phone-verification`.
- [x] No fixed `min-width` or `overflow: hidden` on layout containers.
- [x] `static/MOBILE_OPTIMIZATION.md` updated.

**Migration needed?** No  
**Manual steps:** 
1. Ensure the logged-in user has an email address set on their account (`current_user.email`).
2. Ensure the user has a phone number in their profile (`profile.phone_number`).
3. Restart Flask server.
4. Visit `/verify-phone` to test the email-based phone verification flow.

**Risks/conflicts:** No schema changes. This is a temporary routing change — when Twilio/SMS is configured, revert `send_phone_verification` and `verify_phone` to use `SMSService`. Existing `SMSService` code is untouched. No colors, branding, or desktop layout altered.
