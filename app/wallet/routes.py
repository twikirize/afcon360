"""
Wallet routes for the wallet system.
Complete implementation with all endpoints for user wallet operations.
"""

from datetime import datetime, timezone
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
from app.wallet.decorators import (
    require_no_freeze,
    require_sufficient_kyc,
    require_transaction_verification
)
from app.wallet.services.wallet_status_service import WalletFeature, WalletStatusService
from app.auth.decorators import require_fresh_user
from app.utils.analytics import AnalyticsService
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
    from app.wallet.models.ledger import AccountModel, AccountOwnerType, AccountStatus, AccountType
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
    account = AccountModel.query.filter_by(
        user_id=internal_id,
        owner_type=AccountOwnerType.USER
    ).first()
    
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
            monthly_volume_reset_at=None,
            owner_type=AccountOwnerType.USER,
            status=AccountStatus.ACTIVE,
            account_type=AccountType.USER_WALLET,
            account_name=f"Wallet_{currency}_{internal_id}",
            verified=False
        )
        db.session.add(account)
        db.session.commit()
        
        # Re-query to ensure we have a fresh object from the DB
        account = AccountModel.query.filter_by(
            user_id=internal_id,
            owner_type=AccountOwnerType.USER
        ).first()
        
    return account


@wallet_bp.route("/activate", methods=["GET", "POST"], endpoint='wallet_activate')
@login_required
@require_fresh_user
def activate_wallet():
    """User explicitly opts in to wallet activation with terms acceptance."""
    from app.identity.models.user import User
    from app.wallet.models.ledger import AccountOwnerType
    from app.wallet.services.wallet_creation_tracker import (
        WalletCreationTracker, WalletCreationEvent
    )
    from datetime import datetime, timezone

    db_user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not db_user:
        flash("User not found.", "danger")
        return redirect(url_for("user.dashboard"))

    # Ownership validation: get account ONLY if it belongs to this user
    account = AccountModel.query.filter_by(
        user_id=db_user.id,
        owner_type=AccountOwnerType.USER
    ).first()

    if not account:
        flash('You need to create a wallet first.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))

    # Check if wallet is already activated
    if account.verified:
        flash('Your wallet is already activated.', 'info')
        return redirect(url_for('wallet.wallet_dashboard'))

    # GET request: Show activation form
    if request.method == 'GET':
        return render_template('wallet/wallet_activate.html', account=account)

    # POST request: Process activation
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

        # Check if already activated
        if account.verified:
            flash('Your wallet is already activated.', 'info')
            return redirect(url_for('wallet.wallet_dashboard'))

        # Check terms acceptance
        if not request.form.get('accept_terms'):
            flash('You must accept the terms to activate your wallet.', 'warning')
            return render_template('wallet/wallet_activate.html', account=account)

        # Activate wallet
        account.verified = True
        account.terms_accepted_at = datetime.now(timezone.utc)
        db.session.commit()

        # Record activation in tracker
        try:
            WalletCreationTracker.record_activation(
                user_id=current_user.id,
                account_id=str(account.id)
            )
            WalletCreationTracker.record_completion(
                user_id=current_user.id,
                account_id=str(account.id)
            )
        except Exception as e:
            current_app.logger.warning(f"Could not record activation in tracker: {e}")

        # Record in audit log (compliance/system event)
        try:
            from app.audit.comprehensive_audit import AuditService
            AuditService.data_change(
                entity_type="wallet",
                entity_id=str(account.id),
                operation="activate",
                old_value={"verified": False},
                new_value={"verified": True, "terms_accepted_at": str(account.terms_accepted_at)},
                changed_by=current_user.id,
                extra_data={
                    "ip_address": request.remote_addr,
                    "user_agent": request.user_agent.string if request.user_agent else None
                }
            )
            current_app.logger.info(f"Audit: Wallet activation logged for user {current_user.id}")
        except Exception as e:
            current_app.logger.error(f"Audit error: {e}")

        flash('Your wallet has been activated!', 'success')

        # Check PIN setup
        if not current_user.transaction_pin_hash:
            flash('Please set a transaction PIN to secure your funds before you start.', 'info')
            return redirect(url_for('wallet.pin_page'))

        return redirect(url_for('wallet.wallet_dashboard'))

    return render_template('wallet/wallet_activate.html', account=account)


# =============================================================================
# HOME / DASHBOARD ROUTES
# =============================================================================

from app.utils.module_guard import require_module_enabled

@wallet_bp.route('/')
@require_module_enabled("wallet")
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
@require_module_enabled("wallet")
@login_required
def wallet_dashboard():
    """Main wallet dashboard — the real landing page."""
    import traceback
    import logging
    logger = logging.getLogger(__name__)

    is_pane = request.args.get('_pane') == '1'
    if is_pane:
        # Loaded inside the unified user dashboard pane — render fragment only
        return _wallet_dashboard_pane()

    AnalyticsService.track_page_view('wallet')

    # Clear admin/module flash messages from previous page loads
    from flask import session
    if '_flashes' in session:
        session['_flashes'] = [(category, message) for category, message in session['_flashes'] if 'module' not in message.lower()]

    try:
        logger.info("=" * 60)
        logger.info("WALLET DASHBOARD START")
        logger.info(f"User ID: {current_user.id}")
        logger.info(f"User Public ID: {current_user.public_id}")
        logger.info("=" * 60)

        # 1. Get wallet status
        logger.info("Step 1: Getting wallet status...")
        wallet_status = WalletStatusService.get_wallet_status(current_user)
        logger.info(f"Wallet Status: exists={wallet_status.exists if wallet_status else 'None'}, activated={wallet_status.is_activated if wallet_status else 'None'}")

        # 2. Get account
        logger.info("Step 2: Getting account...")
        account = get_account(current_user.id)
        logger.info(f"Account found: {account is not None}")

        # Get wallet creation trace for dashboard context
        from app.wallet.services.wallet_creation_tracker import WalletCreationTracker
        creation_trace = WalletCreationTracker.get_creation_status(current_user.id)

        if account:
            logger.info(f"  Account ID: {account.id}")
            logger.info(f"  Account Verified: {account.verified}")
            logger.info(f"  Account Currency: {account.currency}")
            logger.info(f"  Account Is Frozen: {account.is_frozen}")

        # 3. If no account, show no-wallet state
        if not account:
            logger.info("No account found - showing create prompt")
            return render_template(
                'wallet/wallet_dashboard.html',
                account=None,
                balance=Decimal('0'),
                recent_transactions=[],
                commission=Decimal('0'),
                transaction_count=0,
                no_wallet=True,
                wallet_activated=False,
                show_create_prompt=True,
                wallet_creation_status=creation_trace
            )

        # 4. Get balance from ledger
        logger.info("Step 3: Getting balance...")
        service = WalletService()
        balance_data = service.get_balance(account.user_id)
        balance = balance_data.get('balance', Decimal('0'))
        logger.info(f"Balance: {balance}")

        # 5. Get recent transactions
        logger.info("Step 4: Getting transactions...")
        recent_transactions = TransactionModel.query.filter(
            or_(
                TransactionModel.user_id == current_user.id,
                TransactionModel.recipient_user_id == current_user.id
            )
        ).order_by(TransactionModel.created_at.desc()).limit(10).all()
        logger.info(f"Transactions: {len(recent_transactions)}")

        # 6. Calculate transaction count
        transaction_count = calculate_transaction_usage(current_user.id)
        commission = Decimal('0')

        logger.info("Step 5: Rendering dashboard...")
        return render_template(
            'wallet/wallet_dashboard.html',
            account=account,
            balance=balance,
            recent_transactions=recent_transactions,
            commission=commission,
            transaction_count=transaction_count,
            no_wallet=False,
            wallet_activated=wallet_status.is_activated if wallet_status else False,
            show_create_prompt=False,
            wallet_creation_status={}
        )

    except Exception as e:
        # Log the FULL error
        logger.error("=" * 60)
        logger.error("❌ DASHBOARD ERROR")
        logger.error(f"Error Type: {type(e).__name__}")
        logger.error(f"Error Message: {str(e)}")
        logger.error("Full Traceback:")
        logger.error(traceback.format_exc())
        logger.error("=" * 60)

        # Also log to the app's error handler
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="WALLET_DASHBOARD_ERROR",
            error_message=str(e),
            context={"component": "wallet_dashboard"}
        )

        flash('Unable to load wallet dashboard. Please try again later.', 'warning')
        return render_template(
            'wallet/wallet_dashboard.html',
            balance=Decimal('0'),
            recent_transactions=[],
            commission=Decimal('0'),
            no_wallet=True,
            wallet_activated=False,
            show_create_prompt=True,
            wallet_creation_status={}
        )


def _wallet_dashboard_pane():
    """Render the wallet dashboard as a fragment for the unified user dashboard pane."""
    try:
        wallet_status = WalletStatusService.get_wallet_status(current_user)
        account = get_account(current_user.id)
        balance = Decimal('0')
        recent_transactions = []
        transaction_count = 0
        no_wallet = not account
        wallet_activated = wallet_status.is_activated if wallet_status else False

        if account:
            service = WalletService()
            balance_data = service.get_balance(account.user_id)
            balance = balance_data.get('balance', Decimal('0'))
            recent_transactions = TransactionModel.query.filter(
                or_(
                    TransactionModel.user_id == current_user.id,
                    TransactionModel.recipient_user_id == current_user.id
                )
            ).order_by(TransactionModel.created_at.desc()).limit(5).all()
            transaction_count = calculate_transaction_usage(current_user.id)

        return render_template(
            'wallet/wallet_dashboard_pane.html',
            account=account,
            balance=balance,
            recent_transactions=recent_transactions,
            commission=Decimal('0'),
            transaction_count=transaction_count,
            no_wallet=no_wallet,
            wallet_activated=wallet_activated,
            show_create_prompt=no_wallet,
            wallet_creation_status={}
        )
    except Exception:
        return render_template(
            'wallet/wallet_dashboard_pane.html',
            balance=Decimal('0'),
            recent_transactions=[],
            commission=Decimal('0'),
            no_wallet=True,
            wallet_activated=False,
            show_create_prompt=True,
            wallet_creation_status={}
        )


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
    """Show wallet creation page with user context"""
    account = get_account(current_user.id)
    if account:
        flash('You already have a wallet.', 'info')
        return redirect(url_for('wallet.wallet_dashboard'))
    
    # Get user profile for pre-filling
    from app.profile.models import get_profile_by_user
    profile = get_profile_by_user(current_user.public_id)
    nationality = getattr(profile, 'nationality', 'UG') if profile else 'UG'
    
    return render_template('wallet/wallet_create.html', nationality=nationality)


@wallet_bp.route('/create', methods=['POST'])
@login_required
def wallet_create():
    """Create a new wallet"""
    from flask_wtf.csrf import validate_csrf
    from app.extensions import db
    
    # Validate CSRF
    csrf_token = request.form.get('csrf_token')
    if not csrf_token:
        flash('Security token missing. Please try again.', 'danger')
        return redirect(url_for('wallet.wallet_create_page'))
    try:
        validate_csrf(csrf_token)
    except Exception:
        flash('Security validation failed. Please refresh and try again.', 'danger')
        return redirect(url_for('wallet.wallet_create_page'))
    
    # Check KYC level before wallet creation
    # (Must have verified email/phone for a fintech-grade wallet)
    if not current_user.email_verified:
        flash('Email verification required to open a financial account.', 'warning')
        return redirect(url_for('wallet.wallet_create_page'))
    
    # Check terms acceptance
    accept_terms = request.form.get('accept_terms') == '1'
    if not accept_terms:
        flash('Please accept the Wallet Terms of Service to proceed.', 'danger')
        return redirect(url_for('wallet.wallet_create_page'))
    
    try:
        # Check if wallet already exists
        account = get_account(current_user.id)
        if account:
            flash('You already have a wallet.', 'info')
            return redirect(url_for('wallet.wallet_dashboard'))

        # Get currency from form (default to UGX)
        currency = request.form.get('currency', 'UGX')

        # Start wallet creation tracker
        from app.wallet.services.wallet_creation_tracker import (
            WalletCreationTracker, WalletCreationEvent
        )
        WalletCreationTracker.log_step(current_user.id, WalletCreationEvent.INITIATED)

        # Create account using get_or_create_account with selected currency
        account = get_or_create_account(current_user.id, currency=currency)

        # Verify account was created and is retrievable
        if not account:
            raise ValueError("Account creation returned None")

        # Record account creation in tracker
        WalletCreationTracker.record_account_created(
            current_user.id, str(account.id)
        )

        # Force flush and re-query to ensure account is visible
        db.session.flush()
        db.session.commit()

        # Verify the account exists by re-querying and checking ownership
        verify_account = get_account(current_user.id)
        if not verify_account:
            current_app.logger.error(
                f"Account verification failed after creation for user {current_user.id}"
            )
            WalletCreationTracker.log_step(
                current_user.id,
                WalletCreationEvent.FAILED,
                metadata={"error": "Account created but not found in database"}
            )
            raise ValueError("Account created but not found in database")

        # Verify account ownership to prevent hijacking
        if not WalletCreationTracker.verify_account_ownership(
            str(verify_account.id), current_user.id
        ):
            WalletCreationTracker.log_step(
                current_user.id,
                WalletCreationEvent.FAILED,
                metadata={"error": "Account ownership verification failed"}
            )
            raise ValueError("Account ownership verification failed")

        WalletCreationTracker.log_step(
            current_user.id,
            WalletCreationEvent.ACCOUNT_VERIFIED
        )
        WalletCreationTracker.record_completion(
            current_user.id, str(verify_account.id)
        )

        # Record in audit log (compliance/system event)
        try:
            from app.audit.comprehensive_audit import AuditService
            AuditService.data_change(
                entity_type="wallet",
                entity_id=str(verify_account.id),
                operation="create",
                old_value=None,
                new_value={
                    "currency": currency,
                    "owner_type": "USER",
                    "status": "ACTIVE",
                    "verified": False
                },
                changed_by=current_user.id,
                extra_data={
                    "ip_address": request.remote_addr,
                    "user_agent": request.user_agent.string if request.user_agent else None
                }
            )
            current_app.logger.info(f"Audit: Wallet creation logged for user {current_user.id}")
        except Exception as e:
            current_app.logger.error(f"Audit error: {e}")

        current_app.logger.info(
            f"Wallet created and verified for user {current_user.id} with currency {currency}"
        )

        flash('Financial account opened successfully! Your vault is ready for activation.', 'success')
        return redirect(url_for('wallet.wallet_activate'))

    except Exception as e:
        db.session.rollback()
        from app.utils.error_handler import log_error_to_audit
        log_error_to_audit(
            user_id=current_user.id,
            error_type="WALLET_CREATION_FAILURE",
            error_message=str(e),
            context={"component": "wallet_onboarding", "currency": request.form.get('currency')}
        )
        current_app.logger.error(f"Wallet creation failed: {e}")

        from app.wallet.services.wallet_creation_tracker import WalletCreationTracker, WalletCreationEvent
        WalletCreationTracker.log_step(
            current_user.id,
            WalletCreationEvent.FAILED,
            metadata={"error": str(e)}
        )

        flash('System encountered a temporary glitch while securing your vault. Please try again.', 'warning')
        return redirect(url_for('wallet.wallet_create_page'))


@wallet_bp.route('/deposit')
@login_required
@require_deposit_access
def deposit_page():
    """GET: Show deposit form"""
    account = get_account(current_user.id)
    if request.args.get('_pane') == '1':
        return render_template('wallet/deposit_pane.html', account=account, balance=Decimal('0'))
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
            flash('Amount is required', 'danger')
            return redirect(url_for('wallet.deposit_page'))
        
        try:
            amount = Decimal(amount)
        except:
            flash('Invalid amount', 'danger')
            return redirect(url_for('wallet.deposit_page'))
        
        if amount <= 0:
            flash('Amount must be greater than zero', 'danger')
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
        flash(f'Deposit limit exceeded: {str(e)}', 'danger')
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
    if request.args.get('_pane') == '1':
        balance = Decimal('0')
        if account:
            try:
                balance = WalletService().get_balance(account.user_id).get('balance', Decimal('0'))
            except Exception:
                balance = Decimal('0')
        return render_template('wallet/send_pane.html', account=account, balance=balance)
    if not account:
        flash('You need to create a wallet first.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))
    return render_template('wallet/send.html', account=account, balance=Decimal('0'))


@wallet_bp.route('/send', methods=['POST'])
@login_required
@require_send_access
@require_fresh_user
@require_no_freeze
def send_funds():
    """POST: Process send/transfer request"""
    try:
        receiver_id = request.form.get('receiver_id')
        amount = request.form.get('amount')
        currency = request.form.get('currency', 'UGX')
        agent_fee = request.form.get('agent_fee', '0')
        
        if not receiver_id or not amount:
            flash('Receiver ID and amount are required', 'danger')
            return redirect(url_for('wallet.send_page'))
        
        try:
            amount = Decimal(amount)
            agent_fee = Decimal(agent_fee) if agent_fee else Decimal('0')
        except:
            flash('Invalid amount', 'danger')
            return redirect(url_for('wallet.send_page'))
        
        if amount <= 0:
            flash('Amount must be greater than zero', 'danger')
            return redirect(url_for('wallet.send_page'))
        
        # KYC limit check before processing
        from app.wallet.services.kyc_limit_service import KYCLimitService
        kyc_check = KYCLimitService.check_transaction_allowed(current_user.id, amount, 'send', currency)
        if not kyc_check['allowed']:
            flash(kyc_check.get('reason', 'Transaction not permitted for your KYC level.'), 'warning')
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
            flash('Receiver not found', 'danger')
            return redirect(url_for('wallet.send_page'))
        
        # Check if receiver has an account (do NOT auto-create)
        receiver_account = get_account(receiver.id, currency)
        if not receiver_account:
            flash('Receiver does not have a wallet account. Please ask them to create one first.', 'danger')
            current_app.logger.warning(
                f"Transfer attempt to user {receiver_id} without wallet account "
                f"by sender {current_user.id}"
            )
            return redirect(url_for('wallet.send_page'))
        
        # Get pin from form (optional) and call service.transfer using internal user ids
        pin = request.form.get('pin')

        service = WalletService()
        client_request_id = str(uuid4())
        transaction = service.transfer(
            from_account_id=sender_account.id,
            to_account_id=receiver_account.id,
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
        flash('Insufficient balance', 'danger')
        return redirect(url_for('wallet.send_page'))
    except LimitExceededError as e:
        flash(f'Limit exceeded: {str(e)}', 'danger')
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

@wallet_bp.route('/withdraw', endpoint='withdraw')
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
@require_no_freeze
def withdraw_funds():
    """POST: Process withdrawal request"""
    try:
        amount = request.form.get('amount')
        currency = request.form.get('currency', 'UGX')
        method = request.form.get('method', 'ATM')
        agent_id = request.form.get('agent_id', '')
        
        if not amount:
            flash('Amount is required', 'danger')
            return redirect(url_for('wallet.withdraw_page'))
        
        try:
            amount = Decimal(amount)
        except:
            flash('Invalid amount', 'danger')
            return redirect(url_for('wallet.withdraw_page'))
        
        if amount <= 0:
            flash('Amount must be greater than zero', 'danger')
            return redirect(url_for('wallet.withdraw_page'))
        
        # KYC limit check before processing
        from app.wallet.services.kyc_limit_service import KYCLimitService
        kyc_check = KYCLimitService.check_transaction_allowed(current_user.id, amount, 'withdraw', currency)
        if not kyc_check['allowed']:
            flash(kyc_check.get('reason', 'Withdrawal not permitted for your KYC level.'), 'warning')
            return redirect(url_for('wallet.withdraw_page'))
        
        # Get existing account (do NOT auto-create)
        account = get_account(current_user.id, currency)
        if not account:
            flash('You need to create a wallet first.', 'warning')
            return redirect(url_for('wallet.wallet_dashboard'))
        
        # Process withdrawal using WalletService
        service = WalletService()
        transaction = service.withdraw(
            account_id=account.id,
            amount=amount,
            currency=currency,
            client_request_id=str(uuid4()),
            metadata={'method': method, 'agent_id': agent_id}
        )
        
        flash(f'Withdrawal of {amount} {currency} initiated successfully!', 'success')
        return redirect(url_for('wallet.wallet_dashboard'))
        
    except InsufficientBalanceError:
        flash('Insufficient balance', 'danger')
        return redirect(url_for('wallet.withdraw_page'))
    except LimitExceededError as e:
        flash(f'Withdrawal limit exceeded: {str(e)}', 'danger')
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
            flash('Amount is required', 'danger')
            return redirect(url_for('wallet.agent_payout_request_page'))

        from decimal import Decimal
        try:
            amount = Decimal(amount)
        except:
            flash('Invalid amount', 'danger')
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
                flash('Invalid currency', 'danger')
        
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
            flash('PIN and confirmation are required', 'danger')
            return redirect(url_for('wallet.pin_page'))

        if pin != confirm:
            flash('PINs do not match', 'danger')
            return redirect(url_for('wallet.pin_page'))

        # Persist via current_user and DB session
        from app.extensions import db
        current_user.set_transaction_pin(pin, session=db.session)
        db.session.commit()

        flash('Transaction PIN set successfully', 'success')
        return redirect(url_for('wallet.wallet_settings'))
    except ValueError as e:
        flash(str(e), 'danger')
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
    """View FX rates page with safety indicators."""
    try:
        from app.wallet.services.fx_service import FXService
        fx_service = FXService()
        
        account = get_account(current_user.id)
        base_currency = request.args.get('base') or (account.currency if account else 'USD')
        
        # Use the dict format method
        rates = fx_service.get_all_rates_as_dict(base_currency)
        
        # Show warning if no rates available
        if not rates.get('rates'):
            flash(
                "Exchange rates are currently being updated. Some features may be temporarily unavailable.",
                "warning"
            )
        
        return render_template(
            'wallet/fx_rates.html', 
            rates=rates,
            base_currency=base_currency
        )
    except Exception as e:
        current_app.logger.error(f"FX rates error: {e}")
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

@wallet_bp.route('/fx-convert', endpoint='fx_convert')
@login_required
def fx_convert_page():
    """GET: Show FX conversion form"""
    account = get_account(current_user.id)
    if not account:
        flash('You need to create a wallet first.', 'warning')
        return redirect(url_for('wallet.wallet_dashboard'))
    return render_template('wallet/fx_convert.html', account=account, balance=Decimal('0'))


# =============================================================================
# FINANCIAL ACCOUNT LOOKUP SYSTEM (Financial Roles Only)
# =============================================================================

def _has_financial_access(user) -> bool:
    """Check if user has financial access (Owner, Super Admin, Admin, Wallet Admin, Compliance, Auditor)."""
    if not user or not user.is_authenticated:
        return False

    # Owner has ultimate access
    if user.is_app_owner():
        return True

    role_names = user.role_names if hasattr(user, 'role_names') else []
    financial_roles = {'owner', 'super_admin', 'admin', 'wallet_admin', 'compliance_officer', 'auditor'}
    return any(role in financial_roles for role in role_names)


@wallet_bp.route('/financial/lookup', methods=['GET', 'POST'])
@login_required
def financial_account_lookup():
    """
    Search for user accounts by name, email, phone, or username.
    Only users with financial roles can access this.
    """
    from app.identity.models.user import User
    from app.profile.models import get_profile_by_user, UserProfile
    from app.wallet.models.ledger import AccountModel
    from sqlalchemy import or_
    from decimal import Decimal

    # Authorisation check
    if not _has_financial_access(current_user):
        flash('You do not have permission to access financial account lookup.', 'danger')
        return redirect(url_for('wallet.wallet_dashboard'))

    results = []
    search_query = None
    search_type = 'all'

    if request.method == 'POST':
        search_query = request.form.get('search_query', '').strip()
        search_type = request.form.get('search_type', 'all')

        if search_query and len(search_query) >= 2:
            query = User.query.filter(User.is_deleted == False)

            if search_type == 'all' or search_type == 'name':
                query = query.join(UserProfile, User.public_id == UserProfile.user_id)
                query = query.filter(UserProfile.full_name.ilike(f'%{search_query}%'))

            if search_type == 'all' or search_type == 'email':
                query = query.filter(User.email.ilike(f'%{search_query}%'))

            if search_type == 'all' or search_type == 'phone':
                query = query.filter(User.phone.ilike(f'%{search_query}%'))

            if search_type == 'all' or search_type == 'username':
                query = query.filter(User.username.ilike(f'%{search_query}%'))

            users = query.limit(50).all()

            for user in users:
                profile = get_profile_by_user(user.public_id)
                account = AccountModel.query.filter_by(user_id=user.id).first()

                results.append({
                    'user': user,
                    'profile': profile,
                    'account': account,
                    'account_status': 'active' if account and account.verified else 'pending_activation' if account else 'no_wallet',
                    'account_balance': Decimal('0'),
                    'account_currency': account.currency if account else 'N/A',
                    'roles': user.role_names if hasattr(user, 'role_names') else [],
                    'is_frozen': account.is_frozen if account else False
                })

    return render_template(
        'wallet/financial/account_lookup.html',
        results=results,
        search_query=search_query,
        search_type=search_type,
        total_results=len(results),
        has_access=_has_financial_access(current_user)
    )


@wallet_bp.route('/financial/account/<public_id>')
@login_required
def financial_account_detail(public_id):
    """
    View detailed account information for a specific user.
    Only users with financial roles can access this.
    """
    from app.identity.models.user import User
    from app.profile.models import get_profile_by_user, UserProfile
    from app.wallet.models.ledger import AccountModel
    from app.wallet.models.transaction import TransactionModel
    from app.audit.comprehensive_audit import SecurityEventLog
    from sqlalchemy import or_
    from decimal import Decimal
    from datetime import datetime, timezone

    # Authorisation check
    if not _has_financial_access(current_user):
        flash('You do not have permission to view financial account details.', 'danger')
        return redirect(url_for('wallet.wallet_dashboard'))

    user = User.query.filter_by(public_id=public_id, is_deleted=False).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('wallet.financial_account_lookup'))

    profile = get_profile_by_user(user.public_id)
    account = AccountModel.query.filter_by(user_id=user.id).first()

    # Recent transactions
    recent_transactions = []
    if account:
        recent_transactions = TransactionModel.query.filter(
            or_(
                TransactionModel.user_id == user.id,
                TransactionModel.recipient_user_id == user.id
            )
        ).order_by(TransactionModel.created_at.desc()).limit(20).all()

    # Summary stats
    total_deposits = Decimal('0')
    total_withdrawals = Decimal('0')
    total_transfers_sent = Decimal('0')
    total_transfers_received = Decimal('0')

    for tx in recent_transactions:
        if tx.status.value == 'COMPLETED':
            if tx.tx_type.value == 'DEPOSIT':
                total_deposits += tx.amount
            elif tx.tx_type.value == 'WITHDRAW':
                total_withdrawals += tx.amount
            elif tx.tx_type.value == 'TRANSFER':
                if tx.user_id == user.id:
                    total_transfers_sent += tx.amount
                elif tx.recipient_user_id == user.id:
                    total_transfers_received += tx.amount

    # Active sessions
    active_sessions = []
    if user:
        from app.identity.models.user import Session
        now = datetime.now(timezone.utc)
        active_sessions = Session.query.filter_by(
            user_id=user.id,
            revoked_at=None
        ).filter(Session.expires_at > now).order_by(Session.created_at.desc()).all()

    # KYC info
    kyc_info = {}
    try:
        from app.auth.kyc_compliance import calculate_kyc_tier
        kyc_info = calculate_kyc_tier(user.id)
    except Exception:
        kyc_info = {'tier': 0, 'tier_name': 'Unregistered'}

    # Security events for this user
    security_events = []
    if user:
        security_events = SecurityEventLog.query.filter_by(
            user_id=user.id
        ).order_by(SecurityEventLog.created_at.desc()).limit(50).all()

    # FX conversions for this user
    fx_conversions = []
    if account:
        try:
            from app.wallet.models.fx import FXRateModel
            # FX conversions are tracked in transactions with type FX or in a separate FX log
            # For now, we'll note that FX activity exists
            fx_conversions = TransactionModel.query.filter(
                TransactionModel.user_id == user.id,
                TransactionModel.tx_type == 'FX'
            ).order_by(TransactionModel.created_at.desc()).limit(20).all()
        except Exception:
            pass

    # Payout requests for this user
    payout_requests = []
    if account:
        try:
            from app.wallet.models.payout import PayoutRequest
            payout_requests = PayoutRequest.query.filter_by(
                agent_id=user.id
            ).order_by(PayoutRequest.created_at.desc()).limit(20).all()
        except Exception:
            pass

    # Adjustments for this user
    adjustments = []
    if account:
        try:
            adjustments = TransactionModel.query.filter(
                TransactionModel.user_id == user.id,
                TransactionModel.tx_type == 'ADJUSTMENT'
            ).order_by(TransactionModel.created_at.desc()).limit(20).all()
        except Exception:
            pass

    # Wallet creation tracker events (admin view)
    creation_events = []
    if account:
        try:
            from app.wallet.services.wallet_creation_tracker import WalletCreationTracker
            creation_events = WalletCreationTracker.get_events_for_account(str(account.id))
        except Exception:
            pass

    # Build comprehensive activity timeline
    timeline = []

    # 1. User account creation
    timeline.append({
        'timestamp': user.created_at.isoformat() if user.created_at else None,
        'type': 'account_created',
        'label': 'User Account Created',
        'description': f'User account created for {user.email or user.username}',
        'icon': 'fa-user-plus',
        'color': 'blue'
    })

    # 2. Profile creation
    if profile and profile.created_at:
        timeline.append({
            'timestamp': profile.created_at.isoformat() if profile.created_at else None,
            'type': 'profile_created',
            'label': 'Profile Created',
            'description': f'Profile created for {profile.full_name or user.username}',
            'icon': 'fa-id-card',
            'color': 'green'
        })

    # 3. Wallet/account creation
    if account and account.created_at:
        timeline.append({
            'timestamp': account.created_at.isoformat() if account.created_at else None,
            'type': 'wallet_created',
            'label': 'Wallet Created',
            'description': f'Wallet created with currency {account.currency}',
            'icon': 'fa-wallet',
            'color': 'purple'
        })

    # 4. Wallet activation
    if account and account.verified and account.terms_accepted_at:
        timeline.append({
            'timestamp': account.terms_accepted_at.isoformat() if account.terms_accepted_at else None,
            'type': 'wallet_activated',
            'label': 'Wallet Activated',
            'description': 'Wallet activated with terms accepted',
            'icon': 'fa-check-circle',
            'color': 'green'
        })

    # 5. Wallet suspension/freeze events
    if account and account.is_frozen and account.frozen_at:
        timeline.append({
            'timestamp': account.frozen_at.isoformat() if account.frozen_at else None,
            'type': 'wallet_frozen',
            'label': 'Wallet Frozen',
            'description': f'Wallet frozen: {account.frozen_reason or "No reason provided"}',
            'icon': 'fa-snowflake',
            'color': 'red'
        })

    # 6. Security events
    for event in security_events:
        timeline.append({
            'timestamp': event.created_at.isoformat() if event.created_at else None,
            'type': 'security_event',
            'label': f'Security Event: {event.event_type}',
            'description': event.description or '',
            'icon': 'fa-shield-alt',
            'color': 'red' if event.severity.value == 'WARNING' else 'orange'
        })

    # 7. All transactions (chronological)
    all_transactions = TransactionModel.query.filter(
        or_(
            TransactionModel.user_id == user.id,
            TransactionModel.recipient_user_id == user.id
        )
    ).order_by(TransactionModel.created_at.asc()).all()

    for tx in all_transactions:
        timeline.append({
            'timestamp': tx.created_at.isoformat() if tx.created_at else None,
            'type': 'transaction',
            'label': f'Transaction: {tx.tx_type.value}',
            'description': f'{tx.amount} {tx.currency} - {tx.status.value}',
            'icon': 'fa-exchange-alt',
            'color': 'blue'
        })

    # 8. FX conversions
    for fx in fx_conversions:
        timeline.append({
            'timestamp': fx.created_at.isoformat() if fx.created_at else None,
            'type': 'fx_conversion',
            'label': f'FX Conversion: {fx.tx_type.value}',
            'description': f'{fx.amount} {fx.currency} - {fx.status.value}',
            'icon': 'fa-exchange-alt',
            'color': 'cyan'
        })

    # 9. Payout requests
    for payout in payout_requests:
        timeline.append({
            'timestamp': payout.created_at.isoformat() if payout.created_at else None,
            'type': 'payout',
            'label': f'Payout Request: {payout.status}',
            'description': f'{payout.amount} {payout.currency} via {payout.payment_method}',
            'icon': 'fa-money-bill-wave',
            'color': 'green'
        })

    # 10. Adjustments
    for adj in adjustments:
        timeline.append({
            'timestamp': adj.created_at.isoformat() if adj.created_at else None,
            'type': 'adjustment',
            'label': f'Adjustment: {adj.tx_type.value}',
            'description': f'{adj.amount} {adj.currency} - {adj.status.value}',
            'icon': 'fa-wrench',
            'color': 'orange'
        })

    # Sort timeline by timestamp (oldest first)
    timeline.sort(key=lambda x: x['timestamp'] or '')

    context = {
        'user': user,
        'profile': profile,
        'account': account,
        'recent_transactions': recent_transactions,
        'all_transactions': all_transactions,
        'total_deposits': total_deposits,
        'total_withdrawals': total_withdrawals,
        'total_transfers_sent': total_transfers_sent,
        'total_transfers_received': total_transfers_received,
        'active_sessions': active_sessions,
        'kyc_info': kyc_info,
        'user_roles': user.role_names if hasattr(user, 'role_names') else [],
        'is_frozen': account.is_frozen if account else False,
        'frozen_reason': account.frozen_reason if account else None,
        'account_status': 'active' if account and account.verified else 'pending_activation' if account else 'no_wallet',
        'has_access': _has_financial_access(current_user),
        'security_events': security_events,
        'timeline': timeline,
        'account_created_at': account.created_at if account else None,
        'account_activated_at': account.terms_accepted_at if account and account.verified else None,
        'profile_created_at': profile.created_at if profile else None,
        'user_created_at': user.created_at,
        'fx_conversions': fx_conversions,
        'payout_requests': payout_requests,
        'adjustments': adjustments,
        'total_transactions': len(all_transactions),
        'total_fx_conversions': len(fx_conversions),
        'total_payouts': len(payout_requests),
        'total_adjustments': len(adjustments),
        'creation_events': creation_events
    }

    return render_template('wallet/financial/account_detail.html', **context)


@wallet_bp.route('/financial/account/<public_id>/freeze', methods=['POST'])
@login_required
def financial_freeze_account(public_id):
    """
    Freeze a user's wallet account (Owner, Super Admin, Admin, Wallet Admin only).
    """
    from app.identity.models.user import User
    from app.wallet.models.ledger import AccountModel
    from app.extensions import db
    from datetime import datetime, timezone

    # Authorisation check (only high-level financial roles)
    if not current_user.is_app_owner() and not any(role in current_user.role_names for role in ['super_admin', 'admin', 'wallet_admin']):
        flash('You do not have permission to freeze accounts.', 'danger')
        return redirect(url_for('wallet.financial_account_lookup'))

    user = User.query.filter_by(public_id=public_id, is_deleted=False).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('wallet.financial_account_lookup'))

    account = AccountModel.query.filter_by(user_id=user.id).first()
    if not account:
        flash('User does not have a wallet account.', 'warning')
        return redirect(url_for('wallet.financial_account_detail', public_id=public_id))

    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('Please provide a reason for freezing the account.', 'danger')
        return redirect(url_for('wallet.financial_account_detail', public_id=public_id))

    if account.is_frozen:
        flash('Account is already frozen.', 'warning')
        return redirect(url_for('wallet.financial_account_detail', public_id=public_id))

    account.is_frozen = True
    account.frozen_reason = reason
    account.frozen_at = datetime.now(timezone.utc)
    account.frozen_by = current_user.id
    db.session.commit()

    # Audit log
    from app.audit.comprehensive_audit import AuditService
    AuditService.security(
        event_type="account_frozen",
        severity="WARNING",
        description=f"Account {account.id} frozen by {current_user.username}",
        user_id=current_user.id,
        extra_data={"target_user_id": user.id, "reason": reason}
    )

    flash(f'Account for {user.email} has been frozen.', 'success')
    return redirect(url_for('wallet.financial_account_detail', public_id=public_id))


@wallet_bp.route('/financial/account/<public_id>/unfreeze', methods=['POST'])
@login_required
def financial_unfreeze_account(public_id):
    """
    Unfreeze a user's wallet account (Owner, Super Admin, Admin, Wallet Admin only).
    """
    from app.identity.models.user import User
    from app.wallet.models.ledger import AccountModel
    from app.extensions import db

    # Authorisation check
    if not current_user.is_app_owner() and not any(role in current_user.role_names for role in ['super_admin', 'admin', 'wallet_admin']):
        flash('You do not have permission to unfreeze accounts.', 'danger')
        return redirect(url_for('wallet.financial_account_lookup'))

    user = User.query.filter_by(public_id=public_id, is_deleted=False).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('wallet.financial_account_lookup'))

    account = AccountModel.query.filter_by(user_id=user.id).first()
    if not account:
        flash('User does not have a wallet account.', 'warning')
        return redirect(url_for('wallet.financial_account_detail', public_id=public_id))

    if not account.is_frozen:
        flash('Account is not frozen.', 'warning')
        return redirect(url_for('wallet.financial_account_detail', public_id=public_id))

    account.is_frozen = False
    account.frozen_reason = None
    account.frozen_at = None
    account.frozen_by = None
    db.session.commit()

    from app.audit.comprehensive_audit import AuditService
    AuditService.security(
        event_type="account_unfrozen",
        severity="INFO",
        description=f"Account {account.id} unfrozen by {current_user.username}",
        user_id=current_user.id,
        extra_data={"target_user_id": user.id}
    )

    flash(f'Account for {user.email} has been unfrozen.', 'success')
    return redirect(url_for('wallet.financial_account_detail', public_id=public_id))
