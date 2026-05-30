# AFCON 360 - Onboarding Remediation Pass 2
## Strict Fix List for Codeium Agent

**Document Version:** 2.0 (Remediation)
**Date:** 2026-05-05
**Source:** Audit report dated 2026-05-04
**Status of previous pass:** PARTIALLY IMPLEMENTED - 5 blocking defects remain
**Goal of this pass:** Close all 5 defects. Produce evidence. Sign off.

---

## WHAT CODEIUM MUST NOT TOUCH

These things work. Do not refactor them:
- `app/auth/onboarding_routes.py` - routes exist, only specific fixes below
- `app/auth/routes.py` - `_dashboard_for_user()` is already wired
- Blueprint registration in `app/__init__.py`
- `tests/test_onboarding.py` - keep this file, expand it per this doc

---

## THE 5 DEFECTS TO FIX (in priority order)

---

## DEFECT 1 - DUPLICATE /wallet/activate ROUTES (CRITICAL)

**Problem:** There are 3 route handlers for wallet activation in `app/wallet/routes.py`:
- `activate_wallet` (GET + POST) - the correct one from Pass 1
- `wallet_activate` (GET only) - a leftover
- `wallet_activate_submit` (POST only) - a leftover

Flask will crash or behave unpredictably with duplicate URL rules.

**Fix:** Open `app/wallet/routes.py`. Find and DELETE the two legacy handlers. Keep ONLY this one:

```python
@wallet_bp.route("/activate", methods=["GET", "POST"])
@login_required
def activate_wallet():
    """
    User explicitly opts in to the wallet.
    Shows terms → on accept, creates AccountModel.
    Wallet is NEVER auto-created. This is the single canonical activation path.
    """
    from app.wallet.models.ledger import AccountModel, AccountOwnerType
    from app.identity.models.user import User
    from app.extensions import db
    from app.utils.transactions import db_transaction

    # Resolve internal user ID from public_id (UUID)
    db_user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not db_user:
        flash("User not found.", "danger")
        return redirect(url_for("fan.dashboard"))

    # Check if wallet already exists - do not double-create
    existing = AccountModel.query.filter_by(
        user_id=db_user.id,
        owner_type=AccountOwnerType.USER
    ).first()
    if existing:
        flash("You already have a wallet.", "info")
        return redirect(url_for("wallet.wallet_dashboard"))

    if request.method == "POST":
        if not request.form.get("accept_terms"):
            flash("You must accept the wallet terms to continue.", "warning")
            return render_template("wallet/wallet_activate.html")

        with db_transaction("Wallet activation - user opt-in"):
            account = AccountModel(
                user_id=db_user.id,          # internal BIGINT FK - correct
                owner_type=AccountOwnerType.USER,
                currency="UGX",
            )
            db.session.add(account)

        flash("Your wallet has been activated!", "success")
        return redirect(url_for("wallet.wallet_dashboard"))

    return render_template("wallet/wallet_activate.html")
```

**Verification command:**
```bash
grep -n "def activate_wallet\|def wallet_activate\|def wallet_activate_submit\|route.*activate" app/wallet/routes.py
```
**Expected output:** Only one match - `def activate_wallet` at one line number.

---

## DEFECT 2 - IMPLICIT WALLET AUTO-CREATION (CRITICAL)

**Problem:** `get_or_create_account()` is called in fan routes and other places, silently creating wallets for users who never asked for one. This violates the core rule.

**Fix - Step A:** Find all callsites:
```bash
grep -rn "get_or_create_account" app/
```

**Fix - Step B:** For EVERY match in user-facing routes (fan, profile, etc.), replace the auto-create call with a safe read-only lookup:

```python
# BEFORE (auto-creates - WRONG):
account = get_or_create_account(internal_id)

# AFTER (read-only - CORRECT):
from app.wallet.models.ledger import AccountModel, AccountOwnerType
account = AccountModel.query.filter_by(
    user_id=internal_id,
    owner_type=AccountOwnerType.USER
).first()
# account may be None - templates must handle this gracefully
```

**Fix - Step C:** In every template that receives `wallet` or `account`, guard against None:

```html
{% if wallet %}
  <p>Balance: {{ wallet.balance }}</p>
{% else %}
  <a href="{{ url_for('wallet.activate_wallet') }}" class="btn-activate-wallet">
    Activate Wallet
  </a>
{% endif %}
```

**Files most likely to need this fix:**
- `app/fan/routes.py` - `dashboard()`, `wallet()`, `view_fan_profile()`
- `app/profile/routes.py` - `account_overview()`

**Verification command:**
```bash
grep -rn "get_or_create_account" app/fan/ app/profile/ app/wallet/routes.py
```
**Expected output:** Zero matches in fan/ and profile/. Only allowed in the wallet module internals if unavoidable.

---

## DEFECT 3 - ORG SESSION USES INTERNAL ID (SECURITY)

**Problem:** After org onboarding completes, the code does:
```python
session["current_org_id"] = org.id          # WRONG - internal BIGINT
return redirect(url_for("org.dashboard", org_id=org.id))  # WRONG
```

`org.id` is the internal BIGINT primary key. It must never appear in session data visible to the browser or in URLs.

**Fix:** Open `app/auth/onboarding_routes.py`. Find `_commit_organisation_onboarding` and the `organisation_onboarding` route. Change every reference to `org.id` in session and URL context to `org.org_id`:

```python
# In _commit_organisation_onboarding - return the org object (already done)
return org

# In organisation_onboarding, after the commit:
org = _commit_organisation_onboarding(current_user, data)
session.pop("org_onboarding", None)
session.pop("org_onboarding_type", None)

# FIX: use org.org_id (UUID string) everywhere externally visible
session["current_context"] = "organization"
session["current_org_id"] = org.org_id      # ← UUID string, NOT org.id
session["current_org_name"] = org.legal_name

flash(f"Organisation '{org.legal_name}' registered successfully!", "success")
return redirect(url_for("org.dashboard", org_id=org.org_id))  # ← UUID
```

**Also fix** any place in `app/auth/routes.py` or `app/__init__.py` that reads `session["current_org_id"]` and passes it to a DB query - those queries must look up the org by `org_id` (UUID), not by `id` (BIGINT):

```python
# CORRECT pattern wherever org_id from session is used:
from app.identity.models.organisation import Organisation
org = Organisation.query.filter_by(org_id=session["current_org_id"]).first()
# Then use org.id internally for FK operations
```

**Verification command:**
```bash
grep -n "current_org_id.*org\.id\|org_id=org\.id" app/auth/onboarding_routes.py app/auth/routes.py
```
**Expected output:** Zero matches.

---

## DEFECT 4 - TEMPLATE DEPTH (UX / PRODUCTION QUALITY)

**Problem:** All wizard step templates (driver_step1/2/3, organisation_step1/2, host_step1/2, event_organiser) are single-line placeholders. The `choose.html` exists but lacks the visual grouping required by spec.

### 4A - Fix `choose.html` grouping

The cards must be split into 3 explicit visual sections:

```html
<!-- templates/onboarding/choose.html -->
{% extends "base.html" %}

{% block title %}What brings you here? - AFCON 360{% endblock %}

{% block content %}
<div class="onboarding-root">

  <!-- ── HEADER ─────────────────────────────────────────── -->
  <header class="ob-header">
    <div class="ob-logo">AFCON <span>360</span></div>
    <h1 class="ob-title">What brings you to AFCON&nbsp;360?</h1>
    <p class="ob-sub">Choose your path. You can always add more later.</p>
  </header>

  <!-- ── SECTION 1: I WANT TO USE SERVICES ─────────────── -->
  <section class="ob-section">
    <div class="ob-section-label">
      <span class="ob-section-icon">👤</span>
      I want to <strong>use services</strong>
    </div>
    <div class="ob-grid ob-grid--2">

      <a href="{{ url_for('onboarding.fan_onboarding') }}" class="ob-card ob-card--quick">
        <div class="ob-card-icon">🎟️</div>
        <div class="ob-card-body">
          <h3>Fan &amp; Explorer</h3>
          <p>Book events, find accommodation and arrange transport as an individual. No business details needed.</p>
          <ul class="ob-what-you-get">
            <li>Browse &amp; book events</li>
            <li>Reserve accommodation</li>
            <li>Book transport</li>
            <li>Activate wallet (optional)</li>
          </ul>
        </div>
        <div class="ob-card-footer">
          <span class="ob-kyc-badge ob-kyc--1">✓ Phone verified - ready now</span>
          <span class="ob-cta">Get Started →</span>
        </div>
      </a>

    </div>
  </section>

  <!-- ── SECTION 2: I WANT TO OFFER SERVICES ───────────── -->
  <section class="ob-section">
    <div class="ob-section-label">
      <span class="ob-section-icon">🛠️</span>
      I want to <strong>offer services</strong>
    </div>
    <div class="ob-grid ob-grid--3">

      <a href="{{ url_for('onboarding.driver_onboarding') }}" class="ob-card">
        <div class="ob-card-icon">🚗</div>
        <div class="ob-card-body">
          <h3>Independent Driver</h3>
          <p>Earn by offering transport. Register your licence and one vehicle. Get matched with passengers booking trips.</p>
          <ul class="ob-what-you-get">
            <li>Receive trip requests</li>
            <li>Set your own schedule</li>
            <li>Get paid per trip</li>
          </ul>
          <div class="ob-requirements">
            <strong>You will need:</strong>
            <span>National ID · Driver's licence · Vehicle registration + insurance</span>
          </div>
        </div>
        <div class="ob-card-footer">
          <span class="ob-kyc-badge ob-kyc--2">Requires ID verification</span>
          <span class="ob-cta">Become a Driver →</span>
        </div>
      </a>

      <a href="{{ url_for('onboarding.host_onboarding') }}" class="ob-card">
        <div class="ob-card-icon">🏠</div>
        <div class="ob-card-body">
          <h3>Accommodation Host</h3>
          <p>List your home, apartment or spare rooms for short-term guests. Set your own pricing and availability.</p>
          <ul class="ob-what-you-get">
            <li>List 1 or more rooms</li>
            <li>Manage availability calendar</li>
            <li>Receive bookings &amp; payments</li>
          </ul>
          <div class="ob-requirements">
            <strong>You will need:</strong>
            <span>National ID · Proof of property ownership or tenancy</span>
          </div>
        </div>
        <div class="ob-card-footer">
          <span class="ob-kyc-badge ob-kyc--2">Requires ID verification</span>
          <span class="ob-cta">List My Property →</span>
        </div>
      </a>

      <a href="{{ url_for('onboarding.event_organiser_onboarding') }}" class="ob-card">
        <div class="ob-card-icon">🎪</div>
        <div class="ob-card-body">
          <h3>Event Organiser</h3>
          <p>Create and publish events. Sell tickets, manage guest lists and coordinate venues - as an individual or company.</p>
          <ul class="ob-what-you-get">
            <li>Create &amp; publish events</li>
            <li>Sell tickets online</li>
            <li>Manage attendees &amp; check-in</li>
          </ul>
          <div class="ob-requirements">
            <strong>You will need:</strong>
            <span>National ID (individual) or Business registration (company)</span>
          </div>
        </div>
        <div class="ob-card-footer">
          <span class="ob-kyc-badge ob-kyc--2">Requires ID verification</span>
          <span class="ob-cta">Start Organising →</span>
        </div>
      </a>

    </div>
  </section>

  <!-- ── SECTION 3: I REPRESENT AN ORGANISATION ────────── -->
  <section class="ob-section">
    <div class="ob-section-label">
      <span class="ob-section-icon">🏢</span>
      I represent an <strong>organisation</strong>
    </div>
    <div class="ob-grid ob-grid--3">

      <a href="{{ url_for('onboarding.organisation_onboarding', type='transport') }}" class="ob-card ob-card--org">
        <div class="ob-card-icon">🚌</div>
        <div class="ob-card-body">
          <h3>Transport Company / Fleet</h3>
          <p>Register your company. Add multiple vehicles and drivers. Manage bookings and dispatching at scale.</p>
          <ul class="ob-what-you-get">
            <li>Register as a legal entity</li>
            <li>Add unlimited drivers &amp; vehicles</li>
            <li>Manage dispatch &amp; routes</li>
            <li>Org wallet &amp; payouts</li>
          </ul>
          <div class="ob-requirements">
            <strong>You will need:</strong>
            <span>Business registration · Fleet documents · Contact details</span>
          </div>
        </div>
        <div class="ob-card-footer">
          <span class="ob-kyc-badge ob-kyc--3">Business KYB required</span>
          <span class="ob-cta">Register Fleet →</span>
        </div>
      </a>

      <a href="{{ url_for('onboarding.organisation_onboarding', type='accommodation') }}" class="ob-card ob-card--org">
        <div class="ob-card-icon">🏨</div>
        <div class="ob-card-body">
          <h3>Hotel / Lodge / Guesthouse</h3>
          <p>Register your establishment. Manage multiple room types, staff access, bookings and billing centrally.</p>
          <ul class="ob-what-you-get">
            <li>Register as a legal entity</li>
            <li>Manage multiple room types</li>
            <li>Staff login &amp; role management</li>
            <li>Central billing &amp; payouts</li>
          </ul>
          <div class="ob-requirements">
            <strong>You will need:</strong>
            <span>Business registration · Operating licence · Contact details</span>
          </div>
        </div>
        <div class="ob-card-footer">
          <span class="ob-kyc-badge ob-kyc--3">Business KYB required</span>
          <span class="ob-cta">Register Establishment →</span>
        </div>
      </a>

      <a href="{{ url_for('onboarding.organisation_onboarding', type='consumer') }}" class="ob-card ob-card--org">
        <div class="ob-card-icon">🏢</div>
        <div class="ob-card-body">
          <h3>Organisation (Consumer)</h3>
          <p>Book transport, accommodation and events on behalf of your company. Manage team access, central invoicing and bulk bookings.</p>
          <ul class="ob-what-you-get">
            <li>Team member management</li>
            <li>Central org wallet</li>
            <li>Bulk event &amp; transport bookings</li>
            <li>Reporting &amp; audit trail</li>
          </ul>
          <div class="ob-requirements">
            <strong>You will need:</strong>
            <span>Business registration · Contact details</span>
          </div>
        </div>
        <div class="ob-card-footer">
          <span class="ob-kyc-badge ob-kyc--2">Business registration required</span>
          <span class="ob-cta">Register Organisation →</span>
        </div>
      </a>

    </div>
  </section>

  <!-- ── FOOTER ESCAPE HATCH ────────────────────────────── -->
  <footer class="ob-footer">
    <p>Not sure yet? <a href="{{ url_for('onboarding.fan_onboarding') }}">Start as a Fan</a> - you can upgrade your account at any time.</p>
    <p class="ob-footer-note">Already have an account? <a href="{{ url_for('auth.logout') }}">Sign out</a></p>
  </footer>

</div>

<style>
/* ── CSS VARIABLES ───────────────────────────────────────── */
:root {
  --ob-bg:        #080c10;
  --ob-surface:   #0f1419;
  --ob-border:    #1e2830;
  --ob-accent:    #00c2ff;
  --ob-accent2:   #00ff9d;
  --ob-text:      #e8edf2;
  --ob-muted:     #7a8a9a;
  --ob-org:       #f5a623;
  --ob-radius:    14px;
  --ob-font-head: 'Syne', sans-serif;
  --ob-font-body: 'DM Sans', sans-serif;
}

@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500&display=swap');

/* ── ROOT ───────────────────────────────────────────────── */
.onboarding-root {
  min-height: 100vh;
  background: var(--ob-bg);
  color: var(--ob-text);
  font-family: var(--ob-font-body);
  padding: 0 0 80px;
}

/* ── HEADER ─────────────────────────────────────────────── */
.ob-header {
  text-align: center;
  padding: 64px 24px 48px;
  position: relative;
}
.ob-header::after {
  content: '';
  display: block;
  width: 60px;
  height: 3px;
  background: var(--ob-accent);
  margin: 24px auto 0;
}
.ob-logo {
  font-family: var(--ob-font-head);
  font-size: 13px;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: var(--ob-accent);
  margin-bottom: 24px;
}
.ob-logo span { color: var(--ob-accent2); }
.ob-title {
  font-family: var(--ob-font-head);
  font-size: clamp(28px, 5vw, 52px);
  font-weight: 800;
  line-height: 1.1;
  margin: 0 0 16px;
  letter-spacing: -0.02em;
}
.ob-sub {
  font-size: 18px;
  color: var(--ob-muted);
  margin: 0;
}

/* ── SECTIONS ───────────────────────────────────────────── */
.ob-section {
  max-width: 1200px;
  margin: 0 auto 56px;
  padding: 0 24px;
}
.ob-section-label {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ob-muted);
  border-bottom: 1px solid var(--ob-border);
  padding-bottom: 14px;
  margin-bottom: 28px;
}
.ob-section-label strong { color: var(--ob-text); }
.ob-section-icon { font-size: 18px; }

/* ── GRIDS ──────────────────────────────────────────────── */
.ob-grid {
  display: grid;
  gap: 20px;
}
.ob-grid--2 { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
.ob-grid--3 { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }

/* ── CARDS ──────────────────────────────────────────────── */
.ob-card {
  display: flex;
  flex-direction: column;
  background: var(--ob-surface);
  border: 1px solid var(--ob-border);
  border-radius: var(--ob-radius);
  padding: 28px;
  text-decoration: none;
  color: var(--ob-text);
  transition: border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
  position: relative;
  overflow: hidden;
}
.ob-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(0,194,255,0.04) 0%, transparent 60%);
  opacity: 0;
  transition: opacity 0.2s ease;
}
.ob-card:hover {
  border-color: var(--ob-accent);
  transform: translateY(-4px);
  box-shadow: 0 12px 40px rgba(0,194,255,0.12);
}
.ob-card:hover::before { opacity: 1; }

.ob-card--quick { border-color: rgba(0,255,157,0.2); }
.ob-card--quick:hover { border-color: var(--ob-accent2); box-shadow: 0 12px 40px rgba(0,255,157,0.12); }

.ob-card--org { border-color: rgba(245,166,35,0.15); }
.ob-card--org:hover { border-color: var(--ob-org); box-shadow: 0 12px 40px rgba(245,166,35,0.1); }

.ob-card-icon {
  font-size: 36px;
  margin-bottom: 16px;
  line-height: 1;
}
.ob-card-body { flex: 1; }
.ob-card-body h3 {
  font-family: var(--ob-font-head);
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 10px;
}
.ob-card-body p {
  font-size: 14px;
  color: var(--ob-muted);
  line-height: 1.6;
  margin: 0 0 16px;
}

/* ── WHAT YOU GET LIST ──────────────────────────────────── */
.ob-what-you-get {
  list-style: none;
  padding: 0;
  margin: 0 0 16px;
}
.ob-what-you-get li {
  font-size: 13px;
  color: var(--ob-text);
  padding: 4px 0;
  padding-left: 20px;
  position: relative;
}
.ob-what-you-get li::before {
  content: '→';
  position: absolute;
  left: 0;
  color: var(--ob-accent);
  font-size: 12px;
}
.ob-card--quick .ob-what-you-get li::before { color: var(--ob-accent2); }
.ob-card--org .ob-what-you-get li::before { color: var(--ob-org); }

/* ── REQUIREMENTS BOX ───────────────────────────────────── */
.ob-requirements {
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--ob-border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-top: 4px;
}
.ob-requirements strong {
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ob-muted);
  margin-bottom: 4px;
}
.ob-requirements span {
  font-size: 13px;
  color: var(--ob-text);
  line-height: 1.5;
}

/* ── CARD FOOTER ────────────────────────────────────────── */
.ob-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--ob-border);
  flex-wrap: wrap;
  gap: 8px;
}

/* ── KYC BADGES ─────────────────────────────────────────── */
.ob-kyc-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 20px;
  letter-spacing: 0.04em;
}
.ob-kyc--1 {
  background: rgba(0,255,157,0.12);
  color: var(--ob-accent2);
  border: 1px solid rgba(0,255,157,0.25);
}
.ob-kyc--2 {
  background: rgba(0,194,255,0.1);
  color: var(--ob-accent);
  border: 1px solid rgba(0,194,255,0.2);
}
.ob-kyc--3 {
  background: rgba(245,166,35,0.1);
  color: var(--ob-org);
  border: 1px solid rgba(245,166,35,0.2);
}

/* ── CTA ARROW ──────────────────────────────────────────── */
.ob-cta {
  font-size: 13px;
  font-weight: 500;
  color: var(--ob-accent);
  transition: transform 0.15s ease;
}
.ob-card--quick .ob-cta { color: var(--ob-accent2); }
.ob-card--org .ob-cta { color: var(--ob-org); }
.ob-card:hover .ob-cta { transform: translateX(4px); }

/* ── FOOTER ─────────────────────────────────────────────── */
.ob-footer {
  text-align: center;
  padding: 40px 24px 0;
  color: var(--ob-muted);
  font-size: 14px;
}
.ob-footer a { color: var(--ob-accent); text-decoration: none; }
.ob-footer a:hover { text-decoration: underline; }
.ob-footer-note { margin-top: 8px; font-size: 12px; }

/* ── ENTRANCE ANIMATION ─────────────────────────────────── */
.ob-section { animation: fadeUp 0.4s ease both; }
.ob-section:nth-child(2) { animation-delay: 0.05s; }
.ob-section:nth-child(3) { animation-delay: 0.1s; }
.ob-section:nth-child(4) { animation-delay: 0.15s; }
.ob-card { animation: fadeUp 0.4s ease both; }
.ob-card:nth-child(2) { animation-delay: 0.06s; }
.ob-card:nth-child(3) { animation-delay: 0.12s; }

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── MOBILE ─────────────────────────────────────────────── */
@media (max-width: 640px) {
  .ob-grid--2, .ob-grid--3 { grid-template-columns: 1fr; }
  .ob-card { padding: 20px; }
  .ob-card-footer { flex-direction: column; align-items: flex-start; }
}
</style>
{% endblock %}
```

### 4B - Fix `_progress_bar.html`

Replace the single-line placeholder with this reusable component:

```html
<!-- templates/onboarding/_progress_bar.html -->
<!-- Usage: {% include 'onboarding/_progress_bar.html' %} with variables: step_current, step_total, step_labels -->
<div class="ob-progress">
  {% for i in range(1, step_total + 1) %}
    <div class="ob-progress-step {% if i < step_current %}ob-step--done{% elif i == step_current %}ob-step--active{% endif %}">
      <div class="ob-step-dot">
        {% if i < step_current %}✓{% else %}{{ i }}{% endif %}
      </div>
      {% if step_labels is defined and step_labels[i-1] is defined %}
        <span class="ob-step-label">{{ step_labels[i-1] }}</span>
      {% endif %}
    </div>
    {% if not loop.last %}
      <div class="ob-progress-line {% if i < step_current %}ob-line--done{% endif %}"></div>
    {% endif %}
  {% endfor %}
</div>

<style>
.ob-progress {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 24px 0 32px;
}
.ob-progress-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.ob-step-dot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #1e2830;
  border: 2px solid #2a3540;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: #7a8a9a;
  transition: all 0.2s ease;
}
.ob-step--done .ob-step-dot {
  background: #003d2a;
  border-color: #00ff9d;
  color: #00ff9d;
}
.ob-step--active .ob-step-dot {
  background: #001f33;
  border-color: #00c2ff;
  color: #00c2ff;
  box-shadow: 0 0 12px rgba(0,194,255,0.3);
}
.ob-step-label {
  font-size: 11px;
  color: #7a8a9a;
  white-space: nowrap;
}
.ob-step--active .ob-step-label { color: #00c2ff; }
.ob-step--done .ob-step-label { color: #00ff9d; }
.ob-progress-line {
  flex: 1;
  height: 2px;
  background: #1e2830;
  min-width: 40px;
  max-width: 80px;
  margin-bottom: 18px;
}
.ob-line--done { background: #00ff9d; }
</style>
```

### 4C - Fix all wizard step templates

Each step template must follow this exact pattern. The forms are functional, validated, and styled. Build all 9 remaining templates using this pattern - do not leave any as placeholders:

```html
<!-- PATTERN - copy and adapt for each step -->
<!-- templates/onboarding/driver_step1.html -->
{% extends "base.html" %}
{% block title %}Become a Driver - Step 1 of 3{% endblock %}
{% block content %}

{% set step_current = 1 %}
{% set step_total = 3 %}
{% set step_labels = ["Your Details", "Licence", "Vehicle"] %}

<div class="onboarding-root ob-wizard">
  <div class="ob-wizard-inner">

    <a href="{{ url_for('onboarding.choose') }}" class="ob-back">← Back to paths</a>
    <h2 class="ob-wizard-title">Become a Driver</h2>
    <p class="ob-wizard-sub">Tell us about yourself. Your details will be verified before you can accept trips.</p>

    {% include 'onboarding/_progress_bar.html' %}

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for category, message in messages %}
        <div class="ob-alert ob-alert--{{ category }}">{{ message }}</div>
      {% endfor %}
    {% endwith %}

    <form method="POST" action="{{ url_for('onboarding.driver_onboarding', step=1) }}" class="ob-form" novalidate>
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

      <div class="ob-field">
        <label for="full_name">Full Name <span class="ob-req">*</span></label>
        <input type="text" id="full_name" name="full_name"
               value="{{ data.get('step1', {}).get('full_name', '') }}"
               placeholder="As it appears on your national ID"
               required maxlength="128">
        <span class="ob-hint">Must match your ID document exactly</span>
      </div>

      <div class="ob-field">
        <label for="date_of_birth">Date of Birth <span class="ob-req">*</span></label>
        <input type="date" id="date_of_birth" name="date_of_birth"
               value="{{ data.get('step1', {}).get('date_of_birth', '') }}"
               required>
      </div>

      <div class="ob-field">
        <label for="nationality">Nationality <span class="ob-req">*</span></label>
        <input type="text" id="nationality" name="nationality"
               value="{{ data.get('step1', {}).get('nationality', '') }}"
               placeholder="e.g. Ugandan" required maxlength="64">
      </div>

      <div class="ob-field">
        <label for="national_id_number">National ID Number <span class="ob-req">*</span></label>
        <input type="text" id="national_id_number" name="national_id_number"
               value="{{ data.get('step1', {}).get('national_id_number', '') }}"
               placeholder="e.g. CM90100006HNBA" required maxlength="64">
        <span class="ob-hint">This will be verified against NIRA records</span>
      </div>

      <div class="ob-form-footer">
        <button type="submit" class="ob-btn ob-btn--primary">
          Continue to Licence Details →
        </button>
      </div>
    </form>

  </div>
</div>

{% include 'onboarding/_wizard_styles.html' %}
{% endblock %}
```

**Create `templates/onboarding/_wizard_styles.html`** - shared CSS for all wizard steps:

```html
<!-- templates/onboarding/_wizard_styles.html -->
<style>
.ob-wizard { padding: 40px 24px 80px; }
.ob-wizard-inner {
  max-width: 560px;
  margin: 0 auto;
}
.ob-back {
  display: inline-block;
  font-size: 13px;
  color: #7a8a9a;
  text-decoration: none;
  margin-bottom: 24px;
}
.ob-back:hover { color: #00c2ff; }
.ob-wizard-title {
  font-family: 'Syne', sans-serif;
  font-size: 28px;
  font-weight: 800;
  margin: 0 0 8px;
  color: #e8edf2;
}
.ob-wizard-sub {
  color: #7a8a9a;
  margin: 0 0 8px;
  font-size: 15px;
  line-height: 1.5;
}
.ob-alert {
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 14px;
}
.ob-alert--danger  { background: rgba(255,60,60,0.1); color: #ff6b6b; border: 1px solid rgba(255,60,60,0.2); }
.ob-alert--success { background: rgba(0,255,157,0.1); color: #00ff9d; border: 1px solid rgba(0,255,157,0.2); }
.ob-alert--warning { background: rgba(245,166,35,0.1); color: #f5a623; border: 1px solid rgba(245,166,35,0.2); }
.ob-form { margin-top: 24px; }
.ob-field { margin-bottom: 20px; }
.ob-field label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #b0bec8;
  margin-bottom: 6px;
  letter-spacing: 0.02em;
}
.ob-req { color: #ff6b6b; }
.ob-field input, .ob-field select, .ob-field textarea {
  width: 100%;
  background: #0f1419;
  border: 1px solid #1e2830;
  border-radius: 8px;
  padding: 12px 14px;
  color: #e8edf2;
  font-size: 15px;
  font-family: 'DM Sans', sans-serif;
  transition: border-color 0.15s ease;
  box-sizing: border-box;
}
.ob-field input:focus, .ob-field select:focus, .ob-field textarea:focus {
  outline: none;
  border-color: #00c2ff;
  box-shadow: 0 0 0 3px rgba(0,194,255,0.08);
}
.ob-field input::placeholder { color: #3a4a5a; }
.ob-hint {
  display: block;
  font-size: 12px;
  color: #7a8a9a;
  margin-top: 5px;
}
.ob-form-footer {
  padding-top: 12px;
  border-top: 1px solid #1e2830;
  margin-top: 12px;
}
.ob-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 14px 28px;
  border-radius: 8px;
  border: none;
  font-size: 15px;
  font-weight: 600;
  font-family: 'DM Sans', sans-serif;
  cursor: pointer;
  transition: all 0.15s ease;
  text-decoration: none;
}
.ob-btn--primary {
  background: #00c2ff;
  color: #080c10;
}
.ob-btn--primary:hover {
  background: #00d4ff;
  box-shadow: 0 4px 20px rgba(0,194,255,0.3);
}
.ob-btn--secondary {
  background: transparent;
  color: #7a8a9a;
  border: 1px solid #1e2830;
}
.ob-btn--secondary:hover { border-color: #7a8a9a; color: #e8edf2; }
</style>
```

**Now build all remaining step templates using the same pattern:**

| Template | Wizard Title | Steps | Fields |
|---|---|---|---|
| `driver_step2.html` | Become a Driver | 2 of 3 - Licence | licence_number, licence_expiry (date), licence_class (select: A/B/C/D), file: licence_document |
| `driver_step3.html` | Become a Driver | 3 of 3 - Your Vehicle | vehicle_make, vehicle_model, vehicle_year (number 1990-2026), plate_number, vehicle_type (select: Sedan/SUV/Minibus/Truck), file: insurance_document |
| `organisation_step1.html` | Register Organisation | 1 of 2 - Details | legal_name, country (select), registration_no, tax_id, contact_email, contact_phone, website |
| `organisation_step2.html` | Register Organisation | 2 of 2 - Confirm | Show summary of step 1 data (read-only), file: registration_document (optional), checkbox: confirm accuracy |
| `host_step1.html` | List Your Property | 1 of 2 - Your Identity | full_name, national_id_number, file: id_document, file: proof_of_address |
| `host_step2.html` | List Your Property | 2 of 2 - Property Details | property_name, address, city, country, property_type (select: Apartment/House/Room/Villa), number_of_rooms (number) |
| `event_organiser.html` | Host Events | 1 of 1 | full_name, organiser_type (radio: Individual/Company), company_name (shown if Company), contact_email |
| `fan.html` | Get Started | 1 of 1 | full_name, city, country (select) |

---

## DEFECT 5 - MISSING TESTS EVIDENCE

**Problem:** The audit could not run tests. Tests must be run and evidence must be pasted in the report.

**Fix - Step A:** Verify `tests/test_onboarding.py` exists. If not, create it from Phase 7 of the original guide.

**Fix - Step B:** Run and capture output:
```bash
flask seed-all
pytest tests/test_onboarding.py -v --tb=short 2>&1 | tee test_output.txt
cat test_output.txt
```

**Fix - Step C:** Also run:
```bash
flask routes | grep onboarding
flask routes | grep activate
```

---

## VERIFICATION CHECKLIST (Codeium must complete all items)

Run each command. Paste the output in your report.

```
COMMAND 1 - No duplicate wallet routes:
$ grep -n "def activate_wallet\|def wallet_activate\|def wallet_activate_submit" app/wallet/routes.py
EXPECTED: Exactly 1 line: "def activate_wallet"
ACTUAL: ___________

COMMAND 2 - No auto-create in fan routes:
$ grep -n "get_or_create_account" app/fan/routes.py app/profile/routes.py
EXPECTED: 0 matches
ACTUAL: ___________

COMMAND 3 - Org session uses UUID not BIGINT:
$ grep -n "current_org_id.*org\.id\b" app/auth/onboarding_routes.py
EXPECTED: 0 matches
ACTUAL: ___________

COMMAND 4 - All template files exist:
$ ls templates/onboarding/
EXPECTED: choose.html, fan.html, driver_step1.html, driver_step2.html,
          driver_step3.html, organisation_step1.html, organisation_step2.html,
          host_step1.html, host_step2.html, event_organiser.html,
          _progress_bar.html, _wizard_styles.html
ACTUAL: ___________

COMMAND 5 - Onboarding routes registered:
$ flask routes | grep onboarding
EXPECTED: 6+ lines showing all onboarding routes
ACTUAL: ___________

COMMAND 6 - Wallet activate route:
$ flask routes | grep activate
EXPECTED: 1 line - /wallet/activate
ACTUAL: ___________

COMMAND 7 - Test results:
$ pytest tests/test_onboarding.py -v --tb=short
EXPECTED: All tests passed
ACTUAL: ___________

COMMAND 8 - Role seed:
$ flask seed-all
EXPECTED: "Seed complete" with role count > 0
ACTUAL: ___________
```

---

## FINAL REPORT TEMPLATE (Codeium fills this)

```
=== REMEDIATION PASS 2 REPORT ===
Date: ___________

DEFECT 1 - Duplicate wallet routes:
Status: FIXED / NOT FIXED
Evidence (command output): ___________

DEFECT 2 - Auto-create wallet removed:
Status: FIXED / NOT FIXED
Files changed: ___________
Evidence (command output): ___________

DEFECT 3 - Org session uses UUID:
Status: FIXED / NOT FIXED
Evidence (command output): ___________

DEFECT 4 - Templates production-grade:
Status: FIXED / NOT FIXED
Files created/updated: ___________
Visual note (any rendering issues): ___________

DEFECT 5 - Tests run with evidence:
Status: FIXED / NOT FIXED
Test results: Total ___ / Passed ___ / Failed ___
Failed test names: ___________

OVERALL STATUS: SPEC-COMPLETE / STILL INCOMPLETE
Remaining issues (if any): ___________
```
