# AFCON360 Wallet/Tourism/Accommodation Fixes

## Summary
This update completes the final implementation steps for wallet, tourism, and accommodation endpoint stabilization.

## Key Changes
- Fixed accommodation routing in both templates and backend code by replacing legacy Flask endpoint names like `accommodation.guest.search` with actual blueprint endpoints such as `accommodation.guest_search`.
- Added a new Alembic migration `migrations/versions/afcon360_analytics_001.py` for analytics page view aggregation.
- Ensured wallet activation and dashboard routing use the correct public and authenticated flow.
- Confirmed wallet activation page uses CSRF token `{{ csrf_token() }}` and preserves verification/state handling.
- Preserved analytics/audit separation for tourism and wallet page tracking.

## Files Updated
- `templates/accommodation/guest/search.html`
- `templates/accommodation/guest/detail.html`
- `templates/accommodation/guest/my_bookings.html`
- `templates/accommodation/guest/checkout.html`
- `templates/accommodation/guest/confirmation.html`
- `templates/accommodation_home.html`
- `templates/public_home.html`
- `templates/events/public/landing.html`
- `templates/events/attendee/attendee_dashboard.html`
- `templates/dashboard/user_dashboard.html`
- `templates/fan/components/middle_pane.html`
- `templates/fan/components/left_pane.html`
- `templates/super_admin_dashboard.html`
- `migrations/versions/afcon360_analytics_001.py`
- `app/services/analytics.py`
- `app/wallet/middleware/wallet_check.py`
- `app/config.py`
- `templates/wallet/wallet_dashboard.html`
- `templates/wallet/base_wallet.html`

## Notes
- No remaining `accommodation.guest.*` template references were found after the fix.
- The new migration is wired to the current Alembic head `5d751ad7bf6f`.

## Verification Checklist
- [x] `app/wallet/routes.py` `home()` has no `@login_required` and now returns `wallet_home.html` for unauthenticated users.
- [x] `app/wallet/routes.py` contains no `entity_id=None` references.
- [x] `app/tourism/routes.py` `home()` no longer calls `ForensicAuditService.log_attempt(entity_id=None)` and only tracks analytics.
- [x] `app/services/analytics.py` exists and provides the lightweight analytics service.
- [x] `app/wallet/middleware/wallet_check.py` supports `redirect_to` correctly.
- [x] `templates/wallet/wallet_dashboard.html` includes distinct branches for no-wallet, inactive-wallet, and active-wallet states.
- [x] `templates/wallet/base_wallet.html` includes a wallet terms acceptance banner.
- [x] `app/config.py` contains analytics configuration keys: `ANALYTICS_ENABLED`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_ANALYTICS_DB`.
- [x] `templates/wallet/wallet_activate.html` uses `{{ csrf_token() }}`.

## Runtime Verification
- `GET /wallet/` returned `200` with the public wallet marketing page accessible without login.
- `GET /wallet/dashboard` returned `302`, which is expected for an unauthenticated request because the dashboard route is still protected by `@login_required`.
- `GET /tourism/` returned `302`, which matches the current `@login_required` on `tourism.home`.

## Important Observation
- The file-level fix for tourism home is present, but `tourism.home` remains login-protected. If the goal is a public tourism landing page, that route will still need `@login_required` removed.
