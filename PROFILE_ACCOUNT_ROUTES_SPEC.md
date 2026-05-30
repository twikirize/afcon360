# Profile & Account Routes — Implementation Spec
# File: app/profile/routes.py
# Blueprint: profile_bp  (already registered as 'profile', url_prefix='/profile')

## Context
This spec is for the AI plugin. Do not change model files.
All models exist. All imports listed below are valid.

---

## Imports required

```python
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.identity.models.user import User, Session as UserSession
from app.profile.models import UserProfile, get_profile_by_user
from app.auth.kyc_compliance import calculate_kyc_tier, get_user_limits
from app.auth.roles import ROLE_PERMISSIONS
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
profile_bp = Blueprint('profile', __name__, url_prefix='/profile')
```

---

## Route 1 — Public profile
**Endpoint:** `GET /profile/<public_id>`
**Function name:** `public_profile(public_id)`
**Login required:** No (public page)
**Template:** `profile/public.html`

### Logic
```python
user = User.get_by_public_id(public_id)
if not user or user.is_deleted:
    abort(404)

profile = get_profile_by_user(user.public_id)
is_own_profile = current_user.is_authenticated and current_user.public_id == user.public_id

# Public-safe info only — NO PII (no DOB, no gender, no nationality, no email, no phone)
public_info = {
    'display_name': profile.display_name if profile else None,
    'full_name': profile.full_name if profile else user.username,
    'avatar_url': profile.avatar_url if profile else None,
    'bio': profile.bio if profile else None,
    'fan_team': profile.fan_team if profile else None,
    'city': profile.city if profile else None,
    'country': profile.country if profile else None,
}

user_roles = user.role_names  # uses existing property
stats = {'stays_count': 0, 'trips_count': 0, 'reviews_count': 0}  # placeholder

tournament_mode = True  # can wire to MODULE_FLAGS later
```

### Template variables passed
| Variable | Type | Source |
|---|---|---|
| `user` | User | DB lookup by public_id |
| `profile` | UserProfile or None | get_profile_by_user() |
| `public_info` | dict | filtered — NO PII |
| `is_own_profile` | bool | current_user check |
| `user_roles` | list[str] | user.role_names |
| `stats` | dict | placeholder zeros |
| `tournament_mode` | bool | True |

---

## Route 2 — Account overview (private)
**Endpoint:** `GET /profile/account`
**Function name:** `account_overview()`
**Login required:** Yes (`@login_required`)
**Template:** `profile/account.html`

### Logic
```python
# Get internal user (current_user may be proxy)
user = User.query.filter_by(public_id=str(current_user.public_id)).first()
if not user:
    return redirect(url_for('auth.logout'))

profile = get_profile_by_user(current_user.public_id)

# KYC
kyc_info = {}
try:
    kyc_info = calculate_kyc_tier(current_user.id)
except Exception:
    pass

limits = {}
try:
    limits = get_user_limits(current_user.id)
except Exception:
    pass

# Verification status for template
verification_status = profile.verification_status if profile else 'pending'
tier_name = kyc_info.get('tier_name', 'Basic')
progress_percentage = kyc_info.get('progress_percentage', 0)

# Active sessions — exclude current, show last 5
active_sessions = []
try:
    now = datetime.now(timezone.utc)
    sessions = UserSession.query.filter_by(
        user_id=user.id
    ).filter(
        UserSession.expires_at > now,
        UserSession.revoked_at == None
    ).order_by(UserSession.created_at.desc()).limit(5).all()
    active_sessions = sessions
except Exception:
    pass

# Roles — full list from RBAC
user_roles = user.role_names  # e.g. ['user', 'event_manager']

# Org memberships
org_memberships = []
try:
    for membership in user.organisations:
        org = membership.organisation
        if org and not org.is_deleted:
            org_roles = [our.role.name for our in membership.roles if our.role]
            org_memberships.append({
                'org_name': org.legal_name,
                'org_id': org.id,
                'roles': org_roles,
            })
except Exception:
    pass

# Password status
password_expires_at = user.password_expires_at
password_expired = False
if password_expires_at:
    password_expired = datetime.now(timezone.utc) > password_expires_at

# MFA status
mfa_active = user.mfa_enabled
active_mfa_types = [m.mfa_type for m in user.mfa_secrets if m.is_active] if user.mfa_secrets else []

# Transaction PIN status
has_pin = bool(user.transaction_pin_hash)
pin_locked = bool(
    user.transaction_pin_locked_until and
    datetime.now(timezone.utc) < user.transaction_pin_locked_until
)

role_stats = {}  # placeholder — wire to real counts later
```

### Template variables passed
| Variable | Type | Source |
|---|---|---|
| `user` | User | DB lookup |
| `profile` | UserProfile or None | get_profile_by_user() |
| `kyc_info` | dict | calculate_kyc_tier() |
| `limits` | dict | get_user_limits() |
| `verification_status` | str | profile.verification_status |
| `tier_name` | str | kyc_info |
| `progress_percentage` | int | kyc_info |
| `active_sessions` | list[Session] | Session query |
| `user_roles` | list[str] | user.role_names |
| `org_memberships` | list[dict] | user.organisations |
| `password_expires_at` | datetime or None | user.password_expires_at |
| `password_expired` | bool | computed |
| `mfa_active` | bool | user.mfa_enabled |
| `active_mfa_types` | list[str] | user.mfa_secrets |
| `has_pin` | bool | bool(user.transaction_pin_hash) |
| `pin_locked` | bool | computed |
| `role_stats` | dict | placeholder |

---

## Route 3 — Edit profile (GET + POST)
**Endpoint:** `GET/POST /profile/edit`
**Function name:** `edit_profile()`
**Login required:** Yes (`@login_required`)
**Template:** `profile/edit.html`

### GET logic
```python
profile = get_profile_by_user(current_user.public_id)
completion = profile.get_completion_percentage() if profile else 0
completion_breakdown = profile.get_completion_breakdown() if profile else {}
is_verified = profile and profile.verification_status == 'verified'
```

### POST logic
```python
profile = get_profile_by_user(current_user.public_id)
if not profile:
    flash('Profile not found.', 'danger')
    return redirect(url_for('profile.edit_profile'))

is_verified = profile.verification_status == 'verified'

# Fields always editable
profile.display_name = request.form.get('display_name') or profile.display_name
profile.bio = request.form.get('bio') or profile.bio
profile.fan_team = request.form.get('fan_team') or profile.fan_team
profile.avatar_url = request.form.get('avatar_url') or profile.avatar_url
profile.nationality = request.form.get('nationality') or profile.nationality
profile.address = request.form.get('address') or profile.address
profile.city = request.form.get('city') or profile.city
profile.country = request.form.get('country') or profile.country

# Fields only editable before verification (immutability enforced at model level too)
if not is_verified:
    full_name = request.form.get('full_name')
    if full_name:
        profile.full_name = full_name

try:
    db.session.commit()
    flash('Profile updated successfully.', 'success')
    return redirect(url_for('profile.edit_profile'))
except ValueError as e:
    db.session.rollback()
    flash(str(e), 'danger')
except Exception as e:
    db.session.rollback()
    logger.error(f"Profile update error: {e}")
    flash('An error occurred. Please try again.', 'danger')
```

### Template variables passed (GET)
| Variable | Type | Source |
|---|---|---|
| `profile` | UserProfile or None | get_profile_by_user() |
| `completion` | int | profile.get_completion_percentage() |
| `completion_breakdown` | dict | profile.get_completion_breakdown() |
| `is_verified` | bool | profile.verification_status == 'verified' |

---

## Route 4 — Revoke a single session (POST, AJAX)
**Endpoint:** `POST /profile/sessions/<int:session_db_id>/revoke`
**Function name:** `revoke_session(session_db_id)`
**Login required:** Yes
**Returns:** JSON

```python
user = User.query.filter_by(public_id=str(current_user.public_id)).first()
session = UserSession.query.filter_by(id=session_db_id, user_id=user.id).first()
if not session:
    return jsonify({'success': False, 'error': 'Session not found'}), 404

session.revoked_at = datetime.now(timezone.utc)
session.revoked_reason = 'user_revoked'
db.session.commit()
return jsonify({'success': True})
```

---

## Navigation links to add across all three templates

Every template in `profile/` should have these navigation links.
Use Jinja2 `url_for()` — never hardcode paths.

```jinja2
{# Navigation bar for profile pages — paste into each template #}
<nav class="profile-subnav">
  <a href="{{ url_for('profile.public_profile', public_id=current_user.public_id) }}"
     class="subnav-link {% if request.endpoint == 'profile.public_profile' %}active{% endif %}">
    <i class="fas fa-id-card"></i> My Profile
  </a>
  <a href="{{ url_for('profile.account_overview') }}"
     class="subnav-link {% if request.endpoint == 'profile.account_overview' %}active{% endif %}">
    <i class="fas fa-user-cog"></i> Account
  </a>
  <a href="{{ url_for('profile.edit_profile') }}"
     class="subnav-link {% if request.endpoint == 'profile.edit_profile' %}active{% endif %}">
    <i class="fas fa-edit"></i> Edit Profile
  </a>
  <a href="{{ url_for('user.user_dashboard') }}"
     class="subnav-link">
    <i class="fas fa-tachometer-alt"></i> Dashboard
  </a>
</nav>
```

---

## Blueprint registration

Add to `app/__init__.py` (or wherever blueprints are registered):

```python
from app.profile.routes import profile_bp
app.register_blueprint(profile_bp)
```

If `profile_bp` is already registered, skip — only add the new routes to the existing file.

---

## Notes for AI plugin

1. **Never** pass `user.id` (BIGINT) to templates as a public identifier — always use `user.public_id`
2. The `Session` model is imported as `UserSession` to avoid name collision with Flask's session
3. `get_profile_by_user()` accepts `user.public_id` (UUID string) — never pass `user.id` (int)
4. All 4 KYC states must be handled in templates: `pending`, `verified`, `rejected`, `suspended`
5. The `enforce_immutable_after_verification` SQLAlchemy event already protects the DB — the template just needs to reflect it visually (lock icon on full_name, DOB, ID fields when `is_verified == True`)
6. `active_sessions` list items have: `.ip`, `.user_agent`, `.created_at`, `.expires_at`, `.device_id`
