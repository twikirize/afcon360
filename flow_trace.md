# Complete Flow: /onboarding/choose/individual → Accommodation Host Onboarding

## Overview

This trace documents the complete browser flow when a user navigates from the individual onboarding choose page to the accommodation host onboarding wizard and completes property listing.

---

## FLOW DIAGRAM

```
User Session (logged in)
          |
          v
1. GET /onboarding/choose/individual
   │
   └─ app/auth/onboarding_routes.py:choose_individual()
   └─ template: templates/onboarding/choose_individual.html
   └─ Shows 3 cards: Driver (🚗), Accommodation Host (🏠), Event Organiser (🎪)
   └─ "Accommodation Host" card <a href="/onboarding/host">List My Property →</a>
          |
          v

2. GET /onboarding/host (step=1 default)
   │
   └─ app/auth/onboarding_routes.py:host_onboarding(step=1)
   └─ template: templates/onboarding/host_step1.html
   └─ Wizard Step 1: "Host — Identity"
   └─ Form fields:
       • Full Name (required, input type="text" name="full_name")
       • National ID Number (required, input type="text" name="national_id")
       • ID Document (input type="file" name="id_document")
       • Proof of Address (input type="file" name="proof_of_address")
       • CSRF token hidden field
       • Continue → button (type="submit")
   └─ Authorization: @login_required
   └─ On POST step=1:
       • Saves: session["host_onboarding"]["step1"] = {full_name, national_id, proof_of_address}
       • Redirect: url_for("onboarding.host_onboarding", step=2) → /onboarding/host/step/2
          |
          v

3. GET /onboarding/host/step/2
   │
   └─ app/auth/onboarding_routes.py:host_onboarding(step=2)
   └─ template: templates/onboarding/host_step2.html
   └─ Wizard Step 2: "Host — Property"
   └─ Form fields:
       • Property Name (required, input type="text" name="property_name")
       • Description (textarea name="description")
       • Address (required, input type="text" name="address")
       • City (required, input type="text" name="city")
       • Country (required, input type="text" name="country", placeholder="UG")
       • Property Type (select: apartment, house, room, villa)
       • Number of Rooms (input type="number" name="number_of_rooms" min="1" value="1")
       • CSRF token hidden field
       • List Property → button (type="submit")
   └─ Authorization: @login_required
   └─ On POST step=2:
       • Normalizes country: normalize_country(data["step2"]["country"])
       • Calls: _commit_host_onboarding(current_user, data, save_as_intent_only=...)
       • On success:
         - session.pop("host_onboarding", None)
         - flash("Property listed successfully! We will verify your details.", "success")
         - Redirect: url_for("accommodation.host_dashboard") → /host/dashboard
       • On ValueError: flash error, re-render step 2
       • On Exception: log error, flash "Something went wrong", re-render step 2
          |
          v

4. GET /host/dashboard
   │
   └─ app/accommodation/routes.py:host_dashboard()
   └─ Calls: _ensure_host_identity()
   └─ Identity verification chain:
       a. AccommodationIdentityService.can_host(current_user)
          → verifies user has completed host onboarding pathway
       b. AccommodationIdentityService.get_host_identity(current_user)
          → returns host_info dict with {type: "individual"|"organisation", id, ...}
       c. Check active context type:
          • PLATFORM → return host_info
          • Not ACCOMMODATION_HOST → flash warning, null
       d. If individual host:
          • Verify active_context.public_id == str(current_user.public_id)
          • Abort(403) if mismatch
       e. If organisation host:
          • Query Organisation by host_info["id"]
          • Verify str(organisation.org_id) == str(active_context.public_id)
          • Abort(403) if mismatch
   └─ On success: HostService.get_dashboard_data() + render_template()
     └─ template: accommodation/host/dashboard.html
     └─ Displays: host info, listings, bookings, stats, revenue, analytics
   └─ On failure: flash warning, redirect url_for("index")

---

## DETAILED PER-STEP BREAKDOWN

### Step 1: Choose Individual → Host Onboarding Landing

**File:** `app/auth/onboarding_routes.py:92-96`
```python
@onboarding_bp.route("/choose/individual", methods=["GET"])
@login_required
def choose_individual():
    """Individual onboarding landing page."""
    return render_template("onboarding/choose_individual.html")
```

**Template:** `templates/onboarding/choose_individual.html:30-37`
```html
<a href="{{ url_for('onboarding.host_onboarding') }}" class="ob-big-card">
    <div class="ob-big-card-icon">🏠</div>
    <div class="ob-big-card-body">
        <h2>Accommodation Host</h2>
        <p>List your property for short-term stays.</p>
    </div>
    <span class="ob-big-card-cta">List My Property →</span>
</a>
```
- No form fields; pure navigation link
- Link resolves to `/onboarding/host` (step=1 default)

**Session data:** None read; user must be `@login_required`

**Authorization:** `@login_required` — ensures user is authenticated

**Redirect:** None on GET

---

### Step 2: Host Onboarding Step 1 — Identity Verification

**File:** `app/auth/onboarding_routes.py:636-689`
```python
@onboarding_bp.route("/host", methods=["GET", "POST"])
@onboarding_bp.route("/host/step/<int:step>", methods=["GET", "POST"])
@login_required
def host_onboarding(step: int = 1):
    """Accommodation host onboarding wizard."""
    if "host_onboarding" not in session:
        session["host_onboarding"] = {}

    if request.method == "POST":
        data = session["host_onboarding"]

        if step == 1:
            data["step1"] = {
                "full_name": request.form.get("full_name", "").strip(),
                "national_id": request.form.get("national_id", "").strip(),
                "proof_of_address": request.form.get("proof_of_address", "").strip(),
            }
            session["host_onboarding"] = data
            return redirect(url_for("onboarding.host_onboarding", step=2))

        elif step == 2:
            # ... (see Step 3 below)
```

**Template:** `templates/onboarding/host_step1.html:1-36`
```html
<form method="POST" action="{{ url_for('onboarding.host_onboarding', step=1) }}" class="ob-form" enctype="multipart/form-data">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="ob-field">
        <label>Full Name <span class="ob-req">*</span></label>
        <input type="text" name="full_name" required>
    </div>
    <div class="ob-field">
        <label>National ID Number <span class="ob-req">*</span></label>
        <input type="text" name="national_id" required>
    </div>
    <div class="ob-field">
        <label>ID Document</label>
        <input type="file" name="id_document">
    </div>
    <div class="ob-field">
        <label>Proof of Address</label>
        <input type="file" name="proof_of_address">
    </div>
    <div class="ob-form-footer">
        <button class="ob-btn ob-btn--primary" type="submit">Continue →</button>
    </div>
</form>
```

**Session data stored:**
```
session["host_onboarding"] = {
    "step1": {
        "full_name": "<entered full name>",
        "national_id": "<entered national id>",
        "proof_of_address": "<uploaded filename or empty>"
    }
}
```

**Redirect target:** `/onboarding/host/step/2` (step=2)

**Authorization:** `@login_required`

---

### Step 3: Host Onboarding Step 2 — Property Details

**File:** `app/auth/onboarding_routes.py:656-684`
```python
elif step == 2:
    data["step2"] = {
        "property_name": request.form.get("property_name", "").strip(),
        "description": request.form.get("description", "").strip(),
        "address": request.form.get("address", "").strip(),
        "city": request.form.get("city", "").strip(),
        "country": request.form.get("country", "").strip(),
        "property_type": request.form.get("property_type", "").strip(),
        "number_of_rooms": request.form.get("number_of_rooms", "1").strip(),
    }

    try:
        # Normalize country name/Code to ISO alpha-2 before persisting
        data["step2"]["country"] = normalize_country(data["step2"]["country"])
        _commit_host_onboarding(
            current_user,
            data,
            save_as_intent_only=request.args.get("intent_only") == "1",
        )
        session.pop("host_onboarding", None)
        flash("Property listed successfully! We will verify your details.", "success")
        return redirect(url_for("accommodation.host_dashboard"))
    except ValueError as e:
        current_app.logger.warning(f"Host onboarding country error: {e}")
        flash(str(e), "danger")
    except Exception as e:
        current_app.logger.error(f"Host onboarding error: {e}")
        flash("Something went wrong. Please again.", "danger")
```

**Template:** `templates/onboarding/host_step2.html:1-53`
```html
<form method="POST" action="{{ url_for('onboarding.host_onboarding', step=2) }}" class="ob-form" enctype="multipart/form-data">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <div class="ob-field">
        <label>Property Name <span class="ob-req">*</span></label>
        <input type="text" name="property_name" required>
    </div>
    <div class="ob-field">
        <label>Description</label>
        <textarea name="description" rows="3"></textarea>
    </div>
    <div class="ob-field">
        <label>Address <span class="ob-req">*</span></label>
        <input type="text" name="address" required>
    </div>
    <div class="ob-field">
        <label>City <span class="ob-req">*</span></label>
        <input type="text" name="city" required>
    </div>
    <div class="ob-field">
        <label>Country (2-letter code) <span class="ob-req">*</span></label>
        <input type="text" name="country" placeholder="UG" required>
    </div>
    <div class="ob-field">
        <label>Property Type</label>
        <select name="property_type">
            <option value="apartment">Apartment</option>
            <option value="house">House</option>
            <option value="room">Room</option>
            <option value="villa">Villa</option>
        </select>
    </div>
    <div class="ob-field">
        <label>Number of Rooms</label>
        <input type="number" name="number_of_rooms" min="1" value="1">
    </div>
    <div class="ob-form-footer">
        <button class="ob-btn ob-btn--primary" type="submit">List Property →</button>
    </div>
</form>
```

**Session data read:**
```
session.get("host_onboarding", {})  # contains step1 + step2
```

**_commit_host_onboarding() actions:**
1. Updates UserProfile:
   - full_name (if not already set from verified KYC)
   - id_type = "national_id"
   - id_number = step1["national_id"]
   - profile_completed = True
   - country (preserves verified KYC country if already set)
2. Maps property_type string to enum:
   - 'apartment' → AccommodationPropertyType.ENTIRE_PLACE
   - 'house' → AccommodationPropertyType.ENTIRE_PLACE
   - 'room' → AccommodationPropertyType.PRIVATE_ROOM
   - 'villa' → AccommodationPropertyType.ENTIRE_PLACE
   - etc.
3. Creates Property record with:
   - title = step2["property_name"]
   - slug = _generate_unique_slug(title)
   - address_line1 = step2["address"]
   - city = step2["city"]
   - country = step2["country"] (normalized ISO alpha-2)
   - property_type = selected enum value
   - bedrooms = int(step2["number_of_rooms"])
   - owner_user_id = user.id (internal FK)
   - verification_status = PENDING
   - status = DRAFT
   - base_price_per_night = 0
   - max_guests = int(number_of_rooms) * 2
   - description = step2["description"] or f"Property hosted by {step1['full_name']}"

**Redirect target on success:** `/host/dashboard` (accommodation.host_dashboard)

**Authorization:** `@login_required`; `_commit_host_onboarding` assumes identity already verified

---

### Step 4: Host Dashboard

**File:** `app/accommodation/routes.py:4115-4117`
```python
@accommodation_bp.route("/host/dashboard", endpoint="host_dashboard")
@login_required
def host_dashboard():
    host_info = _ensure_host_identity()
    if not host_info:
        return redirect(url_for("index"))
    # ... gather dashboard data from HostService ...
    # ... render accommodation/host/dashboard.html
```

**_ensure_host_identity() verification chain:**
1. `AccommodationIdentityService.can_host(current_user)` — verifies user can host
2. `AccommodationIdentityService.get_host_identity(current_user)` — gets host info
3. Check active context type via `app.auth.context.get_active_context(current_user)`:
   - `ContextType.PLATFORM` → return host_info (proceed)
   - Not `ContextType.ACCOMMODATION_HOST` → flash warning, return None
4. If individual host: verify `active_context.public_id == str(current_user.public_id)` — abort(403) if mismatch
5. If organisation host: query Organisation by id, verify `str(organisation.org_id) == str(active_context.public_id)` — abort(403) if mismatch

**Dashboard data rendered** in `accommodation/host/dashboard.html`:
- host_info, listings, bookings, recent_bookings
- stats, revenue_summary, monthly_revenue
- total_bookings_count, total_revenue, avg_rating, total_reviews
- avg_response_rate, total_views, conversion_rate
- insights, advanced_metrics, performance_metrics, guest_intelligence

**Authorization:** `@login_required` + `_ensure_host_identity()` comprehensive checks

---

## SESSION DATA FLOW SUMMARY

| Phase | Session Key | Data Stored |
|-------|------------|-------------|
| Initial | None | User is `@login_required` only |
| After Step 1 | `session["host_onboarding"]` | `{"step1": {full_name, national_id, proof_of_address}}` |
| After Step 2 (commit) | `session["host_onboarding"]` | Popped/removed after successful Property creation |
| At Dashboard | None (uses `current_user` + active context) | Identity verified via `_ensure_host_identity()` |

---

## AUTHORIZATION CHECKS THROUGHOUT FLOW

1. **`@login_required`** on: `choose_individual`, `host_onboarding` (both steps), all onboarding routes
2. **`_commit_host_onboarding()`** relies on `@login_required` → `current_user` available
3. **`/host/dashboard`** additional checks via `_ensure_host_identity()`:
   - `AccommodationIdentityService.can_host(current_user)` — host eligibility
   - Active context type validation (PLATFORM vs ACCOMMODATION_HOST)
   - Individual host: public_id matching current_user.public_id
   - Organisation host: org_id matching active_context.public_id
4. **Property creation** via `_commit_host_onboarding`:
   - `owner_user_id=user.id` — uses internal FK, not exposed public_id
   - Profile updates preserve verified KYC data (do not overwrite)

---

## KEY POINTS

- **Dual ID system**: Property uses `owner_user_id` (internal BigInteger FK); external references use `public_id` via `Property.public_id` UUID
- **Soft delete**: Property queries filter `is_deleted == False` (per AGENTS.md §19.3)
- **No ENUMs**: property_type stored as String + validation, not PostgreSQL ENUM (per AGENTS.md §14)
- **BaseModel**: All models inherit `app.models.base.BaseModel` (per AGENTS.md §13)
- **Check constraint sync**: Any CHECK constraint changes require `scripts/sync_check_constraints.py` (per AGENTS.md §20.2)
- **Wallet = CRITICAL**: Not directly involved in this flow, but host onboarding updates UserProfile which may affect wallet behavior (per AGENTS.md §18.1)
- **Forensic audit**: Host onboarding pathway should audit role changes and profile updates (per AGENTS.md §29)