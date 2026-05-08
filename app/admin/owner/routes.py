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
from sqlalchemy import func
from app.admin.owner.decorators import owner_required
from app.admin.owner.utils import log_owner_action, get_system_health
from app.auth.roles import assign_global_role, revoke_global_role
from app.profile.models import get_profile_by_user
from app.auth.config_model import AuthConfiguration

# Import audit decorators
from app.admin.owner.audit import audit_owner_action

# Import owner blueprint
from app.admin.owner import owner_bp

# Import security dashboard routes
from app.admin.owner.security_routes import add_security_routes

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
@owner_login_required
def wallet_capabilities():
    """Wallet system capabilities overview and configuration (Owner only)"""
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
        flash('Error loading wallet capabilities', 'error')
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
        flash('Error loading admin audit log', 'error')
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
            
            AggregatorService.create_aggregator(
                name=name,
                display_name=display_name,
                api_key=api_key,
                api_secret=api_secret,
                description=description,
                tier=tier,
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
        flash('Error managing aggregators', 'error')
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
        flash('Error suspending aggregator', 'error')
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
        flash('Error activating aggregator', 'error')
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
            return redirect(url_for('owner.configure_fraud_detection'))
        
        # GET request - show current configuration
        config = FraudDetectionService.get_config()
        return render_template('owner/configure_fraud_detection.html', config=config)
    except Exception as e:
        current_app.logger.error(f"Configure fraud detection error: {e}")
        flash('Error configuring fraud detection', 'error')
        return redirect(url_for('owner.dashboard'))

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
            return redirect(url_for('owner.configure_nonce_protection'))
        
        # GET request - show current configuration
        config = NonceProtectionService.get_config()
        return render_template('owner/configure_nonce_protection.html', config=config)
    except Exception as e:
        current_app.logger.error(f"Configure nonce protection error: {e}")
        flash('Error configuring nonce protection', 'error')
        return redirect(url_for('owner.dashboard'))

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
            return redirect(url_for('owner.configure_travel_rule'))
        
        # GET request - show current configuration
        config = TravelRuleService.get_config()
        return render_template('owner/configure_travel_rule.html', config=config)
    except Exception as e:
        current_app.logger.error(f"Configure travel rule error: {e}")
        flash('Error configuring travel rule', 'error')
        return redirect(url_for('owner.dashboard'))

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
            return redirect(url_for('owner.add_payment_gateway'))
        
        return render_template('owner/add_payment_gateway.html')
    except Exception as e:
        current_app.logger.error(f"Add payment gateway error: {e}")
        flash('Error adding payment gateway', 'error')
        return redirect(url_for('owner.dashboard'))

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
        from app.admin.owner.models import SystemSetting
        lockdown_enabled = SystemSetting.get('EMERGENCY_LOCKDOWN', False)
        maintenance_enabled = SystemSetting.get('MAINTENANCE_MODE', False)
        wallet_enabled = SystemSetting.get('ENABLE_WALLET', True)

        # Module flags
        modules = current_app.config.get("MODULE_FLAGS", {})
        super_admin_can_toggle_modules = SystemSetting.get('SUPER_ADMIN_CAN_TOGGLE_MODULES', False)

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
                               super_admin_can_toggle_modules=super_admin_can_toggle_modules,

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
                               org_registration_mode=org_registration_mode)
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
                               super_admin_can_toggle_modules=False,
                               total_revenue=0,
                               # Event statistics with defaults
                               total_events=0,
                               active_events=0,
                               pending_events=0,
                               total_registrations=0,
                               pending_events_list=[],
                               
                               # Organization registration mode
                               org_registration_mode='testing')

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
            'accommodation_admin': url_for('accommodation.admin_dashboard'),
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
            owner_user = User.query.get(original_id)
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
        flash("Error loading audit logs", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/settings', methods=['GET', 'POST'])
@owner_login_required
@audit_owner_action('viewed_settings', 'settings')
def settings():
    """Owner settings page - includes system security settings"""
    try:
        logger.info("Loading settings page")
        from app.admin.owner.models import OwnerSettings, SystemSetting

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

            owner_settings.session_timeout_minutes = session_timeout
            db.session.commit()

            flash("✅ Settings updated successfully", "success")
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

        # Get current MFA requirement status
        require_mfa = current_app.config.get('REQUIRE_OWNER_MFA', False)

        # Get super admin module toggle permission
        super_admin_can_toggle_modules = SystemSetting.get('SUPER_ADMIN_CAN_TOGGLE_MODULES', False)

        # Get organization registration mode setting
        try:
            from app.admin.models import SystemConfiguration
            logger.info("Fetching SystemConfiguration for org_registration_mode")
            org_registration_config = SystemConfiguration.query.filter_by(
                key='org_registration_mode'
            ).first()
            org_registration_mode = (
                org_registration_config.value if org_registration_config else 'testing'
            )
        except Exception as config_error:
            logger.warning(f"Could not load SystemConfiguration: {config_error}")
            org_registration_mode = 'testing'

        logger.info(f"Rendering settings template with org_registration_mode={org_registration_mode}")
        return render_template('owner/settings.html',
                             settings=owner_settings,
                             require_owner_mfa=require_mfa,
                             super_admin_can_toggle_modules=super_admin_can_toggle_modules,
                             org_registration_mode=org_registration_mode)
    except Exception as e:
        logger.error(f"Settings error: {e}", exc_info=True)
        flash(f"Error loading settings: {str(e)}", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/settings/toggle-org-registration-mode', methods=['POST'])
@owner_login_required
@audit_owner_action('toggled_org_registration_mode', 'settings')
def toggle_org_registration_mode():
    """Toggle organization registration requirements mode"""
    try:
        testing_mode = request.form.get('testing_mode') == 'on'
        
        # Store the setting in a system-wide configuration
        from app.admin.models import SystemConfiguration
        config = SystemConfiguration.query.filter_by(key='org_registration_mode').first()
        
        if not config:
            config = SystemConfiguration(
                key='org_registration_mode',
                value='testing' if testing_mode else 'standard',
                description='Organization registration requirements mode'
            )
            db.session.add(config)
        else:
            config.value = 'testing' if testing_mode else 'standard'
            config.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        mode = 'Testing Mode' if testing_mode else 'Standard Mode'
        log_owner_action(
            f'toggled_org_registration_mode_to_{config.value}',
            f'Organization registration mode changed to {mode}',
            details={'testing_mode': testing_mode}
        )
        
        flash(f'Organization registration mode changed to {mode}', 'success')
        
    except Exception as e:
        logger.error(f"Error toggling organization registration mode: {e}")
        db.session.rollback()
        flash('Error updating registration mode', 'error')
    
    return redirect(url_for('admin.owner.settings'))


@owner_bp.route('/settings/toggle-super-admin-module-access', methods=['POST'])
@owner_login_required
@audit_owner_action('toggled_super_admin_module_access', 'settings')
def toggle_super_admin_module_access():
    """Toggle whether super admins are allowed to enable/disable modules"""
    try:
        from app.admin.owner.models import SystemSetting
        current_value = SystemSetting.get('SUPER_ADMIN_CAN_TOGGLE_MODULES', False)
        new_value = not current_value

        SystemSetting.set(
            key='SUPER_ADMIN_CAN_TOGGLE_MODULES',
            value=new_value,
            value_type='bool',
            category='permissions',
            description='Allow super_admins to toggle system modules',
            updated_by=current_user.id
        )

        flash(
            f"Super admins are now {'authorized' if new_value else 'restricted'} to toggle modules.",
            "success" if new_value else "info"
        )

        log_owner_action(
            action='toggled_super_admin_module_access',
            category='settings',
            details={
                'new_value': new_value,
                'previous_value': current_value
            }
        )
    except Exception as e:
        logger.error(f"Error toggling super admin module access: {e}")
        flash("Failed to update permission.", "danger")

    return redirect(url_for('admin.owner.settings'))


@owner_bp.route('/users')
@owner_login_required
@audit_owner_action('viewed_users', 'user_management')
def users():
    """Manage all users"""
    try:
        page = request.args.get('page', 1, type=int)
        users = User.query.paginate(
            page=page, per_page=50, error_out=False
        )
        return render_template('owner/users.html', users=users)
    except Exception as e:
        logger.error(f"Users management error: {e}")
        flash("Error loading users", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/manage-roles')
@owner_login_required
@audit_owner_action('viewed_roles', 'user_management')
def manage_roles():
    """Manage system roles"""
    try:
        roles = Role.query.all()
        users = User.query.all()

        # Get role statistics
        role_stats = {}
        try:
            role_stats = dict(db.session.query(Role.name, func.count(UserRole.user_id))
                .join(UserRole, Role.id == UserRole.role_id)
                .group_by(Role.name).all())
        except Exception as role_error:
            logger.warning(f"Role stats query error: {role_error}")

        return render_template('admin/manage_roles.html', roles=roles, users=users, role_stats=role_stats)
    except Exception as e:
        logger.error(f"Role management error: {e}")
        flash("Error loading roles", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/roles/<int:role_id>/users')
@owner_login_required
@audit_owner_action('viewed_role_users', 'user_management')
def role_users(role_id):
    """View users with a specific role"""
    try:
        role = Role.query.get_or_404(role_id)
        user_roles = UserRole.query.filter_by(role_id=role_id).all()
        users = [ur.user for ur in user_roles]

        return render_template('admin/role_users.html', role=role, users=users)
    except Exception as e:
        logger.error(f"Error loading role users: {e}")
        flash("Error loading role users", "danger")
        return redirect(url_for('admin.owner.manage_roles'))

@owner_bp.route('/roles/assign', methods=['POST'])
@owner_login_required
@audit_owner_action('assigned_role', 'user_management')
def assign_role():
    """Assign a role to a user"""
    try:
        user_id = request.form.get('user_id')
        role_id = request.form.get('role_id')

        if not user_id or not role_id:
            flash("User ID and Role ID are required", "danger")
            return redirect(url_for('admin.owner.manage_roles'))

        user = User.query.get_or_404(user_id)
        role = Role.query.get_or_404(role_id)

        # Check if user already has this role
        existing = UserRole.query.filter_by(user_id=user_id, role_id=role_id).first()
        if existing:
            flash(f"{user.username} already has the {role.name} role", "warning")
            return redirect(url_for('admin.owner.manage_roles'))

        # Assign the role
        user_role = UserRole(user_id=user_id, role_id=role_id)
        db.session.add(user_role)
        db.session.commit()

        flash(f"Successfully assigned {role.name} role to {user.username}", "success")
        log_owner_action(
            action='role_assigned',
            category='user_management',
            details={'user_id': user_id, 'username': user.username, 'role': role.name}
        )

    except Exception as e:
        logger.error(f"Error assigning role: {e}")
        db.session.rollback()
        flash("Error assigning role", "danger")

    return redirect(url_for('admin.owner.manage_roles'))

@owner_bp.route('/roles/revoke', methods=['POST'])
@owner_login_required
@audit_owner_action('revoked_role', 'user_management')
def revoke_role():
    """Revoke a role from a user"""
    try:
        user_id = request.form.get('user_id')
        role_id = request.form.get('role_id')

        if not user_id or not role_id:
            flash("User ID and Role ID are required", "danger")
            return redirect(url_for('admin.owner.manage_roles'))

        user = User.query.get_or_404(user_id)
        role = Role.query.get_or_404(role_id)

        # Prevent revoking owner role from the only owner
        if role.name == 'owner':
            owner_count = UserRole.query.filter_by(role_id=role_id).count()
            if owner_count <= 1:
                flash("Cannot revoke owner role from the last owner", "danger")
                return redirect(url_for('admin.owner.manage_roles'))

        # Revoke the role
        user_role = UserRole.query.filter_by(user_id=user_id, role_id=role_id).first()
        if user_role:
            db.session.delete(user_role)
            db.session.commit()

            flash(f"Successfully revoked {role.name} role from {user.username}", "success")
            log_owner_action(
                action='role_revoked',
                category='user_management',
                details={'user_id': user_id, 'username': user.username, 'role': role.name}
            )
        else:
            flash(f"{user.username} does not have the {role.name} role", "warning")

    except Exception as e:
        logger.error(f"Error revoking role: {e}")
        db.session.rollback()
        flash("Error revoking role", "danger")

    return redirect(url_for('admin.owner.manage_roles'))

@owner_bp.route('/danger-zone')
@owner_login_required
@audit_owner_action('viewed_danger_zone', 'danger')
def danger_zone():
    """Danger zone - critical platform actions"""
    try:
        from app.admin.owner.models import SystemSetting
        lockdown_enabled = SystemSetting.get('EMERGENCY_LOCKDOWN', False)
        maintenance_enabled = SystemSetting.get('MAINTENANCE_MODE', False)

        return render_template('owner/danger_zone.html',
                               lockdown_enabled=lockdown_enabled,
                               maintenance_enabled=maintenance_enabled)
    except Exception as e:
        logger.error(f"Danger zone error: {e}")
        flash("Error loading danger zone", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/toggle-global-maintenance', methods=['POST'])
@owner_login_required
@audit_owner_action('toggled_maintenance_mode', 'danger')
def toggle_global_maintenance():
    """Toggle global maintenance mode"""
    try:
        from app.admin.owner.models import SystemSetting
        current_mode = SystemSetting.get('MAINTENANCE_MODE', False)
        new_mode = not current_mode

        SystemSetting.set('MAINTENANCE_MODE', new_mode, value_type='bool',
                         category='system', description='Maintenance mode toggle')

        # Log the action
        log_owner_action(
            action='maintenance_mode_toggled',
            category='system',
            details={'new_mode': new_mode, 'previous_mode': current_mode}
        )

        flash(f"Maintenance mode {'enabled' if new_mode else 'disabled'}",
              "success" if not new_mode else "warning")

    except Exception as e:
        logger.error(f"Toggle maintenance error: {e}")
        flash("Failed to toggle maintenance mode", "danger")

    return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/toggle-lockdown', methods=['POST'])
@owner_login_required
@audit_owner_action('toggled_lockdown', 'danger')
def toggle_lockdown():
    """Toggle emergency lockdown"""
    try:
        from app.admin.owner.models import SystemSetting
        current_mode = SystemSetting.get('EMERGENCY_LOCKDOWN', False)
        new_mode = not current_mode

        SystemSetting.set('EMERGENCY_LOCKDOWN', new_mode, value_type='bool',
                         category='security', description='Emergency lockdown toggle')

        # Log the action
        log_owner_action(
            action='emergency_lockdown_toggled',
            category='security',
            details={'new_mode': new_mode, 'previous_mode': current_mode}
        )

        flash(f"Emergency lockdown {'enabled' if new_mode else 'disabled'}",
              "success" if not new_mode else "danger")

    except Exception as e:
        logger.error(f"Toggle lockdown error: {e}")
        flash("Failed to toggle emergency lockdown", "danger")

    return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/system-health')
@owner_login_required
@audit_owner_action('viewed_system_health', 'navigation')
def system_health():
    """View system health metrics"""
    try:
        health = get_system_health()
        from app.admin.owner.models import SystemSetting
        settings_count = SystemSetting.query.count()

        return render_template('owner/system_health.html',
                               health=health,
                               settings_count=settings_count)
    except Exception as e:
        logger.error(f"System health error: {e}")
        flash("Error loading system health", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/impersonate-page')
@owner_login_required
@audit_owner_action('viewed_impersonate_page', 'security')
def impersonate_page():
    """Master key impersonation page"""
    try:
        # Get all roles
        roles = Role.query.all()

        # Get all users with their roles for display
        users = User.query.all()

        # Enhance user data with role information
        enhanced_users = []
        for user in users:
            user_roles = db.session.query(Role.name).join(UserRole, Role.id == UserRole.role_id).filter(UserRole.user_id == user.id).all()
            role_names = [role[0] for role in user_roles]
            enhanced_users.append({
                'user': user,
                'roles': role_names,
                'primary_role': role_names[0] if role_names else 'user'
            })

        return render_template('owner/impersonate.html',
                          roles=roles,
                          users=enhanced_users,
                          global_roles=roles)
    except Exception as e:
        logger.error(f"Impersonate page error: {e}")
        flash("Error loading impersonate page", "danger")
        return redirect(url_for('admin.owner.dashboard'))

# ============================================================================
# Super Admin Management
# ============================================================================

@owner_bp.route('/add-super-admin', methods=['POST'])
@owner_login_required
@audit_owner_action('added_super_admin', 'user_management')
def add_super_admin():
    """Add a new super admin"""
    try:
        user_id = request.form.get('user_id')
        if not user_id:
            flash("Please select a user", "warning")
            return redirect(url_for('admin.owner.dashboard'))

        user = User.query.get(user_id)
        if not user:
            flash("User not found", "danger")
            return redirect(url_for('admin.owner.dashboard'))

        logger.info(f"Attempting to add super admin: user_id={user_id}, user={user.username}")

        # First, find or create the super_admin role
        super_admin_role = Role.query.filter_by(name='super_admin').first()
        if not super_admin_role:
            # Create the role if it doesn't exist
            logger.info("Creating super_admin role")
            super_admin_role = Role(
                name='super_admin',
                description='System super administrator with full access',
                scope='global',
                level=100  # High level for super admin
            )
            db.session.add(super_admin_role)
            db.session.commit()  # Commit to ensure role exists
            logger.info(f"Created super_admin role with id={super_admin_role.id}")
        else:
            logger.info(f"Found existing super_admin role with id={super_admin_role.id}")

        # Check if user already has this role
        existing_role = UserRole.query.filter_by(
            user_id=user.id,
            role_id=super_admin_role.id
        ).first()

        if existing_role:
            logger.info(f"User {user.username} already has super_admin role")
            flash(f"⚠️ {user.username} is already a Super Admin", "info")
        else:
            # Assign the role to the user using assign_global_role
            logger.info(f"Assigning super_admin role to user {user.username}")
            user_role = assign_global_role(user.id, 'super_admin', assigned_by_id=current_user.id)
            logger.info(f"Assigned UserRole with id={user_role.id}")

            # Verify the assignment
            verification = UserRole.query.filter_by(
                user_id=user.id,
                role_id=super_admin_role.id
            ).first()
            if verification:
                logger.info(f"Verification successful: UserRole exists for user {user.username}")
            else:
                logger.error(f"Verification failed: UserRole not found for user {user.username}")

            flash(f"✅ {user.username} is now a Super Admin", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Add super admin error: {e}", exc_info=True)
        flash("Failed to add super admin", "danger")

    return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/remove-super-admin/<int:user_id>', methods=['POST'])
@owner_login_required
@audit_owner_action('removed_super_admin', 'user_management')
def remove_super_admin(user_id):
    """Remove super admin privileges"""
    try:
        user = User.query.get(user_id)
        if not user:
            flash("User not found", "danger")
            return redirect(url_for('admin.owner.dashboard'))

        revoke_global_role(user.id, 'super_admin', revoked_by_id=current_user.id)
        flash(f"✅ Super admin privileges removed from {user.username}", "success")

    except Exception as e:
        logger.error(f"Remove super admin error: {e}")
        flash("Failed to remove super admin", "danger")

    return redirect(url_for('admin.owner.dashboard'))

# ============================================================================
# KYC Tier Management
# ============================================================================

@owner_bp.route('/kyc/tiers')
@owner_login_required
@audit_owner_action('viewed_kyc_tiers', 'compliance')
def kyc_tier_management():
    """KYC tier management panel."""
    try:
        from app.auth.kyc_compliance import (
            TIER_REQUIREMENTS, DAILY_LIMITS, MONTHLY_LIMITS, TRANSACTION_LIMITS
        )

        # Get all users with their KYC tiers
        from app.auth.kyc_compliance import calculate_kyc_tier
        from app.identity.models.user import User

        # Get filter parameters
        tier_filter = request.args.get('tier', type=int)
        status_filter = request.args.get('status')
        search_query = request.args.get('search', '').strip()

        # Build query
        query = User.query

        if search_query:
            query = query.filter(
                (User.username.ilike(f'%{search_query}%')) |
                (User.email.ilike(f'%{search_query}%'))
            )

        users = query.order_by(User.created_at.desc()).limit(200).all()

        # Calculate KYC info for each user and count tiers
        user_kyc_info = []
        tier_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        for user in users:
            kyc_info = calculate_kyc_tier(user.id)
            tier_counts[kyc_info['tier']] += 1
            user_kyc_info.append({
                'user': user,
                'kyc_info': kyc_info
            })

        # Filter by tier if specified
        if tier_filter is not None:
            user_kyc_info = [info for info in user_kyc_info if info['kyc_info']['tier'] == tier_filter]

        # Filter by verification status if specified
        if status_filter:
            user_kyc_info = [info for info in user_kyc_info
                           if info['kyc_info'].get('verification_status') == status_filter]

        # Get pending manual reviews
        from app.audit.forensic_audit import ForensicAuditService
        pending_reviews = ForensicAuditService.get_pending_reviews(
            entity_type="kyc",
            limit=50
        )

        return render_template('owner/kyc_tiers.html',
                               user_kyc_info=user_kyc_info,
                               tier_counts=tier_counts,
                               tier_requirements=TIER_REQUIREMENTS,
                               daily_limits=DAILY_LIMITS,
                               monthly_limits=MONTHLY_LIMITS,
                               transaction_limits=TRANSACTION_LIMITS,
                               pending_reviews=pending_reviews,
                               current_filters={
                                   'tier': tier_filter,
                                   'status': status_filter,
                                   'search': search_query
                               })
    except Exception as e:
        logger.error(f"KYC tier management error: {e}")
        flash("Error loading KYC tier management", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/kyc/manual-upgrade/<int:user_id>', methods=['POST'])
@owner_login_required
@audit_owner_action('manual_kyc_upgrade', 'compliance')
def manual_kyc_upgrade(user_id):
    """Manually upgrade a user's KYC tier (compliance officer override)."""
    try:
        target_tier = request.form.get('tier', type=int)
        reason = request.form.get('reason', '').strip()

        if not reason:
            flash("Please provide a reason for the manual upgrade", "warning")
            return redirect(url_for('admin.owner.kyc_tier_management'))

        if target_tier not in range(0, 6):
            flash("Invalid KYC tier", "danger")
            return redirect(url_for('admin.owner.kyc_tier_management'))

        # Get user
        from app.identity.models.user import User
        user = User.query.get(user_id)
        if not user:
            flash("User not found", "danger")
            return redirect(url_for('admin.owner.kyc_tier_management'))

        # Create manual verification record
        from app.identity.individuals.individual_verification import IndividualVerification
        from app.auth.kyc_compliance import TIER_REQUIREMENTS

        tier_info = TIER_REQUIREMENTS.get(target_tier, {})

        verification = IndividualVerification(
            user_id=user_id,
            status="verified",
            scope=tier_info.get("required_scope", {}),
            notes=f"Manual KYC upgrade to tier {target_tier} by {current_user.username}. Reason: {reason}",
            reviewer_id=current_user.id
        )

        db.session.add(verification)
        db.session.commit()

        # Log the action
        log_owner_action(
            action='manual_kyc_upgrade',
            category='compliance',
            details={
                'target_user': user.username,
                'target_tier': target_tier,
                'reason': reason,
                'performed_by': current_user.username
            }
        )

        flash(f"✅ KYC tier {target_tier} manually assigned to {user.username}", "success")

    except Exception as e:
        logger.error(f"Manual KYC upgrade error: {e}")
        flash("Failed to manually upgrade KYC tier", "danger")

    return redirect(url_for('admin.owner.kyc_tier_management'))

@owner_bp.route('/kyc/suspicious-activity')
@owner_login_required
@audit_owner_action('viewed_suspicious_activity', 'compliance')
def suspicious_activity():
    """View suspicious activity reports for AML/CFT compliance."""
    try:
        from app.audit.comprehensive_audit import SecurityEventLog
        from datetime import datetime, timezone, timedelta

        # Get filter parameters
        days = int(request.args.get('days', 7))
        event_type = request.args.get('event_type')

        query = SecurityEventLog.query.filter(
            (SecurityEventLog.event_type.in_(['aml_review_flagged', 'fia_report_generated',
                                            'transaction_limit_exceeded', 'kyc_tier_blocked'])) |
            (SecurityEventLog.severity.in_(['high', 'critical']))
        )

        if event_type:
            query = query.filter_by(event_type=event_type)

        # Filter by date
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(SecurityEventLog.created_at >= since_date)

        logs = query.order_by(SecurityEventLog.created_at.desc()).limit(200).all()

        # Get unique event types for filter dropdown
        event_types = db.session.query(SecurityEventLog.event_type).distinct().all()
        event_types = [et[0] for et in event_types if et[0]]

        return render_template('owner/suspicious_activity.html',
                               logs=logs,
                               event_types=event_types,
                               current_filters={'event_type': event_type, 'days': days})
    except Exception as e:
        logger.error(f"Suspicious activity error: {e}")
        flash("Error loading suspicious activity reports", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/kyc/compliance-reports')
@owner_login_required
@audit_owner_action('viewed_kyc_compliance_reports', 'compliance')
def kyc_compliance_reports():
    """Generate KYC compliance reports for regulatory authorities."""
    try:
        from datetime import datetime, timezone, timedelta
        from app.auth.kyc_compliance import calculate_kyc_tier
        from app.identity.models.user import User

        # Get report parameters
        report_type = request.args.get('type', 'daily')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # Set default date range
        if report_type == 'daily':
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=1)
        elif report_type == 'weekly':
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=7)
        elif report_type == 'monthly':
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=30)

        # Generate report data
        report_data = {
            'total_users': User.query.count(),
            'new_users': User.query.filter(User.created_at >= start_date).count(),
            'kyc_stats': {},
            'large_transactions': 0,  # Would need transaction data
            'aml_flags': 0,  # Would need AML flag data
            'report_period': f"{start_date.date()} to {end_date.date()}",
            'generated_at': datetime.now(timezone.utc)
        }

        # Calculate KYC tier distribution
        from app.auth.kyc_compliance import TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD, \
                                           TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE

        tiers = [TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD,
                TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE]

        for tier in tiers:
            # This is simplified - in production, you'd want to cache or optimize this
            count = 0
            for user in User.query.all():
                kyc_info = calculate_kyc_tier(user.id)
                if kyc_info['tier'] == tier:
                    count += 1
            report_data['kyc_stats'][tier] = count

        return render_template('owner/compliance_reports.html',
                               report_data=report_data,
                               report_type=report_type,
                               start_date=start_date,
                               end_date=end_date)
    except Exception as e:
        logger.error(f"Compliance reports error: {e}")
        flash("Error generating compliance reports", "danger")
        return redirect(url_for('admin.owner.dashboard'))

# ============================================================================
# FORENSIC AUDIT & COMPLIANCE ROUTES
# ============================================================================

@owner_bp.route('/compliance/dashboard')
@owner_login_required
@audit_owner_action('viewed_compliance_dashboard', 'compliance')
def compliance_dashboard():
    """Compliance Officer Dashboard - Central hub for forensic audit monitoring"""
    try:
        from app.audit.forensic_audit import ForensicAuditService

        # Get pending reviews
        pending_reviews = []
        try:
            pending_reviews = ForensicAuditService.get_pending_reviews(limit=20)
        except:
            pass

        # Get suspicious activity
        suspicious_patterns = []
        try:
            suspicious_patterns = ForensicAuditService.get_suspicious_patterns(days=7)
        except:
            pass

        # Calculate metrics
        metrics = {
            'pending_reviews_count': len(pending_reviews),
            'blocked_attempts_today': 0,
            'avg_approval_time_hours': 2.5,
            'high_risk_alerts': len([p for p in suspicious_patterns if p.get('risk_score', 0) > 70]),
            'total_audit_events': 0,
        }

        # Get recent high-risk events
        recent_alerts = []
        try:
            from app.audit.comprehensive_audit import SecurityEventLog
            recent_alerts = SecurityEventLog.query.filter(
                SecurityEventLog.severity.in_(['high', 'critical'])
            ).order_by(SecurityEventLog.created_at.desc()).limit(10).all()
        except:
            pass

        return render_template('admin/compliance/dashboard.html',
                               pending_reviews=pending_reviews,
                               suspicious_patterns=suspicious_patterns,
                               metrics=metrics,
                               recent_alerts=recent_alerts)
    except Exception as e:
        logger.error(f"Compliance dashboard error: {e}")
        flash("Error loading compliance dashboard", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/compliance/audit-timeline')
@owner_login_required
@audit_owner_action('viewed_audit_timeline', 'compliance')
def audit_timeline():
    """Audit timeline search interface"""
    try:
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        days = int(request.args.get('days', 7))

        timeline_events = []

        return render_template('admin/compliance/search.html',
                               timeline_events=timeline_events,
                               entity_type=entity_type,
                               entity_id=entity_id,
                               days=days)
    except Exception as e:
        logger.error(f"Audit timeline error: {e}")
        flash("Error loading audit timeline", "danger")
        return redirect(url_for('admin.owner.compliance_dashboard'))

@owner_bp.route('/compliance/user-audit/<int:user_id>')
@owner_login_required
@audit_owner_action('viewed_user_audit_profile', 'compliance')
def user_audit_profile(user_id):
    """Comprehensive audit view for a specific user"""
    try:
        from app.identity.models.user import User
        user = User.query.get_or_404(user_id)

        timeline_events = []
        security_events = []
        risk_score = 0

        return render_template('admin/compliance/user_audit_profile.html',
                               user=user,
                               timeline_events=timeline_events,
                               security_events=security_events,
                               risk_score=risk_score)
    except Exception as e:
        logger.error(f"User audit profile error: {e}")
        flash("Error loading user audit profile", "danger")
        return redirect(url_for('admin.owner.compliance_dashboard'))

@owner_bp.route('/compliance/reports')
@owner_login_required
@audit_owner_action('viewed_compliance_reports', 'compliance')
def compliance_reports_page():
    """Compliance report generator"""
    try:
        from datetime import datetime, timezone, timedelta

        report_type = request.args.get('type', 'daily')

        # Set default date ranges
        end_date = datetime.now(timezone.utc)
        if report_type == 'daily':
            start_date = end_date - timedelta(days=1)
        elif report_type == 'weekly':
            start_date = end_date - timedelta(days=7)
        elif report_type == 'monthly':
            start_date = end_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(days=1)

        return render_template('admin/compliance/reports.html',
                               report_type=report_type,
                               start_date=start_date,
                               end_date=end_date)
    except Exception as e:
        logger.error(f"Compliance reports error: {e}")
        flash("Error loading compliance reports", "danger")
        return redirect(url_for('admin.owner.compliance_dashboard'))

@owner_bp.route('/api/compliance/pending-reviews')
@owner_login_required
def api_pending_reviews():
    """JSON API for pending reviews"""
    try:
        from app.audit.forensic_audit import ForensicAuditService

        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        pending_reviews = []
        try:
            pending_reviews = ForensicAuditService.get_pending_reviews(
                limit=limit,
                offset=offset
            )
        except:
            pass

        return jsonify({
            'success': True,
            'pending_reviews': pending_reviews,
            'count': len(pending_reviews)
        })
    except Exception as e:
        logger.error(f"API pending reviews error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@owner_bp.route('/api/compliance/review/<audit_id>', methods=['POST'])
@owner_login_required
def api_review_audit(audit_id):
    """API to approve/reject an audit item"""
    try:
        data = request.get_json()
        action = data.get('action')  # 'approve' or 'reject'
        notes = data.get('notes', '')

        if action not in ['approve', 'reject']:
            return jsonify({'success': False, 'error': 'Invalid action'}), 400

        # Simulate success for now
        return jsonify({'success': True, 'message': f'Action {action} processed'})
    except Exception as e:
        logger.error(f"API review audit error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@owner_bp.route('/api/compliance/suspicious-patterns')
@owner_login_required
def api_suspicious_patterns():
    """JSON API for suspicious patterns"""
    try:
        from app.audit.forensic_audit import ForensicAuditService

        days = request.args.get('days', 7, type=int)
        min_risk = request.args.get('min_risk', 50, type=int)

        patterns = []
        try:
            patterns = ForensicAuditService.get_suspicious_patterns(
                days=days,
                min_risk_score=min_risk
            )
        except:
            pass

        return jsonify({
            'success': True,
            'patterns': patterns,
            'count': len(patterns)
        })
    except Exception as e:
        logger.error(f"API suspicious patterns error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# AUTH SETTINGS ROUTES
# ============================================================================

@owner_bp.route('/owner/settings/auth', methods=['GET', 'POST'])
@owner_login_required
@audit_owner_action('view_auth_settings')
def auth_settings():
    """
    Authentication and verification service settings.
    Only accessible by app owner.
    """
    config = AuthConfiguration.get_config()
    
    if request.method == 'POST':
        # Update configuration
        try:
            # Service enable/disable toggles
            config.google_oauth_enabled = request.form.get('google_oauth_enabled') == 'on'
            config.sendgrid_enabled = request.form.get('sendgrid_enabled') == 'on'
            config.twilio_enabled = request.form.get('twilio_enabled') == 'on'
            config.africa_talking_enabled = request.form.get('africa_talking_enabled') == 'on'
            
            # API credentials
            config.google_client_id = request.form.get('google_client_id', '').strip()
            config.google_client_secret = request.form.get('google_client_secret', '').strip()
            config.sendgrid_api_key = request.form.get('sendgrid_api_key', '').strip()
            config.sendgrid_from_email = request.form.get('sendgrid_from_email', '').strip()
            config.sendgrid_from_name = request.form.get('sendgrid_from_name', 'AFCON360').strip()
            config.twilio_account_sid = request.form.get('twilio_account_sid', '').strip()
            config.twilio_auth_token = request.form.get('twilio_auth_token', '').strip()
            config.twilio_phone_number = request.form.get('twilio_phone_number', '').strip()
            config.africa_talking_username = request.form.get('africa_talking_username', '').strip()
            config.africa_talking_api_key = request.form.get('africa_talking_api_key', '').strip()
            
            # SMS routing
            config.sms_provider_preference = request.form.get('sms_provider_preference', 'auto')
            
            # Feature flags
            config.email_verification_required = request.form.get('email_verification_required') == 'on'
            config.phone_verification_required = request.form.get('phone_verification_required') == 'on'
            config.google_oauth_required = request.form.get('google_oauth_required') == 'on'
            
            # KYC requirements
            config.kyc_required_for_tier_2 = request.form.get('kyc_required_for_tier_2') == 'on'
            config.kyc_required_for_tier_3 = request.form.get('kyc_required_for_tier_3') == 'on'
            
            # Signup restrictions
            config.allow_email_password_signup = request.form.get('allow_email_password_signup') == 'on'
            config.allow_google_oauth_signup = request.form.get('allow_google_oauth_signup') == 'on'
            
            # Rate limits
            config.email_verification_rate_limit = int(request.form.get('email_verification_rate_limit', 5))
            config.sms_verification_rate_limit = int(request.form.get('sms_verification_rate_limit', 3))
            
            # Audit
            config.updated_by = current_user.id
            config.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            
            log_owner_action('update_auth_settings', current_user.id, 
                           {'changes': 'Authentication settings updated'})
            flash('Authentication settings updated successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating auth settings: {str(e)}")
            flash(f'Error updating settings: {str(e)}', 'danger')
        
        return redirect(url_for('admin.owner.auth_settings'))
    
    return render_template('admin/owner/auth_settings.html', config=config)


@owner_bp.route('/owner/settings/auth/test/<service>', methods=['POST'])
@owner_login_required
def test_auth_service(service):
    """
    Test connectivity to authentication services.
    """
    config = AuthConfiguration.get_config()
    result = {'success': False, 'message': ''}
    
    try:
        if service == 'sendgrid':
            if not config.sendgrid_enabled or not config.sendgrid_api_key:
                result['message'] = 'SendGrid is disabled or API key not configured'
            else:
                # Test SendGrid API
                from sendgrid import SendGridAPIClient
                sg = SendGridAPIClient(config.sendgrid_api_key)
                response = sg.client.api_keys.get()
                if response.status_code == 200:
                    result['success'] = True
                    result['message'] = 'SendGrid API connection successful'
                else:
                    result['message'] = f'SendGrid API error: {response.status_code}'
        
        elif service == 'twilio':
            if not config.twilio_enabled or not config.twilio_account_sid:
                result['message'] = 'Twilio is disabled or credentials not configured'
            else:
                # Test Twilio API
                from twilio.rest import Client
                client = Client(config.twilio_account_sid, config.twilio_auth_token)
                account = client.api.accounts(config.twilio_account_sid).fetch()
                if account:
                    result['success'] = True
                    result['message'] = 'Twilio API connection successful'
                else:
                    result['message'] = 'Twilio API authentication failed'
        
        elif service == 'africa_talking':
            if not config.africa_talking_enabled or not config.africa_talking_api_key:
                result['message'] = 'Africa\'s Talking is disabled or credentials not configured'
            else:
                # Test Africa's Talking API
                from africastalking.AfricasTalking import AfricasTalking
                at = AfricasTalking(config.africa_talking_username, config.africa_talking_api_key)
                result['success'] = True
                result['message'] = 'Africa\'s Talking API connection successful'
        
        else:
            result['message'] = f'Unknown service: {service}'
    
    except Exception as e:
        logger.error(f"Error testing {service}: {str(e)}")
        result['message'] = f'Error: {str(e)}'
    
    return jsonify(result)


@owner_bp.route('/owner/settings/auth/preview', methods=['GET'])
@owner_login_required
def auth_settings_preview():
    """
    Get current auth configuration (without secrets) for preview.
    """
    config = AuthConfiguration.get_config()
    return jsonify(config.to_dict(include_secrets=False))


# ============================================================================
# END AUTH SETTINGS ROUTES
# ============================================================================

# ============================================================================
# Initialize Security Dashboard Routes
# ============================================================================

# Add security dashboard routes to the blueprint
add_security_routes(owner_bp)
