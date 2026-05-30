# AFCON 360 - Final Architecture Decision & Implementation
## Codeium Agent Instructions - Architecture Pass 5

**Version:** 5.0 - FINAL ARCHITECTURE
**Date:** 2026-05-06
**Authority:** This document supersedes all previous passes on fan/role/profile decisions.
**Principle:** Surgical changes only. Every change listed. Nothing unlisted is touched.

---

## THE ARCHITECTURE DECISION IN ONE PARAGRAPH

AFCON 360 is a super app with a tournament skin. Every person has one
account with a default role of "user". The word "fan" is a product label
and a UI skin - not a database role and not a separate profile model.
Fan allegiance (which team someone supports) is stored as a single
nullable field on UserProfile. All tournament-specific UI features are
controlled by MODULE_FLAGS["tournament"] in config.py. When the
tournament ends, the flag is toggled off - accounts, wallets, bookings,
and history are completely untouched.

---

## PHASE 0 - READ BEFORE TOUCHING ANYTHING

### What you must NOT change
- Any route URLs or blueprint prefixes
- The wallet system (models, routes, services)
- The KYC system (kyc_compliance.py, kyc_routes.py)
- The org model (Organisation, OrganisationMember, OrgUserRole)
- All admin roles (owner, super_admin, admin, moderator, support, auditor)
- All service provider roles (driver, transport_admin, accommodation_admin, event_manager)
- The onboarding blueprints and routes built in previous passes
- The login/logout/register routes
- Any migration already applied to the database

### What you ARE changing
Five things only - listed in Phases 1 through 5 below.
Execute them in order. Do not combine phases.

---

## PHASE 1 - DATABASE: Add fields to UserProfile, create migration

### 1.1 Add 4 columns to UserProfile model

**File:** `app/profile/models.py`

Find the `UserProfile` class. After the existing `email` column, add:

```python
    # ── Fan / tournament identity (optional, tournament skin uses these) ──
    fan_team = Column(String(64), nullable=True, index=True)
    # Which AFCON team this user supports e.g. "Nigeria", "Ghana", "Uganda"
    # NULL means not declared. Not a role. Not a permission. Just a preference.

    display_name = Column(String(128), nullable=True)
    # Public-facing name shown on profile cards. Falls back to full_name if null.

    avatar_url = Column(String(512), nullable=True)
    # Profile photo URL. Stored externally (S3/Cloudinary). Null = use initials.

    bio = Column(Text, nullable=True)
    # Short personal description shown on public profile. Max 500 chars.
```

Do not change any other column. Do not change any relationship.
Do not change IMMUTABLE_AFTER_VERIFICATION - these 4 new fields are
mutable at any time.

### 1.2 Create the migration

```bash
flask db migrate -m "add_fan_fields_to_user_profile"
```

Check the generated migration file. It must only contain:
- `op.add_column('user_profiles', sa.Column('fan_team', ...))`
- `op.add_column('user_profiles', sa.Column('display_name', ...))`
- `op.add_column('user_profiles', sa.Column('avatar_url', ...))`
- `op.add_column('user_profiles', sa.Column('bio', ...))`
- One `op.create_index` for fan_team

If it contains anything else - especially any `op.drop_table` -
STOP and report before running.

### 1.3 Apply the migration

```bash
flask db upgrade
```

### 1.4 Verify columns exist

```bash
flask shell
>>> from app.extensions import db
>>> from sqlalchemy import inspect, text
>>> cols = [c['name'] for c in inspect(db.engine).get_columns('user_profiles')]
>>> assert 'fan_team' in cols, "MISSING fan_team"
>>> assert 'display_name' in cols, "MISSING display_name"
>>> assert 'avatar_url' in cols, "MISSING avatar_url"
>>> assert 'bio' in cols, "MISSING bio"
>>> print("Phase 1 verified")
```

Expected output: `Phase 1 verified`

---

## PHASE 2 - DATABASE: Migrate FanProfile data and drop table

### 2.1 Check if FanProfile table has any data

```bash
flask shell
>>> from app.extensions import db
>>> from sqlalchemy import text
>>> result = db.session.execute(text("SELECT COUNT(*) FROM fan_profiles")).scalar()
>>> print(f"FanProfile rows: {result}")
```

### 2.2 Migrate existing data into UserProfile

If count > 0, run this migration script first.
If count == 0, skip to 2.3.

Create `scripts/migrate_fan_profiles.py`:

```python
"""
One-time migration: copy FanProfile data into UserProfile new columns.
Run with: flask shell < scripts/migrate_fan_profiles.py
"""
from app.extensions import db
from sqlalchemy import text

rows = db.session.execute(text("""
    SELECT
        fp.user_id,
        fp.display_name,
        fp.avatar_url,
        fp.bio,
        fp.nationality
    FROM fan_profiles fp
""")).fetchall()

print(f"Migrating {len(rows)} FanProfile records...")

for row in rows:
    # fan_profiles.user_id is the internal BIGINT users.id
    # UserProfile.user_id is users.public_id (UUID string)
    # We need to join through users table
    user_public_id = db.session.execute(
        text("SELECT public_id FROM users WHERE id = :uid"),
        {"uid": row.user_id}
    ).scalar()

    if not user_public_id:
        print(f"  SKIP: no user found for fan_profiles.user_id={row.user_id}")
        continue

    db.session.execute(text("""
        UPDATE user_profiles SET
            display_name = COALESCE(display_name, :display_name),
            avatar_url   = COALESCE(avatar_url, :avatar_url),
            bio          = COALESCE(bio, :bio)
        WHERE user_id = :public_id
    """), {
        "display_name": row.display_name,
        "avatar_url":   row.avatar_url,
        "bio":          row.bio,
        "public_id":    user_public_id,
    })

    # nationality already exists on UserProfile - only copy if empty
    if row.nationality:
        db.session.execute(text("""
            UPDATE user_profiles SET nationality = :nat
            WHERE user_id = :public_id AND (nationality IS NULL OR nationality = '')
        """), {"nat": row.nationality, "public_id": user_public_id})

    print(f"  OK: migrated fan_profile for user {user_public_id}")

db.session.commit()
print("Migration complete.")
```

Run it:
```bash
flask shell < scripts/migrate_fan_profiles.py
```

### 2.3 Drop FanProfile model and table

**File:** `app/fan/models.py`

Replace the entire file contents with:

```python
# app/fan/models.py
"""
FanProfile has been merged into UserProfile (app/profile/models.py).
Fields moved: display_name, avatar_url, bio, fan_team (new).
This file is kept as a placeholder to avoid import errors during transition.
All fan_profiles references should be updated to use UserProfile instead.
"""
# DEPRECATED - do not add new code here
```

Create a new migration to drop the table:

```bash
flask db migrate -m "drop_fan_profiles_table"
```

Check the generated file - it must contain `op.drop_table('fan_profiles')`.
Apply it:

```bash
flask db upgrade
```

Verify:
```bash
flask shell
>>> from sqlalchemy import inspect
>>> from app.extensions import db
>>> tables = inspect(db.engine).get_table_names()
>>> assert 'fan_profiles' not in tables, "fan_profiles table still exists"
>>> print("Phase 2 verified - fan_profiles dropped")
```

---

## PHASE 3 - CODE: Remove get_or_create_fan() calls

### 3.1 Find every callsite

```bash
grep -rn "get_or_create_fan\|FanProfile\|fan_profiles\|from app.fan.models" app/ --include="*.py"
```

Record every file returned. You must fix all of them.

### 3.2 Fix each callsite

For every occurrence, the replacement is the same pattern:

```python
# BEFORE - creates a FanProfile record (no longer exists):
from app.fan.services.registry import get_or_create_fan
fan = get_or_create_fan(user.id)
if fan:
    fan.display_name = full_name

# AFTER - updates UserProfile directly:
from app.profile.models import get_profile_by_user
profile = get_profile_by_user(user.public_id)
if profile and not profile.display_name:
    profile.display_name = full_name
# No separate record needed - UserProfile is the single source of truth
```

### 3.3 Fix app/fan/routes.py specifically

The fan dashboard route uses `get_or_create_fan`. Replace the profile
section with a direct UserProfile lookup:

```python
# In fan/routes.py dashboard() - REPLACE this pattern:
# profile = get_or_create_fan(internal_id)
# WITH:
from app.profile.models import get_profile_by_user
profile = get_profile_by_user(current_user.public_id)
# profile is now UserProfile - has full_name, display_name, avatar_url, bio, fan_team
```

### 3.4 Fix app/auth/onboarding_routes.py

In fan_onboarding() and _commit_driver_onboarding(), remove the
get_or_create_fan() calls added in previous passes. Replace with the
UserProfile pattern from 3.2.

### 3.5 Verify no FanProfile references remain

```bash
grep -rn "get_or_create_fan\|FanProfile\|from app.fan.models import" app/ --include="*.py"
```

Expected: zero matches (except the deprecated comment in app/fan/models.py).

---

## PHASE 4 - CODE: Fix the "fan" role → "user" role alignment

### 4.1 The situation

`register_user()` in `app/auth/services.py` already assigns the `"user"` role.
`seed_roles.py` defines a `"fan"` role at level 13.
These must be aligned. The default end-user role is `"user"`.
The word "fan" exists only in the UI, not in RBAC.

### 4.2 Update seed_roles.py

**File:** `app/auth/seed_roles.py`

Find this line in `GLOBAL_ROLE_DEFS`:
```python
RoleDef("fan", 13, "Default end-user; no admin access"),
```

Change it to:
```python
RoleDef("user", 13, "Default registered user - can browse and book services"),
```

Also update `GLOBAL_PERMISSION_DEFS` - find every place `"fan"` appears
in the `roles` list of a permission and change it to `"user"`:

```python
# Example - find and replace pattern:
# BEFORE:
PermDef("accommodation.search", "Search and view listings",
        ["owner", "super_admin", "admin", "fan"]),
# AFTER:
PermDef("accommodation.search", "Search and view listings",
        ["owner", "super_admin", "admin", "user"]),
```

Do this for ALL permission definitions that include `"fan"` in their roles list.

### 4.3 Update _dashboard_for_user in app/auth/routes.py

Find any reference to `"fan"` as a role name and replace with `"user"`:

```python
# BEFORE (if present):
if "fan" in role_names:
    return url_for("fan.dashboard")

# AFTER:
if "user" in role_names:
    return url_for("fan.dashboard")
# Note: URL stays as fan.dashboard - we are not renaming the blueprint
```

### 4.4 Update helpers.py if needed

```bash
grep -n '"fan"' app/auth/helpers.py app/auth/decorators.py app/auth/roles.py
```

Replace any `"fan"` used as a role name check with `"user"`.

### 4.5 Re-seed the database

```bash
flask seed-all
```

### 4.6 Update existing users in DB who have "fan" role

```bash
flask shell
>>> from app.extensions import db
>>> from sqlalchemy import text
>>>
>>> # Find the old fan role id and new user role id
>>> fan_role = db.session.execute(
...     text("SELECT id FROM roles WHERE name = 'fan'")
... ).fetchone()
>>>
>>> user_role = db.session.execute(
...     text("SELECT id FROM roles WHERE name = 'user'")
... ).fetchone()
>>>
>>> if fan_role and user_role:
...     result = db.session.execute(
...         text("UPDATE user_roles SET role_id = :new WHERE role_id = :old"),
...         {"new": user_role.id, "old": fan_role.id}
...     )
...     db.session.commit()
...     print(f"Updated {result.rowcount} user_roles rows from fan -> user")
... elif not fan_role:
...     print("No fan role found - already clean")
... elif not user_role:
...     print("ERROR: user role not found - run flask seed-all first")
```

### 4.7 Verify

```bash
flask shell
>>> from app.extensions import db
>>> from sqlalchemy import text
>>> fan_count = db.session.execute(
...     text("SELECT COUNT(*) FROM roles WHERE name = 'fan'")
... ).scalar()
>>> user_count = db.session.execute(
...     text("SELECT COUNT(*) FROM roles WHERE name = 'user'")
... ).scalar()
>>> print(f"fan role count: {fan_count} (should be 0)")
>>> print(f"user role count: {user_count} (should be 1)")
```

---

## PHASE 5 - CODE: Tournament skin via MODULE_FLAGS

### 5.1 Confirm flag exists in config.py

**File:** `app/config.py`

Find `MODULE_FLAGS`. Confirm `"tournament"` is present:

```python
MODULE_FLAGS = {
    "wallet":        ...,
    "tourism":       ...,
    "transport":     ...,
    "accommodation": ...,
    "tournament":    os.getenv("ENABLE_TOURNAMENT", "true").lower() == "true",
    "agents":        ...,
    "admin":         ...,
}
```

If `"tournament"` is missing, add it. Do not change any other flag.

### 5.2 Create a template context helper

**File:** `app/__init__.py`

Find the `inject_sitewide()` context processor. Add `tournament_mode` to it:

```python
@app.context_processor
def inject_sitewide() -> Dict:
    return {
        "app_name":             current_app.config.get("APP_NAME", "AFCON 360"),
        "tournament_name":      current_app.config.get("TOURNAMENT_NAME", "AFCON Tournament"),
        "year":                 current_app.config.get("YEAR", 2025),
        "require_email_verification": current_app.config.get("REQUIRE_EMAIL_VERIFICATION", False),
        "allow_username_login": current_app.config.get("ALLOW_USERNAME_LOGIN", True),
        # ADD THIS LINE ONLY:
        "tournament_mode":      current_app.config.get("MODULE_FLAGS", {}).get("tournament", False),
    }
```

### 5.3 Use tournament_mode in the fan dashboard template

**File:** `templates/fan/dashboard.html`

Find the section that shows fan-specific content (favorite team, match
scores, fan feed, etc.). Wrap it:

```html
{% if tournament_mode %}
  {# ── TOURNAMENT SKIN - only shown during AFCON ──────────── #}

  {% if profile and profile.fan_team %}
  <div class="fan-allegiance-badge">
    Supporting: <strong>{{ profile.fan_team }}</strong>
  </div>
  {% else %}
  <div class="fan-declare-prompt">
    <p>Which team are you supporting at AFCON?</p>
    <a href="{{ url_for('profile.edit_profile') }}#fan-team" class="btn btn-sm btn-outline-success">
      Declare your team
    </a>
  </div>
  {% endif %}

  {# Match feed, fan events, fan trips go here - all inside this block #}

{% endif %}
{# ── END TOURNAMENT SKIN ─────────────────────────────────── #}
```

### 5.4 Add fan_team to the profile edit form

**File:** `templates/profile/edit.html`

Add this field to the form (it is always editable - not locked after verification):

```html
<!-- Fan team declaration - shown always, relevant during tournament -->
<div class="mb-3">
  <label for="fan_team" class="form-label">
    AFCON team you support
    <span class="text-muted small">(optional)</span>
  </label>
  <select class="form-select" id="fan_team" name="fan_team">
    <option value="">Not declared</option>
    <option value="Algeria"   {% if profile.fan_team == 'Algeria' %}selected{% endif %}>Algeria</option>
    <option value="Angola"    {% if profile.fan_team == 'Angola' %}selected{% endif %}>Angola</option>
    <option value="Cameroon"  {% if profile.fan_team == 'Cameroon' %}selected{% endif %}>Cameroon</option>
    <option value="DR Congo"  {% if profile.fan_team == 'DR Congo' %}selected{% endif %}>DR Congo</option>
    <option value="Egypt"     {% if profile.fan_team == 'Egypt' %}selected{% endif %}>Egypt</option>
    <option value="Ghana"     {% if profile.fan_team == 'Ghana' %}selected{% endif %}>Ghana</option>
    <option value="Ivory Coast" {% if profile.fan_team == 'Ivory Coast' %}selected{% endif %}>Ivory Coast</option>
    <option value="Kenya"     {% if profile.fan_team == 'Kenya' %}selected{% endif %}>Kenya</option>
    <option value="Mali"      {% if profile.fan_team == 'Mali' %}selected{% endif %}>Mali</option>
    <option value="Morocco"   {% if profile.fan_team == 'Morocco' %}selected{% endif %}>Morocco</option>
    <option value="Nigeria"   {% if profile.fan_team == 'Nigeria' %}selected{% endif %}>Nigeria</option>
    <option value="Senegal"   {% if profile.fan_team == 'Senegal' %}selected{% endif %}>Senegal</option>
    <option value="South Africa" {% if profile.fan_team == 'South Africa' %}selected{% endif %}>South Africa</option>
    <option value="Tanzania"  {% if profile.fan_team == 'Tanzania' %}selected{% endif %}>Tanzania</option>
    <option value="Tunisia"   {% if profile.fan_team == 'Tunisia' %}selected{% endif %}>Tunisia</option>
    <option value="Uganda"    {% if profile.fan_team == 'Uganda' %}selected{% endif %}>Uganda</option>
    <option value="Other"     {% if profile.fan_team == 'Other' %}selected{% endif %}>Other / Neutral</option>
  </select>
  <div class="form-text">Used to personalise your tournament experience.</div>
</div>
```

### 5.5 Save fan_team in the profile edit route

**File:** `app/profile/routes.py` → `edit_profile()` POST handler

Find where the profile fields are saved from the form. Add:

```python
# fan_team is always mutable - not in IMMUTABLE_AFTER_VERIFICATION
fan_team = request.form.get("fan_team", "").strip() or None
profile.fan_team = fan_team
```

### 5.6 Show fan badge on public profile

**File:** `templates/profile/public.html`

Add inside the profile header section:

```html
{% if tournament_mode and profile.fan_team %}
<span class="badge" style="background:#E1F5EE;color:#085041;font-size:12px;padding:4px 10px;border-radius:20px;">
  AFCON fan - {{ profile.fan_team }}
</span>
{% endif %}
```

---

## PHASE 6 - VERIFICATION: Full system check

Run all of these. Paste output in your report.

### 6.1 Database state
```bash
flask shell
>>> from app.extensions import db
>>> from sqlalchemy import inspect, text
>>> tables = inspect(db.engine).get_table_names()
>>> print("fan_profiles exists:", 'fan_profiles' in tables)  # must be False
>>> cols = [c['name'] for c in inspect(db.engine).get_columns('user_profiles')]
>>> for f in ['fan_team','display_name','avatar_url','bio']:
...     print(f"{f} in user_profiles:", f in cols)  # all must be True
>>> fan_role = db.session.execute(text("SELECT COUNT(*) FROM roles WHERE name='fan'")).scalar()
>>> user_role = db.session.execute(text("SELECT COUNT(*) FROM roles WHERE name='user'")).scalar()
>>> print(f"fan role count: {fan_role}")   # must be 0
>>> print(f"user role count: {user_role}") # must be 1
```

### 6.2 No FanProfile imports remain
```bash
grep -rn "get_or_create_fan\|from app.fan.models import FanProfile\|FanProfile" \
  app/ --include="*.py" | grep -v "fan/models.py"
```
Expected: zero matches.

### 6.3 Routes still work
```bash
flask routes | grep -E "fan\.|onboarding\.|wallet\.|profile\."
```
Expected: all existing routes still listed, none missing.

### 6.4 App starts without errors
```bash
flask run --no-reload &
sleep 3
curl -s http://localhost:5000/ | grep -i "afcon\|200" | head -3
kill %1
```
Expected: app starts, homepage responds.

### 6.5 Run existing tests
```bash
pytest tests/test_onboarding.py tests/test_registration_flow.py -v --tb=short 2>&1 | tail -20
```
Expected: all passing tests still pass.

---

## REPORT TEMPLATE

```
=== ARCHITECTURE PASS 5 REPORT ===
Date: ___________
Branch: ___________

PHASE 1 - UserProfile columns added:
fan_team column: EXISTS / MISSING
display_name column: EXISTS / MISSING
avatar_url column: EXISTS / MISSING
bio column: EXISTS / MISSING
Migration applied without errors: YES / NO

PHASE 2 - FanProfile dropped:
Rows migrated before drop: ___ rows
fan_profiles table dropped: YES / NO
app/fan/models.py cleared: YES / NO

PHASE 3 - get_or_create_fan removed:
Files changed: ___________
Remaining references: ___ (must be 0)

PHASE 4 - fan role renamed to user:
seed_roles.py updated: YES / NO
flask seed-all ran: YES / NO
Existing user_roles rows updated: ___ rows
fan role count in DB: ___ (must be 0)
user role count in DB: ___ (must be 1)

PHASE 5 - Tournament skin:
tournament_mode in context processor: YES / NO
fan_team field in edit form: YES / NO
fan_team saved in edit route: YES / NO
Tournament block in dashboard template: YES / NO

PHASE 6 - Verification:
App starts without errors: YES / NO
All routes still present: YES / NO
FanProfile references remaining: ___ (must be 0)
Test results: Total ___ / Passed ___ / Failed ___
Failed tests: ___________

ANYTHING BROKEN THAT WORKED BEFORE: YES / NO
If yes: ___________

SIGN-OFF: COMPLETE / INCOMPLETE
```

---

## WHAT COMES AFTER THIS PASS

Once this pass is complete and verified, the architecture is settled.
The next work items in priority order are:

1. Fill the tournament content (match feed, fan events, fan trips)
   into the `{% if tournament_mode %}` blocks
2. Build the org admin panel (transfer org_owner, manage members)
3. Build the driver dashboard (post-verification experience)
4. Build the host dashboard (listing management, booking calendar)
5. Deployment configuration (environment variables, MODULE_FLAGS per env)

Do not start any of those until this pass report is signed off.
```
