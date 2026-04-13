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

        # Map all settings that should be in CSS variables
        css_vars = {}
        settings = pref.settings

        # Map frontend keys to CSS variable names
        # font_scale -> user-font-scale
        if 'font_scale' in settings:
            css_vars['user-font-scale'] = settings['font_scale']

        # high_contrast -> user-high-contrast
        if 'high_contrast' in settings:
            css_vars['user-high-contrast'] = settings['high_contrast']

        # dyslexic_font -> user-dyslexic-font
        if 'dyslexic_font' in settings:
            css_vars['user-dyslexic-font'] = 'true' if settings['dyslexic_font'] else 'false'

        # color_blind_mode -> user-color-blind-mode
        if 'color_blind_mode' in settings:
            css_vars['user-color-blind-mode'] = settings['color_blind_mode']

        # dark_mode -> user-dark-mode
        if 'dark_mode' in settings:
            css_vars['user-dark-mode'] = settings['dark_mode']

        # reduced_motion -> user-reduced-motion
        if 'reduced_motion' in settings:
            css_vars['user-reduced-motion'] = 'true' if settings['reduced_motion'] else 'false'

        # reading_width -> user-reading-width
        if 'reading_width' in settings:
            css_vars['user-reading-width'] = settings['reading_width']

        # compact_mode -> user-compact-mode
        if 'compact_mode' in settings:
            css_vars['user-compact-mode'] = 'true' if settings['compact_mode'] else 'false'

        # custom_accent -> brand-primary (user override)
        if 'custom_accent' in settings and settings['custom_accent']:
            css_vars['brand-primary'] = settings['custom_accent']
            # Also generate RGB values
            try:
                # Convert hex to RGB
                hex_color = settings['custom_accent'].lstrip('#')
                if len(hex_color) == 6:
                    r = int(hex_color[0:2], 16)
                    g = int(hex_color[2:4], 16)
                    b = int(hex_color[4:6], 16)
                    css_vars['brand-primary-rgb'] = f"{r}, {g}, {b}"
            except:
                pass

        content = cls.generate_css_content(css_vars)
        dir_path = cls.ensure_generated_dir()
        file_path = os.path.join(dir_path, f'user-{user_id}.css')

        with open(file_path, 'w') as f:
            f.write(content)

        return content
