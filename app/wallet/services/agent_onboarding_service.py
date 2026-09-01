"""
app/wallet/services/agent_onboarding_service.py

Drives the agent onboarding lifecycle and the sequential (bank-style) approval
chain:

    submitted --(wallet_admin)--> wallet_approved
             --(compliance_officer)--> compliance_approved
             --(super_admin | owner)--> active

Each decision is recorded immutably in AgentOnboardingApproval.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional

from flask import current_app
from app.extensions import db

AGENCY_SUPPORTED_COUNTRIES = ["UG", "KE", "TZ", "RW"]
AGENCY_COUNTRY_SETTINGS_KEY = "agency_country_settings"


def agency_country_settings() -> Dict[str, bool]:
    from app.models.system_config import SystemConfig

    try:
        return SystemConfig.get(AGENCY_COUNTRY_SETTINGS_KEY) or {}
    except Exception:
        return {}


def is_agency_available_for_country(country_code: Optional[str] = None) -> bool:
    from app.wallet.models.config import WalletSystemConfig

    if not bool(WalletSystemConfig.get_config().agents_enabled):
        return False

    if not country_code:
        return True

    settings = agency_country_settings()
    key = country_code.upper()
    if key in settings:
        return bool(settings[key])
    return True


STAGE_CONFIG = {
    "wallet_admin": {"expects": "submitted", "next": "wallet_approved", "stage": "wallet_review"},
    "compliance_officer": {"expects": "wallet_approved", "next": "compliance_approved", "stage": "compliance_review"},
    "super_admin": {"expects": "compliance_approved", "next": "active", "stage": "final_approval"},
    "owner": {"expects": "compliance_approved", "next": "active", "stage": "final_approval"},
}


class AgentOnboardingService:
    def __init__(self, session=None):
        self.db = session or db.session

    def submit(
        self,
        user: Any,
        agent_type: str,
        applicant_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        if agent_type not in ("individual", "organisation"):
            return {"success": False, "error": "agent_type must be 'individual' or 'organisation'."}

        reference = f"AGT-ONB-{uuid.uuid4().hex[:12].upper()}"

        from app.wallet.models.agent_onboarding import AgentOnboarding

        onboarding = AgentOnboarding(
            user_id=int(user.id),
            agent_type=agent_type,
            reference=reference,
            status="submitted",
            current_stage="wallet_review",
            applicant_data=applicant_data or {},
        )

        self.db.add(onboarding)
        self.db.commit()

        return {"success": True, "reference": reference, "onboarding_id": onboarding.id}

    def get(self, onboarding_id: int) -> Any:
        from app.wallet.models.agent_onboarding import AgentOnboarding

        return self.db.get(AgentOnboarding, onboarding_id)

    def list_by_status(self, status: str) -> list:
        from app.wallet.models.agent_onboarding import AgentOnboarding

        return (
            self.db.query(AgentOnboarding)
            .filter(AgentOnboarding.status == status, AgentOnboarding.is_deleted == False)
            .order_by(AgentOnboarding.created_at.desc())
            .all()
        )

    def list_for_reviewer(self, role: str) -> list:
        cfg = STAGE_CONFIG.get(role)
        if not cfg:
            return []
        return self.list_by_status(cfg["expects"])

    def review(
        self,
        onboarding_id: int,
        approver_user: Any,
        approver_role: str,
        decision: str,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        cfg = STAGE_CONFIG.get(approver_role)
        if not cfg:
            return {
                "success": False,
                "error": f"Role '{approver_role}' is not part of the agent approval chain.",
            }

        from app.wallet.models.agent_onboarding import AgentOnboarding, AgentOnboardingApproval

        onboarding = self.db.get(AgentOnboarding, onboarding_id)
        if not onboarding or onboarding.is_deleted:
            return {"success": False, "error": "Onboarding not found."}

        if onboarding.status != cfg["expects"]:
            return {
                "success": False,
                "error": f"Cannot act: application is in status '{onboarding.status}', expected '{cfg['expects']}'.",
            }

        approval = AgentOnboardingApproval(
            onboarding_id=onboarding.id,
            stage=cfg["stage"],
            approver_user_id=int(approver_user.id),
            approver_role=approver_role,
            decision=decision,
            comment=comment or "",
        )

        self.db.add(approval)

        if decision == "reject":
            onboarding.status = "rejected"
            onboarding.current_stage = "rejected"
            onboarding.rejected_at = datetime.now(timezone.utc)
            onboarding.rejection_reason = comment or "Rejected during review."
            self.db.commit()
            return {"success": True, "status": "rejected"}

        next_status = cfg["next"]
        onboarding.status = next_status

        if next_status == "wallet_approved":
            onboarding.reviewed_by_wallet_admin_at = datetime.now(timezone.utc)
            onboarding.current_stage = "compliance_review"
        elif next_status == "compliance_approved":
            onboarding.reviewed_by_compliance_at = datetime.now(timezone.utc)
            onboarding.current_stage = "final_approval"
        elif next_status == "active":
            result = self._activate(onboarding)
            if not result.get("success"):
                self.db.rollback()
                return result

        self.db.commit()
        return {"success": True, "status": onboarding.status}

    def _activate(self, onboarding: Any) -> Dict[str, Any]:
        from app.identity.models.user import User
        from app.wallet.services.agent_float_service import AgentFloatService

        user = self.db.get(User, int(onboarding.user_id))
        if not user:
            return {"success": False, "error": "Applicant user not found."}

        user.is_agent = True

        if not user.agent_code:
            for _ in range(5):
                code = f"AGT-{uuid.uuid4().hex[:8].upper()}"
                exists = self.db.query(User).filter(User.agent_code == code).first()
                if not exists:
                    user.agent_code = code
                    break

        fs = AgentFloatService(self.db)
        fs.get_or_create(int(user.id), "UGX")

        onboarding.activated_at = datetime.now(timezone.utc)
        onboarding.current_stage = "active"

        current_app.logger.info(
            f"Agent activated: user={user.id} code={user.agent_code} ref={onboarding.reference}"
        )

        return {"success": True}