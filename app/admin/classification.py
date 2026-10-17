"""
Organisation Classification Manager for AFCON360.

Provides admin interface for managing organisation categories and
organisation types with proper permission gating.

Features:
- Category CRUD (add, edit, deactivate, activate)
- Organisation type CRUD (add, edit, move between categories)
- Dependency checking before deletion
- Audit trail for all changes
- Stable code preservation for existing types
"""

from datetime import datetime, timezone
import logging
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)
from flask_login import login_required, current_user
from app.auth.decorators import admin_required
from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_catalogues import (
    OrganisationCategory,
    OrganisationTypeCatalogue,
)

# Setup logging
logger = logging.getLogger(__name__)

# Blueprint for classification management
# Restricted to super_admin and owner only
classification_bp = Blueprint(
    "classification",
    __name__,
    url_prefix="/admin/classification",
    template_folder="templates",
)

# Allowed roles for classification management
CLASSIFICATION_MANAGER_ROLES = ("super_admin", "owner")


def _check_classification_permission():
    """Check if current user has permission to manage classification."""
    from app.auth.helpers import has_global_role
    return has_global_role(current_user, *CLASSIFICATION_MANAGER_ROLES)


# Helper: import audit logging locally to avoid module-level import issues
def _log_attempt(**kwargs):
    """Log an attempt with the forensic audit service."""
    from app.audit.forensic_audit import log_attempt as _internal_log_attempt
    _internal_log_attempt(**kwargs)


# -----------------------------
# Category CRUD Routes
# -----------------------------

@classification_bp.route("/", methods=["GET"])
@login_required
def category_list():
    """List all organisation categories."""
    if not _check_classification_permission():
        flash("Super admin or owner access required.", "danger")
        return redirect(url_for("admin.dashboard"))

    page = request.args.get("page", 1, type=int)
    per_page = 20

    query = OrganisationCategory.query.filter_by(is_active=True).order_by(
        OrganisationCategory.sort_order, OrganisationCategory.code
    )
    categories = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get inactive categories too for reference
    inactive_query = (
        OrganisationCategory.query.filter_by(is_active=False)
        .order_by(OrganisationCategory.sort_order, OrganisationCategory.code)
    )
    inactive_categories = inactive_query.all()

    # Count types in each category
    for cat in categories:
        cat.type_count = (
            OrganisationTypeCatalogue.query.filter_by(
                category_code=cat.code, is_active=True
            ).count()
        )

    for cat in inactive_categories:
        cat.type_count = (
            OrganisationTypeCatalogue.query.filter_by(category_code=cat.code).count()
        )

    return render_template(
        "admin/classification/category_list.html",
        categories=categories,
        inactive_categories=inactive_categories,
        current_tab="categories",
    )


@classification_bp.route("/create", methods=["GET", "POST"])
@login_required
def category_create():
    """Create a new organisation category."""
    if not _check_classification_permission():
        flash("Super admin or owner access required.", "danger")
        return redirect(url_for("admin.dashboard"))

    if request.method == "GET":
        return render_template("admin/classification/category_form.html", form_action="create")

    # POST - create new category
    name = (request.form.get("name") or "").strip()
    display_order = request.form.get("display_order") or 0
    description = (request.form.get("description") or "").strip()

    if not name:
        flash("Category name is required.", "danger")
        return redirect(url_for("admin.classification.category_list"))

    # Check if code already exists
    existing = OrganisationCategory.query.filter_by(code=name.lower()).first()
    if existing:
        flash(f"Category code '{name}' already exists.", "danger")
        return redirect(url_for("admin.classification.category_list"))

    try:
        new_category = OrganisationCategory(
            code=name.lower(),
            label=name,
            sort_order=int(display_order),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(new_category)
        db.session.commit()

        # Audit trail
        _log_attempt(
            entity_type="organisation_category",
            entity_id=str(new_category.id),
            action="category_create",
            user_id=current_user.id,
            risk_score=1,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
            correlation_id=current_user.correlation_id
            if hasattr(current_user, "correlation_id")
            else None,
        )

        flash(f"Category '{name}' created successfully.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating category: {e}")
        flash("Error creating category. Please try again.", "danger")

    return redirect(url_for("admin.classification.category_list"))


@classification_bp.route("/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
def category_edit(category_id):
    """Edit an existing organisation category."""
    if not _check_classification_permission():
        flash("Super admin or owner access required.", "danger")
        return redirect(url_for("admin.dashboard"))

    category = OrganisationCategory.query.get_or_404(category_id)

    if request.method == "GET":
        return render_template(
            "admin/classification/category_form.html",
            form_action="edit",
            category=category,
        )

    # POST - update category
    name = (request.form.get("name") or category.code).strip()
    display_order = request.form.get("display_order") or category.sort_order
    description = (request.form.get("description") or "").strip()
    is_active = request.form.get("is_active") == "on"

    if not name:
        flash("Category name is required.", "danger")
        return redirect(url_for("admin.classification.category_edit", category_id=category_id))

    # Check if code already exists (excluding current category)
    existing = (
        OrganisationCategory.query.filter(
            OrganisationCategory.code == name.lower(), OrganisationCategory.id != category_id
        )
        .first()
    )
    if existing:
        flash(f"Category code '{name}' already exists.", "danger")
        return redirect(
            url_for("admin.classification.category_edit", category_id=category_id)
        )

    # RESTRICT guard: organisation_types.category_code references
    # organisation_categories.code ON DELETE RESTRICT, so renaming the code
    # while any types (active or inactive) still reference it would fail at
    # the database. Reject upfront with an actionable message instead.
    # Non-code edits on referenced categories remain allowed.
    new_code = name.lower()
    if new_code != category.code:
        referencing = OrganisationTypeCatalogue.query.filter_by(
            category_code=category.code
        ).count()
        if referencing:
            flash(
                f"Category code cannot be changed while {referencing} "
                f"organisation type(s) still use '{category.code}'. "
                "Reassign those types to another category first, then rename.",
                "danger",
            )
            return redirect(
                url_for("admin.classification.category_edit", category_id=category_id)
            )

    try:
        category.code = name.lower()
        category.label = name
        category.sort_order = int(display_order)
        category.is_active = is_active
        category.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        # Audit trail
        _log_attempt(
            entity_type="organisation_category",
            entity_id=str(category.id),
            action="category_edit",
            user_id=current_user.id,
            risk_score=2,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
            correlation_id=current_user.correlation_id
            if hasattr(current_user, "correlation_id")
            else None,
        )

        flash(f"Category '{name}' updated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error editing category: {e}")
        flash("Error updating category. Please try again.", "danger")

    return redirect(url_for("admin.classification.category_list"))


@classification_bp.route("/<int:category_id>/deactivate", methods=["POST"])
@login_required
def category_deactivate(category_id):
    """Deactivate a category (hide from onboarding, keep for history)."""
    if not _check_classification_permission():
        flash("Super admin or owner access required.", "danger")
        return redirect(url_for("admin.dashboard"))

    category = OrganisationCategory.query.get_or_404(category_id)

    # Check if category has active types
    active_types = (
        OrganisationTypeCatalogue.query.filter_by(
            category_code=category.code, is_active=True
        ).count()
    )

    # Get organisations using this category
    used_by_orgs = (
        Organisation.query.filter(
            Organisation.organisation_type_code == category.code,
            Organisation.is_deleted == False,
        ).count()
    )

    if active_types > 0 or used_by_orgs > 0:
        # Cannot fully deactivate if types still reference it
        flash(
            f"Category has {active_types} active type(s) and is used by {used_by_orgs} organisation(s). "
            "Types will remain but category will be hidden from new onboarding.",
            "warning",
        )
    else:
        # Safe to fully deactivate
        category.is_active = False
        category.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        # Audit trail
        _log_attempt(
            entity_type="organisation_category",
            entity_id=str(category.id),
            action="category_deactivate",
            user_id=current_user.id,
            risk_score=2,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
            correlation_id=current_user.correlation_id
            if hasattr(current_user, "correlation_id")
            else None,
        )

        flash(f"Category '{category.label}' deactivated successfully.", "success")

    return redirect(url_for("admin.classification.category_list"))


@classification_bp.route("/<int:category_id>/activate", methods=["POST"])
@login_required
def category_activate(category_id):
    """Reactivate a previously deactivated category."""
    if not _check_classification_permission():
        flash("Super admin or owner access required.", "danger")
        return redirect(url_for("admin.dashboard"))

    category = OrganisationCategory.query.get_or_404(category_id)

    category.is_active = True
    category.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    # Audit trail
    _log_attempt(
        entity_type="organisation_category",
        entity_id=str(category.id),
        action="category_activate",
        user_id=current_user.id,
        risk_score=2,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=current_user.correlation_id
        if hasattr(current_user, "correlation_id")
        else None,
    )

    flash(f"Category '{category.label}' reactivated successfully.", "success")
    return redirect(url_for("admin.classification.category_list"))


# -----------------------------
# Organisation Type CRUD Routes
# -----------------------------

@classification_bp.route("/types", methods=["GET"])
@login_required
def type_list():
    """List all organisation types with their category assignments."""
    if not _check_classification_permission():
        flash("Super admin or owner access required.", "danger")
        return redirect(url_for("admin.dashboard"))

    page = request.args.get("page", 1, type=int)
    per_page = 30

    query = OrganisationTypeCatalogue.query.order_by(
        OrganisationTypeCatalogue.sort_order, OrganisationTypeCatalogue.code
    )
    types = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get inactive types
    inactive_query = OrganisationTypeCatalogue.query.filter(
        OrganisationTypeCatalogue.is_active == False
    )
    inactive_types = inactive_query.all()

    # Build category lookup
    category_map = {}
    for cat in OrganisationCategory.query.filter_by(is_active=True).all():
        category_map[cat.code] = cat

    # Count types per category
    for typ in types:
        typ.category_name = category_map.get(typ.category_code, "Unknown").label if typ.category_code else "Uncategorised"

    for typ in inactive_types:
        typ.category_name = category_map.get(typ.category_code, "Unknown").label if typ.category_code else "Uncategorised"

    return render_template(
        "admin/classification/type_list.html",
        types=types,
        inactive_types=inactive_types,
        category_map=category_map,
        current_tab="types",
    )


@classification_bp.route("/types/create", methods=["GET", "POST"])
@login_required
def type_create():
    """Create a new organisation type."""
    if not _check_classification_permission():
        flash("Super admin or owner access required.", "danger")
        return redirect(url_for("admin.dashboard"))

    # Get available categories for assignment
    categories = (
        OrganisationCategory.query.filter_by(is_active=True)
        .order_by(OrganisationCategory.sort_order, OrganisationCategory.code)
        .all()
    )

    if request.method == "GET":
        return render_template(
            "admin/classification/type_form.html",
            form_action="create",
            categories=categories,
        )

    # POST - create new type
    code = (request.form.get("code") or "").strip().lower()
    label = (request.form.get("label") or "").strip()
    category_code = request.form.get("category_code") or ""
    display_order = request.form.get("display_order") or 0
    description = (request.form.get("description") or "").strip()

    if not code:
        flash("Type code is required.", "danger")
        return redirect(url_for("admin.classification.type_list"))

    if not label:
        flash("Type label is required.", "danger")
        return redirect(url_for("admin.classification.type_list"))

    # Check if code already exists
    existing = OrganisationTypeCatalogue.query.filter_by(code=code).first()
    if existing:
        flash(f"Type code '{code}' already exists.", "danger")
        return redirect(url_for("admin.classification.type_list"))

    # Validate category_code if provided
    category = None
    if category_code:
        category = OrganisationCategory.query.filter_by(code=category_code).first()
        if not category:
            flash(f"Category code '{category_code}' not found.", "danger")
            return redirect(url_for("admin.classification.type_list"))

    try:
        new_type = OrganisationTypeCatalogue(
            code=code,
            label=label,
            category_code=category.code if category else None,
            sort_order=int(display_order),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(new_type)
        db.session.commit()

        # Audit trail
        _log_attempt(
            entity_type="organisation_type_catalogue",
            entity_id=str(new_type.id),
            action="type_create",
            user_id=current_user.id,
            risk_score=1,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
            correlation_id=current_user.correlation_id
            if hasattr(current_user, "correlation_id")
            else None,
        )

        flash(f"Organisation type '{label}' created successfully.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating type: {e}")
        flash("Error creating type. Please try again.", "danger")

    return redirect(url_for("admin.classification.type_list"))


@classification_bp.route("/types/<int:type_id>/edit", methods=["GET", "POST"])
@login_required
def type_edit(type_id):
    """Edit an existing organisation type."""
    if not _check_classification_permission():
        flash("Super admin or owner access required.", "danger")
        return redirect(url_for("admin.dashboard"))

    type_record = OrganisationTypeCatalogue.query.get_or_404(type_id)

    # Get available categories for reassignment
    categories = (
        OrganisationCategory.query.filter_by(is_active=True)
        .order_by(OrganisationCategory.sort_order, OrganisationCategory.code)
        .all()
    )

    if request.method == "GET":
        return render_template(
            "admin/classification/type_form.html",
            form_action="edit",
            type_record=type_record,
            categories=categories,
        )

    # POST - update type
    code = (request.form.get("code") or type_record.code).strip().lower()
    label = (request.form.get("label") or type_record.label).strip()
    category_code = request.form.get("category_code") or type_record.category_code or ""
    display_order = request.form.get("display_order") or type_record.sort_order
    is_active = request.form.get("is_active") == "on"

    if not code:
        flash("Type code is required.", "danger")
        return redirect(url_for("admin.classification.type_edit", type_id=type_id))

    if not label:
        flash("Type label is required.", "danger")
        return redirect(url_for("admin.classification.type_edit", type_id=type_id))

    # Check if code already exists (excluding current type)
    existing = (
        OrganisationTypeCatalogue.query.filter(
            OrganisationTypeCatalogue.code == code, OrganisationTypeCatalogue.id != type_id
        )
        .first()
    )
    if existing:
        flash(f"Type code '{code}' already exists.", "danger")
        return redirect(url_for("admin.classification.type_edit", type_id=type_id))

    # Validate new category if changed
    new_category = None
    new_cat_code = request.form.get("new_category_code") or ""
    if new_cat_code and new_cat_code != (type_record.category_code or ""):
        new_category = OrganisationCategory.query.filter_by(code=new_cat_code).first()
        if not new_category:
            flash(f"New category code '{new_cat_code}' not found.", "danger")
            return redirect(url_for("admin.classification.type_edit", type_id=type_id))

    try:
        type_record.code = code
        type_record.label = label
        type_record.sort_order = int(display_order)
        type_record.is_active = is_active

        # Handle category reassignment if requested
        target_cat_code = request.form.get("target_category_code") or ""
        if target_cat_code and target_cat_code != (type_record.category_code or ""):
            new_category = OrganisationCategory.query.filter_by(code=target_cat_code).first()
            if new_category:
                type_record.category_code = new_category.code
                new_category.updated_at = datetime.now(timezone.utc)

        type_record.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        # Audit trail
        _log_attempt(
            entity_type="organisation_type_catalogue",
            entity_id=str(type_record.id),
            action="type_edit",
            user_id=current_user.id,
            risk_score=2,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
            correlation_id=current_user.correlation_id
            if hasattr(current_user, "correlation_id")
            else None,
        )

        flash(f"Organisation type '{label}' updated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error editing type: {e}")
        flash("Error updating type. Please try again.", "danger")

    return redirect(url_for("admin.classification.type_list"))


@classification_bp.route("/types/<int:type_id>/deactivate", methods=["POST"])
@login_required
def type_deactivate(type_id):
    """Deactivate an organisation type (soft delete)."""
    if not _check_classification_permission():
        flash("Super admin or owner access required.", "danger")
        return redirect(url_for("admin.dashboard"))

    type_record = OrganisationTypeCatalogue.query.get_or_404(type_id)

    # Check if type is used by any organisations
    used_by_orgs = (
        Organisation.query.filter(
            Organisation.organisation_type_code == type_record.code,
            Organisation.is_deleted == False,
        ).count()
    )

    if used_by_orgs > 0:
        flash(
            f"Type is used by {used_by_orgs} organisation(s). "
            "Cannot deactivate while organisations still use this type.",
            "danger",
        )
    else:
        type_record.is_active = False
        type_record.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        # Audit trail
        _log_attempt(
            entity_type="organisation_type_catalogue",
            entity_id=str(type_record.id),
            action="type_deactivate",
            user_id=current_user.id,
            risk_score=2,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
            correlation_id=current_user.correlation_id
            if hasattr(current_user, "correlation_id")
            else None,
        )

        flash(f"Organisation type '{type_record.label}' deactivated successfully.", "success")

    return redirect(url_for("admin.classification.type_list"))


@classification_bp.route("/types/<int:type_id>/activate", methods=["POST"])
@login_required
def type_activate(type_id):
    """Reactivate a previously deactivated type."""
    if not _check_classification_permission():
        flash("Super admin or owner access required.", "danger")
        return redirect(url_for("admin.dashboard"))

    type_record = OrganisationTypeCatalogue.query.get_or_404(type_id)

    type_record.is_active = True
    type_record.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    # Audit trail
    _log_attempt(
        entity_type="organisation_type_catalogue",
        entity_id=str(type_record.id),
        action="type_activate",
        user_id=current_user.id,
        risk_score=2,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=current_user.correlation_id
        if hasattr(current_user, "correlation_id")
        else None,
    )

    flash(f"Organisation type '{type_record.label}' reactivated successfully.", "success")
    return redirect(url_for("admin.classification.type_list"))


# -----------------------------
# Dependency Check API
# -----------------------------

@classification_bp.route("/check-dependencies/<int:category_id>", methods=["GET"])
@login_required
def check_category_dependencies(category_id):
    """Check if a category has types that would be affected by deletion."""
    if not _check_classification_permission():
        return {"error": "Permission denied"}, 403

    category = OrganisationCategory.query.get_or_404(category_id)

    active_types = (
        OrganisationTypeCatalogue.query.filter_by(
            category_code=category.code, is_active=True
        ).count()
    )

    used_by_orgs = (
        Organisation.query.filter(
            Organisation.organisation_type_code == category.code,
            Organisation.is_deleted == False,
        ).count()
    )

    # Get the type codes
    type_codes = (
        OrganisationTypeCatalogue.query.filter_by(
            category_code=category.code, is_active=True
        )
        .with_entities(OrganisationTypeCatalogue.code)
        .all()
    )
    type_list = [t[0] for t in type_codes] if type_codes else []

    return {
        "category_id": category_id,
        "category_code": category.code,
        "category_label": category.label,
        "active_types": active_types,
        "types": type_list,
        "organisations_using": used_by_orgs,
        "can_safe_deactivate": active_types == 0 and used_by_orgs == 0,
    }


@classification_bp.route("/check-type-dependencies/<int:type_id>", methods=["GET"])
@login_required
def check_type_dependencies(type_id):
    """Check if an organisation type is in use."""
    if not _check_classification_permission():
        return {"error": "Permission denied"}, 403

    type_record = OrganisationTypeCatalogue.query.get_or_404(type_id)

    used_by_orgs = (
        Organisation.query.filter(
            Organisation.organisation_type_code == type_record.code,
            Organisation.is_deleted == False,
        ).count()
    )

    # Get category info
    category = None
    if type_record.category_code:
        category = (
            OrganisationCategory.query.filter_by(code=type_record.category_code).first()
        )

    category_info = None
    if category:
        category_info = {
            "code": category.code,
            "label": category.label,
        }

    return {
        "type_id": type_id,
        "type_code": type_record.code,
        "type_label": type_record.label,
        "organisations_using": used_by_orgs,
        "category": category_info,
        "can_safe_deactivate": used_by_orgs == 0,
    }


# =============================================================================
# INITIALISATION
# =============================================================================

def init_classification(app):
    """Register the classification blueprint."""
    app.register_blueprint(classification_bp)
    logger.info("✅ Registered classification blueprint")


__all__ = ["classification_bp", "init_classification"]