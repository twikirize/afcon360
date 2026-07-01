# AFCON360 — Forensic Audit & Compliance

## Forensic Audit Service
- Location: `app/audit/forensic_audit.py`
- Tracks full lifecycle: attempt → completion → blocked
- Methods: `log_attempt()`, `log_completion()`, `log_blocked()`
- Timeline query: `get_audit_timeline()`, pending reviews: `get_pending_reviews()`
- Suspicious pattern detection: `get_suspicious_patterns()`

## Enhanced Audit Columns (all audit tables)
`attempted_at`, `status` (pending/completed/blocked/rejected), `reviewed_by_user_id`,
`reviewed_at`, `review_notes`, `ip_address`, `user_agent`, `session_id`,
`correlation_id`, `risk_score`

## Known Schema Issue
- `owner_audit_logs.is_deleted` column may be missing — queries use graceful error handling
- Preserve this pattern: wrap `owner_audit_logs` queries in try/except

## What Must Be Logged
- Role changes → `OwnerAuditLog`
- Wallet transactions → `ForensicAuditService`
- KYC status changes → `ForensicAuditService`
- Login/registration → already integrated in `app/auth/services.py`

## Compliance Requirements
- **Bank of Uganda**: KYC approval timelines and statistics
- **FIA Uganda**: All transactions > UGX 20M with timestamps
- Suspicious pattern detection runs hourly via Celery
- Stale review escalation (>24h) runs every 4 hours via Celery
- Daily compliance reports generated automatically

## API Endpoints
- `GET /api/audit/timeline/<entity_type>/<entity_id>`
- `GET /api/audit/pending-reviews`
- `POST /api/audit/review/<audit_id>`
- `GET /api/audit/suspicious-patterns`
- `GET /api/audit/compliance-report`

## Dashboards with Audit Components
- Owner dashboard — system-wide oversight
- Compliance officer dashboard — regulatory monitoring
- Auditor dashboard — `templates/auditor/dashboard.html`
- User dashboard — personal audit trail
