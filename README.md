# AFCON360 - Integrated Management Ecosystem

## Overview

AFCON360 is a comprehensive Flask/PostgreSQL/Redis web application ecosystem that combines multiple management systems into a unified platform. It serves organizers, attendees, community hosts, and administrators with distinct capabilities:

- **Fintech/Wallet System**: Double-entry ledger, transactions, payouts, commissions
- **Transport Management**: Booking system, driver/vehicle management, route tracking
- **Accommodation Management**: Property listings, booking system, host management
- **Event Management**: Event creation, registration, ticketing, payments
- **Tourism Management**: Tourism services, activities, bookings
- **Tournament Management**: Bracket management, scheduling
- **Identity/KYC System**: User verification, organization verification, compliance

Each module operates independently but integrates seamlessly - users can pay for events via wallet, book transport to events, secure accommodation, and access tourism activities through a unified interface.

## Payment Architecture

**Wallet is the single source of truth for all financial events.** Every module (accommodation, transport, events) delegates actual money movement to the wallet module and stores only a thin `wallet_txn_id` reference.

```
Wallet Module (source of truth)
├── TransactionModel      ← immutable record of every financial event
├── LedgerEntryModel      ← double-entry records
├── AccountModel          ← balances derived from ledger
└── PaymentMethodConfig   ← global payment catalogue

Accommodation             Transport             Events
├── AccommodationBooking  ├── Booking           ├── EventRegistration
│   ├── wallet_txn_id     │   ├── wallet_txn_id │   ├── wallet_txn_id
│   └── payment_status    │   └── payment_status│   └── payment_status
└── AccommodationBookingPayment (thin index)
    ├── booking_id
    ├── wallet_txn_id      ← canonical link
    ├── payment_reference
    ├── payment_status     ← cached from wallet
    └── retry_count        ← module-specific
```

**Key rules:**
- **Wallet owns the money.** All charges, refunds, and transfers flow through `WalletService` or `PaymentGateway`.
- **Modules own the context.** Which room, which car, which event ticket — that stays in the domain module.
- **One line links them.** `wallet_txn_id` / `wallet_transaction_id` points from the booking record to the canonical `TransactionModel`.
- **No duplicate ledgers.** Module-specific payment tables (`AccommodationBookingPayment`, transport `BookingPayment`) are thin indexes for fast queries, not sources of truth.

## System Architecture

### **Core Technologies**
- **Backend**: Flask (Python) with SQLAlchemy ORM
- **Database**: PostgreSQL (production), SQLite (local dev)
- **Cache/Queue**: Redis
- **Frontend**: Bootstrap 5 with custom CSS (dark editorial UI with gold accents)
- **Authentication**: Flask-Login with role-based permissions
- **Deployment**: Docker Compose on Oracle Cloud VM.Standard.E4.Flex (IP 79.76.104.169)
- **Server**: Gunicorn + Nginx
- **Rate Limiting**: Flask-Limiter with Redis storage

### **Key Components**
- **User Management System**: Complete CRUD operations with bulk actions
- **Role-Based Access Control**: Hierarchical roles with granular permissions
- **Impersonation System**: Owner can impersonate any role below them
- **Dashboard System**: Role-specific dashboards with relevant functionality
- **Module System**: Toggleable features (events, wallet, transport, etc.)
- **Media Management**: File upload, processing, and storage
- **Compliance & Audit**: Forensic audit trails for regulatory compliance

---

## Project Structure

```
app/
├── __init__.py                 # Application factory
├── config.py                   # Configuration settings
├── extensions.py               # Flask extensions initialization
├── routes.py                   # Core application routes
├── utils.py                    # Utility functions
│
├── admin/                      # Admin management routes
│   ├── __init__.py
│   ├── routes.py               # Core admin functionality
│   ├── routes_ultimate.py      # Advanced user management
│   ├── decorators.py           # Admin decorators
│   ├── models.py               # Admin models
│   ├── services.py             # Admin services
│   ├── trust_settings.py       # Trust settings
│   ├── hooks.py                # Admin hooks
│   │
│   ├── admin_services/         # Admin service modules
│   │   ├── ai_detection.py
│   │   ├── analytics_service.py
│   │   ├── content_safety.py
│   │   ├── escalation_workflow.py
│   │   ├── moderation_queue.py
│   │   ├── payment_methods.py
│   │   └── training_system.py
│   │
│   ├── owner/                  # Owner-specific functionality
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── audit.py
│   │   ├── csp_routes.py
│   │   ├── decorators.py
│   │   ├── models.py
│   │   ├── security_routes.py
│   │   ├── security_service.py
│   │   ├── settings.md
│   │   ├── utils.py
│   │   ├── wallet_config.py
│   │   └── api/
│   │       └── module_api.py
│   │
│   ├── compliance/             # Compliance routes
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── routes.py
│   │   └── services.py
│   │
│   ├── moderator/              # Moderator routes
│   │   ├── __init__.py
│   │   ├── pipeline.py
│   │   ├── registry.py
│   │   └── routes.py
│   │
│   ├── support/                # Support routes
│   │   ├── __init__.py
│   │   └── routes.py
│   │
│   ├── auditor/                # Auditor routes
│   │   ├── __init__.py
│   │   └── routes.py
│   │
│   ├── models/                 # Admin models
│   │   ├── __init__.py
│   │   ├── core.py
│   │   ├── emergency_access.py
│   │   └── moderation.py
│   │
│   └── route_modules/          # Role-specific route modules
│       ├── accommodation_admin.py
│       ├── event_manager.py
│       ├── org_admin.py
│       ├── org_member.py
│       ├── settings.py
│       ├── tourism_admin.py
│       ├── transport_admin.py
│       └── wallet_admin.py
│
├── accommodation/              # Accommodation module
│   ├── __init__.py
│   ├── routes.py
│   ├── routes_old.py
│   ├── services.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── availability.py
│   │   ├── booking.py
│   │   ├── property.py
│   │   ├── review.py
│   │   └── wishlist.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── abuse_prevention_service.py
│   │   ├── ai_search_service.py
│   │   ├── ai_trip_planner_service.py
│   │   ├── availability_service.py
│   │   ├── blockchain_reviews_service.py
│   │   ├── booking_service.py
│   │   ├── competitive_intelligence_service.py
│   │   ├── dynamic_pricing_service.py
│   │   ├── gamified_loyalty_service.py
│   │   ├── host_service.py
│   │   ├── hyper_personalization_service.py
│   │   ├── identity_service.py
│   │   ├── immersive_tour_service.py
│   │   ├── payment_option_service.py
│   │   ├── predictive_availability_service.py
│   │   ├── pricing_service.py
│   │   ├── search_service.py
│   │   ├── urgency_service.py
│   │   └── voice_booking_service.py
│   │
│   └── state_machine/
│       ├── __init__.py
│       └── booking_states.py
│
├── transport/                  # Transport module
│   ├── __init__.py
│   ├── models.py
│   ├── routes.py
│   ├── decorator.py
│   ├── event_listeners.py
│   ├── listeners.py
│   ├── view_models.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── analytic_routes.py
│   │   ├── booking_routes.py
│   │   ├── dashboard_routes.py
│   │   ├── driver_routes.py
│   │   ├── incident_routes.py
│   │   ├── organisation_routes.py
│   │   ├── route_routes.py
│   │   ├── settings_routes.py
│   │   ├── utils.py
│   │   └── vehicle_routes.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── booking_service.py
│   │   ├── dashboard_service.py
│   │   ├── external_platforms.py
│   │   ├── future_adds.py
│   │   ├── matching_service.py
│   │   ├── notification_service.py
│   │   ├── payment_service.py
│   │   ├── promotion_service.py
│   │   ├── provider_service.py
│   │   └── settings_service.py
│   │
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
│
├── events/                     # Events module
│   ├── __init__.py
│   ├── models.py
│   ├── routes.py
│   ├── services.py
│   ├── signal_handlers.py
│   ├── permissions.py
│   ├── metrics_service.py
│   ├── payment_service.py
│   ├── payment_config.py
│   ├── assignment.py
│   ├── bulk_upload.py
│   ├── constants.py
│   ├── routes_accommodation.py
│   ├── routes_community_hosts.py
│   ├── settings_model.py
│   ├── settings_routes.py
│   ├── signals.py
│   └── view_models.py
│
├── wallet/                     # Wallet module
│   ├── __init__.py
│   ├── models.py
│   ├── decorators.py
│   ├── exceptions.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── admin_api.py
│   │   ├── admin_webhook_routes.py
│   │   ├── fx_api.py
│   │   ├── wallet_api.py
│   │   └── webhooks.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── admin_audit.py
│   │   ├── aggregator.py
│   │   ├── audit.py
│   │   ├── commission.py
│   │   ├── config.py
│   │   ├── fraud_detection.py
│   │   ├── fx.py
│   │   ├── ledger.py
│   │   ├── nonce_protection.py
│   │   ├── payout.py
│   │   ├── reconciliation.py
│   │   ├── transaction.py
│   │   ├── travel_rule.py
│   │   └── webhook_event.py
│   │
│   ├── payments/
│   │   ├── __init__.py
│   │   ├── alipay.py
│   │   ├── flutterwave.py
│   │   ├── mobile_money.py
│   │   ├── paypal.py
│   │   ├── paystack.py
│   │   ├── visa.py
│   │   └── wechat.py
│   │
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── idempotency.py
│   │   ├── kill_switch.py
│   │   ├── wallet_activation.py
│   │   └── wallet_check.py
│   │
│   └── repositories/
│       ├── __init__.py
│       ├── account_repository.py
│       └── commission_repository.py
│
├── identity/                   # Identity module
│   ├── __init__.py
│   ├── routes.py
│   ├── services.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── compliance_audit_log.py
│   │   ├── compliance_settings.py
│   │   ├── kyb.py
│   │   ├── licence_document.py
│   │   ├── note.py
│   │   ├── organisation.py
│   │   ├── organisation_controller.py
│   │   ├── organisation_member.py
│   │   ├── organization_types.py
│   │   ├── roles_permission.py
│   │   └── user.py
│   │
│   └── services/
│       ├── __init__.py
│       ├── organization_permissions.py
│       └── organization_registration.py
│
├── kyc/                        # KYC verification
│   ├── __init__.py
│   ├── models.py
│   ├── routes.py
│   ├── services.py
│   ├── nira_verification.py
│   └── upgrade_routes.py
│
├── tourism/                    # Tourism module
│   ├── __init__.py
│   └── routes.py
│
├── tournament/                 # Tournament module
│   ├── __init__.py
│   └── routes.py
│
├── auth/                       # Authentication system
│   ├── routes.py
│   ├── services.py
│   ├── decorators.py
│   └── sessions.py
│
├── audit/                      # Audit logging
│   ├── forensic_audit.py
│   └── models.py
│
├── fan/                        # Fan/attendee features
│   └── routes.py
│
├── profile/                    # User profile management
│   ├── __init__.py
│   ├── models.py
│   └── routes.py
│
├── user/                       # User management
│   ├── routes.py
│   └── use_dashboard.md
│
├── services/                     # Core services
│   ├── __init__.py
│   ├── analytics.py
│   ├── module_toggle_service.py
│   └── sms_service.py
│
├── tasks/                      # Background tasks
│   ├── reconcile.py
│   └── webhook_processor.py
│
├── middleware/                 # Middleware components
│   └── (middleware files)
│
├── backup/                     # Backup system
│   └── (backup files)
│
├── cli/                        # CLI commands
│   └── owner.py
│
├── tools/                      # Development tools
│   ├── inspect_project.py
│   ├── theme_routes.py
│   └── theme_service.py
│
├── forms/                      # Form definitions
│   ├── booking_forms.py
│   └── settings_forms.py
│
├── models/                     # Core models
│   ├── base.py
│   ├── audit.py
│   ├── analytics.py
│   ├── system_config.py
│   └── theme.py
│
├── utils/                      # Utility functions
│   ├── __init__.py
│   ├── audit.py
│   ├── caching.py
│   ├── db_retry.py
│   ├── error_handler.py
│   ├── exceptions.py
│   ├── id_guard.py
│   ├── id_helpers.py
│   ├── id_validator.py
│   ├── idempotency.py
│   ├── module_disabled.py
│   ├── module_guard.py
│   ├── module_switch.py
│   ├── monitoring.py
│   ├── rate_limiting.py
│   ├── redis_lock.py
│   ├── security.py
│   ├── template_helpers.py
│   ├── transactions.py
│   └── validators.py
│
├── core/                       # Core functionality
│   └── (core files)
│
├── compliance/                 # Compliance system
│   └── (compliance files)
│
├── dashboard/                  # Dashboard components
│   └── (dashboard files)
│
├── media/                      # Media management
│   ├── __init__.py
│   ├── routes.py
│   ├── service.py
│   ├── tasks.py
│   ├── validators.py
│   ├── models.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── local.py
│   │   └── oci.py
│   └── (media files)
│
└── Documentation/              # Documentation files
    └── ID_SYSTEM_RULES.md
```

---

## Role Hierarchy & Permissions

### **Role Levels (Highest to Lowest)**

1. **owner** - Complete system control, can impersonate all roles
2. **super_admin** - System administration except owner modification
3. **admin** - Administrative functions
4. **auditor** - Audit and compliance oversight
5. **compliance_officer** - Regulatory compliance
6. **moderator** - Content moderation
7. **support** - Customer service
8. **event_manager** - Event administration
9. **transport_admin** - Transportation management
10. **wallet_admin** - Financial operations
11. **accommodation_admin** - Lodging management
12. **tourism_admin** - Tourism services
13. **org_admin** - Organization management
14. **org_member** - Organization member
15. **user** - Standard user access

---

## Core Modules

### **1. Events Module** (`app/events/`)
- Event creation, approval, and registration workflows
- Ticketing and payment processing
- **Wallet integration** — `EventRegistration.wallet_txn_id` links to `TransactionModel`; no separate payment ledger table needed
- Signal handlers for event lifecycle
- Event metrics and analytics
- Community host integration
- Accommodation and transport integration for events

### **2. Wallet Module** (`app/wallet/`)
- **Single source of truth for all financial events** across accommodation, transport, and events
- Double-entry ledger architecture (enterprise-grade)
- `TransactionModel` — immutable transaction records every other module references via `wallet_txn_id`
- `LedgerEntryModel` — double-entry records; balances are derived, never stored
- `PaymentMethodConfig` — global catalogue of enabled payment methods
- Payment provider integrations (Flutterwave, Paystack, PayPal, Alipay, WeChat, Visa, Mobile Money)
- Webhook handling and reconciliation
- API endpoints for wallet operations
- Middleware: idempotency, kill switch, activation checks
- **Other modules do not duplicate financial records.** They store thin indexes (`AccommodationBookingPayment`, transport `BookingPayment`) that link back to `TransactionModel`.

### **3. Transport Module** (`app/transport/`)
- Transport booking system
- Driver and vehicle management
- Route and incident tracking
- Real-time notifications
- External platform integrations
- Analytics and reporting (32+ API endpoints)
- State management and matching services
- **Wallet integration for payments** — `Booking.wallet_transaction_id` links to `TransactionModel`
- Thin payment index `BookingPayment` for fast module-level queries

### **4. Accommodation Module** (`app/accommodation/`)
- Host registration and management
- Property listing and search
- Booking system with state machine
- Review and rating system
- Pricing and availability management
- **Wallet integration for payments** — `AccommodationBooking.wallet_txn_id` links to `TransactionModel`
- Thin payment index `AccommodationBookingPayment` for fast module-level queries
- AI-powered search and trip planning
- Gamified loyalty and blockchain reviews

### **5. Tournament Module** (`app/tournament/`)
- Bracket management
- Tournament scheduling

### **6. Identity Module** (`app/identity/`)
- KYC (Know Your Customer) verification
- Organization verification (KYB)
- License document management
- Compliance audit logging
- Role and permission management
- Organization registration and permissions

### **7. KYC Module** (`app/kyc/`)
- KYC document verification
- NIRA verification integration
- KYC upgrade workflows

### **8. Tourism Module** (`app/tourism/`)
- Tourism service listings
- Tourism booking management
- Activity management

### **9. Auth Module** (`app/auth/`)
- Authentication and session management
- Role-based access control
- OTP and email verification
- Password policy enforcement
- Onboarding workflows

### **10. Admin Module** (`app/admin/`)
- Role-based admin dashboards
- Trust settings management
- Security and compliance monitoring
- Module toggle controls
- AI content detection and moderation
- Escalation workflows

### **11. Media Module** (`app/media/`)
- File upload, processing, and storage
- Local and OCI (Oracle Cloud Infrastructure) storage backends
- Media validation and processing tasks

### **12. User Module** (`app/user/`)
- User dashboard and profile management
- User-specific features and settings

### **13. Profile Module** (`app/profile/`)
- User profile management
- Profile update and verification workflows

### **14. Fan Module** (`app/fan/`)
- Enhanced fan/attendee dashboard
- Event discovery and registration

### **15. Services Module** (`app/services/`)
- Analytics services
- Module toggle service
- SMS service

### **16. Tasks Module** (`app/tasks/`)
- Webhook processing
- Transaction reconciliation

### **17. CLI Module** (`app/cli/`)
- Owner CLI commands

### **18. Tools Module** (`app/tools/`)
- Theme management
- Project inspection tools

### **19. Forms Module** (`app/forms/`)
- Booking forms
- Settings forms

### **20. Models Module** (`app/models/`)
- BaseModel for all models
- Audit models
- Analytics models
- System configuration
- Theme models

### **21. Utils Module** (`app/utils/`)
- IDGuard for ID mixing protection
- Module switch and guard
- Audit, caching, and security utilities
- Rate limiting, Redis locks, validators
- Error handling and template helpers

---

## Key Features

### **IDGuard System**
- Runtime ID mixing protection
- String FK exception handling
- Automatic ID validation

### **Owner Management System**
- **Owner Dashboard** (`/admin/owner/dashboard`): System statistics, user counts, role distribution
- **Master Key Impersonation** (`/admin/owner/impersonate-page`): Role-based access with smart redirects
- **Role Management**: Add/remove super admin privileges

### **Advanced User Management**
- **Ultimate User Interface** (`/admin/manage-users-ultimate`): Real-time search, bulk operations
- **User Details View**: Complete profile, role history, audit trail
- **Status Management**: Verification, activation, suspension

### **Role Management System**
- **Role Administration** (`/admin/roles`): Role statistics, assignment, hierarchy display
- **Global Role Switcher (Persona System)**: Card-based UI to toggle between assigned roles

### **Dashboard System**
- Super Admin Dashboard (`/admin/super-dashboard`)
- Moderator Dashboard (`/admin/moderator-dashboard`)
- Support Dashboard (`/admin/support-dashboard`)
- Auditor Dashboard (`/admin/auditor-dashboard`)
- Compliance Officer Dashboard (`/admin/compliance/dashboard`)
- Event Manager Dashboard (`/admin/event-manager-dashboard`)
- Transport Admin Dashboard (`/admin/transport-admin-dashboard`)
- Wallet Admin Dashboard (`/admin/wallet-admin-dashboard`)
- Accommodation Admin Dashboard (`/admin/accommodation-admin-dashboard`)
- Tourism Admin Dashboard (`/admin/tourism-admin-dashboard`)
- Org Admin Dashboard (`/admin/org-admin-dashboard`)
- Org Member Dashboard (`/admin/org-member-dashboard`)
- Enhanced Fan Dashboard (`/fan/enhanced-dashboard`)

### **Module System**
- Toggleable features (events, wallet, transport, accommodation, tournament, identity, tourism)
- Instant module reload hooks
- Module disabled page handler

### **Compliance & Forensic Audit**
- Attempt vs completion tracking
- Blocked action logging
- Risk scoring for audit events
- Suspicious pattern detection
- Compliance reporting (FIA Uganda, Bank of Uganda formats)

---

## API Endpoints

### **Health Check**
- `GET /api/health/ping` - Health check endpoint

### **Owner Routes**
- `GET /admin/owner/dashboard` - Owner dashboard
- `GET /admin/owner/impersonate-page` - Role impersonation interface
- `POST /admin/owner/master-key/act-as/<role_name>` - Impersonate role
- `POST /admin/owner/master-key/exit` - Exit impersonation

### **User Management Routes**
- `GET /admin/manage-users-ultimate` - Advanced user interface
- `POST /admin/users/<user_id>/verify` - Verify user
- `POST /admin/users/<user_id>/activate` - Activate user
- `POST /admin/users/<user_id>/deactivate` - Deactivate user
- `POST /admin/users/<user_id>/delete` - Delete user
- `POST /admin/users/bulk-verify` - Bulk verification
- `POST /admin/users/bulk-deactivate` - Bulk deactivation

### **Role Management Routes**
- `GET /admin/roles` - Role management interface
- `GET /admin/roles/<role_id>/users` - View users with role
- `POST /admin/roles/assign` - Assign role to user
- `POST /admin/roles/remove` - Remove role from user

### **Audit API**
- `/api/audit/timeline/<entity_type>/<entity_id>` - Get forensic timeline
- `/api/audit/pending-reviews` - Get pending review items
- `/api/audit/review/<audit_id>` - Process review approvals/rejections
- `/api/audit/suspicious-patterns` - Get suspicious activity patterns
- `/api/audit/compliance-report` - Generate compliance reports

### **Wallet API**
- `/api/wallet/balance` - Get wallet balance
- `/api/wallet/transactions` - List transactions
- `/api/wallet/deposit` - Create deposit
- `/api/wallet/withdraw` - Create withdrawal
- `/api/wallet/admin/*` - Admin wallet operations

### **Transport API**
- `/api/transport/bookings` - Booking operations
- `/api/transport/drivers` - Driver management
- `/api/transport/vehicles` - Vehicle management
- `/api/transport/routes` - Route management
- `/api/transport/analytics` - Analytics data

---

## Configuration

### **Environment Variables**
```python
# Database Configuration
DATABASE_URL = "postgresql://user:password@localhost/afcon360"
REDIS_URL = "redis://localhost:6379/0"

# Security Configuration
SECRET_KEY = "your-secret-key"
CSRF_SECRET_KEY = "your-csrf-secret"

# Rate Limiting
RATELIMIT_STORAGE_URI = "redis://localhost:6379/1"

# Application Configuration
DEBUG = False
TESTING = False
```

### **Module Toggle Configuration**
Modules can be enabled/disabled via system configuration:
- `events` - Event management module
- `wallet` - Wallet/transaction module
- `transport` - Transport booking module
- `accommodation` - Accommodation module
- `tournament` - Tournament module
- `identity` - KYC/identity module
- `moderation` - Moderation module

---

## Database Models

### **Core Models**
- **User**: Core user information and authentication (inherits from `BaseModel`)
- **Role**: Role definitions and permissions
- **UserRole**: Many-to-many relationship between users and roles
- **Organisation**: Organization management
- **SystemConfig**: System-wide configuration

### **Wallet Models** (source of truth for all payments)
- **AccountModel**: Financial accounts (user wallets, org wallets, platform accounts); balances derived from ledger
- **TransactionModel**: Immutable transaction records — every charge, refund, or transfer in the system
- **LedgerEntryModel**: Double-entry ledger records tied to `TransactionModel`
- **PaymentMethodConfig**: Global catalogue of enabled payment methods (wallet, mobile money, card)
- **Payout**: Payout requests
- **Commission**: Commission tracking
- **FraudDetection**: Fraud detection records

### **Module Payment Indexes** (thin references to wallet, not ledgers)
- **AccommodationBookingPayment**: Maps `booking_id` → `wallet_txn_id`, caches `payment_status` and `payment_reference`
- **Transport BookingPayment**: Maps `booking_id` → `wallet_txn_id`, caches `payment_status` and `payment_reference`
- **EventRegistration**: Stores `wallet_txn_id` and `payment_status` directly — no separate ledger table needed

### **Audit Models**
- **AuditLog**: General audit logging
- **ForensicAudit**: Forensic audit trail
- **ComplianceAuditLog**: Compliance-specific audit

---

## Deployment

### **Docker Compose Stack**
- Flask application container
- PostgreSQL database container
- Redis cache/queue container
- Celery worker container (for background tasks)
- Nginx reverse proxy container

### **Production Server**
- Oracle Cloud VM.Standard.E4.Flex (IP: 79.76.104.169)
- User: ubuntu
- Health check: `/api/health/ping`

### **Deployment Commands**
```bash
# Build and start containers
docker-compose up -d

# Run database migrations
flask db upgrade

# Stamp head (after bootstrap)
flask db stamp head

# Check container status
docker-compose ps

# View logs
docker-compose logs -f web
```

### **Key Dependencies**
- Flask 2.x+
- SQLAlchemy with Alembic migrations
- PostgreSQL 14+
- Redis 6+
- Celery for background tasks
- Bootstrap 5 for frontend

---

## Development Setup

### **Prerequisites**
- Python 3.10+
- PostgreSQL 14+
- Redis 6+
- Docker (for containerized deployment)

### **Installation**
```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
flask db upgrade

# Run development server
flask run
```

---

## Security Considerations

- **Password Hashing**: Argon2 with passlib
- **CSRF Protection**: All forms include security tokens
- **Rate Limiting**: API endpoint protection via Flask-Limiter
- **Session Security**: Secure session handling with Flask-Session
- **Role-Based Access**: Granular permission control
- **Audit Logging**: Comprehensive activity tracking
- **Fernet Encryption**: Lazy `_get_fernet()` pattern for encryption

---

## Testing

- **Unit Testing**: Model, route, and service tests
- **Integration Testing**: End-to-end workflow tests
- **Security Testing**: Permission and authentication tests
- **Run tests**: `pytest` or `pytest --cov=app`

---

## License

Proprietary - AFCON360 Platform

---

## Static Files & Templates

### **Static Files Structure**
```
static/
├── css/
│   └── modules/
│       ├── accommodation/
│       ├── admin/
│       ├── events/
│       ├── fan/
│       ├── transport/
│       └── wallet/
├── js/
│   ├── global/
│   │   ├── main.js
│   │   ├── media-manager.js
│   │   └── theme-manager.js
│   └── modules/
│       ├── accommodation/
│       ├── events/
│       └── transport/
└── images/
```

### **Templates Structure**
```
templates/
├── admin/
│   ├── super_dashboard.html
│   ├── moderator_dashboard.html
│   ├── support_dashboard.html
│   ├── auditor_dashboard.html
│   ├── manage_roles.html
│   ├── manage_users_ultimate.html
│   ├── view_user_ultimate.html
│   └── compliance/
├── fan/
│   └── enhanced_dashboard.html
├── accommodation_home.html
├── transport_home.html
├── tournament_home.html
├── tourism_home.html
├── public_home.html
└── base.html
```

### **Mobile Optimization Documentation**
- **`static/MOBILE_OPTIMIZATION.md`** — Canonical record of the 2026 mobile responsive refactor. Includes full file tree, per-file change log, what was explicitly preserved (colors, gradients, desktop layout), verification checklist, and future isolation plan for subsequent optimization phases.
