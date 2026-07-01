# AFCON360 — Project Identity

Flask + PostgreSQL + Redis + Celery platform for football tournament management.
Handles events, accommodation, transport, wallet/payments, KYC, and multi-role admin.

## Stack
- **Backend**: Flask 3.1 / Python 3.13, SQLAlchemy 2.0, Alembic migrations
- **Database**: PostgreSQL (psycopg2-binary)
- **Cache/Sessions**: Redis + Flask-Session
- **Async tasks**: Celery 5.4
- **Auth**: Flask-Login, role-based decorators
- **Frontend**: Bootstrap 5, Jinja2 templates
- **Payments**: Flutterwave, Paystack, Mobile Money integrations

## Blueprint Map
- `app/auth/` — login, registration, onboarding, KYC routes
- `app/admin/` — admin, super_admin, owner, moderator, support, auditor
- `app/events/` — event lifecycle, registrations, payments
- `app/wallet/` — double-entry ledger, transfers, withdrawals, webhooks
- `app/accommodation/` — property listings, bookings, state machine
- `app/transport/` — drivers, vehicles, routes, fleet management
- `app/identity/` — organisations, KYB, individual verification
- `app/profile/` — user profiles, KYC immutable fields
- `app/kyc/` — KYC submissions, document verification
- `app/audit/` — forensic audit, compliance logging
- `app/fan/` — fan-specific models and routes
- `app/tourism/` — tourism listings
- `app/tournament/` — tournament data

## Entry Points
- `app.py` — Flask app entry
- `app/__init__.py` — app factory (main factory, ~69KB)
- `app/config.py` — configuration classes
- `app/extensions.py` — shared extensions (db, login_manager, etc.)

## Key Conventions
- Models inherit from `BaseModel` in `app/models/base.py`
- FK columns use `BigInteger` referencing `user.id`
- No PostgreSQL ENUM types — use String columns
- Blueprint-based modular design
- All sensitive modules gated by `@module_required` decorator
