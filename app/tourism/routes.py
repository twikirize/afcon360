# app/tourism/routes.py

from flask import render_template, request
from flask_login import login_required, current_user
from app.tourism import tourism_bp
from app.auth.decorators import require_role
from app.audit.forensic_audit import ForensicAuditService
from app.auth.kyc_compliance import calculate_kyc_tier

# Attach routes to the tourism blueprint
@tourism_bp.route("/", endpoint="home")
@login_required
@require_role('fan', 'admin', 'owner')
def home():
    # Log access
    ForensicAuditService.log_attempt(
        entity_type="tourism",
        entity_id="home",
        action="view_home",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    return render_template("tourism_home.html")

@tourism_bp.route("/detail/<string:slug>", endpoint="detail")
@login_required
@require_role('fan', 'admin', 'owner')
def detail(slug):
    # Log access with forensic audit
    ForensicAuditService.log_attempt(
        entity_type="tourism",
        entity_id=slug,
        action="view_detail",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )

    # Check KYC tier if needed (for paid features)
    kyc_info = calculate_kyc_tier(current_user.id)

    return render_template('tourism_detail.html',
                         slug=slug,
                         kyc_info=kyc_info,
                         user_public_id=current_user.public_id)
