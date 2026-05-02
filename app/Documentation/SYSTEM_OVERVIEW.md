# AFCON360 - Complete System Documentation

## Overview

AFCON360 is a comprehensive football tournament management platform built with Flask, featuring advanced user administration, role-based access control, financial transactions, transportation, accommodation, events, and tourism modules. The system is designed for multi-tenant operations with organization management, KYC compliance, and forensic audit capabilities.

## Technology Stack

### Core Technologies
- **Backend**: Flask 3.1.2 (Python) with SQLAlchemy 2.0.44 ORM
- **Database**: PostgreSQL with psycopg2-binary
- **Cache/Session**: Redis 7.1.0
- **Authentication**: Flask-Login 0.6.3 with Argon2 password hashing
- **Security**: Flask-WTF CSRF protection, Flask-Limiter rate limiting
- **Migrations**: Alembic 1.17.2
- **Task Queue**: Celery 5.4.0
- **Testing**: Pytest 8.3.0 with pytest-flask

### Frontend
- **Framework**: Bootstrap 5 with custom CSS
- **UI Components**: Custom dashboard layouts with responsive design
- **Theme Management**: Dynamic theme switching

## System Architecture

### Module Structure

```
app/
├── admin/              # Administration interfaces
│   ├── auditor/        # Audit and compliance dashboards
│   ├── compliance/     # Regulatory compliance
│   ├── moderator/      # Content moderation
│   ├── owner/          # Owner controls and security
│   └── support/        # Customer service
├── accommodation/      # Property booking system
│   ├── models/         # Property, booking, availability, reviews
│   ├── routes/         # Admin, guest, host routes
│   └── services/       # Business logic
├── audit/              # Forensic audit logging
├── auth/               # Authentication & authorization
│   ├── services/       # Login, registration, OTP
│   └── kyc_routes.py   # KYC verification flows
├── events/             # Event management
│   ├── models.py       # Event, ticket, registration
│   └── routes.py       # Event endpoints
├── identity/           # User & organization management
│   ├── individuals/    # Individual verification
│   └── models/         # User, Organisation, Roles
├── kyc/                # KYC compliance system
│   ├── models.py       # KYC records and tiers
│   └── routes.py       # KYC workflows
├── profile/            # User profile management
├── transport/          # Transportation module
│   ├── api/            # RESTful API endpoints
│   └── models.py       # Driver, vehicle, route, booking
├── tourism/            # Tourism packages
├── wallet/             # Financial wallet system
│   ├── models.py       # Wallet, transaction, payout
│   └── routes.py       # Wallet operations
└── utils/              # Utility functions
```

## Core Features

### 1. User Management & Authentication

**Registration System**
- Username/password registration with optional email
- Email OTP verification (Flask-Mail integration)
- Phone SMS OTP verification (Twilio/Africa's Talking)
- Security questions for no-email users
- Recovery code generation
- Rate limiting (10 attempts/minute for registration, 5/hour for recovery)

**Authentication**
- Flask-Login session management
- Argon2 password hashing
- Role-based access control (15 hierarchical roles)
- Impersonation system (owner can impersonate any role)
- Session security with Redis backend

### 2. Role-Based Access Control (RBAC)

**Role Hierarchy** (Highest to Lowest)
1. owner - Complete system control
2. super_admin - System administration
3. admin - Administrative functions
4. auditor - Audit and compliance oversight
5. compliance_officer - Regulatory compliance
6. moderator - Content moderation
7. support - Customer service
8. event_manager - Event administration
9. transport_admin - Transportation management
10. wallet_admin - Financial operations
11. accommodation_admin - Lodging management
12. tourism_admin - Tourism services
13. org_admin - Organization management
14. org_member - Organization member
15. user - Standard user access

**Permission System**
- Dot-namespaced permissions (e.g., `users.manage`, `wallet.approve`)
- Global and organization-scoped roles
- Direct permission grants/denies per member
- Owner bypass for all permission checks

### 3. KYC Compliance System

**6-Tier Framework** (T0-T5)
- T0: Unverified
- T1: Basic verification
- T2: Enhanced verification
- T3: Full verification
- T4: Business verification
- T5: Enterprise verification

**Features**
- Document upload workflow
- NIRA verification integration
- Tier progress calculation
- Transaction limits per tier
- AML/CFT monitoring

### 4. Wallet & Financial System

**Wallet Features**
- Multi-currency support (home/local currency)
- User and organization wallets
- Daily/monthly volume tracking
- Freeze functionality with reason tracking
- Wallet verification status
- Reconciliation system

**Transaction Types**
- Deposits (Flutterwave, MTN MoMo, Airtel Money)
- Withdrawals
- Peer-to-peer transfers
- Merchant payouts
- Commission tracking

**Compliance**
- Transaction limits per KYC tier
- Suspicious activity alerts
- AML/CFT transaction monitoring
- Full audit trail

### 5. Transportation Module

**Driver Management**
- Driver onboarding and verification
- Document verification (licenses, insurance)
- Driver rating system
- Compliance status tracking

**Vehicle Management**
- Vehicle registration
- Maintenance tracking
- Insurance verification
- Route assignment

**Booking System**
- Real-time availability checking
- Pricing calculation
- Booking confirmation flow
- Cancellation/refund workflow
- GPS tracking integration

**Admin Features**
- Analytics dashboard
- Incident reporting
- Route management
- Organization management

### 6. Accommodation Module

**Property Management**
- Property listing creation
- Photo upload/gallery
- Amenities management
- Availability calendar
- Property types (entire place, private room, shared room, hotel)

**Booking System**
- Search with filters
- Booking flow
- Cancellation policies (flexible, moderate, strict, super_strict)
- Host verification workflow

**Reviews**
- Guest reviews
- Host responses
- Rating aggregation

### 7. Events Module

**Event Management**
- Event creation and editing
- Ticket type management
- QR code generation
- Check-in/scanning
- Attendee registration
- Waitlist management

**Organizer Tools**
- Analytics dashboard
- Attendee communication
- Staff management

**Status System**
- Draft → Published → Active → Completed → Archived
- Soft-delete hierarchy
- Event transfer requests
- Moderation logging

### 8. Tourism Module

**Package Management**
- Tour package creation
- Itinerary builder
- Pricing configuration
- Group bookings
- Custom requests

**Guide Management**
- Tour guide profiles
- Guide availability
- Guide ratings

### 9. Audit & Compliance

**Forensic Audit System**
- Attempt vs completion tracking
- Blocked action logging
- Risk scoring
- Suspicious pattern detection
- Compliance reporting (FIA Uganda, Bank of Uganda)

**Audit Tables**
- User authentication events
- Profile modifications
- KYC approvals
- Wallet transactions
- Role changes

**Compliance Reports**
- Transaction reports (> UGX 20M)
- KYC approval timelines
- Suspicious activity summaries

## Database Architecture

### Dual ID System

**Critical Rule**: Never mix internal and external IDs

- **Internal Operations**: Use `.id` (BIGINT) - for foreign keys, database queries, session storage
- **External Operations**: Use `.user_id` (UUID) - for URLs, API responses, Flask-Login, JavaScript

**Example**:
```python
# ✅ CORRECT
audit_log.owner_id = current_user.id  # Foreign key
url_for('profile', user_id=user.user_id)  # URL

# ❌ WRONG
audit_log.owner_id = current_user.user_id  # UUID in FK
url_for('profile', user_id=user.id)  # Internal ID in URL
```

### Key Models

**User & Identity**
- `User` - Core user with dual ID system
- `UserProfile` - Extended profile information
- `Organisation` - Organization management
- `OrganisationMember` - Organization membership
- `Role` - Role definitions with hierarchy
- `Permission` - Granular permissions
- `UserRole` / `OrgUserRole` - Role assignments

**Financial**
- `Wallet` - User/organization wallets
- `Transaction` - All financial transactions
- `PaymentMethod` - Tokenized payment methods
- `PayoutRequest` - Merchant withdrawals
- `CommissionRule` - Platform fee configuration

**Transport**
- `Driver` - Driver profiles and verification
- `Vehicle` - Vehicle registration
- `Route` - Transport routes
- `TransportBooking` - Booking records
- `Incident` - Incident reports

**Accommodation**
- `Property` - Property listings
- `Booking` - Accommodation bookings
- `Availability` - Availability calendar
- `Review` - Guest reviews

**Events**
- `Event` - Event records
- `TicketType` - Ticket configurations
- `Registration` - Attendee registrations
- `EventModerationLog` - Status transitions

**Audit**
- `ForensicAuditLog` - Comprehensive audit trail
- `ComplianceAuditLog` - Compliance-specific events

## API Endpoints

### Authentication
- `POST /register` - User registration
- `POST /login` - User login
- `POST /verify-email` - Email OTP verification
- `POST /verify-phone` - Phone OTP verification
- `POST /recover` - Password recovery

### Admin
- `GET /admin/super-dashboard` - Super admin dashboard
- `GET /admin/manage-users-ultimate` - User management
- `GET /admin/roles` - Role management
- `GET /admin/owner/dashboard` - Owner dashboard
- `POST /admin/owner/master-key/act-as/<role>` - Impersonation

### Wallet
- `GET /wallet` - Wallet dashboard
- `POST /wallet/deposit` - Deposit funds
- `POST /wallet/withdraw` - Withdraw funds
- `GET /wallet/transactions` - Transaction history

### Transport
- `GET /transport/dashboard` - Transport dashboard
- `POST /transport/api/bookings` - Create booking
- `GET /transport/api/drivers` - Driver list
- `GET /transport/api/vehicles` - Vehicle list

### Events
- `GET /events` - Event listing
- `POST /events` - Create event
- `POST /events/<id>/register` - Register for event

### Audit
- `GET /api/audit/timeline/<entity_type>/<entity_id>` - Audit timeline
- `GET /api/audit/pending-reviews` - Pending compliance reviews
- `GET /api/audit/suspicious-patterns` - Suspicious activity

## Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost/afcon360
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-secret-key
ENCRYPTION_KEY=your-encryption-key
CSRF_SECRET_KEY=your-csrf-secret

# Email
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# SMS
SMS_PROVIDER=twilio  # or africas_talking or console
TWILIO_ACCOUNT_SID=your-sid
TWILIO_AUTH_TOKEN=your-token
TWILIO_PHONE_NUMBER=your-number

# Application
REQUIRE_EMAIL_VERIFICATION=False
DEBUG=False
TESTING=False
```

### Feature Flags

Module features can be toggled via configuration:
- Wallet module enable/disable
- Transport module settings
- KYC tier requirements
- Email verification requirement

## Development Workflow

### CLI Commands

```bash
# Database
flask db upgrade              # Apply migrations
flask db downgrade            # Rollback migrations
flask db revision             # Create migration

# Owner Management
flask assign-owner --list                    # Show current owner
flask assign-owner --user USERNAME          # Assign owner role
flask assign-owner --revoke USERNAME         # Revoke owner role

# Running
flask run                    # Dev server on http://localhost:5000
flask shell                   # Interactive Python shell

# Debugging
flask routes                  # List all registered routes
flask routes --sort method    # Sort by HTTP method
```

### Pre-commit Hooks

- ID system violation detection
- Prevents mixing internal/external IDs
- Run `python scripts/check_id_usage.py` to check manually

### Testing

```bash
pytest                       # Run all tests
pytest --cov                 # With coverage
pytest tests/auth/           # Specific module
```

## Security Features

### Authentication Security
- Argon2 password hashing (cost factor 12+)
- Rate limiting (5 attempts → 15 min lockout)
- Session management (30-day expiry)
- CSRF protection on all forms
- Secure session storage with Redis

### Authorization Security
- Role-based access control
- Principle of least privilege
- Owner bypass for all checks
- Self-protection (cannot delete/impersonate self)
- Template-level permission checks

### Data Security
- Field-level encryption for sensitive data
- HTTPS enforcement in production
- Secure session cookies
- Environment variable secrets management
- SQL injection prevention via ORM

### Audit Security
- Comprehensive forensic audit trail
- Attempt and completion tracking
- Risk scoring and pattern detection
- Immutable audit logs
- Compliance reporting

## Deployment

### Production Checklist

**Configuration**
- [ ] Set strong SECRET_KEY and ENCRYPTION_KEY
- [ ] Configure production database
- [ ] Set up Redis with proper credentials
- [ ] Configure email provider
- [ ] Set up SMS provider
- [ ] Enable HTTPS with valid certificates
- [ ] Set SESSION_COOKIE_SECURE=True
- [ ] Configure rate limits for production loads

**Database**
- [ ] Run `flask db upgrade`
- [ ] Run `flask seed-all` for initial data
- [ ] Assign owner role via CLI
- [ ] Set up automated backups
- [ ] Configure connection pooling

**Security**
- [ ] Enable firewall rules
- [ ] Set up WAF if available
- [ ] Configure DDoS protection
- [ ] Enable security monitoring
- [ ] Set up error tracking (Sentry)

**Monitoring**
- [ ] Configure application logging
- [ ] Set up performance monitoring
- [ ] Monitor Redis and database connections
- [ ] Set up alerts for critical failures
- [ ] Configure health check endpoints

## Development Roadmap

### Completed (Phase 1)
- ✅ Registration & User Management
- ✅ KYC System (T0-T5)
- ✅ Role-Based Access Control
- ✅ Admin Panel & Dashboards
- ✅ Forensic Audit System
- ✅ Impersonation System

### In Progress
- ⏳ Wallet & Payments (Phase 2)
- ⏳ Transport Module Enhancements (Phase 3)
- ⏳ Accommodation Module (Phase 4)
- ⏳ Tourism Module (Phase 5)
- ⏳ Events Module Enhancements (Phase 6)

### Planned
- ⏳ Analytics & Reporting (Phase 7)
- ⏳ Mobile API & Notifications (Phase 8)
- ⏳ Multi-factor authentication
- ⏳ SSO integration
- ⏳ Advanced compliance (GDPR, SOC2)

## Known Issues

1. **Transport API endpoint conflict** - DriverListResource endpoint name conflict (cosmetic, doesn't affect runtime)
2. **Audit log schema** - Some audit tables have missing columns (graceful error handling in place)
3. **SQLAlchemy 2.x migration** - Some models use `__allow_unmapped__` as bridge (valid permanent solution)

## Support & Documentation

### Technical Documentation
- API Documentation: Complete API reference
- Developer Guide: Development setup and procedures
- Deployment Guide: Production deployment instructions
- ID System Rules: Dual ID system usage guidelines

### User Documentation
- User Manual: End-user instructions
- Admin Guide: Administrative procedures
- Role Guides: Role-specific instructions
- FAQ: Common questions and answers

## System Status

**Version**: 1.0.0  
**Last Updated**: April 2026  
**Architecture**: Flask + PostgreSQL + Redis  
**Status**: Production Ready (Phase 1 Complete)  
**Active Modules**: Auth, Admin, Audit, KYC, Profile, Transport (basic), Wallet (basic), Events (basic), Accommodation (basic)

---

**Note**: This is a comprehensive overview. For detailed implementation details of specific modules, refer to the module-specific documentation in `app/Documentation/` and the existing README files.
