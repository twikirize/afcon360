# Onboarding Implementation Report

**Date:** 2026-05-04  
**Status:** Complete

## Routes Created

- [x] `/onboarding/choose` - Landing page with role selection cards
- [x] `/onboarding/fan` - 1-step fan/explorer onboarding
- [x] `/onboarding/driver` - 3-step driver onboarding wizard
- [x] `/onboarding/driver/step/<n>` - Individual driver wizard steps
- [x] `/onboarding/organisation` - 2-step organisation registration
- [x] `/onboarding/organisation/step/<n>` - Organisation wizard steps
- [x] `/onboarding/host` - 2-step accommodation host onboarding
- [x] `/onboarding/host/step/<n>` - Host wizard steps
- [x] `/onboarding/event-organiser` - 1-step event organiser onboarding
- [x] `/wallet/activate` - Wallet activation (opt-in, not auto-created)

## Templates Created

- [x] `templates/onboarding/choose.html` - Main landing page with 7 role cards
- [x] `templates/onboarding/fan.html` - Simple 1-step form
- [x] `templates/onboarding/driver_step1.html` - Personal details
- [x] `templates/onboarding/driver_step2.html` - Licence details with file upload
- [x] `templates/onboarding/driver_step3.html` - Vehicle details
- [x] `templates/onboarding/_progress_bar.html` - Shared step indicator
- [x] `templates/onboarding/organisation_step1.html` - Org details
- [x] `templates/onboarding/organisation_step2.html` - Confirm & submit
- [x] `templates/onboarding/host_step1.html` - Personal verification
- [x] `templates/onboarding/host_step2.html` - Property details
- [x] `templates/onboarding/event_organiser.html` - 1-step form

## Code Modifications

### `app/auth/onboarding_routes.py` (NEW FILE)
- All 6 onboarding routes implemented
- Helper functions: `_get_or_create_profile`, `_commit_driver_onboarding`, `_commit_organisation_onboarding`, `_commit_host_onboarding`
- Uses `db_transaction` for atomic commits
- Session-based multi-step wizard flow

### `app/auth/routes.py` - `_dashboard_for_user()`
- Added onboarding completion check at the top
- Added driver profile check for routing to transport dashboard
- Added event_manager role check
- Falls through to fan dashboard as default

### `app/__init__.py`
- Registered `onboarding_bp` blueprint
- Added import for `onboarding_routes`

### `app/wallet/routes.py`
- `/wallet/activate` route already exists for explicit wallet opt-in
- Creates `AccountModel` only after terms acceptance
- Checks for existing wallet before creating

## Migrations

```bash
flask db migrate -m "add_driver_profile_onboarding"
flask db upgrade
flask seed-all
```

## Test Results

- `tests/test_onboarding.py` created with 10 test cases
- Tests cover: choose page access, fan onboarding, organisation registration, dashboard routing, wallet activation
- Run with: `pytest tests/test_onboarding.py -v --tb=short`

## Key Design Decisions

1. **Wallet is never auto-created** - only on explicit user request with terms acceptance
2. **All role assignments go through `assign_global_role()` or `assign_org_role()`** from `app/auth/roles.py`
3. **Every DB mutation is wrapped in `db_transaction()`** from `app/utils/transactions.py`
4. **`get_profile_by_user()` always receives `user.public_id`** (UUID string), never an integer
5. **Org creation** always creates an `Organisation` record + `OrganisationMember` record + assigns `org_owner` role
6. **Session-based multi-step wizards** - data stored in session until final commit
7. **Profile completion** is the gate for dashboard routing - incomplete profiles always go to onboarding
