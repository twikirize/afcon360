"""
Onboarding routes for post-registration user journey.
Users choose their path after OTP verification.
"""
from __future__ import annotations

import uuid
import secrets
from typing import Optional, Dict, Any
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
# Helper: get or create profile
# ---------------------------------------------------------------------------

def _get_or_create_profile(user) -> Any:
    """Return the UserProfile for *user*, creating one if it doesn't exist."""
    from app.profile.models import UserProfile, get_profile_by_user

    profile = get_profile_by_user(user.public_id)
    if not profile:
        profile = UserProfile(user_id=user.public_id)
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
    Post-verification landing page.
    Shows all available roles/services and lets user pick their path.
    Only shown once - if profile is already completed, redirect to dashboard.
    """
    from app.profile.models import get_profile_by_user

    profile = get_profile_by_user(current_user.public_id)

    if profile and profile.profile_completed:
        # Already onboarded - check for saved deep-link redirect
        post_redirect = session.pop("post_onboarding_redirect", None)
        if post_redirect:
            from app.auth.routes import is_safe_url
            if is_safe_url(post_redirect):
                return redirect(post_redirect)
        # Go to their dashboard
        from app.auth.routes import _dashboard_for_user
        return redirect(_dashboard_for_user(current_user))

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
# Fan / Explorer (1-step)
# ---------------------------------------------------------------------------

@onboarding_bp.route("/fan", methods=["GET", "POST"])
@login_required
def fan_onboarding():
    """Simple 1-step fan onboarding."""
    from app.profile.models import get_profile_by_user
    from app.identity.models.user import User

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        city = request.form.get("city", "").strip()
        country = request.form.get("country", "").strip()

        if not full_name:
            flash("Full name is required.", "danger")
            return render_template("onboarding/fan.html")

        db_user = User.query.filter_by(public_id=str(current_user.public_id)).first()
        if not db_user:
            flash("Session error. Please log in again.", "danger")
            return redirect(url_for("auth.login"))

        with db_transaction("Fan onboarding - profile update"):
            profile = get_profile_by_user(current_user.public_id)
            if profile:
                profile.full_name = full_name
                profile.city = city or profile.city
                profile.country = country or profile.country
                profile.profile_completed = True
                if not profile.display_name:
                    profile.display_name = full_name

        flash("Welcome to AFCON 360! Your account is ready.", "success")
        return redirect(url_for("fan.dashboard"))

    profile = get_profile_by_user(current_user.public_id)
    return render_template("onboarding/fan.html", profile=profile)


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
# Organisation onboarding (universal - type determines sub-path)
# ---------------------------------------------------------------------------

@onboarding_bp.route("/organisation", methods=["GET", "POST"])
@onboarding_bp.route("/organisation/step/<int:step>", methods=["GET", "POST"])
@login_required
def organisation_onboarding(step: int = 1):
    """Organisation registration wizard (transport / accommodation / consumer)."""
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

    return render_template(
        f"onboarding/organisation_step{step}.html",
        data=session.get("org_onboarding", {}),
        org_type=org_type,
        step=step,
    )


def _commit_organisation_onboarding(user, data: Dict[str, Any]) -> Any:
    """Atomic commit of organisation registration."""
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
        internal_org_id = org.id
        assign_org_role(
            user_id=user.id,
            org_id=internal_org_id,
            role_name="org_owner",
            assigned_by_id=user.id,
        )

        # Set user's default org
        from app.identity.models.user import User as UserModel
        db_user = UserModel.query.get(user.id)
        if db_user:
            db_user.default_org_id = org.id

        # Mark profile complete
        profile = _get_or_create_profile(user)
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
                _commit_host_onboarding(current_user, data)
                session.pop("host_onboarding", None)
                flash("Property listed successfully! We will verify your details.", "success")
                return redirect(url_for("accommodation.host.dashboard"))
            except Exception as e:
                current_app.logger.error(f"Host onboarding error: {e}")
                flash("Something went wrong. Please try again.", "danger")

    return render_template(
        f"onboarding/host_step{step}.html",
        data=session.get("host_onboarding", {}),
        step=step,
    )


def _commit_host_onboarding(user, data: Dict[str, Any]) -> None:
    """Atomic commit of host onboarding data."""
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
        profile.full_name = step1.get("full_name", profile.full_name)
        profile.id_type = "national_id"
        profile.id_number = step1.get("national_id")
        profile.profile_completed = True

        # Map property type string to enum
        property_type_map = {
            'apartment': AccommodationPropertyType.ENTIRE_PLACE,
            'house': AccommodationPropertyType.ENTIRE_PLACE,
            'room': AccommodationPropertyType.PRIVATE_ROOM,
            'villa': AccommodationPropertyType.ENTIRE_PLACE,
            'guesthouse': AccommodationPropertyType.ENTIRE_PLACE,
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
            property_type=selected_type,
            bedrooms=int(step2.get("number_of_rooms", 1)),
            owner_user_id=user.id,
            verification_status=AccommodationVerificationStatus.PENDING,
            status=AccommodationPropertyStatus.DRAFT,
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
