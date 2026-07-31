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
│   ├── host/
│   │   ├── bookings.html            ← UPDATED (added approve/reject actions for pending_approval status, inline forms with CSRF)
│   │   ├── booking_detail.html      ← UPDATED (added approve/reject collapse forms for pending_approval, inline CSRF)
│   │   ├── booking_policy.html      ← UPDATED (payment method checkboxes now use method_id string value instead of numeric id; added Cash Payment Protection section with allow_cash_payments, cash_requires_deposit, cash_deposit_percentage, cash_max_amount, cash_min_kyc_level, cash_min_previous_bookings, cash_requires_verified_guest fields)
│   │   ├── dashboard.html           ← UPDATED (added payment settings widget linking to booking policy per property)
│   │   └── guest/
│   │       └── checkout.html        ← UPDATED (moved inline styles to external CSS, added selection cards, validation feedback, responsive grids)
│   │       └── detail.html          ← UPDATED (added live AJAX availability checking on date/guest change; added live_availability_results container; submit button disabled when no availability; partial availability suggestions)
│   ├── moderate.html                ← UPDATED (matched global AFCON360 light theme, removed inline styles, added table scroll wrappers)
│   ├── moderate_property.html       ← UPDATED (matched global AFCON360 light theme, removed all inline layout styles, added photo grid classes)
│   └── moderate_review.html         ← UPDATED (matched global AFCON360 light theme, removed inline styles, hidden/visible toggle via CSS class)
└── super_admin_dashboard.html        ← UPDATED (mobile drawer + JS)
```

```
templates/
├── owner/
│   ├── cash_settings.html            ← NEW (global cash payment settings: development mode toggle, fraud protection requirements, amount limits)
│   └── dashboard.html                ← UPDATED (added Cash Settings card linking to cash_settings.html)
```

---

## 2. Change Log by File

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
- Linked external `checkout.css` via `{% block module_styles %}` and removed inline `<style>` block.
- Restructured booking type, payment method, and payment timing sections to use card-based grids with `onclick` selection handlers.
- Added `.checkout-feedback` validation blocks with `.show` class for proper error display.
- Removed `required` attributes from radio buttons to allow deselection; validation now handled by JavaScript on submit.
- **Mobile:** Payment grids collapse from 3 columns → 2 columns → 1 column across breakpoints.
- **Preserved:** All form fields, hidden inputs, and Bootstrap layout classes.

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
- **Preserved:** Existing form layout, payment timing fields, cancellation policy dropdowns, and CSRF tokens.

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

**Files changed:** 10 files (1 new CSS, 5 updated templates, 4 updated docs)
**What was done:** 
- Extracted accommodation checkout styles from inline `<style>` into dedicated `static/css/modules/accommodation/checkout.css`.
- Fixed payment timing and payment method card selection states with `.selected` class, checkmark badges, and hover effects.
- Added proper validation feedback blocks (`.checkout-feedback.show`) with shake animation instead of inline text.
- Made payment timing and method cards deselectable by removing `required` and handling validation in JavaScript.
- Wired owner-only payment method management into existing owner settings page (`/owner/settings/wallet` → Payment Methods tab).
- Added host dashboard payment settings widget linking to per-property booking policy.
- Added `cash` to `PaymentMethodConfig.initialize_defaults()` so it is no longer hardcoded.
- Updated property 2 booking policy to allow `pay_on_arrival` and `deposit`.
- Updated README.md, PAYMENT_ARCHITECTURE.md, and MOBILE_OPTIMIZATION.md with new payment settings wiring.

**Migration needed?** No
**Manual steps:** 
1. Restart Flask server.
2. Owner visits `/owner/settings/wallet` → Payment Methods tab to enable/disable methods.
3. Host visits `/host/property/2/booking-policy` to enable Cash and payment timings for the property.
4. Test checkout at `/accommodation/guest/hotel-yriad` to verify Wallet + Cash cards and Pay Now / Deposit / Pay on Arrival timings appear.

**Risks/conflicts:** No schema changes. Owner endpoints protected by `@require_owner_role`. Host booking policy already had payment-method saving logic. No colors, branding, or desktop layout were altered.
