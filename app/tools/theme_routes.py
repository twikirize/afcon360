import os
from flask import Blueprint, jsonify, request, render_template, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models.theme import UserThemePreference, GlobalTheme, EventTheme
from app.tools.theme_service import ThemeService
from app.identity.models.user import User
# Import Event if needed, assuming app.events.models.Event exists

theme_bp = Blueprint('theme', __name__, url_prefix='/theme')

@theme_bp.context_processor
def inject_theme_context():
    from flask_login import current_user
    return {
        'user_authenticated': current_user.is_authenticated
    }

@theme_bp.route('/preferences')
@login_required
def preferences_page():
    return render_template('user/preferences.html')

@theme_bp.route('/api/preferences', methods=['GET'])
def get_user_preferences():
    # Check if user is authenticated
    if not current_user.is_authenticated:
        # Return default preferences for guests
        return jsonify({
            "font_scale": 1.0,
            "high_contrast": "off",
            "dyslexic_font": False,
            "color_blind_mode": "none",
            "dark_mode": "system",
            "reduced_motion": False,
            "reading_width": "full",
            "compact_mode": False
        })

    pref = UserThemePreference.query.get(current_user.id)
    if pref:
        return jsonify(pref.settings)
    return jsonify({
        "font_scale": 1.0,
        "high_contrast": "off",
        "dyslexic_font": False,
        "color_blind_mode": "none",
        "dark_mode": "system",
        "reduced_motion": False,
        "reading_width": "full",
        "compact_mode": False
    })

@theme_bp.route('/preferences/save', methods=['POST'])
@login_required
def save_user_preferences():
    data = request.json
    pref = UserThemePreference.query.get(current_user.id)
    if not pref:
        pref = UserThemePreference(user_id=current_user.id)
        db.session.add(pref)

    pref.settings = data
    db.session.commit()

    # Update the generated CSS file
    try:
        ThemeService.update_user_theme_css(current_user.id)
    except Exception as e:
        current_app.logger.error(f"Failed to update user theme CSS: {e}")
        # Don't fail the request, just log the error

    return jsonify({"success": True, "message": "Preferences saved"})

@theme_bp.route('/api/global', methods=['GET'])
def get_global_theme():
    # Allow both authenticated and non-authenticated access for global theme
    active_theme = GlobalTheme.query.filter_by(is_active=True).first()
    if active_theme:
        return jsonify(active_theme.settings)
    return jsonify({})

@theme_bp.route('/admin/global/save', methods=['POST'])
@login_required
def save_global_theme():
    if not current_user.has_global_role('admin'):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    active_theme = GlobalTheme.query.filter_by(is_active=True).first()
    if not active_theme:
        active_theme = GlobalTheme(name="Global Theme", is_active=True)
        db.session.add(active_theme)

    active_theme.settings = data
    db.session.commit()

    # Update the global theme CSS
    try:
        ThemeService.update_global_theme_css()
    except Exception as e:
        current_app.logger.error(f"Failed to update global theme CSS: {e}")

    return jsonify({"success": True, "message": "Global theme saved"})

@theme_bp.route('/event/<int:event_id>/api', methods=['GET'])
def get_event_theme(event_id):
    event_theme = EventTheme.query.get(event_id)
    if event_theme:
        return jsonify(event_theme.settings)
    return jsonify({"use_global_branding": True})

@theme_bp.route('/event/<int:event_id>/save', methods=['POST'])
@login_required
def save_event_theme(event_id):
    # Add organizer check here if applicable
    data = request.json
    event_theme = EventTheme.query.get(event_id)
    if not event_theme:
        event_theme = EventTheme(event_id=event_id)
        db.session.add(event_theme)

    event_theme.settings = data
    db.session.commit()
    return jsonify({"success": True, "message": "Event theme saved"})

@theme_bp.route('/reset', methods=['POST'])
@login_required
def reset_preferences():
    pref = UserThemePreference.query.get(current_user.id)
    if pref:
        db.session.delete(pref)
        db.session.commit()
        # Try to remove the generated CSS file
        try:
            generated_dir = ThemeService.ensure_generated_dir()
            file_path = os.path.join(generated_dir, f'user-{current_user.id}.css')
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            current_app.logger.error(f"Failed to remove user theme CSS: {e}")
    return jsonify({"success": True, "message": "Preferences reset"})
