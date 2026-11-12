"""
Focused PostgreSQL-backed tests for AdminAuditService serialization and redaction.
Tests the centralized audit logging with security-first design.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.wallet.models.admin_audit import AdminAuditLog
from app.wallet.services.admin_audit_service import AdminAuditService


@pytest.fixture(autouse=True)
def _create_audit_test_admins(app):
    """Create real FK-backed admin actors for each audit serialization test."""
    from app.extensions import db
    from app.identity.models.user import User, UserRole
    from app.identity.models.roles_permission import get_or_create_role

    with app.app_context():
        owner_role = get_or_create_role("owner", level=1)
        admin_ids = []

        for _ in range(2):
            uid = uuid4().hex[:10]
            admin = User(
                username=f"audit_admin_{uid}",
                email=f"audit_admin_{uid}@test.example.com",
                is_verified=True,
                is_active=True,
            )
            admin.set_password("TestPass123!")
            db.session.add(admin)
            db.session.flush()
            db.session.add(UserRole(user_id=admin.id, role_id=owner_role.id))
            admin_ids.append(admin.id)

        db.session.commit()
        app.config["AUDIT_TEST_ADMIN_IDS"] = tuple(admin_ids)


@pytest.mark.usefixtures("app")
class TestAdminAuditSerialization:
    """Test audit value serialization"""

    def test_dict_value_saved_and_retrieved(self, app):
        """Dictionary audit value is saved successfully"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='test',
                target_type='config',
                target_id='1',
                target_name='Test Config',
                old_value={'setting': 'old_value', 'enabled': True},
                new_value={'setting': 'new_value', 'enabled': False},
                reason='Test dict serialization'
            )

            log = AdminAuditLog.query.first()
            assert log is not None
            assert log.old_value is not None
            assert log.new_value is not None

            # Verify stored as JSON string
            old_parsed = json.loads(log.old_value)
            new_parsed = json.loads(log.new_value)
            assert old_parsed['setting'] == 'old_value'
            assert new_parsed['setting'] == 'new_value'
            assert old_parsed['enabled'] is True
            assert new_parsed['enabled'] is False

    def test_list_value_saved_and_retrieved(self, app):
        """List audit value is saved successfully"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='test',
                target_type='config',
                target_id='1',
                target_name='Test Config',
                old_value=['item1', 'item2'],
                new_value=['item1', 'item2', 'item3'],
                reason='Test list serialization'
            )

            log = AdminAuditLog.query.first()
            assert log is not None

            old_parsed = json.loads(log.old_value)
            new_parsed = json.loads(log.new_value)
            assert old_parsed == ['item1', 'item2']
            assert new_parsed == ['item1', 'item2', 'item3']

    def test_plain_string_compatible(self, app):
        """Plain string values remain compatible"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='test',
                target_type='config',
                target_id='1',
                target_name='Test Config',
                old_value='legacy_string_value',
                new_value='new_string_value',
                reason='Test string compatibility'
            )

            log = AdminAuditLog.query.first()
            assert log.old_value == 'legacy_string_value'
            assert log.new_value == 'new_string_value'

    def test_none_value_compatible(self, app):
        """None values remain compatible"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='create',
                action_category='test',
                target_type='config',
                target_id='1',
                target_name='Test Config',
                old_value=None,
                new_value={'key': 'value'},
                reason='Test None compatibility'
            )

            log = AdminAuditLog.query.first()
            assert log.old_value is None
            assert log.new_value is not None

    def test_decimal_serialized(self, app):
        """Decimal values are serialized without failure"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='test',
                target_type='config',
                target_id='1',
                target_name='Test Config',
                old_value={'amount': Decimal('100.50')},
                new_value={'amount': Decimal('200.75')},
                reason='Test Decimal serialization'
            )

            log = AdminAuditLog.query.first()
            old_parsed = json.loads(log.old_value)
            new_parsed = json.loads(log.new_value)
            assert old_parsed['amount'] == 100.50
            assert new_parsed['amount'] == 200.75

    def test_datetime_serialized(self, app):
        """Date and datetime values are serialized in ISO format"""
        with app.app_context():
            dt = datetime(2026, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
            d = datetime(2026, 1, 15).date()

            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='test',
                target_type='config',
                target_id='1',
                target_name='Test Config',
                old_value={'timestamp': dt, 'date': d},
                new_value={'timestamp': dt, 'date': d},
                reason='Test datetime serialization'
            )

            log = AdminAuditLog.query.first()
            parsed = json.loads(log.old_value)
            assert parsed['timestamp'] == '2026-01-15T10:30:45+00:00'
            assert parsed['date'] == '2026-01-15'

    def test_uuid_serialized(self, app):
        """UUID values are serialized as strings"""
        with app.app_context():
            test_uuid = uuid4()

            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='test',
                target_type='config',
                target_id='1',
                target_name='Test Config',
                old_value={'id': test_uuid},
                new_value={'id': test_uuid},
                reason='Test UUID serialization'
            )

            log = AdminAuditLog.query.first()
            parsed = json.loads(log.old_value)
            assert parsed['id'] == str(test_uuid)

    def test_existing_json_string_not_double_encoded(self, app):
        """Already valid JSON strings are not double-encoded"""
        with app.app_context():
            json_str = '{"key": "value", "number": 42}'

            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='test',
                target_type='config',
                target_id='1',
                target_name='Test Config',
                old_value=json_str,
                new_value=json_str,
                reason='Test JSON string passthrough'
            )

            log = AdminAuditLog.query.first()
            assert log.old_value == json_str
            assert log.new_value == json_str

    def test_json_string_with_leading_whitespace_redacts_secrets(self, app):
        """Sensitive values are redacted even when JSON strings start with whitespace."""
        with app.app_context():
            json_str = '  \n  {"api_key": "must-not-persist", "label": "gateway"}'

            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='payment_gateway',
                target_type='gateway',
                target_id='1',
                target_name='Gateway',
                old_value=json_str,
                new_value=json_str,
                reason='Test whitespace-prefixed JSON redaction'
            )

            log = AdminAuditLog.query.first()
            for serialized in (log.old_value, log.new_value):
                parsed = json.loads(serialized)
                assert parsed['api_key'] == '[REDACTED]'
                assert parsed['label'] == 'gateway'
                assert 'must-not-persist' not in serialized


@pytest.mark.usefixtures("app")
class TestAdminAuditRedaction:
    """Test sensitive field redaction"""

    def test_api_key_redacted(self, app):
        """API keys are redacted in audit logs"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='aggregator',
                target_type='aggregator',
                target_id='1',
                target_name='Test Aggregator',
                old_value={'api_key': 'secret_key_123', 'name': 'test'},
                new_value={'api_key': 'new_secret_456', 'name': 'test'},
                reason='Test API key redaction'
            )

            log = AdminAuditLog.query.first()
            old_parsed = json.loads(log.old_value)
            new_parsed = json.loads(log.new_value)

            assert old_parsed['api_key'] == '[REDACTED]'
            assert new_parsed['api_key'] == '[REDACTED]'
            assert old_parsed['name'] == 'test'

    def test_api_secret_redacted(self, app):
        """API secrets are redacted"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='aggregator',
                target_type='aggregator',
                target_id='1',
                target_name='Test Aggregator',
                old_value={'api_secret': 'super_secret', 'display_name': 'test'},
                new_value={'api_secret': 'new_super_secret', 'display_name': 'test'},
                reason='Test API secret redaction'
            )

            log = AdminAuditLog.query.first()
            old_parsed = json.loads(log.old_value)
            assert old_parsed['api_secret'] == '[REDACTED]'

    def test_nested_sensitive_fields_redacted(self, app):
        """Sensitive fields in nested dicts are redacted"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='payment_gateway',
                target_type='gateway',
                target_id='1',
                target_name='Test Gateway',
                old_value={
                    'config': {
                        'api_key': 'nested_key',
                        'normal_field': 'value'
                    }
                },
                new_value={
                    'config': {
                        'api_key': 'new_nested_key',
                        'normal_field': 'new_value'
                    }
                },
                reason='Test nested redaction'
            )

            log = AdminAuditLog.query.first()
            old_parsed = json.loads(log.old_value)
            new_parsed = json.loads(log.new_value)

            assert old_parsed['config']['api_key'] == '[REDACTED]'
            assert new_parsed['config']['api_key'] == '[REDACTED]'
            assert old_parsed['config']['normal_field'] == 'value'
            assert new_parsed['config']['normal_field'] == 'new_value'

    def test_config_json_sanitized(self, app):
        """config_json field is sanitized when it contains sensitive data"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='payment_method',
                target_type='payment_method',
                target_id='1',
                target_name='Test Method',
                old_value={
                    'config_json': {
                        'api_key': 'secret_in_config',
                        'webhook_url': 'https://example.com/webhook'
                    }
                },
                new_value={
                    'config_json': {
                        'api_key': 'new_secret_in_config',
                        'webhook_url': 'https://example.com/new_webhook'
                    }
                },
                reason='Test config_json sanitization'
            )

            log = AdminAuditLog.query.first()
            old_parsed = json.loads(log.old_value)
            new_parsed = json.loads(log.new_value)

            # config_json should be sanitized
            assert old_parsed['config_json']['api_key'] == '[REDACTED]'
            assert new_parsed['config_json']['api_key'] == '[REDACTED]'
            assert old_parsed['config_json']['webhook_url'] == 'https://example.com/webhook'

    def test_payment_gateway_credentials_never_stored(self, app):
        """Payment gateway API keys and secrets never appear in audit"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='create',
                action_category='payment_gateway',
                target_type='payment_gateway',
                target_name='Test Gateway',
                new_value={
                    'gateway_name': 'Test Gateway',
                    'gateway_type': 'stripe',
                    'credentials_provided': True,
                    'webhook_url': 'https://example.com/webhook'
                },
                reason='Test payment gateway audit'
            )

            log = AdminAuditLog.query.first()
            parsed = json.loads(log.new_value)

            assert 'api_key' not in parsed
            assert 'api_secret' not in parsed
            assert parsed['credentials_provided'] is True
            assert parsed['webhook_url'] == 'https://example.com/webhook'

    def test_aggregator_secrets_never_stored(self, app):
        """Aggregator API keys and secrets never appear in audit when using to_dict()"""
        with app.app_context():
            # Simulate what aggregator.to_dict() returns (with exclude_secret=True)
            safe_aggregator_data = {
                'id': 1,
                'name': 'test_aggregator',
                'display_name': 'Test Aggregator',
                'status': 'active',
                'mode': 'testing',
                # No api_key, api_secret, webhook_secret, etc.
            }

            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='aggregator',
                target_type='aggregator',
                target_id='1',
                target_name='Test Aggregator',
                old_value=safe_aggregator_data,
                new_value=safe_aggregator_data,
                reason='Test aggregator audit'
            )

            log = AdminAuditLog.query.first()
            parsed = json.loads(log.new_value)

            assert 'api_key' not in parsed
            assert 'api_secret' not in parsed
            assert 'webhook_secret' not in parsed
            assert 'sandbox_api_key' not in parsed
            assert 'live_api_key' not in parsed
            assert parsed['name'] == 'test_aggregator'

    def test_travel_rule_vasp_api_key_redacted(self, app):
        """Travel rule VASP API key is redacted"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='modify',
                action_category='travel_rule',
                target_type='travel_rule_config',
                target_id='1',
                target_name='Travel Rule Config',
                old_value={'vasp_api_key': 'vasp_secret', 'enabled': True},
                new_value={'vasp_api_key': 'new_vasp_secret', 'enabled': True},
                reason='Test travel rule audit'
            )

            log = AdminAuditLog.query.first()
            old_parsed = json.loads(log.old_value)
            new_parsed = json.loads(log.new_value)

            assert old_parsed['vasp_api_key'] == '[REDACTED]'
            assert new_parsed['vasp_api_key'] == '[REDACTED]'


@pytest.mark.usefixtures("app")
class TestAdminAuditCallers:
    """Test that existing audit callers still work"""

    def test_audit_log_entry_created(self, app):
        """Basic audit log entry is created successfully"""
        with app.app_context():
            log = AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                admin_name='test_admin',
                admin_role='owner',
                action_type='create',
                action_category='test',
                target_type='entity',
                target_id='1',
                target_name='Test Entity',
                reason='Test audit creation'
            )

            assert log is not None
            assert log.id is not None
            assert log.admin_id == 1
            assert log.admin_name == 'test_admin'
            assert log.action_type == 'create'
            assert log.reason == 'Test audit creation'

    def test_audit_log_with_all_fields(self, app):
        """Audit log with all optional fields works"""
        with app.app_context():
            log = AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][1],
                admin_name='another_admin',
                admin_role='super_admin',
                action_type='delete',
                action_category='user_management',
                target_type='user',
                target_id='42',
                target_name='Test User',
                old_value={'status': 'active', 'email': 'user@example.com'},
                new_value={'status': 'deleted'},
                reason='User account deleted'
            )

            assert log is not None
            assert log.target_id == '42'
            assert log.target_name == 'Test User'

            old_parsed = json.loads(log.old_value)
            new_parsed = json.loads(log.new_value)
            assert old_parsed['status'] == 'active'
            assert new_parsed['status'] == 'deleted'


@pytest.mark.usefixtures("app")
class TestAdminAuditRetrieval:
    """Test audit log retrieval methods"""

    def test_get_audit_logs(self, app):
        """get_audit_logs returns correct entries"""
        with app.app_context():
            # Create multiple audit entries
            for i in range(3):
                AdminAuditService.log_action(
                    admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0],
                    admin_name='test_admin',
                    admin_role='owner',
                    action_type='modify' if i > 0 else 'create',
                    action_category='test',
                    target_type='config',
                    target_id=str(i),
                    target_name=f'Config {i}',
                    reason=f'Action {i}'
                )

            logs = AdminAuditService.get_audit_logs(limit=10)
            assert len(logs) == 3

            # Most recent first
            assert logs[0]['target_name'] == 'Config 2'
            assert logs[1]['target_name'] == 'Config 1'
            assert logs[2]['target_name'] == 'Config 0'

    def test_get_audit_logs_filtered(self, app):
        """get_audit_logs with filters works"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0], admin_name='a1', admin_role='owner',
                action_type='create', action_category='cat1', target_type='t1', target_id='1', target_name='t1'
            )
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][1], admin_name='a2', admin_role='owner',
                action_type='modify', action_category='cat2', target_type='t2', target_id='2', target_name='t2'
            )

            # Filter by admin_id
            logs = AdminAuditService.get_audit_logs(admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0])
            assert len(logs) == 1
            assert logs[0]['admin_name'] == 'a1'

            # Filter by action_type
            logs = AdminAuditService.get_audit_logs(action_type='modify')
            assert len(logs) == 1
            assert logs[0]['action_type'] == 'modify'

            # Filter by action_category
            logs = AdminAuditService.get_audit_logs(action_category='cat2')
            assert len(logs) == 1
            assert logs[0]['action_category'] == 'cat2'

    def test_get_audit_summary(self, app):
        """get_audit_summary returns correct statistics"""
        with app.app_context():
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0], admin_name='a1', admin_role='owner',
                action_type='create', action_category='cat1', target_type='t1', target_id='1', target_name='t1'
            )
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][0], admin_name='a1', admin_role='owner',
                action_type='modify', action_category='cat1', target_type='t1', target_id='2', target_name='t2'
            )
            AdminAuditService.log_action(
                admin_id=app.config['AUDIT_TEST_ADMIN_IDS'][1], admin_name='a2', admin_role='owner',
                action_type='delete', action_category='cat2', target_type='t2', target_id='3', target_name='t3'
            )

            summary = AdminAuditService.get_audit_summary(days=30)
            assert summary['total_actions'] == 3
            assert summary['actions_by_type']['create'] == 1
            assert summary['actions_by_type']['modify'] == 1
            assert summary['actions_by_type']['delete'] == 1
            assert summary['actions_by_category']['cat1'] == 2
            assert summary['actions_by_category']['cat2'] == 1