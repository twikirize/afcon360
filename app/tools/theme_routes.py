from flask import Blueprint, jsonify, request, render_template, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models.theme import UserThemePreference, GlobalTheme, EventTheme
from app.tools.theme_service import ThemeService
from app.identity.models.user import User
# Import Event if needed, assuming app.events.models.Event exists

theme_bp = Blueprint('theme', __name__, url_prefix='/theme')

@theme_bp.route('/api/preferences', methods=['GET'])
@login_required
def get_user_preferences():
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
    ThemeService.update_user_theme_css(current_user.id)
    return jsonify({"success": True, "message": "Preferences saved"})

@theme_bp.route('/api/global', methods=['GET'])
def get_global_theme():
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
    ThemeService.update_global_theme_css()
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
    return jsonify({"success": True, "message": "Preferences reset"})
