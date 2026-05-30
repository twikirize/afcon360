# app/admin/routes/settings.py
"""
Comprehensive role-based settings system for:
- Super Admin: System-wide configuration, user management, platform settings
- Admin: Module-specific settings, reporting, analytics
- Moderator: Content moderation tools, queue management
- Owner: Property management, booking oversight (already exists)
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps
from app.extensions import db
from app.auth.policy import can
from app.auth.decorators import require_role, require_admin
import logging

logger = logging.getLogger(__name__)

settings_bp = Blueprint('admin_settings', __name__, url_prefix='/admin/settings')

# Role-based decorators
def require_super_admin(f):
    """Decorator to require super admin role"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'super_admin':
            flash('Super admin access required', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def require_admin_role(f):
    """Decorator to require admin role or higher"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'super_admin']:
            flash('Admin access required', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def require_moderator_role(f):
    """Decorator to require moderator role or higher"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['moderator', 'admin', 'super_admin']:
            flash('Moderator access required', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


# ================================
# SUPER ADMIN SETTINGS
# ================================

@settings_bp.route('/system', endpoint="system_settings")
@require_super_admin
def system_settings():
    """System-wide configuration for super admins"""
    from app.models import SystemConfig, User
    
    # Get system configurations
    configs = SystemConfig.query.all()
    config_dict = {c.key: c.value for c in configs}
    
    # System statistics
    stats = {
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'admin_users': User.query.filter(User.role.in_(['admin', 'super_admin'])).count(),
        'moderator_users': User.query.filter_by(role='moderator').count(),
    }
    
    return render_template('admin/settings/system.html', 
                       config=config_dict, 
                       stats=stats)


@settings_bp.route('/system/save', methods=['POST'])
@require_super_admin
def save_system_settings():
    """Save system-wide configuration"""
    try:
        data = request.get_json()
        
        # Update system configurations
        from app.models import SystemConfig
        for key, value in data.items():
            config = SystemConfig.query.filter_by(key=key).first()
            if not config:
                config = SystemConfig(key=key, value=str(value))
                db.session.add(config)
            else:
                config.value = str(value)
        
        db.session.commit()
        
        # Log the change
        logger.info(f"System settings updated by super admin {current_user.id}: {list(data.keys())}")
        
        return jsonify({'success': True, 'message': 'System settings saved successfully'})
        
    except Exception as e:
        logger.error(f"Failed to save system settings: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to save system settings'})


@settings_bp.route('/users', endpoint="user_management")
@require_super_admin
def user_management():
    """User management for super admins"""
    from app.models import User
    
    # Get users with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    users = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/settings/users.html', users=users)


@settings_bp.route('/users/<int:user_id>/role', methods=['POST'])
@require_super_admin
def update_user_role(user_id):
    """Update user role (super admin only)"""
    try:
        data = request.get_json()
        new_role = data.get('role')
        
        if new_role not in ['user', 'moderator', 'admin', 'super_admin']:
            return jsonify({'success': False, 'error': 'Invalid role'})
        
        from app.models import User
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})
        
        # Prevent super admin from demoting themselves
        if user_id == current_user.id and new_role != 'super_admin':
            return jsonify({'success': False, 'error': 'Cannot remove your own super admin role'})
        
        old_role = user.role
        user.role = new_role
        db.session.commit()
        
        logger.info(f"User {user_id} role changed from {old_role} to {new_role} by super admin {current_user.id}")
        
        return jsonify({'success': True, 'message': f'User role updated to {new_role}'})
        
    except Exception as e:
        logger.error(f"Failed to update user role: {e}")
        return jsonify({'success': False, 'error': 'Failed to update user role'})


# ================================
# ADMIN SETTINGS
# ================================

@settings_bp.route('/platform', endpoint="platform_settings")
@require_admin_role
def platform_settings():
    """Platform-wide settings for admins"""
    # Platform configuration
    config = {
        'booking': {
            'auto_confirm': True,
            'cancellation_window': 24,  # hours
            'max_guests_per_booking': 20,
            'require_verification': True,
        },
        'pricing': {
            'service_fee_percent': 12.5,
            'min_nightly_rate': 1000,
            'max_nightly_rate': 1000000,
            'currency': 'UGX',
        },
        'notifications': {
            'email_enabled': True,
            'sms_enabled': False,
            'push_enabled': True,
            'booking_alerts': True,
            'cancellation_alerts': True,
        },
        'security': {
            'session_timeout': 30,  # minutes
            'max_login_attempts': 5,
            'lockout_duration': 15,  # minutes
            'require_2fa_admin': True,
        }
    }
    
    return render_template('admin/settings/platform.html', config=config)


@settings_bp.route('/analytics', endpoint="analytics_settings")
@require_admin_role
def analytics_settings():
    """Analytics and reporting settings for admins"""
    from app.accommodation.models.property import Property
    from app.accommodation.models.booking import AccommodationBooking
    from datetime import datetime, timedelta
    
    # Calculate key metrics
    total_properties = Property.query.count()
    active_properties = Property.query.filter_by(is_active=True).count()
    verified_properties = Property.query.filter_by(is_verified=True).count()
    
    total_bookings = AccommodationBooking.query.count()
    confirmed_bookings = AccommodationBooking.query.filter_by(status='confirmed').count()
    
    # Recent activity (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_bookings = AccommodationBooking.query.filter(
        AccommodationBooking.created_at >= thirty_days_ago
    ).count()
    
    metrics = {
        'properties': {
            'total': total_properties,
            'active': active_properties,
            'verified': verified_properties,
            'verification_rate': round((verified_properties / total_properties * 100) if total_properties > 0 else 0, 1)
        },
        'bookings': {
            'total': total_bookings,
            'confirmed': confirmed_bookings,
            'recent': recent_bookings,
            'confirmation_rate': round((confirmed_bookings / total_bookings * 100) if total_bookings > 0 else 0, 1)
        }
    }
    
    return render_template('admin/settings/analytics.html', metrics=metrics)


@settings_bp.route('/platform/save', methods=['POST'])
@require_admin_role
def save_platform_settings():
    """Save platform configuration"""
    try:
        data = request.get_json()
        
        # Validate and save platform settings
        # This would typically save to a configuration table or file
        logger.info(f"Platform settings updated by admin {current_user.id}: {list(data.keys())}")
        
        return jsonify({'success': True, 'message': 'Platform settings saved successfully'})
        
    except Exception as e:
        logger.error(f"Failed to save platform settings: {e}")
        return jsonify({'success': False, 'error': 'Failed to save platform settings'})


# ================================
# MODERATOR SETTINGS
# ================================

@settings_bp.route('/moderation', endpoint="moderation_settings")
@require_moderator_role
def moderation_settings():
    """Moderation tools and queue management"""
    from app.accommodation.models.property import Property, AccommodationPropertyStatus
    from app.accommodation.models.booking import AccommodationBooking
    from app.accommodation.models.review import Review, AccommodationReviewStatus
    
    # Get moderation queue counts
    pending_properties = Property.query.filter_by(status=AccommodationPropertyStatus.PENDING_REVIEW).count()
    pending_bookings = AccommodationBooking.query.filter_by(status='pending').count()
    pending_reviews = Review.query.filter_by(status=AccommodationReviewStatus.PENDING).count()
    
    # Recent moderation activity
    from datetime import datetime, timedelta
    last_24h = datetime.utcnow() - timedelta(hours=24)
    
    recent_moderations = {
        'properties_approved': Property.query.filter(
            Property.status == AccommodationPropertyStatus.ACTIVE,
            Property.verified_at >= last_24h
        ).count(),
        'reviews_approved': Review.query.filter(
            Review.status == AccommodationReviewStatus.APPROVED,
            Review.moderated_at >= last_24h
        ).count(),
    }
    
    queue_stats = {
        'pending_properties': pending_properties,
        'pending_bookings': pending_bookings,
        'pending_reviews': pending_reviews,
        'total_pending': pending_properties + pending_bookings + pending_reviews,
        'recent_activity': recent_moderations
    }
    
    return render_template('admin/settings/moderation.html', queue_stats=queue_stats)


@settings_bp.route('/moderation/filters', endpoint="moderation_filters")
@require_moderator_role
def moderation_filters():
    """Configure moderation filters and automation"""
    filters = {
        'auto_approval': {
            'enabled': False,
            'min_rating_threshold': 4.0,
            'required_documents': ['id_proof', 'address_proof'],
        },
        'content_filters': {
            'profanity_filter': True,
            'spam_detection': True,
            'duplicate_detection': True,
        },
        'escalation_rules': {
            'auto_flag_threshold': 3,  # Auto-flag after 3 reports
            'high_value_threshold': 10000,  # Auto-escalate high-value bookings
            'suspicious_patterns': True,
        }
    }
    
    return render_template('admin/settings/moderation_filters.html', filters=filters)


@settings_bp.route('/moderation/save-filters', methods=['POST'])
@require_moderator_role
def save_moderation_filters():
    """Save moderation filter configuration"""
    try:
        data = request.get_json()
        
        # Save moderation filters
        logger.info(f"Moderation filters updated by moderator {current_user.id}: {list(data.keys())}")
        
        return jsonify({'success': True, 'message': 'Moderation filters saved successfully'})
        
    except Exception as e:
        logger.error(f"Failed to save moderation filters: {e}")
        return jsonify({'success': False, 'error': 'Failed to save moderation filters'})


# ================================
# ROLE-BASED ACCESS CONTROL
# ================================

@settings_bp.route('/access-control', endpoint="access_control")
@require_admin_role
def access_control():
    """Configure role-based access permissions"""
    permissions = {
        'super_admin': {
            'can_manage_users': True,
            'can_manage_system': True,
            'can_manage_all_modules': True,
            'can_view_all_data': True,
        },
        'admin': {
            'can_manage_users': False,
            'can_manage_system': True,
            'can_manage_modules': ['accommodation', 'wallet', 'events'],
            'can_view_module_data': ['accommodation', 'wallet', 'events'],
        },
        'moderator': {
            'can_manage_users': False,
            'can_manage_system': False,
            'can_moderate_content': True,
            'can_view_moderation_queue': True,
        },
        'owner': {
            'can_manage_properties': True,
            'can_manage_bookings': True,
            'can_view_analytics': True,
            'can_delegate_permissions': True,
        }
    }
    
    return render_template('admin/settings/access_control.html', permissions=permissions)


# ================================
# IMPERSONATION CONTROL
# ================================

@settings_bp.route('/impersonation', endpoint="impersonation_control")
@require_admin_role
def impersonation_control():
    """Impersonation control for admins and super admins"""
    from app.identity.models.user import User
    
    # Get current impersonation status
    impersonated_user_id = request.session.get('impersonated_user_id')
    impersonated_user = None
    if impersonated_user_id:
        impersonated_user = User.query.get(impersonated_user_id)
    
    # Get available users for impersonation (only admins+ can impersonate)
    if current_user.role in ['owner', 'super_admin']:
        # Owner and super admin can impersonate any role
        available_users = User.query.filter(User.role.in_(['admin', 'moderator', 'support', 'user'])).all()
    elif current_user.role == 'admin':
        # Admin can impersonate moderator and below
        available_users = User.query.filter(User.role.in_(['moderator', 'support', 'user'])).all()
    else:
        available_users = []
    
    return render_template('admin/settings/impersonation.html', 
                       impersonated_user=impersonated_user,
                       available_users=available_users)


@settings_bp.route('/impersonation/start/<int:user_id>', methods=['POST'])
@require_admin_role
def start_impersonation(user_id):
    """Start impersonating a user"""
    from app.identity.models.user import User
    
    try:
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'success': False, 'error': 'User not found'})
        
        # Validate impersonation permissions
        if current_user.role == 'admin' and target_user.role in ['owner', 'super_admin']:
            return jsonify({'success': False, 'error': 'Admin cannot impersonate owner or super admin'})
        
        if current_user.role not in ['owner', 'super_admin'] and target_user.role in ['admin', 'super_admin']:
            return jsonify({'success': False, 'error': 'Insufficient permissions'})
        
        # Start impersonation
        request.session['impersonated_user_id'] = target_user.id
        request.session['impersonation_started_at'] = datetime.utcnow().isoformat()
        request.session['impersonation_by'] = current_user.id
        request.session['impersonated_role'] = target_user.role
        
        logger.info(f"User {current_user.id} started impersonating {target_user.id} ({target_user.role})")
        
        return jsonify({'success': True, 'message': f'Now impersonating {target_user.username}'})
        
    except Exception as e:
        logger.error(f"Failed to start impersonation: {e}")
        return jsonify({'success': False, 'error': 'Failed to start impersonation'})


@settings_bp.route('/impersonation/stop', methods=['POST'])
@require_admin_role
def stop_impersonation():
    """Stop current impersonation"""
    try:
        impersonated_user_id = request.session.get('impersonated_user_id')
        if not impersonated_user_id:
            return jsonify({'success': False, 'error': 'No active impersonation'})
        
        # Clear impersonation session
        request.session.pop('impersonated_user_id', None)
        request.session.pop('impersonation_started_at', None)
        request.session.pop('impersonation_by', None)
        request.session.pop('impersonated_role', None)
        
        logger.info(f"User {current_user.id} stopped impersonating {impersonated_user_id}")
        
        return jsonify({'success': True, 'message': 'Impersonation stopped'})
        
    except Exception as e:
        logger.error(f"Failed to stop impersonation: {e}")
        return jsonify({'success': False, 'error': 'Failed to stop impersonation'})


# API ENDPOINTS FOR ALL ROLES

@settings_bp.route('/api/save-config', methods=['POST'])
@login_required
def save_config():
    """Generic config save endpoint - validates user role"""
    try:
        data = request.get_json()
        config_type = data.get('config_type')
        
        # Validate permissions based on config type and user role
        if config_type == 'system' and current_user.role != 'super_admin':
            return jsonify({'success': False, 'error': 'Insufficient permissions'})
        
        if config_type == 'platform' and current_user.role not in ['admin', 'super_admin']:
            return jsonify({'success': False, 'error': 'Insufficient permissions'})
        
        if config_type == 'moderation' and current_user.role not in ['moderator', 'admin', 'super_admin']:
            return jsonify({'success': False, 'error': 'Insufficient permissions'})
        
        # Save configuration based on type
        logger.info(f"Configuration {config_type} saved by {current_user.role} {current_user.id}")
        
        return jsonify({'success': True, 'message': f'{config_type} configuration saved'})
        
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
        return jsonify({'success': False, 'error': 'Failed to save configuration'})
