import os
from flask import current_app
from app.models.theme import GlobalTheme, UserThemePreference, EventTheme

class ThemeService:
    @staticmethod
    def generate_css_content(settings):
        """Generates CSS variable overrides based on settings map."""
        lines = [":root {"]
        for key, value in settings.items():
            # Basic validation/sanitization could be added here
            lines.append(f"  --{key}: {value};")
        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def ensure_generated_dir():
        generated_path = os.path.join(current_app.static_folder, 'css', 'generated')
        if not os.path.exists(generated_path):
            os.makedirs(generated_path)
        return generated_path

    @classmethod
    def update_global_theme_css(cls):
        """Generates static/css/generated/global-theme.css from DB settings."""
        active_theme = GlobalTheme.query.filter_by(is_active=True).first()
        if not active_theme:
            return ""

        content = cls.generate_css_content(active_theme.settings)
        dir_path = cls.ensure_generated_dir()
        file_path = os.path.join(dir_path, 'global-theme.css')

        with open(file_path, 'w') as f:
            f.write(content)

        return content

    @classmethod
    def update_user_theme_css(cls, user_id):
        """Generates static/css/generated/user-{user_id}.css for a user."""
        pref = UserThemePreference.query.get(user_id)
        if not pref:
            return ""

        # Only map settings that should be in CSS variables
        css_vars = {}
        if 'fontScale' in pref.settings:
            css_vars['user-font-scale'] = pref.settings['fontScale']
        if 'lineHeight' in pref.settings:
            css_vars['user-line-height'] = pref.settings['lineHeight']

        # Add color overrides if user has specific color settings
        # ...

        content = cls.generate_css_content(css_vars)
        dir_path = cls.ensure_generated_dir()
        file_path = os.path.join(dir_path, f'user-{user_id}.css')

        with open(file_path, 'w') as f:
            f.write(content)

        return content
