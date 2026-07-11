# app/auditor/__init__.py
"""Auditor package for forensic logs and compliance auditing"""

from app.admin.auditor.routes import auditor_bp

__all__ = ['auditor_bp']
# Empty file to make the package importable
