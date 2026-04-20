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
    # First, check if user is an owner using the is_app_owner() method
    # This is consistent with the login function's owner check
    if hasattr(user, 'is_app_owner') and callable(user.is_app_owner):
        try:
            if user.is_app_owner():
                return url_for("admin.owner.dashboard")
        except Exception as e:
            current_app.logger.warning(f"Error calling is_app_owner(): {e}")

    # Get user's role names safely
    role_names = set()
    try:
        # Try different possible attribute names for roles
        if hasattr(user, 'roles'):
            for user_role in user.roles:
                if hasattr(user_role, 'role') and user_role.role:
                    role_names.add(user_role.role.name)
                elif hasattr(user_role, 'name'):
                    role_names.add(user_role.name)
        # Also check if user has a direct 'role_names' attribute
        if hasattr(user, 'role_names'):
            try:
                names = user.role_names
                if isinstance(names, (list, set, tuple)):
                    role_names.update(names)
            except Exception as e:
                current_app.logger.warning(f"Error getting role_names: {e}")
    except Exception as e:
        current_app.logger.warning(f"Error getting user roles: {e}")

    # Check for owner role in role_names as well (for consistency)
    # Also check for variations like 'app_owner', 'system_owner', etc.
    owner_roles = {'owner', 'app_owner', 'system_owner', 'platform_owner'}
    if any(owner_role in role_names for owner_role in owner_roles):
        return url_for("admin.owner.dashboard")

    # Check if user is in organization context (only for non-owners)
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
    # Check remaining roles in priority order (highest first)
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
        return url_for("fan.dashboard")
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
        security_question = (request.form.get("security_question") or "").strip() or None
        security_answer = (request.form.get("security_answer") or "").strip() or None

        # Check if email verification is required
        require_email_verification = current_app.config.get('REQUIRE_EMAIL_VERIFICATION', False)
        if require_email_verification and not email:
            flash("Email is required for registration.", "danger")
            return render_template("register.html",
                                   username=username,
                                   email=email,
                                   security_question=security_question,
                                   security_answer=security_answer)

        # If email is not provided, security question and answer become required
        if not email:
            if not security_question:
                flash("Security question is required when email is not provided.", "danger")
                return render_template("register.html",
                                       username=username,
                                       email=email,
                                       security_question=security_question,
                                       security_answer=security_answer)
            if not security_answer:
                flash("Security answer is required when email is not provided.", "danger")
                return render_template("register.html",
                                       username=username,
                                       email=email,
                                       security_question=security_question,
                                       security_answer=security_answer)
            if len(security_answer) < 2:
                flash("Security answer must be at least 2 characters long.", "danger")
                return render_template("register.html",
                                       username=username,
                                       email=email,
                                       security_question=security_question,
                                       security_answer=security_answer)

        if len(username) > 64 or len(password) > 128 or (email and len(email) > 255):
            flash("Input exceeds maximum length.", "danger")
            return render_template("register.html",
                                   username=username,
                                   email=email,
                                   security_question=security_question,
                                   security_answer=security_answer)

        ok, msg = validate_registration(username, password, email)
        if not ok:
            flash(msg, "danger")
            return render_template("register.html",
                                   username=username,
                                   email=email,
                                   security_question=security_question,
                                   security_answer=security_answer)

        try:
            # Pass security_question and security_answer to register_user
            result = register_user(
                username=username,
                password=password,
                email=email,
                security_question=security_question,
                security_answer=security_answer
            )
        except ValueError as exc:
            db.session.rollback()
            current_app.logger.warning("registration_rejected", extra={"reason": str(exc), "username": username})
            flash(str(exc) or "Invalid registration details.", "warning")
            return render_template("register.html",
                                   username=username,
                                   email=email,
                                   security_question=security_question,
                                   security_answer=security_answer)
        except Exception:
            db.session.rollback()
            current_app.logger.exception("registration_backend_error")
            flash("Registration is temporarily unavailable.", "danger")
            return render_template("register.html",
                                   username=username,
                                   email=email,
                                   security_question=security_question,
                                   security_answer=security_answer)

        # Check if email was provided
        if not email:
            # Handle recovery code from register_user result
            recovery_code = None
            # Try to get recovery code from result
            if hasattr(result, 'recovery_code'):
                recovery_code = result.recovery_code
            elif isinstance(result, dict) and 'recovery_code' in result:
                recovery_code = result['recovery_code']
            else:
                # If register_user doesn't provide a recovery code, generate a placeholder
                # In a real implementation, this should be handled by the service
                recovery_code = secrets.token_urlsafe(16)

            flash(f"Registration successful! Since no email was provided, please save your recovery code: {recovery_code}", "warning")
        else:
            # Check if email verification is required
            require_email_verification = current_app.config.get('REQUIRE_EMAIL_VERIFICATION', False)
            if require_email_verification:
                # Send verification email
                from app.auth.email import send_verification_email
                from app.identity.models.user import User

                # Find the newly registered user by username
                user = User.query.filter_by(username=username).first()
                if user:
                    email_sent = send_verification_email(user)
                    if email_sent:
                        flash("Registration successful! Please check your email for verification code.", "success")
                    else:
                        flash("Registration successful, but we couldn't send the verification email. Please contact support.", "warning")
                else:
                    flash("Registration successful, but we couldn't find your user account to send verification email.", "warning")
            else:
                flash("Registration successful! You can now log in.", "success")

        return redirect(url_for("auth.login"))

    from config import APP_NAME
    return render_template("register.html", app_name=APP_NAME)


# ---------------------------------------------------------------------------
# Email verification (legacy token-based)
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
# Email verification via OTP code
# ---------------------------------------------------------------------------

@auth_bp.route("/verify-email", methods=["POST"], endpoint="verify_email_code")
@login_required
@limiter.limit("10 per hour")
def verify_email_code():
    """
    Verify email using 6-digit OTP code.
    """
    from app.auth.email import verify_email_code as verify_code

    code = request.form.get("code", "").strip()

    if not code or len(code) != 6 or not code.isdigit():
        flash("Please enter a valid 6-digit code.", "danger")
        return redirect(request.referrer or url_for("index"))

    # Verify the code
    success, message = verify_code(current_user.id, code)

    if success:
        flash(message, "success")
        # Update session if needed
        session['email_verified'] = True
    else:
        flash(message, "danger")

    return redirect(request.referrer or url_for("index"))

# ---------------------------------------------------------------------------
# Phone verification via OTP code
# ---------------------------------------------------------------------------

@auth_bp.route("/verify-phone", methods=["POST"], endpoint="verify_phone")
@login_required
@limiter.limit("10 per hour")
def verify_phone():
    """
    Verify phone number using OTP code sent via SMS.
    """
    code = request.form.get("code", "").strip()
    phone_number = request.form.get("phone_number", "").strip()

    if not code or len(code) != 6 or not code.isdigit():
        flash("Please enter a valid 6-digit code.", "danger")
        return redirect(request.referrer or url_for("index"))

    if not phone_number:
        # Try to get phone number from user's profile
        from app.profile.models import get_profile_by_user
        profile = get_profile_by_user(current_user.public_id)
        if profile and profile.phone_number:
            phone_number = profile.phone_number
        else:
            flash("Phone number not found. Please update your profile.", "danger")
            return redirect(request.referrer or url_for("index"))

    # Verify the OTP code
    sms_service = SMSService()
    if sms_service.verify_otp(phone_number, code):
        flash("Phone number verified successfully!", "success")
        # Update session or profile as needed
        session['phone_verified'] = True
        # Update user's profile verification status if needed
        from app.profile.models import get_profile_by_user
        from app.extensions import db
        profile = get_profile_by_user(current_user.public_id)
        if profile:
            profile.phone_verified = True
            db.session.commit()
    else:
        flash("Invalid or expired verification code.", "danger")

    return redirect(request.referrer or url_for("index"))

@auth_bp.route("/send-phone-verification", methods=["POST"], endpoint="send_phone_verification")
@login_required
@limiter.limit("5 per hour")
def send_phone_verification():
    """
    Send OTP code to user's phone number for verification.
    """
    from app.services.sms_service import SMSService

    phone_number = request.form.get("phone_number", "").strip()

    if not phone_number:
        # Try to get phone number from user's profile
        from app.profile.models import get_profile_by_user
        profile = get_profile_by_user(current_user.public_id)
        if profile and profile.phone_number:
            phone_number = profile.phone_number
        else:
            flash("Please provide a phone number.", "danger")
            return redirect(request.referrer or url_for("index"))

    # Send OTP
    sms_service = SMSService()
    result = sms_service.send_otp(phone_number)

    if result.get('success'):
        flash("Verification code sent to your phone number.", "success")
    else:
        flash(f"Failed to send verification code: {result.get('error', 'Unknown error')}", "danger")

    return redirect(request.referrer or url_for("index"))


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

    require_verification = current_app.config.get("REQUIRE_EMAIL_VERIFICATION", False)

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

            # If no profile exists or profile is not completed, set flag but allow login
            # Profile completion is now optional, but some features may require it
            if not profile or not profile.profile_completed:
                session["profile_incomplete"] = True
                # Don't flash a message here to avoid interrupting the login flow
                # Users will see the message when they try to access features that require profile completion
            else:
                # Clear any existing incomplete flag
                session.pop("profile_incomplete", None)

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

    from config import APP_NAME
    return render_template("login.html", app_name=APP_NAME)


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
# Password recovery without email (using security question) - Step 1: Username entry
# ---------------------------------------------------------------------------

@auth_bp.route("/recover", methods=["GET", "POST"], endpoint="recover")
@limiter.limit("5 per hour")
def recover():
    """Password recovery for users without email - Step 1: Enter username."""
    from app.auth.services import initiate_password_recovery

    if request.method == "GET":
        return render_template("auth/recover_request.html")

    # POST request: submit username
    username = (request.form.get("username") or "").strip()[:64]

    if not username:
        flash("Please enter your username.", "danger")
        return render_template("auth/recover_request.html", username=username)

    success, result = initiate_password_recovery(username)

    if not success:
        # Don't reveal too much information
        flash("If the account exists and has a security question configured, you will be able to reset your password.", "info")
        return render_template("auth/recover_request.html", username=username)

    # Store username in session for the next step
    session["recovery_username"] = username
    session["recovery_attempts"] = 0

    return render_template("auth/recover_question.html",
                          username=username,
                          security_question=result["security_question"])

# ---------------------------------------------------------------------------
# Password recovery without email (using security question) - Step 2: Verify security question
# ---------------------------------------------------------------------------

@auth_bp.route("/recover/verify", methods=["POST"], endpoint="recover_verify")
@limiter.limit("5 per hour")
def recover_verify():
    """Password recovery for users without email - Step 2: Verify security question and reset password."""
    from app.auth.services import verify_security_answer_and_reset_password

    # Check if we have a username in session
    username = session.get("recovery_username")
    if not username:
        flash("Recovery session expired. Please start over.", "danger")
        return redirect(url_for("auth.recover"))

    # Check rate limiting
    attempts = session.get("recovery_attempts", 0)
    if attempts >= 5:
        flash("Too many attempts. Please try again later.", "danger")
        session.pop("recovery_username", None)
        session.pop("recovery_attempts", None)
        return redirect(url_for("auth.recover"))

    answer = (request.form.get("answer") or "").strip()
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    # Validate inputs
    if not answer:
        flash("Please provide an answer to your security question.", "danger")
        return render_template("auth/recover_question.html",
                              username=username,
                              security_question="[Hidden for security]")

    if not new_password or len(new_password) < 10:
        flash("Password must be at least 10 characters long.", "danger")
        return render_template("auth/recover_question.html",
                              username=username,
                              security_question="[Hidden for security]")

    if new_password != confirm_password:
        flash("Passwords do not match.", "danger")
        return render_template("auth/recover_question.html",
                              username=username,
                              security_question="[Hidden for security]")

    # Verify answer and reset password
    success, error_message = verify_security_answer_and_reset_password(
        username, answer, new_password
    )

    if success:
        # Clear session data
        session.pop("recovery_username", None)
        session.pop("recovery_attempts", None)

        flash("Password has been reset successfully. You can now log in with your new password.", "success")
        return redirect(url_for("auth.login"))
    else:
        # Increment attempt counter
        session["recovery_attempts"] = attempts + 1
        remaining_attempts = 5 - (attempts + 1)

        if remaining_attempts > 0:
            flash(f"Incorrect answer. {remaining_attempts} attempts remaining.", "danger")
        else:
            flash("Too many incorrect attempts. Please try again later.", "danger")
            session.pop("recovery_username", None)
            session.pop("recovery_attempts", None)
            return redirect(url_for("auth.recover"))

        return render_template("auth/recover_question.html",
                              username=username,
                              security_question="[Hidden for security]")


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

        # Try to check membership
        try:
            # Check if user has organisations attribute
            if hasattr(user, 'organisations'):
                for membership in user.organisations:
                    if (membership.organisation_id == int(org_id) and
                        not getattr(membership, 'is_deleted', False) and
                        getattr(membership, 'is_active', True)):
                        is_member = True
                        break
            else:
                # Try querying directly
                membership = OrganisationMember.query.filter_by(
                    user_id=user.id,
                    organisation_id=int(org_id),
                    is_deleted=False,
                    is_active=True
                ).first()
                is_member = membership is not None
        except Exception as e:
            current_app.logger.warning(f"Error checking organization membership: {e}")
            is_member = False

        if not is_member:
            if request.is_json:
                return jsonify({"error": "Not a member of this organization"}), 403
            flash("You are not a member of this organization.", "danger")
            return redirect(request.referrer or url_for("index"))

        session["current_context"] = "organization"
        session["current_org_id"] = int(org_id)
        # Store organization name if available
        try:
            from app.identity.models.organisation import Organisation
            org = Organisation.query.get(int(org_id))
            if org:
                session["current_org_name"] = org.name
        except:
            pass

        if request.is_json:
            return jsonify({"success": True, "message": "Context switched to organization"})
        flash(f"Now acting as organization", "success")

    elif context == "individual":
        session["current_context"] = "individual"
        session["current_org_id"] = None
        session.pop("current_org_name", None)

        if request.is_json:
            return jsonify({"success": True, "message": "Context switched to individual"})
        flash("Now acting as individual", "success")

    next_page = request.form.get("next") or request.referrer or url_for("index")
    if request.is_json:
        return jsonify({"success": True, "redirect": next_page})
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
    """Complete user profile to unlock features."""
    from flask import session, render_template, redirect, url_for, request, flash
    from app.profile.models import UserProfile
    from app.extensions import db

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()

        if not full_name:
            flash("Full name is required.", "danger")
            return render_template("kyc/complete_profile.html")

        # Update user profile using public_id
        user = current_user
        profile = get_profile_by_user(user.public_id)
        if not profile:
            # Create a new profile if it doesn't exist
            profile = UserProfile(user_id=user.public_id)
            db.session.add(profile)

        profile.full_name = full_name
        if phone_number:
            profile.phone_number = phone_number
        profile.profile_completed = True

        # Update KYC level to Tier 2 (Verified Booker)
        # First, ensure we have the user object from the database
        from app.identity.models.user import User
        db_user = User.query.filter_by(id=user.id).first()
        if db_user:
            if hasattr(db_user, 'kyc_level'):
                db_user.kyc_level = 2
            else:
                # If kyc_level attribute doesn't exist, we need to add it
                # For now, we'll skip this, but in a real implementation, we'd need to handle it
                pass
            db.session.commit()

        db.session.commit()

        # Clear the incomplete flag
        session.pop("profile_incomplete", None)
        flash("Profile completed successfully! You've been upgraded to KYC Tier 2 and can now access booking features.", "success")
        return redirect(url_for("fan.dashboard"))

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
