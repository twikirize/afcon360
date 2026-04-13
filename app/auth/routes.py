# app/auth/routes.py
"""
Authentication routes: register, verify, login, logout, password reset, MFA.
Optimized for lazy loading.
"""

from __future__ import annotations

import secrets
import time
from typing import Optional
from urllib.parse import urlparse, urljoin
from flask import (Blueprint, current_app, flash, redirect, render_template, request, session, url_for,)
from flask_login import current_user, login_required, login_user, logout_user

from app.auth.decorators import require_role  # noqa: F401
from app.extensions import db, limiter
from app.profile.models import get_profile_by_user

# Standardized blueprint name: auth
auth_bp = Blueprint("auth", __name__, url_prefix="")


# ---------------------------------------------------------------------------
# Post-login redirect helper
# ---------------------------------------------------------------------------

def _dashboard_for_user(user) -> str:
    """
    Return the URL for this user's home dashboard based on their
    HIGHEST-PRIVILEGE role (role hierarchy aware) and current context.
    """
    # Get user's role names safely
    role_names = set()
    try:
        for user_role in user.roles:
            if user_role.role:
                role_names.add(user_role.role.name)
    except Exception as e:
        current_app.logger.warning(f"Error getting user roles: {e}")

    # Check if user is in organization context
    from flask import session
    current_context = session.get("current_context", "individual")
    current_org_id = session.get("current_org_id")

    if current_context == "organization" and current_org_id:
        # User is acting as an organization
        try:
            return url_for("org.dashboard", org_id=current_org_id)
        except:
            # Fall back to individual dashboard if org dashboard doesn't exist
            pass

    # Individual context or organization context failed
    # Check roles in priority order (highest first)
    if "owner" in role_names:
        return url_for("admin.owner.dashboard")

    if "super_admin" in role_names or "admin" in role_names:
        return url_for("admin.super_dashboard")

    if "org_admin" in role_names:
        # Even if user has org_admin role, they're in individual context
        # Redirect to organization selection or individual dashboard
        try:
            return url_for("auth.select_organization")  # Page to select which organization to act as
        except:
            # Fall back to fan dashboard
            pass

    if "moderator" in role_names:
        try:
            return url_for("moderator.dashboard")
        except:
            return url_for("index")

    if "support" in role_names:
        try:
            return url_for("support.dashboard")
        except:
            return url_for("index")

    # Default for regular users
    try:
        return url_for("fan.fan_dashboard")
    except:
        return url_for("index")

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _ct_delay() -> None:
    """Constant-time delay."""
    time.sleep(0.050 + secrets.randbelow(51) / 1000.0)

def generate_csrf_token():
    """Generate a CSRF token."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@auth_bp.route("/register", methods=["GET", "POST"], endpoint="register")
@limiter.limit("10 per minute")
def register():
    # Lazy imports
    from app.auth.validators import validate_registration
    from app.auth.services import register_user

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password =  request.form.get("password") or ""
        email    = (request.form.get("email")    or "").strip() or None

        if len(username) > 64 or len(password) > 128 or (email and len(email) > 255):
            flash("Input exceeds maximum length.", "danger")
            return render_template("register.html", username=username, email=email)

        ok, msg = validate_registration(username, password, email)
        if not ok:
            flash(msg, "danger")
            return render_template("register.html", username=username, email=email)

        try:
            register_user(username=username, password=password, email=email)
        except ValueError as exc:
            db.session.rollback()
            current_app.logger.warning("registration_rejected", extra={"reason": str(exc), "username": username})
            flash(str(exc) or "Invalid registration details.", "warning")
            return render_template("register.html", username=username, email=email)
        except Exception:
            db.session.rollback()
            current_app.logger.exception("registration_backend_error")
            flash("Registration is temporarily unavailable.", "danger")
            return render_template("register.html", username=username, email=email)

        flash("Registration successful! Please check your email.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

@auth_bp.route("/verify", methods=["GET"], endpoint="verify")
@limiter.limit("30 per hour")
def verify():
    from app.auth.services import verify_email
    token = request.args.get("token")
    token = token[:128] if token else None
    if not token or not verify_email(token):
        flash("Invalid or expired verification link.", "danger")
        return redirect(url_for("auth.login"))

    flash("Email verified. You can now log in.", "success")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def is_safe_url(target):
    host_url = request.host_url
    ref_url = urlparse(host_url)
    test_url = urlparse(urljoin(host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc

@auth_bp.route("/login", methods=["GET", "POST"], endpoint="login")
@limiter.limit("100 per minute")
def login():
    from app.auth.services import authenticate_user, AuthResult

    require_verification = current_app.config.get("VERIFY_EMAIL_REQUIRED", False)

    if request.method == "POST":
        identifier = (request.form.get("username") or "").strip()[:64]
        password   = (request.form.get("password") or "")[:128]
        ip         = request.remote_addr
        user_agent = request.headers.get("User-Agent", "")

        try:
            result, payload = authenticate_user(
                identifier=identifier,
                password=password,
                ip=ip,
                user_agent=user_agent,
            )
        except Exception:
            current_app.logger.exception("login_backend_error")
            _ct_delay()
            flash("Login is temporarily unavailable.", "danger")
            return render_template("login.html", username=identifier)

        if result == AuthResult.SUCCESS:
            user       = payload["user"]
            session_id = payload["session_id"]

            # Check if email verification is required
            if require_verification and not getattr(user, "is_verified", False):
                flash("Please confirm your email address.", "warning")
                return render_template("login.html", username=identifier)

            # Check if user is an owner - owners bypass all checks
            if user.is_app_owner():
                # Directly log in the owner without any profile or verification checks
                login_user(user, remember="remember" in request.form)

                # Set up session for owner
                session.update({
                    "server_session_id": session_id,
                    "user_id": user.public_id,
                    "username": user.username,
                    "ip": ip,
                    "user_agent": user_agent,
                    "current_context": "individual",
                    "current_org_id": None,
                    "kyc_tier": 3,  # Highest tier for owners
                    "kyc_tier_name": "owner",
                    "kyc_limits": {},
                    "kyc_missing_reqs": [],
                    "kyc_verification_id": None,
                    "kyc_verification_status": "verified",
                })

                # Flash a message for the owner
                flash("Welcome back, owner!", "success")

                # Redirect to owner dashboard
                next_page = request.args.get("next") or session.pop("next_url", None)
                if not next_page or not is_safe_url(next_page):
                    next_page = url_for("admin.owner.dashboard")
                return redirect(next_page)

            # DEBUG - remove after testing
            import sys
            print(f"DEBUG: user.public_id = {user.public_id}, type = {type(user.public_id)}", file=sys.stderr)
            print(f"DEBUG: user.id = {user.id}, type = {type(user.id)}", file=sys.stderr)

            # Use public_id explicitly since get_profile_by_user expects a string UUID
            profile = get_profile_by_user(user.public_id)

            # If no profile exists or profile is not completed
            if not profile or not profile.profile_completed:
                login_user(user, remember="remember" in request.form)

                # Save the intended destination before redirecting to profile completion
                intended = request.args.get("next") or session.pop("next_url", None)

                session.update({
                    "server_session_id": session_id,
                    "user_id": user.public_id,
                    "username": user.username,
                    "ip": ip,
                    "user_agent": user_agent,
                    "needs_profile_completion": True,
                    "next_url": intended if intended and is_safe_url(intended) else None,
                })
                flash("Please complete your profile to continue.", "info")
                return redirect(url_for("auth.complete_profile"))

            # Check verification status if profile exists and is completed
            if profile and profile.verification_status == "pending":
                flash("Your profile is pending verification. Some features may be limited.", "warning")
            elif profile and profile.verification_status == "rejected":
                flash("Your profile verification was rejected. Please update your information.", "danger")
                # Don't log them in if verification is rejected?
                # For now, we'll let them login but show a warning
            elif profile and profile.verification_status == "suspended":
                flash("Your account is suspended. Please contact support.", "danger")
                logout_user()
                return redirect(url_for("auth.login"))

            login_user(user, remember="remember" in request.form)

            # Calculate KYC tier and limits
            from app.auth.kyc_compliance import calculate_kyc_tier, get_user_limits

            kyc_info = calculate_kyc_tier(user.id)
            user_limits = get_user_limits(user.id)

            session.update({
                "server_session_id": session_id,
                "user_id":           user.public_id,
                "username":          user.username,
                "ip":                ip,
                "user_agent":        user_agent,
                "current_context":   "individual",  # Default to individual context
                "current_org_id":    None,          # No organization selected by default
                "kyc_tier":          kyc_info["tier"],
                "kyc_tier_name":     kyc_info["tier_name"],
                "kyc_limits":        user_limits,
                "kyc_missing_reqs":  kyc_info.get("missing_requirements", []),
                "kyc_verification_id": kyc_info.get("verification_id"),
                "kyc_verification_status": kyc_info.get("verification_status"),
            })

            # Check if user has organization memberships
            if hasattr(user, 'organisations') and user.organisations:
                active_orgs = []
                for membership in user.organisations:
                    if not membership.is_deleted and membership.is_active:
                        # Get organization name safely
                        org_name = "Unknown Organization"
                        if hasattr(membership, 'organisation') and membership.organisation:
                            org_name = getattr(membership.organisation, 'name', f"Organization {membership.organisation_id}")

                        active_orgs.append({
                            "org_id": membership.organisation_id,
                            "org_name": org_name,
                            "membership": membership
                        })

                if active_orgs:
                    session["has_organisations"] = True
                    # Store organization info for quick switching
                    session["available_orgs"] = active_orgs

                    # If user has a default organization, set it as current context
                    if hasattr(user, 'default_org_id') and user.default_org_id:
                        default_org_exists = any(org["org_id"] == user.default_org_id for org in active_orgs)
                        if default_org_exists:
                            session["current_context"] = "organization"
                            session["current_org_id"] = user.default_org_id

            next_page = request.args.get("next") or session.pop("next_url", None)
            if not next_page or not is_safe_url(next_page):
                next_page = _dashboard_for_user(user)

            return redirect(next_page)

        # Audit failed login attempt
        from app.audit.comprehensive_audit import AuditService, AuditSeverity
        AuditService.security(
            event_type="failed_login_attempt",
            severity=AuditSeverity.WARNING,
            description=f"Failed login attempt for identifier: {identifier}",
            user_id=None,  # Unknown user
            ip_address=ip,
            user_agent=user_agent,
            extra_data={
                "identifier": identifier,
                "failed_attempts": result.value if hasattr(result, 'value') else "unknown"
            }
        )

        _ct_delay()
        flash("Invalid username or password.", "danger")
        return render_template("login.html", username=identifier)

    return render_template("login.html")


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@auth_bp.route("/logout", methods=["POST"], endpoint="logout")
@login_required
def logout():
    from app.auth.services import revoke_session
    ssid = session.get("server_session_id")
    try:
        if ssid:
            revoke_session(ssid)
    except Exception:
        pass

    logout_user()
    # Clear all session data
    keys_to_clear = [
        "server_session_id", "user_id", "username", "ip", "user_agent",
        "current_context", "current_org_id", "has_organisations",
        "available_orgs", "needs_profile_completion"
    ]
    for key in keys_to_clear:
        session.pop(key, None)

    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

@auth_bp.route("/reset/request", methods=["GET", "POST"], endpoint="reset_request")
@limiter.limit("10 per hour")
def reset_request():
    from app.identity.models.user import User
    from app.auth.services import request_password_reset

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()[:64]
        user     = User.query.filter_by(username=username).first()

        if user and user.email:
            request_password_reset(user)

        flash("If that account exists, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))

    return render_template("reset_request.html")


# ---------------------------------------------------------------------------
# Organization Context Switching
# ---------------------------------------------------------------------------

@auth_bp.route("/switch-context", methods=["POST"], endpoint="switch_context")
@login_required
def switch_context():
    """Switch between individual and organization contexts."""
    from flask import session, request, jsonify
    from app.identity.models.organisation_member import OrganisationMember

    context = request.form.get("context", "individual")
    org_id = request.form.get("org_id")

    if context == "organization" and org_id:
        # Verify user is a member of this organization
        user = current_user
        is_member = False
        for membership in user.organisations:
            if (membership.organisation_id == int(org_id) and
                not membership.is_deleted and
                membership.is_active):
                is_member = True
                break

        if not is_member:
            flash("You are not a member of this organization.", "danger")
            return redirect(request.referrer or url_for("index"))

        session["current_context"] = "organization"
        session["current_org_id"] = int(org_id)
        flash(f"Now acting as organization {org_id}", "success")

    elif context == "individual":
        session["current_context"] = "individual"
        session["current_org_id"] = None
        flash("Now acting as individual", "success")

    next_page = request.form.get("next") or request.referrer or url_for("index")
    return redirect(next_page)

# ---------------------------------------------------------------------------
# Organization Selection
# ---------------------------------------------------------------------------

@auth_bp.route("/select-organization", methods=["GET"], endpoint="select_organization")
@login_required
def select_organization():
    """Page to select which organization to act as."""
    from flask import session, render_template

    user = current_user
    active_orgs = []

    if hasattr(user, 'organisations') and user.organisations:
        active_orgs = [org for org in user.organisations if not org.is_deleted and org.is_active]

    return render_template("select_organization.html",
                          organizations=active_orgs,
                          current_context=session.get("current_context", "individual"),
                          current_org_id=session.get("current_org_id"))

# ---------------------------------------------------------------------------
# Profile Completion
# ---------------------------------------------------------------------------

@auth_bp.route("/complete-profile", methods=["GET", "POST"], endpoint="complete_profile")
@login_required
def complete_profile():
    """Complete user profile after login."""
    from flask import session, render_template, redirect, url_for, request, flash
    from app.profile.models import UserProfile
    from app.extensions import db

    # 1. Check if user actually needs profile completion
    if not session.get("needs_profile_completion"):
        return redirect(url_for("index"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()

        if not full_name:
            flash("Full name is required.", "danger")
            # FIX: Point to the sub-folder
            return render_template("kyc/complete_profile.html")

        # 2. Update user profile using public_id
        user = current_user
        # Get the profile using public_id to avoid type mismatch
        profile = get_profile_by_user(user.public_id)
        if not profile:
            # Create a new profile if it doesn't exist
            profile = UserProfile(user_id=user.public_id)
            db.session.add(profile)

        profile.full_name = full_name
        if phone_number:
            profile.phone_number = phone_number
        profile.profile_completed = True

        db.session.commit()

        # 3. Clear the flag and move on
        session.pop("needs_profile_completion", None)
        flash("Profile completed successfully!", "success")
        next_page = session.pop("next_url", None)
        return redirect(next_page if next_page and is_safe_url(next_page) else url_for("index"))

    return render_template("kyc/complete_profile.html")

# ---------------------------------------------------------------------------
# MFA
# ---------------------------------------------------------------------------

@auth_bp.route("/mfa/<user_id>", methods=["GET", "POST"], endpoint="mfa")
def mfa(user_id: str):
    flash("Multi-factor authentication is not yet active.", "danger")
    return redirect(url_for("auth.login"))



# ---------------------------------------------------------------------------
# Check toutes
# ---------------------------------------------------------------------------
@auth_bp.route("/test-csrf")
@login_required
def test_csrf():
    """Test CSRF token generation"""
    token = generate_csrf_token()
    print(f"CSRF Token generated: {token}")
    return f"CSRF Token: {token} (check console for value)"
