from flask import Blueprint, render_template, session, redirect, url_for, flash, current_app, request
from flask_login import current_user, login_required
from app.identity.models.user import User
from app.profile.models import UserProfile, get_profile_by_user
from app.extensions import db
from app.auth.kyc_compliance import calculate_kyc_tier, get_user_limits, TIER_REQUIREMENTS, TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD, TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE
from app.wallet.services.wallet_service import WalletService
import math

profile_bp = Blueprint("profile", __name__)

@profile_bp.route("/profile/<public_id>")
def view_profile(public_id):
    user = User.query.filter_by(public_id=public_id).first()
    if not user:
        flash("User not found.", "warning")
        return redirect(url_for("main.home"))

    profile = get_profile_by_user(user.public_id)

    public_info = {
        'full_name': getattr(profile, 'full_name', None) if profile else None,
        'avatar_url': getattr(profile, 'avatar_url', None) if profile else None,
        'bio': getattr(profile, 'bio', None) if profile else None,
        'city': getattr(profile, 'city', None) if profile else None,
        'country': getattr(profile, 'country', None) if profile else None,
        'joined_date': getattr(user, 'created_at', None),
    }

    # Get user roles
    user_roles = []
    # Check for owner/admin roles
    if user.is_app_owner():
        user_roles.append('owner')
    # Check for global admin role
    if user.has_global_role('admin'):
        user_roles.append('admin')
    # Check for driver role (assuming there's a 'driver' role)
    if user.has_global_role('driver'):
        user_roles.append('driver')
    # Check for host role
    if user.has_global_role('host'):
        user_roles.append('host')
    # Check for other roles
    # Add organization-specific roles if needed

    # Get real stats
    stats = {
        'events_count': 0,
        'reviews_count': 0,
        'stays_count': 0,
        'trips_count': 0,
    }

    # Add role-specific stats
    if 'driver' in user_roles:
        # Get driver-specific stats
        try:
            from app.transport.models import DriverVehicleHistory
            driver_stats = DriverVehicleHistory.query.filter_by(driver_id=user.id).first()
            if driver_stats:
                stats['driver_trips'] = 0  # Placeholder
                stats['driver_rating'] = 4.5  # Placeholder
        except:
            pass

    if 'host' in user_roles:
        # Get host-specific stats
        try:
            from app.accommodation.models.property import Property
            host_properties = Property.query.filter_by(owner_user_id=user.id).count()
            stats['host_properties'] = host_properties
        except:
            pass

    # Get recent activity from audit logs
    recent_activity = []
    try:
        from app.audit.models import AuditLog
        logs = AuditLog.query.filter_by(user_id=user.id).order_by(
            AuditLog.created_at.desc()
        ).limit(5).all()

        for log in logs:
            recent_activity.append({
                'icon': 'activity',
                'title': log.action.replace('_', ' ').title(),
                'description': log.resource_type or '',
                'time': log.created_at.strftime('%b %d, %Y')
            })
    except:
        pass

    # Badges
    badges = []
    if profile and profile.verification_status == 'verified':
        badges.append({'icon': 'check-circle-fill', 'name': 'Verified'})
    if stats['events_count'] >= 5:
        badges.append({'icon': 'calendar-check', 'name': '5+ Events'})
    # Add role badges
    for role in user_roles:
        badges.append({'icon': 'person-badge', 'name': role.title()})

    is_own_profile = current_user.is_authenticated and current_user.public_id == public_id

    return render_template(
        "profile/public.html",
        user=user,
        profile=profile,
        public_info=public_info,
        stats=stats,
        recent_activity=recent_activity,
        badges=badges,
        is_own_profile=is_own_profile,
        user_roles=user_roles
    )

@profile_bp.route("/account")
@login_required
def account_overview():
    """
    User profile overview page showing:
    - User avatar, username, email, phone
    - KYC tier with progress bar to next tier
    - Verification status
    - Quick action cards for Wallet, Bookings, Trips, Settings
    - Links to complete profile if profile_completed=False
    """
    # Get current user
    user = current_user

    # Get user profile
    profile = get_profile_by_user(user.public_id)

    # Calculate KYC tier information
    kyc_info = calculate_kyc_tier(user.id)  # Pass internal BIGINT id
    current_tier = kyc_info["tier"]
    tier_name = kyc_info["tier_name"]
    missing_requirements = kyc_info.get("missing_requirements", [])

    # Get user limits for current tier
    limits_info = get_user_limits(user.id)

    # Calculate progress to next tier
    next_tier = current_tier + 1 if current_tier < 5 else current_tier
    progress_percentage = 0
    next_tier_name = ""
    next_tier_requirements = []

    if current_tier < 5:
        next_tier_name = TIER_REQUIREMENTS.get(next_tier, {}).get("name", "")
        next_tier_requirements = TIER_REQUIREMENTS.get(next_tier, {}).get("required_documents", [])

        # Calculate progress based on current tier requirements met
        current_requirements = TIER_REQUIREMENTS.get(current_tier, {}).get("required_documents", [])
        if current_requirements:
            # For simplicity, assume each requirement is equally weighted
            progress_percentage = min(100, int((len(current_requirements) - len(missing_requirements)) / len(current_requirements) * 100))
        else:
            progress_percentage = 100 if current_tier > 0 else 0
    else:
        progress_percentage = 100

    # Get wallet balance if wallet exists
    wallet_balance = None
    wallet_currency = None
    try:
        wallet_service = WalletService()
        wallet_info = wallet_service.get_balance(user.id)
        if wallet_info.get("exists"):
            wallet_balance = wallet_info.get("balance_home", "0.00")
            wallet_currency = wallet_info.get("home_currency", "USD")
    except Exception as e:
        current_app.logger.warning(f"Could not fetch wallet balance: {e}")
        wallet_balance = "0.00"
        wallet_currency = "USD"

    # Calculate profile completion percentage (use model's method for consistency)
    profile_completion = profile.get_completion_percentage() if profile else 0

    # Get recent bookings count (placeholder - would need actual query)
    recent_bookings_count = 0
    try:
        from app.accommodation.models.booking import AccommodationBooking
        recent_bookings_count = AccommodationBooking.query.filter_by(
            guest_user_id=user.id
        ).count()
    except Exception as e:
        current_app.logger.warning(f"Could not fetch bookings count: {e}")

    # Get user roles
    user_roles = []
    # Check for owner/admin roles
    if user.is_app_owner():
        user_roles.append('owner')
    # Check for global admin role
    if user.has_global_role('admin'):
        user_roles.append('admin')
    # Check for driver role
    if user.has_global_role('driver'):
        user_roles.append('driver')
    # Check for host role
    if user.has_global_role('host'):
        user_roles.append('host')

    # Get role-specific stats
    role_stats = {}
    if 'driver' in user_roles:
        try:
            from app.transport.models import DriverVehicleHistory
            driver_stats = DriverVehicleHistory.query.filter_by(driver_id=user.id).first()
            if driver_stats:
                role_stats['driver_trips'] = 0  # Placeholder
                role_stats['driver_rating'] = 4.5
        except:
            pass

    if 'host' in user_roles:
        try:
            from app.accommodation.models.property import Property
            host_properties = Property.query.filter_by(owner_user_id=user.id).count()
            role_stats['host_properties'] = host_properties
        except:
            pass

    # Prepare data for template
    context = {
        'user': user,
        'profile': profile,
        'current_tier': current_tier,
        'tier_name': tier_name,
        'tier_display': f"Tier {current_tier}: {tier_name}",
        'progress_percentage': progress_percentage,
        'next_tier': next_tier if current_tier < 5 else None,
        'next_tier_name': next_tier_name,
        'missing_requirements': missing_requirements,
        'next_tier_requirements': next_tier_requirements,
        'limits': limits_info,
        'wallet_balance': wallet_balance,
        'wallet_currency': wallet_currency,
        'profile_completion': profile_completion,
        'recent_bookings_count': recent_bookings_count,
        'verification_status': profile.verification_status if profile else 'pending',
        'kyc_level': profile.kyc_level if profile else 'basic',
        'user_roles': user_roles,
        'role_stats': role_stats,
    }

    return render_template("profile/account.html", **context)

@profile_bp.route("/profile/me")
@login_required
def my_public_profile():
    """Redirect to the current user's public profile page"""
    return redirect(url_for('profile.view_profile', public_id=current_user.public_id))

@profile_bp.route("/profile/overview")
@login_required
def profile_overview():
    """Alias for account overview"""
    return redirect(url_for('profile.account_overview'))

@profile_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    """Edit profile page with form for updating personal information"""
    from app.profile.models import IMMUTABLE_AFTER_VERIFICATION

    # Get current user's profile
    profile = get_profile_by_user(current_user.public_id)

    # If profile doesn't exist, create a new one
    if not profile:
        # Set a default full_name to satisfy the NOT NULL constraint
        # Use the user's email or a placeholder
        default_name = current_user.email if current_user.email else "User"
        profile = UserProfile(
            user_id=current_user.public_id,
            full_name=default_name,
            phone_number="",
            address="",
            city="",
            country="",
            verification_status="pending",
            kyc_level="basic"
        )
        db.session.add(profile)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating profile: {str(e)}", "danger")
            return redirect(url_for("profile.account_overview"))

    # Calculate current completion percentage
    completion_percentage = profile.get_completion_percentage()

    if request.method == "POST":
        # Track which fields were attempted to be changed
        attempted_changes = {}
        errors = []

        # Check if profile is verified for immutability enforcement
        is_verified = profile.verification_status == "verified"

        # Update mutable fields (can always be changed)
        profile.phone_number = request.form.get("phone_number", "").strip()
        profile.address = request.form.get("address", "").strip()
        profile.city = request.form.get("city", "").strip()
        profile.country = request.form.get("country", "").strip()

        # fan_team is always mutable - not in IMMUTABLE_AFTER_VERIFICATION
        fan_team = request.form.get("fan_team", "").strip() or None
        profile.fan_team = fan_team

        # Update email (always save the value, verification is separate)
        new_email = request.form.get("email", "").strip()
        if new_email and new_email != profile.email:
            if is_verified:
                errors.append("Email cannot be changed after verification. Please contact support.")
            else:
                profile.email = new_email
                profile.email_verified = False  # Require re-verification
        elif new_email and not profile.email:
            # Setting email for the first time
            profile.email = new_email
            profile.email_verified = False

        # Handle immutable fields (only if not verified)
        if not is_verified:
            profile.full_name = request.form.get("full_name", "").strip()
            
            # Handle date_of_birth
            dob_str = request.form.get("date_of_birth", "").strip()
            if dob_str:
                try:
                    from datetime import datetime
                    profile.date_of_birth = datetime.strptime(dob_str, "%Y-%m-%d").date()
                except ValueError:
                    errors.append("Invalid date format for date of birth. Use YYYY-MM-DD.")
            
            profile.gender = request.form.get("gender", "").strip() or None
            profile.nationality = request.form.get("nationality", "").strip()
        else:
            # For verified profiles, check if user tried to change immutable fields
            old_full_name = profile.full_name
            new_full_name = request.form.get("full_name", "").strip()
            if new_full_name != old_full_name:
                attempted_changes["full_name"] = {"old": old_full_name, "new": new_full_name}
            
            old_dob = profile.date_of_birth.isoformat() if profile.date_of_birth else None
            new_dob = request.form.get("date_of_birth", "").strip()
            if new_dob != old_dob:
                attempted_changes["date_of_birth"] = {"old": old_dob, "new": new_dob}
            
            old_gender = profile.gender
            new_gender = request.form.get("gender", "").strip() or None
            if new_gender != old_gender:
                attempted_changes["gender"] = {"old": old_gender, "new": new_gender}
            
            old_nationality = profile.nationality
            new_nationality = request.form.get("nationality", "").strip()
            if new_nationality != old_nationality:
                attempted_changes["nationality"] = {"old": old_nationality, "new": new_nationality}

        # If there were attempted changes to immutable fields, log and error
        if attempted_changes:
            from app.audit.forensic_audit import ForensicAuditService
            for field, change in attempted_changes.items():
                ForensicAuditService.log_blocked(
                    entity_type="user_profile",
                    entity_id=str(profile.id),
                    action=f"update_{field}",
                    user_id=current_user.id,
                    reason=f"{field} cannot be changed after verification",
                    attempted_value=change["new"],
                    old_value=change["old"]
                )
            errors.append(f"Cannot change immutable fields after verification: {', '.join(attempted_changes.keys())}")

        # Save changes if no errors
        if not errors:
            try:
                db.session.commit()
                
                # Recalculate completion percentage
                new_completion = profile.get_completion_percentage()
                
                # Update profile_completed flag
                if new_completion >= 100:
                    profile.profile_completed = True
                else:
                    profile.profile_completed = False
                
                db.session.commit()
                
                flash(f"Profile updated successfully! Completion: {new_completion}%", "success")
                return redirect(url_for("profile.account_overview"))
            except Exception as e:
                db.session.rollback()
                flash(f"Error updating profile: {str(e)}", "danger")
        else:
            for error in errors:
                flash(error, "danger")

    # Prepare context for template
    context = {
        "profile": profile,
        "completion_percentage": completion_percentage,
        "is_verified": profile.verification_status == "verified",
        "immutable_fields": IMMUTABLE_AFTER_VERIFICATION,
    }

    return render_template("profile/edit.html", **context)
@profile_bp.route("/profile")
def old_profile_redirect():
    """Redirect old /profile URL to appropriate location"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.my_public_profile'))
    else:
        flash("Please log in to view your profile.", "warning")
        return redirect(url_for("auth.login"))
