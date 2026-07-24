# Mobile Optimization Plan — AFCON 360

## Goal
Make the app usable and clean on phones (320–480px) and tablets (768–1024px) with minimal risk.

## Scope Decision (Phased)
**Do not try to fix everything at once.** Split into 3 phases so each can be tested independently. This avoids shipping a massive diff that is hard to review and hard to roll back.

---

## Phase 1 — Global Foundation (affects every page, highest ROI)
**Best first move:** Fix the shared layout and extract inline styles that break mobile on *all* pages.

### Tasks
1. **`static/css/global/style.css`**
   - Switch `main#main` padding to `clamp(1rem, 4vw, 2.5rem)`.
   - Reduce `.site-header` padding/font sizes on mobile and add `min-height: 44px` touch targets to `.menu-item > a`, `.hamburger`, `.drawer-link`.
   - Add safe-area insets: `padding-bottom: env(safe-area-inset-bottom)` on `.site-footer`, `.mobile-drawer`, and `.sticky-book-bar`.
   - Add a tablet-only breakpoint `@media (min-width: 768px) and (max-width: 1024px)` that keeps desktop nav but tightens spacing.

2. **`static/css/global/mobile-utilities.css`** (new)
   - Create once, reuse everywhere:
     - `.touch-target { min-height: 44px; min-width: 44px; }`
     - `.stack-mobile { flex-direction: column; }` (applied via `@media (max-width: 768px)`)
     - `.hide-mobile { display: none !important; }` / `.show-mobile { display: block !important; }`
     - `.scroll-x-mobile { overflow-x: auto; -webkit-overflow-scrolling: touch; }`
     - `.safe-bottom { padding-bottom: env(safe-area-inset-bottom); }`

3. **`templates/base.html`**
   - Extract the profile-incomplete banner and impersonation banner inline `style=` blocks into CSS classes (`.banner-incomplete`, `.banner-impersonation`) in `style.css`.
   - Remove hardcoded `top: 40px` offset; use a CSS custom property `--banner-offset` that the banners set via inline `style="--banner-offset: 0px"` and header reads via `top: var(--banner-offset, 0)`.
   - Stack `.container-fluid > .row` columns vertically on `max-width: 768px` with `gap: 1rem`.

4. **`static/css/global/home.css`**
   - Replace the left-sidebar horizontal-wrap hack at 768px with a **bottom navigation bar** (`.home-bottom-nav`) that appears only on mobile.
   - Use `repeat(auto-fit, minmax(280px, 1fr))` for `.featured-grid`.
   - Stack `.search-inner` vertically on `max-width: 480px`.

---

## Phase 2 — High-Traffic User Pages (wallet, events, user dashboard)
**Best second move:** Fix the pages users touch most. These are independent of admin.

### Tasks
5. **`static/css/modules/wallet/wallet.css`**
   - `.wallet-balance-amount` → `clamp(1.8rem, 5vw, 3rem)`.
   - `.wallet-title` → `clamp(1.5rem, 4vw, 2.5rem)`.
   - `.wallet-action-tile` grid: 2 columns on tablet (`max-width: 1024px`), 1 column on phone.
   - Ensure `.withdraw-method-grid` is 1 column on phone (already exists, verify).

6. **`static/css/modules/events/base_events.css`**
   - `.event-card-img` → `clamp(140px, 30vw, 180px)`.
   - Wrap `.event-table` in `.scroll-x-mobile` via template (or add wrapper class in CSS).
   - Stack `.event-filters` vertically on mobile.

7. **`static/css/modules/user/dashboard.css`**
   - `.greeting-text` → `clamp(1.25rem, 4vw, 2rem)`.
   - `.stats-grid` → `repeat(auto-fit, minmax(160px, 1fr))` on mobile.
   - `.section-card` padding → `clamp(1rem, 3vw, 2rem)`.

8. **`templates/events/attendee/attendee_dashboard.html`**
   - Remove inline `style=` from `.reg-actions`, `.reg-badges`, `.reg-card-body`.
   - Add `.stack-mobile` class to `.reg-card-body` so badges stack above actions on narrow screens.
   - Remove `min-width: 240px` from `.reg-actions`.

---

## Phase 3 — Admin & Polish (higher complexity, lower traffic)
**Best third move:** Fix admin last because it has the most bespoke CSS and least user traffic.

### Tasks
9. **`static/css/modules/admin/owner.css`**
   - **Do NOT remove the duplicate CSS blocks yet.** That is a separate cleanup task with higher risk.
   - Add a mobile hamburger/drawer for `.sad-sidebar` (`.sad-mobile-drawer`) triggered by a new button.
   - Ensure `.sad-stats`, `.sad-twocol`, `.sad-qa`, `.sad-settings-grid` stack to 1 column on `max-width: 768px`.
   - Hide `.sad-sidebar` only after the drawer is functional.

10. **`templates/super_admin_dashboard.html`**
    - Add the drawer trigger button and JavaScript toggle using the same pattern as `base.html`'s mobile drawer (reuse `.drawer-overlay` / `.mobile-drawer` classes where possible, or create `.sad-mobile-drawer`).
    - Scale `.sad-card` padding on mobile.

11. **`static/css/modules/accommodation/detail.css`**
    - Add `min-height: 44px` to `.sbb-cta`.
    - Add `env(safe-area-inset-bottom)` to `.sticky-book-bar` (already partially there, verify).

---

## Out of Scope (explicitly deferred)
- **Owner.css duplicate cleanup** — risky, unrelated to mobile. Do as a separate PR with visual regression testing.
- **Theme variables expansion** — `--header-height-mobile` etc. Low impact; current fixed values are acceptable.
- **`theme-components.css`** — Bootstrap overrides are already mostly responsive.
- **Wallet dashboard inline styles** — functional but lower priority than the CSS file itself.

---

## Execution Order
1. Phase 1 (foundation + utilities)
2. Phase 2 (wallet + events + user dashboard)
3. Phase 3 (admin)

After each phase: verify on 375px and 768px viewports before moving to the next.

## Files Changed (total ~11)
- `static/css/global/style.css`
- `static/css/global/home.css`
- `static/css/global/mobile-utilities.css` (new)
- `templates/base.html`
- `static/css/modules/wallet/wallet.css`
- `static/css/modules/events/base_events.css`
- `static/css/modules/user/dashboard.css`
- `templates/events/attendee/attendee_dashboard.html`
- `static/css/modules/admin/owner.css`
- `templates/super_admin_dashboard.html`
- `static/css/modules/accommodation/detail.css`

## Migration / Manual Steps
- No database changes. No env vars.
- Static files only; normal browser refresh applies.

## Risks
- **Inline styles in templates** are highest specificity. Phase 1 and Phase 2 must extract them to classes before CSS media queries can take effect.
- **Super admin drawer** reuses patterns from `base.html` but with different markup; ensure z-index doesn't conflict with `.sad-sidebar`.
- **Owner.css duplication** is left untouched to avoid regression; only additive mobile rules are added.

## Verification
1. Chrome DevTools device emulation:
   - iPhone SE (375px)
   - iPhone 14 Pro Max (430px)
   - iPad Mini (768px)
   - iPad Pro (1024px)
2. Check touch targets ≥44×44px.
3. Verify no horizontal scroll on main content (except intentional `.scroll-x-mobile` tables).
4. Verify banners stack correctly and do not overlap header content.
