# Production Deployment Checklist

## 🔧 Configuration
- [ ] Update `RATELIMIT_DEFAULT` in config.py for production loads
- [ ] Set proper `SESSION_COOKIE_SECURE=True` for HTTPS
- [ ] Configure proper `SECRET_KEY` and `SECURITY_SALT` in environment
- [ ] Set up proper database connection pooling
- [ ] Configure Redis connection with proper credentials

## 🚀 Transport Module
- [ ] Review dashboard auto-refresh interval (currently 5 min)
- [ ] Test all admin routes with production user roles
- [ ] Verify rate limits for API endpoints
- [ ] Check that all stats display correctly with real data
- [ ] Test driver/vehicle approval workflows
- [ ] Verify booking system with high volume

## 🛡️ Security
- [ ] Enable HTTPS everywhere
- [ ] Test CSRF protection on all forms
- [ ] Review session timeout settings
- [ ] Test role-based access control (admin/super_admin)
- [ ] Audit logging for sensitive actions

## 📊 Monitoring
- [ ] Set up error tracking (Sentry, etc.)
- [ ] Configure performance monitoring
- [ ] Set up alerts for rate limit breaches
- [ ] Monitor Redis and database connections

## 🧪 Testing
- [ ] Load test with expected production traffic
- [ ] Test all user roles and permissions
- [ ] Verify email notifications work
- [ ] Test file uploads (driver licenses, vehicle photos)

## 📝 Documentation
- [ ] Document environment variables needed
- [ ] Create deployment runbook
- [ ] Document rollback procedures
- [ ] List all external dependencies

Updated: 2026-03-13
# Already have @limiter.limit per endpoint
# Consider adding per-user limits in services.py
# AFCON 360 — Development TODO

Last updated: March 2026

---

## ✅ COMPLETED

### RBAC Foundation
- [x] Role model with scope (global/org) and level hierarchy
- [x] Permission model with dot-namespaced naming convention
- [x] RolePermission association table
- [x] UserRole (global assignments)
- [x] OrgUserRole (org-scoped assignments)
- [x] OrgRole per-org role definitions with template_name
- [x] OrgMemberPermission direct grant/deny per member
- [x] Idempotent factory helpers (get_or_create_role, get_or_create_permission, assign_permission_to_role)
- [x] ORM event listeners for data integrity (scope enum, level >= 1, permission naming)
- [x] `__allow_unmapped__ = True` on all SQLAlchemy 2.x models

### Seed System
- [x] 6 global roles seeded with levels (owner=1 → fan=6)
- [x] 9 org roles seeded (org_owner, org_admin, finance_manager, transport_manager, hr_manager, dispatcher, project_manager, org_member, org_guest)
- [x] 27 global permissions across users, kyc, orgs, content, wallet, transport, system, audit, roles
- [x] 12 org-scoped permissions (org.finance.*, org.transport.*, org.members.*, org.settings.*, org.projects.*)
- [x] OrgRoleTemplates for onboarding (org_owner gets all, finance_manager gets finance.*, etc.)
- [x] CLI commands: flask seed-all, flask seed-roles, flask seed-permissions, flask seed-links
- [x] register_commands(app) pattern wired into create_app()

### Auth System
- [x] helpers.py — has_global_role, has_global_permission, has_org_role, has_org_permission, is_owner, highest_role, ROLE_HIERARCHY
- [x] policy.py — can() single entry point, DB-driven, owner bypass, convenience wrappers
- [x] decorators.py — @require_role, @require_org_role, @require_permission, @owner_only
- [x] roles.py — assign_global_role, revoke_global_role, assign_org_role, revoke_org_role with audit logging
- [x] routes.py — role-based post-login redirect via _dashboard_for_user(), fans no longer land on admin
- [x] ownership.py — transfer_ownership with correct imports from organisation_member

### Admin Dashboard
- [x] Super admin dashboard — module toggles, wallet features, transport settings, KYC stats
- [x] base.html — {% block body %} override so admin dashboard escapes header/footer
- [x] style.css — sad- prefix namespace, zero collision with public site styles
- [x] Dark theme admin shell with sidebar navigation, stat cards, quick actions

---

## 🔴 DO FIRST (Blocking)

### 1. Assign yourself owner role
- [ ] Run `flask db upgrade` then `flask seed-all`
- [ ] Write `flask assign-owner <username>` CLI command so you never need raw SQL
- [ ] Verify login redirects you to super_dashboard not index

### 2. Audit hooks in services.py
- [ ] Wire `_emit()` to write rows into the `audit_logs` table
- [ ] Events to capture: login_success, login_failed, login_locked, role_assigned, role_revoked, kyc_approved, kyc_rejected, withdrawal_approved, module_toggled
- [ ] This unlocks the Recent Activity panel already built in the dashboard
- [ ] Without this, compliance story is broken and incidents can't be investigated

### 3. Admin UI — User Management
- [ ] User list with role badges and KYC status
- [ ] Role assignment modal (assign/revoke global roles)
- [ ] User suspend / reactivate
- [ ] KYC review queue with approve/reject actions
- [ ] Without this, RBAC system is unusable — you can only change roles via terminal

### 4. Admin UI — Organisation Management
- [ ] Organisation list with verification status
- [ ] Org detail view: members, roles, documents
- [ ] Approve / reject / suspend organisations
- [ ] Assign org roles to members

---

## 🟡 DO NEXT (Before first real user)

### 5. Unit tests — auth helpers
- [ ] tests/auth/test_helpers.py
- [ ] test_owner_bypasses_all_role_checks()
- [ ] test_owner_bypasses_all_permission_checks()
- [ ] test_fan_denied_admin_routes()
- [ ] test_has_global_role_returns_false_for_empty_roles()
- [ ] test_org_role_scoped_to_correct_org()
- [ ] test_revoke_global_role_returns_false_if_not_held()
- [ ] test_org_member_permission_explicit_deny_overrides_role()
- [ ] test_effective_permissions_cached_property_invalidation()

### 6. Unit tests — seed
- [ ] tests/auth/test_seed.py
- [ ] test_seed_all_is_idempotent() — run twice, no duplicates
- [ ] test_role_permission_links_correct() — owner has system.modules, fan does not
- [ ] test_org_role_template_permissions() — finance_manager has org.finance.manage

### 7. Route protection audit
- [ ] Audit every admin blueprint route — confirm @require_role or @require_permission is present
- [ ] Confirm no route redirects to admin without login_required
- [ ] Check transport_admin routes — currently unprotected (the flask-restful conflict)
- [ ] Fix the transport_api route conflict (DriverListResource endpoint overwrite in __init__.py)

---

## 🔵 PLANNED (Dashboard builds)

### 8. Owner dashboard (separate from super_admin)
- [ ] Leaner than super_admin — god-mode controls only
- [ ] Module on/off toggles (system.modules permission only)
- [ ] Role assignment for all levels including super_admin promotion
- [ ] Full audit log viewer (all roles, all events)
- [ ] System health with real health-check endpoints (not static badges)
- [ ] Billing / plan settings placeholder
- [ ] Danger zone section (wipe, reset)

### 9. Admin dashboard
- [ ] Manages fans and supporters only (not super_admins)
- [ ] Assign moderator and support roles
- [ ] Organisation approvals
- [ ] KYC queue (fans only)
- [ ] Activity reports
- [ ] Swap routes.py TODO: url_for("admin.admin_dashboard") when built

### 10. Moderator dashboard
- [ ] Content moderation queue
- [ ] User reports and flags
- [ ] Submission review
- [ ] Read-only user lookup
- [ ] Warn / mute users
- [ ] Swap routes.py TODO: url_for("admin.moderator_dashboard") when built

### 11. Support dashboard
- [ ] Support ticket queue
- [ ] Read-only user lookup
- [ ] Wallet issue escalation
- [ ] Booking lookup
- [ ] Swap routes.py TODO: url_for("admin.support_dashboard") when built

---

## ⚪ LATER (When you have real traffic or non-technical admins)

### 12. Per-user rate limiting
- [ ] Current endpoint-level @limiter.limit is sufficient for now
- [ ] Add per-user limits in services.py when API abuse patterns emerge
- [ ] Consider: 10 withdrawals/hour per user, 5 KYC submissions/day per user

### 13. Permission editor UI
- [ ] Owner-only screen to create permissions and link to roles
- [ ] flask seed-all covers this completely for now
- [ ] Only needed when non-technical admins need to manage permissions

### 14. MFA activation
- [ ] routes.py mfa() stub is in place and ready
- [ ] Replace POST body with real TOTP/OTP validation
- [ ] MFASecret model already exists in user.py
- [ ] Wire up when you have paying users who need it

### 15. Org onboarding flow
- [ ] When a new organisation is created, auto-provision OrgRole instances from ORG_ROLE_TEMPLATES
- [ ] Assign org_owner role to the creating user automatically
- [ ] org_user_roles and org_member_permissions tables are ready and waiting

### 16. Health check endpoints
- [ ] Replace static "Connected" badges in system status card with real pings
- [ ] GET /health/db — SQLAlchemy ping
- [ ] GET /health/redis — Redis ping
- [ ] GET /health/email — SMTP handshake
- [ ] GET /health/payment — gateway ping
- [ ] Wire owner dashboard status card to these endpoints

### 17. SQLAlchemy 2.x Mapped[] migration
- [ ] roles_permission.py currently uses __allow_unmapped__ = True as a bridge
- [ ] Long-term: replace list["RolePermission"] with Mapped[list["RolePermission"]]
- [ ] Requires importing Mapped from sqlalchemy.orm in each affected model
- [ ] Not urgent — __allow_unmapped__ is a permanent valid solution

---

## 🐛 KNOWN BUGS / TECH DEBT

- [ ] transport/__init__.py — DriverListResource endpoint name conflict causing flask app startup error in console (does not affect runtime, fix when touching transport module)
- [ ] roles_permission.py — create_role() was previously defined twice (fixed)
- [ ] helpers.py — bare `org_roles` name at module level causing NameError on import (fixed)
- [ ] seed.py — role names were app_owner/user instead of owner/fan (fixed)
- [ ] routes.py — all users redirected to super_dashboard after login regardless of role (fixed)
- [ ] ownership.py — imported OrgUserRole/OrgRole from user.py instead of organisation_member.py (fixed)

# 🏗️ PLATFORM SECURITY - MASTER TODO LIST

## 📋 LEGEND
- 🟢 **NOW** - Do this immediately (Launch Required)
- 🟡 **SOON** - Add within 3-6 months
- 🔴 **LATER** - Add when scaling/invested

---

## 👑 OWNER SECURITY

### 🟢 PHASE 1: SIMPLE OWNER MODEL (Start Here)

#### 1.1 Database Setup
- [ ] Create `owners` table (single row only)
  - `id` (primary key)
  - `email` (unique)
  - `password_hash` (bcrypt/Argon2)
  - `role` (default: 'owner')
  - `created_at`
  - `last_login_at`
  - `last_login_ip`

- [ ] Create `owner_sessions` table
  - `id`
  - `owner_id`
  - `token` (secure random)
  - `ip_address`
  - `user_agent`
  - `expires_at`
  - `created_at`

- [ ] Create `audit_logs` table
  - `id`
  - `actor_id` (owner ID)
  - `actor_email`
  - `action` (e.g., 'login', 'user_banned', 'settings_changed')
  - `details` (JSON of what changed)
  - `ip_address`
  - `user_agent`
  - `created_at`
  - `INDEX(created_at)`

#### 1.2 Authentication Implementation
- [ ] Set up password hashing (bcrypt cost factor 12+)
- [ ] Implement 2FA with Google/Microsoft Authenticator
  - [ ] Install pyotp or similar library
  - [ ] Generate secret on owner creation
  - [ ] Show QR code for setup
  - [ ] Verify code before enabling
- [ ] Add rate limiting (5 attempts → 15 min lockout)
- [ ] Session management (30-day expiry, extend on use)

#### 1.3 Critical Action Protection
- [ ] Define critical actions list:
  - [ ] Delete platform
  - [ ] Export all user data
  - [ ] Change owner email
  - [ ] Disable 2FA
  - [ ] Ban admin users
  - [ ] Change payment settings

- [ ] Require password re-entry for all critical actions
- [ ] Log ALL critical actions to audit table

#### 1.4 Audit Logging
- [ ] Log every owner login (success + failure)
- [ ] Log every critical action
- [ ] Log all user management actions (ban, role change)
- [ ] Make logs append-only (no delete/update)

#### 1.5 Simple Recovery
- [ ] Password reset via email + 2FA confirmation
- [ ] Reset link expires in 15 minutes
- [ ] Log all reset attempts

---

### 🟡 PHASE 2: ENHANCED OWNER SECURITY (3-6 Months)

#### 2.1 Hardware Keys
- [ ] Purchase YubiKeys (minimum 2 per owner)
- [ ] Implement WebAuthn for hardware key support
- [ ] Make 2FA optional → hardware key optional → eventually mandatory
- [ ] Store backup keys in safe place

#### 2.2 Session Improvements
- [ ] Add device fingerprinting
- [ ] Implement concurrent session limiting (kick previous)
- [ ] Add "remember this device" option
- [ ] Send email alerts for new device logins

#### 2.3 Better Audit
- [ ] Add IP geolocation to logs
- [ ] Build simple audit viewer (owner only)
- [ ] Add export function (for compliance)
- [ ] Set up weekly audit summary email

#### 2.4 Recovery Improvements
- [ ] Add 3-5 trusted recovery contacts
- [ ] Implement 2-of-3 recovery for owner lockout
- [ ] Store paper backup codes in safe
- [ ] Document recovery procedure

#### 2.5 Danger Zone Timeouts
- [ ] Add 24-hour delay for:
  - [ ] Platform deletion
  - [ ] Owner email change
  - [ ] Master key rotation
- [ ] Send confirmation emails during delay period

---

### 🔴 PHASE 3: ADVANCED OWNER SECURITY (Post-Investment)

#### 3.1 Hardware Security Module (HSM)
- [ ] Evaluate cloud HSM options (AWS CloudHSM, Azure Dedicated)
- [ ] Migrate master keys to HSM
- [ ] Update signing logic to use HSM

#### 3.2 Cold Storage Ceremony
- [ ] Set up air-gapped machine for critical actions
- [ ] Create bootable signed USB
- [ ] Document physical ceremony procedures
- [ ] Train backup signers

#### 3.3 3-of-5 Trustee System
- [ ] Recruit 5 trustees (diverse backgrounds)
- [ ] Implement verifiable secret sharing
- [ ] Create trustee onboarding/training
- [ ] Test recovery annually

#### 3.4 External Witness
- [ ] Push daily audit hash to Bitcoin OP_RETURN
- [ ] Build verification tool
- [ ] Set up monitoring for tampering

#### 3.5 Behavioral Biometrics
- [ ] Implement typing pattern analysis
- [ ] Train model on owner behavior
- [ ] Add step-up auth on anomalies

---

## 👥 USER SECURITY

### 🟢 PHASE 1: BASIC USER PROTECTION (Launch)

#### 1.1 Authentication
- [ ] Strong password requirements (min 8 chars, mix)
- [ ] Optional 2FA (TOTP)
- [ ] Rate limiting (5 attempts → 15 min lockout)
- [ ] Session management (30-day expiry)

#### 1.2 Data Protection
- [ ] HTTPS everywhere (TLS 1.3)
- [ ] Encrypt sensitive fields at rest (AES-256)
- [ ] Never log passwords or tokens
- [ ] Sanitize all inputs (prevent injection)

#### 1.3 User Controls
- [ ] Email confirmation on signup
- [ ] Password reset flow
- [ ] "Remember this device" option
- [ ] Logout from all devices button

#### 1.4 Basic Logging
- [ ] Log all user logins (success + failure)
- [ ] Log all password resets
- [ ] Log all profile changes

---

### 🟡 PHASE 2: ENHANCED USER SECURITY (3-6 Months)

#### 2.1 Advanced Auth
- [ ] WebAuthn/Passkey support
- [ ] SMS backup 2FA (optional)
- [ ] Recovery codes (10, single-use)
- [ ] Device management page

#### 2.2 User Alerts
- [ ] Email on new device login
- [ ] SMS for suspicious activity (optional)
- [ ] In-app notifications for security events

#### 2.3 Data Separation
- [ ] Split user data into separate tables
- [ ] Encrypt PII with per-user keys
- [ ] Implement data retention policies

#### 2.4 Self-Service Security
- [ ] View active sessions
- [ ] View login history
- [ ] Set spending limits (if wallet)
- [ ] Self-freeze account option

---

### 🔴 PHASE 3: ADVANCED USER SECURITY (Post-Launch)

#### 3.1 Per-User Encryption
- [ ] Generate per-user encryption keys
- [ ] Encrypt all sensitive data with user key
- [ ] Wrap user keys with master HSM key

#### 3.2 Fraud Detection
- [ ] Implement ML-based anomaly detection
- [ ] Real-time scoring of suspicious activity
- [ ] Automated blocking rules

#### 3.3 Compliance
- [ ] GDPR data export tool
- [ ] Right to erasure workflow
- [ ] Data residency controls

---

## 💳 PAYMENT SECURITY (If Handling Cards)

### 🟢 PHASE 1: BASIC PAYMENT SECURITY (Launch)
- [ ] NEVER store raw card numbers
- [ ] Use Stripe/Paystack/Braintree tokens only
- [ ] PCI DSS self-assessment questionnaire
- [ ] HTTPS for all payment pages

### 🟡 PHASE 2: ENHANCED PAYMENT SECURITY
- [ ] PCI DSS Level 4 compliance
- [ ] Tokenization for all payment methods
- [ ] 3D Secure for transactions
- [ ] Fraud monitoring integration

### 🔴 PHASE 3: ADVANCED PAYMENT SECURITY
- [ ] PCI DSS Level 1 certification
- [ ] Hardware security modules for keys
- [ ] Dedicated security team
- [ ] Annual external audits

---

## 🔧 INFRASTRUCTURE SECURITY

### 🟢 PHASE 1: BASIC INFRASTRUCTURE (Launch)
- [ ] Firewall rules (allow only necessary ports)
- [ ] Database in private subnet
- [ ] Automated daily backups
- [ ] Environment variables for secrets (never in code)
- [ ] Regular OS security updates

### 🟡 PHASE 2: ENHANCED INFRASTRUCTURE
- [ ] WAF (Web Application Firewall)
- [ ] DDoS protection
- [ ] Vulnerability scanning (weekly)
- [ ] Penetration testing (quarterly)
- [ ] Intrusion detection system

### 🔴 PHASE 3: ADVANCED INFRASTRUCTURE
- [ ] Multi-region active-passive
- [ ] Immutable infrastructure
- [ ] Zero-trust network architecture
- [ ] 24/7 security monitoring

---

## 📝 DOCUMENTATION & COMPLIANCE

### 🟢 PHASE 1: BASIC DOCS (Launch)
- [ ] Security checklist for deployment
- [ ] Incident response plan (simple)
- [ ] Password policy documentation

### 🟡 PHASE 2: ENHANCED DOCS
- [ ] SOC2 readiness documentation
- [ ] Data processing agreements
- [ ] Vendor security assessments
- [ ] Employee security training

### 🔴 PHASE 3: ADVANCED COMPLIANCE
- [ ] SOC2 Type II audit
- [ ] ISO 27001 certification
- [ ] GDPR representative (if EU users)
- [ ] Regular compliance reviews

---

## 🚀 LAUNCH CHECKLIST (Minimum Viable Security)

### Owner Security
- [ ] Single owner account
- [ ] Strong password + 2FA
- [ ] Critical actions require password re-entry
- [ ] All owner actions logged

### User Security
- [ ] Password requirements enforced
- [ ] Email confirmation on signup
- [ ] Password reset flow
- [ ] HTTPS everywhere

### Infrastructure
- [ ] Database backups automated
- [ ] Secrets in environment variables
- [ ] Firewall configured
- [ ] Regular updates scheduled

### Payments (if applicable)
- [ ] No raw card storage
- [ ] Use Stripe/Paystack tokens
- [ ] PCI SAQ completed

---

## 📈 TRIGGERS FOR NEXT PHASE

| Trigger | Move to Phase |
|--------|---------------|
| Launch complete | Start Phase 2 Owner + Phase 2 User |
| 1,000 users | Enhance user security |
| Handling payments | Prioritize payment security |
| 10,000 users | Add fraud detection |
| 5 employees | Add role-based access |
| 50,000 users | Start Phase 3 planning |
| Investment round | Full trustee system + HSM |
| Enterprise customers | SOC2 certification |

---

## 🎯 THIS WEEK'S FOCUS (Owner Launch Prep)

### Day 1-2: Database
- [ ] Create owners table
- [ ] Create audit_logs table
- [ ] Test single owner constraint

### Day 3-4: Authentication
- [ ] Implement password hashing
- [ ] Add 2FA with authenticator app
- [ ] Test login flow

### Day 5: Critical Actions
- [ ] Define critical actions list
- [ ] Add password confirmation middleware
- [ ] Test with sample actions

### Day 6: Audit Logging
- [ ] Implement audit logger
- [ ] Log all owner actions
- [ ] Build simple log viewer

### Day 7: Documentation
- [ ] Document owner setup
- [ ] Document recovery process
- [ ] Add to runbook

---

## 🔐 QUICK START CODE SNIPPETS

### Owner Model (SQL)
```sql
CREATE TABLE owners (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    twofa_secret TEXT,
    twofa_enabled BOOLEAN DEFAULT false,
    role TEXT DEFAULT 'owner',
    created_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP,
    last_login_ip INET
);

-- Ensure only one owner
CREATE UNIQUE INDEX single_owner_check ON owners ((role IS NOT NULL)) WHERE role = 'owner';
Last Updated: 2026-03-14