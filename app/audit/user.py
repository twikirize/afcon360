# app/audit/user.py
"""
Re-exports AuditLog from the canonical models module.
All audit logic lives in app.audit.models to avoid duplicate SQLAlchemy table registration.
"""

from app.audit.models import AuditLog  # noqa: F401  — re-export for backwards compatibility

__all__ = ["AuditLog"]