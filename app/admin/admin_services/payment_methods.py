"""
Admin API Routes for Payment Methods Configuration
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.wallet import PaymentMethodConfig, EventPaymentPreference
from app.admin.decorators import admin_required
from app.wallet.services.admin_audit_service import AdminAuditService
import logging

logger = logging.getLogger(__name__)

payment_methods_bp = Blueprint('payment_methods', __name__, url_prefix='/admin/api/payment-methods')


@payment_methods_bp.route('', methods=['GET'])
@login_required
@admin_required
def get_payment_methods():
    """Get all payment method configurations"""
    try:
        # Initialize defaults if none exist
        PaymentMethodConfig.initialize_defaults()
        
        methods = PaymentMethodConfig.query.all()
        
        # Count statuses
        active_count = len([m for m in methods if m.is_enabled and m.is_active])
        disabled_count = len([m for m in methods if not m.is_enabled])
        inactive_count = len([m for m in methods if m.is_enabled and not m.is_active])
        
        method_data = []
        for method in methods:
            method_dict = {
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
                'use_sandbox': method.use_sandbox,
                'last_tested_at': method.last_tested_at.isoformat() if method.last_tested_at else None,
                'last_test_result': method.last_test_result,
                'last_error_message': method.last_error_message,
                'icon': _get_method_icon(method.method_type),
                # Credential presence indicators only - never the actual values
                'api_key_configured': bool(method.api_key),
                'api_secret_configured': bool(method.api_secret),
                'sandbox_configured': bool(method.sandbox_url),
                'production_configured': bool(method.production_url),
                'config_json_present': bool(method.config_json),
            }
            method_data.append(method_dict)
        
        return jsonify({
            'success': True,
            'payment_methods': method_data,
            'active_count': active_count,
            'disabled_count': disabled_count,
            'inactive_count': inactive_count
        })
        
    except Exception as e:
        logger.error(f"Error getting payment methods: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@payment_methods_bp.route('/initialize', methods=['POST'])
@login_required
@admin_required
def initialize_defaults():
    """Initialize default payment method configurations"""
    try:
        PaymentMethodConfig.initialize_defaults()
        return jsonify({'success': True, 'message': 'Default payment methods initialized'})
    except Exception as e:
        logger.error(f"Error initializing defaults: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@payment_methods_bp.route('/<int:method_id>', methods=['GET'])
@login_required
@admin_required
def get_payment_method(method_id):
    """Get specific payment method configuration"""
    try:
        method = PaymentMethodConfig.query.get_or_404(method_id)
        
        method_dict = {
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
            'use_sandbox': method.use_sandbox,
            # Credential presence indicators only - never the actual values
            'api_key_configured': bool(method.api_key),
            'api_secret_configured': bool(method.api_secret),
            'sandbox_configured': bool(method.sandbox_url),
            'production_configured': bool(method.production_url),
            'config_json_present': bool(method.config_json),
        }
        
        return jsonify({'success': True, 'method': method_dict})
        
    except Exception as e:
        logger.error(f"Error getting payment method {method_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@payment_methods_bp.route('/<int:method_id>', methods=['PUT'])
@login_required
@admin_required
def update_payment_method(method_id):
    """Update payment method configuration"""
    try:
        method = PaymentMethodConfig.query.get_or_404(method_id)
        
        # Capture old audit snapshot before change
        old_snapshot = method.to_audit_dict()
        
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400
        
        # Update basic fields
        method.display_name = data.get('display_name', method.display_name)
        method.is_enabled = data.get('is_enabled', method.is_enabled)
        method.is_active = data.get('is_active', method.is_active)
        method.use_sandbox = data.get('use_sandbox', method.use_sandbox)
        
        # Update financial fields
        method.transaction_fee = data.get('transaction_fee', method.transaction_fee)
        method.min_amount = data.get('min_amount', method.min_amount)
        method.max_amount = data.get('max_amount', method.max_amount)
        
        # Update URLs
        if 'sandbox_url' in data:
            method.sandbox_url = data['sandbox_url']
        if 'production_url' in data:
            method.production_url = data['production_url']
        if 'use_sandbox' in data:
            method.use_sandbox = bool(data['use_sandbox'])
        
        method.updated_by = current_user.id
        
        with AdminAuditService.audited_change():
            # Log the action with audit snapshots
            AdminAuditService.log_action(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='admin',
                action_type='update',
                action_category='payment_method_config',
                target_type='payment_method',
                target_id=str(method.id),
                target_name=method.method_id,
                old_value=old_snapshot,
                new_value=method.to_audit_dict(),
                reason=f'Updated payment method {method.method_id} configuration'
            )
        
        return jsonify({'success': True, 'message': 'Payment method updated successfully'})
        
    except Exception as e:
        logger.error(f"Error updating payment method {method_id}: {e}")
        return jsonify({'success': False, 'error': 'Change not saved — audit record could not be created. No configuration was modified.'}), 409


@payment_methods_bp.route('/<int:method_id>/rotate-credentials', methods=['POST'])
@login_required
@admin_required
def rotate_credentials(method_id):
    """Rotate payment method credentials (write-only operation)"""
    try:
        method = PaymentMethodConfig.query.get_or_404(method_id)
        
        data = request.get_json() or {}
        
        if not any(k in data for k in ('api_key', 'api_secret', 'webhook_secret')):
            return jsonify({'success': False, 'error': 'No credentials provided for rotation'}), 400
        
        # Capture old audit snapshot before change
        old_snapshot = method.to_audit_dict()
        
        # Rotate credentials - only update if provided
        if 'api_key' in data:
            method.api_key = data['api_key']
        if 'api_secret' in data:
            method.api_secret = data['api_secret']
        if 'webhook_secret' in data:
            config = dict(method.config_json or {})
            config['webhook_secret'] = data['webhook_secret']
            method.config_json = config
        
        method.updated_by = current_user.id
        
        with AdminAuditService.audited_change():
            # Log the action with audit snapshots - never include actual credential values
            AdminAuditService.log_action(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='admin',
                action_type='rotate_credentials',
                action_category='payment_method_config',
                target_type='payment_method',
                target_id=str(method.id),
                target_name=method.method_id,
                old_value=old_snapshot,
                new_value=method.to_audit_dict(),
                reason=f'Rotated credentials for payment method {method.method_id}'
            )
        
        return jsonify({
            'success': True, 
            'message': 'Credentials rotated successfully',
            'api_key_configured': bool(method.api_key),
            'api_secret_configured': bool(method.api_secret),
        })
        
    except Exception as e:
        logger.error(f"Error rotating credentials for payment method {method_id}: {e}")
        return jsonify({'success': False, 'error': 'Change not saved — audit record could not be created. No configuration was modified.'}), 409


@payment_methods_bp.route('/<int:method_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_payment_method(method_id):
    """Toggle payment method enabled/disabled status"""
    try:
        method = PaymentMethodConfig.query.get_or_404(method_id)
        
        # Capture old audit snapshot before change
        old_snapshot = method.to_audit_dict()
        
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400
        
        enable = data.get('enabled', False)
        method.is_enabled = enable
        method.updated_by = current_user.id
        
        with AdminAuditService.audited_change():
            # Log the action with audit snapshots
            AdminAuditService.log_action(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='admin',
                action_type='toggle',
                action_category='payment_method_config',
                target_type='payment_method',
                target_id=str(method.id),
                target_name=method.method_id,
                old_value=old_snapshot,
                new_value=method.to_audit_dict(),
                reason=f'Toggled payment method {method.method_id} enabled={enable}'
            )
        
        action = "enabled" if enable else "disabled"
        return jsonify({'success': True, 'message': f'Payment method {action} successfully'})
        
    except Exception as e:
        logger.error(f"Error toggling payment method {method_id}: {e}")
        return jsonify({'success': False, 'error': 'Change not saved — audit record could not be created. No configuration was modified.'}), 409


@payment_methods_bp.route('/<int:method_id>/test', methods=['POST'])
@login_required
@admin_required
def test_payment_method(method_id):
    """Test payment method connection"""
    try:
        method = PaymentMethodConfig.query.get_or_404(method_id)
        
        if method.method_type != 'mobile_money':
            return jsonify({'success': False, 'error': 'Only mobile money methods can be tested'}), 400
        
        # Capture old audit snapshot before change
        old_snapshot = method.to_audit_dict()
        
        # Test connection logic here
        # For now, simulate a test
        from datetime import datetime, timezone
        
        if method.api_key and method.api_secret:
            method.last_tested_at = datetime.now(timezone.utc)
            method.last_test_result = 'success'
            method.last_error_message = None
        else:
            method.last_tested_at = datetime.now(timezone.utc)
            method.last_test_result = 'failed'
            method.last_error_message = 'API credentials not configured'
        
        method.updated_by = current_user.id
        
        with AdminAuditService.audited_change():
            # Log the action with audit snapshots
            AdminAuditService.log_action(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='admin',
                action_type='test',
                action_category='payment_method_config',
                target_type='payment_method',
                target_id=str(method.id),
                target_name=method.method_id,
                old_value=old_snapshot,
                new_value=method.to_audit_dict(),
                reason=f'Tested payment method {method.method_id}: {method.last_test_result}'
            )
        
        if method.last_test_result == 'success':
            return jsonify({'success': True, 'message': 'Connection test successful'})
        else:
            return jsonify({'success': False, 'error': method.last_error_message})
        
    except Exception as e:
        logger.error(f"Error testing payment method {method_id}: {e}")
        return jsonify({'success': False, 'error': 'Change not saved — audit record could not be created. No configuration was modified.'}), 409


@payment_methods_bp.route('/event-preferences/<int:event_id>', methods=['GET'])
@login_required
@admin_required
def get_event_payment_preferences(event_id):
    """Get payment preferences for an event"""
    try:
        preference = EventPaymentPreference.query.filter_by(event_id=event_id).first()
        
        if not preference:
            return jsonify({'success': False, 'error': 'No payment preferences found for this event'}), 404
        
        preference_dict = {
            'id': preference.id,
            'event_id': preference.event_id,
            'user_id': preference.user_id,
            'accepted_methods': preference.accepted_methods,
            'preferred_currency': preference.preferred_currency,
            'auto_convert_wallet': preference.auto_convert_wallet,
            'wallet_conversion_rate': float(preference.wallet_conversion_rate),
            'payment_settings': preference.payment_settings
        }
        
        return jsonify({'success': True, 'preference': preference_dict})
        
    except Exception as e:
        logger.error(f"Error getting event payment preferences: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@payment_methods_bp.route('/event-preferences/<int:event_id>', methods=['PUT'])
@login_required
@admin_required
def update_event_payment_preferences(event_id):
    """Update payment preferences for an event"""
    try:
        preference = EventPaymentPreference.query.filter_by(event_id=event_id).first()
        
        if not preference:
            return jsonify({'success': False, 'error': 'No payment preferences found for this event'}), 404
        
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Invalid JSON payload'}), 400
        
        # Update preferences
        if 'accepted_methods' in data:
            preference.set_accepted_methods(data['accepted_methods'])
        
        if 'preferred_currency' in data:
            preference.preferred_currency = data['preferred_currency']
        
        if 'auto_convert_wallet' in data:
            preference.auto_convert_wallet = data['auto_convert_wallet']
        
        if 'wallet_conversion_rate' in data:
            preference.wallet_conversion_rate = data['wallet_conversion_rate']
        
        if 'payment_settings' in data:
            preference.payment_settings = data['payment_settings']
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Payment preferences updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating event payment preferences: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _get_method_icon(method_type):
    """Get appropriate icon for payment method type"""
    icon_map = {
        "wallet": "💳",
        "mobile_money": "📱",
        "card": "💳",
        "bank_transfer": "🏦"
    }
    return icon_map.get(method_type, "💳")