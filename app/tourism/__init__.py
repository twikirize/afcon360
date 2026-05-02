# app/tourism/__init__.py
from flask import Blueprint

tourism_bp = Blueprint(
    "tourism",
    __name__,
    url_prefix="/tourism",
    template_folder="templates"
)

from app.tourism import routes  # noqa: F401,E402

# Register with moderator system
try:
    from app.admin.moderator.registry import register_module
    from flask import url_for
    register_module('tourism_listing', 'Tourism Attraction',
                   review_url_fn=lambda id: url_for('tourism.moderate_listing', id=id),
                   module_name='Tourism', icon='fa-tree')
except Exception:
    pass

"""
#version 1
from flask import Blueprint

tourism_bp = Blueprint(
    "tourism",
    __name__,
    url_prefix="/tourism",
    template_folder="templates",
    static_folder="static",
)

# Import routes module and register its handlers onto tourism_bp
from app.tourism import routes  # noqa: E402,F401
routes.register_routes(tourism_bp) """
