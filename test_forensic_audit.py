"""
Test the forensic audit system.
"""
import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

def test_log_attempt():
    """Test logging an attempt."""
    # Mock the dependencies
    with patch('app.audit.forensic_audit.DataChangeLog') as MockDataChangeLog, \
         patch('app.audit.forensic_audit.SecurityEventLog') as MockSecurityEventLog:
        mock_log_change = MagicMock()
        MockDataChangeLog.log_change = mock_log_change

        mock_log_event = MagicMock()
        MockSecurityEventLog.log_event = mock_log_event

        # Import after mocking
        from app.audit.forensic_audit import ForensicAuditService

        audit_id = ForensicAuditService.log_attempt(
            entity_type="test",
            entity_id="123",
            action="test_action",
            user_id=1,
            details={"test": "data"},
            correlation_id="test-correlation"
        )

        assert audit_id is not None
        assert isinstance(audit_id, str)
        assert len(audit_id) > 10
        # Verify DataChangeLog was called
        assert mock_log_change.called

def test_log_completion():
    """Test logging completion."""
    with patch('app.audit.forensic_audit.DataChangeLog') as MockDataChangeLog:
        mock_log_change = MagicMock()
        MockDataChangeLog.log_change = mock_log_change

        # Import after mocking
        from app.audit.forensic_audit import ForensicAuditService

        result = ForensicAuditService.log_completion(
            audit_id="test-audit-id",
            status="completed",
            reviewed_by=2,
            review_notes="Test review"
        )

        assert result is True
        # Verify DataChangeLog was called
        assert mock_log_change.called

def test_log_blocked():
    """Test logging a blocked action."""
    with patch('app.audit.forensic_audit.DataChangeLog') as MockDataChangeLog, \
         patch('app.audit.forensic_audit.SecurityEventLog') as MockSecurityEventLog:
        mock_log_change = MagicMock()
        MockDataChangeLog.log_change = mock_log_change

        mock_log_event = MagicMock()
        MockSecurityEventLog.log_event = mock_log_event

        # Import after mocking
        from app.audit.forensic_audit import ForensicAuditService

        audit_id = ForensicAuditService.log_blocked(
            entity_type="test",
            entity_id="456",
            action="modify",
            user_id=1,
            reason="Test block reason",
            attempted_value="new_value",
            old_value="old_value"
        )

        assert audit_id is not None
        assert isinstance(audit_id, str)
        # Verify both DataChangeLog and SecurityEventLog were called
        assert mock_log_change.called
        assert mock_log_event.called

def test_risk_scoring():
    """Test risk score calculation."""
    # Import without mocking since calculate_risk_score doesn't use external dependencies
    from app.audit.forensic_audit import ForensicAuditService

    risk_score = ForensicAuditService.calculate_risk_score(
        user_id=1,
        action="login",
        entity_type="user",
        details={"ip": "192.168.1.1"}
    )
    assert isinstance(risk_score, int)
    assert 0 <= risk_score <= 100

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
