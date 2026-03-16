# app/tourism/__init__.py
from flask import Blueprint

tourism_bp = Blueprint(
    "tourism",
    __name__,
    url_prefix="/tourism",
    template_folder="templates"
)

from app.tourism import routes  # noqa: F401,E402

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