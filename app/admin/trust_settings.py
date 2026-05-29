# app/admin/routes/trust_settings.py
"""
Trust-based security settings routes for owner/super admin dashboard
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.events.settings_model import EventSettings
from app.events.trust_service import EventTrustService
from app.auth.decorators import require_role
from app.extensions import db

trust_settings_bp = Blueprint('trust_settings', __name__)


@trust_settings_bp.route('/trust-settings')
@login_required
@require_role('owner', 'super_admin', 'admin')
def trust_settings():
    """Trust-based security settings page"""
    settings = EventSettings.get()
    
    # Get sample trust analysis for demonstration
    from app.identity.models.user import User
    sample_users = User.query.limit(5).all()
    user_analyses = []
    
    for user in sample_users:
        analysis = EventTrustService.get_trust_analysis(user)
        user_analyses.append(analysis)
    
    return render_template('admin/trust_settings.html', 
                         settings=settings, 
                         user_analyses=user_analyses)


@trust_settings_bp.route('/trust-settings/update', methods=['POST'])
@login_required
@require_role('owner', 'super_admin', 'admin')
def update_trust_settings():
    """Update trust-based security settings"""
    settings = EventSettings.get()
    
    try:
        # Boolean toggles
        settings.enable_trust_based_publishing = request.form.get('enable_trust_based_publishing') == 'on'
        settings.enable_role_bypass = request.form.get('enable_role_bypass') == 'on'
        settings.enable_kyc_boost = request.form.get('enable_kyc_boost') == 'on'
        settings.enable_account_age_boost = request.form.get('enable_account_age_boost') == 'on'
        settings.enable_event_history_boost = request.form.get('enable_event_history_boost') == 'on'
        
        # Threshold values
        settings.high_trust_threshold = int(request.form.get('high_trust_threshold', 70))
        settings.medium_trust_threshold = int(request.form.get('medium_trust_threshold', 40))
        
        # Validate thresholds
        if settings.high_trust_threshold < settings.medium_trust_threshold:
            error_msg = 'High trust threshold must be greater than medium trust threshold'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': error_msg})
            flash(error_msg, 'danger')
            return redirect(url_for('trust_settings.trust_settings'))
        
        if not (0 <= settings.high_trust_threshold <= 100):
            error_msg = 'High trust threshold must be between 0 and 100'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': error_msg})
            flash(error_msg, 'danger')
            return redirect(url_for('trust_settings.trust_settings'))
        
        if not (0 <= settings.medium_trust_threshold <= 100):
            error_msg = 'Medium trust threshold must be between 0 and 100'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': error_msg})
            flash(error_msg, 'danger')
            return redirect(url_for('trust_settings.trust_settings'))
        
        # Save settings
        success, error = settings.save(updated_by_id=current_user.id)
        
        if success:
            success_msg = 'Trust-based security settings updated successfully'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': success_msg})
            flash(success_msg, 'success')
        else:
            error_msg = f'Error updating settings: {error}'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': error_msg})
            flash(error_msg, 'danger')
            
    except ValueError as e:
        error_msg = f'Invalid input: {str(e)}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': error_msg})
        flash(error_msg, 'danger')
    except Exception as e:
        error_msg = f'Error updating settings: {str(e)}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': error_msg})
        flash(error_msg, 'danger')
    
    return redirect(url_for('trust_settings.trust_settings'))


@trust_settings_bp.route('/trust-settings/reset', methods=['POST'])
@login_required
@require_role('owner', 'super_admin')
def reset_trust_settings():
    """Reset trust settings to defaults"""
    settings = EventSettings.get()
    
    try:
        # Reset to default values
        settings.enable_trust_based_publishing = True
        settings.enable_role_bypass = True
        settings.enable_kyc_boost = True
        settings.enable_account_age_boost = True
        settings.enable_event_history_boost = True
        settings.high_trust_threshold = 70
        settings.medium_trust_threshold = 40
        
        success, error = settings.save(updated_by_id=current_user.id)
        
        if success:
            flash('Trust settings reset to defaults', 'success')
        else:
            flash(f'Error resetting settings: {error}', 'danger')
            
    except Exception as e:
        flash(f'Error resetting settings: {str(e)}', 'danger')
    
    return redirect(url_for('trust_settings.trust_settings'))


@trust_settings_bp.route('/trust-settings/analyze-user/<int:user_id>')
@login_required
@require_role('owner', 'super_admin', 'admin')
def analyze_user_trust(user_id):
    """Get detailed trust analysis for a specific user"""
    from app.identity.models.user import User
    
    user = User.query.get_or_404(user_id)
    analysis = EventTrustService.get_trust_analysis(user)
    
    return jsonify(analysis)


@trust_settings_bp.route('/trust-settings/test-thresholds', methods=['POST'])
@login_required
@require_role('owner', 'super_admin', 'admin')
def test_thresholds():
    """Test how different thresholds affect user trust levels"""
    try:
        high_threshold = int(request.form.get('high_threshold', 70))
        medium_threshold = int(request.form.get('medium_threshold', 40))
        
        if high_threshold < medium_threshold:
            return jsonify({'error': 'High threshold must be greater than medium threshold'})
        
        from app.identity.models.user import User
        users = User.query.limit(10).all()
        
        results = []
        for user in users:
            # Temporarily override thresholds for testing
            from app.events.settings_model import EventSettings
            original_settings = EventSettings.get()
            
            # Create temporary settings for testing
            class TempSettings:
                def __init__(self):
                    self.enable_trust_based_publishing = original_settings.enable_trust_based_publishing
                    self.enable_role_bypass = original_settings.enable_role_bypass
                    self.enable_kyc_boost = original_settings.enable_kyc_boost
                    self.enable_account_age_boost = original_settings.enable_account_age_boost
                    self.enable_event_history_boost = original_settings.enable_event_history_boost
                    self.high_trust_threshold = high_threshold
                    self.medium_trust_threshold = medium_threshold
            
            # Temporarily replace settings
            EventSettings._cached_instance = TempSettings()
            
            try:
                trust_level = EventTrustService.calculate_trust_level(user)
                should_auto, reason = EventTrustService.should_auto_publish(user, trust_level)
                
                results.append({
                    'username': user.username,
                    'trust_level': trust_level,
                    'should_auto_publish': should_auto,
                    'reason': reason
                })
            finally:
                # Restore original settings
                EventSettings._cached_instance = original_settings
        
        return jsonify({'results': results})
        
    except Exception as e:
        return jsonify({'error': str(e)})
