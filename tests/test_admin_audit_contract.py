"""
Test for AdminAuditService contract - commit/rollback spy and safe indicator handling
"""

import json
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.wallet.models.admin_audit import AdminAuditLog
from app.wallet.services.admin_audit_service import AdminAuditService


class TestAdminAuditServiceContract:
    """Test AdminAuditService contract compliance"""

    def test_log_action_does_not_commit_or_rollback(self, app):
        """Test that log_action only adds and flushes, never commits or rolls back"""
        with app.app_context():
            with patch.object(db.session, 'commit') as mock_commit, \
                 patch.object(db.session, 'rollback') as mock_rollback, \
                 patch.object(db.session, 'flush') as mock_flush, \
                 patch.object(db.session, 'add') as mock_add:
                
                mock_flush.return_value = None
                mock_add.return_value = None
                
                # Create a mock audit log that will be returned
                mock_audit_log = MagicMock(spec=AdminAuditLog)
                mock_audit_log.id = 1
                
                # We need to mock the AdminAuditLog constructor to return our mock
                with patch('app.wallet.services.admin_audit_service.AdminAuditLog', return_value=mock_audit_log):
                    AdminAuditService.log_action(
                        admin_id=1,
                        admin_name='test_admin',
                        admin_role='owner',
                        action_type='modify',
                        action_category='test',
                        target_type='config',
                        target_id='1',
                        target_name='Test Config',
                        old_value={'setting': 'old'},
                        new_value={'setting': 'new'},
                        reason='Test'
                    )
                
                # Assert commit and rollback were NEVER called
                mock_commit.assert_not_called()
                mock_rollback.assert_not_called()
                
                # Assert flush WAS called
                mock_flush.assert_called_once()
                mock_add.assert_called_once_with(mock_audit_log)

    def test_safe_indicators_not_redacted(self, app):
        """Test that safe boolean indicators are not redacted in audit snapshots"""
        with app.app_context():
            # Test with safe indicator keys
            safe_data = {
                'api_key_configured': True,
                'api_secret_configured': False,
                'webhook_configured': True,
                'sandbox_configured': True,
                'production_configured': False,
                'config_json_present': True,
                'credentials_provided': True,
                'api_key_configured': True,
                'api_secret_configured': True,
                'sandbox_api_key_configured': True,
                'sandbox_api_secret_configured': True,
                'live_api_key_configured': True,
                'live_api_secret_configured': True,
                'webhook_configured': True,
                'webhook_secret_configured': True,
                'ip_whitelist_configured': True,
                'alert_emails_configured': True,
                'vasp_endpoint_configured': True,
                'vasp_api_key_configured': True,
            }
            
            serialized = AdminAuditService._serialize_audit_value(safe_data)
            parsed = json.loads(serialized)
            
            # All safe indicators should remain as booleans, not be redacted
            for key, expected_value in safe_data.items():
                assert key in parsed, f"Missing key: {key}"
                assert parsed[key] == expected_value, f"Key {key} was redacted or changed: got {parsed[key]}, expected {expected_value}"

    def test_actual_secrets_redacted(self, app):
        """Test that actual secret keys are redacted"""
        with app.app_context():
            secret_data = {
                'api_key': 'sk_live_abc123',
                'api_secret': 'whsec_xyz789',
                'webhook_secret': 'whsec_secret',
                'password': 'mypassword',
                'access_token': 'token123',
                'private_key': '-----BEGIN PRIVATE KEY-----',
                'api_key_configured': True,  # This should NOT be redacted
            }
            
            serialized = AdminAuditService._serialize_audit_value(secret_data)
            parsed = json.loads(serialized)
            
            # Actual secrets should be redacted
            assert parsed['api_key'] == '[REDACTED]'
            assert parsed['api_secret'] == '[REDACTED]'
            assert parsed['webhook_secret'] == '[REDACTED]'
            assert parsed['password'] == '[REDACTED]'
            assert parsed['access_token'] == '[REDACTED]'
            assert parsed['private_key'] == '[REDACTED]'
            
            # Safe indicator should NOT be redacted
            assert parsed['api_key_configured'] is True

    def test_json_string_sanitization(self, app):
        """Test that JSON strings containing secrets are sanitized"""
        with app.app_context():
            # JSON string with secret
            json_str = '{"api_key": "secret123", "normal_field": "value"}'
            
            serialized = AdminAuditService._serialize_audit_value(json_str)
            parsed = json.loads(serialized)
            
            assert parsed['api_key'] == '[REDACTED]'
            assert parsed['normal_field'] == 'value'

    def test_decimal_exact_precision(self, app):
        """Test that Decimal values are serialized as exact strings"""
        with app.app_context():
            from decimal import Decimal
            
            data = {
                'amount': Decimal('100.50'),
                'fee': Decimal('0.0001'),
                'rate': Decimal('1.5')
            }
            
            serialized = AdminAuditService._serialize_audit_value(data)
            parsed = json.loads(serialized)
            
            assert parsed['amount'] == '100.50'
            assert parsed['fee'] == '0.0001'
            assert parsed['rate'] == '1.5'

    def test_enum_serialization(self, app):
        """Test that Enum values are serialized as their underlying value"""
        with app.app_context():
            from enum import Enum
            
            class TestEnum(Enum):
                VALUE_A = 'a'
                VALUE_B = 'b'
            
            data = {'status': TestEnum.VALUE_A}
            
            serialized = AdminAuditService._serialize_audit_value(data)
            parsed = json.loads(serialized)
            
            assert parsed['status'] == 'a'

    def test_unsupported_type_raises(self, app):
        """Test that unsupported types raise TypeError"""
        with app.app_context():
            class CustomObject:
                pass
            
            with pytest.raises(TypeError, match="Unsupported type for audit serialization"):
                AdminAuditService._serialize_audit_value(CustomObject())

    def test_non_finite_float_raises(self, app):
        """Test that non-finite floats raise TypeError"""
        with app.app_context():
            import math
            
            for bad_value in [float('inf'), float('-inf'), float('nan')]:
                with pytest.raises(TypeError, match="Non-finite float value not allowed"):
                    AdminAuditService._serialize_audit_value({'value': bad_value})

    def test_legacy_string_preserved(self, app):
        """Test that plain strings are preserved as-is"""
        with app.app_context():
            # Non-JSON string should be preserved
            plain_string = "this is a plain string"
            serialized = AdminAuditService._serialize_audit_value(plain_string)
            assert serialized == plain_string
            
            # JSON-looking string that's invalid JSON
            invalid_json = "{not valid json"
            serialized = AdminAuditService._serialize_audit_value(invalid_json)
            assert serialized == invalid_json

    def test_audited_change_commits_on_success(self, app):
        """Test that audited_change context manager commits on success"""
        with app.app_context():
            with patch.object(db.session, 'commit') as mock_commit, \
                 patch.object(db.session, 'rollback') as mock_rollback:
                
                with AdminAuditService.audited_change():
                    pass  # Do some work
                
                mock_commit.assert_called_once()
                mock_rollback.assert_not_called()

    def test_audited_change_rollbacks_on_exception(self, app):
        """Test that audited_change context manager rolls back on exception"""
        with app.app_context():
            with patch.object(db.session, 'commit') as mock_commit, \
                 patch.object(db.session, 'rollback') as mock_rollback:
                
                try:
                    with AdminAuditService.audited_change():
                        raise ValueError("Test error")
                except ValueError:
                    pass
                
                mock_rollback.assert_called_once()
                mock_commit.assert_not_called()