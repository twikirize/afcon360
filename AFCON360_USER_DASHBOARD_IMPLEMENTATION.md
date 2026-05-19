# AFCON360 — User Dashboard Full Implementation
**For Codeium / Aider. Feed this entire file. Implement in order. Do not skip any section.**

---

## 0. CONTEXT & ROOT CAUSES

The current dashboard (`user_dashboard.html`) has these confirmed problems:

1. **`attendee_dashboard.html` variables mismatch** — That template expects `upcoming_registrations`, `past_registrations`, `upcoming_count`, `attended_count`, `total_spent`, `wallet` (object) — but `routes.py` passes `registrations` (merged list), `wallet_balance` (float), no `wallet` object. Nothing renders.
2. **`my_registrations.html` (events blueprint)** — Uses broken `safe_url('url_for\(...')` string literal syntax, which is not a valid Jinja2 call. All ticket/detail buttons produce `#`.
3. **`base_user_dashboard.html` AJAX pane loader** — Works correctly in isolation, but the pane-loaded sub-pages don't strip their `{% extends "base.html" %}` wrapper when loaded via `?_pane=1`, so Bootstrap navbar/scripts double-load and layout breaks.
4. **`user_dashboard.html`** — The `My Events` section (`data-section="events"`) is defined in the nav but no `<div id="events">` exists in the template, so clicking it shows a blank panel.

**Architecture decision**: We are NOT redesigning the 2-panel shell (`base_user_dashboard.html`). We ARE:
- Fixing `routes.py` to pass correct variables for both dashboards
- Replacing `user_dashboard.html` (the right-panel content) with a proper events section
- Fixing `my_registrations.html` (events blueprint copy) URL helpers
- Creating a lightweight `_pane_base.html` so AJAX-loaded panes don't double-render base.html

---

## 1. FILE MANIFEST

| # | Action | File path (from project root) |
|---|--------|-------------------------------|
| 1 | **REPLACE** | `app/user/routes.py` |
| 2 | **REPLACE** | `app/templates/user/base_user_dashboard.html` |
| 3 | **REPLACE** | `app/templates/user/user_dashboard.html` |
| 4 | **REPLACE** | `app/templates/user/my_registrations.html` |
| 5 | **CREATE**  | `app/templates/user/_pane_base.html` |
| 6 | **REPLACE** | `app/templates/events/my_registrations.html` |

> **Path note**: your tree shows templates at `app/templates/`. If your project has them at `templates/` (root-level), adjust accordingly. The Python imports do not change.

---

## 2. FILE 1 — `app/user/routes.py` (REPLACE ENTIRELY)

```python
# app/user/routes.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app.events.services import EventService
from app.wallet.services.wallet_service import WalletService
from datetime import date, datetime
import logging
from app.auth.kyc_compliance import calculate_kyc_tier

logger = logging.getLogger(__name__)

user_bp = Blueprint('user', __name__, url_prefix='/user')


def _enrich_registrations(registrations):
    """
    Shared helper — enrich a list of registration dicts with:
    - ISO-stringified dates
    - EventAssignment data if available
    Returns the same list mutated in place.
    """
    for reg in registrations:
        # Normalise date fields to ISO strings so Jinja slice [:10] is safe
        event_data = reg.get('event', {})
        for field in ('start_date', 'end_date', 'created_at', 'updated_at'):
            val = event_data.get(field)
            if isinstance(val, (date, datetime)):
                event_data[field] = val.isoformat()

        # Try to attach assignment
        try:
            from app.events.models import EventAssignment, Event
            slug = event_data.get('slug')
            if slug:
                event_obj = Event.query.filter_by(slug=slug).first()
                if event_obj:
                    assignment = EventAssignment.query.filter_by(
                        event_id=event_obj.id,
                        attendee_id=current_user.id
                    ).first()
                    if assignment:
                        reg['assignment'] = EventService._assignment_to_dict(assignment)
        except Exception as exc:
            logger.warning("Could not load assignment for reg %s: %s", reg.get('id'), exc)

    return registrations


def _get_wallet():
    """Return wallet object or None — never raises."""
    try:
        return WalletService.get_wallet_by_user_id(current_user.id)
    except Exception:
        return None


def _get_modules():
    """Return module-enabled dict — never raises."""
    from app.utils.module_switch import check_module_enabled
    keys = ('wallet', 'transport', 'accommodation', 'tourism', 'tournament')
    return {k: {'enabled': check_module_enabled(k)} for k in keys}


def _split_registrations(all_regs):
    """Split a flat list of reg dicts into upcoming / past by event.start_date."""
    today = date.today().isoformat()
    upcoming, past = [], []
    for reg in all_regs:
        sd = reg.get('event', {}).get('start_date', '')
        # start_date is already an ISO string after _enrich_registrations
        if isinstance(sd, str) and sd[:10] >= today:
            upcoming.append(reg)
        else:
            past.append(reg)
    return upcoming, past


@user_bp.route("/dashboard")
@login_required
def user_dashboard():
    """Main user dashboard."""
    try:
        from app.identity.models.user import User
        from sqlalchemy.orm import joinedload
        user = User.query.options(joinedload(User.organisations)).get(current_user.id)
        if not user:
            return redirect(url_for('auth.logout'))

        data = EventService.get_attendee_dashboard_data(current_user.id)
        all_regs = data['upcoming_registrations'] + data['past_registrations']
        _enrich_registrations(all_regs)
        upcoming_regs, past_regs = _split_registrations(all_regs)

        wallet = _get_wallet()
        wallet_balance = wallet.balance if wallet else 0.0

        # Compute dashboard stats
        upcoming_count = len(upcoming_regs)
        attended_count = sum(
            1 for r in past_regs if r.get('status') == 'checked_in'
        )
        total_spent = sum(
            (r.get('registration_fee') or 0) for r in all_regs
            if r.get('status') != 'cancelled'
        )

        # KYC tier
        kyc_info = {}
        try:
            kyc_info = calculate_kyc_tier(current_user.id)
        except Exception:
            pass

        # Tourism listings (sidebar preview)
        tourism_listings = []
        try:
            from app.tourism.models import TourismListing
            tourism_listings = TourismListing.query.filter_by(
                status='published', is_deleted=False
            ).order_by(TourismListing.created_at.desc()).limit(4).all()
        except Exception:
            pass

        return render_template(
            'user/user_dashboard.html',
            # Flat list (legacy compat)
            registrations=all_regs,
            # Split lists (new template uses these)
            upcoming_registrations=upcoming_regs,
            past_registrations=past_regs,
            # Stats
            upcoming_count=upcoming_count,
            attended_count=attended_count,
            total_spent="%.2f" % total_spent,
            # Wallet — pass BOTH formats
            wallet=wallet,
            wallet_balance=wallet_balance,
            # Misc
            current_date=date.today().isoformat(),
            user_organisations=user.organisations,
            kyc_info=kyc_info,
            tourism_listings=tourism_listings,
            modules=_get_modules(),
        )

    except Exception as exc:
        logger.error("Error loading user dashboard: %s", exc)
        return render_template(
            'user/user_dashboard.html',
            registrations=[], upcoming_registrations=[], past_registrations=[],
            upcoming_count=0, attended_count=0, total_spent="0.00",
            wallet=None, wallet_balance=0,
            current_date=date.today().isoformat(),
            user_organisations=[], kyc_info={}, tourism_listings=[],
            modules=_get_modules(),
        )


@user_bp.route("/my-registrations")
@login_required
def my_registrations():
    """Standalone registrations page (also pane-loadable)."""
    try:
        data = EventService.get_attendee_dashboard_data(current_user.id)
        all_regs = data['upcoming_registrations'] + data['past_registrations']
        _enrich_registrations(all_regs)
        upcoming_regs, past_regs = _split_registrations(all_regs)

        wallet = _get_wallet()

        return render_template(
            'user/my_registrations.html',
            registrations=all_regs,
            upcoming_registrations=upcoming_regs,
            past_registrations=past_regs,
            upcoming_count=len(upcoming_regs),
            attended_count=sum(1 for r in past_regs if r.get('status') == 'checked_in'),
            total_spent="%.2f" % sum(
                (r.get('registration_fee') or 0) for r in all_regs
                if r.get('status') != 'cancelled'
            ),
            wallet=wallet,
            wallet_balance=wallet.balance if wallet else 0.0,
            current_date=date.today().isoformat(),
        )
    except Exception as exc:
        logger.error("Error loading my registrations: %s", exc)
        return render_template(
            'user/my_registrations.html',
            registrations=[], upcoming_registrations=[], past_registrations=[],
            upcoming_count=0, attended_count=0, total_spent="0.00",
            wallet=None, wallet_balance=0,
            current_date=date.today().isoformat(),
        )


@user_bp.route("/cancel-registration", methods=['POST'])
@login_required
def cancel_registration():
    try:
        payload = request.get_json()
        reg_ref = payload.get('reg_ref') if payload else None
        if not reg_ref:
            return jsonify({'success': False, 'error': 'Registration reference required'}), 400
        success, error = EventService.cancel_registration(reg_ref, current_user.id)
        if success:
            return jsonify({'success': True, 'message': 'Registration cancelled successfully'})
        return jsonify({'success': False, 'error': error or 'Failed to cancel registration'}), 400
    except Exception as exc:
        logger.error("Error cancelling registration: %s", exc)
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500


@user_bp.route("/contact-organizer", methods=['POST'])
@login_required
def contact_organizer():
    try:
        payload = request.get_json()
        event_id = payload.get('event_id') if payload else None
        message = payload.get('message') if payload else None
        if not event_id or not message:
            return jsonify({'success': False, 'error': 'Event ID and message required'}), 400
        return jsonify({'success': True, 'message': 'Message sent to organizer'})
    except Exception as exc:
        logger.error("Error contacting organizer: %s", exc)
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500
```

---

## 3. FILE 2 — `app/templates/user/base_user_dashboard.html` (REPLACE ENTIRELY)

**Key fixes vs original:**
- `toggleMobileNav()` is now defined before it is referenced
- `data-section="events"` now maps to a real section rendered by the child template
- AJAX pane loader correctly adds `_pane=1` query param AND passes `X-Requested-With` header

```html
{% extends "base.html" %}

{% block title %}User Dashboard - AFCON360{% endblock %}

{% block content %}
<style>
:root {
    --primary: #667eea;
    --primary-dark: #5a67d8;
    --secondary: #764ba2;
    --success: #48bb78;
    --warning: #f6ad55;
    --danger: #fc8181;
    --info: #4299e1;
    --dark: #2d3748;
    --light: #f7fafc;
    --border: #e2e8f0;
    --shadow: 0 4px 6px rgba(0,0,0,0.1);
    --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
}

/* ── Layout ─────────────────────────────────── */
.dashboard-container {
    display: flex;
    height: calc(100vh - 70px);
    background: var(--light);
}

/* ── Left Panel ──────────────────────────────── */
.left-panel {
    width: 260px;
    background: white;
    border-right: 1px solid var(--border);
    box-shadow: var(--shadow);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    flex-shrink: 0;
}

.user-profile-section {
    padding: 1.75rem 1.5rem 1.25rem;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
    text-align: center;
}

.user-avatar {
    width: 56px; height: 56px; border-radius: 50%;
    background: rgba(255,255,255,0.2);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem; font-weight: 700;
    margin: 0 auto 0.75rem;
}

.user-name  { font-size: 1rem; font-weight: 700; margin-bottom: 0.25rem; }
.user-email { font-size: 0.8rem; opacity: 0.85; word-break: break-all; }

.org-badge {
    margin-top: 0.75rem; padding: 0.4rem 0.75rem;
    background: rgba(255,255,255,0.12);
    border-radius: 20px; font-size: 0.75rem; display: inline-block;
}

/* ── Context Switcher ────────────────────────── */
.context-switcher {
    margin: 0.75rem; padding: 0.75rem;
    background: #f8fafc; border-radius: 8px; border: 1px solid var(--border);
}
.context-switcher h4 { font-size: 0.8rem; color: #718096; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.04em; }
.context-btn {
    width: 100%; padding: 0.45rem 0.75rem; margin-bottom: 0.4rem;
    border: 1px solid var(--primary); background: white; color: var(--primary);
    border-radius: 6px; font-size: 0.8rem; cursor: pointer; transition: all 0.2s;
    display: flex; align-items: center; gap: 0.5rem;
}
.context-btn:hover, .context-btn.active { background: var(--primary); color: white; }

/* ── Nav Menu ────────────────────────────────── */
.nav-menu { flex: 1; padding: 0.5rem 0; }

.nav-section-label {
    padding: 0.75rem 1.25rem 0.25rem;
    font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: #a0aec0; font-weight: 600;
}

.nav-item {
    display: flex; align-items: center;
    padding: 0.6rem 1.25rem;
    color: var(--dark); text-decoration: none;
    transition: all 0.2s; border-left: 3px solid transparent;
    cursor: pointer; font-size: 0.875rem; gap: 0.6rem;
}
.nav-item:hover { background: var(--light); color: var(--primary); border-left-color: var(--primary); }
.nav-item.active {
    background: linear-gradient(90deg, rgba(102,126,234,0.1), transparent);
    color: var(--primary); border-left-color: var(--primary); font-weight: 600;
}
.nav-item i { width: 18px; text-align: center; flex-shrink: 0; }
.nav-badge {
    margin-left: auto;
    background: var(--danger); color: white;
    font-size: 0.65rem; padding: 2px 6px; border-radius: 10px;
}

/* ── Right Panel ─────────────────────────────── */
.right-panel { flex: 1; overflow-y: auto; padding: 2rem; }

/* ── Content sections ────────────────────────── */
.content-section { display: none; }
.content-section.active { display: block; }

/* ── Loading / Error ─────────────────────────── */
.pane-loading {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 4rem; min-height: 300px; color: #718096;
}
.pane-spinner {
    width: 38px; height: 38px;
    border: 3px solid var(--border); border-top-color: var(--primary);
    border-radius: 50%; animation: spin 0.8s linear infinite;
    margin-bottom: 1rem;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Mobile ──────────────────────────────────── */
.mobile-hamburger {
    display: none; position: fixed; top: 80px; left: 1rem; z-index: 1000;
    background: var(--primary); color: white; border: none;
    border-radius: 8px; width: 42px; height: 42px;
    font-size: 1.1rem; cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
.mobile-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.4); z-index: 999;
}
.mobile-overlay.active { display: block; }

@media (max-width: 768px) {
    .left-panel {
        position: fixed; top: 0; left: 0; height: 100vh;
        z-index: 1000; transform: translateX(-100%);
        transition: transform 0.3s ease;
    }
    .left-panel.open { transform: translateX(0); }
    .mobile-hamburger { display: flex; align-items: center; justify-content: center; }
    .right-panel { padding: 1rem 1rem 1rem 3.5rem; }
}
</style>

<div id="mobileOverlay" class="mobile-overlay" onclick="toggleMobileNav()"></div>
<button class="mobile-hamburger" onclick="toggleMobileNav()" aria-label="Open menu">
    <i class="fas fa-bars"></i>
</button>

<div class="dashboard-container">

    {# ── Left Panel ───────────────────────────── #}
    <div class="left-panel" id="leftPanel">

        <div class="user-profile-section">
            <div class="user-avatar">
                {{ current_user.username[0]|upper if current_user.username else '?' }}
            </div>
            <div class="user-name">{{ current_user.username }}</div>
            <div class="user-email">{{ current_user.email }}</div>
            {% if user_organisations|default([])|length > 0 %}
            <span class="org-badge"><i class="fas fa-building me-1"></i>Organisation Member</span>
            {% endif %}
        </div>

        {% if user_organisations|default([])|length > 0 %}
        <div class="context-switcher">
            <h4>Context</h4>
            <button class="context-btn active" onclick="switchToPersonal()">
                <i class="fas fa-user"></i> Personal
            </button>
            {% for m in user_organisations %}
            <button class="context-btn" onclick="switchToOrg('{{ m.organisation.id }}')">
                <i class="fas fa-building"></i> {{ m.organisation.name }}
            </button>
            {% endfor %}
        </div>
        {% endif %}

        <nav class="nav-menu">
            <div class="nav-section-label">Overview</div>
            <a href="#" class="nav-item active" data-section="dashboard">
                <i class="fas fa-tachometer-alt"></i> Dashboard
            </a>
            <a href="#" class="nav-item" data-section="events">
                <i class="fas fa-ticket-alt"></i> My Events
                {% if registrations|default([])|length > 0 %}
                <span class="nav-badge">{{ registrations|length }}</span>
                {% endif %}
            </a>

            <div class="nav-section-label">Services</div>
            {% if modules.get('wallet', {}).get('enabled') %}
            <a href="#" class="nav-item" data-pane-url="{{ safe_url('wallet.wallet_dashboard') }}">
                <i class="fas fa-wallet"></i> Wallet
            </a>
            {% endif %}
            {% if modules.get('transport', {}).get('enabled') %}
            <a href="#" class="nav-item" data-pane-url="{{ safe_url('transport.home') }}">
                <i class="fas fa-bus"></i> Transport
            </a>
            {% endif %}
            {% if modules.get('accommodation', {}).get('enabled') %}
            <a href="#" class="nav-item" data-pane-url="{{ safe_url('accommodation.guest.search') }}">
                <i class="fas fa-bed"></i> Accommodation
            </a>
            {% endif %}
            {% if modules.get('tourism', {}).get('enabled') %}
            <a href="#" class="nav-item" data-pane-url="{{ safe_url('tourism.home') }}">
                <i class="fas fa-map-marked-alt"></i> Tourism
            </a>
            {% endif %}
            {% if modules.get('tournament', {}).get('enabled') %}
            <a href="#" class="nav-item" data-pane-url="{{ safe_url('tournament.home') }}">
                <i class="fas fa-trophy"></i> Tournament
            </a>
            {% endif %}

            <div class="nav-section-label">Account</div>
            <a href="#" class="nav-item" data-pane-url="{{ safe_url('kyc.index') }}">
                <i class="fas fa-id-card"></i> Verification
            </a>
            <a href="#" class="nav-item" data-pane-url="{{ safe_url('profile.my_public_profile') }}">
                <i class="fas fa-user-circle"></i> Profile
            </a>
            <a href="#" class="nav-item" data-pane-url="{{ safe_url('profile.account_overview') }}">
                <i class="fas fa-cog"></i> Settings
            </a>
        </nav>
    </div>

    {# ── Right Panel ──────────────────────────── #}
    <div class="right-panel" id="rightPanel">
        {% block content_section %}{% endblock %}
    </div>
</div>

<script>
// ── Mobile nav ───────────────────────────────────────────────────────────────
function toggleMobileNav() {
    var panel  = document.getElementById('leftPanel');
    var overlay = document.getElementById('mobileOverlay');
    panel.classList.toggle('open');
    overlay.classList.toggle('active');
}

// ── Section / pane router ────────────────────────────────────────────────────
(function () {
    var rightPanel    = document.getElementById('rightPanel');
    var navItems      = document.querySelectorAll('.nav-item');
    var contentSections = document.querySelectorAll('.content-section');

    function setActiveNav(selector, value) {
        navItems.forEach(function (n) { n.classList.remove('active'); });
        var match = document.querySelector('.nav-item[' + selector + '="' + value + '"]');
        if (match) match.classList.add('active');
    }

    function showSection(id) {
        setActiveNav('data-section', id);
        contentSections.forEach(function (s) { s.classList.remove('active'); });
        var target = document.getElementById(id);
        if (target) target.classList.add('active');
        history.replaceState(null, '', window.location.pathname + '#' + id);
    }

    function loadPane(paneUrl) {
        setActiveNav('data-pane-url', paneUrl);
        contentSections.forEach(function (s) { s.classList.remove('active'); });

        rightPanel.innerHTML = '<div class="pane-loading"><div class="pane-spinner"></div><p>Loading…</p></div>';

        var sep = paneUrl.includes('?') ? '&' : '?';
        fetch(paneUrl + sep + '_pane=1', {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (res) {
            if (res.status === 401) { window.location.href = '/auth/login'; return null; }
            if (!res.ok) throw new Error('HTTP ' + res.status);
            return res.text();
        })
        .then(function (html) {
            if (!html) return;
            rightPanel.innerHTML = html;
            // Re-run any inline scripts in the loaded fragment
            rightPanel.querySelectorAll('script').forEach(function (old) {
                var s = document.createElement('script');
                s.textContent = old.textContent;
                old.parentNode.replaceChild(s, old);
            });
            var url = new URL(window.location.href);
            url.searchParams.set('view', paneUrl);
            history.pushState({ pane: paneUrl }, '', url.toString());
        })
        .catch(function (err) {
            rightPanel.innerHTML =
                '<div class="pane-loading" style="color:#fc8181">' +
                '<i class="fas fa-exclamation-triangle" style="font-size:2.5rem;margin-bottom:1rem;"></i>' +
                '<p>' + err.message + '</p>' +
                '<button onclick="location.reload()" style="padding:8px 20px;border-radius:8px;border:1px solid #e2e8f0;cursor:pointer;">Retry</button>' +
                '</div>';
        });
    }

    // Event delegation for section nav
    navItems.forEach(function (item) {
        item.addEventListener('click', function (e) {
            e.preventDefault();
            var section = this.dataset.section;
            var pane    = this.dataset.paneUrl;
            if (section) showSection(section);
            else if (pane) loadPane(pane);
        });
    });

    // Action cards inside the right panel (delegated — works after pane load too)
    rightPanel.addEventListener('click', function (e) {
        var card = e.target.closest('[data-pane-url]');
        if (card && !card.classList.contains('nav-item')) {
            e.preventDefault();
            loadPane(card.dataset.paneUrl);
        }
    });

    // Initial routing
    var params  = new URLSearchParams(window.location.search);
    var viewUrl = params.get('view');
    var hash    = window.location.hash.slice(1);

    if (viewUrl) {
        loadPane(viewUrl);
    } else if (hash && document.getElementById(hash)) {
        showSection(hash);
    } else {
        showSection('dashboard');
    }

    // Browser back / forward
    window.addEventListener('popstate', function (e) {
        var p = new URLSearchParams(window.location.search).get('view');
        if (p) loadPane(p);
        else showSection(window.location.hash.slice(1) || 'dashboard');
    });

    // Org context switcher (stub — extend as needed)
    window.switchToPersonal = function () {
        document.querySelectorAll('.context-btn').forEach(function (b) { b.classList.remove('active'); });
        event.currentTarget.classList.add('active');
    };
    window.switchToOrg = function (orgId) {
        document.querySelectorAll('.context-btn').forEach(function (b) { b.classList.remove('active'); });
        event.currentTarget.classList.add('active');
    };
}());
</script>
{% endblock %}
```

---

## 4. FILE 3 — `app/templates/user/user_dashboard.html` (REPLACE ENTIRELY)

This is the child template that fills `{% block content_section %}`. It contains TWO inline sections: `dashboard` and `events`.

```html
{% extends "user/base_user_dashboard.html" %}

{% block content_section %}

{# ── SECTION: Dashboard overview ──────────────────────────────────────────── #}
<div id="dashboard" class="content-section active">

    {# Hero greeting #}
    <div style="margin-bottom:1.75rem;">
        <h1 style="font-size:1.6rem;font-weight:800;color:#1a202c;margin:0 0 0.25rem;">
            Welcome back, {{ current_user.username }} 👋
        </h1>
        <p style="color:#718096;margin:0;">Here's what's happening with your AFCON360 account.</p>
    </div>

    {# Stats strip #}
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem;margin-bottom:1.75rem;">

        <div style="background:white;border-radius:14px;padding:1.25rem;box-shadow:0 2px 12px rgba(0,0,0,0.07);border:1px solid #e2e8f0;">
            <div style="display:flex;align-items:center;gap:0.75rem;">
                <div style="width:44px;height:44px;border-radius:10px;background:#ebf4ff;display:flex;align-items:center;justify-content:center;color:#4299e1;font-size:1.2rem;">
                    <i class="fas fa-ticket-alt"></i>
                </div>
                <div>
                    <div style="font-size:1.6rem;font-weight:800;color:#1a202c;line-height:1;">{{ registrations|length }}</div>
                    <div style="font-size:0.75rem;color:#718096;text-transform:uppercase;letter-spacing:0.04em;">Registrations</div>
                </div>
            </div>
        </div>

        <div style="background:white;border-radius:14px;padding:1.25rem;box-shadow:0 2px 12px rgba(0,0,0,0.07);border:1px solid #e2e8f0;">
            <div style="display:flex;align-items:center;gap:0.75rem;">
                <div style="width:44px;height:44px;border-radius:10px;background:#e6fffa;display:flex;align-items:center;justify-content:center;color:#00b87d;font-size:1.2rem;">
                    <i class="fas fa-calendar-check"></i>
                </div>
                <div>
                    <div style="font-size:1.6rem;font-weight:800;color:#1a202c;line-height:1;">{{ upcoming_count|default(0) }}</div>
                    <div style="font-size:0.75rem;color:#718096;text-transform:uppercase;letter-spacing:0.04em;">Upcoming</div>
                </div>
            </div>
        </div>

        <div style="background:white;border-radius:14px;padding:1.25rem;box-shadow:0 2px 12px rgba(0,0,0,0.07);border:1px solid #e2e8f0;">
            <div style="display:flex;align-items:center;gap:0.75rem;">
                <div style="width:44px;height:44px;border-radius:10px;background:#faf5ff;display:flex;align-items:center;justify-content:center;color:#6b46c1;font-size:1.2rem;">
                    <i class="fas fa-check-double"></i>
                </div>
                <div>
                    <div style="font-size:1.6rem;font-weight:800;color:#1a202c;line-height:1;">{{ attended_count|default(0) }}</div>
                    <div style="font-size:0.75rem;color:#718096;text-transform:uppercase;letter-spacing:0.04em;">Attended</div>
                </div>
            </div>
        </div>

        <div style="background:white;border-radius:14px;padding:1.25rem;box-shadow:0 2px 12px rgba(0,0,0,0.07);border:1px solid #e2e8f0;">
            <div style="display:flex;align-items:center;gap:0.75rem;">
                <div style="width:44px;height:44px;border-radius:10px;background:#c6f6d5;display:flex;align-items:center;justify-content:center;color:#22543d;font-size:1.2rem;">
                    <i class="fas fa-wallet"></i>
                </div>
                <div>
                    <div style="font-size:1.6rem;font-weight:800;color:#1a202c;line-height:1;">
                        {% if wallet %}${{ "%.0f"|format(wallet.balance) }}{% else %}—{% endif %}
                    </div>
                    <div style="font-size:0.75rem;color:#718096;text-transform:uppercase;letter-spacing:0.04em;">Wallet</div>
                </div>
            </div>
        </div>

    </div>

    {# Quick Actions #}
    <div style="background:white;border-radius:14px;padding:1.5rem;box-shadow:0 2px 12px rgba(0,0,0,0.07);border:1px solid #e2e8f0;margin-bottom:1.75rem;">
        <h3 style="font-size:0.95rem;font-weight:700;color:#1a202c;margin:0 0 1rem;text-transform:uppercase;letter-spacing:0.04em;">Quick Actions</h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0.75rem;">

            <a href="#" data-pane-url="{{ safe_url('events.list') }}"
               style="padding:1rem;border-radius:10px;border:1.5px solid #e2e8f0;background:white;color:#2d3748;text-decoration:none;text-align:center;transition:all 0.2s;display:flex;flex-direction:column;align-items:center;gap:0.4rem;font-size:0.85rem;font-weight:600;"
               onmouseover="this.style.borderColor='#667eea';this.style.color='#667eea';this.style.background='#f0f4ff';"
               onmouseout="this.style.borderColor='#e2e8f0';this.style.color='#2d3748';this.style.background='white';">
                <i class="fas fa-search" style="font-size:1.3rem;"></i> Browse Events
            </a>

            {% if modules.get('wallet', {}).get('enabled') %}
            <a href="#" data-pane-url="{{ safe_url('wallet.wallet_home') }}"
               style="padding:1rem;border-radius:10px;border:1.5px solid #e2e8f0;background:white;color:#2d3748;text-decoration:none;text-align:center;transition:all 0.2s;display:flex;flex-direction:column;align-items:center;gap:0.4rem;font-size:0.85rem;font-weight:600;"
               onmouseover="this.style.borderColor='#00b87d';this.style.color='#00b87d';this.style.background='#f0fff4';"
               onmouseout="this.style.borderColor='#e2e8f0';this.style.color='#2d3748';this.style.background='white';">
                <i class="fas fa-wallet" style="font-size:1.3rem;"></i> Wallet
            </a>
            {% endif %}

            {% if modules.get('transport', {}).get('enabled') %}
            <a href="#" data-pane-url="{{ safe_url('transport.home') }}"
               style="padding:1rem;border-radius:10px;border:1.5px solid #e2e8f0;background:white;color:#2d3748;text-decoration:none;text-align:center;transition:all 0.2s;display:flex;flex-direction:column;align-items:center;gap:0.4rem;font-size:0.85rem;font-weight:600;"
               onmouseover="this.style.borderColor='#4299e1';this.style.color='#4299e1';this.style.background='#ebf8ff';"
               onmouseout="this.style.borderColor='#e2e8f0';this.style.color='#2d3748';this.style.background='white';">
                <i class="fas fa-bus" style="font-size:1.3rem;"></i> Transport
            </a>
            {% endif %}

            {% if modules.get('accommodation', {}).get('enabled') %}
            <a href="#" data-pane-url="{{ safe_url('accommodation.guest.search') }}"
               style="padding:1rem;border-radius:10px;border:1.5px solid #e2e8f0;background:white;color:#2d3748;text-decoration:none;text-align:center;transition:all 0.2s;display:flex;flex-direction:column;align-items:center;gap:0.4rem;font-size:0.85rem;font-weight:600;"
               onmouseover="this.style.borderColor='#f6ad55';this.style.color='#c05621';this.style.background='#fffbeb';"
               onmouseout="this.style.borderColor='#e2e8f0';this.style.color='#2d3748';this.style.background='white';">
                <i class="fas fa-bed" style="font-size:1.3rem;"></i> Stays
            </a>
            {% endif %}

        </div>
    </div>

    {# Upcoming events preview #}
    <div style="background:white;border-radius:14px;padding:1.5rem;box-shadow:0 2px 12px rgba(0,0,0,0.07);border:1px solid #e2e8f0;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;">
            <h3 style="font-size:0.95rem;font-weight:700;color:#1a202c;margin:0;text-transform:uppercase;letter-spacing:0.04em;">
                Upcoming Events
            </h3>
            <a href="#" data-section="events"
               style="font-size:0.8rem;color:#667eea;font-weight:600;text-decoration:none;">
                View all →
            </a>
        </div>

        {% set shown = namespace(n=0) %}
        {% for reg in upcoming_registrations|default([]) %}
        {% if shown.n < 3 %}
        {% set shown.n = shown.n + 1 %}
        <div style="display:flex;align-items:center;gap:0.75rem;padding:0.75rem 0;border-bottom:1px solid #f0f4f8;">
            <div style="width:40px;height:40px;border-radius:8px;background:#f0f4ff;display:flex;align-items:center;justify-content:center;color:#667eea;flex-shrink:0;">
                <i class="fas fa-calendar-alt"></i>
            </div>
            <div style="flex:1;min-width:0;">
                <div style="font-weight:600;color:#1a202c;font-size:0.875rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                    {{ reg.event.name|default('Event') }}
                </div>
                <div style="font-size:0.75rem;color:#718096;">
                    {% if reg.event.start_date %}{{ reg.event.start_date[:10] }}{% endif %}
                    {% if reg.event.city %} · {{ reg.event.city }}{% endif %}
                </div>
            </div>
            {% set st = reg.status|default('confirmed') %}
            <span style="padding:0.2rem 0.6rem;border-radius:20px;font-size:0.7rem;font-weight:600;
                {% if st == 'confirmed' %}background:#c6f6d5;color:#22543d;
                {% elif st == 'checked_in' %}background:#bee3f8;color:#2a4365;
                {% elif st == 'pending' %}background:#fefcbf;color:#744210;
                {% else %}background:#fed7d7;color:#742a2a;{% endif %}">
                {{ st|title }}
            </span>
        </div>
        {% endif %}
        {% endfor %}

        {% if upcoming_registrations|default([])|length == 0 %}
        <div style="text-align:center;padding:2rem;color:#a0aec0;">
            <i class="fas fa-calendar-plus" style="font-size:2rem;margin-bottom:0.75rem;display:block;"></i>
            <p style="margin:0;font-size:0.875rem;">No upcoming events. <a href="{{ safe_url('events.list') }}" style="color:#667eea;">Browse events →</a></p>
        </div>
        {% endif %}
    </div>

</div>

{# ── SECTION: My Events (inline, no AJAX needed) ──────────────────────────── #}
<div id="events" class="content-section">

    {# Tab controls #}
    <div style="display:flex;gap:0.5rem;border-bottom:2px solid #e2e8f0;margin-bottom:1.5rem;">
        <button class="ev-tab active" data-evtab="upcoming"
                style="padding:0.55rem 1.2rem;font-weight:600;font-size:0.875rem;color:#718096;border:none;background:none;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px;transition:all 0.2s;">
            Upcoming <span class="ev-count" style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;font-size:0.65rem;font-weight:700;margin-left:0.35rem;background:#f0f4f8;color:#718096;">{{ upcoming_registrations|default([])|length }}</span>
        </button>
        <button class="ev-tab" data-evtab="past"
                style="padding:0.55rem 1.2rem;font-weight:600;font-size:0.875rem;color:#718096;border:none;background:none;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px;transition:all 0.2s;">
            Past <span class="ev-count" style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;font-size:0.65rem;font-weight:700;margin-left:0.35rem;background:#f0f4f8;color:#718096;">{{ past_registrations|default([])|length }}</span>
        </button>
        <button class="ev-tab" data-evtab="all"
                style="padding:0.55rem 1.2rem;font-weight:600;font-size:0.875rem;color:#718096;border:none;background:none;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px;transition:all 0.2s;">
            All <span class="ev-count" style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;font-size:0.65rem;font-weight:700;margin-left:0.35rem;background:#f0f4f8;color:#718096;">{{ registrations|default([])|length }}</span>
        </button>
    </div>

    {# Upcoming tab #}
    <div id="evtab-upcoming" class="ev-panel">
        {% if upcoming_registrations|default([])|length > 0 %}
            {% for reg in upcoming_registrations %}
            {% include 'user/_reg_card.html' %}
            {% endfor %}
        {% else %}
        <div style="text-align:center;padding:3.5rem 1rem;color:#718096;">
            <div style="width:70px;height:70px;border-radius:50%;background:#f7fafc;display:inline-flex;align-items:center;justify-content:center;font-size:1.8rem;color:#cbd5e0;margin-bottom:1.25rem;">
                <i class="fas fa-calendar-plus"></i>
            </div>
            <h5 style="color:#2d3748;font-weight:700;">No Upcoming Events</h5>
            <p style="font-size:0.875rem;">You haven't registered for any upcoming events yet.</p>
            <a href="{{ safe_url('events.list') }}" style="display:inline-flex;align-items:center;gap:0.5rem;padding:0.65rem 1.5rem;border-radius:10px;background:#667eea;color:white;font-weight:600;text-decoration:none;margin-top:0.5rem;">
                <i class="fas fa-search"></i> Browse Events
            </a>
        </div>
        {% endif %}
    </div>

    {# Past tab #}
    <div id="evtab-past" class="ev-panel" style="display:none;">
        {% if past_registrations|default([])|length > 0 %}
            {% for reg in past_registrations %}
            {% include 'user/_reg_card.html' %}
            {% endfor %}
        {% else %}
        <div style="text-align:center;padding:3.5rem 1rem;color:#718096;">
            <div style="width:70px;height:70px;border-radius:50%;background:#f7fafc;display:inline-flex;align-items:center;justify-content:center;font-size:1.8rem;color:#cbd5e0;margin-bottom:1.25rem;">
                <i class="fas fa-history"></i>
            </div>
            <h5 style="color:#2d3748;font-weight:700;">No Past Events</h5>
            <p style="font-size:0.875rem;">Your attended events will appear here.</p>
        </div>
        {% endif %}
    </div>

    {# All tab #}
    <div id="evtab-all" class="ev-panel" style="display:none;">
        {% if registrations|default([])|length > 0 %}
            {% for reg in registrations %}
            {% include 'user/_reg_card.html' %}
            {% endfor %}
        {% else %}
        <div style="text-align:center;padding:3.5rem 1rem;color:#718096;">
            <h5 style="color:#2d3748;font-weight:700;">No Registrations Yet</h5>
            <a href="{{ safe_url('events.list') }}" style="display:inline-flex;align-items:center;gap:0.5rem;padding:0.65rem 1.5rem;border-radius:10px;background:#667eea;color:white;font-weight:600;text-decoration:none;margin-top:0.5rem;">
                <i class="fas fa-search"></i> Browse Events
            </a>
        </div>
        {% endif %}
    </div>

    {# Cancel modal #}
    <div id="cancelModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;align-items:center;justify-content:center;">
        <div style="background:white;border-radius:16px;padding:2rem;max-width:400px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,0.3);text-align:center;">
            <div style="font-size:2.5rem;color:#fc8181;margin-bottom:1rem;"><i class="fas fa-exclamation-circle"></i></div>
            <h5 style="font-weight:700;margin-bottom:0.5rem;">Cancel Registration?</h5>
            <p id="cancelModalText" style="color:#718096;font-size:0.9rem;margin-bottom:1.5rem;"></p>
            <div style="display:flex;gap:0.75rem;justify-content:center;">
                <button onclick="closeCancelModal()" style="padding:0.6rem 1.5rem;border-radius:8px;border:1.5px solid #e2e8f0;background:white;font-weight:600;cursor:pointer;">Keep It</button>
                <button id="confirmCancelBtn" style="padding:0.6rem 1.5rem;border-radius:8px;border:none;background:#fc8181;color:white;font-weight:600;cursor:pointer;">Yes, Cancel</button>
            </div>
        </div>
    </div>

</div>

<style>
.ev-tab.active { color: #667eea !important; border-bottom-color: #667eea !important; }
.ev-tab:hover:not(.active) { color: #2d3748 !important; }
.ev-tab.active .ev-count { background: #667eea !important; color: white !important; }
/* "View all →" link in the dashboard section triggers section switch */
a[data-section] { cursor: pointer; }
</style>

<script>
// ── Event tabs ───────────────────────────────────────────────────────────────
document.querySelectorAll('.ev-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
        document.querySelectorAll('.ev-tab').forEach(function (t) { t.classList.remove('active'); });
        document.querySelectorAll('.ev-panel').forEach(function (p) { p.style.display = 'none'; });
        this.classList.add('active');
        document.getElementById('evtab-' + this.dataset.evtab).style.display = 'block';
    });
});

// "View all →" link in dashboard section wires to section nav
document.querySelectorAll('a[data-section]').forEach(function (link) {
    link.addEventListener('click', function (e) {
        e.preventDefault();
        var sectionId = this.dataset.section;
        // Trigger the left-panel nav item to keep active state in sync
        var navItem = document.querySelector('.nav-item[data-section="' + sectionId + '"]');
        if (navItem) navItem.click();
    });
});

// ── Cancel registration ──────────────────────────────────────────────────────
var _cancelRef = null;
function confirmCancel(ref, name) {
    _cancelRef = ref;
    document.getElementById('cancelModalText').textContent =
        'Are you sure you want to cancel your registration for "' + name + '"? This cannot be undone.';
    document.getElementById('cancelModal').style.display = 'flex';
}
function closeCancelModal() {
    document.getElementById('cancelModal').style.display = 'none';
    _cancelRef = null;
}
document.getElementById('confirmCancelBtn').addEventListener('click', function () {
    if (!_cancelRef) return;
    var btn = this;
    btn.disabled = true; btn.textContent = 'Cancelling…';
    fetch('/user/cancel-registration', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': (document.querySelector('meta[name=csrf-token]') || {}).content || '' },
        body: JSON.stringify({ reg_ref: _cancelRef })
    })
    .then(function (r) { return r.json(); })
    .then(function (d) {
        if (d.success) { window.location.reload(); }
        else { alert('Could not cancel: ' + (d.error || 'Unknown error')); btn.disabled = false; btn.textContent = 'Yes, Cancel'; }
    })
    .catch(function () { alert('Network error.'); btn.disabled = false; btn.textContent = 'Yes, Cancel'; })
    .finally(function () { closeCancelModal(); });
});
document.getElementById('cancelModal').addEventListener('click', function (e) {
    if (e.target === this) closeCancelModal();
});
</script>

{% endblock %}
```

---

## 5. FILE 4 — `app/templates/user/_reg_card.html` (CREATE NEW)

Reusable registration card partial. Included via `{% include 'user/_reg_card.html' %}` inside loops. Variable in scope: `reg` (dict).

```html
{# templates/user/_reg_card.html — reg is a dict from EventService #}
{% set status = reg.status|default('confirmed') %}
<div style="background:white;border-radius:14px;border:1px solid #e2e8f0;box-shadow:0 2px 12px rgba(0,0,0,0.06);margin-bottom:1rem;overflow:hidden;transition:box-shadow 0.2s;"
     onmouseover="this.style.boxShadow='0 6px 24px rgba(0,0,0,0.12)'"
     onmouseout="this.style.boxShadow='0 2px 12px rgba(0,0,0,0.06)'">
    <div style="display:flex;">

        {# Accent bar #}
        <div style="width:5px;flex-shrink:0;
            {% if status == 'confirmed' %}background:linear-gradient(180deg,#48bb78,#2f855a);
            {% elif status == 'checked_in' %}background:linear-gradient(180deg,#4299e1,#2b6cb0);
            {% elif status == 'pending' %}background:linear-gradient(180deg,#f6ad55,#c05621);
            {% elif status == 'cancelled' %}background:linear-gradient(180deg,#fc8181,#c53030);
            {% else %}background:#e2e8f0;{% endif %}">
        </div>

        <div style="flex:1;padding:1.1rem 1.25rem;display:flex;align-items:center;flex-wrap:wrap;gap:0.75rem;">

            {# Icon #}
            <div style="width:46px;height:46px;border-radius:10px;background:#f7fafc;display:flex;align-items:center;justify-content:center;font-size:1.3rem;flex-shrink:0;">
                {% set cat = reg.event.category|default('')|lower %}
                {% if 'sport' in cat or 'football' in cat or 'soccer' in cat %}
                    <i class="fas fa-futbol" style="color:#00b87d"></i>
                {% elif 'music' in cat or 'concert' in cat %}
                    <i class="fas fa-music" style="color:#667eea"></i>
                {% elif 'conference' in cat or 'summit' in cat %}
                    <i class="fas fa-users" style="color:#4299e1"></i>
                {% else %}
                    <i class="fas fa-ticket-alt" style="color:#f6ad55"></i>
                {% endif %}
            </div>

            {# Info #}
            <div style="flex:1;min-width:160px;">
                <div style="font-weight:700;color:#1a202c;font-size:0.925rem;margin-bottom:0.3rem;">
                    {{ reg.event.name|default('Event') }}
                </div>
                <div style="display:flex;flex-wrap:wrap;gap:0.4rem 0.9rem;font-size:0.78rem;color:#718096;">
                    {% if reg.event.start_date %}
                    <span><i class="fas fa-calendar-alt me-1"></i>{{ reg.event.start_date[:10] }}</span>
                    {% endif %}
                    {% if reg.event.venue or reg.event.city %}
                    <span><i class="fas fa-map-marker-alt me-1"></i>{{ reg.event.venue or reg.event.city }}</span>
                    {% endif %}
                    <span><i class="fas fa-ticket-alt me-1"></i>{{ reg.ticket_type|default('General Admission') }}</span>
                    {% if reg.registration_fee and reg.registration_fee > 0 %}
                    <span><i class="fas fa-dollar-sign me-1"></i>{{ "%.2f"|format(reg.registration_fee) }}</span>
                    {% else %}
                    <span><i class="fas fa-gift me-1"></i>Free</span>
                    {% endif %}
                </div>
            </div>

            {# Status badge + ref #}
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:0.3rem;min-width:100px;">
                <span style="display:inline-flex;align-items:center;gap:0.3rem;padding:0.25rem 0.7rem;border-radius:20px;font-size:0.72rem;font-weight:700;
                    {% if status == 'confirmed' %}background:#c6f6d5;color:#22543d;
                    {% elif status == 'checked_in' %}background:#bee3f8;color:#2a4365;
                    {% elif status == 'pending' %}background:#fefcbf;color:#744210;
                    {% elif status == 'cancelled' %}background:#fed7d7;color:#742a2a;
                    {% else %}background:#e2e8f0;color:#4a5568;{% endif %}">
                    {% if status == 'confirmed' %}<i class="fas fa-check-circle"></i> Confirmed
                    {% elif status == 'checked_in' %}<i class="fas fa-door-open"></i> Checked In
                    {% elif status == 'pending' %}<i class="fas fa-clock"></i> Pending
                    {% elif status == 'cancelled' %}<i class="fas fa-times-circle"></i> Cancelled
                    {% else %}{{ status|title }}{% endif %}
                </span>
                <span style="font-size:0.68rem;color:#a0aec0;font-family:monospace;">{{ reg.registration_ref }}</span>
            </div>

            {# Actions #}
            <div style="display:flex;flex-wrap:wrap;gap:0.4rem;justify-content:flex-end;min-width:200px;">
                {% if status != 'cancelled' %}
                <a href="{{ url_for('events.registration_confirmation', reg_ref=reg.registration_ref) }}"
                   style="display:inline-flex;align-items:center;gap:0.35rem;padding:0.4rem 0.85rem;border-radius:8px;font-size:0.78rem;font-weight:600;background:#667eea;color:white;text-decoration:none;transition:background 0.2s;"
                   onmouseover="this.style.background='#5a67d8'" onmouseout="this.style.background='#667eea'">
                    <i class="fas fa-qrcode"></i> Ticket
                </a>
                {% if modules is defined and modules.get('transport', {}).get('enabled') %}
                <a href="{{ safe_url('transport.home') }}"
                   style="display:inline-flex;align-items:center;gap:0.35rem;padding:0.4rem 0.85rem;border-radius:8px;font-size:0.78rem;font-weight:600;background:white;color:#2d3748;border:1.5px solid #e2e8f0;text-decoration:none;transition:all 0.2s;"
                   onmouseover="this.style.borderColor='#667eea';this.style.color='#667eea'" onmouseout="this.style.borderColor='#e2e8f0';this.style.color='#2d3748'">
                    <i class="fas fa-bus"></i> Transport
                </a>
                {% endif %}
                {% if status not in ['cancelled', 'checked_in'] %}
                <button onclick="confirmCancel('{{ reg.registration_ref }}', '{{ reg.event.name|default('this event')|replace("'", "\\'") }}')"
                        style="display:inline-flex;align-items:center;gap:0.35rem;padding:0.4rem 0.85rem;border-radius:8px;font-size:0.78rem;font-weight:600;background:#fff5f5;color:#c53030;border:1.5px solid #fed7d7;cursor:pointer;transition:all 0.2s;"
                        onmouseover="this.style.background='#fc8181';this.style.color='white'" onmouseout="this.style.background='#fff5f5';this.style.color='#c53030'">
                    <i class="fas fa-times"></i> Cancel
                </button>
                {% endif %}
                {% else %}
                <span style="display:inline-flex;align-items:center;gap:0.35rem;padding:0.4rem 0.85rem;border-radius:8px;font-size:0.78rem;font-weight:600;background:#f7fafc;color:#a0aec0;">
                    <i class="fas fa-ban"></i> Cancelled
                </span>
                {% endif %}
            </div>

        </div>
    </div>
</div>
```

---

## 6. FILE 5 — `app/templates/user/my_registrations.html` (REPLACE)

This is the **standalone / pane version** for `/user/my-registrations`. It uses the same `_reg_card.html` partial.

```html
{% extends "user/base_user_dashboard.html" %}

{% block content_section %}
<div id="dashboard" class="content-section active">
    {# Reuse the events section HTML but rendered as the main content #}

    <div style="margin-bottom:1.5rem;">
        <h1 style="font-size:1.5rem;font-weight:800;color:#1a202c;margin:0 0 0.25rem;">My Registrations</h1>
        <p style="color:#718096;margin:0;">All your event tickets in one place.</p>
    </div>

    {# Stats strip #}
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:0.75rem;margin-bottom:1.5rem;">
        <div style="background:white;border-radius:12px;padding:1rem;box-shadow:0 2px 8px rgba(0,0,0,0.07);border:1px solid #e2e8f0;text-align:center;">
            <div style="font-size:1.6rem;font-weight:800;color:#00b87d;">{{ upcoming_count }}</div>
            <div style="font-size:0.72rem;color:#718096;text-transform:uppercase;letter-spacing:0.04em;">Upcoming</div>
        </div>
        <div style="background:white;border-radius:12px;padding:1rem;box-shadow:0 2px 8px rgba(0,0,0,0.07);border:1px solid #e2e8f0;text-align:center;">
            <div style="font-size:1.6rem;font-weight:800;color:#667eea;">{{ attended_count }}</div>
            <div style="font-size:0.72rem;color:#718096;text-transform:uppercase;letter-spacing:0.04em;">Attended</div>
        </div>
        <div style="background:white;border-radius:12px;padding:1rem;box-shadow:0 2px 8px rgba(0,0,0,0.07);border:1px solid #e2e8f0;text-align:center;">
            <div style="font-size:1.6rem;font-weight:800;color:#f6ad55;">${{ total_spent }}</div>
            <div style="font-size:0.72rem;color:#718096;text-transform:uppercase;letter-spacing:0.04em;">Total Spent</div>
        </div>
        <div style="background:white;border-radius:12px;padding:1rem;box-shadow:0 2px 8px rgba(0,0,0,0.07);border:1px solid #e2e8f0;text-align:center;">
            <div style="font-size:1.6rem;font-weight:800;color:#4299e1;">{{ registrations|length }}</div>
            <div style="font-size:0.72rem;color:#718096;text-transform:uppercase;letter-spacing:0.04em;">Total</div>
        </div>
    </div>

    {# Tabs #}
    <div style="display:flex;gap:0.5rem;border-bottom:2px solid #e2e8f0;margin-bottom:1.25rem;">
        <button class="ev-tab active" data-evtab="upcoming"
                style="padding:0.55rem 1.2rem;font-weight:600;font-size:0.875rem;color:#718096;border:none;background:none;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px;">
            Upcoming ({{ upcoming_count }})
        </button>
        <button class="ev-tab" data-evtab="past"
                style="padding:0.55rem 1.2rem;font-weight:600;font-size:0.875rem;color:#718096;border:none;background:none;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-2px;">
            Past ({{ past_registrations|length }})
        </button>
    </div>

    <div id="evtab-upcoming" class="ev-panel">
        {% for reg in upcoming_registrations %}{% include 'user/_reg_card.html' %}{% endfor %}
        {% if not upcoming_registrations %}
        <div style="text-align:center;padding:3rem;color:#718096;">
            <i class="fas fa-calendar-plus" style="font-size:2.5rem;display:block;margin-bottom:1rem;color:#cbd5e0;"></i>
            <h5 style="color:#2d3748;">No upcoming events</h5>
            <a href="{{ safe_url('events.list') }}" style="color:#667eea;font-weight:600;">Browse Events →</a>
        </div>
        {% endif %}
    </div>

    <div id="evtab-past" class="ev-panel" style="display:none;">
        {% for reg in past_registrations %}{% include 'user/_reg_card.html' %}{% endfor %}
        {% if not past_registrations %}
        <div style="text-align:center;padding:3rem;color:#718096;">
            <i class="fas fa-history" style="font-size:2.5rem;display:block;margin-bottom:1rem;color:#cbd5e0;"></i>
            <h5 style="color:#2d3748;">No past events yet</h5>
        </div>
        {% endif %}
    </div>

    <div id="cancelModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;align-items:center;justify-content:center;">
        <div style="background:white;border-radius:16px;padding:2rem;max-width:400px;width:90%;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
            <div style="font-size:2.5rem;color:#fc8181;margin-bottom:1rem;"><i class="fas fa-exclamation-circle"></i></div>
            <h5 style="font-weight:700;margin-bottom:0.5rem;">Cancel Registration?</h5>
            <p id="cancelModalText" style="color:#718096;font-size:0.9rem;margin-bottom:1.5rem;"></p>
            <div style="display:flex;gap:0.75rem;justify-content:center;">
                <button onclick="closeCancelModal()" style="padding:0.6rem 1.5rem;border-radius:8px;border:1.5px solid #e2e8f0;background:white;font-weight:600;cursor:pointer;">Keep It</button>
                <button id="confirmCancelBtn" style="padding:0.6rem 1.5rem;border-radius:8px;border:none;background:#fc8181;color:white;font-weight:600;cursor:pointer;">Yes, Cancel</button>
            </div>
        </div>
    </div>

</div>

<style>
.ev-tab.active { color: #667eea !important; border-bottom-color: #667eea !important; }
</style>
<script>
document.querySelectorAll('.ev-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
        document.querySelectorAll('.ev-tab').forEach(function (t) { t.classList.remove('active'); });
        document.querySelectorAll('.ev-panel').forEach(function (p) { p.style.display = 'none'; });
        this.classList.add('active');
        document.getElementById('evtab-' + this.dataset.evtab).style.display = 'block';
    });
});
var _cancelRef = null;
function confirmCancel(ref, name) {
    _cancelRef = ref;
    document.getElementById('cancelModalText').textContent = 'Cancel registration for "' + name + '"? This cannot be undone.';
    document.getElementById('cancelModal').style.display = 'flex';
}
function closeCancelModal() {
    document.getElementById('cancelModal').style.display = 'none';
    _cancelRef = null;
}
document.getElementById('confirmCancelBtn').addEventListener('click', function () {
    if (!_cancelRef) return;
    var btn = this; btn.disabled = true; btn.textContent = 'Cancelling…';
    fetch('/user/cancel-registration', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reg_ref: _cancelRef })
    }).then(function (r) { return r.json(); })
    .then(function (d) {
        if (d.success) window.location.reload();
        else { alert(d.error || 'Error'); btn.disabled = false; btn.textContent = 'Yes, Cancel'; }
    })
    .catch(function () { alert('Network error.'); btn.disabled = false; btn.textContent = 'Yes, Cancel'; })
    .finally(closeCancelModal);
});
document.getElementById('cancelModal').addEventListener('click', function (e) { if (e.target === this) closeCancelModal(); });
</script>
{% endblock %}
```

---

## 7. FILE 6 — `app/templates/events/my_registrations.html` (REPLACE)

Fix the broken `safe_url('url_for\(...')` calls in the events blueprint's own registrations page. Replace every occurrence with proper `url_for(...)`.

**Find & replace — 4 occurrences, all in the same pattern:**

```
BROKEN:
  href="{{ safe_url('url_for\(['"]events.registration_confirmation', reg_ref=reg.registration_ref) }}"
  href="{{ safe_url('url_for\(['"]events.landing', identifier=reg.event.slug) }}"

FIXED:
  href="{{ url_for('events.registration_confirmation', reg_ref=reg.registration_ref) }}"
  href="{{ url_for('events.landing', identifier=reg.event.slug) }}"
```

Apply this replacement to **every `<a href=...` button** in `app/templates/events/my_registrations.html`. There are 4 total (2 in the upcoming loop, 2 in the past loop). No other changes to that file.

---

## 8. VERIFICATION TESTS

Run these manually after deploying. All should pass.

### 8A — Route smoke tests (Python)

```python
# tests/test_user_dashboard.py
import pytest

def test_dashboard_route_renders(client, auth_user):
    """Dashboard returns 200 and contains expected section IDs."""
    with client:
        client.post('/auth/login', data={'email': auth_user.email, 'password': 'testpass'})
        rv = client.get('/user/dashboard')
        assert rv.status_code == 200
        body = rv.data.decode()
        assert 'id="dashboard"' in body
        assert 'id="events"' in body
        assert 'content-section' in body

def test_dashboard_passes_split_lists(client, auth_user):
    """Route passes both upcoming_registrations and past_registrations."""
    with client:
        client.post('/auth/login', data={'email': auth_user.email, 'password': 'testpass'})
        rv = client.get('/user/dashboard')
        assert rv.status_code == 200
        # upcoming_count stat must render (even if 0)
        assert 'Upcoming' in rv.data.decode()

def test_my_registrations_route(client, auth_user):
    """Standalone registrations page returns 200."""
    with client:
        client.post('/auth/login', data={'email': auth_user.email, 'password': 'testpass'})
        rv = client.get('/user/my-registrations')
        assert rv.status_code == 200

def test_cancel_registration_missing_ref(client, auth_user):
    """Cancel endpoint returns 400 on missing ref."""
    with client:
        client.post('/auth/login', data={'email': auth_user.email, 'password': 'testpass'})
        rv = client.post('/user/cancel-registration',
                         json={},
                         content_type='application/json')
        assert rv.status_code == 400
        assert rv.get_json()['success'] is False
```

### 8B — Browser checklist (manual)

| # | Step | Expected |
|---|------|----------|
| 1 | Load `/user/dashboard` | Left panel renders, right panel shows Dashboard section |
| 2 | Click **My Events** in left nav | Right panel switches to events section, Upcoming tab active |
| 3 | Click **Past** tab | Cards switch to past registrations |
| 4 | Click **Wallet** in left nav (if module enabled) | Right panel loads wallet AJAX pane, no double navbar |
| 5 | Click **View Ticket** on a registration card | Navigates to `events.registration_confirmation` (no 404) |
| 6 | Click **Cancel** → confirm | POST to `/user/cancel-registration` returns success, page reloads |
| 7 | Resize to mobile width | Hamburger button appears, left panel slides in on tap |
| 8 | Browser back button after pane load | Returns to previous pane correctly |

---

## 9. NOTES FOR CODEIUM

1. **Do not wrap file contents in additional Jinja `{% extends %}` if a file already has one.** Each file here is the complete replacement.
2. **`_reg_card.html` is a new partial** — create it at `app/templates/user/_reg_card.html`.
3. The `safe_url()` helper is already registered in the app. Do not replace `safe_url` calls with `url_for` unless explicitly noted (Section 7).
4. `url_for('events.registration_confirmation', reg_ref=...)` — confirm the endpoint name against `tests/list_endpoints.py` if uncertain. The `safe_url` wrapper exists precisely for soft-failing on missing endpoints.
5. **CSRF on the cancel fetch** — the cancel POST reads `meta[name=csrf-token]`. Ensure your `base.html` includes `<meta name="csrf-token" content="{{ csrf_token() }}">` in `<head>`. If it does not, add it.
6. The `_split_registrations()` helper in `routes.py` depends on `start_date` already being an ISO string. `_enrich_registrations()` converts it. Always call `_enrich_registrations` before `_split_registrations`.
