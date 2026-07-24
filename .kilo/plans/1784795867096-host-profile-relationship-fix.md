# Fix SQLAlchemy Ambiguous Relationship Errors in HostProfile Models

## Root Cause

SQLAlchemy raises `"Could not determine join condition"` because `HostProfile` defines:

```python
user_id     = Column(BigInteger, ForeignKey("users.id", ...), ...)
user        = relationship("User", backref="host_profile")

suspended_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
```

Both `user_id` and `suspended_by` point to `users.id`, creating two FK paths between `users` and `accommodation_host_profiles`. The automatic `backref="host_profile"` on `User` adds a third path perspective, so SQLAlchemy cannot infer which column to use — it needs an explicit hint.

The same structural pattern applies to `HostOrganisationProfile.org` (`org_id` and `suspended_by` → `organisations.id`).

**GuestProfile and Property already specify `foreign_keys` correctly** and are unaffected.

---

## Plan

### Task 1 — Add `foreign_keys=[user_id]` to `HostProfile.user`

**File:** `app/accommodation/models/host_profile.py`  
**Line:** 35

```python
# BEFORE
user = relationship("User", backref="host_profile")

# AFTER
user = relationship("User", foreign_keys=[user_id], backref="host_profile")
```

### Task 2 — Add `foreign_keys=[org_id]` to `HostOrganisationProfile.org`

**File:** `app/accommodation/models/host_profile.py`  
**Line:** 96

```python
# BEFORE
org = relationship("Organisation", backref="host_profile")

# AFTER
org = relationship("Organisation", foreign_keys=[org_id], backref="host_profile")
```

### Task 3 — Verify model imports cleanly

Run:

```powershell
python -c "from app import create_app"
```

This confirms the SQLAlchemy mapper can resolve all unambiguous relationships on startup.

---

## Pre-Flight Checks

- [x] Confirmed `HostProfile.user_id` and `HostProfile.suspended_by` both reference `users.id` — the ambiguity source
- [x] Confirmed `GuestProfile` already uses `foreign_keys=[guest_user_id]` — no change needed
- [x] Confirmed `Property.owner_user` / `owner_org` already use `foreign_keys` — no change needed
- [x] Confirmed `AccommodationBooking.guest` / `host` already use `foreign_keys` — no change needed

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `backref="host_profile"` name collision if a future model also uses `backref="host_profile"` on `User` | Low | Documented in plan; any new backref must use a distinct name or switch to `back_populates` |
| Restart artefacts from stale model state | Low | Full process restart after edit |

## Migration Needed

No — this is a pure ORM relationship configuration fix. Column schemas are unchanged. No Alembic migration required.
