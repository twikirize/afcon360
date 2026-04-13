# app/accommodation/routes.py
from flask import render_template, request
from flask_login import login_required, current_user
from app.accommodation import accommodation_bp
from app.auth.decorators import require_role
from app.audit.forensic_audit import ForensicAuditService
from app.utils.id_guard import IDGuard

@accommodation_bp.route("/", endpoint="home")
@login_required
@require_role('fan', 'admin', 'owner')
def home():
    # Log access
    ForensicAuditService.log_attempt(
        entity_type="accommodation",
        entity_id="home",
        action="view_home",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    return render_template("accommodation_home.html")

@accommodation_bp.route("/detail/<string:public_id>", endpoint="detail")
@login_required
@require_role('fan', 'admin', 'owner')
def detail(public_id):
    # Validate public_id format
    IDGuard.check_public_id(public_id, "accommodation detail route")

    # Log access with forensic audit
    ForensicAuditService.log_attempt(
        entity_type="accommodation",
        entity_id=public_id,
        action="view_detail",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )

    # Get accommodation using public_id (implementation depends on your model)
    # For now, we'll pass the public_id to template
    return render_template('accommodation/detail.html', public_id=public_id)
