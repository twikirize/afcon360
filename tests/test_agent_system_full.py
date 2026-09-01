"""
Functional test for the AFCON360 agent system (Phase 1 + 2):
float ledger, statement, payout approval/settlement, reconciliation.
"""

import pytest
from decimal import Decimal
import uuid

from app import create_app
from app.extensions import db
from app.identity.models.user import User
from app.wallet.services.agent_float_service import AgentFloatService
from app.wallet.services.agent_statement_service import AgentStatementService
from app.wallet.services.agent_reconciliation_service import AgentReconciliationService
from app.wallet.services.payout_service import PayoutService
from app.wallet.repositories.commission_repository import CommissionRepository


@pytest.fixture(scope="module")
def app():
    """Create a Flask app for testing."""
    _app = create_app()
    with _app.app_context():
        yield _app


@pytest.fixture(scope="module")
def _make_agent(app):
    """Helper fixture to create a test agent user with float."""

    def _creator():
        with app.app_context():
            uniq = uuid.uuid4().hex[:8]
            u = User(email=f"agent_test_{uniq}@example.com", phone=f"+2567{uniq[:8]}", password_hash="dummy")
            u.is_agent = True
            u.agent_code = f"AGT-{uuid.uuid4().hex[:8].upper()}"
            db.session.add(u)
            db.session.commit()
            # Ensure float account exists
            AgentFloatService().get_or_create(u.id, "UGX")
            return u

    return _creator


@pytest.fixture(scope="module")
def _make_admin(app):
    """Helper fixture to create a test admin user."""

    def _creator():
        with app.app_context():
            from app.identity.models.roles_permission import get_or_create_role, Role
            from app.identity.models.user import User, UserRole

            uniq = uuid.uuid4().hex[:8]
            role = Role.query.filter_by(name="super_admin").first()
            if not role:
                role = get_or_create_role("super_admin", level=3)
            u = User(
                email=f"admin_test_{uniq}@example.com",
                username=f"admin_{uniq}",
                is_verified=True,
                is_active=True,
                password_hash="dummy",
            )
            db.session.add(u)
            db.session.flush()
            db.session.add(UserRole(user_id=u.id, role_id=role.id))
            db.session.commit()
            return u

    return _creator


def test_agent_payout_request_approve_pay_overlimit(app, _make_agent, _make_admin):
    """
    Restores the recovered payout coverage:
    request_for_agent -> approve -> pay, and over-limit payout rejection.
    """
    with app.app_context():
        # Re-attach detached fixture objects into the current session so
        # attribute accesses (e.g. .id) stay bound for payout service calls.
        agent = db.session.merge(_make_agent())
        admin = db.session.merge(_make_admin())

        # Give the agent earned, unpaid commission so a payout is allowed.
        # source_id is an ID-guarded string column, so it must be a UUID.
        CommissionRepository(db.session).create(
            commission_ref=f"cm_{uuid.uuid4().hex[:12]}",
            agent_id=agent.id,
            amount=Decimal("50"),
            currency="UGX",
            source_type="cashback",
            source_id=str(uuid.uuid4()),
            status="pending",
        )

        payout_svc = PayoutService()

        # Over-limit payout should be rejected (exceeds available commission).
        over = payout_svc.request_for_agent(
            agent_id=agent.id,
            amount=Decimal("999"),
            currency="UGX",
            payment_method="bank",
            payment_details={"account_ref": "ACC123"},
        )
        assert over.get("success") is False

        # Request, approve, and pay a valid payout.
        req = payout_svc.request_for_agent(
            agent_id=agent.id,
            amount=Decimal("50"),
            currency="UGX",
            payment_method="bank",
            payment_details={"account_ref": "ACC123"},
        )
        assert req.get("success") is True
        ref = req["request_ref"]

        approved = payout_svc.approve(ref, admin)
        assert approved.get("success") is True

        paid = payout_svc.pay(ref, admin)
        assert paid.get("success") is True
        assert paid["status"] == "paid"

        db.session.rollback()


def test_agent_float_ledger_statement_payout_reconciliation(app, _make_agent):
    """
    End‑to‑end functional test covering:
    - agent float credit (cash‑in)
    - float debit (cash‑out)
    - statement generation
    - reconciliation run
    """
    with app.app_context():
        u = _make_agent()

        # ----- Float credit (simulate cash‑in) -----
        svc = AgentFloatService()
        svc.credit(u.id, "UGX", Decimal("100"), entry_type="cash_in", reference="ref-1", created_by=u.id)

        # ----- Float debit (simulate cash‑out) -----
        svc.debit(u.id, "UGX", Decimal("30"), entry_type="cash_out", reference="ref-2", created_by=u.id)

        # ----- Statement generation -----
        stmt_svc = AgentStatementService()
        stmt = stmt_svc.generate(u.id, "UGX")
        assert Decimal(stmt["closing_balance"]) == Decimal("70")
        # commission and payout may be zero in this minimal scenario
        assert Decimal(stmt["commission_earned"]) == Decimal("0")
        assert Decimal(stmt["payout_paid"]) == Decimal("0")
        assert len(stmt["line_items"]) == 2

        # ----- Reconciliation -----
        recon_svc = AgentReconciliationService()
        recon = recon_svc.reconcile_all()
        assert recon["success"] is True
        assert recon["summary"]["agents_checked"] >= 1
        assert recon["summary"]["issues_found"] == 0

        # Clean up session
        db.session.rollback()