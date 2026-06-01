"""
Wallet routes for the wallet system.
Complete implementation with all endpoints for user wallet operations.
"""

from datetime import datetime
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from app.extensions import db
from app.utils.transactions import db_transaction
from app.wallet.models.ledger import AccountModel, LedgerEntryModel
from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.currency_service import CurrencyService
from app.wallet.exceptions import InsufficientBalanceError, WalletNotFoundError, LimitExceededError
from app.wallet.middleware.wallet_check import (
    require_wallet_for_feature,
    require_deposit_access,
    require_send_access,
    require_withdraw_access,
    require_payout_access
)
from app.wallet.services.wallet_status_service import WalletFeature, WalletStatusService
from app.auth.decorators import require_fresh_user
from app.services.analytics import AnalyticsService
from uuid import UUID

from uuid import uuid4

wallet_bp = Blueprint('wallet', __name__, url_prefix='/wallet')


def calculate_transaction_usage(user_id):
    """Calculate transaction usage for a user using correct model fields."""
    from app.wallet.models.transaction import TransactionModel
    return TransactionModel.query.filter(
        db.or_(
            TransactionModel.user_id == user_id,
            TransactionModel.recipient_user_id == user_id
        )
    ).count()


def get_account(user_id, currency='UGX', owner_type=None):
    """Helper to get existing account (does NOT create one).
    
    Args:
        user_id: Can be either internal BIGINT id or public_id (UUID string)
        currency: Currency code (default: UGX) - ignored, kept for signature compatibility
        owner_type: AccountOwnerType (USER or ORGANISATION). If None, defaults to USER.
    """
    from app.identity.models.user import User
    from app.wallet.models.ledger import AccountOwnerType
    
    if owner_type is None:
        owner_type = AccountOwnerType.USER
    
    if isinstance(user_id, str):
        if owner_type == AccountOwnerType.USER:
            user = User.query.filter_by(public_id=user_id).first()
            if user:
                internal_id = user.id
            else:
                return None
        else:
            # For organisations, user_id is expected to be internal BIGINT
            internal_id = int(user_id) if user_id.isdigit() else None
            if not internal_id:
                return None
    else:
        internal_id = user_id
    
    account = AccountModel.query.filter_by(
        user_id=internal_id,
        owner_type=owner_type
    ).first()
    return account


def get_or_create_account(user_id, currency='UGX'):
    """
    Get existing account OR create one if it doesn't exist.
    This is the main function for wallet access - creates wallet on first use.
    
    Args:
        user_id: Can be either internal BIGINT id or public_id (UUID string)
        currency: Currency code (default: UGX)
    
    Returns:
        Account object (existing or newly created)
    """
    from app.identity.models.user import User
    from app.wallet.models.ledger import AccountModel
    from app.extensions import db
    from uuid import uuid4
    from decimal import Decimal
    
    # Handle both internal BIGINT and external UUID (public_id)
    if isinstance(user_id, str):
        # It's a public_id (UUID string) - convert to internal
        user = User.query.filter_by(public_id=user_id).first()
        if not user:
            return None
        internal_id = user.id
    else:
        internal_id = user_id
    
    # Try to find existing account (one account per user - unique constraint)
    account = AccountModel.query.filter_by(user_id=internal_id).first()
    
    if not account:
        # Create new account (verified defaults to False in model)
        account = AccountModel(
            id=str(uuid4()),
            user_id=internal_id,
            currency=currency,
            is_frozen=False,
            frozen_reason=None,
            frozen_at=None,
            daily_volume=Decimal('0'),
            daily_volume_reset_at=None,
            monthly_volume=Decimal('0'),
            monthly_volume_reset_at=None
        )
        db.session.add(account)
        db.session.commit()
        
    return account


@wallet_bp.route("/activate", methods=["GET", "POST"], endpoint='wallet_activate')
@login_required
@require_fresh_user
def activate_wallet():
    """User explicitly opts in to wallet activation with terms acceptance."""
    from app.identity.models.user import User
    from app.wallet.models.ledger import AccountOwnerType

    db_user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not db_user:
        flash("User not found.", "danger")
        return redirect(url_for("fan.dashboard"))

    existing = AccountModel.query.filter_by(
        user_id=db_user.id,
        owner_type=AccountOwnerType.USER,
    ).first()

    if not existing:
        flash('You need to create a wallet first.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))

    if request.method == 'POST':
        from flask_wtf.csrf import validate_csrf
        csrf_token = request.form.get('csrf_token')
        if not csrf_token:
            flash('Security token missing. Please try again.', 'danger')
            return redirect(url_for('wallet.wallet_activate'))
        try:
            validate_csrf(csrf_token)
        except Exception:
            flash('Invalid security token. Please try again.', 'danger')
            return redirect(url_for('wallet.wallet_activate'))

        if existing.verified:
            flash('Your wallet is already activated.', 'info')
            return redirect(url_for('wallet.wallet_dashboard'))

        if not request.form.get('accept_terms'):
            flash('You must accept the terms to activate your wallet.', 'warning')
            return render_template('wallet/wallet_activate.html', action='verify', wallet=existing)

        with db_transaction('Wallet activation'):
            existing.verified = True
            existing.terms_accepted_at = datetime.utcnow()
            db.session.add(existing)

        flash('Your wallet has been activated!', 'success')
        return redirect(url_for('wallet.wallet_dashboard'))

    return render_template('wallet/wallet_activate.html', action='verify', wallet=existing)


# =============================================================================
# HOME / DASHBOARD ROUTES
# =============================================================================

@wallet_bp.route('/')
def home():
    """Wallet module entry point — intelligent traffic director."""
    if not current_user.is_authenticated:
        return render_template('wallet/wallet_home.html')

    try:
        wallet_status = WalletStatusService.get_wallet_status(current_user)
        if wallet_status is None or not wallet_status.exists:
            return redirect(url_for('wallet.wallet_dashboard'))

        if not wallet_status.is_activated:
            return redirect(url_for('wallet.wallet_activate'))

        return redirect(url_for('wallet.wallet_dashboard'))
    except Exception as e:
        current_app.logger.error(f"Wallet home routing error: {e}")
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/home')
def wallet_home():
    """Public wallet marketing page — accessible without login."""
    if current_user.is_authenticated:
        try:
            wallet_status = WalletStatusService.get_wallet_status(current_user)
            if wallet_status and wallet_status.is_activated:
                return redirect(url_for('wallet.wallet_dashboard'))
        except Exception:
            pass
    return render_template('wallet/wallet_home.html')


@wallet_bp.route('/dashboard')
@login_required
def wallet_dashboard():
    """Main wallet dashboard — the real landing page."""
    AnalyticsService.track_page_view('wallet')

    # Clear admin/module flash messages from previous page loads
    from flask import session
    if '_flashes' in session:
        session['_flashes'] = [(category, message) for category, message in session['_flashes'] if 'module' not in message.lower()]

    try:
        wallet_status = WalletStatusService.get_wallet_status(current_user)
        account = get_account(current_user.id)

        if not account:
            return render_template(
                'wallet/wallet_dashboard.html',
                account=None,
                balance=Decimal('0'),
                recent_transactions=[],
                commission=Decimal('0'),
                transaction_count=0,
                no_wallet=True,
                wallet_activated=False
            )

        if account and account.id:
            try:
                from app.audit.forensic_audit import ForensicAuditService
                ForensicAuditService.log_attempt(
                    entity_type="wallet",
                    entity_id=str(account.id),
                    action="view_dashboard",
                    user_id=current_user.id,
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string if request.user_agent else None
                )
            except Exception:
                pass

        service = WalletService()
        balance_data = service.get_balance(account.user_id)
        balance = balance_data.get('balance', Decimal('0'))

        recent_transactions = TransactionModel.query.filter(
            or_(
                TransactionModel.user_id == current_user.id,
                TransactionModel.recipient_user_id == current_user.id
            )
        ).order_by(TransactionModel.created_at.desc()).limit(10).all()

        transaction_count = calculate_transaction_usage(current_user.id)
        commission = Decimal('0')

        return render_template(
            'wallet/wallet_dashboard.html',
            account=account,
            balance=balance,
            recent_transactions=recent_transactions,
            commission=commission,
            transaction_count=transaction_count,
            no_wallet=False,
            wallet_activated=wallet_status.is_activated if wallet_status else False
        )
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="WALLET_DASHBOARD_ERROR",
            error_message=str(e),
            context={"component": "wallet_dashboard"}
        )
        flash('Unable to load wallet dashboard. Please try again later.', 'warning')
        return render_template('wallet/wallet_dashboard.html', balance=Decimal('0'), recent_transactions=[], commission=Decimal('0'), no_wallet=True, wallet_activated=False)


@wallet_bp.route('/overview')
@login_required
def overview():
    """Wallet overview page"""
    try:
        account = get_or_create_account(current_user.id)
        service = WalletService()
        balance = service.get_balance(account.user_id)
        
        # Mock data for template compatibility
        wallet = {
            'user_id': current_user.id,
            'nationality': getattr(current_user, 'nationality', 'UG'),
            'location': getattr(current_user, 'location', 'Kampala'),
            'home_currency': account.currency,
            'local_currency': account.currency,
            'balance_home': balance,
            'balance_local': balance
        }
        
        # Mock commission
        commission = Decimal('0')
        
        return render_template('wallet/overview.html', wallet=wallet, commission=commission)
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="WALLET_OVERVIEW_ERROR",
            error_message=str(e),
            context={"component": "wallet_overview"}
        )
        flash('Unable to load wallet overview. Please try again later.', 'warning')
        return render_template('wallet/overview.html')


# =============================================================================
# DEPOSIT ROUTES
# =============================================================================

@wallet_bp.route('/create', methods=['GET'])
@login_required
def wallet_create_page():
    """Show wallet creation page"""
    account = get_account(current_user.id)
    if account:
        flash('You already have a wallet.', 'info')
        return redirect(url_for('wallet.wallet_dashboard'))
    return render_template('wallet/wallet_create.html')


@wallet_bp.route('/create', methods=['POST'])
@login_required
def wallet_create():
    """Create a new wallet for the current user"""
    from flask_wtf.csrf import validate_csrf
    
    # Validate CSRF
    csrf_token = request.form.get('csrf_token')
    if not csrf_token:
        flash('CSRF token missing', 'error')
        return redirect(url_for('wallet.wallet_create_page'))
    try:
        validate_csrf(csrf_token)
    except Exception:
        flash('Invalid CSRF token', 'error')
        return redirect(url_for('wallet.wallet_create_page'))
    
    # Check KYC level before wallet creation (must be at least Tier 0 - email and phone verified)
    if not current_user.email_verified:
        flash('Please verify your email address before creating a wallet.', 'error')
        return redirect(url_for('wallet.wallet_create_page'))
    
    if not current_user.phone_verified:
        flash('Please verify your phone number before creating a wallet.', 'error')
        return redirect(url_for('wallet.wallet_create_page'))
    
    # Check terms acceptance
    accept_terms = request.form.get('accept_terms') == '1'
    if not accept_terms:
        flash('You must accept the Terms and Conditions to create a wallet', 'error')
        return redirect(url_for('wallet.wallet_create_page'))
    
    try:
        # Check if wallet already exists
        account = get_account(current_user.id)
        if account:
            flash('You already have a wallet.', 'info')
            return redirect(url_for('wallet.wallet_dashboard'))
        
        # Get currency from form (default to UGX)
        currency = request.form.get('currency', 'UGX')
        
        # Create account using get_or_create_account with selected currency
        account = get_or_create_account(current_user.id, currency=currency)
        
        flash('Wallet created successfully! Please activate your wallet.', 'success')
        return redirect(url_for('wallet.wallet_activate'))
        
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="WALLET_CREATION_ERROR",
            error_message=str(e),
            context={"component": "wallet_creation"}
        )
        flash('Unable to create wallet. Please try again later.', 'warning')
        return redirect(url_for('wallet.wallet_create_page'))


@wallet_bp.route('/deposit')
@login_required
@require_deposit_access
def deposit_page():
    """GET: Show deposit form"""
    account = get_account(current_user.id)
    if not account:
        flash('You need to create a wallet first.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))
    return render_template('wallet/deposit.html', account=account, balance=Decimal('0'))


@wallet_bp.route('/deposit', methods=['POST'])
@login_required
@require_deposit_access
@require_fresh_user
def deposit_form():
    """POST: Process deposit request"""
    try:
        amount = request.form.get('amount')
        currency = request.form.get('currency', 'UGX')
        
        if not amount:
            flash('Amount is required', 'error')
            return redirect(url_for('wallet.deposit_page'))
        
        try:
            amount = Decimal(amount)
        except:
            flash('Invalid amount', 'error')
            return redirect(url_for('wallet.deposit_page'))
        
        if amount <= 0:
            flash('Amount must be greater than zero', 'error')
            return redirect(url_for('wallet.deposit_page'))
        
        # Get existing account (do NOT auto-create)
        account = get_account(current_user.id, currency)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        
        # Process deposit using WalletService
        service = WalletService()
        transaction = service.deposit(
            account_id=account.id,  # UUID - correct per Alipay model
            amount=amount,
            currency=currency,
            client_request_id=str(uuid4()),  # Required parameter
            metadata={'source': 'web_form'}
        )
        
        flash(f'Deposit of {amount} {currency} initiated successfully!', 'success')
        return redirect(url_for('wallet.wallet_dashboard'))
        
    except LimitExceededError as e:
        flash(f'Deposit limit exceeded: {str(e)}', 'error')
        return redirect(url_for('wallet.deposit_page'))
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="DEPOSIT_PROCESSING_ERROR",
            error_message=str(e),
            context={"component": "deposit_processing"}
        )
        flash('Unable to process deposit. Please try again later.', 'warning')
        return redirect(url_for('wallet.deposit_page'))


# =============================================================================
# SEND / TRANSFER ROUTES
# =============================================================================

@wallet_bp.route('/send')
@login_required
@require_send_access
def send_page():
    """GET: Show send funds form"""
    account = get_account(current_user.id)
    if not account:
        flash('You need to create a wallet first.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))
    return render_template('wallet/send.html', account=account, balance=Decimal('0'))


@wallet_bp.route('/send', methods=['POST'])
@login_required
@require_send_access
@require_fresh_user
def send_funds():
    """POST: Process send/transfer request"""
    try:
        receiver_id = request.form.get('receiver_id')
        amount = request.form.get('amount')
        currency = request.form.get('currency', 'UGX')
        agent_fee = request.form.get('agent_fee', '0')
        
        if not receiver_id or not amount:
            flash('Receiver ID and amount are required', 'error')
            return redirect(url_for('wallet.send_page'))
        
        try:
            amount = Decimal(amount)
            agent_fee = Decimal(agent_fee) if agent_fee else Decimal('0')
        except:
            flash('Invalid amount', 'error')
            return redirect(url_for('wallet.send_page'))
        
        if amount <= 0:
            flash('Amount must be greater than zero', 'error')
            return redirect(url_for('wallet.send_page'))
        
        # Get sender account (do NOT auto-create)
        sender_account = get_account(current_user.id, currency)
        if not sender_account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        
        # Get receiver account (by user_id or public_id)
        from app.identity.models.user import User
        receiver = User.query.filter(
            (User.id == receiver_id) | (User.public_id == receiver_id)
        ).first()
        
        if not receiver:
            flash('Receiver not found', 'error')
            return redirect(url_for('wallet.send_page'))
        
        # Check if receiver has an account (do NOT auto-create)
        receiver_account = get_account(receiver.id, currency)
        if not receiver_account:
            flash('Receiver does not have a wallet account. Please ask them to create one first.', 'error')
            current_app.logger.warning(
                f"Transfer attempt to user {receiver_id} without wallet account "
                f"by sender {current_user.id}"
            )
            return redirect(url_for('wallet.send_page'))
        
        # Get pin from form (optional) and call service.transfer using internal user ids
        pin = request.form.get('pin')

        service = WalletService()
        # Use from_account_id / to_account_id (UUIDs) and generate a client_request_id
        client_request_id = str(uuid4())
        transaction = service.transfer(
            from_account_id=sender_account.id,  # UUID - correct per Alipay model
            to_account_id=receiver_account.id,    # UUID - correct per Alipay model
            amount=amount,
            currency=currency,
            client_request_id=client_request_id,
            note=f"Transfer to user {receiver_id}",
            metadata={'agent_fee': str(agent_fee)} if agent_fee > 0 else {},
            pin=pin
        )
        
        flash(f'Successfully sent {amount} {currency} to {receiver_id}', 'success')
        return redirect(url_for('wallet.wallet_dashboard'))
        
    except InsufficientBalanceError:
        flash('Insufficient balance', 'error')
        return redirect(url_for('wallet.send_page'))
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="SEND_FUNDS_ERROR",
            error_message=str(e),
            context={"component": "send_funds"}
        )
        flash('Unable to send funds. Please try again later.', 'warning')
        return redirect(url_for('wallet.send_page'))


# =============================================================================
# WITHDRAW ROUTES
# =============================================================================

@wallet_bp.route('/withdraw')
@login_required
@require_withdraw_access
def withdraw_page():
    """GET: Show withdraw form"""
    account = get_account(current_user.id)
    if not account:
        flash('You need to create a wallet first.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))
    return render_template('wallet/withdraw.html', account=account, balance=Decimal('0'))


@wallet_bp.route('/withdraw', methods=['POST'])
@login_required
@require_withdraw_access
@require_fresh_user
def withdraw_funds():
    """POST: Process withdrawal request"""
    try:
        amount = request.form.get('amount')
        currency = request.form.get('currency', 'UGX')
        method = request.form.get('method', 'ATM')
        agent_id = request.form.get('agent_id', '')
        
        if not amount:
            flash('Amount is required', 'error')
            return redirect(url_for('wallet.withdraw_page'))
        
        try:
            amount = Decimal(amount)
        except:
            flash('Invalid amount', 'error')
            return redirect(url_for('wallet.withdraw_page'))
        
        if amount <= 0:
            flash('Amount must be greater than zero', 'error')
            return redirect(url_for('wallet.withdraw_page'))
        
        # Get existing account (do NOT auto-create)
        account = get_account(current_user.id, currency)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        
        # Process withdrawal using WalletService
        service = WalletService()
        transaction = service.withdraw(
            account_id=account.id,  # UUID - correct per Alipay model
            amount=amount,
            currency=currency,
            client_request_id=str(uuid4()),  # Required parameter
            metadata={'method': method, 'agent_id': agent_id}
        )
        
        flash(f'Withdrawal of {amount} {currency} initiated successfully!', 'success')
        return redirect(url_for('wallet.wallet_dashboard'))
        
    except InsufficientBalanceError:
        flash('Insufficient balance', 'error')
        return redirect(url_for('wallet.withdraw_page'))
    except LimitExceededError as e:
        flash(f'Withdrawal limit exceeded: {str(e)}', 'error')
        return redirect(url_for('wallet.withdraw_page'))
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="WITHDRAW_PROCESSING_ERROR",
            error_message=str(e),
            context={"component": "withdraw_processing"}
        )
        flash('Unable to process withdrawal. Please try again later.', 'warning')
        return redirect(url_for('wallet.withdraw_page'))


# =============================================================================
# TRANSACTIONS ROUTES
# =============================================================================

@wallet_bp.route('/transactions')
@login_required
def wallet_transactions():
    """View all transactions"""
    try:
        account = get_account(current_user.id)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        
        # Get all transactions where current user is sender or recipient
        transactions = TransactionModel.query.filter(
            or_(
                TransactionModel.user_id == current_user.id,
                TransactionModel.recipient_user_id == current_user.id
            )
        ).order_by(TransactionModel.created_at.desc()).all()
        
        # Format for template compatibility
        formatted_transactions = []
        for tx in transactions:
            formatted_transactions.append({
                'id': tx.id,
                'type': tx.tx_type.value if hasattr(tx.tx_type, 'value') else str(tx.tx_type),
                'amount': float(tx.amount),
                'currency': tx.currency,
                'status': tx.status.value if hasattr(tx.status, 'value') else str(tx.status),
                'timestamp': tx.created_at.isoformat() if tx.created_at else None,
                'to': tx.recipient_user_id,
                'from': tx.user_id,
                'description': tx.tx_metadata.get('description') if tx.tx_metadata else ''
            })
        
        return render_template(
            'wallet/transactions.html',
            transactions=formatted_transactions,
            account=account,
            balance=Decimal('0')
        )
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="TRANSACTIONS_LOAD_ERROR",
            error_message=str(e),
            context={"component": "transactions_load"}
        )
        flash('Unable to load transactions. Please try again later.', 'warning')
        return render_template('wallet/transactions.html', transactions=[], account=None, balance=Decimal('0'))


# =============================================================================
# AGENT PAYOUT ROUTES (Placeholder for agent functionality)
# =============================================================================

@wallet_bp.route('/agent/payout/history')
@login_required
@require_payout_access
def agent_payout_history():
    """View agent payout history"""
    try:
        account = get_account(current_user.id)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        # Fetch commission summary & payouts
        from app.wallet.services.commission_service import CommissionService
        from app.wallet.services.payout_service import PayoutService

        commission_service = CommissionService()
        payout_service = PayoutService()

        summary = commission_service.get_commission_summary(current_user.id)
        payouts = payout_service.list_requests(current_user.id)

        return render_template('wallet/agent_payout_history.html', account=account, summary=summary, payouts=payouts)
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="PAYOUT_HISTORY_ERROR",
            error_message=str(e),
            context={"component": "payout_history"}
        )
        flash('Unable to load payout history. Please try again later.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/agent/payout/request', methods=['GET'])
@login_required
def agent_payout_request_page():
    """Show agent payout request form"""
    try:
        account = get_account(current_user.id)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        # Commission summary and history
        from app.wallet.services.commission_service import CommissionService
        from app.wallet.services.payout_service import PayoutService

        commission_service = CommissionService()
        payout_service = PayoutService()

        summary = commission_service.get_commission_summary(current_user.id)
        history = commission_service.get_agent_commissions(current_user.id)
        total = summary.get('total_pending') if isinstance(summary, dict) else 0

        return render_template('agent_payout_request.html', agent_id=current_user.id, total=total, history=history)
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="PAYOUT_REQUEST_PAGE_ERROR",
            error_message=str(e),
            context={"component": "payout_request_page"}
        )
        flash('Unable to load payout request page. Please try again later.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/agent/payout/request', methods=['POST'])
@login_required
@require_fresh_user
def payout_request_form():
    """Handle payout request submission from agent"""
    try:
        amount = request.form.get('amount')
        method = request.form.get('method', 'bank')
        account_info = request.form.get('account') or {}

        if not amount:
            flash('Amount is required', 'error')
            return redirect(url_for('wallet.agent_payout_request_page'))

        from decimal import Decimal
        try:
            amount = Decimal(amount)
        except:
            flash('Invalid amount', 'error')
            return redirect(url_for('wallet.agent_payout_request_page'))

        from app.wallet.services.payout_service import PayoutService
        payout_service = PayoutService()
        # Create payout request (persisted)
        pr = payout_service.create_request(
            agent_id=current_user.id,
            amount=amount,
            currency='UGX',
            payment_method=method,
            payment_details={'account': account_info}
        )

        flash('Payout request submitted', 'success')
        return redirect(url_for('wallet.agent_payout_history'))
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="PAYOUT_REQUEST_SUBMISSION_ERROR",
            error_message=str(e),
            context={"component": "payout_request_submission"}
        )
        flash('Unable to submit payout request. Please try again later.', 'warning')
        return redirect(url_for('wallet.agent_payout_request_page'))


# =============================================================================
# ADDITIONAL WALLET ROUTES
# =============================================================================

@wallet_bp.route('/terms')
@login_required
def wallet_terms():
    """Wallet terms and conditions page"""
    return render_template('wallet/wallet_terms.html')


@wallet_bp.route('/settings')
@login_required
def wallet_settings():
    """Wallet settings page"""
    try:
        account = get_account(current_user.id)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        service = WalletService()
        balance_data = service.get_balance(account.user_id)
        balance = balance_data.get('balance', Decimal('0'))
        
        # Get supported currencies
        from app.wallet.services.currency_service import CurrencyService
        currency_service = CurrencyService()
        supported_currencies = currency_service.get_supported_currencies()
        
        return render_template(
            'wallet/wallet_settings.html',
            account=account,
            balance=balance,
            supported_currencies=supported_currencies
        )
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="WALLET_SETTINGS_ERROR",
            error_message=str(e),
            context={"component": "wallet_settings"}
        )
        flash('Unable to load wallet settings. Please try again later.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/settings', methods=['POST'])
@login_required
@require_fresh_user
def wallet_settings_update():
    """Update wallet settings"""
    try:
        account = get_account(current_user.id)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        
        # Update currency preference if provided
        new_currency = request.form.get('currency')
        if new_currency and new_currency != account.currency:
            from app.wallet.services.currency_service import CurrencyService
            currency_service = CurrencyService()
            if currency_service.validate_currency(new_currency):
                flash('Currency change requires creating a new wallet account', 'info')
            else:
                flash('Invalid currency', 'error')
        
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('wallet.wallet_settings'))
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="WALLET_SETTINGS_UPDATE_ERROR",
            error_message=str(e),
            context={"component": "wallet_settings_update"}
        )
        flash('Unable to update settings. Please try again later.', 'warning')
        return redirect(url_for('wallet.wallet_settings'))


# -----------------------------------------------------------------------------
# Transaction PIN endpoints
# -----------------------------------------------------------------------------
@wallet_bp.route('/pin', methods=['GET'])
@login_required
def pin_page():
    """Show PIN management page - forward to template if available."""
    try:
        account = get_account(current_user.id)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        has_pin = bool(getattr(current_user, 'transaction_pin_hash', None))
        return render_template('wallet/pin.html', account=account, has_pin=has_pin)
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="PIN_PAGE_ERROR",
            error_message=str(e),
            context={"component": "pin_page"}
        )
        flash('Unable to load PIN page. Please try again later.', 'warning')
        return redirect(url_for('wallet.wallet_settings'))


@wallet_bp.route('/pin/set', methods=['POST'])
@login_required
@require_fresh_user
def set_pin():
    """Set or update user's transaction PIN."""
    try:
        pin = request.form.get('pin')
        confirm = request.form.get('confirm_pin')

        if not pin or not confirm:
            flash('PIN and confirmation are required', 'error')
            return redirect(url_for('wallet.pin_page'))

        if pin != confirm:
            flash('PINs do not match', 'error')
            return redirect(url_for('wallet.pin_page'))

        # Persist via current_user and DB session
        from app.extensions import db
        current_user.set_transaction_pin(pin, session=db.session)
        db.session.commit()

        flash('Transaction PIN set successfully', 'success')
        return redirect(url_for('wallet.wallet_settings'))
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('wallet.pin_page'))
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="SET_PIN_ERROR",
            error_message=str(e),
            context={"component": "set_pin"}
        )
        flash('Unable to set PIN. Please try again later.', 'warning')
        return redirect(url_for('wallet.pin_page'))


@wallet_bp.route('/fx-rates')
@login_required
def fx_rates():
    """View FX rates page"""
    try:
        from app.wallet.services.fx_service import FXService
        fx_service = FXService()
        
        # Get all available rates
        rates = fx_service.get_all_rates()
        
        return render_template('wallet/fx_rates.html', rates=rates, balance=Decimal('0'))
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="FX_RATES_ERROR",
            error_message=str(e),
            context={"component": "fx_rates"}
        )
        flash('Unable to load FX rates. Please try again later.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/compliance')
@login_required
def compliance_status():
    """View compliance status page"""
    try:
        account = get_account(current_user.id)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        
        return render_template('wallet/compliance.html', account=account, balance=Decimal('0'))
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="COMPLIANCE_STATUS_ERROR",
            error_message=str(e),
            context={"component": "compliance_status"}
        )
        flash('Unable to load compliance status. Please try again later.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/history')
@login_required
def transaction_history():
    """Detailed transaction history page"""
    try:
        account = get_account(current_user.id)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        service = WalletService()
        
        # Get transaction history with filters
        transaction_type = request.args.get('type')
        limit = request.args.get('limit', 50, type=int)
        
        history = service.get_transaction_history(
            user_id=account.user_id,
            limit=limit,
            transaction_type=transaction_type
        )
        
        return render_template(
            'wallet/transaction_history.html',
            transactions=history.get('transactions', []),
            pagination=history.get('pagination', {}),
            account=account
        )
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="TRANSACTION_HISTORY_ERROR",
            error_message=str(e),
            context={"component": "transaction_history"}
        )
        flash('Unable to load transaction history. Please try again later.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))


# =============================================================================
# API ENDPOINTS (JSON)
# =============================================================================

@wallet_bp.route('/api/balance')
@login_required
def api_balance():
    """API: Get current balance"""
    try:
        account = get_account(current_user.id)
        if not account:
            return jsonify({'success': False, 'error': 'No wallet account'}), 404
        service = WalletService()
        balance = service.get_balance(account.user_id)
        
        return jsonify({
            'success': True,
            'balance': str(balance),
            'currency': account.currency,
            'account_id': str(account.id)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_bp.route('/api/transactions')
@login_required
def api_transactions():
    """API: Get transaction history"""
    try:
        account = get_account(current_user.id)
        if not account:
            return jsonify({'success': False, 'error': 'No wallet account'}), 404
        limit = request.args.get('limit', 50, type=int)
        
        transactions = TransactionModel.query.filter(
            or_(
                TransactionModel.user_id == current_user.id,
                TransactionModel.recipient_user_id == current_user.id
            )
        ).order_by(TransactionModel.created_at.desc()).limit(limit).all()
        
        return jsonify({
            'success': True,
            'transactions': [
                {
                    'id': str(tx.id),
                    'type': tx.tx_type.value if hasattr(tx.tx_type, 'value') else str(tx.tx_type),
                    'amount': str(tx.amount),
                    'currency': tx.currency,
                    'status': tx.status.value if hasattr(tx.status, 'value') else str(tx.status),
                    'created_at': tx.created_at.isoformat() if tx.created_at else None,
                    'description': tx.tx_metadata.get('description') if tx.tx_metadata else ''
                }
                for tx in transactions
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
