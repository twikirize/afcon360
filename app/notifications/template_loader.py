"""
Jinja2 Template Loader & Renderer for Notifications
"""

from jinja2 import Environment, FileSystemLoader, select_autoescape
import os

class TemplateLoader:
    def __init__(self, templates_dir=None):
        if not templates_dir:
            templates_dir = os.path.join(
                os.path.dirname(__file__), '..', '..', 'templates', 'notifications'
            )
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

    def render_template(self, template_path: str, context: dict) -> str:
        try:
            template = self.env.get_template(template_path)
            return template.render(**context)
        except Exception:
            # Fallback string interpolation if template file not present
            return f"Notification context: {context}"

template_loader = TemplateLoader()
