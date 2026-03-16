# app/identity/utils/compliance_checker.py

from datetime import datetime
from app.identity.models.compliance_settings import ComplianceSettings
from app.identity.models.compliance_audit_log import ComplianceAuditLog
from app.extensions import db

class ComplianceChecker:
    """
    Central compliance checker class.
    Can be used for Organisations (KYB) or Individuals (KYC).
    Handles compliance enforcement and logs every decision.
    """

    def __init__(self, entity, actor_id=None):
        """
        entity: Organisation or Individual instance
        actor_id: ID of the user/admin/system making the compliance check
        """
        self.entity = entity
        self.actor_id = actor_id

    def _log_decision(self, requirement_key, decision):
        """
        Internal helper: record every compliance decision in ComplianceAuditLog.
        """
        log = ComplianceAuditLog(
            entity_id=self.entity.id,
            entity_type=self.entity.__class__.__name__.lower(),  # "organisation" or "user"
            operation=requirement_key,
            decision=decision,
            requirement_key=requirement_key,
            compliance_level=self.compliance_level(),
            risk_tier=self.risk_tier(),
            context={"status": self.status_light()},
            decided_by=self.actor_id,
        )
        db.session.add(log)
        db.session.commit()

    def can_perform_operation(self, requirement_key):
        """
        Check if entity can perform a given operation
        based on compliance settings and verification state.
        Logs the decision automatically.
        """
        setting = ComplianceSettings.query.filter_by(requirement=requirement_key).first()
        if not setting or not setting.is_enabled:
            decision = "allowed"
            self._log_decision(requirement_key, decision)
            return True

        if setting.enforcement_level == "mandatory":
            result = self.entity.is_fully_verified()
        elif setting.enforcement_level == "conditional":
            result = self.entity.has_partial_verification()
        else:
            result = True

        decision = "allowed" if result else "blocked"
        self._log_decision(requirement_key, decision)
        return result

    def risk_tier(self):
        """
        Return a categorical risk tier: low, medium, high.
        Based on verification status and expired docs/licenses.
        """
        if self.entity.is_fully_verified() and not getattr(self.entity, "has_expired_license", False) and not getattr(self.entity, "has_expired_document", False):
            return "low"
        elif self.entity.has_partial_verification() or getattr(self.entity, "has_expired_document", False):
            return "medium"
        else:
            return "high"

    def compliance_level(self):
        """
        Return a progressive compliance level (0–3).
        Level 0: Registered only
        Level 1: Partial verification
        Level 2: Fully verified
        Level 3: Fully verified + controllers + licenses
        """
        if self.entity.is_fully_verified() and getattr(self.entity, "controllers", None) and getattr(self.entity, "licenses", None):
            return 3
        elif self.entity.is_fully_verified():
            return 2
        elif self.entity.has_partial_verification():
            return 1
        else:
            return 0

    def capabilities(self):
        """
        Return a dictionary of capability flags for operations.
        Used to gate features dynamically.
        """
        return {
            "can_list_offers": True,  # always allowed
            "can_receive_payments": self.entity.has_partial_verification(),
            "can_withdraw_funds": self.entity.is_fully_verified(),
        }

    def status_light(self):
        """
        Return a traffic light style compliance status (green/amber/red).
        Useful for dashboards and admin views.
        """
        if self.entity.is_fully_verified():
            return "green"
        elif self.entity.has_partial_verification():
            return "amber"
        else:
            return "red"
