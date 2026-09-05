"""
Onboarding routes for post-registration user journey.
Users choose their path after OTP verification.
"""
from __future__ import annotations

import uuid
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
    return render_template("onboarding/choose_organisation.html")


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
                _commit_driver_onboarding(current_user, data)
                session.pop("driver_onboarding", None)
                flash(
                    "Driver registration submitted! We will verify your documents within 24 hours.",
                    "success",
                )
                return redirect(url_for("transport.driver_dashboard"))
            except Exception as e:
                current_app.logger.error(f"Driver onboarding error: {e}")
                flash("Something went wrong. Please try again.", "danger")

    return render_template(
        f"onboarding/driver_step{step}.html",
        data=session.get("driver_onboarding", {}),
        step=step,
    )


def _commit_driver_onboarding(user, data: Dict[str, Any]) -> None:
    """Atomic commit of all driver onboarding data."""
    from app.transport.models import DriverProfile, Vehicle, VerificationTier, ComplianceStatus, VehicleClass
    from app.auth.roles import assign_global_role
    from app.extensions import db
    from app.utils.transactions import db_transaction

    step1 = data.get("step1", {})
    step2 = data.get("step2", {})
    step3 = data.get("step3", {})

    with db_transaction("Driver onboarding commit"):
        # Update UserProfile
        profile = _get_or_create_profile(user)
        profile.full_name = step1.get("full_name", profile.full_name)
        profile.nationality = step1.get("nationality")
        profile.date_of_birth = step1.get("date_of_birth") or getattr(profile, "date_of_birth", None)
        profile.id_type = "national_id"
        profile.id_number = step1.get("national_id_number")
        profile.profile_completed = True
        if not profile.display_name:
            profile.display_name = step1.get("full_name", "")

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

        # Create Vehicle using existing model fields
        vehicle = Vehicle(
            owner_type='driver',
            owner_id=driver.id,
            make=step3.get("vehicle_make", ""),
            model=step3.get("vehicle_model", ""),
            year=int(step3["vehicle_year"]) if step3.get("vehicle_year") else datetime.now().year,
            license_plate=step3.get("plate_number", "").upper().strip(),
            vehicle_type=step3.get("vehicle_type", "sedan"),
            vehicle_class=VehicleClass.COMFORT,
            passenger_capacity=4,
            luggage_capacity=2,
            status='active',
            is_available=True,
        )
        db.session.add(vehicle)

        # Assign driver global role if it exists in the database
        try:
            assign_global_role(
                user_id=user.id,
                role_name="driver",
                assigned_by_id=user.id,
            )
        except ValueError:
            current_app.logger.warning("'driver' role not found in DB - skipping role assignment")


# ---------------------------------------------------------------------------
# Organisation onboarding (universal - type + optional provider capabilities)
# ---------------------------------------------------------------------------

# Canonical organisation types surfaced in the onboarding UI, drawn from the
# existing OrganizationType enum. Do NOT add/remove/rename enum members here.
_ORGANISATION_TYPE_LABELS = {
    "hotel": "Hotel",
    "restaurant": "Restaurant",
    "tour_operator": "Tour Operator",
    "travel_agency": "Travel Agency",
    "tourism_board": "Tourism Board",
    "accommodation_provider": "Accommodation Provider",
    "hostel": "Hostel",
    "vacation_rental": "Vacation Rental",
    "camping_site": "Camping Site",
    "event_management": "Event Management",
    "conference_center": "Conference Center",
    "venue_operator": "Venue Operator",
    "exhibition_org": "Exhibition Organisation",
    "sports_team": "Sports Team",
    "football_team": "Football Team",
    "sports_federation": "Sports Federation",
    "fitness_center": "Fitness Center",
    "recreation_facility": "Recreation Facility",
    "transport_company": "Transport Company",
    "airline": "Airline",
    "bus_operator": "Bus Operator",
    "taxi_service": "Taxi Service",
    "car_rental": "Car Rental",
    "corporate": "Corporate",
    "consulting_firm": "Consulting Firm",
    "marketing_agency": "Marketing Agency",
    "it_services": "IT Services",
    "government": "Government",
    "ngo": "NGO",
    "educational_institution": "Educational Institution",
    "healthcare_provider": "Healthcare Provider",
    "bank": "Bank",
    "insurance_company": "Insurance Company",
    "investment_firm": "Investment Firm",
    "fintech": "Fintech",
    "media_company": "Media Company",
    "broadcasting": "Broadcasting",
    "entertainment": "Entertainment",
    "publishing": "Publishing",
}

# Canonical provider capability codes (Stage 3 reference set).
_PROVIDER_CAPABILITY_LABELS = {
    "accommodation": "Accommodation",
    "transport": "Transport",
    "events": "Events",
    "tourism": "Tourism",
    "venue": "Venue",
}


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
                org = _commit_organisation_onboarding(current_user, data)
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
                return redirect(url_for("org.dashboard", org_id=org.org_id))
            except ValueError as e:
                flash(str(e), "danger")
            except Exception as e:
                current_app.logger.error(f"Org onboarding error: {e}")
                flash("Registration failed. Please try again.", "danger")

    org_type_label = _ORGANISATION_TYPE_LABELS.get(org_type, org_type or "")
    capability_labels = [
        _PROVIDER_CAPABILITY_LABELS.get(c, c) for c in capabilities
    ]

    return render_template(
        f"onboarding/organisation_step{step}.html",
        data=session.get("org_onboarding", {}),
        org_type=org_type,
        org_type_label=org_type_label,
        capabilities=capability_labels,
        step=step,
    )


def _commit_organisation_onboarding(user, data: Dict[str, Any]) -> Any:
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
    capabilities = _normalise_capabilities(step1.get("provider_capabilities"))

    if not org_type:
        raise ValueError("Organisation type is required.")

    # Validate the organisation type against the canonical enum and obtain the
    # enum member so business_category persists a native enum value correctly.
    # Normalize to lowercase to match the PostgreSQL enum values (which use
    # .value from OrganizationType, e.g. "hostel" not "HOSTEL").
    org_type_member = _validate_organisation_type(org_type.lower().strip())

    # Domain contract: a missing/blank optional organisation identifier
    # (tax_id) is "not provided" → None → SQL NULL.  An empty string would
    # collide on the (country, tax_id) unique constraint for every org in the
    # same country without a tax ID.
    tax_id = step1.get("tax_id") or None

    with db_transaction("Organisation onboarding commit"):
        # Create Organisation (business_category = organisation type)
        org = Organisation(
            org_id=str(uuid.uuid4()),  # public UUID
            legal_name=step1["legal_name"],
            country=step1["country"],
            registration_no=step1.get("registration_no"),
            tax_id=tax_id,
            contact_email=step1.get("contact_email"),
            contact_phone=step1.get("contact_phone"),
            website=step1.get("website"),
            primary_contact_user_id=user.id,  # internal FK
            verification_status="pending",
            lifecycle_state="registered",
            business_category=org_type_member,
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
            session["host_onboarding"] = data
            return redirect(url_for("onboarding.host_onboarding", step=2))

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
                _commit_host_onboarding(current_user, data)
                session.pop("host_onboarding", None)
                flash(
                    "Your host profile is ready! Add your first property from your dashboard.",
                    "success",
                )
                return redirect(url_for("accommodation.host_dashboard"))
            except ValueError as e:
                current_app.logger.warning(f"Host onboarding country error: {e}")
                flash(str(e), "danger")
            except Exception as e:
                current_app.logger.error(f"Host onboarding error: {e}")
                flash("Something went wrong. Please try again.", "danger")

    return render_template(
        f"onboarding/host_step{step}.html",
        data=session.get("host_onboarding", {}),
        step=step,
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
        Property, AccommodationPropertyType, AccommodationPropertyStatus,
        AccommodationVerificationStatus
    )
    from app.extensions import db
    from app.utils.transactions import db_transaction

    step1 = data.get("step1", {})
    step2 = data.get("step2", {})

    with db_transaction("Host onboarding commit"):
        # Update UserProfile
        profile = _get_or_create_profile(user)

        # Preserve verified full_name from KYC/profile - do not overwrite
        # if the profile already has a full_name set (from verified KYC)
        if not profile.full_name or profile.full_name == getattr(user, "username", None) or profile.full_name == "AFCON 360 User":
            profile.full_name = step1.get("full_name", profile.full_name)
        # If full_name already exists from verified KYC, keep it as-is

        profile.id_type = "national_id"
        profile.id_number = step1.get("national_id")
        profile.profile_completed = True

        # Preserve verified country from KYC/profile - do not overwrite
        # if the profile already has a country set from verified KYC
        if not profile.country:
            profile.country = step2.get("country", "")

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

        # Map property type string to enum
        property_type_map = {
            'apartment': AccommodationPropertyType.ENTIRE_PLACE,
            'house': AccommodationPropertyType.ENTIRE_PLACE,
            'room': AccommodationPropertyType.PRIVATE_ROOM,
            'villa': AccommodationPropertyType.ENTIRE_PLACE,
            'guesthouse': AccommodationPropertyType.ENTIRE_PLACE,
            'community_host': AccommodationPropertyType.COMMUNITY_HOST,
            'lodge': AccommodationPropertyType.LODGE,
            'hostel': AccommodationPropertyType.HOSTEL,
        }
        selected_type = property_type_map.get(
            step2.get("property_type", ""),
            AccommodationPropertyType.ENTIRE_PLACE
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

