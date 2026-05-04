# AFCON 360 — User Onboarding & Role Selection System
## Complete Implementation Guide for Codeium Agent

**Document Version:** 1.0  
**Date:** 2026-05-04  
**Author:** Architecture Review  
**Target Agent:** Codeium  
**Codebase:** Flask + SQLAlchemy + PostgreSQL + Redis

---

## EXECUTIVE SUMMARY

Build a post-registration onboarding system where every user signs up once (username + email/phone + OTP), then selects what they want to do on the platform. Each selection triggers a specific onboarding wizard. Account/profile records are created **only upon completion** of the relevant onboarding wizard. Wallet is always opt-in, never auto-created.

---

## SYSTEM ARCHITECTURE OVERVIEW

```
SIGNUP (username + email/phone)
    ↓
OTP VERIFICATION
    ↓
User record created (role: "fan" by default)
UserProfile created (profile_completed = False)
    ↓
POST-VERIFICATION LANDING PAGE  ← BUILD THIS FIRST
    ↓ (user selects their path)
    ├── FAN / CONSUMER        → minimal profile form → fan dashboard
    ├── DRIVER                → driver onboarding wizard → transport dashboard
    ├── VEHICLE FLEET         → fleet onboarding → org transport dashboard
    ├── ACCOMMODATION HOST    → host onboarding wizard → host dashboard
    ├── HOTEL / LODGE         → hotel org onboarding → hotel dashboard
    ├── EVENT ORGANISER       → organiser onboarding → events dashboard
    └── SERVICE CONSUMER ORG  → org onboarding (no services) → org dashboard
    
WALLET (any time, any role, user-initiated)
    ↓
Terms acceptance → AccountModel created → KYC-gated limits
```

---

## CORE RULES (DO NOT VIOLATE)

1. **Never expose `user.id` (BIGINT)** — always use `user.public_id` (UUID) in URLs, sessions, templates, logs
2. **`get_profile_by_user()`** always receives `user.public_id` string, never an integer
3. **Wallet is never auto-created** — only on explicit user request with terms acceptance
4. **All role assignments go through `assign_global_role()` or `assign_org_role()`** in `app/auth/roles.py`
5. **Every DB mutation must be wrapped in `db_transaction()`** from `app/utils/transactions.py`
6. **Run `flask seed-roles` before testing** — roles must exist in DB before assignment
7. **OTP verification state** is tracked via `session["pending_onboarding"]` — clear it after use
8. **Org creation** always creates an `Organisation` record + `OrganisationMember` record + assigns `org_owner` role
9. **KYC tier** is calculated dynamically by `calculate_kyc_tier(user.id)` — never store tier as a static value in the user record
10. **Profile completion** is calculated by `profile.get_completion_percentage()` — never hardcode it

---

## PHASE 1 — POST-VERIFICATION LANDING PAGE

### 1.1 Route to Create

**File:** `app/auth/onboarding_routes.py` (NEW FILE)

```python
# app/auth/onboarding_routes.py
from flask import Blueprint, render_template, redirect, url_for, session, flash
from flask_login import login_required, current_user

onboarding_bp = Blueprint("onboarding", __name__, url_prefix="/onboarding")

@onboarding_bp.route("/choose", methods=["GET"])
@login_required
def choose():
    """
    Post-verification landing page.
    Shows all available roles/services and lets user pick their path.
    Only shown once — if profile is already completed, redirect to dashboard.
    """
    from app.profile.models import get_profile_by_user
    profile = get_profile_by_user(current_user.public_id)
    
    if profile and profile.profile_completed:
        # Already onboarded — go to their dashboard
        from app.auth.routes import _dashboard_for_user
        return redirect(_dashboard_for_user(current_user))
    
    return render_template("onboarding/choose.html")
```

### 1.2 Template to Create

**File:** `templates/onboarding/choose.html`

This is the most important page. It must clearly explain what each role/path means in plain language. Design requirements:

- Full-screen, visually striking layout (NOT a plain list)
- Each card describes: what you can DO, what you need to PROVIDE, what KYC level is required
- Cards are grouped: "I want to offer services" vs "I want to use services" vs "I'm an organisation"
- Selecting a card routes to that onboarding wizard
- Mobile-first responsive

**Card Definitions (render these exactly):**

```
CARD 1 — "Fan / Event-Goer"
Icon: 🎟️
Title: I'm here to explore
Description: Book events, accommodation and transport as an individual. No business registration needed.
KYC Required: Phone verified (already done at signup)
Button: "Get Started →"
Route: /onboarding/fan

CARD 2 — "Independent Driver"  
Icon: 🚗
Title: I want to offer transport
Description: Register yourself as a driver. Provide your licence and vehicle details. Get matched with passengers.
KYC Required: National ID + Driver's Licence + Vehicle registration
Button: "Become a Driver →"
Route: /onboarding/driver

CARD 3 — "Vehicle Fleet / Transport Company"
Icon: 🚌
Title: I run a transport business
Description: Register your company, add multiple vehicles and drivers. Manage bookings at scale.
KYC Required: Business registration + Fleet documents
Button: "Register Fleet →"
Route: /onboarding/organisation?type=transport

CARD 4 — "Accommodation Host"
Icon: 🏠
Title: I want to list a property
Description: List your home, apartment or rooms for short-term lets. Set your own pricing and availability.
KYC Required: National ID + Proof of ownership/tenancy
Button: "List My Property →"
Route: /onboarding/host

CARD 5 — "Hotel / Lodge / Guesthouse"
Icon: 🏨
Title: I run an accommodation business
Description: Register your hotel, lodge or guesthouse. Manage multiple rooms, bookings and staff.
KYC Required: Business registration + Operating licence
Button: "Register Establishment →"
Route: /onboarding/organisation?type=accommodation

CARD 6 — "Event Organiser"
Icon: 🎪
Title: I want to host events
Description: Create and manage events. Sell tickets, manage attendees and coordinate with venues.
KYC Required: National ID (individual) OR Business registration (company)
Button: "Start Organising →"
Route: /onboarding/event-organiser

CARD 7 — "Organisation (Consumer)"
Icon: 🏢
Title: We're a company using these services
Description: Register your organisation to book transport, accommodation and events at scale. Manage team access and central billing.
KYC Required: Business registration + Contact details
Button: "Register Organisation →"
Route: /onboarding/organisation?type=consumer
```

### 1.3 Register Blueprint

**File:** `app/__init__.py` — add inside `create_app()` after other blueprint registrations:

```python
from app.auth.onboarding_routes import onboarding_bp
app.register_blueprint(onboarding_bp)
```

### 1.4 Redirect After Login

**File:** `app/auth/routes.py` — modify `_dashboard_for_user()`:

```python
def _dashboard_for_user(user) -> str:
    # ADD THIS BLOCK at the very top, before all existing logic:
    from app.profile.models import get_profile_by_user
    profile = get_profile_by_user(user.public_id)
    if not profile or not profile.profile_completed:
        # New user — send to onboarding
        return url_for("onboarding.choose")
    
    # ... rest of existing function unchanged ...
```

---

## PHASE 2 — ONBOARDING WIZARDS

Each wizard is a multi-step form. Each step saves to session. Final step commits everything to DB atomically.

### 2.1 Fan Onboarding (Simplest Path)

**Route:** `GET/POST /onboarding/fan`  
**Steps:** 1 step only  
**Collects:** full_name, city, country  
**Creates:** Updates UserProfile (profile_completed = True)  
**Assigns Role:** `fan` (already assigned at signup — just mark complete)  
**Redirects to:** `fan.dashboard`

```python
@onboarding_bp.route("/fan", methods=["GET", "POST"])
@login_required
def fan_onboarding():
    from app.profile.models import get_profile_by_user
    from app.extensions import db
    from app.utils.transactions import db_transaction
    
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        city = request.form.get("city", "").strip()
        country = request.form.get("country", "").strip()
        
        if not full_name:
            flash("Full name is required.", "danger")
            return render_template("onboarding/fan.html")
        
        profile = get_profile_by_user(current_user.public_id)
        if not profile:
            flash("Profile not found. Please contact support.", "danger")
            return redirect(url_for("onboarding.choose"))
        
        with db_transaction("Fan onboarding completion"):
            profile.full_name = full_name
            profile.city = city
            profile.country = country
            profile.profile_completed = True
        
        flash("Welcome to AFCON 360!", "success")
        return redirect(url_for("fan.dashboard"))
    
    return render_template("onboarding/fan.html")
```

### 2.2 Driver Onboarding (3-Step Wizard)

**Route:** `GET/POST /onboarding/driver`  
**Steps:** 3  
**Collects:**
- Step 1: Personal details (full_name, date_of_birth, nationality, national_id_number)
- Step 2: Licence details (licence_number, licence_expiry, licence_class, licence_document upload)
- Step 3: Vehicle details (make, model, year, plate_number, vehicle_type, insurance_document upload)

**Creates:**
- Updates `UserProfile` (profile_completed = True, id_type = national_id, id_number)
- Creates `DriverProfile` record (see model below)
- Assigns global role: `fan` stays, driver flag set on DriverProfile

**KYC Tier Required:** Tier 2 (triggered after ID submission)

**File:** `app/transport/models.py` — Add `DriverProfile` model if not exists:

```python
class DriverProfile(BaseModel):
    __tablename__ = "driver_profiles"
    
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), 
                     nullable=False, unique=True, index=True)
    
    # Licence
    licence_number = Column(String(64), nullable=False)
    licence_expiry = Column(Date, nullable=True)
    licence_class = Column(String(32), nullable=True)
    licence_document_url = Column(String(512), nullable=True)
    
    # Status
    verification_status = Column(
        SAEnum("pending", "verified", "rejected", "suspended", 
               name="driver_verification_status"),
        default="pending", nullable=False
    )
    is_available = Column(Boolean, default=False, nullable=False)
    
    user = relationship("User", foreign_keys=[user_id])
    vehicles = relationship("Vehicle", back_populates="driver", 
                            foreign_keys="Vehicle.driver_id")
```

**Session Flow for multi-step:**
```python
# Step 1 POST → save to session["driver_onboarding"]["step1"] → redirect to step 2
# Step 2 POST → save to session["driver_onboarding"]["step2"] → redirect to step 3  
# Step 3 POST → read all session data → commit everything → clear session → redirect
```

**Complete route skeleton:**

```python
@onboarding_bp.route("/driver", methods=["GET", "POST"])
@onboarding_bp.route("/driver/step/<int:step>", methods=["GET", "POST"])
@login_required
def driver_onboarding(step=1):
    if "driver_onboarding" not in session:
        session["driver_onboarding"] = {}
    
    if request.method == "POST":
        data = session["driver_onboarding"]
        
        if step == 1:
            data["step1"] = {
                "full_name": request.form.get("full_name", "").strip(),
                "date_of_birth": request.form.get("date_of_birth"),
                "nationality": request.form.get("nationality", "").strip(),
                "national_id_number": request.form.get("national_id_number", "").strip(),
            }
            session["driver_onboarding"] = data
            return redirect(url_for("onboarding.driver_onboarding", step=2))
        
        elif step == 2:
            data["step2"] = {
                "licence_number": request.form.get("licence_number", "").strip(),
                "licence_expiry": request.form.get("licence_expiry"),
                "licence_class": request.form.get("licence_class", "").strip(),
            }
            # Handle file upload for licence
            licence_file = request.files.get("licence_document")
            if licence_file:
                # Save file → get URL → store in data["step2"]["licence_document_url"]
                pass
            session["driver_onboarding"] = data
            return redirect(url_for("onboarding.driver_onboarding", step=3))
        
        elif step == 3:
            data["step3"] = {
                "vehicle_make": request.form.get("vehicle_make", "").strip(),
                "vehicle_model": request.form.get("vehicle_model", "").strip(),
                "vehicle_year": request.form.get("vehicle_year"),
                "plate_number": request.form.get("plate_number", "").strip(),
                "vehicle_type": request.form.get("vehicle_type", "").strip(),
            }
            
            # COMMIT EVERYTHING
            try:
                _commit_driver_onboarding(current_user, data)
                session.pop("driver_onboarding", None)
                flash("Driver registration submitted! We will verify your documents within 24 hours.", "success")
                return redirect(url_for("transport.driver_dashboard"))
            except Exception as e:
                current_app.logger.error(f"Driver onboarding error: {e}")
                flash("Something went wrong. Please try again.", "danger")
    
    return render_template(f"onboarding/driver_step{step}.html",
                           data=session.get("driver_onboarding", {}),
                           step=step)


def _commit_driver_onboarding(user, data):
    """Atomic commit of all driver onboarding data."""
    from app.profile.models import get_profile_by_user
    from app.transport.models import DriverProfile, Vehicle
    from app.extensions import db
    from app.utils.transactions import db_transaction
    
    step1 = data.get("step1", {})
    step2 = data.get("step2", {})
    step3 = data.get("step3", {})
    
    with db_transaction("Driver onboarding commit"):
        # Update UserProfile
        profile = get_profile_by_user(user.public_id)
        profile.full_name = step1["full_name"]
        profile.nationality = step1["nationality"]
        profile.id_type = "national_id"
        profile.id_number = step1["national_id_number"]
        profile.profile_completed = True
        
        # Create DriverProfile
        driver = DriverProfile(
            user_id=user.id,  # internal FK — correct
            licence_number=step2["licence_number"],
            licence_expiry=step2.get("licence_expiry"),
            licence_class=step2.get("licence_class"),
            licence_document_url=step2.get("licence_document_url"),
            verification_status="pending",
        )
        db.session.add(driver)
        db.session.flush()
        
        # Create Vehicle
        vehicle = Vehicle(
            driver_id=driver.id,
            make=step3["vehicle_make"],
            model=step3["vehicle_model"],
            year=step3.get("vehicle_year"),
            plate_number=step3["plate_number"],
            vehicle_type=step3.get("vehicle_type"),
            verification_status="pending",
        )
        db.session.add(vehicle)
```

### 2.3 Organisation Onboarding (Universal — type determines sub-path)

**Route:** `GET/POST /onboarding/organisation`  
**Query param:** `?type=transport|accommodation|consumer`  
**Steps:** 2

- Step 1: Organisation details (legal_name, country, registration_no, tax_id, contact_email, contact_phone, website)
- Step 2: Type-specific documents + confirm

**Creates:**
- `Organisation` record
- `OrganisationMember` record (links current user to org)
- Assigns org role: `org_owner` via `assign_org_role()`
- Sets `session["current_context"] = "organization"` and `session["current_org_id"]`

**IMPORTANT — Org ID rule:** After creating the org, use `org.id` (BIGINT) only for FK assignments internally. Use `org.org_id` (UUID string) for URLs and public display.

```python
@onboarding_bp.route("/organisation", methods=["GET", "POST"])
@onboarding_bp.route("/organisation/step/<int:step>", methods=["GET", "POST"])
@login_required  
def organisation_onboarding(step=1):
    org_type = request.args.get("type", session.get("org_onboarding_type", "consumer"))
    
    if step == 1 and request.method == "GET":
        session["org_onboarding_type"] = org_type
        session["org_onboarding"] = {}
    
    if "org_onboarding" not in session:
        session["org_onboarding"] = {}
    
    if request.method == "POST":
        data = session["org_onboarding"]
        
        if step == 1:
            data["step1"] = {
                "legal_name": request.form.get("legal_name", "").strip(),
                "country": request.form.get("country", "").strip(),
                "registration_no": request.form.get("registration_no", "").strip(),
                "tax_id": request.form.get("tax_id", "").strip(),
                "contact_email": request.form.get("contact_email", "").strip(),
                "contact_phone": request.form.get("contact_phone", "").strip(),
                "website": request.form.get("website", "").strip(),
                "org_type": session.get("org_onboarding_type", "consumer"),
            }
            session["org_onboarding"] = data
            return redirect(url_for("onboarding.organisation_onboarding", step=2))
        
        elif step == 2:
            try:
                org = _commit_organisation_onboarding(current_user, data)
                session.pop("org_onboarding", None)
                session.pop("org_onboarding_type", None)
                
                # Switch context to the new org immediately
                session["current_context"] = "organization"
                session["current_org_id"] = org.id
                session["current_org_name"] = org.legal_name
                
                flash(f"Organisation '{org.legal_name}' registered successfully!", "success")
                return redirect(url_for("org.dashboard", org_id=org.id))
            except ValueError as e:
                flash(str(e), "danger")
            except Exception as e:
                current_app.logger.error(f"Org onboarding error: {e}")
                flash("Registration failed. Please try again.", "danger")
    
    return render_template(
        f"onboarding/organisation_step{step}.html",
        data=session.get("org_onboarding", {}),
        org_type=org_type,
        step=step,
    )


def _commit_organisation_onboarding(user, data):
    """Atomic commit of organisation registration."""
    import uuid
    from app.identity.models.organisation import Organisation
    from app.identity.models.organisation_member import OrganisationMember
    from app.auth.roles import assign_org_role
    from app.profile.models import get_profile_by_user
    from app.extensions import db
    from app.utils.transactions import db_transaction
    
    step1 = data.get("step1", {})
    
    with db_transaction("Organisation onboarding commit"):
        # Create Organisation
        org = Organisation(
            org_id=str(uuid.uuid4()),  # public UUID
            legal_name=step1["legal_name"],
            country=step1["country"],
            registration_no=step1.get("registration_no"),
            tax_id=step1.get("tax_id"),
            contact_email=step1.get("contact_email"),
            contact_phone=step1.get("contact_phone"),
            website=step1.get("website"),
            primary_contact_user_id=user.id,  # internal FK
            verification_status="pending",
            lifecycle_state="registered",
        )
        db.session.add(org)
        db.session.flush()  # Get org.id before creating member
        
        # Create membership
        member = OrganisationMember(
            user_id=user.id,  # internal FK
            organisation_id=org.id,  # internal FK
            is_active=True,
            is_deleted=False,
        )
        db.session.add(member)
        db.session.flush()
        
        # Assign org_owner role
        assign_org_role(
            user_id=user.id,
            org_id=org.id,
            role_name="org_owner",
            assigned_by_id=user.id,
        )
        
        # Set user's default org
        from app.identity.models.user import User as UserModel
        db_user = UserModel.query.get(user.id)
        if db_user:
            db_user.default_org_id = org.id
        
        # Mark profile complete
        profile = get_profile_by_user(user.public_id)
        if profile:
            profile.profile_completed = True
    
    return org
```

### 2.4 Accommodation Host Onboarding (2-Step)

**Route:** `GET/POST /onboarding/host`  
**Steps:** 2

- Step 1: Personal verification (full_name, national_id, proof of address)
- Step 2: Property details (property_name, address, city, country, property_type, number_of_rooms)

**Creates:**
- Updates `UserProfile`
- Creates `Property` record with `verification_status = "pending"`
- No new role — hosts use the `fan` base role + property ownership record

### 2.5 Event Organiser Onboarding (1-Step)

**Route:** `GET/POST /onboarding/event-organiser`  
**Steps:** 1

**Collects:** full_name, organisation_name (optional), contact_email  
**Creates:** Updates `UserProfile`, assigns `event_manager` role if individual OR creates org if company

---

## PHASE 3 — DASHBOARD ROUTING FIX

**File:** `app/auth/routes.py`

Replace the existing `_dashboard_for_user()` completely:

```python
def _dashboard_for_user(user) -> str:
    """
    Route user to the correct dashboard based on:
    1. Onboarding completion (if not done → onboarding)
    2. Owner role (highest privilege)
    3. Admin roles
    4. Organisation context
    5. Driver profile
    6. Host profile  
    7. Event organiser role
    8. Default fan dashboard
    """
    # STEP 1: Check onboarding completion
    try:
        from app.profile.models import get_profile_by_user
        profile = get_profile_by_user(user.public_id)
        if not profile or not profile.profile_completed:
            return url_for("onboarding.choose")
    except Exception as e:
        current_app.logger.warning(f"Profile check error in dashboard routing: {e}")
    
    # STEP 2: Owner
    if hasattr(user, 'is_app_owner') and callable(user.is_app_owner):
        try:
            if user.is_app_owner():
                return url_for("admin.owner.dashboard")
        except Exception:
            pass
    
    # STEP 3: Build role set
    role_names = set()
    try:
        for ur in (user.roles or []):
            if hasattr(ur, 'role') and ur.role:
                role_names.add(ur.role.name)
    except Exception:
        pass
    
    if "owner" in role_names:
        return url_for("admin.owner.dashboard")
    
    # STEP 4: System admin roles
    if "super_admin" in role_names:
        try:
            return url_for("admin.super_dashboard")
        except Exception:
            pass
    
    if "admin" in role_names:
        try:
            return url_for("admin.super_dashboard")
        except Exception:
            pass
    
    # STEP 5: Org context (user is acting as an org)
    from flask import session
    current_context = session.get("current_context", "individual")
    current_org_id = session.get("current_org_id")
    
    if current_context == "organization" and current_org_id:
        try:
            return url_for("org.dashboard", org_id=current_org_id)
        except Exception:
            pass
    
    # STEP 6: Check for driver profile
    try:
        from app.transport.models import DriverProfile
        driver = DriverProfile.query.filter_by(user_id=user.id).first()
        if driver and driver.verification_status == "verified":
            return url_for("transport.driver_dashboard")
    except Exception:
        pass
    
    # STEP 7: Event organiser role
    if "event_manager" in role_names:
        try:
            return url_for("events.organizer_dashboard")
        except Exception:
            pass
    
    # STEP 8: Default fan dashboard
    try:
        return url_for("fan.dashboard")
    except Exception:
        return url_for("index")
```

---

## PHASE 4 — WALLET ACTIVATION (ON-DEMAND)

**This is NOT part of onboarding. Build it as a separate opt-in flow.**

**Route:** `GET/POST /wallet/activate`  
**File:** `app/wallet/routes.py` (already exists — add this route)

```python
@wallet_bp.route("/activate", methods=["GET", "POST"])
@login_required
def activate_wallet():
    """
    User explicitly opts in to the wallet.
    Shows terms → on accept, creates AccountModel.
    """
    from app.wallet.models.ledger import AccountModel, AccountOwnerType
    from app.identity.models.user import User
    from app.extensions import db
    from app.utils.transactions import db_transaction
    
    # Get internal user ID
    db_user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not db_user:
        flash("User not found.", "danger")
        return redirect(url_for("fan.dashboard"))
    
    # Check if wallet already exists
    existing = AccountModel.query.filter_by(
        user_id=db_user.id,
        owner_type=AccountOwnerType.USER
    ).first()
    
    if existing:
        flash("You already have a wallet.", "info")
        return redirect(url_for("wallet.wallet_dashboard"))
    
    if request.method == "POST":
        if not request.form.get("accept_terms"):
            flash("You must accept the terms to activate your wallet.", "warning")
            return render_template("wallet/wallet_activate.html")
        
        with db_transaction("Wallet activation"):
            account = AccountModel(
                user_id=db_user.id,  # internal FK
                owner_type=AccountOwnerType.USER,
                currency="UGX",
                balance=0,
            )
            db.session.add(account)
        
        flash("Your wallet has been activated!", "success")
        return redirect(url_for("wallet.wallet_dashboard"))
    
    return render_template("wallet/wallet_activate.html")
```

---

## PHASE 5 — TEMPLATES TO BUILD

### 5.1 Required Templates (Create All)

```
templates/
  onboarding/
    choose.html          ← THE LANDING PAGE (most important)
    fan.html             ← Simple 1-step form
    driver_step1.html    ← Personal details
    driver_step2.html    ← Licence details  
    driver_step3.html    ← Vehicle details
    organisation_step1.html   ← Org details
    organisation_step2.html   ← Documents + confirm
    host_step1.html      ← Personal verification
    host_step2.html      ← Property details
    event_organiser.html ← 1-step form
    _progress_bar.html   ← Shared component (steps 1/2/3 indicator)
```

### 5.2 `choose.html` Design Specification

```html
<!-- templates/onboarding/choose.html -->
{% extends "base.html" %}
{% block content %}

<!-- 
  DESIGN BRIEF FOR CODEIUM:
  - Full viewport height layout
  - Dark background (#0a0a0a) with electric blue accents (#00d4ff)
  - Bold sans-serif headings (e.g. Syne or DM Sans from Google Fonts)
  - Grid of cards — 3 columns on desktop, 1 on mobile
  - Each card: icon (large emoji or SVG), title, 2-line description, KYC badge, CTA button
  - Cards have hover effect: lift + border glow
  - Header text: "What brings you to AFCON 360?"
  - Subtext: "Choose your path. You can always add more later."
  - NO sidebar, NO nav links — full focus on the choice
  - Bottom: small link "Not sure? Start as a Fan →"
-->

<div class="onboarding-choose">
  <header class="onboarding-header">
    <h1>What brings you to AFCON 360?</h1>
    <p>Choose your path. You can always add more later.</p>
  </header>
  
  <div class="path-grid">
    
    <!-- CARD: Fan -->
    <a href="{{ url_for('onboarding.fan_onboarding') }}" class="path-card">
      <span class="path-icon">🎟️</span>
      <h3>Fan / Explorer</h3>
      <p>Book events, accommodation and transport as an individual.</p>
      <span class="kyc-badge kyc-tier-1">Phone verified only</span>
      <span class="path-cta">Get Started →</span>
    </a>
    
    <!-- CARD: Driver -->
    <a href="{{ url_for('onboarding.driver_onboarding') }}" class="path-card">
      <span class="path-icon">🚗</span>
      <h3>Independent Driver</h3>
      <p>Offer transport services. Register your licence and vehicle.</p>
      <span class="kyc-badge kyc-tier-2">National ID + Licence required</span>
      <span class="path-cta">Become a Driver →</span>
    </a>
    
    <!-- CARD: Fleet / Transport Org -->
    <a href="{{ url_for('onboarding.organisation_onboarding', type='transport') }}" class="path-card">
      <span class="path-icon">🚌</span>
      <h3>Transport Company</h3>
      <p>Register your fleet. Manage multiple drivers and vehicles at scale.</p>
      <span class="kyc-badge kyc-tier-3">Business registration required</span>
      <span class="path-cta">Register Fleet →</span>
    </a>
    
    <!-- CARD: Host -->
    <a href="{{ url_for('onboarding.host_onboarding') }}" class="path-card">
      <span class="path-icon">🏠</span>
      <h3>Accommodation Host</h3>
      <p>List your home or property for short-term lets.</p>
      <span class="kyc-badge kyc-tier-2">National ID + Proof of property</span>
      <span class="path-cta">List My Property →</span>
    </a>
    
    <!-- CARD: Hotel -->
    <a href="{{ url_for('onboarding.organisation_onboarding', type='accommodation') }}" class="path-card">
      <span class="path-icon">🏨</span>
      <h3>Hotel / Lodge</h3>
      <p>Register your establishment. Manage rooms, bookings and staff.</p>
      <span class="kyc-badge kyc-tier-3">Business licence required</span>
      <span class="path-cta">Register Establishment →</span>
    </a>
    
    <!-- CARD: Event Organiser -->
    <a href="{{ url_for('onboarding.event_organiser_onboarding') }}" class="path-card">
      <span class="path-icon">🎪</span>
      <h3>Event Organiser</h3>
      <p>Create and manage events. Sell tickets and manage attendees.</p>
      <span class="kyc-badge kyc-tier-2">National ID (individual) or Business reg</span>
      <span class="path-cta">Start Organising →</span>
    </a>
    
    <!-- CARD: Consumer Org -->
    <a href="{{ url_for('onboarding.organisation_onboarding', type='consumer') }}" class="path-card">
      <span class="path-icon">🏢</span>
      <h3>Organisation</h3>
      <p>Book services as a company. Manage team access and central billing.</p>
      <span class="kyc-badge kyc-tier-2">Business registration required</span>
      <span class="path-cta">Register Organisation →</span>
    </a>
    
  </div>
  
  <footer class="onboarding-footer">
    <a href="{{ url_for('onboarding.fan_onboarding') }}">Not sure yet? Start as a Fan →</a>
  </footer>
</div>

{% endblock %}
```

---

## PHASE 6 — DATABASE MIGRATIONS

Run these in order after code changes:

```bash
# 1. Add DriverProfile table (if not exists)
flask db migrate -m "add_driver_profile_table"
flask db upgrade

# 2. Seed all roles
flask seed-all

# 3. Verify
flask shell
>>> from app.identity.models.roles_permission import Role
>>> Role.query.all()  # Should show all roles including owner, fan, etc.
```

---

## PHASE 7 — TESTS FOR CODEIUM TO RUN

Create `tests/test_onboarding.py`:

```python
# tests/test_onboarding.py
"""
Onboarding flow integration tests.
Run with: pytest tests/test_onboarding.py -v
"""
import pytest
from app import create_app
from app.extensions import db
from app.identity.models.user import User, UserRole
from app.identity.models.roles_permission import Role
from app.profile.models import UserProfile, get_profile_by_user


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def registered_user(app):
    """Create a registered but not-yet-onboarded user."""
    with app.app_context():
        user = User(
            public_id="test-uuid-1234",
            username="testuser",
            email="test@example.com",
        )
        user.set_password("TestPassword123!")
        user.is_active = True
        user.is_verified = True
        db.session.add(user)
        db.session.flush()
        
        # Fan role
        fan_role = Role.query.filter_by(name="fan").first()
        if fan_role:
            db.session.add(UserRole(user_id=user.id, role_id=fan_role.id))
        
        # Incomplete profile
        profile = UserProfile(
            user_id=user.public_id,
            full_name="Test User",
            profile_completed=False,
        )
        db.session.add(profile)
        db.session.commit()
        
        yield user


class TestOnboardingChoosePage:
    """Test the landing/choose page."""
    
    def test_choose_page_accessible_when_logged_in(self, client, registered_user):
        """Authenticated users can access the choose page."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.get("/onboarding/choose")
        assert response.status_code == 200
        assert b"What brings you" in response.data
    
    def test_choose_page_redirects_if_already_onboarded(self, client, app, registered_user):
        """Users with completed profiles skip the choose page."""
        with app.app_context():
            profile = get_profile_by_user(registered_user.public_id)
            profile.profile_completed = True
            db.session.commit()
        
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.get("/onboarding/choose")
        assert response.status_code == 302  # Redirect to dashboard
    
    def test_choose_page_requires_login(self, client):
        """Unauthenticated users are redirected to login."""
        response = client.get("/onboarding/choose")
        assert response.status_code == 302
        assert b"login" in response.headers["Location"].lower()


class TestFanOnboarding:
    """Test fan onboarding flow."""
    
    def test_fan_onboarding_completes_profile(self, client, app, registered_user):
        """Submitting fan form marks profile as complete."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.post("/onboarding/fan", data={
            "full_name": "John Doe",
            "city": "Kampala",
            "country": "UG",
        }, follow_redirects=False)
        
        assert response.status_code == 302
        assert "fan/dashboard" in response.headers["Location"]
        
        with app.app_context():
            profile = get_profile_by_user(registered_user.public_id)
            assert profile.profile_completed is True
            assert profile.full_name == "John Doe"
            assert profile.city == "Kampala"
    
    def test_fan_onboarding_requires_full_name(self, client, registered_user):
        """Fan form rejects empty full_name."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.post("/onboarding/fan", data={
            "full_name": "",
            "city": "Kampala",
            "country": "UG",
        })
        
        assert response.status_code == 200  # Stays on form
        assert b"required" in response.data.lower()


class TestOrganisationOnboarding:
    """Test organisation registration flow."""
    
    def test_org_onboarding_step1_saves_to_session(self, client, registered_user):
        """Step 1 data is saved to session and redirects to step 2."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.post("/onboarding/organisation/step/1?type=consumer", data={
            "legal_name": "Test Company Ltd",
            "country": "UG",
            "registration_no": "REG123",
            "tax_id": "TAX456",
            "contact_email": "company@test.com",
            "contact_phone": "+256700000000",
            "website": "https://test.com",
        }, follow_redirects=False)
        
        assert response.status_code == 302
        assert "step/2" in response.headers["Location"]
    
    def test_org_onboarding_creates_organisation_record(self, client, app, registered_user):
        """Completing org onboarding creates Organisation + Member records."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
            sess["org_onboarding"] = {
                "step1": {
                    "legal_name": "Test Company Ltd",
                    "country": "UG",
                    "registration_no": "REG123",
                    "tax_id": "TAX456",
                    "contact_email": "company@test.com",
                    "contact_phone": "+256700000000",
                    "website": "",
                    "org_type": "consumer",
                }
            }
            sess["org_onboarding_type"] = "consumer"
        
        response = client.post("/onboarding/organisation/step/2", 
                               follow_redirects=False)
        
        assert response.status_code == 302
        
        with app.app_context():
            from app.identity.models.organisation import Organisation
            org = Organisation.query.filter_by(legal_name="Test Company Ltd").first()
            assert org is not None
            assert org.primary_contact_user_id == registered_user.id


class TestDashboardRouting:
    """Test that _dashboard_for_user routes correctly."""
    
    def test_incomplete_profile_routes_to_onboarding(self, app, registered_user):
        """Users with incomplete profiles go to onboarding."""
        with app.app_context():
            from app.auth.routes import _dashboard_for_user
            with app.test_request_context("/"):
                url = _dashboard_for_user(registered_user)
            assert "onboarding" in url
    
    def test_complete_fan_profile_routes_to_fan_dashboard(self, app, registered_user):
        """Completed fan profiles go to fan dashboard."""
        with app.app_context():
            profile = get_profile_by_user(registered_user.public_id)
            profile.profile_completed = True
            db.session.commit()
            
            from app.auth.routes import _dashboard_for_user
            with app.test_request_context("/"):
                url = _dashboard_for_user(registered_user)
            assert "fan" in url


class TestWalletActivation:
    """Test wallet is not auto-created and requires explicit activation."""
    
    def test_wallet_not_created_at_signup(self, app, registered_user):
        """New users have no wallet by default."""
        with app.app_context():
            from app.wallet.models.ledger import AccountModel, AccountOwnerType
            account = AccountModel.query.filter_by(
                user_id=registered_user.id,
                owner_type=AccountOwnerType.USER
            ).first()
            assert account is None
    
    def test_wallet_created_after_activation(self, client, app, registered_user):
        """Wallet is created only after user accepts terms."""
        with client.session_transaction() as sess:
            sess["_user_id"] = registered_user.public_id
        
        response = client.post("/wallet/activate", data={
            "accept_terms": "on"
        }, follow_redirects=False)
        
        assert response.status_code == 302
        
        with app.app_context():
            from app.wallet.models.ledger import AccountModel, AccountOwnerType
            account = AccountModel.query.filter_by(
                user_id=registered_user.id,
                owner_type=AccountOwnerType.USER
            ).first()
            assert account is not None
```

---

## PHASE 8 — EXECUTION ORDER FOR CODEIUM

Follow this exact order. Do not skip steps. Report status after each.

### Step 1: Create `app/auth/onboarding_routes.py`
- Implement all 6 routes: `choose`, `fan_onboarding`, `driver_onboarding`, `organisation_onboarding`, `host_onboarding`, `event_organiser_onboarding`
- Include all helper functions: `_commit_driver_onboarding`, `_commit_organisation_onboarding`
- **Test:** `from app.auth.onboarding_routes import onboarding_bp` — must import without errors

### Step 2: Register Blueprint
- Add `from app.auth.onboarding_routes import onboarding_bp` and `app.register_blueprint(onboarding_bp)` to `app/__init__.py`
- **Test:** `flask routes | grep onboarding` — must show all onboarding routes

### Step 3: Modify `_dashboard_for_user()` in `app/auth/routes.py`
- Replace with the new version from Phase 3
- **Test:** Import and call with a test user object — must return onboarding URL for incomplete profile

### Step 4: Create All Templates
- Build `templates/onboarding/choose.html` first — this is the highest priority
- Then build `fan.html`, `driver_step1.html`, `driver_step2.html`, `driver_step3.html`
- Then `organisation_step1.html`, `organisation_step2.html`
- **Test:** `flask run` and visit `/onboarding/choose` — must render without errors

### Step 5: Add `DriverProfile` Model
- Add to `app/transport/models.py` if not already present
- **Test:** `flask db migrate --dry-run` — must detect new table

### Step 6: Run Migrations
```bash
flask db migrate -m "add_driver_profile_onboarding"
flask db upgrade
flask seed-all
```
- **Test:** `flask shell` → `from app.identity.models.roles_permission import Role; print(Role.query.count())` — must be > 0

### Step 7: Add Wallet Activation Route
- Add `activate_wallet` route to `app/wallet/routes.py`
- **Test:** `flask routes | grep activate` — must show `/wallet/activate`

### Step 8: Run All Tests
```bash
pytest tests/test_onboarding.py -v --tb=short
```
- **Expected:** All tests pass
- **Report:** Paste full test output including any failures

---

## COMMON MISTAKES TO AVOID

| Mistake | Correct Approach |
|---|---|
| `get_profile_by_user(user.id)` | `get_profile_by_user(user.public_id)` |
| `session["user_id"] = user.id` | `session["user_id"] = user.public_id` |
| Auto-creating wallet in register_user() | Never — wallet is opt-in only |
| Hardcoding role check `if user.role == "fan"` | Use `has_global_role(user, "fan")` from helpers.py |
| Creating org without flushing before member | Always `db.session.flush()` after org to get org.id |
| Redirect to dashboard without checking onboarding | Always check `profile.profile_completed` first |
| Storing driver data in User model | Store in separate `DriverProfile` model |
| Using `url_for()` outside request context in tests | Wrap in `app.test_request_context("/")` |

---

## EXPECTED FINAL STATE

After full implementation:

1. New user signs up → verified via OTP → sees `choose.html` landing page
2. Each card clearly explains the service and what's required
3. Selecting a path initiates the correct multi-step wizard
4. Completing a wizard creates the right records atomically
5. User is routed to the correct role-specific dashboard
6. Wallet is never created unless user explicitly activates it
7. All tests in `test_onboarding.py` pass
8. No internal BIGINTs are exposed in any URL or template
9. `flask routes` shows all onboarding endpoints

---

## REPORT TEMPLATE (Codeium must fill this after implementation)

```
=== ONBOARDING IMPLEMENTATION REPORT ===
Date: ___________

ROUTES CREATED:
[ ] /onboarding/choose
[ ] /onboarding/fan  
[ ] /onboarding/driver
[ ] /onboarding/driver/step/<n>
[ ] /onboarding/organisation
[ ] /onboarding/organisation/step/<n>
[ ] /onboarding/host
[ ] /onboarding/host/step/<n>
[ ] /onboarding/event-organiser
[ ] /wallet/activate

TEMPLATES CREATED:
[ ] templates/onboarding/choose.html
[ ] templates/onboarding/fan.html
[ ] templates/onboarding/driver_step1.html
[ ] templates/onboarding/driver_step2.html
[ ] templates/onboarding/driver_step3.html
[ ] templates/onboarding/organisation_step1.html
[ ] templates/onboarding/organisation_step2.html
[ ] templates/onboarding/host_step1.html
[ ] templates/onboarding/host_step2.html
[ ] templates/onboarding/event_organiser.html

MIGRATIONS:
[ ] flask db migrate ran without errors
[ ] flask db upgrade ran without errors
[ ] flask seed-all ran without errors

TEST RESULTS:
Total: ___  Passed: ___  Failed: ___
Failed tests (if any): ___________

ISSUES ENCOUNTERED:
___________

DECISIONS MADE (deviations from this guide):
___________
```
