"""AFCON360 Feed Blueprint."""

from flask import Blueprint

feed_bp = Blueprint("feed", __name__, url_prefix="/api/home")

# Import routes to register them on the blueprint
from app.feed import routes  # noqa: E402, F401
