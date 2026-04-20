# app/compliance/__init__.py
"""Compliance package for KYC, AML, and regulatory compliance"""

from app.admin.compliance.routes import compliance_bp

__all__ = ['compliance_bp']
# Empty file to make the package importable
