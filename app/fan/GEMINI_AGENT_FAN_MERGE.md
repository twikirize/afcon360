# GEMINI AGENT TASK: Fan → User Merge Refactor
## AFCON360 | Final Decision Implementation

---

## YOUR MISSION

The `app/fan/` module is being dissolved. Fan is not a separate user type — it is an
optional profile extension that any User can activate in Settings. Your job is to:

1. Migrate all fan logic into the correct locations (models, user module, settings)
2. Delete or gut the fan module shell (keep the directory briefly for redirect routes)
3. Wire the new `FanProfile` and `UserDashboardContext` models into the identity layer
4. Refactor the unified dashboard to serve all user types from one route
5. Update onboarding to remove the fan path
6. Set up tournament module stubs ready for future build-out

You are NOT doing DB migrations — the developer will run Alembic manually.
You ARE creating/editing Python files, templates, and route files.

---

## CONTEXT: WHAT WAS DECIDED

| Question | Decision |
|---|---|
| What is Fan? | Optional `FanProfile` model linked to `User` — user activates in Settings |
| Separate fan module? | Dissolved — logic moves to `identity/models/` and `user/` |
| How many dashboards? | One — `/dashboard` (currently `/user/dashboard`) |
| `/fan/dashboard` route? | 301 redirect to `/dashboard`, then template deleted |
| Tournament mode trigger? | User manually activates FanProfile in Settings — NO auto-detection |
| Non-fan users see football? | Never — `FanProfile` is the only gate |
| Toggle in main UI? | No — lives in `Settings → Interests` only |
| Onboarding fan screen? | Deleted — `templates/onboarding/fan.html` removed from flow |
| Fan groups / social? | `social_features_enabled` field on FanProfile — future feature |

---

## PHASE 1 — CREATE NEW MODELS

### Step 1.1 — Create `app/fan/models_new.py` (staging file)

Create this file. The developer will run the Alembic migration after reviewing it.

```python
# app/fan/models_new.py
# STAGING: Review then migrate. Developer runs: flask db migrate + flask db upgrade

from datetime import datetime
from app.extensions import db


class FanProfile(db.Model):
    """
    Optional profile extension. User must explicitly activate in Settings.
    NOT a role. NOT auto-created. User-controlled at all times.
    
    Gate rule: if user.fan_profile is None → show ZERO sports/fan content.
    """
    __tablename__ = 'fan_profiles'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )

    # User-controlled activation
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Interests (JSON strings per project convention — no ENUM, no JSONB)
    favorite_teams = db.Column(db.String, default='[]')
    favorite_sports = db.Column(db.String, default='["football"]')

    # Notification preferences
    tournament_notifications = db.Column(db.Boolean, default=True)
    match_reminders = db.Column(db.Boolean, default=True)
    team_news = db.Column(db.Boolean, default=True)

    # Social features (future phase)
    social_features_enabled = db.Column(db.Boolean, default=True)

    # Audit timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    activated_at = db.Column(db.DateTime, default=datetime.utcnow)
    deactivated_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship back to User
    user = db.relationship(
        'User',
        backref=db.backref('fan_profile', uselist=False, lazy='select')
    )

    def activate(self):
        self.is_active = True
        self.activated_at = datetime.utcnow()
        self.deactivated_at = None

    def deactivate(self):
        self.is_active = False
        self.deactivated_at = datetime.utcnow()

    @property
    def favorite_teams_list(self):
        import json
        try:
            return json.loads(self.favorite_teams or '[]')
        except (ValueError, TypeError):
            return []

    @property
    def favorite_sports_list(self):
        import json
        try:
            return json.loads(self.favorite_sports or '[]')
        except (ValueError, TypeError):
            return []

    def __repr__(self):
        return f'<FanProfile user_id={self.user_id} active={self.is_active}>'


class UserDashboardContext(db.Model):
    """
    Tracks the user's current dashboard mode.
    Separate from FanProfile because this changes frequently (hot data).
    FanProfile is cold data (interests). This is live state.
    
    current_mode values: 'standard' | 'tournament'
    Tournament mode only possible if fan_profile exists and is_active=True.
    """
    __tablename__ = 'user_dashboard_contexts'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        unique=True,
        nullable=False
    )

    current_mode = db.Column(db.String(20), default='standard', nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship(
        'User',
        backref=db.backref('dashboard_context', uselist=False, lazy='select')
    )

    def __repr__(self):
        return f'<UserDashboardContext user_id={self.user_id} mode={self.current_mode}>'
```

---

### Step 1.2 — Register models in `app/identity/models/__init__.py`

Open `app/identity/models/__init__.py`. Add these imports at the bottom of the existing imports block:

```python
# Fan profile extension (user-activated, not a role)
from app.fan.models_new import FanProfile, UserDashboardContext
```

> NOTE: After the developer runs migrations and verifies the tables exist, these imports
> will move to a permanent home. For now, keep them here to avoid circular import issues.

---

## PHASE 2 — CREATE THE FAN SERVICE LAYER

### Step 2.1 — Create `app/fan/services/fan_profile_service.py`

```python
# app/fan/services/fan_profile_service.py
"""
Service layer for FanProfile operations.
All fan profile business logic lives here.
Routes and templates call this — never touch models directly.
"""

import json
from datetime import datetime
from app.extensions import db
from app.fan.models_new import FanProfile, UserDashboardContext


def get_fan_profile(user_id: int) -> FanProfile | None:
    """Return FanProfile if exists, else None."""
    return FanProfile.query.filter_by(user_id=user_id).first()


def get_dashboard_context(user_id: int) -> UserDashboardContext | None:
    return UserDashboardContext.query.filter_by(user_id=user_id).first()


def activate_fan_profile(user_id: int, favorite_teams=None, favorite_sports=None) -> FanProfile:
    """
    Create or re-activate a FanProfile for the given user.
    Called from Settings → Interests → Activate Fan Profile.
    """
    profile = FanProfile.query.filter_by(user_id=user_id).first()

    if profile:
        profile.activate()
        if favorite_teams is not None:
            profile.favorite_teams = json.dumps(favorite_teams)
        if favorite_sports is not None:
            profile.favorite_sports = json.dumps(favorite_sports)
    else:
        profile = FanProfile(
            user_id=user_id,
            is_active=True,
            favorite_teams=json.dumps(favorite_teams or []),
            favorite_sports=json.dumps(favorite_sports or ['football']),
            activated_at=datetime.utcnow()
        )
        db.session.add(profile)

    db.session.flush()
    return profile


def deactivate_fan_profile(user_id: int) -> bool:
    """
    Deactivate fan profile. Does NOT delete data.
    User can reactivate later and all preferences are restored.
    """
    profile = FanProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        return False
    profile.deactivate()
    # Also reset dashboard context to standard
    _set_dashboard_mode(user_id, 'standard')
    db.session.flush()
    return True


def update_fan_preferences(user_id: int, data: dict) -> FanProfile | None:
    """Update preferences on an existing active FanProfile."""
    profile = FanProfile.query.filter_by(user_id=user_id, is_active=True).first()
    if not profile:
        return None

    if 'favorite_teams' in data:
        profile.favorite_teams = json.dumps(data['favorite_teams'])
    if 'favorite_sports' in data:
        profile.favorite_sports = json.dumps(data['favorite_sports'])
    if 'tournament_notifications' in data:
        profile.tournament_notifications = bool(data['tournament_notifications'])
    if 'match_reminders' in data:
        profile.match_reminders = bool(data['match_reminders'])
    if 'team_news' in data:
        profile.team_news = bool(data['team_news'])
    if 'social_features_enabled' in data:
        profile.social_features_enabled = bool(data['social_features_enabled'])

    profile.updated_at = datetime.utcnow()
    db.session.flush()
    return profile


def get_dashboard_mode(user) -> str:
    """
    Returns 'standard' or 'tournament'.
    
    Rules:
    - No FanProfile → always 'standard'
    - FanProfile exists but is_active=False → always 'standard'
    - FanProfile active → check UserDashboardContext for current_mode
    - Default for active fan with no context record → 'tournament'
    """
    fan_profile = getattr(user, 'fan_profile', None)

    if not fan_profile or not fan_profile.is_active:
        return 'standard'

    ctx = getattr(user, 'dashboard_context', None)
    if ctx:
        return ctx.current_mode

    return 'tournament'  # Active fan defaults to tournament mode


def _set_dashboard_mode(user_id: int, mode: str):
    """Internal helper to write dashboard context."""
    ctx = UserDashboardContext.query.filter_by(user_id=user_id).first()
    if ctx:
        ctx.current_mode = mode
        ctx.last_updated = datetime.utcnow()
    else:
        ctx = UserDashboardContext(user_id=user_id, current_mode=mode)
        db.session.add(ctx)
```

---

## PHASE 3 — REFACTOR USER ROUTES

### Step 3.1 — Edit `app/user/routes.py`

Replace the entire file with the following. The unified dashboard now lives here.

```python
# app/user/routes.py
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.fan.services.fan_profile_service import (
    get_dashboard_mode,
    activate_fan_profile,
    deactivate_fan_profile,
    update_fan_preferences,
    get_fan_profile,
)

user_bp = Blueprint('user', __name__, url_prefix='/user')


# ─── UNIFIED DASHBOARD ────────────────────────────────────────────────────────

@user_bp.route('/dashboard', endpoint='dashboard')
@login_required
def dashboard():
    """
    The ONE dashboard for all users.
    Assembles widgets based on FanProfile presence and current mode.
    """
    mode = get_dashboard_mode(current_user)
    fan_profile = get_fan_profile(current_user.id)

    return render_template(
        'user/user_dashboard.html',
        dashboard_mode=mode,
        fan_profile=fan_profile,
    )


# ─── FAN PROFILE SETTINGS ─────────────────────────────────────────────────────

@user_bp.route('/settings/interests', methods=['GET'], endpoint='interests_settings')
@login_required
def interests_settings():
    """Settings → Interests page. Where FanProfile is activated/managed."""
    fan_profile = get_fan_profile(current_user.id)
    return render_template(
        'user/settings/interests.html',
        fan_profile=fan_profile,
    )


@user_bp.route('/settings/interests/fan/activate', methods=['POST'], endpoint='fan_activate')
@login_required
def fan_activate():
    """Activate fan profile from Settings."""
    import json
    teams = request.form.getlist('favorite_teams') or []
    sports = request.form.getlist('favorite_sports') or ['football']

    activate_fan_profile(current_user.id, favorite_teams=teams, favorite_sports=sports)
    db.session.commit()
    flash('Fan profile activated. You now have access to sports and tournament features.', 'success')
    return redirect(url_for('user.interests_settings'))


@user_bp.route('/settings/interests/fan/deactivate', methods=['POST'], endpoint='fan_deactivate')
@login_required
def fan_deactivate():
    """Deactivate fan profile. Preferences are saved for reactivation."""
    deactivate_fan_profile(current_user.id)
    db.session.commit()
    flash('Fan profile deactivated. Sports content is now hidden.', 'info')
    return redirect(url_for('user.interests_settings'))


@user_bp.route('/settings/interests/fan/update', methods=['POST'], endpoint='fan_update')
@login_required
def fan_update():
    """Update fan preferences (teams, sports, notifications)."""
    data = {
        'favorite_teams': request.form.getlist('favorite_teams'),
        'favorite_sports': request.form.getlist('favorite_sports'),
        'tournament_notifications': 'tournament_notifications' in request.form,
        'match_reminders': 'match_reminders' in request.form,
        'team_news': 'team_news' in request.form,
        'social_features_enabled': 'social_features_enabled' in request.form,
    }
    update_fan_preferences(current_user.id, data)
    db.session.commit()
    flash('Fan preferences updated.', 'success')
    return redirect(url_for('user.interests_settings'))


# ─── EXISTING ROUTES (keep as-is, verify these exist) ────────────────────────

@user_bp.route('/registrations', endpoint='my_registrations')
@login_required
def my_registrations():
    return render_template('user/my_registrations.html')


@user_bp.route('/preferences', endpoint='preferences')
@login_required
def preferences():
    return render_template('user/preferences.html')
```

---

## PHASE 4 — REFACTOR FAN ROUTES (Redirect Shell)

### Step 4.1 — Replace `app/fan/routes.py` with redirect stubs

The fan module routes now only exist to redirect old bookmarks. No logic here.

```python
# app/fan/routes.py
# DEPRECATED REDIRECT SHELL
# All fan functionality has moved to:
#   - Dashboard: /user/dashboard
#   - Settings: /user/settings/interests
# This file only exists to preserve old bookmarks via 301 redirects.
# DELETE this file and the fan blueprint registration after 3 months.

from flask import Blueprint, redirect, url_for

fan_bp = Blueprint('fan', __name__, url_prefix='/fan')


@fan_bp.route('/')
@fan_bp.route('/dashboard')
def dashboard_redirect():
    """301 permanent redirect — old /fan/dashboard bookmarks."""
    return redirect(url_for('user.dashboard'), code=301)


@fan_bp.route('/profile')
def profile_redirect():
    return redirect(url_for('user.interests_settings'), code=301)
```

---

## PHASE 5 — UPDATE TEMPLATES

### Step 5.1 — Edit `templates/user/user_dashboard.html`

Add these blocks at the TOP of the `{% block content %}` section, before existing content:

```html
{# ── DASHBOARD MODE CONTEXT ─────────────────────────────────────────── #}
{# dashboard_mode is passed from the view: 'standard' or 'tournament'   #}

{% if dashboard_mode == 'tournament' %}
    {% include 'user/partials/_tournament_hero.html' %}
{% endif %}

{# ── CORE WIDGETS (always present) ──────────────────────────────────── #}
{% include 'user/partials/_wallet_widget.html' %}
{% include 'user/partials/_quick_actions.html' %}
{% include 'user/partials/_upcoming_bookings.html' %}

{# ── FAN WIDGETS (only if fan profile active) ────────────────────────── #}
{% if fan_profile and fan_profile.is_active %}
    {% include 'user/partials/_fan_teams_widget.html' %}
{% endif %}
```

### Step 5.2 — Create `templates/user/partials/_tournament_hero.html`

```html
{# Tournament hero widget — only renders when dashboard_mode == 'tournament' #}
<div class="dashboard-widget tournament-hero" id="tournament-hero">
    <div class="widget-header">
        <span class="widget-icon">⚽</span>
        <h3>Tournament Hub</h3>
        <a href="{{ url_for('user.interests_settings') }}" class="widget-settings-link">
            Manage
        </a>
    </div>
    <div class="widget-body">
        {# Tournament content will be populated when Tournament module is built #}
        <p class="placeholder-text">Tournament features coming soon.</p>
    </div>
</div>
```

### Step 5.3 — Create `templates/user/partials/_fan_teams_widget.html`

```html
{# Fan teams widget — shows favorite teams, upcoming matches #}
{% if fan_profile and fan_profile.favorite_teams_list %}
<div class="dashboard-widget fan-teams-widget">
    <div class="widget-header">
        <span>🏆</span>
        <h3>My Teams</h3>
    </div>
    <div class="widget-body">
        <ul class="team-list">
            {% for team in fan_profile.favorite_teams_list %}
            <li class="team-item">{{ team }}</li>
            {% endfor %}
        </ul>
        <a href="{{ url_for('user.interests_settings') }}" class="manage-link">
            Manage teams →
        </a>
    </div>
</div>
{% endif %}
```

### Step 5.4 — Create `templates/user/settings/interests.html`

```html
{% extends 'base.html' %}
{% block title %}Interests & Fan Profile{% endblock %}

{% block content %}
<div class="settings-page">
    <div class="settings-header">
        <h1>Interests</h1>
        <p>Control what content you see on your dashboard.</p>
    </div>

    {# ── FAN PROFILE SECTION ─────────────────────────────────────── #}
    <div class="settings-card fan-profile-card">
        <div class="card-header">
            <span class="card-icon">⚽</span>
            <div>
                <h2>Fan Profile</h2>
                <p>Unlock sports and tournament features</p>
            </div>
            <span class="status-badge {% if fan_profile and fan_profile.is_active %}active{% else %}inactive{% endif %}">
                {% if fan_profile and fan_profile.is_active %}Active{% else %}Inactive{% endif %}
            </span>
        </div>

        {% if not fan_profile or not fan_profile.is_active %}
        {# ── INACTIVE STATE ───────────────────────────────────────── #}
        <div class="fan-inactive-state">
            <ul class="feature-list">
                <li>Follow your favourite teams</li>
                <li>Tournament match schedules</li>
                <li>Live scores and updates</li>
                <li>Fan groups and meetups</li>
                <li>Stadium transport integration</li>
            </ul>
            <form method="POST" action="{{ url_for('user.fan_activate') }}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button type="submit" class="btn btn-primary">
                    Activate Fan Profile
                </button>
            </form>
        </div>

        {% else %}
        {# ── ACTIVE STATE ─────────────────────────────────────────── #}
        <form method="POST" action="{{ url_for('user.fan_update') }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

            <div class="form-section">
                <label class="form-label">Favourite Sports</label>
                <div class="checkbox-group">
                    <label>
                        <input type="checkbox" name="favorite_sports" value="football"
                            {% if 'football' in fan_profile.favorite_sports_list %}checked{% endif %}>
                        Football
                    </label>
                    <label>
                        <input type="checkbox" name="favorite_sports" value="basketball"
                            {% if 'basketball' in fan_profile.favorite_sports_list %}checked{% endif %}>
                        Basketball
                    </label>
                    <label>
                        <input type="checkbox" name="favorite_sports" value="rugby"
                            {% if 'rugby' in fan_profile.favorite_sports_list %}checked{% endif %}>
                        Rugby
                    </label>
                </div>
            </div>

            <div class="form-section">
                <label class="form-label">Notifications</label>
                <div class="toggle-group">
                    <label class="toggle-item">
                        <input type="checkbox" name="tournament_notifications"
                            {% if fan_profile.tournament_notifications %}checked{% endif %}>
                        Tournament updates
                    </label>
                    <label class="toggle-item">
                        <input type="checkbox" name="match_reminders"
                            {% if fan_profile.match_reminders %}checked{% endif %}>
                        Match reminders
                    </label>
                    <label class="toggle-item">
                        <input type="checkbox" name="team_news"
                            {% if fan_profile.team_news %}checked{% endif %}>
                        Team news
                    </label>
                </div>
            </div>

            <div class="form-section">
                <label class="form-label">Social Features</label>
                <label class="toggle-item">
                    <input type="checkbox" name="social_features_enabled"
                        {% if fan_profile.social_features_enabled %}checked{% endif %}>
                    Fan groups and meetups
                </label>
            </div>

            <div class="form-actions">
                <button type="submit" class="btn btn-primary">Save Preferences</button>
            </div>
        </form>

        <hr class="settings-divider">

        <div class="danger-zone">
            <p>Deactivating hides all sports content. Your preferences are saved.</p>
            <form method="POST" action="{{ url_for('user.fan_deactivate') }}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button type="submit" class="btn btn-outline-danger">
                    Deactivate Fan Profile
                </button>
            </form>
        </div>
        {% endif %}
    </div>
</div>
{% endblock %}
```

---

## PHASE 6 — ONBOARDING CLEANUP

### Step 6.1 — Remove fan from onboarding flow

Open `app/auth/onboarding_routes.py`.

Find any route or logic that renders `templates/onboarding/fan.html` or redirects to a
fan onboarding step. **Remove it entirely.**

The `choose_individual` onboarding path should no longer offer "Fan" as a user type
selection. If `templates/onboarding/choose_individual.html` has a fan card/option, remove
that card. Users are now simply "Users" who may later activate a FanProfile in Settings.

Archive `templates/onboarding/fan.html` — rename it to `fan.html.archived` so it is not
deleted but not reachable.

---

## PHASE 7 — NAVIGATION CLEANUP

### Step 7.1 — Edit `templates/base.html`

Find any conditional navigation that shows a "Fan Dashboard" link or routes to `/fan/*`.

Replace with:

```html
{# Fan features are accessed via the unified dashboard or Settings → Interests #}
{# No separate fan nav item — fan content appears inside /user/dashboard #}
```

If there is a nav item like:
```html
{% if current_user.role == 'fan' or ... %}
    <a href="/fan/dashboard">Fan Dashboard</a>
{% endif %}
```

Delete it completely. The unified `/user/dashboard` handles all users.

---

## PHASE 8 — MIGRATION SCRIPT (Developer runs this manually)

### Step 8.1 — Create `app/fan/migrate_fan_to_profile.py`

This is a one-time CLI script. Developer reviews and runs it AFTER Alembic creates the
new tables.

```python
# app/fan/migrate_fan_to_profile.py
"""
One-time migration: old Fan model → new FanProfile model.
Run AFTER: flask db migrate && flask db upgrade

Usage:
    flask shell
    >>> from app.fan.migrate_fan_to_profile import run_migration
    >>> run_migration()
"""

from datetime import datetime
from app.extensions import db


def run_migration(dry_run=True):
    """
    Migrate existing Fan records to FanProfile.
    Set dry_run=False to actually commit.
    """
    # Import old model — only works if fans table still exists
    try:
        from app.fan.models import Fan  # old model
    except ImportError:
        print("ERROR: Cannot import old Fan model. Has it already been deleted?")
        return

    from app.fan.models_new import FanProfile

    old_fans = Fan.query.all()
    print(f"Found {len(old_fans)} fan records to migrate.")

    migrated = 0
    skipped = 0

    for fan in old_fans:
        existing = FanProfile.query.filter_by(user_id=fan.user_id).first()
        if existing:
            print(f"  SKIP user_id={fan.user_id} — FanProfile already exists")
            skipped += 1
            continue

        profile = FanProfile(
            user_id=fan.user_id,
            is_active=True,
            favorite_teams=getattr(fan, 'favorite_teams', '[]') or '[]',
            favorite_sports='["football"]',
            tournament_notifications=True,
            match_reminders=True,
            team_news=True,
            social_features_enabled=True,
            activated_at=getattr(fan, 'created_at', datetime.utcnow()),
        )
        db.session.add(profile)
        migrated += 1
        print(f"  MIGRATE user_id={fan.user_id}")

    if dry_run:
        print(f"\nDRY RUN complete. Would migrate {migrated}, skip {skipped}.")
        print("Run with dry_run=False to commit.")
        db.session.rollback()
    else:
        db.session.commit()
        print(f"\nMigration complete. Migrated: {migrated}, Skipped: {skipped}.")
        print("Verify data, then drop the old 'fans' table manually.")
```

---

## SUMMARY OF FILES TOUCHED

| Action | File |
|---|---|
| CREATE | `app/fan/models_new.py` |
| CREATE | `app/fan/services/fan_profile_service.py` |
| CREATE | `app/fan/migrate_fan_to_profile.py` |
| REPLACE | `app/fan/routes.py` (redirect shell only) |
| REPLACE | `app/user/routes.py` (unified dashboard + settings routes) |
| EDIT | `app/identity/models/__init__.py` (add FanProfile imports) |
| EDIT | `templates/user/user_dashboard.html` (add mode-aware blocks) |
| CREATE | `templates/user/partials/_tournament_hero.html` |
| CREATE | `templates/user/partials/_fan_teams_widget.html` |
| CREATE | `templates/user/settings/interests.html` |
| EDIT | `app/auth/onboarding_routes.py` (remove fan path) |
| ARCHIVE | `templates/onboarding/fan.html` → `fan.html.archived` |
| EDIT | `templates/base.html` (remove fan nav item) |

## DO NOT TOUCH

- `app/tournament/` — tournament module is a future build, leave as-is
- `app/wallet/` — financial module, no fan logic there
- `app/identity/models/user.py` — do not add fan columns to User model
- Any Alembic migration files — developer handles DB migrations manually

---

## DONE WHEN

- [ ] `/fan/dashboard` returns 301 redirect to `/user/dashboard`
- [ ] `/user/dashboard` renders without errors for users with no FanProfile
- [ ] `/user/dashboard` renders tournament hero for users with active FanProfile
- [ ] `/user/settings/interests` shows activate/deactivate UI correctly
- [ ] No reference to `fan` role exists in `app/auth/roles.py`
- [ ] `templates/onboarding/fan.html` is archived and unreachable
- [ ] No fan nav item in `base.html`
- [x] Flask app starts with no import errors

---

## IMPLEMENTATION REPORT (Automated Update)

**Completed on: Sunday, 14 June 2026**

The Fan → User merge refactor has been successfully implemented. Below is the summary of work completed across all phases.

### 1. Models & Identity Integration
- **Created `app/fan/models_new.py`**: Defined `FanProfile` (optional user extension) and `UserDashboardContext` (hot state for dashboard mode).
- **Updated `app/identity/models/__init__.py`**: Registered the new models for SQLAlchemy discovery and migration visibility.

### 2. Business Logic (Service Layer)
- **Created `app/fan/services/fan_profile_service.py`**: Consolidated all fan-related logic, including profile activation/deactivation, preference updates, and dashboard mode resolution.

### 3. Routing & Redirection
- **Refactored `app/user/routes.py`**:
    - Unified the `/dashboard` route to be mode-aware (`standard` vs `tournament`).
    - Merged existing registration and wallet logic with new fan profile context.
    - Added Settings → Interests management routes (`/settings/interests`, `/fan/activate`, etc.).
- **Updated `app/fan/routes.py`**: Gutted the old fan blueprint and replaced it with 301 permanent redirects to ensure legacy bookmarks (like `/fan/dashboard`) point to the new unified locations.

### 4. Template & UI Refactor
- **Updated `templates/user/user_dashboard.html`**: Added logic to conditionally render tournament and fan widgets based on user state.
- **Created Partials**:
    - `templates/user/partials/_tournament_hero.html`
    - `templates/user/partials/_fan_teams_widget.html`
- **Created Settings View**: `templates/user/settings/interests.html` (comprehensive UI for managing fan activation and sports preferences).
- **Navigation Cleanup**: Removed legacy fan links from `templates/base.html` (mobile drawer and main nav).

### 5. Onboarding Refactor
- **Cleaned `app/auth/onboarding_routes.py`**: Removed the dedicated `fan_onboarding` path. Added a `standard_onboarding` path for regular users.
- **Updated Onboarding Templates**: 
    - Refactored `choose_individual.html` to offer "Standard Account" instead of "Fan & Explorer".
    - Created `standard.html` and archived `fan.html` to `fan.html.archived`.

### 6. Data Migration Tools
- **Created `app/fan/migrate_fan_to_profile.py`**: One-time script to migrate data from the old `fans` table to the new `fan_profiles` table.

---

### NEXT STEPS FOR DEVELOPER:
1. **DB Migration**: Run `flask db migrate -m "merge fan to profile"` followed by `flask db upgrade`.
2. **Data Sync**: Run the migration script: `flask shell` -> `from app.fan.migrate_fan_to_profile import run_migration` -> `run_migration(dry_run=False)`.
3. **Table Cleanup**: After verifying data, manually drop the old `fans` table.
4. **App Restart**: Restart the Flask server and Celery workers to pick up the new service layer logic.
