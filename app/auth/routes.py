# app/auth/routes.py
"""
Authentication routes: register, verify, login, logout, password reset, MFA.

Post-login redirect
-------------------
After a successful login every user is routed to their role-appropriate
dashboard via ``_dashboard_for_user()``. No user ever lands somewhere
they should not be.

Role → destination mapping (evaluated highest-privilege first):
    owner / super_admin  →  admin.super_dashboard
    admin                →  admin.super_dashboard  (until admin_dashboard is built)
    moderator            →  index                  (until moderator_dashboard is built)
    support              →  index                  (until support_dashboard is built)
    fan  (end user)      →  index  (public home)

Add new dashboards by updating ``_dashboard_for_user`` — the rest of the
login flow does not need to change.
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.auth.decorators import require_role  # noqa: F401 — re-exported
from app.auth.services import (
    AuthResult,
    authenticate_user,
    register_user,
    request_password_reset,
    verify_email,
)
from app.auth.sessions import revoke_session
from app.auth.validators import validate_registration
from app.extensions import db, limiter
from app.identity.models.user import User


auth_routes = Blueprint("auth_routes", __name__, url_prefix="")


# ---------------------------------------------------------------------------
# Post-login redirect helper
# ---------------------------------------------------------------------------

def _dashboard_for_user(user: User) -> str:
    """
    Return the URL for this user's home dashboard based on their
    highest-privilege role.

    Evaluated in privilege order — the first matching role wins.
    Update this function as new dashboards are built.
    """
    role_names = set(user.role_names)

    if role_names & {"owner", "super_admin"}:
        return url_for("admin.super_dashboard")

    if "admin" in role_names:
        # TODO: swap for url_for("admin.admin_dashboard") when built
        return url_for("admin.super_dashboard")

    if "moderator" in role_names:
        # TODO: swap for url_for("admin.moderator_dashboard") when built
        return url_for("index")

    if "support" in role_names:
        # TODO: swap for url_for("admin.support_dashboard") when built
        return url_for("index")

    # fan / end user → public home
    return url_for("index")


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _ct_delay() -> None:
    """
    Constant-time delay to prevent username/password timing enumeration.
    Uses CSPRNG for jitter — not predictable.
    """
    # 50–100 ms delay with random jitter
    time.sleep(0.050 + secrets.randbelow(51) / 1000.0)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@auth_routes.route("/register", methods=["GET", "POST"], endpoint="register")
@limiter.limit("10 per minute")
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password =  request.form.get("password") or ""
        email    = (request.form.get("email")    or "").strip() or None

        # SECURITY: hard length caps before any processing (DoS prevention)
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
            current_app.logger.warning(
                "registration_rejected",
                extra={"reason": str(exc), "username": username, "email": email},
            )
            flash(str(exc) or "Invalid registration details.", "warning")
            return render_template("register.html", username=username, email=email)

        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "registration_backend_error",
                extra={"username": username, "email": email},
            )
            flash(
                "Registration is temporarily unavailable. Please try again later.",
                "danger",
            )
            return render_template("register.html", username=username, email=email)

        flash(
            "Registration successful! Please check your email for a verification link.",
            "success",
        )
        return redirect(url_for("auth_routes.login"))

    return render_template("register.html")


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

@auth_routes.route("/verify", methods=["GET"], endpoint="verify")
@limiter.limit("30 per hour")
def verify():
    token = request.args.get("token")
    # SECURITY: cap token length
    token = token[:128] if token else None
    if not token or not verify_email(token):
        flash("Invalid or expired verification link.", "danger")
        return redirect(url_for("auth_routes.login"))

    flash("Email verified. You can now log in.", "success")
    return redirect(url_for("auth_routes.login"))


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@auth_routes.route("/login", methods=["GET", "POST"], endpoint="login")
@limiter.limit("5 per minute")
def login():
    require_verification = current_app.config.get("VERIFY_EMAIL_REQUIRED", False)

    if request.method == "POST":
        # SECURITY: hard caps before any processing (DoS prevention)
        identifier = (request.form.get("username") or "").strip()[:64]
        password   = (request.form.get("password") or "")[:128]
        ip         = request.remote_addr
        user_agent = request.headers.get("User-Agent", "")

        # ── Authenticate ──────────────────────────────────────────────────
        try:
            result, payload = authenticate_user(
                identifier=identifier,
                password=password,
                ip=ip,
                user_agent=user_agent,
            )
        except Exception:
            current_app.logger.exception(
                "login_backend_error",
                extra={"identifier": identifier, "ip": ip},
            )
            _ct_delay()  # SECURITY: constant-time delay
            flash("Login is temporarily unavailable. Please try again later.", "danger")
            return render_template("login.html", username=identifier)

        # ── Handle AuthResult branches ────────────────────────────────────

        if result == AuthResult.SUCCESS:
            user       = payload["user"]
            session_id = payload["session_id"]

            if require_verification and not getattr(user, "is_verified", False):
                flash("Please confirm your email address before logging in.", "warning")
                return render_template("login.html", username=identifier)

            if not getattr(user, "is_verified", False):
                flash("Your email is not verified. Some features may be restricted.", "info")

            try:
                previous_sid = session.get("server_session_id")
                if previous_sid:
                    _revoke_server_session(previous_sid)

                login_user(user, remember="remember" in request.form)

                # SECURITY: Do NOT store roles in session — always read from DB
                # Storing roles creates stale privilege escalation window.
                # User roles are loaded by Flask-Login's user_loader on every request.
                session.update({
                    "server_session_id": session_id,
                    "user_id":           user.user_id,
                    "username":          user.username,
                    "ip":                ip,
                    "user_agent":        user_agent,
                })

                current_app.logger.info(
                    "login_success",
                    extra={
                        "uid":        user.user_id,
                        "ip":         ip,
                        "identifier": identifier,
                        "session_id": session_id,
                        "roles":      user.role_names,
                    },
                )

            except Exception:
                current_app.logger.exception(
                    "login_session_error",
                    extra={"uid": getattr(user, "user_id", None)},
                )
                flash("Login failed due to a system error. Please try again later.", "danger")
                return render_template("login.html", username=identifier)

            # ── Role-based redirect ───────────────────────────────────────
            return redirect(_dashboard_for_user(user))

        # ── MFA handling ──────────────────────────────────────────────────
        # SECURITY FIX: MFA stub no longer bypasses authentication.
        # TODO: Implement TOTP (pyotp) with mfa_secret column in User model.
        # When ready, replace this block with real MFA flow.
        if result == AuthResult.MFA_REQUIRED:
            current_app.logger.warning(
                "mfa_required_but_not_implemented",
                extra={"uid": payload.get("user_id"), "ip": ip},
            )
            flash(
                "Multi-factor authentication is required for this account "
                "but is not yet active. Contact support.",
                "danger",
            )
            _ct_delay()
            return render_template("login.html", username=identifier)

        # ── Failure paths (all get constant-time delay) ───────────────────
        _ct_delay()

        if result == AuthResult.LOCKED:
            flash("Your account is temporarily locked. Please try again later.", "danger")
            current_app.logger.info(
                "login_locked", extra={"identifier": identifier, "ip": ip}
            )
        elif result == AuthResult.INACTIVE:
            flash("This account is inactive or deleted. Contact support.", "warning")
            current_app.logger.info(
                "login_inactive", extra={"identifier": identifier, "ip": ip}
            )
        elif result == AuthResult.NOT_FOUND:
            # SECURITY: same message as INVALID_CREDENTIALS — prevents user enumeration
            flash("Invalid username or password.", "danger")
            current_app.logger.info(
                "login_not_found", extra={"ip": ip}
            )
        else:
            # INVALID_CREDENTIALS (default)
            flash("Invalid username or password.", "danger")
            current_app.logger.info(
                "login_failed", extra={"identifier": identifier, "ip": ip}
            )

        return render_template("login.html", username=identifier)

    return render_template("login.html")


# ---------------------------------------------------------------------------
# Logout  — SECURITY FIX: POST only (prevents CSRF logout attacks)
# ---------------------------------------------------------------------------

@auth_routes.route("/logout", methods=["POST"], endpoint="logout")
@login_required
def logout():
    """
    Secure logout — POST method only.

    This prevents CSRF attacks where malicious sites can log users out
    via GET requests (<img src="/logout">).

    Template requirement:
        Use a form with CSRF token instead of an anchor tag:

        <form method="POST" action="{{ url_for('auth_routes.logout') }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button type="submit">Log out</button>
        </form>

    Future improvements:
        - Add logout from all devices option
        - Revoke API tokens / JWTs
        - Log security event for audit
    """
    ssid       = session.get("server_session_id")
    uid        = current_user.user_id if current_user.is_authenticated else None
    ip         = request.remote_addr
    user_agent = request.headers.get("User-Agent", "")

    try:
        if ssid:
            revoke_session(ssid)

        # Future: revoke all sessions (multi-device logout)
        # Future: revoke API tokens / JWTs

        current_app.logger.info(
            "logout_success",
            extra={
                "uid":        uid,
                "ssid":       ssid,
                "ip":         ip,
                "user_agent": user_agent,
                "timestamp":  datetime.utcnow().isoformat(),
            },
        )

    except Exception as exc:
        current_app.logger.warning(
            "logout_revoke_failed",
            extra={"uid": uid, "ssid": ssid, "error": str(exc), "ip": ip},
        )

    logout_user()

    for key in ("server_session_id", "user_id", "username"):
        session.pop(key, None)

    flash("You have been logged out.", "info")
    return redirect(url_for("auth_routes.login"))


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

@auth_routes.route("/reset/request", methods=["GET", "POST"], endpoint="reset_request")
@limiter.limit("10 per hour")
def reset_request():
    if request.method == "POST":
        # SECURITY: cap username length
        username = (request.form.get("username") or "").strip()[:64]
        user     = User.query.filter_by(username=username).first()

        if user and user.email:
            request_password_reset(user)
            current_app.logger.info(
                "password_reset_requested",
                extra={"uid": user.user_id, "username": user.username},
            )

        # Always show the same message to prevent username enumeration.
        flash("If that account exists, a password reset link has been sent.", "info")
        return redirect(url_for("auth_routes.login"))

    return render_template("reset_request.html")


# ---------------------------------------------------------------------------
# MFA  (stub — disabled until TOTP is implemented)
# ---------------------------------------------------------------------------

@auth_routes.route("/mfa/<user_id>", methods=["GET", "POST"], endpoint="mfa")
def mfa(user_id: str):
    """
    MFA verification placeholder.

    SECURITY NOTE: This stub no longer bypasses authentication.
    Previously, this route allowed unauthenticated users to proceed
    into the application. Now it blocks access with a clear message.

    Implementation plan when TOTP is ready:
        1. pip install pyotp
        2. Add mfa_secret column to User model
        3. Add mfa_enabled column to User model
        4. Generate QR code for user setup (otpauth:// URI)
        5. Verify TOTP code with pyotp.TOTP(secret).verify(code)
        6. On success: login_user() and clear mfa_pending flag

    The complete implementation is available in the security_suite
    reference files (app/auth/routes.py from that package).
    """
    # SECURITY: Block access instead of bypassing auth
    flash(
        "Multi-factor authentication is required for this account "
        "but has not been activated yet. Please contact support.",
        "danger",
    )
    return redirect(url_for("auth_routes.login"))


# ---------------------------------------------------------------------------
# Private session helpers  (internal to this module only)
# ---------------------------------------------------------------------------

def _start_server_session(
    user_id: int,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """Create a server-side session record and return its ID."""
    from app.identity.models.user import Session as ServerSession

    sid = secrets.token_urlsafe(32)
    s   = ServerSession(
        session_id = sid,
        user_id    = user_id,
        ip         = ip,
        user_agent = user_agent,
        created_at = datetime.utcnow(),
        expires_at = datetime.utcnow() + timedelta(hours=8),
    )
    db.session.add(s)
    db.session.flush()
    return sid


def _revoke_server_session(session_id: str) -> None:
    """Mark a server-side session as revoked."""
    from app.identity.models.user import Session as ServerSession

    s = ServerSession.query.filter_by(session_id=session_id).first()
    if s:
        s.revoked_at = datetime.utcnow()
        db.session.commit()