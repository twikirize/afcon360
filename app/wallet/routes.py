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
from app.wallet.models.ledger import AccountModel, LedgerEntryModel
from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.currency_service import CurrencyService
from app.wallet.exceptions import InsufficientBalanceError, WalletNotFoundError, LimitExceededError
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


def get_or_create_account(user_id, currency='UGX'):
    """Helper to get or create user account.
    
    Args:
        user_id: Can be either internal BIGINT id or public_id (UUID string)
        currency: Currency code (default: UGX)
    """
    # If user_id looks like a UUID (public_id), query to get internal id
    from app.identity.models.user import User
    user = User.query.filter_by(public_id=str(user_id)).first()
    if user:
        internal_id = user.id
    else:
        # Assume it's already the internal ID
        internal_id = user_id
    
    account = AccountModel.query.filter_by(user_id=internal_id).first()
    if not account:
        account = AccountModel(
            user_id=internal_id,
            currency=currency
        )
        db.session.add(account)
        db.session.commit()
    return account


# =============================================================================
# HOME / DASHBOARD ROUTES
# =============================================================================

@wallet_bp.route('/')
@login_required
def home():
    """Wallet home page - redirect to overview/dashboard"""
    return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/home')
@login_required
def wallet_home():
    """Alternative wallet home endpoint"""
    return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/dashboard')
@login_required
def wallet_dashboard():
    """Main wallet dashboard page"""
    try:
        # Get or create account
        account = get_or_create_account(current_user.id)
        
        # Get balance using WalletService (pass user_id, not account.id)
        service = WalletService()
        balance_data = service.get_balance(account.user_id)
        # get_balance returns dict with 'balance' key
        balance = balance_data.get('balance', Decimal('0'))
        
        # Get recent transactions where current user is sender or recipient
        recent_transactions = TransactionModel.query.filter(
            or_(
                TransactionModel.user_id == current_user.id,
                TransactionModel.recipient_user_id == current_user.id
            )
        ).order_by(TransactionModel.created_at.desc()).limit(10).all()
        
        # Calculate transaction usage count using correct fields
        transaction_count = calculate_transaction_usage(current_user.id)
        
        # Mock commission for agent users (implement properly later)
        commission = Decimal('0')
        
        return render_template(
            'wallet/wallet_dashboard.html',
            account=account,
            balance=balance,
            recent_transactions=recent_transactions,
            commission=commission,
            transaction_count=transaction_count
        )
    except Exception as e:
        current_app.logger.error(f"Wallet dashboard error: {e}")
        flash('Error loading wallet dashboard', 'error')
        return render_template('wallet/wallet_dashboard.html', balance=Decimal('0'), recent_transactions=[], commission=Decimal('0'))


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
        current_app.logger.error(f"Wallet overview error: {e}")
        flash('Error loading wallet overview', 'error')
        return render_template('wallet/overview.html')


# =============================================================================
# DEPOSIT ROUTES
# =============================================================================

@wallet_bp.route('/deposit')
@login_required
def deposit_page():
    """GET: Show deposit form"""
    account = get_or_create_account(current_user.id)
    return render_template('wallet/deposit.html', account=account, balance=Decimal('0'))


@wallet_bp.route('/deposit', methods=['POST'])
@login_required
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
        
        # Get account
        account = get_or_create_account(current_user.id, currency)
        
        # Process deposit using WalletService
        service = WalletService()
        transaction = service.deposit(
            account_id=account.id,
            amount=amount,
            currency=currency,
            description=f"Deposit via web",
            metadata={'source': 'web_form'}
        )
        
        flash(f'Deposit of {amount} {currency} initiated successfully!', 'success')
        return redirect(url_for('wallet.wallet_dashboard'))
        
    except LimitExceededError as e:
        flash(f'Deposit limit exceeded: {str(e)}', 'error')
        return redirect(url_for('wallet.deposit_page'))
    except Exception as e:
        current_app.logger.error(f"Deposit error: {e}")
        flash('Error processing deposit', 'error')
        return redirect(url_for('wallet.deposit_page'))


# =============================================================================
# SEND / TRANSFER ROUTES
# =============================================================================

@wallet_bp.route('/send')
@login_required
def send_page():
    """GET: Show send funds form"""
    account = get_or_create_account(current_user.id)
    return render_template('wallet/send.html', account=account, balance=Decimal('0'))


@wallet_bp.route('/send', methods=['POST'])
@login_required
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
        
        # Get sender account
        sender_account = get_or_create_account(current_user.id, currency)
        
        # Get receiver account (by user_id or public_id)
        from app.identity.models.user import User
        receiver = User.query.filter(
            (User.id == receiver_id) | (User.public_id == receiver_id)
        ).first()
        
        if not receiver:
            flash('Receiver not found', 'error')
            return redirect(url_for('wallet.send_page'))
        
        # Ensure receiver has an account
        receiver_account = get_or_create_account(receiver.id, currency)
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
        # Use from_user_id / to_user_id (internal BIGINT ids) and generate a client_request_id
        client_request_id = str(uuid4())
        transaction = service.transfer(
            from_user_id=sender_account.user_id,
            to_user_id=receiver.id,
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
        # Wallet PIN or other wallet errors
        current_app.logger.error(f"Send funds error: {e}")
        flash(str(e), 'error')
        return redirect(url_for('wallet.send_page'))


# =============================================================================
# WITHDRAW ROUTES
# =============================================================================

@wallet_bp.route('/withdraw')
@login_required
def withdraw_page():
    """GET: Show withdraw form"""
    account = get_or_create_account(current_user.id)
    return render_template('wallet/withdraw.html', account=account, balance=Decimal('0'))


@wallet_bp.route('/withdraw', methods=['POST'])
@login_required
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
        
        # Get account
        account = get_or_create_account(current_user.id, currency)
        
        # Process withdrawal using WalletService
        service = WalletService()
        transaction = service.withdraw(
            account_id=account.id,
            amount=amount,
            currency=currency,
            description=f"Withdrawal via {method}",
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
        current_app.logger.error(f"Withdraw error: {e}")
        flash('Error processing withdrawal', 'error')
        return redirect(url_for('wallet.withdraw_page'))


# =============================================================================
# TRANSACTIONS ROUTES
# =============================================================================

@wallet_bp.route('/transactions')
@login_required
def wallet_transactions():
    """View all transactions"""
    try:
        account = get_or_create_account(current_user.id)
        
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
        current_app.logger.error(f"Transactions error: {e}")
        flash('Error loading transactions', 'error')
        return render_template('wallet/transactions.html', transactions=[], account=None, balance=Decimal('0'))


# =============================================================================
# AGENT PAYOUT ROUTES (Placeholder for agent functionality)
# =============================================================================

@wallet_bp.route('/agent/payout/history')
@login_required
def agent_payout_history():
    """View agent payout history"""
    try:
        account = get_or_create_account(current_user.id)
        # Fetch commission summary & payouts
        from app.wallet.services.commission_service import CommissionService
        from app.wallet.services.payout_service import PayoutService

        commission_service = CommissionService()
        payout_service = PayoutService()

        summary = commission_service.get_commission_summary(current_user.id)
        payouts = payout_service.list_requests(current_user.id)

        return render_template('wallet/agent_payout_history.html', account=account, summary=summary, payouts=payouts)
    except Exception as e:
        current_app.logger.error(f"Agent payout history error: {e}")
        flash('Error loading payout history', 'error')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/agent/payout/request', methods=['GET'])
@login_required
def agent_payout_request_page():
    """Show agent payout request form"""
    try:
        account = get_or_create_account(current_user.id)
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
        current_app.logger.error(f"Agent payout request page error: {e}")
        flash('Error loading payout request page', 'error')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/agent/payout/request', methods=['POST'])
@login_required
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
        current_app.logger.error(f"Payout request submission error: {e}")
        flash('Error submitting payout request', 'error')
        return redirect(url_for('wallet.agent_payout_request_page'))


# =============================================================================
# ADDITIONAL WALLET ROUTES
# =============================================================================

@wallet_bp.route('/activate')
@login_required
def wallet_activate():
    """Wallet activation page"""
    try:
        account = get_or_create_account(current_user.id)
        return render_template('wallet/wallet_activate.html', account=account)
    except Exception as e:
        current_app.logger.error(f"Wallet activation error: {e}")
        flash('Error loading wallet activation page', 'error')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/terms')
@login_required
def wallet_terms():
    """Wallet terms and conditions page"""
    return render_template('wallet/wallet_terms.html')


@wallet_bp.route('/activate', methods=['POST'])
@login_required
def wallet_activate_submit():
    """Submit wallet activation"""
    try:
        # Get account
        account = get_or_create_account(current_user.id)
        
        # Accept terms
        accept_terms = request.form.get('accept_terms')
        if not accept_terms:
            flash('You must accept the terms to activate your wallet', 'error')
            return redirect(url_for('wallet.wallet_activate'))
        
        # Activate account (update status if needed)
        flash('Wallet activated successfully!', 'success')
        return redirect(url_for('wallet.wallet_dashboard'))
    except Exception as e:
        current_app.logger.error(f"Wallet activation error: {e}")
        flash('Error activating wallet', 'error')
        return redirect(url_for('wallet.wallet_activate'))


@wallet_bp.route('/settings')
@login_required
def wallet_settings():
    """Wallet settings page"""
    try:
        account = get_or_create_account(current_user.id)
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
        current_app.logger.error(f"Wallet settings error: {e}")
        flash('Error loading wallet settings', 'error')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/settings', methods=['POST'])
@login_required
def wallet_settings_update():
    """Update wallet settings"""
    try:
        account = get_or_create_account(current_user.id)
        
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
        current_app.logger.error(f"Wallet settings update error: {e}")
        flash('Error updating settings', 'error')
        return redirect(url_for('wallet.wallet_settings'))


# -----------------------------------------------------------------------------
# Transaction PIN endpoints
# -----------------------------------------------------------------------------
@wallet_bp.route('/pin', methods=['GET'])
@login_required
def pin_page():
    """Show PIN management page — forward to template if available."""
    try:
        account = get_or_create_account(current_user.id)
        has_pin = bool(getattr(current_user, 'transaction_pin_hash', None))
        return render_template('wallet/pin.html', account=account, has_pin=has_pin)
    except Exception as e:
        current_app.logger.error(f"PIN page error: {e}")
        flash('Error loading PIN page', 'error')
        return redirect(url_for('wallet.wallet_settings'))


@wallet_bp.route('/pin/set', methods=['POST'])
@login_required
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
        current_app.logger.error(f"Set PIN error: {e}")
        flash('Error setting PIN', 'error')
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
        current_app.logger.error(f"FX rates error: {e}")
        flash('Error loading FX rates', 'error')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/compliance')
@login_required
def compliance_status():
    """View compliance status page"""
    try:
        account = get_or_create_account(current_user.id)
        
        return render_template('wallet/compliance.html', account=account, balance=Decimal('0'))
    except Exception as e:
        current_app.logger.error(f"Compliance status error: {e}")
        flash('Error loading compliance status', 'error')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/history')
@login_required
def transaction_history():
    """Detailed transaction history page"""
    try:
        account = get_or_create_account(current_user.id)
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
        current_app.logger.error(f"Transaction history error: {e}")
        flash('Error loading transaction history', 'error')
        return redirect(url_for('wallet.wallet_dashboard'))


# =============================================================================
# API ENDPOINTS (JSON)
# =============================================================================

@wallet_bp.route('/api/balance')
@login_required
def api_balance():
    """API: Get current balance"""
    try:
        account = get_or_create_account(current_user.id)
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
        account = get_or_create_account(current_user.id)
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
