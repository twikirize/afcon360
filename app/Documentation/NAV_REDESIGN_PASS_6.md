# AFCON 360 - Navigation Redesign & Account Creation Flow
## Codeium Agent Instructions - Pass 6

**Environment:** Windows 11, PyCharm, PowerShell terminal
**Python:** `.venv\Scripts\python.exe`
**Flask app:** `app.py` at `C:\Users\ADMIN\Desktop\afcon360_app\`
**Version:** 6.0
**Date:** 2026-05-07

---

## GOLDEN RULE FOR THIS PASS

> Read every file before editing it.
> Make SURGICAL changes only - copy the exact lines, edit, paste back.
> Do NOT reformat, restructure, or rewrite any file wholistically.
> Test `flask run` after every phase. If it crashes, revert that phase only.

---

## THE FOUR USER STATES - WHAT NAV SHOWS IN EACH

This is the authoritative reference. Every code change below serves these states.

```
STATE 0 - Anonymous (not signed in)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AFCON 360 | Events | Tourism | Transport | Accommodation | Wallet | Sign In | Sign Up

- Wallet → wallet_api.wallet_home  (existing wallet_home.html for non-signed-in)
- Sign In → auth.login
- Sign Up → auth.register  (primary CTA - styled green)

STATE 1 - Signed in, profile_completed = False (just through the gate)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AFCON 360 | Events | Tourism | Transport | Accommodation | Wallet* | Create Account | [Name ▾]

- Wallet* → wallet_api.wallet_home  (same public page - they have no wallet yet)
  Shown with lock icon + tooltip "Create an account to activate your wallet"
- Create Account → onboarding.choose  (PRIMARY CTA - green)
- [Name ▾] → dropdown: My Profile | Sign Out

STATE 2 - Signed in, profile_completed = True, personal context
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AFCON 360 | Events | Tourism | Transport | Accommodation | Wallet | Dashboard | [Name ▾]

- Wallet → wallet.wallet_dashboard  (their personal wallet)
- Dashboard → role-based dashboard (fan.dashboard, transport.driver_dashboard, etc.)
- [Name ▾] → dropdown: My Profile | My Account | Settings | Sign Out

STATE 3 - Signed in, profile_completed = True, org context
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AFCON 360 | Events | Tourism | Transport | Accommodation | Org Wallet | Org Dashboard | [OrgName ▾]

- Org Wallet → wallet.wallet_dashboard (org wallet)
- Org Dashboard → org.dashboard
- [OrgName ▾] styled in amber → dropdown: Switch to Personal | Org Members | Org Settings | Sign Out
```

---

## PHASE 1 - `app/__init__.py` - Add nav state to context processor

**What to change:** Add 4 variables to `inject_sitewide()` so templates
know which state to render without duplicating logic in every template.

Find the `inject_sitewide()` context processor. It currently returns a dict.
Add these keys to that dict - do not remove any existing keys:

```python
@app.context_processor
def inject_sitewide() -> Dict:
    # ── resolve nav state ───────────────────────────────────────
    from flask import session as _session
    from flask_login import current_user as _cu

    _profile_completed = False
    _in_org_context = False
    _org_name = None

    if _cu.is_authenticated:
        try:
            from app.profile.models import get_profile_by_user
            _p = get_profile_by_user(_cu.public_id)
            _profile_completed = bool(_p and _p.profile_completed)
        except Exception:
            pass
        _in_org_context = _session.get("current_context") == "organization"
        if _in_org_context:
            _org_name = _session.get("current_org_name", "Organisation")
    # ── end nav state ───────────────────────────────────────────

    return {
        # ... all existing keys stay exactly as they are ...
        # ADD THESE FOUR at the end of the return dict:
        "nav_profile_completed": _profile_completed,
        "nav_in_org_context":    _in_org_context,
        "nav_org_name":          _org_name,
        "tournament_mode":       app.config.get("MODULE_FLAGS", {}).get("tournament", False),
    }
```

**Verify - no crash:**
```powershell
cd C:\Users\ADMIN\Desktop\afcon360_app
.venv\Scripts\python.exe -m flask --app app.py routes | findstr "onboarding"
```
Expected: onboarding routes listed without error.

---

## PHASE 2 - `templates/base.html` - Desktop nav rewrite

Open `base.html`. Find the desktop nav block - it starts at:
```html
<nav class="main-nav desktop-nav" aria-label="Main menu">
```
and ends at the closing `</nav>` before `</header>`.

**Replace ONLY the authenticated user section** - the block between
`{% if current_user.is_authenticated %}` and its `{% else %}` inside
the desktop nav. Leave the service links (Events, Tourism, Transport,
Accommodation) completely untouched.

**Find this block (lines ~260-316) and replace it entirely:**

```html
        {% if current_user.is_authenticated %}

          {# ── STATE 1: signed in, no account yet ─────────────────── #}
          {% if not nav_profile_completed %}

            <li class="menu-item">
              <a href="{{ url_for('wallet_api.wallet_home') }}"
                 class="nav-wallet-locked"
                 data-bs-toggle="tooltip"
                 data-bs-placement="bottom"
                 title="Create an account to activate your wallet">
                <i class="bi bi-wallet2 me-1"></i>Wallet
                <i class="bi bi-lock-fill ms-1" style="font-size:10px;opacity:0.6;"></i>
              </a>
            </li>

            <li class="menu-item">
              <a href="{{ url_for('onboarding.choose') }}" class="btn-create-account">
                <i class="bi bi-person-plus me-1"></i>Create Account
              </a>
            </li>

            <li class="menu-item has-dropdown nav-user-menu">
              <button class="nav-user-trigger">
                <span class="nav-user-avatar">{{ current_user.username[0]|upper if current_user.username else '?' }}</span>
                <i class="bi bi-chevron-down" style="font-size:10px;"></i>
              </button>
              <ul class="drop-menu drop-menu--right" role="menu">
                <li><a class="drop-item" href="{{ url_for('profile.my_public_profile') }}">
                  <i class="bi bi-person-circle me-2"></i>My Profile</a></li>
                <li><hr class="drop-divider"></li>
                <li>
                  <form method="POST" action="{{ url_for('auth.logout') }}">
                    <input type="hidden" name="csrf_token" value="{{ raw_csrf_token }}">
                    <button type="submit" class="drop-item drop-item--btn">
                      <i class="bi bi-box-arrow-right me-2"></i>Sign Out
                    </button>
                  </form>
                </li>
              </ul>
            </li>

          {# ── STATE 3: org context ─────────────────────────────────── #}
          {% elif nav_in_org_context %}

            <li class="menu-item">
              <a href="{{ url_for('wallet.wallet_dashboard') }}" class="nav-wallet-link">
                <i class="bi bi-wallet2 me-1"></i>Org Wallet
              </a>
            </li>

            <li class="menu-item">
              <a href="{{ url_for('org.dashboard', org_id=session.get('current_org_id')) }}"
                 class="nav-dashboard-link">
                <i class="bi bi-speedometer2 me-1"></i>Org Dashboard
              </a>
            </li>

            <li class="menu-item has-dropdown nav-user-menu nav-user-menu--org">
              <button class="nav-user-trigger nav-user-trigger--org">
                <span class="nav-org-avatar">{{ nav_org_name[0]|upper if nav_org_name else 'O' }}</span>
                <span class="nav-org-name">{{ nav_org_name|truncate(14, true, '…') }}</span>
                <i class="bi bi-chevron-down" style="font-size:10px;"></i>
              </button>
              <ul class="drop-menu drop-menu--right" role="menu">
                <li><span class="drop-header">{{ nav_org_name }}</span></li>
                <li><hr class="drop-divider"></li>
                <li><a class="drop-item" href="{{ url_for('auth.switch_context', context='individual') }}">
                  <i class="bi bi-person me-2"></i>Switch to Personal</a></li>
                <li><a class="drop-item" href="{{ url_for('org.members', org_id=session.get('current_org_id')) }}">
                  <i class="bi bi-people me-2"></i>Org Members</a></li>
                <li><a class="drop-item" href="{{ url_for('org.settings', org_id=session.get('current_org_id')) }}">
                  <i class="bi bi-gear me-2"></i>Org Settings</a></li>
                <li><hr class="drop-divider"></li>
                <li>
                  <form method="POST" action="{{ url_for('auth.logout') }}">
                    <input type="hidden" name="csrf_token" value="{{ raw_csrf_token }}">
                    <button type="submit" class="drop-item drop-item--btn">
                      <i class="bi bi-box-arrow-right me-2"></i>Sign Out
                    </button>
                  </form>
                </li>
              </ul>
            </li>

          {# ── STATE 2: personal account, profile complete ───────────── #}
          {% else %}

            <li class="menu-item">
              <a href="{{ url_for('wallet.wallet_dashboard') }}" class="nav-wallet-link">
                <i class="bi bi-wallet2 me-1"></i>Wallet
              </a>
            </li>

            <li class="menu-item">
              <a href="{% if current_user.is_app_owner() %}{{ url_for('admin.owner.dashboard') }}
                       {% elif current_user.has_global_role('super_admin') %}{{ url_for('admin.super_dashboard') }}
                       {% elif current_user.has_global_role('admin') %}{{ url_for('admin.super_dashboard') }}
                       {% elif current_user.has_global_role('auditor') %}{{ url_for('admin.auditor.dashboard') }}
                       {% elif current_user.has_global_role('compliance_officer') %}{{ url_for('admin.compliance.dashboard') }}
                       {% elif current_user.has_global_role('moderator') %}{{ url_for('admin.moderator.dashboard') }}
                       {% elif current_user.has_global_role('support') %}{{ url_for('admin.support.dashboard') }}
                       {% elif current_user.has_global_role('event_manager') %}{{ url_for('events.admin_dashboard') }}
                       {% elif current_user.has_global_role('transport_admin') %}{{ url_for('transport_admin.dashboard') }}
                       {% elif current_user.has_global_role('wallet_admin') %}{{ url_for('wallet.wallet_dashboard') }}
                       {% elif current_user.has_global_role('accommodation_admin') %}{{ url_for('accommodation.admin.dashboard') }}
                       {% elif current_user.has_global_role('tourism_admin') %}{{ url_for('tourism.home') }}
                       {% else %}{{ url_for('fan.dashboard') }}{% endif %}"
                 class="nav-dashboard-link">
                <i class="bi bi-speedometer2 me-1"></i>Dashboard
              </a>
            </li>

            {# KYC badge - keep as-is from original #}
            <li class="nav-item auth">
              <div class="kyc-badge-nav" style="display:inline-block;margin-left:10px;"
                   data-bs-toggle="tooltip"
                   title="KYC Tier {{ kyc_tier }}: {{ kyc_tier_name }}">
                <span class="badge bg-{{ tier_colors.get(kyc_tier, 'secondary') }}"
                      style="font-size:0.8em;padding:3px 8px;">
                  T{{ kyc_tier }}
                </span>
              </div>
            </li>

            <li class="menu-item has-dropdown nav-user-menu">
              <button class="nav-user-trigger">
                <span class="nav-user-avatar">{{ current_user.username[0]|upper if current_user.username else '?' }}</span>
                <span class="nav-user-name">{{ current_user.username|truncate(12, true, '…') }}</span>
                <i class="bi bi-chevron-down" style="font-size:10px;"></i>
              </button>
              <ul class="drop-menu drop-menu--right" role="menu">
                <li><a class="drop-item" href="{{ url_for('profile.my_public_profile') }}">
                  <i class="bi bi-person-circle me-2"></i>My Profile</a></li>
                <li><a class="drop-item" href="{{ url_for('profile.account_overview') }}">
                  <i class="bi bi-person-badge me-2"></i>My Account</a></li>
                <li><a class="drop-item" href="{{ url_for('profile.edit_profile') }}">
                  <i class="bi bi-gear me-2"></i>Settings</a></li>
                <li><hr class="drop-divider"></li>
                <li>
                  <form method="POST" action="{{ url_for('auth.logout') }}">
                    <input type="hidden" name="csrf_token" value="{{ raw_csrf_token }}">
                    <button type="submit" class="drop-item drop-item--btn">
                      <i class="bi bi-box-arrow-right me-2"></i>Sign Out
                    </button>
                  </form>
                </li>
              </ul>
            </li>

          {% endif %}

        {# ── STATE 0: anonymous ───────────────────────────────────────── #}
        {% else %}

          <li class="menu-item">
            <a href="{{ url_for('wallet_api.wallet_home') }}">
              <i class="bi bi-wallet2 me-1"></i>Wallet
            </a>
          </li>
          <li class="menu-item auth">
            <a href="{{ url_for('auth.login') }}">Sign In</a>
          </li>
          <li class="menu-item auth">
            <a href="{{ url_for('auth.register') }}" class="btn-create-account">Sign Up</a>
          </li>

        {% endif %}
```

---

## PHASE 3 - `templates/base.html` - Mobile drawer rewrite

Find the mobile drawer authenticated section. It starts at:
```html
{% if current_user.is_authenticated %}
```
inside `<nav class="drawer-nav">`.

Replace the entire authenticated block with:

```html
      {% if current_user.is_authenticated %}

        {# Wallet - always first for authenticated users #}
        {% if nav_profile_completed %}
          <a class="drawer-link" href="{{ url_for('wallet.wallet_dashboard') }}">
            <i class="bi bi-wallet2 me-2"></i>Wallet
          </a>
        {% else %}
          <a class="drawer-link" href="{{ url_for('wallet_api.wallet_home') }}"
             style="opacity:0.6;">
            <i class="bi bi-wallet2 me-2"></i>Wallet
            <i class="bi bi-lock-fill ms-1" style="font-size:10px;"></i>
          </a>
        {% endif %}

        {# Dashboard or Create Account depending on state #}
        {% if not nav_profile_completed %}
          <a class="drawer-link drawer-link--primary" href="{{ url_for('onboarding.choose') }}">
            <i class="bi bi-person-plus me-2"></i>Create Account
          </a>
        {% elif nav_in_org_context %}
          <a class="drawer-link" href="{{ url_for('org.dashboard', org_id=session.get('current_org_id')) }}">
            <i class="bi bi-speedometer2 me-2"></i>Org Dashboard
          </a>
          <a class="drawer-link" href="{{ url_for('auth.switch_context', context='individual') }}">
            <i class="bi bi-person me-2"></i>Switch to Personal
          </a>
        {% else %}
          <a class="drawer-link" href="{% if current_user.is_app_owner() %}{{ url_for('admin.owner.dashboard') }}
            {% elif current_user.has_global_role('super_admin') %}{{ url_for('admin.super_dashboard') }}
            {% elif current_user.has_global_role('admin') %}{{ url_for('admin.super_dashboard') }}
            {% else %}{{ url_for('fan.dashboard') }}{% endif %}">
            <i class="bi bi-speedometer2 me-2"></i>Dashboard
          </a>
        {% endif %}

        <div class="drawer-divider"></div>

        <a class="drawer-link" href="{{ url_for('profile.my_public_profile') }}">
          <i class="bi bi-person-circle me-2"></i>My Profile
        </a>
        {% if nav_profile_completed %}
          <a class="drawer-link" href="{{ url_for('profile.account_overview') }}">
            <i class="bi bi-person-badge me-2"></i>My Account
          </a>
          <a class="drawer-link" href="{{ url_for('profile.edit_profile') }}">
            <i class="bi bi-gear me-2"></i>Settings
          </a>
        {% endif %}

        <div class="drawer-divider"></div>

        <form method="POST" action="{{ url_for('auth.logout') }}"
              style="display:block;width:100%;margin:0;padding:0;">
          <input type="hidden" name="csrf_token" value="{{ raw_csrf_token }}">
          <button type="submit" class="drawer-link drawer-auth"
                  style="width:100%;text-align:left;background:none;border:none;cursor:pointer;">
            <i class="bi bi-box-arrow-right me-2"></i>Sign Out
          </button>
        </form>

      {% else %}

        <a class="drawer-link" href="{{ url_for('wallet_api.wallet_home') }}">
          <i class="bi bi-wallet2 me-2"></i>Wallet
        </a>
        <a class="drawer-link drawer-auth" href="{{ url_for('auth.login') }}">Sign In</a>
        <a class="drawer-link drawer-auth drawer-link--primary"
           href="{{ url_for('auth.register') }}">Sign Up</a>

      {% endif %}
```

---

## PHASE 4 - CSS - Style the new nav elements

**File:** `static/css/global/style.css`

Append these styles at the very end of the file. Do not edit any existing styles:

```css
/* ══ PASS 6 NAV ADDITIONS ══════════════════════════════════════════ */

/* Create Account / Sign Up - primary green CTA */
.btn-create-account {
  background: #1D9E75;
  color: #fff !important;
  padding: 6px 14px;
  border-radius: 6px;
  font-weight: 500;
  font-size: 13px;
  transition: background .15s ease;
  white-space: nowrap;
}
.btn-create-account:hover {
  background: #17856A;
  color: #fff !important;
  text-decoration: none;
}

/* Locked wallet link */
.nav-wallet-locked {
  opacity: 0.55;
  cursor: default;
}

/* Wallet link - active */
.nav-wallet-link {
  color: inherit;
}

/* Dashboard link */
.nav-dashboard-link {
  color: inherit;
}

/* User avatar dropdown trigger */
.nav-user-menu { position: relative; }
.nav-user-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: 0.5px solid rgba(255,255,255,0.15);
  border-radius: 20px;
  padding: 4px 10px 4px 4px;
  cursor: pointer;
  color: inherit;
  font: inherit;
  font-size: 13px;
  transition: border-color .15s;
}
.nav-user-trigger:hover {
  border-color: rgba(255,255,255,0.35);
}
.nav-user-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #1D9E75;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.nav-user-name {
  font-size: 13px;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Org context - amber styling */
.nav-user-trigger--org {
  border-color: rgba(255,193,7,0.3);
}
.nav-user-trigger--org:hover {
  border-color: rgba(255,193,7,0.6);
}
.nav-org-avatar {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: rgba(255,193,7,0.2);
  color: #FFC107;
  border: 1px solid rgba(255,193,7,0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.nav-org-name {
  font-size: 12px;
  color: #FFC107;
  font-weight: 500;
}

/* Dropdown right-aligned */
.drop-menu--right {
  right: 0;
  left: auto;
}

/* Dropdown button styled as link */
.drop-item--btn {
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  font: inherit;
  color: inherit;
}

/* Mobile drawer primary link */
.drawer-link--primary {
  color: #1D9E75 !important;
  font-weight: 500;
}

/* ══ END PASS 6 NAV ADDITIONS ══════════════════════════════════════ */
```

---

## PHASE 5 - `app/auth/routes.py` - Remove forced onboarding redirect from login

**Context:** Currently `_dashboard_for_user()` redirects users with
`profile_completed = False` to `/onboarding/choose`. This must be removed.
Users now go directly to the dashboard after login. The "Create Account"
button in the nav takes them to choose when they are ready.

**Find in `_dashboard_for_user()`:**
```python
    # ── ONBOARDING GATE (additive) ──────────────────────────────
    try:
        from app.profile.models import get_profile_by_user
        _profile = get_profile_by_user(user.public_id)
        if not _profile or not _profile.profile_completed:
            return url_for("onboarding.choose")
    except Exception as _e:
        current_app.logger.warning(f"Onboarding gate check failed: {_e}")
    # ── END ONBOARDING GATE ──────────────────────────────────────
```

**Delete those 7 lines entirely.** The function then falls through to its
existing role-based routing logic as before.

**Also find in `_dashboard_for_user()` the final fallback:**
```python
    try:
        return url_for("fan.dashboard")
    except Exception:
        return url_for("index")
```
This stays unchanged. `fan.dashboard` is the personal home for all users
with completed accounts. Users without accounts also land here - but
the nav shows "Create Account" prominently so they know what to do next.

**Verify:**
```bash
grep -n "onboarding.choose" app/auth/routes.py
```
Expected: 0 matches (the gate is gone from routes - it now lives in the nav).

---

## PHASE 6 - `app/auth/routes.py` - Add switch_context route

The nav references `auth.switch_context`. Add this route if it does not
already exist in `app/auth/routes.py`:

```python
@auth_bp.route("/switch-context/<context>", methods=["POST", "GET"])
@login_required
def switch_context(context):
    """
    Switch between personal and organisation context.
    Called from the nav dropdown.
    context: 'individual' | 'organization'
    """
    from flask import session, redirect, url_for, request

    if context == "individual":
        session["current_context"] = "individual"
        session.pop("current_org_id", None)
        session.pop("current_org_name", None)
        # Redirect to personal dashboard
        return redirect(url_for("fan.dashboard"))

    elif context == "organization":
        # org_id must be provided as query param or form field
        org_id = request.args.get("org_id") or request.form.get("org_id")
        if not org_id:
            flash("No organisation specified.", "warning")
            return redirect(url_for("fan.dashboard"))

        # Verify user is a member of this org
        from app.identity.models.organisation import Organisation
        from app.identity.models.organisation_member import OrganisationMember
        from app.identity.models.user import User as UserModel

        db_user = UserModel.query.filter_by(
            public_id=str(current_user.public_id)
        ).first()

        org = Organisation.query.filter_by(org_id=org_id).first()
        if not org:
            flash("Organisation not found.", "danger")
            return redirect(url_for("fan.dashboard"))

        member = OrganisationMember.query.filter_by(
            user_id=db_user.id,
            organisation_id=org.id,
            is_active=True,
            is_deleted=False,
        ).first()

        if not member:
            flash("You are not a member of this organisation.", "danger")
            return redirect(url_for("fan.dashboard"))

        session["current_context"] = "organization"
        session["current_org_id"] = org.org_id   # UUID - not BIGINT
        session["current_org_name"] = org.legal_name

        return redirect(url_for("org.dashboard", org_id=org.org_id))

    else:
        return redirect(url_for("fan.dashboard"))
```

---

## PHASE 7 - `app/auth/routes.py` - Fix login redirect for new users

After OTP verification or standard login, new users currently hit the
onboarding gate (which we just removed). Now they go straight to
`fan.dashboard`. The dashboard must handle both states gracefully -
profile complete and incomplete.

Find the post-login redirect in the login route. It calls
`_dashboard_for_user(user)`. This is correct - keep it.

The fan dashboard already shows the content. The nav "Create Account"
button is the prompt. No changes needed to the login route itself.

---

## PHASE 8 - `templates/fan/dashboard.html` - Add "Create Account" banner

For users who are logged in but have not yet created an account
(`profile_completed = False`), show a welcoming banner at the top of
the dashboard explaining what to do next.

Find the very first line inside `{% block content %}` in `fan/dashboard.html`.
Add this block immediately:

```html
{# ── ACCOUNT CREATION PROMPT (shown only before account is created) ── #}
{% if not nav_profile_completed %}
<div class="container-fluid mt-3 mb-1">
  <div class="alert d-flex align-items-center gap-3 mb-0"
       style="background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);
              border:none;border-radius:12px;padding:20px 24px;color:#fff;">
    <div style="font-size:2rem;">👋</div>
    <div style="flex:1;">
      <strong style="font-size:16px;">Welcome to AFCON 360, {{ current_user.username }}!</strong>
      <p class="mb-0 mt-1" style="font-size:13px;opacity:0.85;">
        You're in. Browse events, accommodation and transport.
        When you're ready to book or provide services -
        <strong>create your account</strong> to unlock everything.
      </p>
    </div>
    <a href="{{ url_for('onboarding.choose') }}"
       class="btn btn-sm flex-shrink-0"
       style="background:#1D9E75;color:#fff;font-weight:600;
              border-radius:8px;padding:8px 18px;white-space:nowrap;">
      Create Account →
    </a>
  </div>
</div>
{% endif %}
{# ── END ACCOUNT CREATION PROMPT ──────────────────────────────────── #}
```

---

## PHASE 9 - `templates/onboarding/choose.html` - Simplify to 2 top-level choices

The current choose page shows 7 cards at once. This is overwhelming
as a first decision. Replace it with 2 top-level cards. Sub-choices
happen inside the wizard after this.

**Replace the entire content of `templates/onboarding/choose.html` with:**

```html
{% extends "base.html" %}
{% block title %}Create Your Account - AFCON 360{% endblock %}
{% block content %}

<div class="ob-choose-root">
  <div class="ob-choose-inner">

    <div class="ob-choose-header">
      <h1>Create your account</h1>
      <p>Are you here as an individual, or representing an organisation?</p>
    </div>

    <div class="ob-choose-grid">

      <!-- INDIVIDUAL -->
      <a href="{{ url_for('onboarding.choose_individual') }}" class="ob-big-card">
        <div class="ob-big-card-icon">👤</div>
        <div class="ob-big-card-body">
          <h2>Individual</h2>
          <p>You are a person - a fan, a driver, a host, or an event organiser. One account, your name, your identity.</p>
          <ul>
            <li>Book events, transport and accommodation</li>
            <li>Offer transport as a driver</li>
            <li>List your property as a host</li>
            <li>Organise events</li>
          </ul>
        </div>
        <span class="ob-big-card-cta">Continue as Individual →</span>
      </a>

      <!-- ORGANISATION -->
      <a href="{{ url_for('onboarding.choose_organisation') }}" class="ob-big-card ob-big-card--org">
        <div class="ob-big-card-icon">🏢</div>
        <div class="ob-big-card-body">
          <h2>Organisation</h2>
          <p>You represent a company, team, hotel, or fleet. Register your business and manage team access and billing centrally.</p>
          <ul>
            <li>Transport company or fleet</li>
            <li>Hotel, lodge or guesthouse</li>
            <li>Sports team or delegation</li>
            <li>Any company booking services at scale</li>
          </ul>
        </div>
        <span class="ob-big-card-cta">Continue as Organisation →</span>
      </a>

    </div>

    <p class="ob-choose-note">
      You can add an organisation account later even if you start as an individual.
    </p>

  </div>
</div>

<style>
.ob-choose-root {
  min-height: 80vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  background: var(--bs-body-bg, #f8f9fa);
}
.ob-choose-inner {
  max-width: 820px;
  width: 100%;
}
.ob-choose-header {
  text-align: center;
  margin-bottom: 36px;
}
.ob-choose-header h1 {
  font-size: clamp(24px, 4vw, 36px);
  font-weight: 700;
  margin: 0 0 10px;
}
.ob-choose-header p {
  font-size: 16px;
  color: #6c757d;
  margin: 0;
}
.ob-choose-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}
@media (max-width: 600px) {
  .ob-choose-grid { grid-template-columns: 1fr; }
}
.ob-big-card {
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1.5px solid #e9ecef;
  border-radius: 16px;
  padding: 32px 28px;
  text-decoration: none;
  color: inherit;
  transition: border-color .2s, box-shadow .2s, transform .2s;
}
.ob-big-card:hover {
  border-color: #1D9E75;
  box-shadow: 0 8px 32px rgba(29,158,117,0.12);
  transform: translateY(-3px);
  text-decoration: none;
  color: inherit;
}
.ob-big-card--org:hover {
  border-color: #FFC107;
  box-shadow: 0 8px 32px rgba(255,193,7,0.12);
}
.ob-big-card-icon {
  font-size: 40px;
  margin-bottom: 16px;
  line-height: 1;
}
.ob-big-card-body h2 {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 10px;
}
.ob-big-card-body p {
  font-size: 14px;
  color: #6c757d;
  margin: 0 0 14px;
  line-height: 1.6;
}
.ob-big-card-body ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
.ob-big-card-body ul li {
  font-size: 13px;
  color: #495057;
  padding: 4px 0;
  padding-left: 18px;
  position: relative;
}
.ob-big-card-body ul li::before {
  content: '→';
  position: absolute;
  left: 0;
  color: #1D9E75;
  font-size: 11px;
}
.ob-big-card--org .ob-big-card-body ul li::before {
  color: #FFC107;
}
.ob-big-card-cta {
  display: block;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #f0f0f0;
  font-size: 14px;
  font-weight: 600;
  color: #1D9E75;
}
.ob-big-card--org .ob-big-card-cta {
  color: #856404;
}
.ob-choose-note {
  text-align: center;
  font-size: 13px;
  color: #6c757d;
  margin: 0;
}
</style>

{% endblock %}
```

---

## PHASE 10 - `app/auth/onboarding_routes.py` - Add two new routes

The new choose page links to `onboarding.choose_individual` and
`onboarding.choose_organisation`. Add these two routes:

```python
@onboarding_bp.route("/choose/individual", methods=["GET"])
@login_required
def choose_individual():
    """
    Second-level individual choose page.
    Shows: Fan/Explorer, Driver, Host, Event Organiser.
    """
    return render_template("onboarding/choose_individual.html")


@onboarding_bp.route("/choose/organisation", methods=["GET"])
@login_required
def choose_organisation():
    """
    Second-level organisation choose page.
    Shows: Transport Company, Hotel/Lodge, Consumer Organisation.
    """
    return render_template("onboarding/choose_organisation.html")
```

Then create two simple templates:

**`templates/onboarding/choose_individual.html`:**
```html
{% extends "base.html" %}
{% block title %}Individual Account - AFCON 360{% endblock %}
{% block content %}
<div class="ob-choose-root">
  <div class="ob-choose-inner">
    <div class="ob-choose-header">
      <a href="{{ url_for('onboarding.choose') }}"
         style="font-size:13px;color:#6c757d;text-decoration:none;">← Back</a>
      <h1 style="margin-top:12px;">What will you do on AFCON 360?</h1>
      <p>Choose what fits you best. You can add more roles later.</p>
    </div>
    <div class="ob-choose-grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr));">

      <a href="{{ url_for('onboarding.fan_onboarding') }}" class="ob-big-card">
        <div class="ob-big-card-icon">🎟️</div>
        <div class="ob-big-card-body">
          <h2 style="font-size:18px;">Fan & Explorer</h2>
          <p>Book events, accommodation and transport as an individual.</p>
        </div>
        <span class="ob-big-card-cta">Get Started →</span>
      </a>

      <a href="{{ url_for('onboarding.driver_onboarding') }}" class="ob-big-card">
        <div class="ob-big-card-icon">🚗</div>
        <div class="ob-big-card-body">
          <h2 style="font-size:18px;">Driver</h2>
          <p>Offer transport. Register your licence and vehicle.</p>
        </div>
        <span class="ob-big-card-cta">Become a Driver →</span>
      </a>

      <a href="{{ url_for('onboarding.host_onboarding') }}" class="ob-big-card">
        <div class="ob-big-card-icon">🏠</div>
        <div class="ob-big-card-body">
          <h2 style="font-size:18px;">Accommodation Host</h2>
          <p>List your property for short-term stays.</p>
        </div>
        <span class="ob-big-card-cta">List Property →</span>
      </a>

      <a href="{{ url_for('onboarding.event_organiser_onboarding') }}" class="ob-big-card">
        <div class="ob-big-card-icon">🎪</div>
        <div class="ob-big-card-body">
          <h2 style="font-size:18px;">Event Organiser</h2>
          <p>Create events, sell tickets, manage attendees.</p>
        </div>
        <span class="ob-big-card-cta">Start Organising →</span>
      </a>

    </div>
  </div>
</div>
{% include 'onboarding/_wizard_styles.html' %}
{% endblock %}
```

**`templates/onboarding/choose_organisation.html`:**
```html
{% extends "base.html" %}
{% block title %}Organisation Account - AFCON 360{% endblock %}
{% block content %}
<div class="ob-choose-root">
  <div class="ob-choose-inner">
    <div class="ob-choose-header">
      <a href="{{ url_for('onboarding.choose') }}"
         style="font-size:13px;color:#6c757d;text-decoration:none;">← Back</a>
      <h1 style="margin-top:12px;">What type of organisation?</h1>
      <p>Register your business to manage team access, billing and services at scale.</p>
    </div>
    <div class="ob-choose-grid" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr));">

      <a href="{{ url_for('onboarding.organisation_onboarding', type='transport') }}" class="ob-big-card ob-big-card--org">
        <div class="ob-big-card-icon">🚌</div>
        <div class="ob-big-card-body">
          <h2 style="font-size:18px;">Transport Company</h2>
          <p>Register your fleet and manage multiple drivers and vehicles.</p>
        </div>
        <span class="ob-big-card-cta">Register Fleet →</span>
      </a>

      <a href="{{ url_for('onboarding.organisation_onboarding', type='accommodation') }}" class="ob-big-card ob-big-card--org">
        <div class="ob-big-card-icon">🏨</div>
        <div class="ob-big-card-body">
          <h2 style="font-size:18px;">Hotel / Lodge</h2>
          <p>Manage rooms, staff and central billing for your establishment.</p>
        </div>
        <span class="ob-big-card-cta">Register Establishment →</span>
      </a>

      <a href="{{ url_for('onboarding.organisation_onboarding', type='consumer') }}" class="ob-big-card ob-big-card--org">
        <div class="ob-big-card-icon">🏢</div>
        <div class="ob-big-card-body">
          <h2 style="font-size:18px;">Organisation</h2>
          <p>Book services as a company - teams, delegations, corporate groups.</p>
        </div>
        <span class="ob-big-card-cta">Register Organisation →</span>
      </a>

    </div>
  </div>
</div>
{% include 'onboarding/_wizard_styles.html' %}
{% endblock %}
```

---

## PHASE 11 - VERIFICATION

Run each command. Paste output in the report.

```powershell
# 1. App starts without errors
cd C:\Users\ADMIN\Desktop\afcon360_app
.venv\Scripts\python.exe -m flask --app app.py routes | findstr "onboarding"

# 2. New routes exist
.venv\Scripts\python.exe -m flask --app app.py routes | findstr "choose"

# 3. switch_context route exists
.venv\Scripts\python.exe -m flask --app app.py routes | findstr "switch"

# 4. No forced onboarding redirect in _dashboard_for_user
findstr /n "onboarding.choose" app\auth\routes.py
# Expected: 0 matches

# 5. nav_profile_completed in context processor
findstr /n "nav_profile_completed" app\__init__.py
# Expected: at least 2 matches (assignment + return dict)

# 6. nav_profile_completed used in base.html
findstr /n "nav_profile_completed" templates\base.html
# Expected: at least 2 matches
```

---

## REPORT TEMPLATE

```
=== PASS 6 REPORT ===
Date: ___________

PHASE 1 - Context processor:
nav_profile_completed added: YES / NO
nav_in_org_context added: YES / NO
nav_org_name added: YES / NO

PHASE 2 - Desktop nav:
State 0 (anonymous) - Wallet + Sign In + Sign Up: YES / NO
State 1 (no account) - Wallet locked + Create Account + name dropdown: YES / NO
State 2 (personal) - Wallet + Dashboard + name dropdown: YES / NO
State 3 (org context) - Org Wallet + Org Dashboard + org dropdown: YES / NO

PHASE 3 - Mobile drawer:
All 4 states handled: YES / NO

PHASE 4 - CSS added to style.css: YES / NO

PHASE 5 - Forced redirect removed from _dashboard_for_user: YES / NO
findstr output: ___________

PHASE 6 - switch_context route added: YES / NO

PHASE 8 - Welcome banner in fan/dashboard.html: YES / NO

PHASE 9 - choose.html simplified to 2 cards: YES / NO

PHASE 10 - choose_individual and choose_organisation routes + templates: YES / NO

PHASE 11 - Verification:
App starts without errors: YES / NO
All routes present: YES / NO
Any pages broken: YES / NO
If yes, describe: ___________

MANUAL TEST - Anonymous visitor sees Wallet in nav: YES / NO
MANUAL TEST - New user (no account) sees Create Account button: YES / NO
MANUAL TEST - Existing user sees Wallet + Dashboard + name dropdown: YES / NO
MANUAL TEST - Fan dashboard shows welcome banner for new users: YES / NO
MANUAL TEST - Choose page shows 2 cards (Individual / Organisation): YES / NO
```

---

## WINDOWS / PYCHARM NOTES FOR ALL FUTURE PASSES

1. Terminal: always use PowerShell inside PyCharm terminal
2. Python path: `.venv\Scripts\python.exe` (not just `python`)
3. Flask commands: `.venv\Scripts\python.exe -m flask --app app.py <command>`
4. Never use `-c` with multi-line Python strings in PowerShell - use script files
5. String search: use `findstr /n "text" file\path.py` (not `grep`)
6. List files: use `dir` (not `ls`)
7. Path separator: backslash `\` in PowerShell commands
8. To run a Python script: `.venv\Scripts\python.exe scripts\script_name.py`
```
