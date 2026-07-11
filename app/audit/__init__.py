# app/audit/__init__.py
"""
Unified Audit Module - Exports all audit functionality
"""

from app.audit.comprehensive_audit import (
    AuditService,
    FinancialAuditLog,
    APIAuditLog,
    SecurityEventLog,
    DataAccessLog,
    DataChangeLog,
    TransactionType,
    AuditSeverity,
    APICallStatus,
    DataAccessType
)

from app.audit.models import AuditLog

# Import ForensicAuditService if available
try:
    from app.audit.forensic_audit import ForensicAuditService
    _has_forensic_audit = True
except ImportError:
    _has_forensic_audit = False
    ForensicAuditService = None

__all__ = [
    # Main service
    'AuditService',
    # Models
    'AuditLog',
    'FinancialAuditLog',
    'APIAuditLog',
    'SecurityEventLog',
    'DataAccessLog',
    'DataChangeLog',
    # Enums
    'TransactionType',
    'AuditSeverity',
    'APICallStatus',
    'DataAccessType',
]

# Conditionally add ForensicAuditService to __all__
if _has_forensic_audit:
    __all__.append('ForensicAuditService')
