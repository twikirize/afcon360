"""
Owner / Super-Admin / Wallet-Admin agent management console.

Provides a directory of all agents and lifecycle actions (suspend, reactivate,
expel, fine) with forensic audit. Gated for wallet_admin, super_admin and owner.
"""

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
from app.auth.decorators import require_role
from app.wallet.services.agent_management_service import (
    list_agents,
    get_agent_status,
    suspend_agent,
    reactivate_agent,
    expel_agent,
    fine_agent,
    ACTIVE,
    SUSPENDED,
    EXPELLED,
)

agent_mgmt_bp = Blueprint("agent_mgmt", __name__, url_prefix="/admin/agents")


@agent_mgmt_bp.route("/", methods=["GET"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_directory():
    status = request.args.get("status")
    agents = list_agents(status=status)
    return render_template(
        "admin/agent_mgmt/index.html",
        agents=agents,
        active_tab=status,
        statuses={
            ACTIVE: "Active",
            SUSPENDED: "Suspended",
            EXPELLED: "Expelled",
        },
        current_filter=status,
    )


@agent_mgmt_bp.route("/<int:user_id>", methods=["GET"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_detail(user_id):
    from app.wallet.services.agent_management_service import get_agent_record, _agent_display

    info = _agent_display(user_id)
    if not info.get("found"):
        flash("Agent not found.", "danger")
        return redirect(url_for("agent_mgmt.agent_directory"))

    rec = get_agent_record(user_id)
    info["status"] = rec.get("status", ACTIVE)
    info["suspended_at"] = rec.get("suspended_at")
    info["suspended_reason"] = rec.get("suspended_reason")
    info["expelled_at"] = rec.get("expelled_at")
    info["expelled_reason"] = rec.get("expelled_reason")
    info["fines"] = rec.get("fines", [])

    return render_template(
        "admin/agent_mgmt/detail.html",
        agent=info,
        statuses={
            ACTIVE: "Active",
            SUSPENDED: "Suspended",
            EXPELLED: "Expelled",
        },
    )


@agent_mgmt_bp.route("/<int:user_id>/suspend", methods=["POST"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_suspend(user_id):
    reason = request.form.get("reason", "").strip() or "Suspended by administrator"
    result = suspend_agent(current_user, user_id, reason)
    if result.get("success"):
        flash("Agent suspended.", "success")
    else:
        flash(result.get("error", "Could not suspend agent."), "danger")
    return redirect(url_for("agent_mgmt.agent_detail", user_id=user_id))


@agent_mgmt_bp.route("/<int:user_id>/reactivate", methods=["POST"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_reactivate(user_id):
    reason = request.form.get("reason", "").strip() or "Reactivated by administrator"
    result = reactivate_agent(current_user, user_id, reason)
    if result.get("success"):
        flash("Agent reactivated.", "success")
    else:
        flash(result.get("error", "Could not reactivate agent."), "danger")
    return redirect(url_for("agent_mgmt.agent_detail", user_id=user_id))


@agent_mgmt_bp.route("/<int:user_id>/expel", methods=["POST"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_expel(user_id):
    reason = request.form.get("reason", "").strip() or "Expelled by administrator"
    result = expel_agent(current_user, user_id, reason)
    if result.get("success"):
        recalled = result.get("recalled", {})
        flash(f"Agent expelled. Float recalled: {recalled}.", "success")
        return redirect(url_for("agent_mgmt.agent_directory"))
    else:
        flash(result.get("error", "Could not expel agent."), "danger")
    return redirect(url_for("agent_mgmt.agent_detail", user_id=user_id))


@agent_mgmt_bp.route("/<int:user_id>/fine", methods=["POST"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_fine(user_id):
    amount = request.form.get("amount", "").strip()
    currency = request.form.get("currency", "").strip().upper() or "UGX"
    reason = request.form.get("reason", "").strip() or "Fine by administrator"

    result = fine_agent(current_user, user_id, amount, currency, reason)
    if result.get("success"):
        flash(f"Fine of {result['amount']} {result['currency']} applied.", "success")
    else:
        flash(result.get("error", "Could not apply fine."), "danger")
    return redirect(url_for("agent_mgmt.agent_detail", user_id=user_id))


# =============================================================================
# RECONSTRUCTED ADMIN FLOWS
# Onboarding review, payout admin, and reconciliation. These call the recovered
# services (AgentOnboardingService / PayoutService / AgentReconciliationService)
# with their exact signatures. Financial POSTs are CSRF-guarded and role-gated.
# =============================================================================

ONBOARDING_APPROVAL_ROLES = ("wallet_admin", "compliance_officer", "super_admin", "owner")


def _active_approver_role():
    """Return the current user's active approval-chain role, or None."""
    try:
        from app.auth.helpers import get_active_role_name
        active = get_active_role_name() or ""
        if active in ONBOARDING_APPROVAL_ROLES:
            return active
    except Exception:
        pass
    for role in ONBOARDING_APPROVAL_ROLES:
        if role in current_user.role_names:
            return role
    return None


@agent_mgmt_bp.route("/applications", methods=["GET"])
@login_required
@require_role("wallet_admin", "compliance_officer", "super_admin", "owner")
def agent_admin_applications():
    """Admin list of agent onboarding applications for the reviewer's stage."""
    from app.wallet.services.agent_onboarding_service import AgentOnboardingService, STAGE_CONFIG

    role = _active_approver_role() or ""
    if role not in STAGE_CONFIG:
        flash("Your role is not part of the agent approval chain.", "warning")
        return redirect(url_for("agent_mgmt.agent_directory"))

    applications = AgentOnboardingService().list_for_reviewer(role)
    return render_template(
        "admin/agent_mgmt/onboarding_list.html",
        applications=applications,
        reviewer_role=role,
        expects=STAGE_CONFIG[role]["expects"],
    )


@agent_mgmt_bp.route("/applications/<int:onboarding_id>", methods=["GET"])
@login_required
@require_role("wallet_admin", "compliance_officer", "super_admin", "owner")
def agent_admin_application_detail(onboarding_id):
    """Admin detail + review form for a single onboarding application."""
    from app.wallet.services.agent_onboarding_service import AgentOnboardingService, STAGE_CONFIG

    role = _active_approver_role() or ""
    onboarding = AgentOnboardingService().get(onboarding_id)
    if not onboarding or onboarding.is_deleted:
        flash("Application not found.", "danger")
        return redirect(url_for("agent_mgmt.agent_admin_applications"))

    return render_template(
        "admin/agent_mgmt/onboarding_detail.html",
        application=onboarding,
        reviewer_role=role,
        reviewable=(role in STAGE_CONFIG and onboarding.status == STAGE_CONFIG[role]["expects"]),
    )


@agent_mgmt_bp.route("/applications/<int:onboarding_id>/review", methods=["POST"])
@login_required
@require_role("wallet_admin", "compliance_officer", "super_admin", "owner")
def agent_admin_application_review(onboarding_id):
    """Approve or reject an onboarding application via AgentOnboardingService.review."""
    from app.wallet.services.agent_onboarding_service import AgentOnboardingService

    role = _active_approver_role()
    if not role:
        flash("Your role is not part of the agent approval chain.", "warning")
        return redirect(url_for("agent_mgmt.agent_admin_applications"))

    decision = request.form.get("decision") or ""
    comment = (request.form.get("comment") or "").strip()
    if decision not in ("approve", "reject"):
        flash("Invalid review decision.", "danger")
        return redirect(url_for("agent_mgmt.agent_admin_application_detail", onboarding_id=onboarding_id))

    result = AgentOnboardingService().review(onboarding_id, current_user, role, decision, comment)
    if result.get("success"):
        flash(f"Application {decision}d.", "success")
    else:
        flash(result.get("error", "Could not review application."), "danger")
    return redirect(url_for("agent_mgmt.agent_admin_applications"))


@agent_mgmt_bp.route("/payouts", methods=["GET"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_admin_payouts():
    """Admin view of all agent payout requests (read-only presentation)."""
    from app.wallet.models.payout import PayoutRequest
    from app.wallet.services.payout_service import PayoutService

    status = request.args.get("status")
    query = PayoutRequest.query.filter(PayoutRequest.is_deleted == False)
    if status:
        query = query.filter(PayoutRequest.status == status)
    payouts = query.order_by(PayoutRequest.created_at.desc()).limit(200).all()

    service = PayoutService()
    statuses = []
    for pr in payouts:
        try:
            summary = service.get_agent_payout_summary(pr.agent_id)
        except Exception:
            summary = {}
        statuses.append({
            "request_ref": pr.request_ref,
            "agent_id": pr.agent_id,
            "amount": pr.amount,
            "currency": pr.currency,
            "payment_method": pr.payment_method,
            "status": pr.status,
            "created_at": pr.created_at,
            "approved_at": pr.approved_at,
            "rejection_reason": pr.rejection_reason,
            "agent_summary": summary,
        })

    return render_template(
        "admin/agent_mgmt/payouts.html",
        payouts=statuses,
        current_filter=status,
    )


@agent_mgmt_bp.route("/payouts/<request_ref>/approve", methods=["POST"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_admin_payout_approve(request_ref):
    """Approve a pending payout request via PayoutService.approve."""
    from app.wallet.services.payout_service import PayoutService
    result = PayoutService().approve(request_ref, current_user)
    if result.get("success"):
        flash(f"Payout {request_ref} approved.", "success")
    else:
        flash(result.get("error", "Could not approve payout."), "danger")
    return redirect(url_for("agent_mgmt.agent_admin_payouts"))


@agent_mgmt_bp.route("/payouts/<request_ref>/reject", methods=["POST"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_admin_payout_reject(request_ref):
    """Reject a pending payout request via PayoutService.reject."""
    from app.wallet.services.payout_service import PayoutService
    reason = (request.form.get("reason") or "").strip() or "Rejected by administrator"
    result = PayoutService().reject(request_ref, current_user, reason)
    if result.get("success"):
        flash(f"Payout {request_ref} rejected.", "success")
    else:
        flash(result.get("error", "Could not reject payout."), "danger")
    return redirect(url_for("agent_mgmt.agent_admin_payouts"))


@agent_mgmt_bp.route("/reconciliations", methods=["GET"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_admin_reconciliation():
    """Admin reconciliation dashboard (read-only; run via POST)."""
    return render_template("admin/agent_mgmt/reconciliation.html", last_run=None)


@agent_mgmt_bp.route("/reconciliations/run", methods=["POST"])
@login_required
@require_role("wallet_admin", "super_admin", "owner")
def agent_admin_reconciliation_run():
    """Trigger a full agent reconciliation via AgentReconciliationService."""
    from app.wallet.services.agent_reconciliation_service import AgentReconciliationService
    try:
        result = AgentReconciliationService().reconcile_all()
    except Exception as e:
        current_app.logger.exception("Agent reconciliation run failed")
        result = {"summary": {"issues_found": -1}, "issues": [{"issue_type": "error", "details": str(e)}]}
    return render_template(
        "admin/agent_mgmt/reconciliation.html",
        last_run=result,
    )


def init_agent_mgmt(app):
    app.register_blueprint(agent_mgmt_bp)


__all__ = ["agent_mgmt_bp", "init_agent_mgmt"]