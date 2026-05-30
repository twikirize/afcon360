# Identity Policies and Data Protection

## Overview

This document outlines the identity policies and data protection measures enforced throughout the system to ensure internal identifiers are never exposed to external parties.

## Core Principles

### 1. Identity Separation

The system maintains three distinct identity layers:

- **Internal User ID (BIGINT)**: Database primary key, used for joins and foreign keys only. NEVER exposed externally.
- **External User ID (UUID)**: Public identifier used in APIs, URLs, sessions, and user-facing operations.
- **Account ID (UUID)**: Wallet/account identifier used for financial operations.

### Organisation Identity

| Identity Type | Storage | Exposure |
|---------------|---------|----------|
| Internal ID | BIGINT | ❌ NEVER expose |
| Public ID | UUID | ✅ Always expose |

**Rule:** `Organisation.id` (BIGINT) is internal only. `Organisation.public_id` (UUID) is for APIs.

### 2. Exposure Rules

**NEVER EXPOSE:**
- `User.id` (BIGINT) - Internal database identifier
- `Organisation.id` (BIGINT) - Internal database identifier
- Any sequential or predictable internal IDs

**ALWAYS EXPOSE:**
- `User.public_id` (UUID) - Public user identifier
- `Organisation.public_id` (UUID) - Public organisation identifier
- `Account.id` (UUID) - Account identifier
- `Transaction.id` (UUID) - Transaction identifier

### Wallet/Account Identity

| Field | Type | Exposure |
|-------|------|----------|
| `Account.id` | UUID | ✅ Safe to expose |
| `Account.user_id` | BIGINT | ❌ NEVER expose (internal FK only) |
| `Account.owner_type` | Enum | ⚠️ Can expose (USER/ORGANISATION) |

## Implementation Guidelines

### API Responses

All API responses MUST use public identifiers:

```python
# ✅ CORRECT
return jsonify({
    'user_id': user.public_id,  # UUID
    'account_id': account.id,   # UUID
    'transaction_id': transaction.id  # UUID
})

# ❌ WRONG
return jsonify({
    'user_id': user.id,  # BIGINT - SECURITY ISSUE
    'account_id': account.user_id  # BIGINT - SECURITY ISSUE
})
```

### Logging

All log statements MUST use public identifiers for user identification:

```python
# ✅ CORRECT
logger.info(f"User {user.public_id} performed action")

# ❌ WRONG
logger.info(f"User {user.id} performed action")  # Exposes internal ID
```

### Templates

All templates MUST use public identifiers:

```html
<!-- ✅ CORRECT -->
<div>User ID: {{ user.public_id }}</div>

<!-- ❌ WRONG -->
<div>User ID: {{ user.id }}</div>  <!-- Exposes internal ID -->
```

### Database Queries

Database queries use internal IDs for performance, but these are never exposed:

```python
# Convert public ID to internal for DB query
user = User.query.filter_by(public_id=public_id).first()
internal_id = user.id  # Use internal ID for joins

# Query using internal ID
account = AccountModel.query.filter_by(
    user_id=internal_id,
    owner_type=AccountOwnerType.USER
).first()
```

### Session Management

Flask-Login MUST use `public_id`, NOT `id`:

```python
# ✅ CORRECT - in User model
def get_id(self):
    return str(self.public_id)  # UUID for session

# ❌ WRONG
def get_id(self):
    return str(self.id)  # BIGINT - exposes internal ID
```

### URL Patterns

- User URLs: `/users/{user.public_id}` (UUID)
- Organisation URLs: `/orgs/{org.public_id}` (UUID)
- Wallet URLs: `/wallet/{account.id}` (UUID)

**NEVER use:** `/users/123` or `/wallet/1` (sequential IDs)

## Enforcement Mechanisms

### 1. Code Review Checklist

- [ ] API responses never return `User.id` or `Organisation.id`
- [ ] Log statements use `public_id` not `id`
- [ ] Templates use `public_id` not `id`
- [ ] All user-facing identifiers are UUIDs
- [ ] Internal BIGINTs only used for database operations
- [ ] Flask-Login user_loader uses public_id, not id
- [ ] Session cookie contains UUID, not BIGINT
- [ ] URL parameters use UUID, not integers
- [ ] No route accepts `<int:user_id>` - use `<string:user_public_id>`
- [ ] Admin routes also use UUIDs for user identification

### 2. Automated Checks

- Linting rules to catch direct `id` usage in API responses
- Static analysis to detect `logger.*\.id` patterns
- Template validation to prevent `user.id` or `organisation.id` exposure

### 3. Training

- All developers must understand identity separation
- Code reviews must verify identity protection
- Security testing must include ID exposure checks

## Common Patterns

### User Lookup Pattern

```python
def get_user_by_identifier(identifier):
    """Lookup user by public_id (UUID) or email"""
    if isinstance(identifier, str) and len(identifier) > 20:
        # Assume UUID
        return User.query.filter_by(public_id=identifier).first()
    else:
        # Assume email
        return User.query.filter_by(email=identifier).first()
```

### Account Retrieval Pattern

```python
def get_user_account(user):
    """Get user's wallet account using proper owner_type filtering"""
    from app.wallet.models.ledger import AccountModel, AccountOwnerType
    
    return AccountModel.query.filter_by(
        user_id=user.id,  # Internal ID for DB query
        owner_type=AccountOwnerType.USER
    ).first()
```

### API Response Pattern

```python
def serialize_user(user):
    """Serialize user for API response - never expose internal ID"""
    return {
        'user_id': user.public_id,  # Public UUID
        'name': user.name,
        'email': user.email,
        'phone': user.phone
    }
```

## Security Implications

### Why Identity Separation Matters

1. **Prevents Enumeration Attack**: Sequential IDs allow attackers to guess user count and iterate through users
2. **Privacy Protection**: Internal IDs can reveal system architecture and user creation patterns
3. **Database Security**: Exposing internal IDs can facilitate SQL injection attacks
4. **Audit Trail**: Public IDs ensure audit logs don't expose sensitive internal information

### Consequences of Violation

- Data breach potential
- User privacy violation
- Regulatory non-compliance (GDPR, CCPA)
- System architecture exposure
- Increased attack surface

## References

- Database Schema: Users table has `id` (BIGINT) and `public_id` (UUID)
- AccountModel: Uses `user_id` (BIGINT FK) but should expose `id` (UUID)
- Flask-Login: Configured to use `public_id` for session management
- Audit System: Uses `public_id` for user identification in logs

## Database Migration Rule

**BEFORE deploying code that adds new columns:**
1. Always create a migration first
2. Run `flask db upgrade` BEFORE code deployment
3. Verify columns exist with `SELECT column_name FROM information_schema.columns`

**Violation example:** Code adds `owner_type` but migration not run → ❌
**Correct procedure:** Migration first, then deploy code → ✅

## Compliance

This policy aligns with:
- GDPR Article 32 (Security of Processing)
- OWASP Top 10 (A01:2021 - Broken Access Control)
- PCI DSS Requirement 3.1 (Protect stored cardholder data)

---

**Document Version**: 2.0  
**Last Updated**: 2026-05-04  
**Owner**: Security Team  
**Review Date**: 2026-08-04
