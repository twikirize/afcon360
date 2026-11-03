# app/admin/owner/routes.py
"""
Owner routes - Highest privilege level
Includes Master Key Impersonation by Role and Security Dashboard
"""

from datetime import datetime, timezone, timedelta
import logging
from flask import (
    render_template, redirect, url_for, flash,
    request, session, jsonify, current_app
)
from flask_login import login_required, current_user, login_user, logout_user

from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.roles_permission import Role
from app.identity.models import User, UserRole
from app.models.system_config import SystemConfig as SystemSetting
from sqlalchemy import func
from app.admin.owner.decorators import owner_required, owner_or_superadmin_required
from app.admin.owner.utils import log_owner_action, get_system_health
from app.auth.roles import assign_global_role, revoke_global_role
from app.profile.models import get_profile_by_user
from app.auth.config_model import AuthConfiguration
from app.utils.module_toggle_service import ModuleToggleService

# Import audit decorators
from app.admin.owner.audit import audit_owner_action

# Import owner blueprint
from app.admin.owner import owner_bp

# Import security dashboard routes
from app.admin.owner.security_routes import add_security_routes

# Import role management routes
from app.owner.routes.role_management import role_management

logger = logging.getLogger(__name__)

# Helper for login required + owner check
def owner_login_required(f):
    return login_required(owner_required(f))

@owner_bp.context_processor
def utility_processor():
    def now():
        return datetime.now(timezone.utc)

    return {
        'now': now,
        'is_impersonating': session.get('is_impersonating', False),
        'impersonated_by': session.get('impersonated_by_name', ''),
        'impersonated_role': session.get('impersonated_role', '')
    }

# ============================================================================
# Dashboard & Core
# ============================================================================

@owner_bp.route('/wallet-capabilities')
@login_required
@owner_or_superadmin_required
def wallet_capabilities():
    """Wallet system capabilities overview and configuration (Owner/Super Admin)"""
    try:
        # Get wallet statistics
        from app.wallet.models.ledger import AccountModel
        from app.wallet.models.transaction import TransactionModel

        stats = {
            'total_users': User.query.count(),
            'active_wallets': AccountModel.query.count(),
            'total_transactions': TransactionModel.query.count(),
            'total_volume': '0'  # Would need calculation from transactions
        }

        return render_template('owner/wallet_capabilities.html', stats=stats)
    except Exception as e:
        current_app.logger.error(f"Wallet capabilities error: {e}")
        flash('Error loading wallet capabilities', 'danger')
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/admin-audit-log')
@owner_login_required
def admin_audit_log():
    """View admin audit log (Owner only)"""
    try:
        from app.wallet.services.admin_audit_service import AdminAuditService
        
        # Get audit logs for last 30 days
        logs = AdminAuditService.get_audit_logs(days=30, limit=100)
        summary = AdminAuditService.get_audit_summary(days=30)
        
        return render_template('owner/admin_audit_log.html', logs=logs, summary=summary)
    except Exception as e:
        current_app.logger.error(f"Admin audit log error: {e}")
        flash('Error loading admin audit log', 'danger')
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/manage-aggregators', methods=['GET', 'POST'])
@owner_login_required
def manage_aggregators():
    """Manage aggregators (Owner only)"""
    try:
        from app.wallet.services.aggregator_service import AggregatorService
        from flask_login import current_user
        
        if request.method == 'POST':
            # Create new aggregator
            name = request.form.get('name')
            display_name = request.form.get('display_name')
            api_key = request.form.get('api_key')
            api_secret = request.form.get('api_secret')
            description = request.form.get('description')
            tier = request.form.get('tier', 'standard')
            mode = request.form.get('mode', 'testing')
            sandbox_api_key = request.form.get('sandbox_api_key')
            sandbox_api_secret = request.form.get('sandbox_api_secret')
            live_api_key = request.form.get('live_api_key')
            live_api_secret = request.form.get('live_api_secret')
            
            AggregatorService.create_aggregator(
                name=name,
                display_name=display_name,
                api_key=api_key or sandbox_api_key or live_api_key,
                api_secret=api_secret or sandbox_api_secret or live_api_secret,
                description=description,
                tier=tier,
                mode=mode,
                sandbox_api_key=sandbox_api_key,
                sandbox_api_secret=sandbox_api_secret,
                live_api_key=live_api_key,
                live_api_secret=live_api_secret,
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='owner'
            )
            
            flash('Aggregator created successfully', 'success')
            return redirect(url_for('admin.owner.manage_aggregators'))
        
        # GET request - show list
        aggregators = AggregatorService.get_all_aggregators()
        return render_template('owner/manage_aggregators.html', aggregators=aggregators)
    except Exception as e:
        current_app.logger.error(f"Manage aggregators error: {e}")
        flash('Error managing aggregators', 'danger')
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/aggregator/<int:aggregator_id>/suspend', methods=['POST'])
@owner_login_required
def suspend_aggregator(aggregator_id):
    """Suspend an aggregator"""
    try:
        from app.wallet.services.aggregator_service import AggregatorService
        from flask_login import current_user
        
        reason = request.form.get('reason', 'No reason provided')
        
        AggregatorService.suspend_aggregator(
            aggregator_id=aggregator_id,
            admin_id=current_user.id,
            admin_name=current_user.username,
            admin_role='owner',
            reason=reason
        )
        
        flash('Aggregator suspended successfully', 'success')
        return redirect(url_for('admin.owner.manage_aggregators'))
    except Exception as e:
        current_app.logger.error(f"Suspend aggregator error: {e}")
        flash('Error suspending aggregator', 'danger')
        return redirect(url_for('admin.owner.manage_aggregators'))

@owner_bp.route('/aggregator/<int:aggregator_id>/activate', methods=['POST'])
@owner_login_required
def activate_aggregator(aggregator_id):
    """Activate a suspended aggregator"""
    try:
        from app.wallet.services.aggregator_service import AggregatorService
        from flask_login import current_user
        
        reason = request.form.get('reason', 'No reason provided')
        
        AggregatorService.activate_aggregator(
            aggregator_id=aggregator_id,
            admin_id=current_user.id,
            admin_name=current_user.username,
            admin_role='owner',
            reason=reason
        )
        
        flash('Aggregator activated successfully', 'success')
        return redirect(url_for('admin.owner.manage_aggregators'))
    except Exception as e:
        current_app.logger.error(f"Activate aggregator error: {e}")
        flash('Error activating aggregator', 'danger')
        return redirect(url_for('admin.owner.manage_aggregators'))

@owner_bp.route('/aggregator/<int:aggregator_id>/set-mode', methods=['POST'])
@owner_login_required
def set_aggregator_mode(aggregator_id):
    """Switch aggregator operating mode between testing and live"""
    try:
        from app.wallet.services.aggregator_service import AggregatorService
        from flask_login import current_user
        
        mode = request.form.get('mode', 'testing')
        reason = request.form.get('reason', f'Switched mode to {mode}')
        
        AggregatorService.set_aggregator_mode(
            aggregator_id=aggregator_id,
            mode=mode,
            admin_id=current_user.id,
            admin_name=current_user.username,
            admin_role='owner',
            reason=reason
        )
        
        flash(f'Aggregator mode successfully switched to {mode.upper()}', 'success')
        return redirect(url_for('admin.owner.manage_aggregators'))
    except Exception as e:
        current_app.logger.error(f"Set aggregator mode error: {e}")
        flash('Error switching aggregator mode', 'danger')
        return redirect(url_for('admin.owner.manage_aggregators'))

@owner_bp.route('/configure-fraud-detection', methods=['GET', 'POST'])
@owner_login_required
def configure_fraud_detection():
    """Configure fraud detection (Owner only)"""
    try:
        from app.wallet.services.fraud_detection_service import FraudDetectionService
        from flask_login import current_user
        
        if request.method == 'POST':
            # Update fraud detection configuration
            updates = {
                'enabled': request.form.get('enabled') == 'on',
                'algorithm_type': request.form.get('algorithm_type', 'rule_based'),
                'low_risk_threshold': float(request.form.get('low_risk_threshold', 0.3)),
                'medium_risk_threshold': float(request.form.get('medium_risk_threshold', 0.7)),
                'auto_block_threshold': float(request.form.get('auto_block_threshold', 0.9)),
                'max_transactions_per_minute': int(request.form.get('max_transactions_per_minute', 10)),
                'max_transactions_per_hour': int(request.form.get('max_transactions_per_hour', 100)),
                'max_amount_per_transaction': float(request.form.get('max_amount_per_transaction', 1000000)),
                'max_amount_per_hour': float(request.form.get('max_amount_per_hour', 10000000)),
                'check_ip_location': request.form.get('check_ip_location') == 'on',
                'check_device_fingerprint': request.form.get('check_device_fingerprint') == 'on',
                'check_velocity': request.form.get('check_velocity') == 'on',
                'check_unusual_patterns': request.form.get('check_unusual_patterns') == 'on',
                'check_new_account_large_transfer': request.form.get('check_new_account_large_transfer') == 'on',
                'check_multiple_failed_attempts': request.form.get('check_multiple_failed_attempts') == 'on',
                'alert_on_high_risk': request.form.get('alert_on_high_risk') == 'on',
                'alert_on_medium_risk': request.form.get('alert_on_medium_risk') == 'on',
                'auto_block_high_risk': request.form.get('auto_block_high_risk') == 'on',
                'require_manual_review_medium_risk': request.form.get('require_manual_review_medium_risk') == 'on',
                'allow_override': request.form.get('allow_override') == 'on',
                'alert_email_recipients': request.form.get('alert_email_recipients'),
                'description': request.form.get('description')
            }
            
            FraudDetectionService.update_config(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='owner',
                **updates
            )
            
            flash('Fraud detection configuration updated successfully', 'success')
            return redirect(url_for('admin.owner.configure_fraud_detection'))
        
        # GET request - show current configuration
        config = FraudDetectionService.get_config()
        return render_template('owner/configure_fraud_detection.html', config=config)
    except Exception as e:
        current_app.logger.error(f"Configure fraud detection error: {e}")
        flash('Error configuring fraud detection', 'danger')
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/configure-nonce-protection', methods=['GET', 'POST'])
@owner_login_required
def configure_nonce_protection():
    """Configure nonce replay protection (Owner only)"""
    try:
        from app.wallet.services.nonce_protection_service import NonceProtectionService
        from flask_login import current_user
        
        if request.method == 'POST':
            # Update nonce protection configuration
            updates = {
                'enabled': request.form.get('enabled') == 'on',
                'nonce_ttl_minutes': int(request.form.get('nonce_ttl_minutes', 15)),
                'cleanup_interval_hours': int(request.form.get('cleanup_interval_hours', 1)),
                'max_nonces_per_user_per_hour': int(request.form.get('max_nonces_per_user_per_hour', 1000)),
                'max_nonces_per_aggregator_per_hour': int(request.form.get('max_nonces_per_aggregator_per_hour', 10000)),
                'require_nonce_for_all_transactions': request.form.get('require_nonce_for_all_transactions') == 'on',
                'allow_nonce_reuse_same_amount': request.form.get('allow_nonce_reuse_same_amount') == 'on',
                'strict_ip_binding': request.form.get('strict_ip_binding') == 'on',
                'alert_on_suspicious_nonce_usage': request.form.get('alert_on_suspicious_nonce_usage') == 'on',
                'alert_threshold_per_hour': int(request.form.get('alert_threshold_per_hour', 100)),
                'description': request.form.get('description')
            }
            
            NonceProtectionService.update_config(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='owner',
                **updates
            )
            
            flash('Nonce protection configuration updated successfully', 'success')
            return redirect(url_for('admin.owner.configure_nonce_protection'))
        
        # GET request - show current configuration
        config = NonceProtectionService.get_config()
        return render_template('owner/configure_nonce_protection.html', config=config)
    except Exception as e:
        current_app.logger.error(f"Configure nonce protection error: {e}")
        flash('Error configuring nonce protection', 'danger')
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/configure-travel-rule', methods=['GET', 'POST'])
@owner_login_required
def configure_travel_rule():
    """Configure FATF Travel Rule compliance (Owner only)"""
    try:
        from app.wallet.services.travel_rule_service import TravelRuleService
        from flask_login import current_user
        
        if request.method == 'POST':
            # Update travel rule configuration
            updates = {
                'enabled': request.form.get('enabled') == 'on',
                'fiat_threshold_usd': int(request.form.get('fiat_threshold_usd', 1000)),
                'crypto_threshold_usd': int(request.form.get('crypto_threshold_usd', 1000)),
                'apply_to_all_jurisdictions': request.form.get('apply_to_all_jurisdictions') == 'on',
                'exempted_jurisdictions': request.form.get('exempted_jurisdictions'),
                'collect_originator_info': request.form.get('collect_originator_info') == 'on',
                'collect_beneficiary_info': request.form.get('collect_beneficiary_info') == 'on',
                'collect_transaction_purpose': request.form.get('collect_transaction_purpose') == 'on',
                'verify_originator_identity': request.form.get('verify_originator_identity') == 'on',
                'verify_beneficiary_identity': request.form.get('verify_beneficiary_identity') == 'on',
                'auto_report_to_vasp': request.form.get('auto_report_to_vasp') == 'on',
                'retain_records_days': int(request.form.get('retain_records_days', 1825)),
                'vasp_api_endpoint': request.form.get('vasp_api_endpoint'),
                'vasp_api_key': request.form.get('vasp_api_key'),
                'vasp_timeout_seconds': int(request.form.get('vasp_timeout_seconds', 30)),
                'description': request.form.get('description')
            }
            
            TravelRuleService.update_config(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='owner',
                **updates
            )
            
            flash('Travel Rule configuration updated successfully', 'success')
            return redirect(url_for('admin.owner.configure_travel_rule'))
        
        # GET request - show current configuration
        config = TravelRuleService.get_config()
        return render_template('owner/configure_travel_rule.html', config=config)
    except Exception as e:
        current_app.logger.error(f"Configure travel rule error: {e}")
        flash('Error configuring travel rule', 'danger')
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/configure-rate-limiting', methods=['GET', 'POST'])
@owner_login_required
def configure_rate_limiting():
    """Configure rate limiting (Owner only)"""
    try:
        from app.admin.owner.rate_limit_service import RateLimitService
        from flask_login import current_user

        if request.method == 'POST':
            updates = {
                'enabled': request.form.get('enabled') == 'on',
                'strategy': request.form.get('strategy', 'fixed-window'),
                'default_per_minute': int(request.form.get('default_per_minute', 500)),
                'default_per_hour': int(request.form.get('default_per_hour', 2000)),
                'default_per_day': int(request.form.get('default_per_day', 10000)),
                'block_duration_minutes': int(request.form.get('block_duration_minutes', 15)),
                'progressive_blocking_enabled': request.form.get('progressive_blocking_enabled') == 'on',
                'max_violations_before_block': int(request.form.get('max_violations_before_block', 10)),
                'key_sources': request.form.get('key_sources', 'ip,user_id'),
                'logging_enabled': request.form.get('logging_enabled') == 'on',
                'alert_on_breach': request.form.get('alert_on_breach') == 'on',
                'alert_threshold_per_minute': int(request.form.get('alert_threshold_per_minute', 100)),
                'edge_rate_limiting_enabled': request.form.get('edge_rate_limiting_enabled') == 'on',
            }

            success = RateLimitService.update_settings(
                updates=updates,
                updated_by=current_user.id
            )

            if success:
                flash('Rate limiting configuration updated successfully', 'success')
            else:
                flash('Error updating rate limiting configuration', 'danger')

            return redirect(url_for('admin.owner.configure_rate_limiting'))

        # GET request - show current configuration
        settings = RateLimitService.get_all_settings()
        return render_template('owner/configure_rate_limiting.html', settings=settings)
    except Exception as e:
        current_app.logger.error(f"Configure rate limiting error: {e}")
        flash('Error configuring rate limiting', 'danger')
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/add-payment-gateway', methods=['GET', 'POST'])
@owner_login_required
def add_payment_gateway():
    """Add additional payment gateway (Owner only)"""
    try:
        from flask_login import current_user
        
        if request.method == 'POST':
            # Get form data
            gateway_name = request.form.get('gateway_name')
            gateway_type = request.form.get('gateway_type')
            api_key = request.form.get('api_key')
            api_secret = request.form.get('api_secret')
            webhook_url = request.form.get('webhook_url')
            
            # Log the action
            from app.wallet.services.admin_audit_service import AdminAuditService
            AdminAuditService.log_action(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='owner',
                action_type='create',
                action_category='payment_gateway',
                target_type='payment_gateway',
                target_name=gateway_name,
                new_value={
                    'gateway_name': gateway_name,
                    'gateway_type': gateway_type,
                    'api_key': api_key,
                    'webhook_url': webhook_url
                },
                reason=f'Added payment gateway: {gateway_name}'
            )
            
            flash(f'Payment gateway {gateway_name} added successfully', 'success')
            return redirect(url_for('admin.owner.add_payment_gateway'))
        
        return render_template('owner/add_payment_gateway.html')
    except Exception as e:
        current_app.logger.error(f"Add payment gateway error: {e}")
        flash('Error adding payment gateway', 'danger')
        return redirect(url_for('admin.owner.dashboard'))


# ============================================================================
# Payment Method Configuration (Owner/Super Admin)
# ============================================================================

@owner_bp.route('/settings/payment-methods')
@owner_or_superadmin_required
def payment_methods_config():
    """List all payment methods with their marketplace collection status"""
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig
        
        methods = PaymentMethodConfig.query.order_by(PaymentMethodConfig.method_id).all()
        
        if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            data = []
            for m in methods:
                data.append({
                    'id': m.id,
                    'method_id': m.method_id,
                    'display_name': m.display_name,
                    'method_type': m.method_type,
                    'provider_name': m.provider_name,
                    'country_code': m.country_code,
                    'is_enabled': m.is_enabled,
                    'is_active': m.is_active,
                    'marketplace_collection_implemented': m.marketplace_collection_implemented,
                    'supported_currencies': m.supported_currencies or [],
                    'allowed_timings': m.allowed_timings or [],
                    'min_amount': float(m.min_amount) if m.min_amount else 0,
                    'max_amount': float(m.max_amount) if m.max_amount else 0,
                    'transaction_fee': float(m.transaction_fee) if m.transaction_fee else 0,
                })
            return jsonify({'success': True, 'payment_methods': data})
        
        return render_template('owner/payment_methods_config.html', methods=methods)
    except Exception as e:
        current_app.logger.error(f"Payment methods config error: {e}")
        flash('Error loading payment methods configuration', 'danger')
        return redirect(url_for('admin.owner.dashboard'))


@owner_bp.route('/settings/payment-methods/<int:method_id>/toggle', methods=['POST'])
@owner_or_superadmin_required
def toggle_payment_method(method_id):
    """Toggle payment method marketplace collection, enabled, or active status"""
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig
        from app.wallet.services.admin_audit_service import AdminAuditService
        from flask_login import current_user
        
        method = PaymentMethodConfig.query.get_or_404(method_id)
        
        data = request.get_json() or {}
        field = data.get('field')
        value = data.get('value')
        
        if field not in ['marketplace_collection_implemented', 'is_enabled', 'is_active']:
            return jsonify({'success': False, 'error': 'Invalid field'}), 400
        
        old_value = getattr(method, field)
        new_value = bool(value)
        
        if old_value == new_value:
            return jsonify({'success': True, 'message': 'No change', 'value': new_value})
        
        setattr(method, field, new_value)
        db.session.commit()
        
        # Audit log
        try:
            AdminAuditService.log_action(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='owner',
                action_type='update',
                action_category='payment_method_config',
                target_type='payment_method',
                target_id=str(method.id),
                target_name=method.method_id,
                old_value={field: old_value},
                new_value={field: new_value},
                reason=f'Toggled payment method {method.method_id} {field} to {new_value}'
            )
        except Exception as audit_e:
            current_app.logger.error(f"Audit log error: {audit_e}")
        
        return jsonify({'success': True, 'value': new_value, 'message': f'{field} set to {new_value}'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Toggle payment method error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@owner_bp.route('/settings/payment-methods/<int:method_id>', methods=['PUT'])
@owner_or_superadmin_required
def update_payment_method(method_id):
    """Update payment method configuration (full update)"""
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig
        from app.wallet.services.admin_audit_service import AdminAuditService
        from flask_login import current_user
        
        method = PaymentMethodConfig.query.get_or_404(method_id)
        data = request.get_json()
        
        # Fields that can be updated
        updatable_fields = [
            'display_name', 'method_type', 'provider_name', 'country_code',
            'is_enabled', 'is_active', 'requires_phone',
            'supported_currencies', 'allowed_timings',
            'min_amount', 'max_amount', 'transaction_fee',
            'sandbox_url', 'production_url', 'use_sandbox',
            'marketplace_collection_implemented',
            'config_json'
        ]
        
        old_values = {}
        for field in updatable_fields:
            if field in data:
                old_values[field] = getattr(method, field)
                new_value = data[field]
                
                # Type conversion for numeric fields
                if field in ['min_amount', 'max_amount', 'transaction_fee']:
                    new_value = float(new_value) if new_value is not None else None
                elif field in ['is_enabled', 'is_active', 'requires_phone', 'use_sandbox', 'marketplace_collection_implemented']:
                    new_value = bool(new_value)
                
                setattr(method, field, new_value)
        
        db.session.commit()
        
        # Audit log
        try:
            AdminAuditService.log_action(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='owner',
                action_type='update',
                action_category='payment_method_config',
                target_type='payment_method',
                target_id=str(method.id),
                target_name=method.method_id,
                old_value=old_values,
                new_value={k: data[k] for k in old_values},
                reason=f'Updated payment method {method.method_id} configuration'
            )
        except Exception as audit_e:
            current_app.logger.error(f"Audit log error: {audit_e}")
        
        return jsonify({'success': True, 'message': 'Payment method updated successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Update payment method error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# Payment Method Configuration (Owner/Super Admin) - Template Route
# ============================================================================

@owner_bp.route('/payment-methods-config')
@owner_or_superadmin_required
def payment_methods_config_page():
    """Render the payment methods configuration page"""
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig
        
        methods = PaymentMethodConfig.query.order_by(PaymentMethodConfig.method_id).all()
        return render_template('owner/payment_methods_config.html', methods=methods)
    except Exception as e:
        current_app.logger.error(f"Payment methods config page error: {e}")
        flash('Error loading payment methods configuration page', 'danger')
        return redirect(url_for('admin.owner.dashboard'))


@owner_bp.route('/dashboard')
@owner_login_required
def dashboard():
    """Owner dashboard - platform overview"""
    try:
        db.session.rollback()

        # User statistics
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        verified_users = User.query.filter_by(is_verified=True).count()

        # Get new users today
        today_utc = datetime.now(timezone.utc).date()
        new_users_today = User.query.filter(
            func.date(User.created_at) == today_utc
        ).count()

        # Organization statistics
        total_orgs = 0
        try:
            from app.identity.models.organisation import Organisation
            total_orgs = Organisation.query.count()
        except Exception as org_error:
            logger.warning(f"Organization query error: {org_error}")

        pending_orgs = 0  # Placeholder for pending organization approvals

        # Role statistics
        total_roles = Role.query.count()

        # Get role distribution
        role_stats = []
        try:
            role_stats = db.session.query(Role.name, func.count(UserRole.user_id))\
                .join(UserRole, Role.id == UserRole.role_id)\
                .group_by(Role.name).all()
        except Exception as role_error:
            logger.warning(f"Role stats query error: {role_error}")

        # Super admin management
        super_admins = []
        regular_users = []
        try:
            super_admin_role = Role.query.filter_by(name='super_admin').first()
            if super_admin_role:
                super_admins = db.session.query(User)\
                    .join(UserRole, User.id == UserRole.user_id)\
                    .join(Role, Role.id == UserRole.role_id)\
                    .filter(Role.name == 'super_admin').all()

            # Get regular users (non-super admins)
            regular_users = db.session.query(User)\
                .outerjoin(UserRole, User.id == UserRole.user_id)\
                .outerjoin(Role, Role.id == UserRole.role_id)\
                .filter((Role.name != 'super_admin') | (Role.name.is_(None)))\
                .limit(50).all()
        except Exception as admin_error:
            logger.warning(f"Super admin query error: {admin_error}")

        # Recent users
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()

        # Recent audit logs - simplified
        recent_logs = []
        try:
            from app.admin.owner.models import OwnerAuditLog
            recent_logs = OwnerAuditLog.query\
                .order_by(OwnerAuditLog.created_at.desc())\
                .limit(10).all()
        except Exception as log_error:
            logger.warning(f"Audit log query error: {log_error}")

        # System health
        health = get_system_health()

        # System settings
        from app.models.system_config import SystemConfig
        lockdown_enabled = SystemConfig.get('EMERGENCY_LOCKDOWN', False)
        maintenance_enabled = SystemConfig.get('MAINTENANCE_MODE', False)
        wallet_enabled = SystemConfig.get('ENABLE_WALLET', True)

        # Module flags
        modules = ModuleToggleService.get_flags()
        super_admin_can_toggle_modules = SystemConfig.get('SUPER_ADMIN_CAN_TOGGLE_MODULES', False)

        module_health = [
            {
                'name': name,
                'enabled': bool(enabled),
                'status': 'online' if enabled else 'offline'
            }
            for name, enabled in sorted(modules.items())
        ]

        # Compliance metrics
        pending_reviews_count = 0
        try:
            from app.audit.forensic_audit import ForensicAuditService
            pending_reviews = ForensicAuditService.get_pending_reviews(limit=5)
            pending_reviews_count = len(pending_reviews)
        except Exception as e:
            logger.warning(f"Could not load pending reviews: {e}")
            pending_reviews = []

        # Financial metrics placeholder
        total_revenue = 0
        try:
            # This would need actual transaction data
            from app.wallet.models.transaction import TransactionModel
            # Check if Transaction has a 'status' field, if not, count all transactions
            # Let's be safe and count all transactions for now
            total_revenue = TransactionModel.query.count()  # Placeholder count
        except Exception as revenue_error:
            logger.warning(f"Revenue query error: {revenue_error}")

        # Event statistics
        total_events = 0
        active_events = 0
        pending_events = 0
        total_registrations = 0
        pending_events_list = []

        try:
            from app.events.services import EventService
            from app.events.models import Event

            event_stats = EventService.get_admin_dashboard_data()
            total_events = event_stats.get('total_events', 0)
            active_events = event_stats.get('active_events', 0)
            pending_events = event_stats.get('pending_events', 0)
            total_registrations = event_stats.get('total_registrations', 0)

            # Get pending events list
            pending_events_list = Event.query.filter_by(
                status='pending',
                is_deleted=False
            ).order_by(Event.created_at.desc()).limit(10).all()
        except Exception as e:
            logger.warning(f"Could not load event statistics: {e}")

        # Get organization registration mode setting
        from app.admin.models import SystemConfiguration
        org_registration_config = SystemConfiguration.query.filter_by(
            key='org_registration_mode'
        ).first()
        org_registration_mode = (
            org_registration_config.value if org_registration_config else 'testing'
        )

        # Accommodation statistics for dashboard widgets
        unclaimed_count = 0
        readiness_issues_count = 0
        try:
            from app.accommodation.models.booking import AccommodationBooking
            from datetime import date as dt_date
            today = dt_date.today()
            unclaimed_count = AccommodationBooking.query.filter(
                AccommodationBooking.booking_owner_id.is_(None),
                AccommodationBooking.is_deleted == False,
            ).count()
            readiness_issues_count = AccommodationBooking.query.filter(
                AccommodationBooking.is_deleted == False,
                db.or_(
                    AccommodationBooking.status != 'confirmed',
                    AccommodationBooking.payment_status.not_in(('paid', 'partially_paid')),
                    AccommodationBooking.check_in > today,
                )
            ).count()
        except Exception as e:
            logger.warning(f"Could not load accommodation dashboard widgets: {e}")

        # KYC submission statistics
        kyc_pending_count = 0
        kyc_recent_pending = []
        kyc_total_subs = 0
        try:
            from app.kyc.models import KycRecord
            kyc_pending_count = KycRecord.query.filter(
                KycRecord.status.in_(('pending', 'manual_review')),
                KycRecord.is_deleted == False,
            ).count()
            kyc_recent_pending = KycRecord.query.filter(
                KycRecord.status.in_(('pending', 'manual_review')),
                KycRecord.is_deleted == False,
            ).order_by(KycRecord.created_at.desc()).limit(8).all()
            kyc_total_subs = KycRecord.query.filter(
                KycRecord.is_deleted == False
            ).count()
        except Exception as e:
            logger.warning(f"Could not load KYC dashboard stats: {e}")

        return render_template('owner/dashboard.html',
                               # User stats
                               total_users=total_users,
                               active_users=active_users,
                               verified_users=verified_users,
                               new_users_today=new_users_today,

                               # Organization stats
                               total_orgs=total_orgs,
                               pending_orgs=pending_orgs,

                               # Role stats
                               total_roles=total_roles,
                               role_stats=dict(role_stats),

                               # Super admin management
                               super_admins=super_admins,
                               regular_users=regular_users,
                               total_super_admins=len(super_admins),

                               # Recent data
                               recent_users=recent_users,
                               recent_logs=recent_logs,

                               # System info
                               health=health,
                               lockdown_enabled=lockdown_enabled,
                               maintenance_enabled=maintenance_enabled,
                               wallet_enabled=wallet_enabled,
                               owner_username=current_user.username,
                               owner_is_verified=current_user.is_verified,

                                # Module controls
                                modules=modules,
                                module_health=module_health,
                                super_admin_can_toggle_modules=super_admin_can_toggle_modules,

                                # Feed theme management
                                home_feed_layout=SystemConfig.get('home_feed_layout', 'mixed'),

                               # Compliance metrics
                               pending_reviews_count=pending_reviews_count,

                               # Financial placeholder
                               total_revenue=total_revenue,

                               # Event statistics
                               total_events=total_events,
                               active_events=active_events,
                               pending_events=pending_events,
                               total_registrations=total_registrations,
                               pending_events_list=pending_events_list,

                               # Organization registration mode
                               org_registration_mode=org_registration_mode,

                               # Accommodation dashboard widgets
                                unclaimed_count=unclaimed_count,
                                readiness_issues_count=readiness_issues_count,

                                # KYC submission stats
                                kyc_pending_count=kyc_pending_count,
                                kyc_recent_pending=kyc_recent_pending,
                                kyc_total_subs=kyc_total_subs,
                                )
    except Exception as e:
        logger.error(f"Owner dashboard error: {e}")
        return render_template('owner/dashboard.html',
                               total_users=0, active_users=0, verified_users=0,
                               new_users_today=0, total_orgs=0, pending_orgs=0,
                               total_roles=0, role_stats={}, super_admins=[],
                               regular_users=[], total_super_admins=0,
                               recent_users=[], recent_logs=[], health=None,
                               lockdown_enabled=False,
                               maintenance_enabled=False,
                               wallet_enabled=True,
                               owner_username=current_user.username,
                               owner_is_verified=current_user.is_verified,
                               modules={},
                               module_health=[],
                                super_admin_can_toggle_modules=False,
                                home_feed_layout=SystemConfig.get('home_feed_layout', 'mixed'),
                                total_revenue=0,
                                # Event statistics with defaults
                               total_events=0,
                               active_events=0,
                               pending_events=0,
                               total_registrations=0,
                               pending_events_list=[],

                               # Organization registration mode
                               org_registration_mode='testing',

                               # Accommodation dashboard widgets
                               unclaimed_count=0,
                               readiness_issues_count=0,

                               # KYC submission stats (fallback defaults)
                               kyc_pending_count=0,
                               kyc_recent_pending=[],
                               kyc_total_subs=0,
                               )

# ============================================================================
# Master Key: Impersonate by Role
# ============================================================================

@owner_bp.route('/master-key/act-as/<string:role_name>', methods=['POST'])
@owner_login_required
def impersonate_role(role_name):
    """
    MASTER KEY: Start impersonation of a user with the specified role.
    Persist impersonation in session without changing the logged-in actor.
    """
    try:
        # 1. Find a user that HAS this role
        target_user = (
            User.query
            .join(UserRole, User.id == UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name == role_name)
            .first()
        )

        if not target_user:
            flash(f"No existing users found with role: {role_name}. Please create one first.", "warning")
            return redirect(url_for('admin.owner.dashboard'))

        # 2. Set standardized impersonation session keys
        session['impersonated_user_id'] = target_user.id
        session['impersonation_started_at'] = datetime.now(timezone.utc).isoformat()
        session['impersonation_by'] = current_user.id
        session['impersonated_role'] = role_name

        # 3. Log the action
        log_owner_action(
            action='role_impersonation_started',
            category='security',
            details={'role': role_name, 'target_user': target_user.username, 'target_user_id': target_user.id}
        )

        flash(
            f"🗝️ Master Key Activated: You are now acting as a {role_name.replace('_', ' ').title()} ({target_user.username})",
            "success",
        )

        # 4. Redirect to the appropriate dashboard based on role
        dashboard_redirects = {
            'owner': url_for('admin.owner.dashboard'),
            'super_admin': url_for('admin.super_dashboard'),
            'admin': url_for('admin.super_dashboard'),
            'auditor': url_for('admin.auditor_dashboard'),
            'compliance_officer': url_for('admin.auditor_dashboard'),
            'moderator': url_for('admin.moderator_dashboard'),
            'support': url_for('admin.support_dashboard'),
            'event_manager': url_for('events.admin_dashboard'),
            'transport_admin': url_for('transport_admin.dashboard'),
            'wallet_admin': url_for('wallet.wallet_dashboard'),
            'accommodation_admin': url_for('accommodation.guest_search'),
            'tourism_admin': url_for('tourism.home'),
            'org_admin': url_for('events.events_hub'),
            'org_member': url_for('events.events_hub'),
            'user': url_for('fan.fan_dashboard')
        }

        redirect_url = dashboard_redirects.get(role_name, url_for('events.events_hub'))
        return redirect(redirect_url)

    except Exception as e:
        logger.error(f"Master Key Error: {e}")
        flash("Failed to activate Master Key.", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/master-key/exit', methods=['POST'])
@login_required
def exit_impersonation():
    """Exit impersonation (clear effective identity) and return to actor context."""
    try:
        # Prefer new standardized keys
        cleared = False
        if session.get('impersonated_user_id'):
            session.pop('impersonated_user_id', None)
            session.pop('impersonation_started_at', None)
            session.pop('impersonation_by', None)
            cleared = True

        # Backward compatibility: legacy keys
        session.pop('impersonated_by', None)
        session.pop('impersonated_by_name', None)
        session.pop('is_impersonating', None)
        session.pop('impersonated_role', None)

        if cleared:
            flash("✅ Impersonation ended. You are now acting as yourself.", "info")
            return redirect(url_for('admin.owner.dashboard'))

        # Legacy flow fallback: if previous implementation swapped login
        original_id = session.get('original_actor_user_id') or session.get('impersonated_by')
        if original_id:
            owner_user = db.session.get(User, original_id)
            if owner_user:
                logout_user()
                login_user(owner_user)
                flash("✅ Returned to Owner Dashboard", "info")
                return redirect(url_for('admin.owner.dashboard'))
    except Exception as e:
        current_app.logger.warning(f"Exit impersonation error: {e}")

    return redirect(url_for('transport.home'))

# Keep existing user-specific impersonation for fine-grained testing
@owner_bp.route('/impersonate/<string:user_id>', methods=['POST'])
@owner_login_required
def impersonate_user(user_id):
    """Impersonate a specific user (session-based; does not swap login)."""
    try:
        target_user = User.query.filter_by(public_id=user_id).first()
        if not target_user:
            flash("User not found", "danger")
            return redirect(url_for('admin.owner.dashboard'))

        # Standardized session keys
        session['impersonated_user_id'] = target_user.id
        session['impersonation_started_at'] = datetime.now(timezone.utc).isoformat()
        session['impersonation_by'] = current_user.id

        log_owner_action(
            action='user_impersonation_started',
            category='security',
            details={'target_user': target_user.username, 'target_user_id': target_user.id}
        )

        flash(f"🎭 You are now acting as {target_user.username}", "success")
        return redirect(url_for('admin.owner.dashboard'))

    except Exception as e:
        logger.error(f"User impersonation error: {e}")
        flash("Failed to impersonate user", "danger")
        return redirect(url_for('admin.owner.dashboard'))

# ============================================================================
# Management Routes
# ============================================================================

@owner_bp.route('/audit-logs')
@owner_login_required
def audit_logs():
    """View owner audit logs"""
    try:
        from app.audit.comprehensive_audit import SecurityEventLog

        # Get filter parameters
        event_type = request.args.get('event_type')
        severity = request.args.get('severity')
        days = int(request.args.get('days', 7))
        page = request.args.get('page', 1, type=int)

        query = SecurityEventLog.query

        if event_type:
            query = query.filter_by(event_type=event_type)
        if severity:
            query = query.filter_by(severity=severity)

        # Filter by date
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(SecurityEventLog.created_at >= since_date)

        # Use pagination
        logs = query.order_by(SecurityEventLog.created_at.desc()).paginate(
            page=page, per_page=50, error_out=False
        )

        # Get unique event types for filter dropdown
        event_types = db.session.query(SecurityEventLog.event_type).distinct().all()
        event_types = [et[0] for et in event_types if et[0]]

        # Use event_types as categories for the filter dropdown
        categories = event_types

        return render_template('owner/audit_logs.html',
                               logs=logs,
                               event_types=event_types,
                               categories=categories,
                               current_category=event_type,
                               current_filters={'event_type': event_type, 'severity': severity, 'days': days})
    except Exception as e:
        logger.error(f"Audit logs error: {e}")
        return render_template('owner/audit_logs.html', logs=[], event_types=[], categories=[], current_category=None, current_filters={})


# ============================================================================
# Owner Settings
# ============================================================================

@owner_bp.route('/settings')
@owner_login_required
def settings():
    """Owner settings page with MFA requirement toggle."""
    try:
        if request.method == 'POST':
            # Update settings
            session_timeout = request.form.get('session_timeout', type=int, default=120)

            # SECURITY: Update MFA requirement toggle
            require_owner_mfa = request.form.get('require_owner_mfa') == 'on'

            # Update config (this is a system-wide setting)
            # In production, this should update a SystemSetting in DB
            current_app.config['REQUIRE_OWNER_MFA'] = require_owner_mfa

            # Also update OwnerSettings
            owner_settings = OwnerSettings.query.filter_by(owner_id=current_user.id).first()
            if not owner_settings:
                owner_settings = OwnerSettings(owner_id=current_user.id)
                db.session.add(owner_settings)
            owner_settings.session_timeout = session_timeout

            log_owner_action(
                action='updated_settings',
                category='settings',
                details={
                    'session_timeout': session_timeout,
                    'require_owner_mfa': require_owner_mfa
                }
            )
            return redirect(url_for('admin.owner.settings'))

        # GET request - show settings page
        logger.info("Fetching owner settings from database")
        owner_settings = OwnerSettings.query.filter_by(owner_id=current_user.id).first()

        # Get the database-persisted MFA policy (environment is only bootstrap fallback).
        require_mfa = bool(SystemConfig.get(
            'REQUIRE_OWNER_MFA', current_app.config.get('REQUIRE_OWNER_MFA', False)
        ))

        # Get super admin module toggle permission
        super_admin_can_toggle_modules = SystemSetting.get('SUPER_ADMIN_CAN_TOGGLE_MODULES', False)

        # Get organization registration mode
        from app.admin.models import SystemConfiguration
        org_registration_config = SystemConfiguration.query.filter_by(
            key='org_registration_mode'
        ).first()
        org_registration_mode = (
            org_registration_config.value if org_registration_config else 'testing'
        )

        # Get wallet adjustment workflow settings
        wallet_adjustment_workflow = SystemConfig.get('WALLET_ADJUSTMENT_WORKFLOW', False)
        wallet_adjustment_threshold = SystemConfig.get('WALLET_ADJUSTMENT_THRESHOLD', 100000)

        # Get Socket.IO stored setting
        socketio_enabled_stored = SystemConfig.get('SOCKETIO_ENABLED', None)

        logger.info(f"Rendering settings template with org_registration_mode={org_registration_mode}")
        return render_template('owner/settings.html',
                               settings=owner_settings,
                               require_owner_mfa=require_mfa,
                               super_admin_can_toggle_modules=super_admin_can_toggle_modules,
                               org_registration_mode=org_registration_mode,
                               wallet_adjustment_workflow=wallet_adjustment_workflow,
                               wallet_adjustment_threshold=wallet_adjustment_threshold,
                               socketio_enabled_stored=socketio_enabled_stored,
                               )
    except Exception as e:
        logger.error(f"Settings page error: {e}")
        flash("Unable to load settings. Please try again later.", "warning")
        return redirect(url_for('admin.owner.dashboard'))


@owner_bp.route('/settings/owner-mfa', methods=['POST'])
@owner_login_required
@audit_owner_action('updated_owner_mfa_requirement', 'security')
def update_owner_mfa_requirement():
    """Persist the owner MFA requirement after safe enrollment preconditions."""
    from app.identity.models import User, UserRole
    from app.identity.models.user import MFASecret
    from app.models.system_config import SystemConfig

    try:
        if not current_user.is_app_owner():
            flash("Only the platform owner can change the owner MFA policy.", "danger")
            return redirect(url_for('admin.owner.settings'))
        from app.auth.security_policy import recent_owner_totp_proof
        if not recent_owner_totp_proof(max_age_seconds=300):
            flash(
                "For security, verify a current authenticator-app code and save this setting within five minutes.",
                "warning",
            )
            return redirect(url_for('admin.owner.settings'))

        enabled = request.form.get('require_owner_mfa') == 'on'

        if enabled:
            owner_role = Role.query.filter_by(name='owner', scope='global').first()
            if owner_role is None:
                flash("Owner MFA could not be enabled: the global owner role was not found.", "danger")
                return redirect(url_for('admin.owner.settings'))

            active_owners = (
                User.query.join(UserRole, UserRole.user_id == User.id)
                .filter(
                    UserRole.role_id == owner_role.id,
                    User.is_active.is_(True),
                    User.is_deleted.is_(False),
                )
                .all()
            )
            from app.auth.security_policy import totp_proof_matches

            enrolled_ids = set()
            for owner in active_owners:
                active_totp = MFASecret.query.filter_by(
                    user_id=owner.id,
                    mfa_type='totp',
                    is_active=True,
                ).first()
                if active_totp is None:
                    continue
                try:
                    plaintext_secret = active_totp.get_totp_secret()
                    if totp_proof_matches(owner, plaintext_secret):
                        enrolled_ids.add(owner.id)
                except Exception:
                    current_app.logger.exception(
                        "Could not validate TOTP proof for owner %s", owner.public_id
                    )

            missing = [
                owner for owner in active_owners
                if not owner.mfa_enabled or owner.id not in enrolled_ids
            ]
            if not active_owners or missing:
                names = ", ".join(
                    (owner.username or owner.public_id) for owner in missing[:5]
                )
                suffix = f" Not enrolled: {names}." if names else ""
                flash(
                    "Owner MFA was not enabled. Every active platform owner must first "
                    "enable an authenticator app (TOTP) and verify their enrollment."
                    + suffix,
                    "warning",
                )
                return redirect(url_for('admin.owner.settings'))

        SystemConfig.set(
            key='REQUIRE_OWNER_MFA',
            value=enabled,
            value_type='bool',
            category='security',
            description='Require authenticator-based MFA for every active platform owner',
            updated_by=current_user.id,
            commit=False,
        )
        db.session.commit()

        log_owner_action(
            action='updated_owner_mfa_requirement',
            category='security',
            details={'require_owner_mfa': enabled},
        )
        flash(
            "Owner MFA enforcement is now enabled for all enrolled platform owners."
            if enabled else
            "Owner MFA enforcement has been disabled. Enrolled users still need MFA to log in.",
            "success",
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to update owner MFA enforcement")
        flash("Unable to update owner MFA enforcement. No change was saved.", "danger")

    return redirect(url_for('admin.owner.settings'))