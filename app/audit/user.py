# app/audit/user.py
"""
Re-exports AuditLog from the consolidated audit module.
All audit logic lives in app.audit.comprehensive_audit to avoid duplicate SQLAlchemy table registration.
"""

from app.audit.models import AuditLog  # noqa: F401  — re-export for backwards compatibility

__all__ = ["AuditLog"]
