# app/media/admin_routes.py
"""
Admin routes for managing media settings.
Accessible by: owner, super_admin, admin roles.
"""

from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required, current_user
from app.extensions import db, limiter
from app.media.settings_service import MediaSettingsService

media_admin_bp = Blueprint(
    'media_admin',
    __name__,
    url_prefix='/admin/media',
    template_folder='../../templates'
)


def _can_manage_settings() -> bool:
    """Check if current user can manage media settings.
    
    Owner always has access.
    Other roles must be explicitly authorized by the owner via MediaSettings.authorized_manager_roles.
    """
    if not current_user.is_authenticated:
        return False
    # Owner always has access
    if hasattr(current_user, 'is_app_owner') and current_user.is_app_owner():
        return True
    # Check owner-authorized roles from DB settings
    try:
        from app.media.models import MediaSettings
        settings = MediaSettings.get()
        authorized = settings.authorized_manager_roles or []
        # Get current user's role names
        user_role_names = set()
        if hasattr(current_user, 'role_names'):
            user_role_names = set(current_user.role_names)
        elif hasattr(current_user, 'roles'):
            for ur in current_user.roles:
                if hasattr(ur, 'role') and ur.role and hasattr(ur.role, 'name'):
                    user_role_names.add(ur.role.name)
        # Check if user has any authorized role
        return bool(user_role_names & set(authorized))
    except Exception:
        # If settings aren't available yet, deny access to non-owners
        return False


@media_admin_bp.route('/settings', methods=['GET'])
@login_required
def media_settings_page():
    """Render the media settings admin page."""
    if not _can_manage_settings():
        return jsonify({'error': 'Unauthorized'}), 403

    settings = MediaSettingsService.get_all()
    return render_template('admin/media_settings.html', settings=settings)


@media_admin_bp.route('/settings/api', methods=['GET'])
@login_required
def get_media_settings_api():
    """Get media settings as JSON for API consumers."""
    if not _can_manage_settings():
        return jsonify({'error': 'Unauthorized'}), 403

    settings = MediaSettingsService.get_all()
    return jsonify(settings)


@media_admin_bp.route('/settings', methods=['POST', 'PUT'])
@login_required
@limiter.limit("20 per minute")
def update_media_settings():
    """Update media settings."""
    if not _can_manage_settings():
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or request.form
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    success, error = MediaSettingsService.update(
        data=data,
        updated_by_id=current_user.id
    )

    if success:
        return jsonify({'success': True, 'message': 'Settings updated successfully'})
    else:
        return jsonify({'error': error or 'Failed to update settings'}), 500


@media_admin_bp.route('/settings/reset', methods=['POST'])
@login_required
def reset_media_settings():
    """Reset media settings to defaults."""
    if not _can_manage_settings():
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        from app.media.models import MediaSettings
        from app.extensions import db

        # Delete current settings row
        settings = MediaSettings.query.first()
        if settings:
            db.session.delete(settings)
            db.session.commit()

        # Clear cache
        MediaSettings.invalidate_cache()

        return jsonify({'success': True, 'message': 'Settings reset to defaults'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@media_admin_bp.route('/settings/authorized-roles', methods=['GET'])
@login_required
def get_authorized_roles_api():
    """Get list of roles authorized to manage media settings."""
    # Only owner can view/manage authorization
    if not (hasattr(current_user, 'is_app_owner') and current_user.is_app_owner()):
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        from app.media.models import MediaSettings
        settings = MediaSettings.get()
        return jsonify({
            'authorized_manager_roles': settings.authorized_manager_roles or []
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@media_admin_bp.route('/settings/authorized-roles', methods=['POST', 'PUT'])
@login_required
def update_authorized_roles_api():
    """Update which roles are authorized to manage media settings."""
    # Only owner can grant/revoke access
    if not (hasattr(current_user, 'is_app_owner') and current_user.is_app_owner()):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or request.form
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    authorized_roles = data.get('authorized_manager_roles', [])
    if not isinstance(authorized_roles, list):
        return jsonify({'error': 'authorized_manager_roles must be a list'}), 400

    try:
        from app.media.models import MediaSettings
        settings = MediaSettings.get()
        settings.authorized_manager_roles = authorized_roles
        db.session.commit()
        MediaSettings.invalidate_cache()
        return jsonify({'success': True, 'message': 'Authorized roles updated'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
