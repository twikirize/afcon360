"""
Wallet Admin Routes for AFCON360 - Production Ready.
All decorators imported from app.auth.decorators.
"""

from datetime import datetime, timezone
import logging
from flask import (
    render_template, redirect, url_for,
    current_app, request, flash, jsonify
)
from flask_login import login_required, current_user

from app.admin import admin_bp
from app.extensions import db
from app.auth.decorators import (
    admin_required,
    require_permission,
    require_role,
    require_fresh_user
)

# Setup logging
logger = logging.getLogger(__name__)


# -----------------------------
# Wallet Admin Dashboard
# -----------------------------
@admin_bp.route("/wallet-admin", endpoint="wallet_admin_dashboard")
@login_required
@require_role("wallet_admin")
def wallet_admin_dashboard():
    """Wallet Admin Dashboard with comprehensive financial management."""
    try:
        # Import wallet modules
        from app.wallet.models import Wallet, Transaction, PaymentMethod
        from app.wallet.services import WalletService
        
        # Get wallet statistics
        wallet_stats = WalletService.get_admin_dashboard_data()
        total_balance = wallet_stats.get('total_balance', 0)
        total_transactions = wallet_stats.get('total_transactions', 0)
        active_wallets = wallet_stats.get('active_wallets', 0)
        payment_methods = wallet_stats.get('payment_methods', 0)
        
        # Get recent transactions
        recent_transactions = Transaction.query.filter_by(
            is_deleted=False
        ).order_by(Transaction.created_at.desc()).limit(10).all()
        
        # Get pending transactions
        pending_transactions = Transaction.query.filter_by(
            status='pending',
            is_deleted=False
        ).order_by(Transaction.created_at.desc()).limit(5).all()
        
        return render_template(
            "admin/wallet_admin_dashboard.html",
            total_balance=total_balance,
            total_transactions=total_transactions,
            active_wallets=active_wallets,
            payment_methods=payment_methods,
            recent_transactions=recent_transactions,
            pending_transactions=pending_transactions,
        )
    except Exception as e:
        logger.error(f"Error loading wallet admin dashboard: {e}")
        flash("Error loading dashboard.", "danger")
        return redirect(url_for('admin.dashboard'))


# -----------------------------
# Transaction Management Routes
# -----------------------------
@admin_bp.route("/wallet-admin/transactions", endpoint="wallet_admin_transactions")
@login_required
@require_role("wallet_admin")
def wallet_admin_transactions():
    """List and manage all transactions."""
    try:
        from app.wallet.models import Transaction
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        transaction_type = request.args.get('type', 'all')
        
        query = Transaction.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        if transaction_type != 'all':
            query = query.filter_by(transaction_type=transaction_type)
        
        transactions = query.order_by(
            Transaction.created_at.desc()
        ).paginate(page=page, per_page=20, error_out=False)
        
        return render_template(
            "admin/wallet_admin/transactions.html",
            transactions=transactions,
            current_status=status,
            current_type=transaction_type
        )
    except Exception as e:
        logger.error(f"Error loading transactions: {e}")
        flash("Error loading transactions.", "danger")
        return redirect(url_for('admin.wallet_admin_dashboard'))


@admin_bp.route("/wallet-admin/transactions/<int:transaction_id>/approve", endpoint="wallet_admin_approve_transaction", methods=['POST'])
@login_required
@require_role("wallet_admin")
def wallet_admin_approve_transaction(transaction_id):
    """Approve pending transaction."""
    try:
        from app.wallet.models import Transaction
        from app.wallet.services import WalletService
        
        transaction = Transaction.query.get_or_404(transaction_id)
        
        if WalletService.approve_transaction(transaction_id, approved_by=current_user.id):
            flash(f"Transaction {transaction.reference} approved successfully.", "success")
        else:
            flash("Error approving transaction.", "danger")
        
        return redirect(url_for('admin.wallet_admin_transactions'))
    except Exception as e:
        logger.error(f"Error approving transaction: {e}")
        flash("Error approving transaction.", "danger")
        return redirect(url_for('admin.wallet_admin_transactions'))


@admin_bp.route("/wallet-admin/transactions/<int:transaction_id>/reject", endpoint="wallet_admin_reject_transaction", methods=['POST'])
@login_required
@require_role("wallet_admin")
def wallet_admin_reject_transaction(transaction_id):
    """Reject pending transaction."""
    try:
        from app.wallet.models import Transaction
        from app.wallet.services import WalletService
        
        transaction = Transaction.query.get_or_404(transaction_id)
        reason = request.form.get('reason', 'No reason provided')
        
        if WalletService.reject_transaction(transaction_id, reason, rejected_by=current_user.id):
            flash(f"Transaction {transaction.reference} rejected.", "warning")
        else:
            flash("Error rejecting transaction.", "danger")
        
        return redirect(url_for('admin.wallet_admin_transactions'))
    except Exception as e:
        logger.error(f"Error rejecting transaction: {e}")
        flash("Error rejecting transaction.", "danger")
        return redirect(url_for('admin.wallet_admin_transactions'))


# -----------------------------
# Payment Processing Routes
# -----------------------------
@admin_bp.route("/wallet-admin/payments", endpoint="wallet_admin_payments")
@login_required
@require_role("wallet_admin")
def wallet_admin_payments():
    """Manage payment methods and processing."""
    try:
        from app.wallet.models import PaymentMethod, PaymentGateway
        
        payment_methods = PaymentMethod.query.filter_by(
            is_deleted=False
        ).order_by(PaymentMethod.created_at.desc()).all()
        
        payment_gateways = PaymentGateway.query.filter_by(
            is_active=True
        ).all()
        
        return render_template(
            "admin/wallet_admin/payments.html",
            payment_methods=payment_methods,
            payment_gateways=payment_gateways
        )
    except Exception as e:
        logger.error(f"Error loading payments: {e}")
        flash("Error loading payments.", "danger")
        return redirect(url_for('admin.wallet_admin_dashboard'))


@admin_bp.route("/wallet-admin/payments/<int:payment_id>/verify", endpoint="wallet_admin_verify_payment", methods=['POST'])
@login_required
@require_role("wallet_admin")
def wallet_admin_verify_payment(payment_id):
    """Verify payment method."""
    try:
        from app.wallet.models import PaymentMethod
        from app.wallet.services import WalletService
        
        payment_method = PaymentMethod.query.get_or_404(payment_id)
        
        if WalletService.verify_payment_method(payment_id, verified_by=current_user.id):
            flash(f"Payment method {payment_method.type} verified successfully.", "success")
        else:
            flash("Error verifying payment method.", "danger")
        
        return redirect(url_for('admin.wallet_admin_payments'))
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        flash("Error verifying payment.", "danger")
        return redirect(url_for('admin.wallet_admin_payments'))


# -----------------------------
# Commission Management Routes
# -----------------------------
@admin_bp.route("/wallet-admin/commissions", endpoint="wallet_admin_commissions")
@login_required
@require_role("wallet_admin")
def wallet_admin_commissions():
    """Manage commission rates and payouts."""
    try:
        from app.wallet.models import Commission, AgentCommission
        
        commissions = Commission.query.filter_by(
            is_deleted=False
        ).order_by(Commission.created_at.desc()).all()
        
        pending_payouts = AgentCommission.query.filter_by(
            status='pending',
            is_deleted=False
        ).order_by(AgentCommission.created_at.desc()).limit(10).all()
        
        return render_template(
            "admin/wallet_admin/commissions.html",
            commissions=commissions,
            pending_payouts=pending_payouts
        )
    except Exception as e:
        logger.error(f"Error loading commissions: {e}")
        flash("Error loading commissions.", "danger")
        return redirect(url_for('admin.wallet_admin_dashboard'))


@admin_bp.route("/wallet-admin/commissions/create", endpoint="wallet_admin_create_commission", methods=['GET', 'POST'])
@login_required
@require_role("wallet_admin")
def wallet_admin_create_commission():
    """Create new commission rule."""
    try:
        if request.method == 'POST':
            from app.wallet.models import Commission
            from app.wallet.services import WalletService
            
            # Process commission creation
            commission_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'commission_type': request.form.get('commission_type'),
                'rate': request.form.get('rate', type=float),
                'min_amount': request.form.get('min_amount', type=float),
                'max_amount': request.form.get('max_amount', type=float),
                'service_type': request.form.get('service_type'),
                'created_by': current_user.id
            }
            
            commission = WalletService.create_commission(commission_data)
            if commission:
                flash("Commission rule created successfully.", "success")
                return redirect(url_for('admin.wallet_admin_commissions'))
            else:
                flash("Error creating commission rule.", "danger")
        
        return render_template("admin/wallet_admin/create_commission.html")
    except Exception as e:
        logger.error(f"Error creating commission: {e}")
        flash("Error creating commission.", "danger")
        return redirect(url_for('admin.wallet_admin_commissions'))


@admin_bp.route("/wallet-admin/commissions/<int:commission_id>/payout", endpoint="wallet_admin_payout_commission", methods=['POST'])
@login_required
@require_role("wallet_admin")
def wallet_admin_payout_commission(commission_id):
    """Process commission payout."""
    try:
        from app.wallet.models import AgentCommission
        from app.wallet.services import WalletService
        
        commission = AgentCommission.query.get_or_404(commission_id)
        
        if WalletService.process_commission_payout(commission_id, processed_by=current_user.id):
            flash(f"Commission payout of ${commission.amount} processed successfully.", "success")
        else:
            flash("Error processing commission payout.", "danger")
        
        return redirect(url_for('admin.wallet_admin_commissions'))
    except Exception as e:
        logger.error(f"Error processing payout: {e}")
        flash("Error processing payout.", "danger")
        return redirect(url_for('admin.wallet_admin_commissions'))


# -----------------------------
# Reconciliation Routes
# -----------------------------
@admin_bp.route("/wallet-admin/reconciliation", endpoint="wallet_admin_reconciliation")
@login_required
@require_role("wallet_admin")
def wallet_admin_reconciliation():
    """Balance accounts and reconcile transactions."""
    try:
        from app.wallet.services import WalletService
        
        # Get reconciliation data
        reconciliation_data = WalletService.get_reconciliation_data()
        
        return render_template(
            "admin/wallet_admin/reconciliation.html",
            reconciliation_data=reconciliation_data
        )
    except Exception as e:
        logger.error(f"Error loading reconciliation: {e}")
        flash("Error loading reconciliation.", "danger")
        return redirect(url_for('admin.wallet_admin_dashboard'))


@admin_bp.route("/wallet-admin/reconciliation/process", endpoint="wallet_admin_process_reconciliation", methods=['POST'])
@login_required
@require_role("wallet_admin")
@require_fresh_user
def wallet_admin_process_reconciliation():
    """Process account reconciliation."""
    try:
        from app.wallet.services import WalletService
        
        reconciliation_date = request.form.get('reconciliation_date')
        
        if WalletService.process_reconciliation(reconciliation_date, processed_by=current_user.id):
            flash(f"Reconciliation for {reconciliation_date} processed successfully.", "success")
        else:
            flash("Error processing reconciliation.", "danger")
        
        return redirect(url_for('admin.wallet_admin_reconciliation'))
    except Exception as e:
        logger.error(f"Error processing reconciliation: {e}")
        flash("Error processing reconciliation.", "danger")
        return redirect(url_for('admin.wallet_admin_reconciliation'))


# -----------------------------
# Payment Gateway Management
# -----------------------------
@admin_bp.route("/wallet-admin/gateways", endpoint="wallet_admin_gateways")
@login_required
@require_role("wallet_admin")
def wallet_admin_gateways():
    """Manage payment gateway integrations."""
    try:
        from app.wallet.models import PaymentGateway
        
        gateways = PaymentGateway.query.order_by(
            PaymentGateway.created_at.desc()
        ).all()
        
        return render_template(
            "admin/wallet_admin/gateways.html",
            gateways=gateways
        )
    except Exception as e:
        logger.error(f"Error loading gateways: {e}")
        flash("Error loading gateways.", "danger")
        return redirect(url_for('admin.wallet_admin_dashboard'))


@admin_bp.route("/wallet-admin/gateways/<int:gateway_id>/toggle", endpoint="wallet_admin_toggle_gateway", methods=['POST'])
@login_required
@require_role("wallet_admin")
def wallet_admin_toggle_gateway(gateway_id):
    """Toggle payment gateway status."""
    try:
        from app.wallet.models import PaymentGateway
        from app.wallet.services import WalletService
        
        gateway = PaymentGateway.query.get_or_404(gateway_id)
        
        new_status = not gateway.is_active
        if WalletService.toggle_gateway(gateway_id, new_status, toggled_by=current_user.id):
            status_text = "activated" if new_status else "deactivated"
            flash(f"Payment gateway {gateway.name} {status_text} successfully.", "success")
        else:
            flash("Error toggling gateway.", "danger")
        
        return redirect(url_for('admin.wallet_admin_gateways'))
    except Exception as e:
        logger.error(f"Error toggling gateway: {e}")
        flash("Error toggling gateway.", "danger")
        return redirect(url_for('admin.wallet_admin_gateways'))


# -----------------------------
# Analytics and Settings
# -----------------------------
@admin_bp.route("/wallet-admin/analytics", endpoint="wallet_admin_analytics")
@login_required
@require_role("wallet_admin")
def wallet_admin_analytics():
    """Wallet analytics and financial reports."""
    try:
        from app.wallet.services import WalletService
        
        # Get analytics data
        analytics = WalletService.get_analytics_data()
        
        return render_template(
            "admin/wallet_admin/analytics.html",
            analytics=analytics
        )
    except Exception as e:
        logger.error(f"Error loading analytics: {e}")
        flash("Error loading analytics.", "danger")
        return redirect(url_for('admin.wallet_admin_dashboard'))


@admin_bp.route("/wallet-admin/settings", endpoint="wallet_admin_settings")
@login_required
@require_role("wallet_admin")
def wallet_admin_settings():
    """Wallet admin settings."""
    try:
        return render_template("admin/wallet_admin/settings.html")
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        from flask_login import current_user
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="SETTINGS_LOAD_ERROR",
            error_message=str(e),
            context={"module": "wallet_admin", "template": "settings.html"}
        )
        flash("Unable to load settings. Please try again later.", "warning")
        return redirect(url_for('admin.wallet_admin_dashboard'))
