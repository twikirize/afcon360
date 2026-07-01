# app/media/__init__.py
"""
AFCON360 Unified Media Management Module

Resource-efficient design:
- Process images ONCE at upload (not on every request)
- Content-addressable storage (SHA-256 deduplication)
- No video storage - use YouTube/Vimeo URLs
- OCI Object Storage for production (S3-compatible, cheap)
- Local filesystem for development
- Admin-configurable settings via MediaSettings model
"""

from flask import Blueprint

media_bp = Blueprint(
    "media",
    __name__,
    url_prefix="/api/media",
    template_folder="../templates",
)

# Admin blueprint for media settings management
media_admin_bp = Blueprint(
    "media_admin",
    __name__,
    url_prefix="/admin/media",
    template_folder="../../templates",
)

from app.media.routes import *  # noqa: E402,F401
from app.media.admin_routes import *  # noqa: E402,F401
from app.media import models  # noqa: E402,F401
