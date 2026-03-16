# app/accommodation/__init__.py
from flask import Blueprint

accommodation_bp = Blueprint(
    "accommodation",
    __name__,
    url_prefix="/accommodation",
    template_folder="templates"
)

from app.accommodation import routes  # noqa: F401,E402


"""
#version 2


from flask import Blueprint

accommodation_bp = Blueprint(
    "accommodation",
    __name__,
    url_prefix="/accommodation",
    template_folder="templates",
    static_folder="static"
)

from app.accommodation import routes  # noqa: E402,F401"""