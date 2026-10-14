"""Regression proof for Phase 1B: canonical AuditLog import.

Covers:
  1. The ``AuditLog`` symbol used by ``app.audit.comprehensive_audit`` is the
     canonical model class from ``app.audit.models`` (table ``audit_logs``),
     not ``None`` and not ``app.models.audit`` (which only declares
     ``ActivityLog`` / table ``activity_logs``).
  2. ``AuditService.log_role_change`` constructs and returns the expected
     audit entry under a fully mocked database session -- no real query,
     commit, rollback, or database write occurs.
  3. A genuine persistence failure still resolves to ``None`` via the
     pre-existing contained-error path (that behavior is intentionally
     unchanged: import-failure mode is tested separately from
     persistence-failure mode).

All mocks use context managers and are restored afterwards.
"""

from unittest import mock
from typing import cast

import app.audit.comprehensive_audit as ca
from app.audit.models import AuditLog as CanonicalAuditLog


def test_auditlog_symbol_is_canonical_model():
    assert ca.AuditLog is not None
    assert ca.AuditLog is CanonicalAuditLog
    assert ca.AuditLog.__tablename__ == "audit_logs"


def test_activitylog_declaration_is_preserved():
    from app.models.audit import ActivityLog

    assert ActivityLog.__tablename__ == "activity_logs"
    assert ActivityLog is not CanonicalAuditLog


def test_log_role_change_constructs_entry_without_database():
    original_db = ca.db
    original_request = ca.request
    target = mock.MagicMock(username="target-user")
    actor = mock.MagicMock(username="actor-user")
    with mock.patch.object(ca, "db") as mock_db, mock.patch.object(
        ca, "request", mock.MagicMock(remote_addr="10.0.0.1")
    ):
        mock_db.session.get.side_effect = [target, actor]
        result = ca.AuditService.log_role_change(
            1, "user", "admin", 1, reason="test"
        )
        assert result is not None
        assert isinstance(result, CanonicalAuditLog)
        assert cast(str, result.action) == "role_change"
        assert cast(str, result.resource_type) == "user_role"
        assert cast(str, result.resource_id) == "1"
        assert cast(int, result.user_id) == 1
        assert cast(str, result.meta["old_role"]) == "user"
        assert cast(str, result.meta["new_role"]) == "admin"
        assert cast(str, result.meta["reason"]) == "test"
        assert cast(int, result.meta["target_user_id"]) == 1
        assert cast(str, result.meta["target_username"]) == "target-user"
        assert cast(str, result.meta["performed_by_username"]) == "actor-user"
        mock_db.session.add.assert_called_once_with(result)
        mock_db.session.commit.assert_called_once_with()
        mock_db.session.rollback.assert_not_called()
    # Mocks are restored after the test.
    assert ca.db is original_db
    assert ca.request is original_request


def test_log_role_change_persistence_failure_still_returns_none():
    """Genuine persistence failures keep the pre-existing None path."""
    target = mock.MagicMock(username="target-user")
    actor = mock.MagicMock(username="actor-user")
    with mock.patch.object(ca, "db") as mock_db, mock.patch.object(
        ca, "request", mock.MagicMock(remote_addr="10.0.0.1")
    ):
        mock_db.session.get.side_effect = [target, actor]
        mock_db.session.add.side_effect = RuntimeError("simulated write failure")
        result = ca.AuditService.log_role_change(
            1, "user", "admin", 1, reason="test"
        )
        assert result is None
        mock_db.session.rollback.assert_called_once_with()
