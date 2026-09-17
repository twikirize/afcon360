"""
Onboarding routes for post-registration user journey.
Users choose their path after OTP verification.
"""
from __future__ import annotations

import uuid
import hashlib
import secrets
from typing import Optional, Dict, Any, List
from functools import wraps
from datetime import datetime, date
from decimal import Decimal

from flask import (
    Blueprint, current_app, flash, redirect, render_template,
    request, session, url_for,
)
from flask_login import current_user, login_required
from app.auth.context import switch_context
from app.identity.services.organisation_slug import ensure_unique_slug
from app.identity.services.provider_participation_service import (
    activate_individual_intention,
)

from app.extensions import db
from app.utils.transactions import db_transaction

onboarding_bp = Blueprint("onboarding", __name__, url_prefix="/onboarding")

# ---------------------------------------------------------------------------
# Decorator: require completed onboarding
# ---------------------------------------------------------------------------

def onboarding_completed(f):
    """Decorator to ensure user has completed the onboarding process."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.profile.models import get_profile_by_user
        # Assumes @login_required is used before this decorator
        profile = get_profile_by_user(current_user.public_id)
        if not profile or not profile.profile_completed:
            return redirect(url_for("onboarding.choose"))
        return f(*args, **kwargs)
    return decorated_function

# ---------------------------------------------------------------------------
# Helper: get or create profile
# ---------------------------------------------------------------------------

def _get_or_create_profile(user) -> Any:
    """Return the UserProfile for *user*, creating one if it doesn't exist."""
    from app.profile.models import UserProfile, get_profile_by_user

    profile = get_profile_by_user(user.public_id)
    if not profile:
        # ``full_name`` is NOT NULL (and has a non-empty CHECK constraint), so
        # a newly created profile must carry a non-empty value. Derive a safe
        # fallback from the user's username; onboarding forms that collect a
        # real name overwrite this before the transaction commits.
        fallback = getattr(user, "username", None) or "AFCON 360 User"
        profile = UserProfile(user_id=user.public_id, full_name=fallback)
        db.session.add(profile)
        db.session.flush()
    return profile


# ---------------------------------------------------------------------------
# Helper: reconcile submitted onboarding data against the canonical profile
# ---------------------------------------------------------------------------

def _reconcile_host_profile(profile, user, step1: Dict[str, Any], step2: Dict[str, Any]) -> None:
    """Reconcile submitted host-onboarding data against the canonical
    UserProfile.

    Architecture: onboarding is a completion/extension of existing
    UserProfile/KYC state, not a second KYC registration. The verified
    profile is the source of truth for the identity fields declared in
    ``IMMUTABLE_AFTER_VERIFICATION``. The rules applied here mirror that
    single authority (no second immutable-field list is introduced):

    - verified value present        -> keep (verified wins, submission ignored)
    - field missing on the profile  -> accept the submitted value after validation
    - unverified/editable value     -> may be replaced by the submitted value

    ``country`` is not in the immutable set (it stays editable even when
    verified), but a present verified country is still kept so onboarding
    cannot silently rewrite it. An empty submission never introduces a
    value (profile.country stays None until the user provides a country).
    """
    from app.profile.models import IMMUTABLE_AFTER_VERIFICATION

    # Assert the fields this helper reconciles are (and remain) the protected
    # identity authority — do not edit reconciled fields without updating the
    # immutable set.
    protected = IMMUTABLE_AFTER_VERIFICATION
    for field in ("full_name", "id_type", "id_number"):
        if field not in protected:
            raise ValueError(f"{field} is not covered by IMMUTABLE_AFTER_VERIFICATION")

    verified = profile.verification_status == "verified"

    # full_name — NOT NULL with a non-empty CHECK constraint; never write None.
    submitted_name = (step1.get("full_name") or "").strip()
    current_name = profile.full_name or ""
    if not verified and submitted_name and (
        not current_name
        or current_name == "AFCON 360 User"
        or current_name == getattr(user, "username", None)
    ):
        profile.full_name = submitted_name

    # id_type / id_number — written together, and only when neither exists yet.
    submitted_id = (step1.get("national_id") or "").strip()
    if not verified and not profile.id_type and not profile.id_number and submitted_id:
        profile.id_type = "national_id"
        profile.id_number = submitted_id

    # country — an empty submission must never become the default "UG".
    submitted_country = (step2.get("country") or "").strip()
    if not verified and not profile.country and submitted_country:
        profile.country = submitted_country


def _host_prefill_values(user) -> Dict[str, Any]:
    """Canonical profile values shown (and locked) on the host wizard.

    Onboarding extends existing UserProfile/KYC state: the GET forms render
    these values so verified/known identity data is visible but never
    re-collected. Verified profiles are rendered read-only on the protected
    fields (see host_step1.html).
    """
    from app.profile.models import get_profile_by_user

    profile = get_profile_by_user(user.public_id)
    if not profile:
        return {}
    return {
        "verified": profile.verification_status == "verified",
        "full_name": profile.full_name or "",
        "national_id": profile.id_number or "",
        "country": profile.country or "",
    }


# ---------------------------------------------------------------------------
# Landing page - choose your path
# ---------------------------------------------------------------------------

@onboarding_bp.route("/choose", methods=["GET"])
@login_required
def choose():
    """
    Canonical partner entry gate (/onboarding).

    This is NOT an account-creation step: every user reaching this page
    already has an AFCON 360 System User Account. It presents the two
    approved partner paths (Individual | Organisation). Partnership is
    optional and additive, so the page stays reachable even after a user has
    completed a profile and/or enabled other capabilities - it never redirects
    an already-onboarded user away from the gate.
    """
    post_redirect = session.pop("post_onboarding_redirect", None)
    if post_redirect:
        from app.auth.routes import is_safe_url
        if is_safe_url(post_redirect):
            return redirect(post_redirect)

    return render_template("onboarding/choose.html")


# ---------------------------------------------------------------------------
# Individual onboarding landing (after 2-card choice)
# ---------------------------------------------------------------------------

@onboarding_bp.route("/choose/individual", methods=["GET"])
@login_required
def choose_individual():
    """Individual onboarding landing page."""
    return render_template("onboarding/choose_individual.html")


# ---------------------------------------------------------------------------
# Organisation onboarding landing (after 2-card choice)
# ---------------------------------------------------------------------------

@onboarding_bp.route("/choose/organisation", methods=["GET"])
@login_required
def choose_organisation():
    """Organisation onboarding landing page."""
    from app.identity.services.organisation_classification_service import category_groups
    return render_template(
        "onboarding/choose_organisation.html",
        classification_categories=category_groups(),
        capability_options=_capability_options(),
    )


# ---------------------------------------------------------------------------
# Standard User (1-step)
# ---------------------------------------------------------------------------

@onboarding_bp.route("/standard", methods=["GET", "POST"])
@login_required
def standard_onboarding():
    """Simple 1-step standard user onboarding."""
    from app.profile.models import get_profile_by_user
    from app.identity.models.user import User

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        city = request.form.get("city", "").strip()
        country = request.form.get("country", "").strip()

        if not full_name:
            flash("Full name is required.", "danger")
            return render_template("onboarding/standard.html")

        db_user = User.query.filter_by(public_id=str(current_user.public_id)).first()
        if not db_user:
            flash("Session error. Please log in again.", "danger")
            return redirect(url_for("auth.login"))

        with db_transaction("Standard onboarding - profile update"):
            profile = get_profile_by_user(current_user.public_id)
            if profile:
                profile.full_name = full_name
                profile.city = city or profile.city
                profile.country = country or profile.country
                profile.profile_completed = True
                if not profile.display_name:
                    profile.display_name = full_name

        flash("Welcome to AFCON 360! Your profile is complete.", "success")
        return redirect(url_for("user.dashboard"))

    profile = get_profile_by_user(current_user.public_id)
    return render_template("onboarding/standard.html", profile=profile)


# ---------------------------------------------------------------------------
# Driver onboarding (3-step wizard)
# ---------------------------------------------------------------------------

@onboarding_bp.route("/driver", methods=["GET", "POST"])
@onboarding_bp.route("/driver/step/<int:step>", methods=["GET", "POST"])
@login_required
def driver_onboarding(step: int = 1):
    """Multi-step driver onboarding wizard."""
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
            if licence_file and licence_file.filename:
                # Save file - in production use a proper file storage service
                try:
                    from app.utils.file_upload import save_upload
                    url = save_upload(licence_file, folder="driver_licences")
                    data["step2"]["licence_document_url"] = url
                except ImportError:
                    # Fallback: store filename only for development
                    data["step2"]["licence_document_url"] = f"/uploads/{licence_file.filename}"
                except Exception as e:
                    current_app.logger.warning(f"Licence upload failed: {e}")
                    data["step2"]["licence_document_url"] = None
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
                driver = _commit_driver_onboarding(current_user, data)
                session.pop("driver_onboarding", None)

                # Verified -> switch into the Driver Workspace context. The
                # workspace is a PARTICIPATION surface (not a go-live surface):
                # entering it no longer requires KYC — identity verification,
                # compliance approval, licence validity, and (where required by
                # the operating mode) a vehicle are enforced by the transport
                # GO-LIVE capability (can_go_live) at "go online", never here.
                # See app/transport/services/go_live_service.py.
                switch_context(current_user, {
                    "type": "driver",
                    "public_id": str(
                        getattr(driver, "public_id", None) or driver.driver_code
                    ),
                })
                flash(
                    "Driver registration submitted! We will verify your documents within 24 hours.",
                    "success",
                )
                return redirect(url_for("transport.driver_dashboard"))
            except Exception as e:
                current_app.logger.error(f"Driver onboarding error: {e}")
                flash("Something went wrong. Please try again.", "danger")

    from app.profile.models import get_profile_by_user
    profile = get_profile_by_user(current_user.public_id)

    return render_template(
        f"onboarding/driver_step{step}.html",
        data=session.get("driver_onboarding", {}),
        step=step,
        profile=profile,
    )


def _commit_driver_onboarding(user, data: Dict[str, Any]) -> Any:
    """Atomic commit of all driver onboarding data.

    DriverProfile is created ONLY after validate_driver_eligibility. The
    transport provider intention is declared resource-free (PP row only). A
    Vehicle is a SEPARATE, later operation — never created here (stage 4B-5).
    """
    from app.transport.models import DriverProfile, VerificationTier, ComplianceStatus
    from app.extensions import db
    from app.utils.transactions import db_transaction

    # step1 (identity fields: full_name, nationality, date_of_birth,
    # national_id_number) is intentionally NOT persisted by driver onboarding.
    # Canonical identity lives in UserProfile; driver onboarding may read it
    # but must not write it. step1 data remains transport/session-only.
    step2 = data.get("step2", {})

    with db_transaction("Driver onboarding commit"):
        # Canonical UserProfile identity is a READ-ONLY source for driver
        # onboarding. Driver onboarding must never create, overwrite, or
        # complete canonical identity (full_name, nationality, date_of_birth,
        # id_type, id_number, display_name, profile_completed). Identity is
        # consumed from IdentityService / get_profile_by_user / UserProfile,
        # never written here.

        # Validate driver eligibility (domain authority) BEFORE creating the profile
        from app.transport.services.provider_service import get_provider_service
        get_provider_service().validate_driver_eligibility(user.id)

        # Guard against duplicate driver registration at the write point
        existing = DriverProfile.query.filter_by(
            user_id=user.id,
            is_deleted=False,
        ).first()
        if existing:
            raise ValueError("User is already registered as a driver")

        # Declare transport provider intention (resource-free) — INTENT only.
        from app.identity.models.organisation_provider_capability import (
            ProviderCapabilityCode,
        )
        from app.identity.services.provider_participation_service import (
            create_individual_intention,
        )
        create_individual_intention(user, ProviderCapabilityCode.TRANSPORT.value)

        # Create DriverProfile using existing model fields
        driver = DriverProfile(
            user_id=user.id,  # internal FK - correct
            license_number=step2.get("licence_number", ""),  # Will be encrypted by model
            license_expiry=(
                datetime.strptime(step2["licence_expiry"], "%Y-%m-%d")
                if step2.get("licence_expiry")
                else None
            ),
            verification_tier=VerificationTier.PENDING,
            compliance_status=ComplianceStatus.PENDING_REVIEW,
            is_online=False,
            is_available=False,
            languages_spoken=['en'],
            vehicle_classes=['comfort'],
            service_types=['on_demand'],
            operational_zones=['general'],
            max_passenger_capacity=4,
            max_luggage_capacity=2,
            commission_rate=Decimal('15.00'),
        )
        db.session.add(driver)
        db.session.flush()

        # The global 'driver' role does not exist and is intentionally not
        # seeded. Workspace access is governed by the Driver Workspace context
        # (context.py), not a global role, and operational actions are gated
        # independently by the transport service layer.
        return driver


# ---------------------------------------------------------------------------
# Organisation onboarding (universal - type + optional provider capabilities)
# ---------------------------------------------------------------------------

# Canonical provider capability codes (Stage 3 reference set).
_PROVIDER_CAPABILITY_LABELS = {
    "accommodation": "Accommodation",
    "transport": "Transport",
    "events": "Events",
    "tourism": "Tourism",
    "venue": "Venue",
}

# Display metadata keyed by ProviderCapabilityCode.value. New enum members
# gracefully degrade to the label + default icon via .get() fallbacks.
_CAPABILITY_METADATA = {
    "accommodation": {
        "description": "List and manage rooms, stays and bookings.",
        "icon": "bi bi-building",
    },
    "transport": {
        "description": "Manage vehicles, drivers, trips and transport services.",
        "icon": "bi bi-bus-front",
    },
    "events": {
        "description": "Create, organise and manage events and attendees.",
        "icon": "bi bi-calendar2-heart",
    },
    "tourism": {
        "description": "Offer tours, activities and local experiences.",
        "icon": "bi bi-globe-americas",
    },
    "venue": {
        "description": "Offer venue spaces for events and gatherings.",
        "icon": "bi bi-building-check",
    },
}


def _capability_options() -> List[Dict[str, str]]:
    """Data-driven provider capability options for the onboarding picker,
    derived from the canonical ``ProviderCapabilityCode`` enum.

    Adding a capability code to the enum automatically surfaces it here
    (labels/icons from the metadata above; graceful fallbacks when absent).
    """
    from app.identity.models.organisation_provider_capability import (
        ProviderCapabilityCode,
    )
    return [
        {
            "code": c.value,
            "label": _PROVIDER_CAPABILITY_LABELS.get(
                c.value, c.value.replace("_", " ").title()
            ),
            "description": _CAPABILITY_METADATA.get(c.value, {}).get(
                "description", ""
            ),
            "icon": _CAPABILITY_METADATA.get(c.value, {}).get(
                "icon", "bi bi-box"
            ),
        }
        for c in ProviderCapabilityCode
    ]


def _validate_organisation_type(value: str):
    """
    Return the canonical ``OrganizationType`` member for *value* or raise
    ValueError. ``business_category`` is a native PostgreSQL enum whose member
    names (e.g. ``HOTEL``) are derived from the enum *names*, so the existing
    canonical mechanism persists the ``OrganizationType`` member (not the
    lowercase ``.value`` string).
    """
    from app.identity.models.organization_types import OrganizationType
    try:
        return OrganizationType(value)
    except ValueError:
        raise ValueError("Please select a valid organisation type.")


def _normalise_capabilities(raw: Optional[List[str]]) -> List[str]:
    """Return a deduplicated list of valid provider-capability codes."""
    from app.identity.models.organisation_provider_capability import (
        ProviderCapabilityCode,
    )
    if not raw:
        return []
    valid = {c.value for c in ProviderCapabilityCode}
    seen = set()
    result = []
    for code in raw:
        code = str(code or "").strip()
        if code and code in valid and code not in seen:
            seen.add(code)
            result.append(code)
    return result


@onboarding_bp.route("/organisation", methods=["GET", "POST"])
@onboarding_bp.route("/organisation/step/<int:step>", methods=["GET", "POST"])
@login_required
def organisation_onboarding(step: int = 1):
    """
    Organisation registration wizard: one organisation type + zero or more
    optional provider capabilities (recorded as intent only).
    """
    # Step 0: organisation type + provider capabilities are chosen on the
    # landing form (/onboarding/choose/organisation). This route persists the
    # temporary onboarding state so the multi-step wizard can use it.
    if step == 1 and request.method == "GET":
        session["org_onboarding"] = {}

    if "org_onboarding" not in session:
        session["org_onboarding"] = {}

    # When posting the initial type+capability form (step defaults to 1 but the
    # form posts here from /onboarding/choose/organisation), capture the
    # selections and advance to step 1.
    if request.method == "POST" and "org_type" in request.form:
        step = 1
        org_type = request.form.get("org_type", "").strip()
        selected_caps = request.form.getlist("provider_capabilities")

        try:
            _validate_organisation_type(org_type)
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("onboarding.choose_organisation"))

        capabilities = _normalise_capabilities(selected_caps)
        session["org_onboarding_type"] = org_type
        session["org_onboarding_capabilities"] = capabilities
        session["org_onboarding"] = {}
        return redirect(url_for("onboarding.organisation_onboarding", step=1))

    org_type = request.args.get("type", session.get("org_onboarding_type"))
    capabilities = session.get("org_onboarding_capabilities", [])

    if step == 1 and request.method == "GET":
        if not org_type:
            flash("Please choose an organisation type first.", "danger")
            return redirect(url_for("onboarding.choose_organisation"))

    if request.method == "POST":
        data = session["org_onboarding"]

        if step == 1:
            data["step1"] = {
                "full_name": request.form.get("full_name", "").strip(),
                "legal_name": request.form.get("legal_name", "").strip(),
                "country": request.form.get("country", "").strip(),
                "registration_no": request.form.get("registration_no", "").strip(),
                "tax_id": request.form.get("tax_id", "").strip() or None,
                "contact_email": request.form.get("contact_email", "").strip(),
                "contact_phone": request.form.get("contact_phone", "").strip(),
                "website": request.form.get("website", "").strip(),
                "org_type": org_type,
                "provider_capabilities": capabilities,
            }
            session["org_onboarding"] = data
            return redirect(url_for("onboarding.organisation_onboarding", step=2))

        elif step == 2:
            try:
                registration_document_ref = None
                registration_document = request.files.get("registration_document")
                if registration_document and registration_document.filename:
                    registration_document_ref = _store_onboarding_registration_document(
                        registration_document
                    )
                org = _commit_organisation_onboarding(
                    current_user, data,
                    registration_document_ref=registration_document_ref,
                )
                session.pop("org_onboarding", None)
                session.pop("org_onboarding_type", None)
                session.pop("org_onboarding_capabilities", None)

                # Switch context to the new org immediately
                session["current_context"] = "organization"
                session["current_org_id"] = org.org_id
                session["current_org_name"] = org.legal_name

                flash(
                    f"Organisation '{org.legal_name}' registered successfully!",
                    "success",
                )
                return redirect(url_for("org.dashboard", org_id=org.slug))
            except ValueError as e:
                flash(str(e), "danger")
            except Exception as e:
                current_app.logger.error(f"Org onboarding error: {e}")
                if "StringDataRightTruncation" in str(type(e).__name__) or "value too long" in str(e).lower():
                    flash("One or more fields contain values that are too long. Please check your inputs (e.g. use a 2-letter country code like UG).", "danger")
                elif "IntegrityError" in str(type(e).__name__) or "unique" in str(e).lower():
                    flash("An organisation with similar details already exists.", "danger")
                else:
                    flash("Registration failed. Please try again.", "danger")

    from app.identity.services.organisation_classification_service import label_for
    org_type_label = label_for(org_type)
    capability_labels = [
        _PROVIDER_CAPABILITY_LABELS.get(c, c) for c in capabilities
    ]

    from app.profile.models import get_profile_by_user
    profile = get_profile_by_user(current_user.public_id)

    return render_template(
        f"onboarding/organisation_step{step}.html",
        data=session.get("org_onboarding", {}),
        org_type=org_type,
        org_type_label=org_type_label,
        capabilities=capability_labels,
        step=step,
        profile=profile,
    )


def _store_onboarding_registration_document(file_storage) -> Optional[str]:
    """Persist the uploaded registration certificate via the canonical
    media/KYB path (mirrors app/kyc/routes.py ``_save_uploaded_file``).

    - Virus scan / quota / forensic audit run inside ``MediaService.upload_photo``.
    - Prefers an immediate URL, then resolves a servable URL from the Media
      record, and finally degrades to None when storage is unavailable (the
      wizard still completes; the document row is simply skipped).
    - Validation/scan rejections (``ValueError``) propagate so the user sees
      why their file was refused.
    """
    from app.media.models import Media
    from app.media.service import MediaService
    from app.media.storage import get_storage_backend

    filename = getattr(file_storage, "filename", "") or ""
    if not filename:
        return None
    try:
        result = MediaService.upload_photo(
            file=file_storage,
            module="kyc",
            entity_id=str(current_user.public_id),
            uploader_user_id=current_user.id,
        )
        urls = result.get("urls") or {}
        url = urls.get("original") or (list(urls.values())[0] if urls else None)
        if url:
            return url
        media_id = result.get("media_id")
        if media_id:
            media = db.session.query(Media).filter(
                Media.public_id == media_id, Media.is_deleted == False
            ).first()
            if media and media.storage_key:
                try:
                    return get_storage_backend().get_url(media.storage_key)
                except Exception:
                    pass
        return None
    except ValueError:
        raise
    except Exception as e:
        current_app.logger.warning(f"Registration document upload failed: {e}")
        # MediaService may have left a pending Media insert / written an
        # orphan object when the async enqueue failed; clear the session so
        # the organisation commit below starts clean.
        db.session.rollback()
        return None


def _commit_organisation_onboarding(
    user,
    data: Dict[str, Any],
    registration_document_ref: Optional[str] = None,
) -> Any:
    """
    Atomic commit of organisation registration:
      Organisation + OrganisationMember + org_owner + provider participation
      rows (status=intent) + default org + context within a single transaction.
    Any failure rolls the whole thing back — no partial organisation.
    """
    from app.identity.models.organisation import Organisation
    from app.identity.models.organisation_member import (
        OrganisationMember, OrgRole, OrgUserRole,
    )
    from app.identity.services.organisation_role_provisioning import (
        provision_organisation_roles,
    )
    from app.identity.services.provider_participation_service import (
        create_organisation_intention,
    )
    from app.profile.models import get_profile_by_user
    from app.extensions import db
    from app.utils.transactions import db_transaction

    step1 = data.get("step1", {})
    org_type = step1.get("org_type")
    raw_capabilities = step1.get("provider_capabilities") or []
    chosen_none = "none" in raw_capabilities
    capabilities = _normalise_capabilities(raw_capabilities)

    if not org_type:
        raise ValueError("Organisation type is required.")

    # Validate the organisation type against the canonical enum and obtain the
    # enum member. The CANONICAL write target is the frozen classification
    # catalogue: organisation.organisation_type_code stores the lowercase
    # ".value" string (e.g. "hostel"), which 1:1 maps organisation_types.code
    # (see get_effective_org_type). The legacy business_category enum column is
    # intentionally NO LONGER WRITTEN (Stage 4B classification redesign).
    org_type_member = _validate_organisation_type(org_type.lower().strip())

    # Validate country — auto-convert full names to ISO alpha-2.
    from app.utils.validators import resolve_country_code
    country_code = resolve_country_code(step1.get("country", ""))
    if not country_code:
        raise ValueError(
            "Country must be a valid country name or 2-letter ISO code "
            "(e.g. 'Uganda' or 'UG')."
        )

    # Domain contract: a missing/blank optional organisation identifier
    # (tax_id) is "not provided" → None → SQL NULL.  An empty string would
    # collide on the (country, tax_id) unique constraint for every org in the
    # same country without a tax ID.
    tax_id = step1.get("tax_id") or None

    with db_transaction("Organisation onboarding commit"):
        # Create Organisation (organisation_type_code = canonical type code)
        org = Organisation(
            org_id=str(uuid.uuid4()),  # public UUID
            legal_name=step1["legal_name"],
            country=country_code,
            registration_no=step1.get("registration_no"),
            tax_id=tax_id,
            contact_email=step1.get("contact_email"),
            contact_phone=step1.get("contact_phone"),
            website=step1.get("website"),
            primary_contact_user_id=user.id,  # internal FK
            verification_status="pending",
            lifecycle_state="registered",
            organisation_type_code=org_type_member.value,
            meta={"provider_capabilities_none": chosen_none},
        )
        ensure_unique_slug(org)
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

        # Create provider participation rows (status = intent only) via the
        # canonical ProviderParticipation service (Stage 4B-3 — OPC is no
        # longer a production write target).
        # Created BEFORE assign_org_role (which commits internally) so that a
        # participation persistence failure rolls back the whole organisation,
        # member, and participations together — never a partial organisation.
        for code in capabilities:
            create_organisation_intention(user, org.id, code)
        db.session.flush()

        # Provision ALL organisation roles (consistent with
        # create_organization path).  commit=False runs as a nested
        # savepoint inside the outer db_transaction; the outer commit
        # finalises everything atomically.
        provision_organisation_roles(org, commit=False)
        db.session.expire_all()

        # Assign creator → org_owner directly within the outer transaction.
        org_owner_role = OrgRole.query.filter_by(
            organisation_id=org.id, name="org_owner",
        ).first()
        if org_owner_role is None:
            raise RuntimeError(
                "org_owner OrgRole not found after provisioning for "
                f"organisation {org.id}"
            )
        db.session.add(
            OrgUserRole(
                organisation_member_id=member.id,
                role_id=org_owner_role.id,
                assigned_by=user.id,
            )
        )
        db.session.flush()

        # Set user's default org
        from app.identity.models.user import User as UserModel
        db_user = db.session.get(UserModel, user.id)
        if db_user:
            db_user.default_org_id = org.id

        # Mark profile complete
        profile = _get_or_create_profile(user)
        full_name = step1.get("full_name") or getattr(user, "username", None) or ""
        if not profile.full_name:
            profile.full_name = full_name or org.legal_name
        profile.profile_completed = True

        # Persist the uploaded registration document (optional) into the
        # canonical, compliance-reviewed KYB document store. The file itself is
        # stored by MediaService before this transaction; only the reference
        # row is added here so the whole organisation commit stays atomic.
        if registration_document_ref:
            from app.identity.models.kyb import OrganisationKYBDocument
            db.session.add(
                OrganisationKYBDocument(
                    organisation_id=org.id,
                    document_type="registration_certificate",
                    storage_key=registration_document_ref,
                    checksum=hashlib.md5(
                        registration_document_ref.encode()
                    ).hexdigest(),
                    verification_status="pending",
                )
            )

    return org


def _generate_unique_slug(base: str) -> str:
    """Generate a URL-safe unique slug from a title."""
    import re, uuid
    slug = re.sub(r"[^\w\s-]", "", base).strip().lower()
    slug = re.sub(r"[-\s]+", "-", slug)
    suffix = str(uuid.uuid4())[:8]
    return f"{slug}-{suffix}"[:220]


# ---------------------------------------------------------------------------
# Accommodation Host onboarding (2-step)
# ---------------------------------------------------------------------------

from app.accommodation.utils import normalize_country

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
            # The former wizard collected country/property details on a second
            # step. Host onboarding is now a single identity step: the property
            # is captured later in the accommodation "Add Listing" flow, which
            # owns Property creation (save_as_intent_only). The only step-2
            # value that was actually persisted to the profile — country — is
            # folded into step 1 here so nothing is lost.
            submitted_country = request.form.get("country", "").strip()
            data["step2"] = {"country": submitted_country}
            if submitted_country:
                data["step2"]["country"] = normalize_country(submitted_country)
            session["host_onboarding"] = data

            try:
                _commit_host_onboarding(current_user, data)
                session.pop("host_onboarding", None)

                if not current_user.is_fully_verified():
                    # KYC gate: host activation is only valid for an
                    # identity-verified individual — AccommodationIdentityService.
                    # can_host (the source of the accommodation_host context used
                    # by switch_context below) requires is_fully_verified().
                    # Unverified individuals keep their saved host profile and
                    # provider intention but are routed to the KYC document flow
                    # (owned by the KYC domain) and return here once compliance
                    # approves their verification.
                    flash(
                        "Your host profile is saved. To start hosting, complete "
                        "identity (KYC) verification first.",
                        "info",
                    )
                    return redirect(url_for("kyc.upload"))

                # Verified -> switch into the host context and activate the
                # individual provider intention so the capability gate passes
                # (is_capability_operational requires ACTIVATED status).
                switch_context(current_user, {
                    "type": "accommodation_host",
                    "public_id": str(current_user.public_id),
                })
                from app.identity.services.provider_participation_service import (
                    ProviderCapabilityCode,
                )
                activate_individual_intention(
                    current_user, ProviderCapabilityCode.ACCOMMODATION.value,
                )
                flash(
                    "Your host profile is ready! Add your first property from your dashboard.",
                    "success",
                )
                return redirect(url_for("accommodation.host_dashboard"))
            except ValueError as e:
                # Intentional validation failures (implicit immutable-field
                # protection, invalid input) re-render with feedback instead
                # of a masked 200 success.
                current_app.logger.warning(f"Host onboarding validation error: {e}")
                flash(str(e), "danger")
            # Unexpected exceptions are intentionally NOT caught here: they
            # propagate to the app-wide error handler (generic 500 with
            # audit) instead of being masked as a successful 200.

        elif step == 2:
            # Legacy step 2 retired: property details are captured via the
            # accommodation "Add Listing" flow, not an onboarding side effect.
            # Preserve a redirect to the dashboard for any stale callers.
            session.pop("host_onboarding", None)
            return redirect(url_for("accommodation.host_dashboard"))

    # Pre-fill the wizard from the canonical profile so onboarding extends
    # existing KYC state instead of asking for it again.
    prefill = _host_prefill_values(current_user)

    # Step 2 retired: property details are captured via the accommodation
    # "Add Listing" flow, not an onboarding side effect. Stale direct links to
    # step 2 fall through to the host dashboard.
    if step != 1:
        return redirect(url_for("accommodation.host_dashboard"))

    return render_template(
        "onboarding/host_step1.html",
        data=session.get("host_onboarding", {}),
        step=step,
        profile=prefill,
    )


def _commit_host_onboarding(user, data: Dict[str, Any], save_as_intent_only: bool = True) -> None:
    """Atomic commit of host onboarding data.

    DEFAULT behavior (save_as_intent_only=True): updates the UserProfile and
    records the accommodation provider intention in the universal
    ProviderParticipation registry (create_individual_intention →
    individual / accommodation / INTENT) — the expression of accommodation
    provider participation is separated from domain resource creation.
    Property creation is owned by the Accommodation domain via the host
    dashboard "Add Listing" flow (host_create_listing →
    HostService.create_property).

    Passing *save_as_intent_only=False* preserves the legacy behavior of
    creating a Property record as an onboarding side effect (test/back-compat
    only).
    """
    from app.profile.models import get_profile_by_user
    from app.accommodation.models.property import (
        Property, AccommodationPropertyType, AccommodationListingType,
        AccommodationPropertyStatus, AccommodationVerificationStatus
    )
    from app.extensions import db
    from app.utils.transactions import db_transaction

    step1 = data.get("step1", {})
    step2 = data.get("step2", {})

    with db_transaction("Host onboarding commit"):
        # Update UserProfile
        profile = _get_or_create_profile(user)

        # Reconcile submitted onboarding data against the canonical profile:
        # verified KYC fields win, missing fields accept submitted values,
        # and unverified/editable fields may be replaced after validation.
        # This keeps onboarding a completion/extension of existing KYC state
        # and never triggers the immutable-after-verification failure.
        _reconcile_host_profile(profile, user, step1, step2)
        profile.profile_completed = True

        # Universal provider participation: record the accommodation
        # provider intention (idempotent). This is the first production use
        # of the ProviderParticipation registry. It creates NO domain
        # resource — Property creation stays with the Accommodation domain
        # (host dashboard "Add Listing" flow).
        from app.identity.services.provider_participation_service import (
            create_individual_intention,
        )
        from app.identity.models.organisation_provider_capability import (
            ProviderCapabilityCode,
        )
        create_individual_intention(
            user, ProviderCapabilityCode.ACCOMMODATION.value,
        )

        # When saving as intent only, skip Property creation entirely.
        # The accommodation provider intention is recorded through the
        # UserProfile update AND the ProviderParticipation row above, but no
        # domain resource is persisted.
        if save_as_intent_only:
            return

        # Map legacy property-type strings to (structure, occupancy). The
        # schema split property_type (what the building is) from listing_type
        # (what the guest rents). community_host is preserved structurally as
        # a house renting the entire place.
        property_type_map = {
            'apartment': (AccommodationPropertyType.APARTMENT, AccommodationListingType.ENTIRE_PLACE),
            'house': (AccommodationPropertyType.HOUSE, AccommodationListingType.ENTIRE_PLACE),
            'room': (AccommodationPropertyType.HOUSE, AccommodationListingType.PRIVATE_ROOM),
            'villa': (AccommodationPropertyType.VILLA, AccommodationListingType.ENTIRE_PLACE),
            'guesthouse': (AccommodationPropertyType.GUESTHOUSE, AccommodationListingType.ENTIRE_PLACE),
            'community_host': (AccommodationPropertyType.HOUSE, AccommodationListingType.ENTIRE_PLACE),
            'lodge': (AccommodationPropertyType.LODGE, AccommodationListingType.ENTIRE_PLACE),
            'hostel': (AccommodationPropertyType.HOSTEL, AccommodationListingType.ENTIRE_PLACE),
        }
        selected_type, selected_listing = property_type_map.get(
            step2.get("property_type", ""),
            (AccommodationPropertyType.HOUSE, AccommodationListingType.ENTIRE_PLACE)
        )

        # Create Property record using correct model fields
        title = step2.get("property_name", "")
        property_record = Property(
            title=title,
            slug=_generate_unique_slug(title),
            address_line1=step2.get("address", ""),
            city=step2.get("city", ""),
            country=step2.get("country", ""),
            property_type=selected_type.value,
            listing_type=selected_listing.value,
            event_metadata={"community_host": True} if step2.get("property_type") == "community_host" else None,
            bedrooms=int(step2.get("number_of_rooms", 1)),
            owner_user_id=user.id,
            verification_status=AccommodationVerificationStatus.PENDING.value,
            status=AccommodationPropertyStatus.DRAFT.value,
            base_price_per_night=Decimal('0'),
            max_guests=int(step2.get("number_of_rooms", 1)) * 2,
            description=step2.get("description") or f"Property hosted by {step1.get('full_name', '')}",
        )
        db.session.add(property_record)


# ---------------------------------------------------------------------------
# Event Organiser onboarding (1-step)
# ---------------------------------------------------------------------------

@onboarding_bp.route("/event-organiser", methods=["GET", "POST"])
@login_required
def event_organiser_onboarding():
    """Simple 1-step event organiser onboarding."""
    from app.auth.roles import assign_global_role

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        organisation_name = request.form.get("organisation_name", "").strip()
        contact_email = request.form.get("contact_email", "").strip()

        if not full_name:
            flash("Full name is required.", "danger")
            return render_template("onboarding/event_organiser.html")

        try:
            with db_transaction("Event organiser onboarding commit"):
                profile = _get_or_create_profile(current_user)
                profile.full_name = full_name
                profile.profile_completed = True

                # Assign event_manager role
                assign_global_role(
                    user_id=current_user.id,
                    role_name="event_manager",
                    assigned_by_id=current_user.id,
                )

            flash("You are now an event organiser!", "success")
            return redirect(url_for("events.my_events"))
        except Exception as e:
            current_app.logger.error(f"Event organiser onboarding error: {e}")
            flash("Something went wrong. Please try again.", "danger")

    return render_template("onboarding/event_organiser.html")

