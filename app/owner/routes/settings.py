# app/owner/routes/settings.py
"""
Owner Settings Routes

Provides organized settings pages for:
- Wallet configuration
- Payment gateway management
- Aggregator settings
- Compliance configuration
- Role delegation management
"""

from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, flash
from functools import wraps
from flask_login import login_required, current_user
from app.extensions import db
from datetime import datetime, timezone

from app.auth.delegation import DelegationService, DelegationScope
from app.audit.comprehensive_audit import AuditService


owner_settings = Blueprint('owner_settings', __name__, url_prefix='/settings')


def require_owner_role(f):
    """Decorator to require owner role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask_login import current_user
        from flask import jsonify, redirect, url_for, flash

        is_owner = False

        if hasattr(current_user, 'has_role'):
            try:
                is_owner = current_user.has_role('owner')
            except Exception:
                pass

        if not is_owner and hasattr(current_user, 'roles'):
            try:
                for ur in current_user.roles:
                    if ur.role and ur.role.name == 'owner':
                        is_owner = True
                        break
            except Exception:
                pass

        if not is_owner:
            return jsonify({
                'success': False,
                'error': 'Owner access required',
                'error_code': 'INSUFFICIENT_PERMISSIONS'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


def inject_media_stats():
    from app.media.models import Media
    from flask import g
    stats = {
        'total_processing_attempts': db.session.query(func.sum(Media.processing_attempts)).scalar() or 0,
        'total_notified': db.session.query(Media.query.notified).count() or 0,
        'total_media': Media.query.count()
    }
    g.media_stats = stats


@owner_settings.route('/wallet')
@require_owner_role
def wallet_settings():
    """Wallet settings page"""
    from app.wallet.models.config import WalletSystemConfig
    
    wallet_config = WalletSystemConfig.get_config()
    
    # Get current wallet configuration
    config = {
        'paypal': {
            'client_id': current_app.config.get('PAYPAL_CLIENT_ID', ''),
            'environment': current_app.config.get('PAYPAL_ENVIRONMENT', 'sandbox')
        },
        'alipay': {
            'app_id': current_app.config.get('ALIPAY_APP_ID', ''),
            'environment': current_app.config.get('ALIPAY_ENVIRONMENT', 'sandbox')
        },
        'flutterwave': {
            'public_key': current_app.config.get('FLUTTERWAVE_PUBLIC_KEY', ''),
            'environment': current_app.config.get('FLUTTERWAVE_ENVIRONMENT', 'sandbox')
        },
        'paystack': {
            'public_key': current_app.config.get('PAYSTACK_PUBLIC_KEY', ''),
            'environment': current_app.config.get('PAYSTACK_ENVIRONMENT', 'sandbox')
        },
        'mobile_money': {
            'mtn_ug_api_key': current_app.config.get('MTN_UG_API_KEY', ''),
            'airtel_ug_api_key': current_app.config.get('AIRTEL_UG_API_KEY', ''),
            'mpesa_api_key': current_app.config.get('MPESA_API_KEY', '')
        },
        'visa': {
            'merchant_id': current_app.config.get('VISA_MERCHANT_ID', ''),
            'environment': current_app.config.get('VISA_ENVIRONMENT', 'sandbox')
        },
        'wechat': {
            'app_id': current_app.config.get('WECHAT_APP_ID', ''),
            'environment': current_app.config.get('WECHAT_ENVIRONMENT', 'sandbox')
        },
        'wallet': {
            'max_deposit_amount': float(wallet_config.max_deposit_amount),
            'max_withdrawal_amount': float(wallet_config.max_withdrawal_amount),
            'max_transfer_amount': float(wallet_config.max_transfer_amount),
            'max_daily_amount': float(wallet_config.max_daily_amount) if wallet_config.max_daily_amount is not None else 5000000,
            'max_monthly_amount': float(wallet_config.max_monthly_amount) if wallet_config.max_monthly_amount is not None else 50000000,
            'require_kyc_for_deposits': wallet_config.require_kyc_for_deposits,
            'require_kyc_for_withdrawals': wallet_config.require_kyc_for_withdrawals,
            'require_kyc_for_transfers': wallet_config.require_kyc_for_transfers,
            'deposits_enabled': wallet_config.deposits_enabled,
            'withdrawals_enabled': wallet_config.withdrawals_enabled,
            'transfers_enabled': wallet_config.transfers_enabled,
            'fx_enabled': wallet_config.fx_enabled,
        },
        'fees': {
            'paypal_fee': current_app.config.get('PAYPAL_FEE', 2.9),
            'paypal_fixed_fee': current_app.config.get('PAYPAL_FIXED_FEE', 0.30),
            'alipay_fee': current_app.config.get('ALIPAY_FEE', 0.6),
            'flutterwave_fee': current_app.config.get('FLUTTERWAVE_FEE', 1.4),
            'paystack_fee': current_app.config.get('PAYSTACK_FEE', 1.5),
            'mobile_money_fee': current_app.config.get('MOBILE_MONEY_FEE', 1.0),
            'deposit_fee_percent': float(wallet_config.deposit_fee_percent),
            'withdrawal_fee_percent': float(wallet_config.withdrawal_fee_percent),
            'transfer_fee_percent': float(wallet_config.transfer_fee_percent),
            'fx_spread_percent': float(wallet_config.fx_spread_percent),
        },
        'security': {
            'pin_threshold': current_app.config.get('WALLET_PIN_THRESHOLD', 100000),
            'max_failed_attempts': current_app.config.get('WALLET_MAX_FAILED_ATTEMPTS', 3),
            'lockout_duration': current_app.config.get('WALLET_LOCKOUT_DURATION', 30)
        },
        'delegation': {
            'max_duration': current_app.config.get('DELEGATION_MAX_DURATION', 168)
        }
    }
    
    return render_template('owner/wallet_settings.html', config=config)


@owner_settings.route('/aggregators')
@require_owner_role
def aggregator_settings():
    """Aggregator settings page"""
    config = {
        'aggregators': {
            'flutterwave': {
                'aggregator_id': current_app.config.get('FLUTTERWAVE_AGGREGATOR_ID', ''),
                'secret_key': current_app.config.get('FLUTTERWAVE_SECRET_KEY', ''),
                'webhook_url': current_app.config.get('FLUTTERWAVE_WEBHOOK_URL', '')
            },
            'paystack': {
                'aggregator_id': current_app.config.get('PAYSTACK_AGGREGATOR_ID', ''),
                'secret_key': current_app.config.get('PAYSTACK_SECRET_KEY', ''),
                'webhook_url': current_app.config.get('PAYSTACK_WEBHOOK_URL', '')
            },
            'stripe': {
                'aggregator_id': current_app.config.get('STRIPE_AGGREGATOR_ID', ''),
                'secret_key': current_app.config.get('STRIPE_SECRET_KEY', ''),
                'webhook_url': current_app.config.get('STRIPE_WEBHOOK_URL', '')
            },
            'adyen': {
                'aggregator_id': current_app.config.get('ADYEN_AGGREGATOR_ID', ''),
                'secret_key': current_app.config.get('ADYEN_SECRET_KEY', ''),
                'webhook_url': current_app.config.get('ADYEN_WEBHOOK_URL', '')
            }
        },
        'webhooks': {
            'default_url': current_app.config.get('DEFAULT_WEBHOOK_URL', ''),
            'secret': current_app.config.get('WEBHOOK_SECRET', ''),
            'retry_attempts': current_app.config.get('WEBHOOK_RETRY_ATTEMPTS', 3),
            'retry_delay': current_app.config.get('WEBHOOK_RETRY_DELAY', 30)
        },
        'api': {
            'rate_limit': current_app.config.get('API_RATE_LIMIT', 1000),
            'timeout': current_app.config.get('API_TIMEOUT', 30),
            'allowed_ips': current_app.config.get('API_ALLOWED_IPS', '')
        }
    }
    
    return render_template('owner/aggregator_settings.html', config=config)


@owner_settings.route('/compliance')
@require_owner_role
def compliance_settings():
    """Compliance settings page"""
    config = {
        'aml': {
            'enabled': current_app.config.get('AML_ENABLED', True),
            'threshold': current_app.config.get('AML_THRESHOLD', 1000000),
            'auto_flag': current_app.config.get('AML_AUTO_FLAG', True)
        },
        'kyc': {
            'enabled': current_app.config.get('KYC_ENABLED', True),
            'required_level': current_app.config.get('KYC_REQUIRED_LEVEL', 2),
            'auto_verify': current_app.config.get('KYC_AUTO_VERIFY', False)
        },
        'regulator': {
            'access_enabled': current_app.config.get('REGULATOR_ACCESS_ENABLED', True),
            'default_duration': current_app.config.get('REGULATOR_DEFAULT_DURATION', 24),
            'max_accesses': current_app.config.get('REGULATOR_MAX_ACCESSES', 10)
        },
        'audit': {
            'retention_days': current_app.config.get('AUDIT_RETENTION_DAYS', 2555),  # 7 years
            'log_level': current_app.config.get('AUDIT_LOG_LEVEL', 'INFO'),
            'auto_cleanup': current_app.config.get('AUDIT_AUTO_CLEANUP', True)
        }
    }
    
    return render_template('owner/compliance_settings.html', config=config)


@owner_settings.route('/delegation')
@require_owner_role
def delegation_settings():
    """Delegation settings page"""
    delegation_service = DelegationService()
    
    config = {
        'rules': delegation_service.get_delegation_rules(),
        'active_delegations': delegation_service.get_active_delegations(),
        'settings': {
            'delegation_enabled': current_app.config.get('DELEGATION_ENABLED', True),
            'admin_delegation_approval': current_app.config.get('ADMIN_DELEGATION_APPROVAL', True),
            'max_delegation_duration': current_app.config.get('MAX_DELEGATION_DURATION', 168),
            'auto_expire_delegations': current_app.config.get('AUTO_EXPIRE_DELEGATIONS', True)
        }
    }
    
    return render_template('owner/delegation_settings.html', config=config)


# API endpoints for saving settings

@owner_settings.route('/wallet/update-gateway-status', methods=['POST'])
@require_owner_role
def update_gateway_status():
    """Update payment gateway status"""
    try:
        data = request.get_json()
        gateway = data.get('gateway')
        active = data.get('active')
        
        if not gateway:
            return jsonify({
                'success': False,
                'error': 'Gateway name required'
            })
        
        # Update gateway status in config
        config_key = f"{gateway.upper()}_ENABLED"
        current_app.config[config_key] = active
        
        # Log the change
        AuditService.compliance(
            action="gateway_status_updated",
            gateway=gateway,
            new_status=active,
            metadata={
                "updated_by": getattr(request, 'user_id', 1),
                "ip_address": request.remote_addr
            }
        )
        
        return jsonify({
            'success': True,
            'message': f'{gateway} status updated successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Update gateway status error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to update gateway status'
        })


@owner_settings.route('/wallet/save-payment-gateways', methods=['POST'])
@require_owner_role
def save_payment_gateways():
    """Save payment gateway configurations"""
    try:
        data = request.get_json()
        
        # Update PayPal settings
        if 'paypal' in data:
            current_app.config['PAYPAL_CLIENT_ID'] = data['paypal'].get('client_id', '')
            current_app.config['PAYPAL_ENVIRONMENT'] = data['paypal'].get('environment', 'sandbox')
        
        # Update Alipay settings
        if 'alipay' in data:
            current_app.config['ALIPAY_APP_ID'] = data['alipay'].get('app_id', '')
            current_app.config['ALIPAY_ENVIRONMENT'] = data['alipay'].get('environment', 'sandbox')
        
        # Update Flutterwave settings
        if 'flutterwave' in data:
            current_app.config['FLUTTERWAVE_PUBLIC_KEY'] = data['flutterwave'].get('public_key', '')
            current_app.config['FLUTTERWAVE_ENVIRONMENT'] = data['flutterwave'].get('environment', 'sandbox')
        
        # Update Paystack settings
        if 'paystack' in data:
            current_app.config['PAYSTACK_PUBLIC_KEY'] = data['paystack'].get('public_key', '')
            current_app.config['PAYSTACK_ENVIRONMENT'] = data['paystack'].get('environment', 'sandbox')
        
        # Update Mobile Money settings
        if 'mobile_money' in data:
            current_app.config['MTN_UG_API_KEY'] = data['mobile_money'].get('mtn_ug_api_key', '')
            current_app.config['AIRTEL_UG_API_KEY'] = data['mobile_money'].get('airtel_ug_api_key', '')
            current_app.config['MPESA_API_KEY'] = data['mobile_money'].get('mpesa_api_key', '')
        
        # Update Visa settings
        if 'visa' in data:
            current_app.config['VISA_MERCHANT_ID'] = data['visa'].get('merchant_id', '')
            current_app.config['VISA_ENVIRONMENT'] = data['visa'].get('environment', 'sandbox')
        
        # Update WeChat settings
        if 'wechat' in data:
            current_app.config['WECHAT_APP_ID'] = data['wechat'].get('app_id', '')
            current_app.config['WECHAT_ENVIRONMENT'] = data['wechat'].get('environment', 'sandbox')
        
        # Log the changes
        AuditService.compliance(
            action="payment_gateways_updated",
            gateways=list(data.keys()),
            metadata={
                "updated_by": getattr(request, 'user_id', 1),
                "ip_address": request.remote_addr
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'Payment gateway settings saved successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Save payment gateways error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to save payment gateway settings'
        })


@owner_settings.route('/wallet/save-limits', methods=['POST'])
@require_owner_role
def save_wallet_limits():
    """Save wallet transaction limits"""
    from app.wallet.models.config import WalletSystemConfig
    
    try:
        data = request.get_json()
        
        wallet_config = WalletSystemConfig.get_config()
        
        # Update transaction limits (per-action operational ceilings)
        if 'max_deposit_amount' in data:
            wallet_config.max_deposit_amount = float(data.get('max_deposit_amount', 1000000))
        if 'max_withdrawal_amount' in data:
            wallet_config.max_withdrawal_amount = float(data.get('max_withdrawal_amount', 500000))
        if 'max_transfer_amount' in data:
            wallet_config.max_transfer_amount = float(data.get('max_transfer_amount', 1000000))
        
        # Update operational cumulative ceilings
        if 'max_daily_amount' in data:
            wallet_config.max_daily_amount = float(data.get('max_daily_amount', 5000000))
        if 'max_monthly_amount' in data:
            wallet_config.max_monthly_amount = float(data.get('max_monthly_amount', 50000000))
        
        # Update KYC requirements
        if 'require_kyc_for_deposits' in data:
            wallet_config.require_kyc_for_deposits = bool(data.get('require_kyc_for_deposits', False))
        if 'require_kyc_for_withdrawals' in data:
            wallet_config.require_kyc_for_withdrawals = bool(data.get('require_kyc_for_withdrawals', True))
        if 'require_kyc_for_transfers' in data:
            wallet_config.require_kyc_for_transfers = bool(data.get('require_kyc_for_transfers', False))
        
        # Update feature flags
        if 'deposits_enabled' in data:
            wallet_config.deposits_enabled = bool(data.get('deposits_enabled', True))
        if 'withdrawals_enabled' in data:
            wallet_config.withdrawals_enabled = bool(data.get('withdrawals_enabled', True))
        if 'transfers_enabled' in data:
            wallet_config.transfers_enabled = bool(data.get('transfers_enabled', True))
        if 'fx_enabled' in data:
            wallet_config.fx_enabled = bool(data.get('fx_enabled', True))
        
        wallet_config.updated_at = datetime.now(timezone.utc)
        wallet_config.updated_by = getattr(current_user, 'id', 1)
        
        db.session.commit()
        
        # Log the changes
        AuditService.compliance(
            action="wallet_limits_updated",
            limits=data,
            metadata={
                "updated_by": getattr(current_user, 'id', 1),
                "ip_address": request.remote_addr
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'Wallet limits saved successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Save wallet limits error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to save wallet limits'
        })


@owner_settings.route('/wallet/save-fees', methods=['POST'])
@require_owner_role
def save_transaction_fees():
    """Save transaction fee structure"""
    try:
        data = request.get_json()
        
        current_app.config['PAYPAL_FEE'] = data.get('paypal_fee', 2.9)
        current_app.config['PAYPAL_FIXED_FEE'] = data.get('paypal_fixed_fee', 0.30)
        current_app.config['ALIPAY_FEE'] = data.get('alipay_fee', 0.6)
        current_app.config['FLUTTERWAVE_FEE'] = data.get('flutterwave_fee', 1.4)
        current_app.config['PAYSTACK_FEE'] = data.get('paystack_fee', 1.5)
        current_app.config['MOBILE_MONEY_FEE'] = data.get('mobile_money_fee', 1.0)
        
        # Log the changes
        AuditService.compliance(
            action="transaction_fees_updated",
            fees=data,
            metadata={
                "updated_by": getattr(request, 'user_id', 1),
                "ip_address": request.remote_addr
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'Transaction fees saved successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Save transaction fees error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to save transaction fees'
        })


@owner_settings.route('/wallet/save-security', methods=['POST'])
@require_owner_role
def save_wallet_security():
    """Save wallet security settings"""
    try:
        data = request.get_json()
        
        current_app.config['WALLET_2FA'] = data.get('wallet_2fa', True)
        current_app.config['WALLET_PIN_THRESHOLD'] = data.get('pin_threshold', 100000)
        current_app.config['WALLET_MAX_FAILED_ATTEMPTS'] = data.get('max_failed_attempts', 3)
        current_app.config['WALLET_LOCKOUT_DURATION'] = data.get('lockout_duration', 30)
        
        # Log the changes
        AuditService.compliance(
            action="wallet_security_updated",
            security=data,
            metadata={
                "updated_by": getattr(request, 'user_id', 1),
                "ip_address": request.remote_addr
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'Wallet security settings saved successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Save wallet security error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to save wallet security settings'
        })


@owner_settings.route('/wallet/save-delegation', methods=['POST'])
@require_owner_role
def save_delegation_settings():
    """Save delegation settings"""
    try:
        data = request.get_json()
        
        current_app.config['DELEGATION_ENABLED'] = data.get('delegation_enabled', True)
        current_app.config['ADMIN_DELEGATION_APPROVAL'] = data.get('admin_delegation_approval', True)
        current_app.config['MAX_DELEGATION_DURATION'] = data.get('max_delegation_duration', 168)
        current_app.config['AUTO_EXPIRE_DELEGATIONS'] = data.get('auto_expire_delegations', True)
        
        # Log the changes
        AuditService.compliance(
            action="delegation_settings_updated",
            settings=data,
            metadata={
                "updated_by": getattr(request, 'user_id', 1),
                "ip_address": request.remote_addr
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'Delegation settings saved successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Save delegation settings error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to save delegation settings'
        })


@owner_settings.route('/aggregator/save-aggregators', methods=['POST'])
@require_owner_role
def save_aggregators():
    """Save aggregator configurations"""
    try:
        data = request.get_json()
        
        # Update aggregator settings
        for aggregator, config in data.items():
            if aggregator == 'flutterwave':
                current_app.config['FLUTTERWAVE_AGGREGATOR_ID'] = config.get('aggregator_id', '')
                current_app.config['FLUTTERWAVE_SECRET_KEY'] = config.get('secret_key', '')
                current_app.config['FLUTTERWAVE_WEBHOOK_URL'] = config.get('webhook_url', '')
            elif aggregator == 'paystack':
                current_app.config['PAYSTACK_AGGREGATOR_ID'] = config.get('aggregator_id', '')
                current_app.config['PAYSTACK_SECRET_KEY'] = config.get('secret_key', '')
                current_app.config['PAYSTACK_WEBHOOK_URL'] = config.get('webhook_url', '')
            elif aggregator == 'stripe':
                current_app.config['STRIPE_AGGREGATOR_ID'] = config.get('aggregator_id', '')
                current_app.config['STRIPE_SECRET_KEY'] = config.get('secret_key', '')
                current_app.config['STRIPE_WEBHOOK_URL'] = config.get('webhook_url', '')
            elif aggregator == 'adyen':
                current_app.config['ADYEN_AGGREGATOR_ID'] = config.get('aggregator_id', '')
                current_app.config['ADYEN_SECRET_KEY'] = config.get('secret_key', '')
                current_app.config['ADYEN_WEBHOOK_URL'] = config.get('webhook_url', '')
        
        # Log the changes
        AuditService.compliance(
            action="aggregators_updated",
            aggregators=list(data.keys()),
            metadata={
                "updated_by": getattr(request, 'user_id', 1),
                "ip_address": request.remote_addr
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'Aggregator settings saved successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Save aggregators error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to save aggregator settings'
        })


@owner_settings.route('/aggregator/save-webhook', methods=['POST'])
@require_owner_role
def save_webhook_config():
    """Save webhook configuration"""
    try:
        data = request.get_json()
        
        current_app.config['DEFAULT_WEBHOOK_URL'] = data.get('default_url', '')
        current_app.config['WEBHOOK_SECRET'] = data.get('secret', '')
        current_app.config['WEBHOOK_RETRY_ATTEMPTS'] = data.get('retry_attempts', 3)
        current_app.config['WEBHOOK_RETRY_DELAY'] = data.get('retry_delay', 30)
        current_app.config['WEBHOOK_LOGGING_ENABLED'] = data.get('logging_enabled', True)
        
        # Log the changes
        AuditService.compliance(
            action="webhook_config_updated",
            config=data,
            metadata={
                "updated_by": getattr(request, 'user_id', 1),
                "ip_address": request.remote_addr
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'Webhook configuration saved successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Save webhook config error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to save webhook configuration'
        })


@owner_settings.route('/aggregator/save-api', methods=['POST'])
@require_owner_role
def save_api_access():
    """Save API access settings"""
    try:
        data = request.get_json()
        
        current_app.config['API_RATE_LIMIT'] = data.get('rate_limit', 1000)
        current_app.config['API_TIMEOUT'] = data.get('timeout', 30)
        current_app.config['API_LOGGING_ENABLED'] = data.get('logging_enabled', True)
        current_app.config['API_IP_WHITELIST_ENABLED'] = data.get('ip_whitelist_enabled', False)
        current_app.config['API_ALLOWED_IPS'] = data.get('allowed_ips', '')
        
        # Log the changes
        AuditService.compliance(
            action="api_access_updated",
            config=data,
            metadata={
                "updated_by": getattr(request, 'user_id', 1),
                "ip_address": request.remote_addr
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'API access settings saved successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Save API access error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to save API access settings'
        })


# ============================================================
# PAYMENT METHOD MANAGEMENT (Owner Only)
# ============================================================

@owner_settings.route('/payment-methods', methods=['GET'])
@require_owner_role
def owner_payment_methods():
    """List all payment methods for owner management"""
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig
        
        methods = PaymentMethodConfig.query.order_by(PaymentMethodConfig.id).all()
        
        method_data = []
        for method in methods:
            method_data.append({
                'id': method.id,
                'method_id': method.method_id,
                'display_name': method.display_name,
                'method_type': method.method_type,
                'provider_name': method.provider_name,
                'country_code': method.country_code,
                'is_enabled': method.is_enabled,
                'is_active': method.is_active,
                'requires_phone': method.requires_phone,
                'supported_currencies': method.supported_currencies,
                'min_amount': float(method.min_amount),
                'max_amount': float(method.max_amount),
                'transaction_fee': float(method.transaction_fee),
                'icon': _get_method_icon(method.method_type)
            })
        
        return jsonify({
            'success': True,
            'payment_methods': method_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting payment methods: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@owner_settings.route('/payment-methods/<int:method_id>/toggle', methods=['POST'])
@require_owner_role
def owner_toggle_payment_method(method_id):
    """Toggle payment method enabled/disabled status"""
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig
        
        method = PaymentMethodConfig.query.get_or_404(method_id)
        data = request.get_json()
        
        enable = data.get('enabled', False)
        method.is_enabled = enable
        method.updated_by = getattr(current_user, 'id', 1)
        
        db.session.commit()
        
        action = "enabled" if enable else "disabled"
        return jsonify({'success': True, 'message': f'Payment method {action} successfully'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling payment method {method_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@owner_settings.route('/cash-settings', methods=['GET', 'POST'])
@require_owner_role
def owner_cash_settings():
    """Global cash payment configuration page"""
    from app.models.system_config import SystemConfig

    if request.method == 'POST':
        try:
            SystemConfig.set('payment_cash_globally_enabled', request.form.get('cash_globally_enabled') == 'on', value_type='bool', category='payments')
            SystemConfig.set('payment_cash_development_mode', request.form.get('cash_development_mode') == 'on', value_type='bool', category='payments')
            SystemConfig.set('payment_cash_requires_kyc', request.form.get('cash_requires_kyc') == 'on', value_type='bool', category='payments')
            kyc_level = request.form.get('cash_min_kyc_level', '2')
            SystemConfig.set('payment_cash_min_kyc_level', int(kyc_level) if kyc_level else 2, value_type='int', category='payments')
            SystemConfig.set('payment_cash_requires_verified_phone', request.form.get('cash_requires_verified_phone') == 'on', value_type='bool', category='payments')
            SystemConfig.set('payment_cash_requires_verified_email', request.form.get('cash_requires_verified_email') == 'on', value_type='bool', category='payments')
            SystemConfig.set('payment_cash_requires_previous_booking', request.form.get('cash_requires_previous_booking') == 'on', value_type='bool', category='payments')
            max_amount = request.form.get('cash_max_amount', '500000')
            SystemConfig.set('payment_cash_max_amount', int(max_amount) if max_amount else 500000, value_type='int', category='payments')
            deposit_pct = request.form.get('cash_default_deposit_pct', '30')
            SystemConfig.set('payment_cash_default_deposit_pct', int(deposit_pct) if deposit_pct else 30, value_type='int', category='payments')

            flash('Cash payment settings updated successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error saving cash settings: {e}")
            flash(f'Error saving settings: {str(e)}', 'danger')
        return redirect(url_for('admin.owner.owner_settings.owner_cash_settings'))

    settings = {
        'cash_globally_enabled': SystemConfig.get('payment_cash_globally_enabled', True),
        'cash_development_mode': SystemConfig.get('payment_cash_development_mode', True),
        'cash_requires_kyc': SystemConfig.get('payment_cash_requires_kyc', True),
        'cash_min_kyc_level': SystemConfig.get('payment_cash_min_kyc_level', 2),
        'cash_requires_verified_phone': SystemConfig.get('payment_cash_requires_verified_phone', True),
        'cash_requires_verified_email': SystemConfig.get('payment_cash_requires_verified_email', True),
        'cash_requires_previous_booking': SystemConfig.get('payment_cash_requires_previous_booking', True),
        'cash_max_amount': SystemConfig.get('payment_cash_max_amount', 500000),
        'cash_default_deposit_pct': SystemConfig.get('payment_cash_default_deposit_pct', 30),
    }
    return render_template('owner/cash_settings.html', settings=settings)


def _get_method_icon(method_type):
    """Get appropriate icon for payment method type"""
    icon_map = {
        "wallet": "💳",
        "mobile_money": "📱",
        "card": "💳",
        "cash": "💵",
        "bank_transfer": "🏦"
    }
    return icon_map.get(method_type, "💳")
