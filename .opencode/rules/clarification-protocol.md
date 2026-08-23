# Clarification Protocol for Locked Files

## Trigger

Permission denied on write to:
- `migrations/versions/*.py`
- `alembic/**/*.py`
- `app/wallet/models/*.py`
- `app/models/base.py`

## Required Response — STOP, Do Not Workaround

When blocked, respond with exactly this format:

```
BLOCKED: <file-path>
CHANGE: <exact modification needed>
REASON: <business rule / bug fix / feature / constitutional requirement>
RISK: <TRIVIAL|LOCAL|BEHAVIORAL|ARCHITECTURAL|HIGH_RISK>
ALTERNATIVES: <considered approaches>
CONSTITUTION: <AGENTS.md sections>
```

## User Decision Options

- `APPROVE` — One-time permission for this specific change
- `GUIDE` — Alternative approach (e.g., "use service layer instead")
- `DENY` — Not authorized; find another solution
- `DEFER` — Record in BACKLOG.md for later

## Migration-Specific Workflow (Additional)

1. Agent proposes: `flask db migrate -m "description"`
2. User executes migration command
3. Agent inspects generated file for correctness
4. User approves `flask db upgrade` after agent verification

## Example

```
BLOCKED: app/wallet/models/account.py
CHANGE: Add kyc_status column (String(20), nullable=False, default='pending')
REASON: New compliance flow requires KYC status tracking on wallet accounts (HIGH_RISK)
RISK: HIGH_RISK (§18.1 Wallet = CRITICAL)
ALTERNATIVES: Add to separate KYC model with FK to account
CONSTITUTION: §18.1, §34, §17 (Wallet ownership)
```