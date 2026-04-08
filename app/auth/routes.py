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

# Standardized blueprint name: auth
auth_bp = Blueprint("auth", __name__, url_prefix="")


# ---------------------------------------------------------------------------
# Post-login redirect helper
# ---------------------------------------------------------------------------

def _dashboard_for_user(user) -> str:
    """
    Return the URL for this user's home dashboard based on their
    HIGHEST-PRIVILEGE role (role hierarchy aware).
    """
    # Get user's role names safely
    role_names = set()
    try:
        for user_role in user.roles:
            if user_role.role:
                role_names.add(user_role.role.name)
    except Exception as e:
        current_app.logger.warning(f"Error getting user roles: {e}")

    # Check roles in priority order (highest first)
    if "owner" in role_names:
        return url_for("admin.owner.dashboard")

    if "super_admin" in role_names or "admin" in role_names:
        return url_for("admin.super_dashboard")

    if "org_admin" in role_names:
        try:
            return url_for("org.dashboard")
        except:
            return url_for("index")

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
@limiter.limit("5 per minute")
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

            if require_verification and not getattr(user, "is_verified", False):
                flash("Please confirm your email address.", "warning")
                return render_template("login.html", username=identifier)

            login_user(user, remember="remember" in request.form)

            session.update({
                "server_session_id": session_id,
                "user_id":           user.user_id,
                "username":          user.username,
                "ip":                ip,
                "user_agent":        user_agent,
            })

            next_page = request.args.get("next") or session.pop("next_url", None)
            if not next_page or not is_safe_url(next_page):
                next_page = _dashboard_for_user(user)

            return redirect(next_page)

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
    for key in ("server_session_id", "user_id", "username"):
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
# MFA
# ---------------------------------------------------------------------------

@auth_bp.route("/mfa/<user_id>", methods=["GET", "POST"], endpoint="mfa")
def mfa(user_id: str):
    flash("Multi-factor authentication is not yet active.", "danger")
    return redirect(url_for("auth.login"))
