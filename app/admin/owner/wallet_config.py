"""
Owner Dashboard - Wallet Configuration Management
Secure interface for configuring payment providers and wallet settings
"""

from functools import wraps
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timezone

from app.extensions import db
from app.wallet.models.config import PaymentProviderConfig, WalletSystemConfig
from app.wallet.services.payment_gateway import PaymentProvider, get_provider_status

wallet_config_bp = Blueprint('wallet_config', __name__, url_prefix='/owner/wallet-config')


def require_owner(f):
    """Decorator to ensure only owner can access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        
        # Check if user has owner role
        if not hasattr(current_user, 'has_role') or not current_user.has_role('owner'):
            flash('Access denied. Owner privileges required.', 'danger')
            return redirect(url_for('main.index'))
        
        return f(*args, **kwargs)
    return decorated_function


@wallet_config_bp.route('/')
@login_required
@require_owner
def index():
    """Main wallet configuration dashboard"""
    
    # Get all provider configurations
    providers = PaymentProviderConfig.get_all_configs()
    
    # Get system config
    system_config = WalletSystemConfig.get_config()
    
    # Get current provider status from .env
    env_status = get_provider_status()
    
    return render_template(
        'owner/wallet_config/index.html',
        providers=providers,
        system_config=system_config,
        env_status=env_status,
        active_tab='overview'
    )


@wallet_config_bp.route('/providers')
@login_required
@require_owner
def providers():
    """Payment providers configuration page"""
    
    # Initialize defaults if none exist
    PaymentProviderConfig.initialize_defaults()
    
    providers = PaymentProviderConfig.get_all_configs()
    
    return render_template(
        'owner/wallet_config/providers.html',
        providers=providers,
        active_tab='providers'
    )


@wallet_config_bp.route('/providers/<int:config_id>/edit', methods=['GET', 'POST'])
@login_required
@require_owner
def edit_provider(config_id):
    """Edit payment provider configuration"""
    
    config = PaymentProviderConfig.query.get_or_404(config_id)
    
    if request.method == 'POST':
        # Update configuration
        config.display_name = request.form.get('display_name', config.display_name)
        config.is_sandbox = request.form.get('environment') == 'sandbox'
        config.is_active = request.form.get('is_active') == 'on'
        config.is_enabled = request.form.get('is_enabled') == 'on'
        
        # API Keys (only update if provided)
        secret_key = request.form.get('secret_key')
        if secret_key and secret_key != '••••••••••••':
            config.secret_key = secret_key
        
        public_key = request.form.get('public_key')
        if public_key and public_key != '••••••••••••':
            config.public_key = public_key
        
        encryption_key = request.form.get('encryption_key')
        if encryption_key and encryption_key != '••••••••••••':
            config.encryption_key = encryption_key
        
        # Webhook URL
        config.webhook_url = request.form.get('webhook_url')
        
        # Additional config JSON
        try:
            import json
            config_json_str = request.form.get('config_json', '{}')
            config.config_json = json.loads(config_json_str)
        except:
            flash('Invalid JSON in additional configuration', 'danger')
            return redirect(url_for('wallet_config.edit_provider', config_id=config_id))
        
        config.updated_at = datetime.now(timezone.utc)
        config.updated_by = current_user.id
        
        db.session.commit()
        
        flash(f'{config.display_name} configuration updated successfully', 'success')
        
        # Log the action
        current_app.logger.info(
            f"Owner {current_user.id} updated payment provider config: {config.provider_name}"
        )
        
        return redirect(url_for('wallet_config.providers'))
    
    return render_template(
        'owner/wallet_config/edit_provider.html',
        config=config,
        active_tab='providers'
    )


@wallet_config_bp.route('/providers/<int:config_id>/test', methods=['POST'])
@login_required
@require_owner
def test_provider(config_id):
    """Test payment provider connection"""
    
    config = PaymentProviderConfig.query.get_or_404(config_id)
    
    # Test the connection
    success, message = config.test_connection()
    
    config.last_tested_at = datetime.now(timezone.utc)
    config.last_test_result = 'success' if success else 'failed'
    config.last_error_message = None if success else message
    
    db.session.commit()
    
    if success:
        flash(f'{config.display_name} connection test successful!', 'success')
    else:
        flash(f'{config.display_name} connection test failed: {message}', 'danger')
    
    return redirect(url_for('wallet_config.providers'))


@wallet_config_bp.route('/system', methods=['GET', 'POST'])
@login_required
@require_owner
def system_config():
    """Wallet system configuration"""
    
    config = WalletSystemConfig.get_config()
    
    if request.method == 'POST':
        # Update feature flags
        config.deposits_enabled = request.form.get('deposits_enabled') == 'on'
        config.withdrawals_enabled = request.form.get('withdrawals_enabled') == 'on'
        config.transfers_enabled = request.form.get('transfers_enabled') == 'on'
        config.fx_enabled = request.form.get('fx_enabled') == 'on'
        
        # Update limits
        try:
            config.max_deposit_amount = float(request.form.get('max_deposit_amount', 1000000))
            config.max_withdrawal_amount = float(request.form.get('max_withdrawal_amount', 500000))
            config.max_transfer_amount = float(request.form.get('max_transfer_amount', 1000000))
        except ValueError:
            flash('Invalid amount values', 'danger')
            return redirect(url_for('wallet_config.system_config'))
        
        # Update fees
        try:
            config.deposit_fee_percent = float(request.form.get('deposit_fee_percent', 0))
            config.withdrawal_fee_percent = float(request.form.get('withdrawal_fee_percent', 1))
            config.transfer_fee_percent = float(request.form.get('transfer_fee_percent', 0.5))
            config.fx_spread_percent = float(request.form.get('fx_spread_percent', 1.5))
        except ValueError:
            flash('Invalid fee values', 'danger')
            return redirect(url_for('wallet_config.system_config'))
        
        # Update KYC settings
        config.require_kyc_for_deposits = request.form.get('require_kyc_for_deposits') == 'on'
        config.require_kyc_for_withdrawals = request.form.get('require_kyc_for_withdrawals') == 'on'
        config.require_kyc_for_transfers = request.form.get('require_kyc_for_transfers') == 'on'
        
        # Update notification settings
        config.notify_large_transactions = request.form.get('notify_large_transactions') == 'on'
        try:
            config.large_transaction_threshold = float(request.form.get('large_transaction_threshold', 10000))
        except ValueError:
            flash('Invalid threshold value', 'danger')
            return redirect(url_for('wallet_config.system_config'))
        
        config.updated_at = datetime.now(timezone.utc)
        config.updated_by = current_user.id
        
        db.session.commit()
        
        flash('System configuration updated successfully', 'success')
        
        current_app.logger.info(f"Owner {current_user.id} updated wallet system config")
        
        return redirect(url_for('wallet_config.system_config'))
    
    return render_template(
        'owner/wallet_config/system.html',
        config=config,
        active_tab='system'
    )


@wallet_config_bp.route('/env-setup')
@login_required
@require_owner
def env_setup():
    """Show .env setup instructions"""
    
    # Generate .env template
    env_template = generate_env_template()
    
    return render_template(
        'owner/wallet_config/env_setup.html',
        env_template=env_template,
        active_tab='env'
    )


@wallet_config_bp.route('/api/providers', methods=['GET'])
@login_required
@require_owner
def api_get_providers():
    """API endpoint to get provider configurations (JSON)"""
    
    providers = PaymentProviderConfig.get_all_configs()
    return jsonify({
        'success': True,
        'providers': [p.to_dict(include_secrets=False) for p in providers]
    })


@wallet_config_bp.route('/api/providers/<int:config_id>', methods=['PUT'])
@login_required
@require_owner
def api_update_provider(config_id):
    """API endpoint to update provider configuration (JSON)"""
    
    config = PaymentProviderConfig.query.get_or_404(config_id)
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    # Update fields
    if 'display_name' in data:
        config.display_name = data['display_name']
    if 'is_sandbox' in data:
        config.is_sandbox = data['is_sandbox']
    if 'is_active' in data:
        config.is_active = data['is_active']
    if 'is_enabled' in data:
        config.is_enabled = data['is_enabled']
    if 'secret_key' in data and data['secret_key']:
        config.secret_key = data['secret_key']
    if 'public_key' in data and data['public_key']:
        config.public_key = data['public_key']
    if 'webhook_url' in data:
        config.webhook_url = data['webhook_url']
    if 'config_json' in data:
        config.config_json = data['config_json']
    
    config.updated_at = datetime.now(timezone.utc)
    config.updated_by = current_user.id
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'{config.display_name} updated successfully',
        'provider': config.to_dict(include_secrets=False)
    })


@wallet_config_bp.route('/api/system', methods=['GET', 'PUT'])
@login_required
@require_owner
def api_system_config():
    """API endpoint for system configuration"""
    
    config = WalletSystemConfig.get_config()
    
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'config': config.to_dict()
        })
    
    # PUT request - update config
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    # Update fields
    for field in ['deposits_enabled', 'withdrawals_enabled', 'transfers_enabled', 
                  'fx_enabled', 'require_kyc_for_deposits', 'require_kyc_for_withdrawals',
                  'require_kyc_for_transfers', 'notify_large_transactions']:
        if field in data:
            setattr(config, field, data[field])
    
    for field in ['max_deposit_amount', 'max_withdrawal_amount', 'max_transfer_amount',
                  'deposit_fee_percent', 'withdrawal_fee_percent', 'transfer_fee_percent',
                  'fx_spread_percent', 'large_transaction_threshold']:
        if field in data:
            try:
                setattr(config, field, float(data[field]))
            except ValueError:
                return jsonify({'success': False, 'error': f'Invalid value for {field}'}), 400
    
    config.updated_at = datetime.now(timezone.utc)
    config.updated_by = current_user.id
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'System configuration updated',
        'config': config.to_dict()
    })


def generate_env_template():
    """Generate .env file template for payment providers"""
    
    template = """# ============================================
# Payment Provider Configuration
# ============================================

# Flutterwave Configuration
FLUTTERWAVE_SECRET_KEY=your_flutterwave_secret_key_here
FLUTTERWAVE_PUBLIC_KEY=your_flutterwave_public_key_here
FLUTTERWAVE_ENCRYPTION_KEY=your_flutterwave_encryption_key_here
FLUTTERWAVE_SANDBOX=true
FLUTTERWAVE_CALLBACK_URL=https://yourdomain.com/webhooks/flutterwave

# Paystack Configuration
PAYSTACK_SECRET_KEY=your_paystack_secret_key_here
PAYSTACK_PUBLIC_KEY=your_paystack_public_key_here
PAYSTACK_SANDBOX=true
PAYSTACK_CALLBACK_URL=https://yourdomain.com/webhooks/paystack

# MTN Mobile Money Configuration
MTN_MOMO_API_KEY=your_mtn_momo_api_key_here
MTN_MOMO_API_USER=your_api_user_here
MTN_MOMO_API_SECRET=your_api_secret_here
MTN_MOMO_SANDBOX=true
MTN_MOMO_CALLBACK_URL=https://yourdomain.com/webhooks/mtn-momo

# Airtel Money Configuration
AIRTEL_MONEY_API_KEY=your_airtel_money_api_key_here
AIRTEL_MONEY_SANDBOX=true
AIRTEL_MONEY_CALLBACK_URL=https://yourdomain.com/webhooks/airtel-money

# ============================================
# Wallet System Configuration
# ============================================

# Feature Flags
WALLET_DEPOSITS_ENABLED=true
WALLET_WITHDRAWALS_ENABLED=true
WALLET_TRANSFERS_ENABLED=true
WALLET_FX_ENABLED=true

# Transaction Limits (in default currency)
MAX_DEPOSIT_AMOUNT=1000000
MAX_WITHDRAWAL_AMOUNT=500000
MAX_TRANSFER_AMOUNT=1000000

# Fee Settings (percentage)
DEPOSIT_FEE_PERCENT=0
WITHDRAWAL_FEE_PERCENT=1
TRANSFER_FEE_PERCENT=0.5
FX_SPREAD_PERCENT=1.5

# KYC Requirements
REQUIRE_KYC_FOR_DEPOSITS=false
REQUIRE_KYC_FOR_WITHDRAWALS=true
REQUIRE_KYC_FOR_TRANSfers=false

# Compliance Settings
LARGE_TRANSACTION_THRESHOLD=10000
NOTIFY_LARGE_TRANSACTIONS=true

# ============================================
# Security Settings
# ============================================

# Database Encryption Key (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
DB_ENCRYPTION_KEY=your_32_byte_encryption_key_here

# Rate Limiting
RATE_LIMIT_DEPOSIT_PER_MINUTE=10
RATE_LIMIT_WITHDRAWAL_PER_MINUTE=5
RATE_LIMIT_TRANSFER_PER_MINUTE=10
"""
    
    return template


# Register this blueprint in app/__init__.py
def init_wallet_config(app):
    """Initialize wallet config blueprint"""
    app.register_blueprint(wallet_config_bp)
    
    # Initialize default configs
    with app.app_context():
        try:
            PaymentProviderConfig.initialize_defaults()
        except Exception as e:
            app.logger.warning(f"Could not initialize payment provider defaults: {e}")


__all__ = ['wallet_config_bp', 'init_wallet_config']
</CodeContent>
<parameter=EmptyFile>false</parameter>
</function>

<function=write_to_file>
<parameter=TargetFile>C:\Users\ADMIN\Desktop\afcon360_app\templates\owner\wallet_config\index.html
