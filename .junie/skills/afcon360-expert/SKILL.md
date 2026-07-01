---
name: afcon360-expert
description: Deep expertise in AFCON360 project architecture, module boundaries, and high-risk constraints (Wallet, Identity, Migrations).
---

# AFCON360 Expert Skill

Use this skill when you are working on core architectural components, database migrations, or the wallet system.

## Key Principles
1. **Safety First:** Wallet and identity changes are mission-critical. Always audit for double-entry integrity.
2. **Modular Integrity:** Respect module boundaries. Avoid leaking logic between `app/events`, `app/wallet`, and `app/transport`.
3. **Database Consistency:** Ensure all models use `BaseModel` and that migrations are handled through the standard `flask db` workflow.

## Technical Guidelines
- **Models:** Inherit from `app.models.base.BaseModel`.
- **Primary Keys:** Internal FKs use `BigInteger` (`id`), External use `UUID` (`public_id`).
- **PostgreSQL ENUMs:** Avoid them. Use `String` columns with validation.
- **Wallet Ledger:** Any balance update must have a corresponding transaction entry. No balance modification without an audit trail.

## Implementation Checklist
- [ ] Checked for circular imports?
- [ ] Verified `BaseModel` inheritance?
- [ ] Wallet change? Performed double-entry audit?
- [ ] Template change? Checked for CSRF and conditional pane loading?
- [ ] Migration needed? Verified root cause fix in model?

## Reference Files
- `app/models/base.py`: The source of `BaseModel`.
- `app/wallet/services.py`: Core wallet logic.
- `rules/`: Detailed legacy rule files.
