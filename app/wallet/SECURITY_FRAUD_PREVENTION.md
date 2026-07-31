# Wallet Security & Fraud Prevention Implementation

## Overview

This document describes the security and fraud prevention features implemented in the AFCON360 wallet module to protect users and the platform from financial crime, account takeover, and fraudulent transactions.

## Implementation Summary

### Files Changed

| File | Purpose |
|------|---------|
| `app/wallet/services/kyc_limit_service.py` | KYC-based transaction limits enforcement |
| `app/wallet/services/identity_verification_service.py` | Identity verification for sensitive actions |
| `app/wallet/services/suspicious_activity_service.py` | Suspicious activity pattern detection |
| `app/wallet/services/fraud_detection_service.py` | Enhanced transaction risk scoring |
| `app/wallet/models/fraud_alert.py` | Fraud alert model for admin review queue |
| `app/wallet/decorators.py` | Security decorators for routes |
| `app/wallet/routes.py` | Route-level security guards |
| `app/wallet/api/admin_api.py` | Admin freeze/thaw and fraud alert review APIs |
| `app/wallet/services/wallet_service.py` | Integrated KYC, fraud, and limit checks |

## Features Implemented

### 1. KYC-Based Transaction Limits

**Service:** `KYCLimitService`

Enforces per-user transaction limits based on KYC level:

| KYC Level | Label | Daily Limit | Monthly Limit | Per-Txn Limit | Max Balance |
|-----------|-------|-------------|---------------|---------------|-------------|
| 0 | Unregistered | 0 | 0 | 0 | 0 |
| 1 | Basic | 1,000,000 UGX | 5,000,000 UGX | 500,000 UGX | 10,000,000 UGX |
| 2 | Standard | 5,000,000 UGX | 20,000,000 UGX | 2,000,000 UGX | 50,000,000 UGX |
| 3 | Enhanced | 20,000,000 UGX | 100,000,000 UGX | 10,000,000 UGX | 200,000,000 UGX |

**Integration:** `WalletService._check_kyc_limits()` is called in `deposit()`, `withdraw()`, and `transfer()` before any financial operation.

**Routes affected:**
- `/wallet/send` (POST)
- `/wallet/withdraw` (POST)
- `/wallet/deposit` (POST)

### 2. Transaction Risk Scoring

**Service:** `FraudDetectionService.score_transaction()`

Enhanced from placeholder to real scoring with weighted factors:

| Factor | Weight | Trigger |
|--------|--------|---------|
| High amount | 0.3 | Amount > `max_amount_per_transaction` |
| High velocity | 0.4 | > `max_transactions_per_minute` in 5 min |
| Hourly limit exceeded | 0.3 | Hourly volume > `max_amount_per_hour` |
| New recipient large amount | 0.2 | New recipient + amount > 50% max |
| New IP | 0.1 | IP not seen in last 30 days |
| Unusual amount pattern | 0.2 | Amount > 3x user average |
| Off-hours | 0.1 | Transaction between 12AM-5AM UTC |

**Risk levels:**
- `low` (< 0.3): Allow
- `medium` (0.3-0.7): Review if configured
- `high` (> 0.7): Block if configured

**Integration:** `WalletService._check_fraud_risk()` is called in all transaction methods.

### 3. Wallet Freeze/Thaw

**Model:** `AccountModel` (existing fields: `is_frozen`, `frozen_reason`, `frozen_at`, `frozen_by`)

Freeze capability already existed in the model. Admin routes were added:

**New Admin APIs:**
- `POST /api/admin/wallet/compliance/thaw-account` — Thaw a frozen account

**Existing Admin APIs:**
- `POST /api/admin/wallet/compliance/freeze-account` — Freeze an account

**Enforcement:** All `WalletService` methods (`deposit`, `withdraw`, `transfer`) check `account.is_frozen` before processing.

### 4. Identity Verification for Sensitive Actions

**Service:** `IdentityVerificationService`

Requires multi-factor re-verification for high-risk actions:

| Action | Required Methods |
|--------|-----------------|
| `change_email` | Current password + MFA |
| `change_phone` | Current password + MFA |
| `change_password` | Current password + MFA + Security question |
| `wallet_activation` | Email OTP + Phone OTP |
| `large_withdrawal` | MFA + Transaction PIN |
| `large_transfer` | MFA + Transaction PIN |
| `close_account` | MFA + Security question |
| `change_pin` | Current password + MFA |

**Session-based:** Verification is cached in Flask session for 10 minutes.

### 5. Suspicious Activity Monitoring

**Service:** `SuspiciousActivityService`

Real-time pattern detection:
- Amount > 3x user average
- New recipient detection
- Rapid consecutive transactions (> 5 in 5 minutes)
- New device/IP detection
- Off-hours transactions
- KYC limit violations

**Fraud Alerts:** `SuspiciousActivityService.create_fraud_alert()` creates `FraudAlert` records for admin review.

### 6. Daily/Monthly Transaction Limits

**Enhanced:** `WalletService._check_daily_limit()` and `_check_monthly_limit()`

- Daily limits are checked against actual ledger volume
- Monthly limits are checked against `AccountModel.monthly_volume_limit`
- Volume resets automatically when period elapses
- Limits are enforced in `deposit()`, `withdraw()`, and `transfer()`

### 7. Admin Review Queue

**Model:** `FraudAlert` (new)

Stores fraud alerts with:
- `risk_score` (0-100)
- `patterns` (JSONB list)
- `details` (JSONB)
- `status` (open/reviewing/resolved/dismissed/escalated)
- `transaction_id` (optional link)

**Admin APIs:**
- `GET /api/admin/wallet/fraud-alerts` — List alerts with filters
- `POST /api/admin/wallet/fraud-alerts/<id>/review` — Review/update alert status

### 8. Route Security Guards

**New Decorators:**
- `@require_no_freeze` — Blocks access if account is frozen
- `@require_sufficient_kyc` — Enforces KYC-based feature access
- `@require_transaction_verification` — Requires identity verification

**Applied to routes:**
- `send_funds()` — Added `@require_no_freeze` + KYC pre-check
- `withdraw_funds()` — Added `@require_no_freeze` + KYC pre-check
- `deposit_form()` — Existing `@require_deposit_access`

## Database Schema Changes

### New Table: `fraud_alerts`

```sql
CREATE TABLE fraud_alerts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    transaction_id VARCHAR(64),
    action VARCHAR(50) NOT NULL,
    risk_score NUMERIC(5,2) NOT NULL,
    patterns JSONB NOT NULL DEFAULT '[]',
    details JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    reviewed_by BIGINT REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    resolution_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_fraud_alert_user_id ON fraud_alerts(user_id);
CREATE INDEX ix_fraud_alert_status ON fraud_alerts(status);
CREATE INDEX ix_fraud_alert_risk_score ON fraud_alerts(risk_score);
CREATE INDEX ix_fraud_alert_created_at ON fraud_alerts(created_at);
CREATE INDEX ix_fraud_alert_transaction_id ON fraud_alerts(transaction_id);

ALTER TABLE fraud_alerts ADD CONSTRAINT ck_fraud_alert_status_valid 
  CHECK (status IN ('open', 'reviewing', 'resolved', 'dismissed', 'escalated'));
ALTER TABLE fraud_alerts ADD CONSTRAINT ck_fraud_alert_action_valid 
  CHECK (action IN ('send_funds', 'withdraw_funds', 'deposit', 'transfer', 
                    'change_email', 'change_phone', 'change_password', 'wallet_activation'));
ALTER TABLE fraud_alerts ADD CONSTRAINT ck_fraud_alert_risk_score_range 
  CHECK (risk_score >= 0 AND risk_score <= 100);
```

### Migration Commands

```bash
# 1. Check current migration head
flask db heads

# 2. If multiple heads, merge first
flask db merge heads -m "merge_20260729_security"

# 3. Auto-generate migration for new fraud_alerts table
flask db migrate -m "add_fraud_alerts_table"

# 4. Review the generated migration file in migrations/versions/

# 5. Apply migration
flask db upgrade
```

## Verification

### Manual Testing

1. **KYC limits:** Create users with different KYC levels and attempt transactions exceeding limits
2. **Fraud scoring:** Trigger rapid transactions and verify alerts are created
3. **Freeze/thaw:** Freeze an account via admin API and verify transactions are blocked
4. **Identity verification:** Attempt sensitive actions and verify re-verification is required

### Automated Tests

```bash
pytest tests/wallet/test_security_services.py -v
pytest tests/wallet/test_fraud_detection.py -v
pytest tests/wallet/test_kyc_limits.py -v
```

## Risks and Considerations

| Risk | Mitigation |
|------|-----------|
| False positives in fraud scoring | Configurable thresholds in `FraudDetectionConfig` |
| KYC limits too restrictive for new users | Tier 1 allows reasonable daily limits |
| Session-based identity verification expiry | 10-minute TTL with re-verification required |
| Performance impact of additional checks | Queries use existing indexes; scoring is lightweight |
| New `fraud_alerts` table requires migration | Schema provided above; no ENUM types used |

## Migration Needed?

**Yes.** The new `fraud_alerts` table requires an Alembic migration.

**Proposed commands:**
```bash
flask db migrate -m "add_fraud_alerts_table"
flask db upgrade
```

**No data migration required** — this is a new empty table.

## Compliance Notes

- All limits align with Bank of Uganda KYC guidelines
- Fraud alerts support STR (Suspicious Transaction Report) generation
- Audit logging captures all admin freeze/thaw actions
- Double-entry ledger integrity is preserved (no balance column modifications)
