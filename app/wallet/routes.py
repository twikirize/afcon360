# app/wallet/routes.py
"""
Wallet routes - HTML templates only.
Optimized for lazy loading.
"""

from decimal import Decimal
from flask import Blueprint, render_template, flash, redirect, url_for, request, current_app
from flask_login import login_required, current_user
from datetime import datetime

from app.extensions import db
from app.wallet.middleware.kill_switch import require_wallet_enabled
from app.wallet.middleware.wallet_activation import require_wallet_activated

# Standardized blueprint name: wallet
wallet_bp = Blueprint("wallet", __name__)


# ============================================================================
# CORE PAGE ROUTES
# ============================================================================

@wallet_bp.route("/wallet", endpoint="wallet_home")
@require_wallet_enabled
def wallet_home():
    """Wallet home page - HTML."""
    return render_template("wallet_home.html")


@wallet_bp.route("/wallet/dashboard", endpoint="wallet_dashboard")
@require_wallet_activated
@require_wallet_enabled
def wallet_dashboard():
    """Wallet dashboard - HTML."""
    from app.wallet.services.wallet_service import WalletService
    from app.wallet.repositories.wallet_repository import WalletRepository
    from app.wallet.services.commission_service import CommissionService

    try:
        service = WalletService()
        wallet_repo = WalletRepository()
        commission_service = CommissionService()

        wallet = wallet_repo.get_or_create_by_user_id(current_user.id)
        balance = service.get_balance(current_user.id)
        commission = float(commission_service.get_agent_total(current_user.id))

        transactions_result = service.get_transaction_history(current_user.id, limit=5)
        recent_transactions = transactions_result.get("transactions", [])

        return render_template(
            "wallet_dashboard.html",
            wallet=wallet,
            balance=balance,
            commission=commission,
            recent_transactions=recent_transactions,
            title="My Wallet Dashboard"
        )
    except Exception as e:
        current_app.logger.error(f"Dashboard error: {e}")
        flash("Unable to load wallet dashboard", "danger")
        return redirect(url_for("index"))


# ============================================================================
# WALLET ACTIVATION
# ============================================================================

@wallet_bp.route("/wallet/activate", methods=["GET", "POST"], endpoint="activate_wallet")
@login_required
def activate_wallet():
    """Wallet activation page."""
    from app.wallet.repositories.wallet_repository import WalletRepository
    from app.wallet.models import Wallet as WalletModel
    from app.wallet.services.audit import wallet_audit
    import secrets

    repo = WalletRepository()
    existing_wallet = repo.get_by_user_id(current_user.id)

    if existing_wallet and existing_wallet.verified:
        flash("Your wallet is already activated.", "info")
        return redirect(url_for("wallet.wallet_dashboard"))

    if existing_wallet and not existing_wallet.verified:
        if request.method == "POST":
            existing_wallet.verified = True
            db.session.commit()
            wallet_audit.log_wallet_created(
                user_id=current_user.id,
                wallet_id=existing_wallet.id,
                wallet_ref=existing_wallet.wallet_ref or str(existing_wallet.id),
                home_currency=existing_wallet.home_currency,
                local_currency=existing_wallet.local_currency,
                created_by=current_user.id
            )
            flash("Your wallet has been activated successfully!", "success")
            return redirect(url_for("wallet.wallet_dashboard"))
        return render_template("wallet_activate.html", wallet=existing_wallet, action="verify")

    if request.method == "POST":
        home_currency = request.form.get("home_currency", "USD")
        local_currency = request.form.get("local_currency", "UGX")
        nationality = request.form.get("nationality", "UG")
        location = request.form.get("location", "UG")

        wallet = WalletModel(
            user_id=current_user.id,
            home_currency=home_currency,
            local_currency=local_currency,
            nationality=nationality,
            location=location,
            verified=True,
            balance_home=Decimal("0"),
            balance_local=Decimal("0"),
            wallet_ref=f"wal_{secrets.token_urlsafe(16)}"
        )
        db.session.add(wallet)
        db.session.flush()
        wallet_audit.log_wallet_created(
            user_id=current_user.id,
            wallet_id=wallet.id,
            wallet_ref=wallet.wallet_ref,
            home_currency=home_currency,
            local_currency=local_currency,
            created_by=current_user.id
        )
        db.session.commit()
        flash("Your wallet has been created and activated successfully!", "success")
        return redirect(url_for("wallet.wallet_dashboard"))

    return render_template("wallet_activate.html", action="create")


# ============================================================================
# FORM PAGES (GET) - These render the HTML forms
# ============================================================================

@wallet_bp.route("/wallet/deposit", endpoint="deposit_page")
@login_required
@require_wallet_enabled
def deposit_page():
    """Deposit page - HTML form."""
    return render_template("deposit.html", title="Deposit Funds")


@wallet_bp.route("/wallet/send", endpoint="send_page")
@login_required
@require_wallet_enabled
def send_page():
    """Send funds page - HTML form."""
    return render_template("send.html", title="Send Funds")


@wallet_bp.route("/wallet/withdraw", endpoint="withdraw_page")
@login_required
@require_wallet_enabled
def withdraw_page():
    """Withdraw page - HTML form."""
    return render_template("withdraw.html", title="Withdraw Funds")


# ============================================================================
# TRANSACTION HISTORY
# ============================================================================

@wallet_bp.route("/wallet/transactions", endpoint="wallet_transactions")
@login_required
@require_wallet_activated
@require_wallet_enabled
def wallet_transactions():
    """Transaction history page - HTML."""
    from app.wallet.services.wallet_service import WalletService

    try:
        service = WalletService()
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        transaction_type = request.args.get('type')

        result = service.get_transaction_history(
            user_id=current_user.id,
            limit=min(limit, 100),
            offset=offset,
            transaction_type=transaction_type
        )

        return render_template(
            "wallet_transactions.html",
            transactions=result.get("transactions", []),
            total=result.get("total", 0),
            limit=result.get("limit", 100),
            offset=result.get("offset", 0),
            has_more=result.get("has_more", False),
            title="Transaction History"
        )
    except Exception as e:
        current_app.logger.error(f"Transactions error: {e}")
        flash("Unable to load transactions", "danger")
        return redirect(url_for("wallet.wallet_dashboard"))


# ============================================================================
# AGENT COMMISSIONS
# ============================================================================

@wallet_bp.route("/wallet/commissions", endpoint="agent_commissions")
@login_required
@require_wallet_activated
@require_wallet_enabled
def agent_commissions():
    """Agent commission history page - HTML."""
    from app.wallet.services.commission_service import CommissionService

    try:
        commission_service = CommissionService()
        status = request.args.get('status')
        limit = request.args.get('limit', 50, type=int)

        history = commission_service.get_agent_commissions(
            agent_id=current_user.id,
            status=status,
            limit=min(limit, 100)
        )
        summary = commission_service.get_commission_summary(current_user.id)

        return render_template(
            "agent_commissions.html",
            agent_id=current_user.id,
            history=history,
            summary=summary,
            title="Commission History"
        )
    except Exception as e:
        current_app.logger.error(f"Agent commissions error: {e}")
        flash("Unable to load commission history", "danger")
        return redirect(url_for("wallet.wallet_dashboard"))


# ============================================================================
# AGENT PAYOUTS
# ============================================================================

@wallet_bp.route("/wallet/payouts", endpoint="agent_payout_history")
@login_required
@require_wallet_activated
@require_wallet_enabled
def agent_payout_history():
    """Agent payout history page - HTML."""
    from app.wallet.services.payout_service import PayoutService
    from app.wallet.services.commission_service import CommissionService

    try:
        payout_service = PayoutService()
        commission_service = CommissionService()

        status = request.args.get('status')
        limit = request.args.get('limit', 50, type=int)

        payouts = payout_service.list_requests(
            agent_id=current_user.id,
            status=status,
            limit=min(limit, 100)
        )
        history = commission_service.get_agent_commissions(
            agent_id=current_user.id,
            limit=50
        )
        summary = payout_service.get_agent_payout_summary(current_user.id)
        total_commission = float(commission_service.get_agent_total(current_user.id))

        return render_template(
            "agent_payout_history.html",
            agent_id=current_user.id,
            requests=payouts,
            history=history,
            summary=summary,
            total=total_commission,
            title="Payout History"
        )
    except Exception as e:
        current_app.logger.error(f"Agent payout history error: {e}")
        flash("Unable to load payout history", "danger")
        return redirect(url_for("wallet.wallet_dashboard"))


@wallet_bp.route("/wallet/payouts/request", endpoint="agent_payout_request_page")
@login_required
@require_wallet_activated
@require_wallet_enabled
def agent_payout_request_page():
    """Payout request page - HTML form."""
    from app.wallet.services.commission_service import CommissionService

    try:
        commission_service = CommissionService()

        total_commission = float(commission_service.get_agent_total(current_user.id))
        pending_total = float(commission_service.get_pending_total(current_user.id))
        history = commission_service.get_agent_commissions(
            agent_id=current_user.id,
            limit=20
        )

        return render_template(
            "agent_payout_request.html",
            agent_id=current_user.id,
            total=total_commission,
            pending_total=pending_total,
            history=history,
            title="Request Payout"
        )
    except Exception as e:
        current_app.logger.error(f"Payout request page error: {e}")
        flash("Unable to load payout request page", "danger")
        return redirect(url_for("wallet.agent_payout_history"))


# ============================================================================
# FORM HANDLERS (POST)
# ============================================================================

@wallet_bp.route("/wallet/deposit-form", methods=["POST"], endpoint="deposit_form")
@require_wallet_enabled
@require_wallet_activated
def deposit_form():
    """Process deposit from HTML form."""
    from app.wallet.services.wallet_service import WalletService
    from app.wallet.validators import parse_amount

    try:
        amount = parse_amount(request.form.get("amount"))
        if amount is None or amount <= 0:
            flash("Invalid amount.", "danger")
            return redirect(url_for("wallet.deposit_page"))

        currency = request.form.get("currency", "USD")
        service = WalletService()
        service.deposit(
            user_id=current_user.id,
            amount=amount,
            currency=currency,
            idempotency_key=f"form_{datetime.utcnow().timestamp()}"
        )
        flash(f"Deposit successful: {amount} {currency}", "success")
    except Exception as e:
        current_app.logger.error(f"Deposit form error: {e}")
        flash("Deposit failed.", "danger")

    return redirect(url_for("wallet.wallet_dashboard"))


@wallet_bp.route("/wallet/send-form", methods=["POST"], endpoint="send_funds")
@require_wallet_enabled
@require_wallet_activated
def send_funds():
    """Send funds from HTML form."""
    from app.wallet.services.wallet_service import WalletService
    from app.wallet.validators import parse_amount
    from app.wallet.exceptions import InsufficientBalanceError
    from app.identity.models.user import User

    try:
        receiver_id = request.form.get("receiver_id", "").strip()
        currency = request.form.get("currency", "USD").strip()
        amount = parse_amount(request.form.get("amount"))
        agent_fee = parse_amount(request.form.get("agent_fee"))

        if not receiver_id or amount is None or amount <= 0:
            flash("Invalid input.", "danger")
            return redirect(url_for("wallet.send_page"))

        receiver_user = User.query.filter_by(public_id=receiver_id).first() or \
                        User.query.filter_by(username=receiver_id).first()
        if not receiver_user:
            flash(f"User not found: {receiver_id}", "danger")
            return redirect(url_for("wallet.send_page"))

        service = WalletService()
        result = service.transfer(
            from_user_id=current_user.id,
            to_user_id=receiver_user.id,
            amount=amount,
            currency=currency,
            idempotency_key=f"form_{datetime.utcnow().timestamp()}",
            note=request.form.get("note"),
            platform_fee=agent_fee if agent_fee and agent_fee > 0 else None,
            fee_currency=currency
        )

        # Record commission if agent_fee was provided
        if agent_fee and agent_fee > 0:
            from app.wallet.services.commission_service import CommissionService
            commission_service = CommissionService()
            commission_service.record_commission(
                agent_id=current_user.id,
                amount=agent_fee,
                currency=currency,
                source_type="peer_transfer",
                source_id=result.get("transaction_id", ""),
                recipient_id=receiver_user.id,
                metadata={"transfer_note": request.form.get("note")}
            )

        flash(f"Transfer sent: {amount} {currency} to {receiver_id}", "success")
    except InsufficientBalanceError as e:
        flash(str(e), "danger")
    except Exception as e:
        current_app.logger.error(f"Send funds error: {e}")
        flash("Transfer failed.", "danger")

    return redirect(url_for("wallet.wallet_dashboard"))


@wallet_bp.route("/wallet/withdraw-form", methods=["POST"], endpoint="withdraw_funds")
@require_wallet_enabled
@require_wallet_activated
def withdraw_funds():
    """Process withdrawal from HTML form."""
    from app.wallet.services.wallet_service import WalletService
    from app.wallet.validators import parse_amount
    from app.wallet.exceptions import InsufficientBalanceError

    try:
        amount = parse_amount(request.form.get("amount"))
        if amount is None or amount <= 0:
            flash("Invalid amount.", "danger")
            return redirect(url_for("wallet.withdraw_page"))

        currency = request.form.get("currency", "UGX")
        method = request.form.get("method", "ATM")
        agent_id = request.form.get("agent_id")

        service = WalletService()
        service.withdraw(
            user_id=current_user.id,
            amount=amount,
            currency=currency,
            idempotency_key=f"form_{datetime.utcnow().timestamp()}",
            destination_type=method.lower(),
            destination_details={"agent_id": agent_id} if agent_id else {},
            payment_method=method.lower(),
            payment_provider="internal"
        )
        flash(f"Withdrawal successful: {amount} {currency}", "success")
    except InsufficientBalanceError as e:
        flash(str(e), "danger")
    except Exception as e:
        current_app.logger.error(f"Withdraw form error: {e}")
        flash("Withdrawal failed.", "danger")

    return redirect(url_for("wallet.wallet_dashboard"))


@wallet_bp.route("/wallet/payouts/request-form", methods=["POST"], endpoint="payout_request_form")
@login_required
@require_wallet_activated
@require_wallet_enabled
def payout_request_form():
    """Process payout request from HTML form."""
    from app.wallet.validators import parse_amount
    from app.wallet.services.payout_service import PayoutService

    try:
        amount = parse_amount(request.form.get("amount"))
        method = request.form.get("method", "bank")
        account = request.form.get("account", "")

        if amount is None or amount <= 0:
            flash("Invalid amount.", "danger")
            return redirect(url_for("wallet.agent_payout_request_page"))

        payout_service = PayoutService()

        payment_details = {}
        if method == "bank":
            payment_details = {"account_number": account}
        elif method == "mobile_money":
            payment_details = {"phone": account, "provider": "mtn"}

        payout_service.create_request(
            agent_id=current_user.id,
            amount=amount,
            currency="UGX",
            payment_method=method,
            payment_details=payment_details
        )

        flash(f"Payout request submitted for {amount} UGX", "success")

    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        current_app.logger.error(f"Payout request error: {e}")
        flash("Failed to create payout request. Please try again.", "danger")

    return redirect(url_for("wallet.agent_payout_history"))


# ============================================================================
# LEGAL PAGES
# ============================================================================

@wallet_bp.route("/wallet/terms", endpoint="terms")
@require_wallet_enabled
def terms():
    """Wallet terms and conditions page."""
    return render_template("wallet_terms.html")
