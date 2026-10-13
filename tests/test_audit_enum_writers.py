"""Focused tests for Phase 4 R1 audit-writer consistency changes.

The four audit persistence paths now pass enum members (not ``.value``
strings) into native PostgreSQL ENUM model columns. All mocks use context
managers and are restored afterwards. No database I/O occurs.
"""

from decimal import Decimal
from unittest import mock
from uuid import uuid4

import app.audit.comprehensive_audit as ca
from app.utils.enums import (
    APICallStatus,
    AuditSeverity,
    AuditTransactionType,
    DataAccessType,
)


def test_log_transaction_persists_member():
    with mock.patch.object(ca, "db") as mock_db:
        result = ca.FinancialAuditLog.log_transaction(
            transaction_id=str(uuid4()),
            transaction_type=AuditTransactionType.DEPOSIT,
            amount=Decimal("10.00"),
            currency="UGX",
            status="completed",
        )
        assert result.transaction_type == AuditTransactionType.DEPOSIT
        assert isinstance(result.transaction_type, AuditTransactionType)
        mock_db.session.add.assert_called_once_with(result)
        mock_db.session.commit.assert_called_once_with()


def test_log_api_call_persists_member():
    with mock.patch.object(ca, "db") as mock_db:
        result = ca.APIAuditLog.log_api_call(
            service_name="flutterwave",
            endpoint="/v3/payments",
            method="POST",
            request_id=str(uuid4()),
            status=APICallStatus.SUCCESS,
        )
        assert result.status == APICallStatus.SUCCESS
        assert isinstance(result.status, APICallStatus)
        mock_db.session.add.assert_called_once_with(result)
        mock_db.session.commit.assert_called_once_with()


def test_log_access_persists_member():
    with mock.patch.object(ca, "db") as mock_db:
        result = ca.DataAccessLog.log_access(
            accessed_by=1,
            subject_user_id=2,
            access_type=DataAccessType.READ,
            data_category="kyc_documents",
            purpose="support",
        )
        assert result.access_type == DataAccessType.READ
        mock_db.session.add.assert_called_once_with(result)
        mock_db.session.commit.assert_called_once_with()


def test_log_event_persists_member_and_keeps_string_input():
    with mock.patch.object(ca, "db") as mock_db:
        ca.SecurityEventLog.log_event(
            event_type="probe",
            severity=AuditSeverity.CRITICAL,
            description="member input",
        )
        insert = mock_db.session.connection.return_value.execute.call_args[0][0]
        assert insert.compile().params["severity"] is AuditSeverity.CRITICAL
    with mock.patch.object(ca, "db") as mock_db:
        # String input contract is preserved: normalised to the member.
        ca.SecurityEventLog.log_event(
            event_type="probe",
            severity="critical",
            description="string input",
        )
        insert = mock_db.session.connection.return_value.execute.call_args[0][0]
        assert insert.compile().params["severity"] is AuditSeverity.CRITICAL


def test_nearest_eta_invalid_class_returns_none_without_database():
    from app.transport.services.availability_service import (
        nearest_eta_minutes_for_class,
    )

    assert nearest_eta_minutes_for_class("not_a_class", (0.0, 0.0)) is None
    assert nearest_eta_minutes_for_class("comfort", None) is None
