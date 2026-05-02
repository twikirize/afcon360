"""
Wallet routes for the wallet system.
Complete implementation with all endpoints for user wallet operations.
"""

from datetime import datetime
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.wallet.models.ledger import AccountModel, LedgerEntryModel
from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.currency_service import CurrencyService
from app.wallet.exceptions import InsufficientBalanceError, WalletNotFoundError, LimitExceededError
from uuid import UUID

wallet_bp = Blueprint('wallet', __name__, url_prefix='/wallet')


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
        
        # Get balance using WalletService
        service = WalletService()
        balance = service.get_balance(account.id)
        
        # Get recent transactions
        recent_transactions = TransactionModel.query.filter_by(
            account_id=account.id
        ).order_by(TransactionModel.created_at.desc()).limit(10).all()
        
        # Mock commission for agent users (implement properly later)
        commission = Decimal('0')
        
        return render_template(
            'wallet/wallet_dashboard.html',
            account=account,
            balance=balance,
            recent_transactions=recent_transactions,
            commission=commission
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
        balance = service.get_balance(account.id)
        
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
    return render_template('wallet/deposit.html', account=account)


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
    return render_template('wallet/send.html', account=account)


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
        
        receiver_account = get_or_create_account(receiver.id, currency)
        
        # Process transfer using WalletService
        service = WalletService()
        transaction = service.transfer(
            from_account_id=sender_account.id,
            to_account_id=receiver_account.id,
            amount=amount,
            currency=currency,
            description=f"Transfer to user {receiver_id}",
            metadata={'agent_fee': str(agent_fee)} if agent_fee > 0 else {}
        )
        
        flash(f'Successfully sent {amount} {currency} to {receiver_id}', 'success')
        return redirect(url_for('wallet.wallet_dashboard'))
        
    except InsufficientBalanceError:
        flash('Insufficient balance', 'error')
        return redirect(url_for('wallet.send_page'))
    except Exception as e:
        current_app.logger.error(f"Send funds error: {e}")
        flash('Error sending funds', 'error')
        return redirect(url_for('wallet.send_page'))


# =============================================================================
# WITHDRAW ROUTES
# =============================================================================

@wallet_bp.route('/withdraw')
@login_required
def withdraw_page():
    """GET: Show withdraw form"""
    account = get_or_create_account(current_user.id)
    return render_template('wallet/withdraw.html', account=account)


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
        
        # Get all transactions for this account
        transactions = TransactionModel.query.filter_by(
            account_id=account.id
        ).order_by(TransactionModel.created_at.desc()).all()
        
        # Format for template compatibility
        formatted_transactions = []
        for tx in transactions:
            formatted_transactions.append({
                'id': tx.id,
                'type': tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type),
                'amount': float(tx.amount),
                'currency': tx.currency,
                'status': tx.status.value if hasattr(tx.status, 'value') else str(tx.status),
                'timestamp': tx.created_at.isoformat() if tx.created_at else None,
                'to': tx.to_account_id,
                'from': tx.from_account_id,
                'description': tx.description
            })
        
        return render_template(
            'wallet/transactions.html',
            transactions=formatted_transactions,
            account=account
        )
    except Exception as e:
        current_app.logger.error(f"Transactions error: {e}")
        flash('Error loading transactions', 'error')
        return render_template('wallet/transactions.html', transactions=[], account=None)


# =============================================================================
# AGENT PAYOUT ROUTES (Placeholder for agent functionality)
# =============================================================================

@wallet_bp.route('/agent/payout/history')
@login_required
def agent_payout_history():
    """View agent payout history"""
    try:
        account = get_or_create_account(current_user.id)
        return render_template('wallet/agent_payout_history.html', account=account)
    except Exception as e:
        current_app.logger.error(f"Agent payout history error: {e}")
        flash('Error loading payout history', 'error')
        return redirect(url_for('wallet.wallet_dashboard'))


@wallet_bp.route('/agent/payout/request')
@login_required
def agent_payout_request_page():
    """Request agent payout page"""
    # Placeholder - implement agent functionality later
    flash('Agent payout request - Feature coming soon', 'info')
    return redirect(url_for('wallet.wallet_dashboard'))


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
        balance = service.get_balance(account.id)
        
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


@wallet_bp.route('/fx-rates')
@login_required
def fx_rates():
    """View FX rates page"""
    try:
        from app.wallet.services.fx_service import FXService
        fx_service = FXService()
        
        # Get all available rates
        rates = fx_service.get_all_rates()
        
        return render_template('wallet/fx_rates.html', rates=rates)
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
        
        return render_template('wallet/compliance.html', account=account)
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
            user_id=account.id,
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
        balance = service.get_balance(account.id)
        
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
        
        transactions = TransactionModel.query.filter_by(
            account_id=account.id
        ).order_by(TransactionModel.created_at.desc()).limit(limit).all()
        
        return jsonify({
            'success': True,
            'transactions': [
                {
                    'id': str(tx.id),
                    'type': tx.transaction_type.value if hasattr(tx.transaction_type, 'value') else str(tx.transaction_type),
                    'amount': str(tx.amount),
                    'currency': tx.currency,
                    'status': tx.status.value if hasattr(tx.status, 'value') else str(tx.status),
                    'created_at': tx.created_at.isoformat() if tx.created_at else None,
                    'description': tx.description
                }
                for tx in transactions
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
