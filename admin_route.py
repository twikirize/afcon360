from flask import render_template, redirect, url_for, current_app, request, flash
from flask_login import login_required, current_user
from app.admin import admin_bp
from app.extensions import db
from app.models.app_config import AppConfig

ALLOWED_DYNAMIC_KEYS = {"MODULE_FLAGS", "WALLET_FEATURES"}


@admin_bp.before_request
@login_required
def require_super_admin():
    if not getattr(current_user, "is_super_admin", False):
        flash("Unauthorized access.", "danger")
        return redirect(url_for("index"))


@admin_bp.route("/super", endpoint="super_dashboard")
def super_dashboard():
    return render_template(
        "super_admindashboard.html",
        modules=current_app.config.get("MODULE_FLAGS", {}),
        wallet_features=current_app.config.get("WALLET_FEATURES", {}),
    )


@admin_bp.route("/update-withdraw-settings", methods=["POST"])
def update_withdraw_settings():
    cfg = AppConfig.query.filter_by(key="WALLET_FEATURES").first()

    if not cfg or cfg.key not in ALLOWED_DYNAMIC_KEYS:
        flash("Wallet configuration unavailable.", "danger")
        return redirect(url_for("admin.super_dashboard"))

    withdraw = cfg.value.get("withdraw", {})

    withdraw["daily_limit"] = int(request.form.get("daily_limit", 0))
    withdraw["require_verification"] = "require_verification" in request.form

    cfg.value["withdraw"] = withdraw
    db.session.commit()

    current_app.config["WALLET_FEATURES"] = cfg.value

    current_app.logger.warning(
        "CONFIG_CHANGE | user=%s | WALLET_FEATURES.withdraw=%s",
        current_user.user_id,
        withdraw,
    )

    flash("Withdraw settings updated.", "success")
    return redirect(url_for("admin.super_dashboard"))


@admin_bp.route("/toggle/<module>", methods=["POST"])
def toggle_module(module):
    cfg = AppConfig.query.filter_by(key="MODULE_FLAGS").first()

    if not cfg or cfg.key not in ALLOWED_DYNAMIC_KEYS:
        flash("Module configuration unavailable.", "danger")
        return redirect(url_for("admin.super_dashboard"))

    if module not in cfg.value:
        flash(f"Module '{module}' not found.", "warning")
        return redirect(url_for("admin.super_dashboard"))

    cfg.value[module] = not bool(cfg.value[module])
    db.session.commit()

    current_app.config["MODULE_FLAGS"] = cfg.value

    current_app.logger.warning(
        "CONFIG_CHANGE | user=%s | MODULE_FLAGS.%s=%s",
        current_user.user_id,
        module,
        cfg.value[module],
    )

    flash(f"Module '{module}' updated.", "success")
    return redirect(url_for("admin.super_dashboard"))
