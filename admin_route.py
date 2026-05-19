from flask import render_template, redirect, url_for, current_app, flash
from flask_login import login_required, current_user

from app.admin import admin_bp
from app.services import ModuleToggleService


def _user_is_owner() -> bool:
    return hasattr(current_user, "has_global_role") and current_user.has_global_role("owner")


def _user_is_super_admin() -> bool:
    return bool(getattr(current_user, "is_super_admin", False) or (
        hasattr(current_user, "has_global_role") and current_user.has_global_role("super_admin")
    ))


@admin_bp.before_request
@login_required
def require_super_admin():
    if not (_user_is_super_admin() or _user_is_owner()):
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
    module_key = module.strip().lower()
    flags = ModuleToggleService.get_flags()
    if module_key not in flags:
        flash(f"Module '{module_key}' not found.", "warning")
        return redirect(url_for("admin.super_dashboard"))

    if not _user_is_owner():
        # Only owners can toggle unless owner has delegated to super admins
        from app.admin.owner.models import SystemSetting

        if not SystemSetting.get("SUPER_ADMIN_CAN_TOGGLE_MODULES", False):
            flash("Owner has restricted module toggles to themselves.", "warning")
            return redirect(url_for("admin.super_dashboard"))

    new_state = not bool(flags.get(module_key))
    ModuleToggleService.set_flag(module_key, new_state, updated_by=getattr(current_user, "id", None))

    current_app.logger.warning(
        "CONFIG_CHANGE | user=%s | MODULE_FLAGS.%s=%s",
        getattr(current_user, "user_id", getattr(current_user, "id", None)),
        module_key,
        new_state,
    )

    flash(
        f"Module '{module_key}' {'enabled' if new_state else 'disabled'}.",
        "success" if new_state else "info",
    )
    return redirect(url_for("admin.super_dashboard"))
