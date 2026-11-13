# PAMOJA-HOMEPAGE-HERO-01 — Contract

## 1. Guarantee

Add a branded Pamoja hero banner immediately above the existing homepage search section. It must introduce Pamoja, provide two useful primary actions, and show horizontally scrollable service shortcuts on mobile widths. Existing homepage sections and their order remain intact.

## 2. Current Behavior

The Flask homepage is rendered by `templates/public_home.html`. Its search bar is currently the first homepage section. Global homepage styling is loaded from `static/css/global/home.css` through `templates/base.html`. There is no `static/css/home.css` file. The website already exposes route-aware destinations and module availability through `safe_url`, `links`, and `modules`.

## 3. Scope-In

- Insert the Pamoja hero above the existing `.top-search` section.
- Include the supplied welcome headline and supporting copy, a featured-events action, and a stay-search action.
- Add service chips for Events, Stays, Transport, Tourism, and Wallet.
- Display the chips as a horizontally scrollable row on mobile (max-width 768px), hidden on larger screens.
- Style the hero in the existing Pamoja green and gold visual language.
- Preserve module-disabled behavior and use the authenticated wallet destination when a user is signed in.
- Keep the hero visually usable without a hero image asset; support a future image through a CSS custom property without referencing a missing file.

## 4. Scope-Out

- No changes to the native React Native app in this website-only work item.
- No changes to Flask routes, feed services, database models, APIs, events, advertisements, authentication, or other homepage sections.
- No image asset is created or downloaded in this change because no image was supplied or selected.
- No deployment, production restart, or production data change.

## 5. Interface Contract

- Template: `templates/public_home.html`.
- Stylesheet: `static/css/global/home.css` (loaded globally by `templates/base.html`).
- Hero root class: `.pamoja-hero-section`.
- Action classes: `.hero-actions`, `.btn-hero-primary`, `.btn-hero-ghost`.
- Mobile shortcuts: `.mobile-service-chips`, `.mobile-chip`.
- Destinations: `events.list`, `accommodation.guest_search`, `transport.home`, `links.tourism_home`, and the existing authenticated/anonymous Wallet destination.
- Transport, accommodation, and tourism shortcuts respect existing module availability.

## 6. Proof of Done

- Template contains exactly one hero banner before `.top-search`.
- Existing search, trending, homepage layout, quick actions, featured/live event content, dynamic feed, advertisements, and host-event promotion remain present and in their original order.
- CSS is responsive, uses no missing asset URL, and keeps all hero links touch-accessible on mobile.
- Run the focused homepage/template and navigation checks available in CI before merge. Visual verification on the running laptop preview remains a separate manual check.

## 7. Rollback

Revert the website-only pull request commit(s). No data rollback is required because this change is presentation-only.

## 8. Constraints

- Website/backend changes stay on a server-only feature branch and the pull request targets `main`.
- Do not include any `mobile/**` or native build/workflow paths.
- Do not modify the existing public-download contract.
- Do not introduce new endpoints or hard-coded active campaign dates.
- Keep the hero useful when no background photograph is configured.

## 9. Acceptance Criteria

- The hero appears above search on desktop and mobile.
- On desktop, the hero headline, supporting copy, and two actions are centered and readable.
- At widths up to 768px, the hero compacts and service chips appear as a single swipeable row without forcing page-wide horizontal overflow.
- All existing routes and disabled-module protections are retained.
- Existing homepage sections and dynamic feed behavior are unaffected.
