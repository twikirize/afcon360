# app/auth/routes.py
"""
Authentication routes: register, verify, login, logout, password reset, MFA.
Optimized for lazy loading.
"""

from __future__ import annotations

import secrets
import time
import json
import logging
from typing import Optional
from urllib.parse import urlparse, urljoin
from flask import (Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for,)
from flask_login import current_user, login_required, login_user, logout_user

from app.auth.decorators import require_role, require_fresh_user  # noqa: F401
from app.extensions import db, limiter
from app.profile.models import get_profile_by_user

# Standardized blueprint name: auth
auth_bp = Blueprint("auth", __name__, url_prefix="")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Security Helpers
# ---------------------------------------------------------------------------

def _verify_mfa_token(user, token: str, backup_code: bool = False) -> bool:
    """
    Verify MFA token for user with enhanced functionality.
    
    SECURITY: Used for owner login MFA requirement.
    
    Args:
        user: User model instance
        token: MFA code from user
        backup_code: Whether this is a backup code verification
        
    Returns:
        True if token valid, False otherwise
    """
    if not token:
        return False
    
    try:
        from app.identity.models.user import MFASecret
        
        # Get active MFA secret
        mfa_secret = MFASecret.query.filter_by(
            user_id=user.id,
            is_active=True
        ).first()
        
        if not mfa_secret:
            return False
        
        # Check if it's a backup code
        if backup_code or len(token) == 8:
            if mfa_secret.verify_backup_code(token.upper()):
                mfa_secret.last_used = datetime.now(timezone.utc)
                db.session.commit()
                return True
            return False
        
        # Verify TOTP token
        if mfa_secret.mfa_type == 'totp':
            import pyotp
            totp = pyotp.TOTP(mfa_secret.secret)
            if totp.verify(token, valid_window=1):
                mfa_secret.last_used = datetime.now(timezone.utc)
                db.session.commit()
                return True
        
        # SMS verification (placeholder)
        elif mfa_secret.mfa_type == 'sms':
            # Implement SMS verification logic here
            return False
        
        return False
        
    except ImportError:
        # Fallback: simple time-based verification (less secure, for dev only)
        import hashlib
        import time
        if hasattr(user, 'mfa_secret'):
            secret = user.mfa_secret
            # Check current time window and adjacent windows
            for window in [-1, 0, 1]:
                time_window = int(time.time()) // 30 + window
                expected = hashlib.sha256(f"{secret}:{time_window}".encode()).hexdigest()[:6]
                if token == expected:
                    return True
        return False
    except Exception as e:
        current_app.logger.error(f"MFA verification error: {e}")
        return False


# ---------------------------------------------------------------------------
# Post-login redirect helper
# ---------------------------------------------------------------------------

def _dashboard_for_user(user) -> str:
    """
    Return the URL for this user's home dashboard based on their
    HIGHEST-PRIVILEGE role (role hierarchy aware) and current context.

    RULE: If the user has NOT completed onboarding, redirect to the
    onboarding landing page regardless of roles.
    """

    # Re-resolve an explicitly selected workspace before legacy role routing.
    # The legacy branches remain as a compatibility fallback during migration.
    try:
        from app.auth.context import get_active_context

        active_context = get_active_context(user)
        if active_context.type.value != "personal" and active_context.workspace_url:
            return active_context.workspace_url
    except Exception as exc:
        current_app.logger.debug("Canonical context redirect unavailable: %s", exc)
    
    # STEP 2: Owner check
    if hasattr(user, 'is_app_owner') and callable(user.is_app_owner):
        try:
            if user.is_app_owner():
                return url_for("admin.owner.dashboard")
        except Exception as e:
            current_app.logger.warning(f"Error calling is_app_owner(): {e}")

    # STEP 3: Build role set
    role_names = set()
    try:
        if hasattr(user, 'roles'):
            for user_role in user.roles:
                if hasattr(user_role, 'role') and user_role.role:
                    role_names.add(user_role.role.name)
                elif hasattr(user_role, 'name'):
                    role_names.add(user_role.name)
        if hasattr(user, 'role_names'):
            try:
                names = user.role_names
                if isinstance(names, (list, set, tuple)):
                    role_names.update(names)
            except Exception:
                pass
    except Exception as e:
        current_app.logger.warning(f"Error getting user roles: {e}")

    # STEP 4: Owner role in names
    owner_roles = {'owner', 'app_owner', 'system_owner', 'platform_owner'}
    if any(owner_role in role_names for owner_role in owner_roles):
        return url_for("admin.owner.dashboard")

    # STEP 5: Org context
    from flask import session
    current_context = session.get("current_context", "individual")
    current_org_id = session.get("current_org_id")

    if current_context == "organization" and current_org_id:
        try:
            return url_for("org.dashboard", org_id=current_org_id)
        except:
            pass

    # STEP 6: System admin roles
    if "super_admin" in role_names or "admin" in role_names:
        return url_for("admin.super_dashboard")

    if "org_admin" in role_names:
        try:
            return url_for("auth.select_organization")
        except:
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

    # STEP 7: New specialized admin roles
    if "event_manager" in role_names:
        try:
            return url_for("admin.event_manager_dashboard")
        except:
            return url_for("index")

    if "transport_admin" in role_names:
        try:
            return url_for("admin.transport_admin_dashboard")
        except:
            return url_for("index")

    if "wallet_admin" in role_names:
        try:
            return url_for("admin.wallet_admin_dashboard")
        except:
            return url_for("index")

    if "accommodation_admin" in role_names:
        try:
            return url_for("admin.accommodation_admin_dashboard")
        except:
            return url_for("index")

    if "tourism_admin" in role_names:
        try:
            return url_for("admin.tourism_admin_dashboard")
        except:
            return url_for("index")

    if "org_member" in role_names:
        try:
            return url_for("admin.org_member_dashboard")
        except:
            return url_for("index")

    if "auditor" in role_names:
        try:
            return url_for("admin.role_dashboard", role_name="auditor")
        except:
            return url_for("index")

    if "compliance_officer" in role_names:
        try:
            return url_for("admin.role_dashboard", role_name="compliance_officer")
        except:
            return url_for("index")

    # STEP 7: Check for driver profile
    try:
        from app.transport.models import DriverProfile, VerificationTier
        driver = DriverProfile.query.filter_by(user_id=user.id).first()
        if driver and driver.verification_tier == VerificationTier.PLATFORM_VERIFIED:
            return url_for("transport.driver_dashboard")
    except Exception:
        pass

    # STEP 8: Event organiser role
    if "event_manager" in role_names:
        try:
            return url_for("events.my_events")
        except:
            pass

    # STEP 9: Default fan dashboard
    try:
        return url_for("user.dashboard")
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
    from app.auth.registration_policy import email_verification_required
    from app.auth.pending_registration import start_pending_registration

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password =  request.form.get("password") or ""
        email    = (request.form.get("email")    or "").strip() or None
        security_question = (request.form.get("security_question") or "").strip() or None
        security_answer = (request.form.get("security_answer") or "").strip() or None

        def _rerender(**extra):
            return render_template("register.html",
                                   username=username,
                                   email=email,
                                   security_question=security_question,
                                   security_answer=security_answer,
                                   **extra)

        # Owner-controlled toggle (Auth Settings page) decides whether an
        # email + OTP is mandatory for every new account.
        require_email_verification = email_verification_required()

        phone = (request.form.get("phone") or "").strip() or None

        if require_email_verification and not email:
            flash("Email is required for registration.", "danger")
            return _rerender()

        # If email is not provided, security question and answer become required
        if not email:
            if not security_question:
                flash("Security question is required when email is not provided.", "danger")
                return _rerender()
            if not security_answer:
                flash("Security answer is required when email is not provided.", "danger")
                return _rerender()
            if len(security_answer) < 2:
                flash("Security answer must be at least 2 characters long.", "danger")
                return _rerender()

        if len(username) > 64 or len(password) > 128 or (email and len(email) > 255):
            flash("Input exceeds maximum length.", "danger")
            return _rerender()

        ok, msg = validate_registration(username, password, email)
        if not ok:
            flash(msg, "danger")
            return _rerender()

        # ------------------------------------------------------------------
        # Verified path: prove the inbox BEFORE creating any database row.
        # ------------------------------------------------------------------
        if email and require_email_verification:
            result = start_pending_registration(
                username=username,
                password=password,
                email=email,
                ip=request.remote_addr,
                user_agent=request.headers.get("User-Agent", ""),
                extra={"phone": phone} if phone else None,
            )

            if not result.success:
                if result.suggestion:
                    flash(f"{result.message}", "warning")
                else:
                    flash(result.message, "danger")
                return _rerender(email_suggestion=result.suggestion)

            # Hold only the opaque token server-side; no credentials in session.
            session["pending_registration_token"] = result.token
            session["pending_registration_email"] = result.email

            if result.debug_otp:
                flash(f"[DEV] Your verification code is {result.debug_otp}", "info")

            flash(result.message, "success")
            return redirect(url_for("auth.verify_signup"))

        # ------------------------------------------------------------------
        # Unverified path (owner toggle off, or no-email + security question).
        # ------------------------------------------------------------------
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
            return _rerender()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("registration_backend_error")
            flash("Registration is temporarily unavailable.", "danger")
            return _rerender()

        # Check if email was provided
        if not email:
            # Handle recovery code from register_user result
            recovery_code = None
            # Try to get recovery code from result
            if hasattr(result, 'recovery_code'):
                recovery_code = result.recovery_code
            elif isinstance(result, dict) and 'recovery_code' in result:
                recovery_code = result['recovery_code']
            elif getattr(result, "_recovery_code", None):
                recovery_code = result._recovery_code
            else:
                # If register_user doesn't provide a recovery code, generate a placeholder
                # In a real implementation, this should be handled by the service
                recovery_code = secrets.token_urlsafe(16)

            flash(f"Registration successful! Since no email was provided, please save your recovery code: {recovery_code}", "warning")
        else:
            flash("Registration successful! You can now log in.", "success")

        return redirect(url_for("auth.login"))

    from config import APP_NAME
    return render_template("register.html", app_name=APP_NAME)


# ---------------------------------------------------------------------------
# Signup email verification (OTP) - account is created only on success
# ---------------------------------------------------------------------------

@auth_bp.route("/verify-signup", methods=["GET", "POST"], endpoint="verify_signup")
@limiter.limit("20 per hour", methods=["POST"])
def verify_signup():
    """
    Confirm the 6-digit code emailed during registration.

    The user record is created here - and only here - once the OTP proves the
    address is real and reachable.
    """
    from app.auth.pending_registration import (
        get_pending_registration,
        verify_pending_registration,
    )

    token = session.get("pending_registration_token")
    if not token:
        flash("Please start by creating your account.", "info")
        return redirect(url_for("auth.register"))

    pending = get_pending_registration(token)

    if request.method == "GET":
        if not pending:
            flash("Your verification session expired. Please sign up again.", "warning")
            session.pop("pending_registration_token", None)
            session.pop("pending_registration_email", None)
            return redirect(url_for("auth.register"))

        return render_template(
            "auth/verify_signup.html",
            email=pending.get("email"),
            expires_in=max(0, int(pending.get("expires_at", 0) - time.time())),
        )

    # POST - check the submitted code
    code = (request.form.get("code") or "").strip()

    result = verify_pending_registration(
        token,
        code,
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
    )

    if not result.success:
        if result.code in ("expired", "too_many_attempts"):
            session.pop("pending_registration_token", None)
            flash(result.message, "danger")
            return redirect(url_for("auth.register"))

        flash(result.message, "danger")
        return render_template(
            "auth/verify_signup.html",
            email=session.get("pending_registration_email"),
            remaining_attempts=result.remaining_attempts,
        )

    # Success - the account now exists and is verified.
    session.pop("pending_registration_token", None)
    session.pop("pending_registration_email", None)

    current_app.logger.info(
        "Signup verified and account created for %s", result.user.public_id
    )

    if result.already_existed:
        flash("Your email is already verified. Please log in.", "info")
    else:
        flash("Email verified! Your account has been created. You can now log in.", "success")

    return redirect(url_for("auth.login"))


@auth_bp.route("/verify-signup/resend", methods=["POST"], endpoint="resend_signup_otp")
@limiter.limit("5 per hour")
def resend_signup_otp():
    """Send a fresh signup OTP (supports the client-side silent resync)."""
    from app.auth.pending_registration import restart_pending_registration

    token = session.get("pending_registration_token")
    wants_json = request.accept_mimetypes.best == "application/json" or request.is_json

    result = restart_pending_registration(token=token, ip=request.remote_addr)

    if wants_json:
        status = 200 if result.success else (429 if result.retry_after else 400)
        return jsonify({
            "success": result.success,
            "message": result.message,
            "code": result.code,
            "retry_after": result.retry_after,
            "debug_otp": result.debug_otp,
        }), status

    if not result.success:
        flash(result.message, "danger")
        if result.code == "expired":
            return redirect(url_for("auth.register"))
        return redirect(url_for("auth.verify_signup"))

    if result.debug_otp:
        flash(f"[DEV] Your verification code is {result.debug_otp}", "info")
    flash(result.message, "success")
    return redirect(url_for("auth.verify_signup"))


@auth_bp.route("/verify-signup/keep-alive", methods=["POST"], endpoint="signup_keep_alive")
@limiter.limit("60 per hour")
def signup_keep_alive():
    """
    Extend the pending-registration TTL while the user is actively verifying.

    Called by the verification page on focus/typing so an engaged user is never
    timed out mid-entry, up to a hard lifetime ceiling.
    """
    from app.auth.pending_registration import touch_pending_registration

    token = session.get("pending_registration_token")
    if not token:
        return jsonify({"success": False, "code": "no_session"}), 400

    extended, seconds_left = touch_pending_registration(token)
    return jsonify({
        "success": extended,
        "expires_in": seconds_left,
    })



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

@auth_bp.route("/verify-email", methods=["GET", "POST"], endpoint="verify_email_code")
@login_required
@limiter.limit("10 per hour")
@require_fresh_user
def verify_email_code():
    """
    Verify email using 6-digit OTP code.

    GET renders the code-entry form (so a clicked "verify" link / push
    notification no longer hits a 405). POST validates the submitted code.
    """
    from app.auth.email import verify_email_code as verify_code
    from app.identity.models.user import User

    if request.method == "GET":
        user = db.session.get(User, current_user.id)
        email = getattr(user, "email", None) if user else None
        return render_template("auth/verify_email.html", email=email)

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

@auth_bp.route("/verify-phone", methods=["GET", "POST"], endpoint="verify_phone")
@login_required
@limiter.limit("10 per hour")
@require_fresh_user
def verify_phone():
    """
    Verify phone number using the owner-selected OTP delivery transport.
    """
    from app.auth.phone_verification import PhoneVerificationService
    from app.auth.config_model import AuthConfiguration
    from app.profile.models import get_profile_by_user

    profile = get_profile_by_user(current_user.public_id)
    phone_number = getattr(profile, 'phone_number', '') if profile else ''
    user_email = getattr(current_user, 'email', '') or ''

    if request.method == "GET":
        if not user_email:
            flash("No email address found on your account. Cannot start phone verification.", "danger")
            return redirect(url_for("profile.edit_profile"))
        try:
            phone_verification_transport = AuthConfiguration.get_config().get_phone_verification_transport()
        except Exception:
            phone_verification_transport = "email"
        return render_template(
            "auth/verify_phone.html",
            phone_number=phone_number,
            email=user_email,
            phone_verification_transport=phone_verification_transport,
        )

    code = request.form.get("code", "").strip()

    if not code or len(code) != 6 or not code.isdigit():
        flash("Please enter a valid 6-digit code.", "danger")
        return redirect(request.referrer or url_for("index"))

    success, message = PhoneVerificationService.verify_code(
        user=current_user,
        profile=profile,
        code=code,
    )

    if success:
        flash("Phone number verified successfully!", "success")
        session['phone_verified'] = True
        return redirect(url_for("profile.account_overview"))
    else:
        flash(f"Invalid or expired verification code: {message}", "danger")

    return redirect(request.referrer or url_for("index"))

@auth_bp.route("/resend-verification", methods=["GET"], endpoint="resend_verification")
@login_required
@limiter.limit("5 per hour")
def resend_verification():
    """Resend a verification email to the current user."""
    from app.auth.email import send_verification_email

    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))

    if getattr(current_user, "is_verified", False):
        flash("Your email is already verified.", "info")
        return redirect(request.referrer or url_for("profile.account_overview"))

    if not getattr(current_user, "email", None):
        flash("No email address is set on your account.", "danger")
        return redirect(request.referrer or url_for("profile.account_overview"))

    if send_verification_email(current_user):
        flash("Verification email resent. Please check your inbox.", "success")
    else:
        flash("Unable to resend verification email at this time. Please contact support.", "danger")

    return redirect(request.referrer or url_for("profile.account_overview"))

@auth_bp.route("/deactivate-account", endpoint="deactivate_account")
@login_required
def deactivate_account():
    from app.auth.services import activate_user

    if activate_user(str(current_user.public_id), active=False, actor_id=str(current_user.public_id)):
        logout_user()
        flash("Your account has been deactivated.", "info")
        return redirect(url_for("auth.login"))

    flash("Unable to deactivate your account. Please contact support.", "danger")
    return redirect(request.referrer or url_for("profile.account_overview"))

@auth_bp.route("/delete-account", endpoint="delete_account")
@login_required
def delete_account():
    flash("Account deletion is currently unavailable. Please contact support.", "warning")
    return redirect(request.referrer or url_for("profile.account_overview"))

@auth_bp.route("/send-phone-verification", methods=["POST"], endpoint="send_phone_verification")
@login_required
@limiter.limit("5 per hour")
def send_phone_verification():
    """
    Send a phone-verification OTP through the owner-selected transport.
    If a new phone number is provided and differs from the profile, update the profile first.
    """
    from app.auth.phone_verification import PhoneVerificationService
    from app.profile.models import get_profile_by_user

    phone_number = request.form.get("phone_number", "").strip()

    if not phone_number:
        profile = get_profile_by_user(current_user.public_id)
        if profile and profile.phone_number:
            phone_number = profile.phone_number
        else:
            flash("Please provide a phone number.", "danger")
            return redirect(request.referrer or url_for("auth.verify_phone"))

    user_email = getattr(current_user, 'email', '') or ''
    if not user_email:
        flash("No email address found on your account. Cannot send verification code.", "danger")
        return redirect(request.referrer or url_for("auth.verify_phone"))

    profile = get_profile_by_user(current_user.public_id)
    result = PhoneVerificationService.request_code(
        user=current_user,
        profile=profile,
        phone_number=phone_number,
    )

    if result.get('success'):
        if result.get('transport') == 'sms':
            flash(f"Verification code sent by SMS to {phone_number}.", "success")
        else:
            flash(f"Verification code sent to your email ({user_email}).", "success")
        if result.get('debug_otp'):
            flash(f"[DEV] Your verification code is {result['debug_otp']}", "info")
    else:
        flash(f"Failed to send verification code: {result.get('message', 'Unknown error')}", "danger")

    return redirect(request.referrer or url_for("auth.verify_phone"))


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def is_safe_url(target):
    host_url = request.host_url
    ref_url = urlparse(host_url)
    test_url = urlparse(urljoin(host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc

@auth_bp.route("/login", methods=["GET", "POST"], endpoint="login")
@limiter.limit("5 per minute", methods=["POST"])
@limiter.limit("30 per minute", methods=["GET"])
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

            # Check if account is active
            if not getattr(user, "is_active", True):
                flash("Please activate your account before logging in.", "warning")
                return render_template("auth/login.html", username=identifier)

            # SECURITY: Owner login with optional MFA (configurable)
            if user.is_app_owner():
                # Check if MFA is required for owners (configurable in settings)
                require_mfa = current_app.config.get('REQUIRE_OWNER_MFA', False)
                
                if require_mfa:
                    # Owners MUST have MFA enabled when requirement is active
                    if not getattr(user, 'mfa_enabled', False):
                        current_app.logger.warning(f"Owner {user.public_id} attempted login without MFA enabled (MFA required)")
                        flash("Owner accounts require Multi-Factor Authentication. Please set up MFA.", "danger")
                        return redirect(url_for("auth.setup_mfa"))
                    
                    # Verify MFA token for owners
                    mfa_code = request.form.get('mfa_code')
                    if not mfa_code:
                        flash("MFA code is required for owner login", "danger")
                        return render_template("login.html", username=identifier, require_mfa=True)
                    
                    # Validate MFA token
                    if not _verify_mfa_token(user, mfa_code):
                        current_app.logger.warning(f"Failed MFA attempt for owner {user.public_id}")
                        flash("Invalid MFA code. Please try again.", "danger")
                        return render_template("login.html", username=identifier, require_mfa=True)
                    
                    # MFA passed - track in session
                    session["mfa_verified"] = True
                else:
                    # MFA not required, but check if user has it enabled anyway
                    if getattr(user, 'mfa_enabled', False):
                        # User has MFA - verify it for extra security even when not required
                        mfa_code = request.form.get('mfa_code')
                        if mfa_code and not _verify_mfa_token(user, mfa_code):
                            flash("Invalid MFA code. Please try again.", "danger")
                            return render_template("login.html", username=identifier, require_mfa=True)
                        # If no MFA code provided but user has MFA, we'll still allow login
                        # (this maintains backward compatibility while encouraging MFA use)
                
                # Proceed with login
                login_user(user, remember="remember" in request.form)
                current_app.logger.warning(
                    f"LOGIN_USER session_id={user.get_id()}"
                )

                # Set up session for owner
                require_mfa = current_app.config.get('REQUIRE_OWNER_MFA', False)
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
                    "mfa_verified": session.get("mfa_verified", False),  # Track actual MFA verification
                    "mfa_required": require_mfa,  # Track if MFA was required
                })

                mfa_status = "with MFA" if session.get("mfa_verified") else "(MFA not required)"
                current_app.logger.info(f"Owner {user.public_id} logged in successfully {mfa_status}")
                flash("Welcome back, owner!", "success")

                # Redirect to owner dashboard
                next_page = request.args.get("next") or session.pop("next_url", None)
                if not next_page or not is_safe_url(next_page):
                    next_page = url_for("admin.owner.dashboard")
                return redirect(next_page)

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
            current_app.logger.warning(
                f"LOGIN_USER session_id={user.get_id()}"
            )

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


@auth_bp.route("/change-username", methods=["GET"], endpoint="change_username")
@login_required
def change_username():
    """Redirect missing username-change endpoint to profile edit."""
    return redirect(url_for("profile.edit_profile"))


@auth_bp.route("/change-password", methods=["GET"], endpoint="change_password")
@login_required
def change_password():
    """Redirect missing password-change endpoint to reset request."""
    return redirect(url_for("auth.reset_request"))


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
        "available_orgs", "needs_profile_completion",
        "active_context_type", "active_context_id", "active_role",
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
# Operating Context Switching
# ---------------------------------------------------------------------------

@auth_bp.route("/switch-context", methods=["POST"])
@auth_bp.route("/switch-context/<context>", methods=["POST"])
@login_required
def switch_context(context=None):
    """
    Select one already-authorised operating context.

    The path parameter is retained only as a POST compatibility shape. The
    request body is the canonical contract and is validated by the resolver.
    Flask-WTF's application-wide CSRF protection rejects missing/invalid tokens
    before this function executes.
    """
    from app.auth.context import (
        ContextRequest,
        ContextSwitchError,
        get_active_context,
        switch_context as select_context,
    )
    from app.audit.forensic_audit import ForensicAuditService

    logger.info("Context switch request received: user=%s path=%s", current_user.public_id, request.path)
    payload = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    payload = payload or {}
    if context and not payload.get("type"):
        payload["type"] = context
    if not payload.get("id") and not payload.get("public_id"):
        payload["id"] = payload.get("org_id") or payload.get("event_id")
    if not payload.get("role") and context in ("individual", "personal"):
        payload["role"] = "user"

    previous = get_active_context(current_user)
    requested_type = payload.get("type") or "unknown"
    requested_id = payload.get("public_id", payload.get("id"))
    audit_details = {
        "previous_context": previous.to_dict(),
        "requested_context": {
            "type": str(requested_type),
            "public_id": str(requested_id) if requested_id else None,
            "role": payload.get("role"),
        },
    }
    audit_id = ForensicAuditService.log_attempt(
        entity_type="operating_context",
        entity_id=str(requested_id or current_user.public_id),
        action="switch",
        user_id=current_user.id,
        details=audit_details,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
    )

    wants_json = request.is_json or request.accept_mimetypes.best == "application/json"
    try:
        normalized = ContextRequest.from_value(payload)
        if normalized.type.value != "personal" and not normalized.role:
            raise ContextSwitchError("role is required for a non-personal context")
        selected = select_context(current_user, normalized)
    except (ContextSwitchError, ValueError) as exc:
        ForensicAuditService.log_blocked(
            entity_type="operating_context",
            entity_id=str(requested_id or current_user.public_id),
            action="switch",
            user_id=current_user.id,
            reason=str(exc),
            attempted_value=json.dumps(audit_details, default=str),
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
        )
        if wants_json:
            return jsonify({"success": False, "error": "Invalid or unassigned context"}), 400
        flash("That operating context is unavailable.", "danger")
        return redirect(url_for("user.dashboard"))

    ForensicAuditService.log_completion(
        audit_id,
        result_details={"context": selected.to_dict()},
    )
    # A context switch must enter the selected workspace.  The browser sends
    # the current page as ``next`` for compatibility, but that is commonly
    # ``/user/dashboard`` and must not override the resolved destination.
    target = selected.workspace_url
    if not target:
        target = payload.get("next")
    if not target or not is_safe_url(target):
        target = url_for("user.dashboard")
    if wants_json:
        logger.info("Context switch completed: user=%s type=%s public_id=%s role=%s redirect=%s", current_user.public_id, selected.type.value, selected.public_id, selected.role, target)
        return jsonify({"success": True, "context": selected.to_dict(), "redirect": target})
    return redirect(target)


# ---------------------------------------------------------------------------
# Global Role Switching
# ---------------------------------------------------------------------------

@auth_bp.route("/switch-role", methods=["GET", "POST"])
@login_required
def switch_role():
    """
    UI and handler for switching between multiple global roles.
    Allows a user to 'act as' a lower privilege role for testing or focused work.
    """
    from app.auth.helpers import switch_global_role, get_active_role_name
    from app.identity.models.roles_permission import Role

    # GET: Render the role selection page
    if request.method == "GET":
        # Get all global roles assigned to this user
        # user.roles is joined-loaded and contains UserRole objects
        available_roles = [ur.role for ur in current_user.roles if ur.role and ur.role.is_global]
        
        # Sort by level (owner=1, super_admin=2, etc.)
        available_roles.sort(key=lambda r: r.level or 999)

        return render_template(
            "auth/switch_role.html",
            roles=available_roles,
            active_role=get_active_role_name()
        )

    # POST: Process the switch request
    role_name = request.form.get("role_name")
    
    # Handle the 'Reset' case explicitly if provided
    if not role_name or role_name.lower() in ['all', 'reset', 'default']:
        role_name = None

    success, message = switch_global_role(role_name)
    
    if success:
        flash(message, "success")
        # Redirect to dashboard or previous page
        return redirect(url_for("user.dashboard"))
    else:
        flash(message, "danger")
        return redirect(url_for("auth.switch_role"))

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
        return redirect(url_for("user.dashboard"))

    return render_template("kyc/complete_profile.html")


# ---------------------------------------------------------------------------
# Enhanced MFA Routes
# ---------------------------------------------------------------------------

@auth_bp.route('/mfa/setup')
@login_required
def mfa_setup():
    """MFA setup page."""
    from app.identity.models.user import MFASecret
    
    # Check if MFA is already enabled
    existing_mfa = MFASecret.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).first()
    
    if existing_mfa:
        flash('MFA is already enabled for your account', 'info')
        return redirect(url_for('auth.mfa_status'))
    
    return render_template('auth/mfa_setup.html')

# Backwards compatible alias for templates that still link to auth.setup_mfa
auth_bp.add_url_rule('/mfa/setup', endpoint='setup_mfa', view_func=mfa_setup)

@auth_bp.route('/mfa/enable', methods=['POST'])
@login_required
@require_fresh_user
def mfa_enable():
    """Enable MFA for user."""
    from app.identity.models.user import MFASecret
    import pyotp
    import qrcode
    import io
    import base64
    
    mfa_type = request.form.get('mfa_type', 'totp')
    device_name = request.form.get('device_name', 'Primary Device')
    
    if mfa_type == 'totp':
        # Generate TOTP secret
        secret = pyotp.random_base32()
        
        # Create MFA record
        mfa_secret = MFASecret(
            user_id=current_user.id,
            mfa_type=mfa_type,
            secret=secret,
            device_name=device_name,
            is_active=True
        )
        
        # Generate backup codes
        backup_codes = mfa_secret.generate_backup_codes()
        mfa_secret.store_backup_codes(backup_codes)
        
        db.session.add(mfa_secret)
        
        # Update user
        current_user.mfa_enabled = True
        current_user.enable_mfa('totp', enabled_by_user_id=current_user.id)
        
        db.session.commit()
        
        # Generate QR code
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=f"user_{current_user.id}@afcon360.com",
            issuer_name="AFCON360 Wallet"
        )
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        qr_code = f"data:image/png;base64,{img_str}"
        
        return jsonify({
            'success': True,
            'secret': secret,
            'qr_code': qr_code,
            'backup_codes': backup_codes
        })
    
    return jsonify({'success': False, 'error': 'Unsupported MFA type'})

@auth_bp.route('/mfa/status')
@login_required
def mfa_status():
    """MFA status page."""
    from app.identity.models.user import MFASecret
    
    mfa_secrets = MFASecret.query.filter_by(user_id=current_user.id).all()
    
    return render_template('auth/mfa_status.html', mfa_secrets=mfa_secrets)

@auth_bp.route("/mfa/<user_id>", methods=["GET", "POST"], endpoint="mfa")
def mfa(user_id: str):
    flash("Multi-factor authentication is not yet active.", "danger")
    return redirect(url_for("auth.login"))



def get_active_channels(user) -> List[Dict[str, Any]]:
    """
    Returns list of {"id", "label", "contact"} for channels enabled in AuthConfiguration.otp_channels
    AND for which user has contact info (email/sms/whatsapp need user.email/user.phone).
    """
    from app.auth.config_model import AuthConfiguration
    cfg = AuthConfiguration.get_config()
    otp_channels = cfg.otp_channels or {}
    
    channels = []
    
    # Email
    email_cfg = otp_channels.get("email", {})
    if email_cfg.get("enabled", True) and getattr(user, "email", None):
        email_val = user.email
        masked = email_val if len(email_val) <= 6 else (email_val[:3] + "..." + email_val[email_val.find("@")-1:])
        channels.append({
            "id": "email",
            "label": "Email Verification",
            "contact": masked,
            "verified": getattr(user, "email_verified", False),
            "verified_at": getattr(user, "email_verified_at", None),
        })

    # SMS
    sms_cfg = otp_channels.get("sms", {})
    if sms_cfg.get("enabled", False) and getattr(user, "phone", None):
        phone_val = user.phone
        masked_phone = phone_val if len(phone_val) <= 4 else ("***" + phone_val[-4:])
        channels.append({
            "id": "sms",
            "label": "SMS Verification",
            "contact": masked_phone,
            "verified": getattr(user, "phone_verified", False),
            "verified_at": getattr(user, "phone_verified_at", None),
        })

    # WhatsApp
    wa_cfg = otp_channels.get("whatsapp", {})
    if wa_cfg.get("enabled", False) and getattr(user, "phone", None):
        phone_val = user.phone
        masked_phone = phone_val if len(phone_val) <= 4 else ("***" + phone_val[-4:])
        channels.append({
            "id": "whatsapp",
            "label": "WhatsApp Verification",
            "contact": masked_phone,
            "verified": getattr(user, "phone_verified", False),
            "verified_at": getattr(user, "phone_verified_at", None),
        })

    return channels


@auth_bp.route("/verify-options", methods=["GET", "POST"], endpoint="verify_options")
@login_required
def verify_options():
    """GET renders auth/verify_options.html with channels; POST takes channel, validates enabled + contact present + no auto-fallback, calls right OTP sender, redirects to /verify-otp?channel=..."""
    channels = get_active_channels(current_user)

    if request.method == "POST":
        channel = request.form.get("channel")
        if not channel:
            flash("Please select a verification channel.", "danger")
            return render_template("auth/verify_options.html", channels=channels)

        # Validate channel is enabled and contact present
        from app.auth.config_model import AuthConfiguration
        cfg = AuthConfiguration.get_config()
        otp_channels = cfg.otp_channels or {}
        ch_settings = otp_channels.get(channel, {})

        if not ch_settings.get("enabled", False) and channel != "email":
            flash(f"Verification channel '{channel}' is not enabled.", "danger")
            return render_template("auth/verify_options.html", channels=channels)

        if channel == "email" and not current_user.email:
            flash("No email address configured for this account.", "danger")
            return render_template("auth/verify_options.html", channels=channels)

        if channel in ("sms", "whatsapp") and not current_user.phone:
            flash(f"No phone number configured for {channel} verification. Please update your profile.", "danger")
            return render_template("auth/verify_options.html", channels=channels)

        from app.auth.pending_registration import start_channel_verification
        success, message, debug_otp = start_channel_verification(current_user.id, channel)
        if not success:
            flash(message, "danger")
            return render_template("auth/verify_options.html", channels=channels)

        if debug_otp:
            flash(f"[DEV] Verification code: {debug_otp}", "info")

        flash(message, "success")
        return redirect(url_for("auth.verify_otp", channel=channel))

    return render_template("auth/verify_options.html", channels=channels)


@auth_bp.route("/verify-otp", methods=["GET", "POST"], endpoint="verify_otp")
@login_required
def verify_otp():
    """GET shows OTP entry form; POST verifies via verify_channel_otp, on success flashes and redirects to dashboard; if failed attempts exceeded, allow re-choose."""
    channel = request.args.get("channel") or request.form.get("channel") or "email"
    channels = get_active_channels(current_user)

    if request.method == "POST":
        code = request.form.get("code")
        from app.auth.pending_registration import verify_channel_otp
        success, message = verify_channel_otp(current_user.id, channel, code)
        if success:
            flash("Account successfully verified!", "success")
            # Redirect to appropriate dashboard
            if current_user.is_app_owner():
                return redirect(url_for("admin.owner.dashboard"))
            elif current_user.has_global_role("admin", "super_admin"):
                return redirect(url_for("admin.dashboard"))
            else:
                return redirect(url_for("dashboard.index") if "dashboard.index" in current_app.view_functions else "/")
        else:
            flash(message, "danger")

    return render_template("auth/verify_otp.html", channel=channel, channels=channels)
@auth_bp.route("/test-csrf")
@login_required
def test_csrf():
    """Test CSRF token generation"""
    token = generate_csrf_token()
    print(f"CSRF Token generated: {token}")
    return f"CSRF Token: {token} (check console for value)"

