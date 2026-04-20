# app/admin/__init__.py
"""
Admin module - General administration and role-based dashboards
Includes: Owner, Moderator, Compliance, Support, Auditor dashboards
"""

from flask import Blueprint
import logging

logger = logging.getLogger(__name__)

# Main admin blueprint
admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates"
)

# Import regular admin routes
from app.admin import routes

# ============================================
# REGISTER ALL ROLE-BASED DASHBOARDS
# (All are subdirectories under app/admin/)
# ============================================

# 1. Owner dashboard (highest privilege)
try:
    from app.admin.owner import owner_bp
    admin_bp.register_blueprint(owner_bp)
    logger.info("✅ Registered owner blueprint")
except ImportError as e:
    logger.warning(f"⚠️ Owner module not available: {e}")

# 2. Moderator dashboard (content & user moderation)
try:
    from app.admin.moderator import moderator_bp
    admin_bp.register_blueprint(moderator_bp)
    logger.info("✅ Registered moderator blueprint")
except ImportError as e:
    logger.warning(f"⚠️ Moderator module not available: {e}")

# 3. Compliance dashboard (KYC, AML, risk management)
try:
    from app.admin.compliance import compliance_bp
    admin_bp.register_blueprint(compliance_bp)
    logger.info("✅ Registered compliance blueprint")
except ImportError as e:
    logger.warning(f"⚠️ Compliance module not available: {e}")

# 4. Support dashboard (user support, KYC assistance)
try:
    from app.admin.support import support_bp
    admin_bp.register_blueprint(support_bp)
    logger.info("✅ Registered support blueprint")
except ImportError as e:
    logger.warning(f"⚠️ Support module not available: {e}")

# 5. Auditor dashboard (forensic logs, compliance auditing)
try:
    from app.admin.auditor import auditor_bp
    admin_bp.register_blueprint(auditor_bp)
    logger.info("✅ Registered auditor blueprint")
except ImportError as e:
    logger.warning(f"⚠️ Auditor module not available: {e}")

# ============================================
# IMPORT MODELS FOR ALEMBIC
# ============================================
from app.admin import models  # noqa: F401, E402

# ============================================
# EXPORT BLUEPRINT
# ============================================
__all__ = ["admin_bp"]
