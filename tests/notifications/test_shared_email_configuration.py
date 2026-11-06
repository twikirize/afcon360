"""Security and delivery contracts for the shared Owner-managed mail provider.

These tests are deliberately DB-free. They exercise the same resolver, crypto,
SMTP transport, logging redaction and Celery context machinery used in runtime.
"""
import logging
from email.message import EmailMessage

import pytest
from cryptography.fernet import Fernet
from flask import Flask, current_app


pytestmark = pytest.mark.no_database


def _fernet(monkeypatch):
    from app.utils.security import _get_fernet

    instance = Fernet(Fernet.generate_key())
    monkeypatch.setattr("app.utils.security._get_fernet", lambda: instance)
    return instance


def test_provider_json_is_authenticated_encrypted_and_round_trips(monkeypatch):
    import app.utils.crypto as crypto

    _fernet(monkeypatch)
    secret = "smtp-password-secret-7b9a"
    payload = {
        "smtp_host": "smtp.example.test",
        "smtp_user": "mailer@example.test",
        "smtp_pass": secret,
        "nested": {"api_key": "provider-key-secret-2a8c"},
    }

    stored = crypto.encrypt_json(payload)

    assert crypto.is_encrypted_json(stored)
    assert secret not in repr(stored)
    assert payload["nested"]["api_key"] not in repr(stored)
    assert crypto.decrypt_json(stored) == payload


def test_provider_json_encryption_fails_closed_without_key(monkeypatch):
    import app.utils.crypto as crypto

    monkeypatch.setattr(
        "app.utils.security._get_fernet",
        lambda: (_ for _ in ()).throw(RuntimeError("key unavailable")),
    )
    with pytest.raises(RuntimeError):
        crypto.encrypt_json({"smtp_pass": "never-store-this-plaintext"})


def test_legacy_plaintext_provider_config_can_be_read_for_migration():
    from app.utils.crypto import is_encrypted_json, decrypt_json

    legacy = {"smtp_host": "smtp.example.test", "smtp_pass": "legacy-secret-value"}
    restored = decrypt_json(legacy)

    assert restored == legacy
    assert not is_encrypted_json(legacy)


def test_provider_records_reject_root_runtime_secrets():
    from app.notifications.settings import CommunicationSettingsService

    forbidden_configs = (
        {"SECRET_KEY": "root-session-key"},
        {"nested": {"ENCRYPTION_KEY": "root-encryption-key"}},
        {"DATABASE_URL": "postgresql://user:password@db.example.test/afcon"},
        {"redis": {"password": "redis-root-password"}},
        {"CELERY_BROKER_URL": "redis://:password@redis.example.test/0"},
    )
    for config in forbidden_configs:
        with pytest.raises(ValueError, match="server-side secrets"):
            CommunicationSettingsService._encrypt_config(config)


def test_upsert_setting_commit_false_defers_commit_to_owner_transaction(monkeypatch):
    from app.extensions import db
    from app.notifications.models import CommunicationSettings
    from app.notifications.settings import CommunicationSettingsService
    from app.utils.crypto import is_encrypted_json

    _fernet(monkeypatch)
    added = []
    commits = []

    class _Query:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return None

    monkeypatch.setattr(CommunicationSettings, "query", _Query())
    monkeypatch.setattr(db.session, "add", lambda value: added.append(value))
    monkeypatch.setattr(db.session, "commit", lambda: commits.append(True))

    setting = CommunicationSettingsService.upsert_setting(
        key="auth_providers",
        channel="auth",
        provider="system",
        config={"google_client_secret": "google-client-secret-1122"},
        commit=False,
    )

    assert setting in added
    assert is_encrypted_json(setting.config)
    assert commits == []


def test_owner_email_provider_row_is_authoritative_for_all_processes(monkeypatch):
    from app.notifications.models import CommunicationSettings
    from app.notifications.settings import CommunicationSettingsService

    _fernet(monkeypatch)
    payload = {
        "smtp_host": "db.smtp.example.test",
        "smtp_port": 465,
        "smtp_user": "worker@example.test",
        "smtp_pass": "shared-db-password-9d2e",
        "use_tls": False,
        "use_ssl": True,
        "default_sender": "AFCON360 <mail@example.test>",
    }
    encrypted = CommunicationSettingsService._encrypt_config(payload)

    class _Query:
        def filter_by(self, **kwargs):
            assert kwargs == {
                "key": "email_provider",
                "channel": "email",
                "is_deleted": False,
            }
            return self

        def first(self):
            return type(
                "Setting",
                (),
                {
                    "enabled": True,
                    "provider": "smtp",
                    "config": encrypted,
                },
            )()

    monkeypatch.setattr(CommunicationSettings, "query", _Query())
    resolved = CommunicationSettingsService.resolve_email_transport_config()

    assert resolved == {
        "provider": "smtp",
        "smtp_host": "db.smtp.example.test",
        "smtp_port": 465,
        "smtp_user": "worker@example.test",
        "smtp_pass": "shared-db-password-9d2e",
        "use_tls": False,
        "use_ssl": True,
        "default_sender": "AFCON360 <mail@example.test>",
        "source": "database",
    }


def test_environment_mail_settings_are_fallback_only_when_owner_row_missing(monkeypatch):
    from app.notifications.models import CommunicationSettings
    from app.notifications.settings import CommunicationSettingsService

    class _Query:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return None

    monkeypatch.setattr(CommunicationSettings, "query", _Query())
    app = Flask("mail-config-fallback-test")
    app.config.update(
        MAIL_SERVER="legacy.smtp.example.test",
        MAIL_PORT=587,
        MAIL_USERNAME="legacy-user@example.test",
        MAIL_PASSWORD="legacy-env-secret-11a2",
        MAIL_USE_TLS=True,
        MAIL_USE_SSL=False,
        MAIL_DEFAULT_SENDER="mail@example.test",
    )
    with app.app_context():
        resolved = CommunicationSettingsService.resolve_email_transport_config()

    assert resolved["source"] == "environment"
    assert resolved["smtp_host"] == "legacy.smtp.example.test"
    assert resolved["smtp_pass"] == "legacy-env-secret-11a2"


def test_smtp_transport_uses_shared_resolver_and_sends_message(monkeypatch):
    from app.notifications.email_transport import send_smtp_email
    from app.notifications.settings import CommunicationSettingsService

    config = {
        "provider": "smtp",
        "smtp_host": "smtp.example.test",
        "smtp_port": 587,
        "smtp_user": "user@example.test",
        "smtp_pass": "smtp-secret-2b33",
        "use_tls": True,
        "use_ssl": False,
        "default_sender": "mailer@example.test",
        "source": "database",
    }
    monkeypatch.setattr(
        CommunicationSettingsService,
        "resolve_email_transport_config",
        classmethod(lambda cls: config),
    )

    sent = {}

    class _SMTP:
        def __init__(self, host, port, timeout):
            sent["connection"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            sent["ehlo"] = True

        def starttls(self, context):
            sent["tls"] = context is not None

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, message):
            assert isinstance(message, EmailMessage)
            sent["message"] = message
            return {}

    monkeypatch.setattr("smtplib.SMTP", _SMTP)

    provider = send_smtp_email(
        recipient="controlled@example.test",
        subject="AFCON360 test",
        body="Delivery body",
        html="<p>Delivery body</p>",
    )

    assert provider == "smtp"
    assert sent["connection"] == ("smtp.example.test", 587, 20)
    assert sent["login"] == ("user@example.test", "smtp-secret-2b33")
    assert sent["tls"] is True
    assert sent["message"]["To"] == "controlled@example.test"


def test_smtp_transport_hides_provider_exception_details(monkeypatch):
    from app.notifications.email_transport import (
        EmailDeliveryError,
        send_smtp_email,
    )
    from app.notifications.settings import CommunicationSettingsService

    config = {
        "provider": "smtp",
        "smtp_host": "smtp.example.test",
        "smtp_port": 587,
        "smtp_user": "user@example.test",
        "smtp_pass": "secret-that-must-not-be-logged",
        "use_tls": True,
        "use_ssl": False,
        "default_sender": "mailer@example.test",
    }
    monkeypatch.setattr(
        CommunicationSettingsService,
        "resolve_email_transport_config",
        classmethod(lambda cls: config),
    )

    class _SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise RuntimeError("AUTH failed for password=secret-that-must-not-be-logged")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("smtplib.SMTP", _SMTP)
    with pytest.raises(EmailDeliveryError) as exc:
        send_smtp_email(
            recipient="controlled@example.test",
            subject="test",
            body="test",
        )

    assert "secret-that-must-not-be-logged" not in str(exc.value)
    assert exc.value.code == "smtp_runtimeerror"


def test_email_handler_returns_safe_failure_code_without_logging_secret(caplog, monkeypatch):
    from types import SimpleNamespace
    from app.notifications.channel_handlers.email import EmailHandler
    from app.notifications.email_transport import EmailDeliveryError

    monkeypatch.setattr(
        "app.notifications.email_transport.send_smtp_email",
        lambda **kwargs: (_ for _ in ()).throw(EmailDeliveryError("smtp_auth_error")),
    )
    notification = SimpleNamespace(
        id=77,
        type="system_alert",
        subject="Secret subject should not be logged",
        body="Secret body should not be logged",
        context={},
        link=None,
        user_id=1,
    )
    with caplog.at_level(logging.INFO):
        result = EmailHandler().deliver(
            notification,
            {"email": "private-recipient@example.test", "user_id": 1},
        )

    assert result["success"] is False
    assert result["error_code"] == "smtp_auth_error"
    assert "private-recipient@example.test" not in caplog.text
    assert "Secret subject should not be logged" not in caplog.text
    assert "Secret body should not be logged" not in caplog.text


def test_log_record_factory_redacts_registered_secret_and_nested_extra(caplog):
    from app.utils.log_redaction import (
        install_log_redaction,
        register_secret,
    )

    install_log_redaction()
    sentinel = "registered-secret-value-88aa"
    register_secret(sentinel)

    logger = logging.getLogger("tests.secret-redaction-contract")
    with caplog.at_level(logging.WARNING, logger=logger.name):
        logger.warning(
            "Provider rejected password=%s",
            sentinel,
            extra={
                "smtp_password": sentinel,
                "diagnostics": {"nested": {"api_key": sentinel}},
            },
        )

    assert sentinel not in caplog.text
    record = next(r for r in caplog.records if r.name == logger.name)
    assert record.smtp_password == "[REDACTED]"
    assert record.diagnostics["nested"]["api_key"] == "[REDACTED]"


def test_log_record_factory_scrubs_exception_text(caplog):
    from app.utils.log_redaction import register_secret

    sentinel = "exception-secret-value-33bb"
    register_secret(sentinel)
    logger = logging.getLogger("tests.secret-redaction-exception")
    with caplog.at_level(logging.ERROR, logger=logger.name):
        try:
            raise RuntimeError(f"SMTP failed password={sentinel}")
        except RuntimeError:
            logger.exception("Provider error")

    assert sentinel not in caplog.text


def test_celery_task_gets_lazy_cached_flask_context(monkeypatch):
    from celery import Celery
    from flask import Flask
    from app.celery_app import make_celery

    task_app = Flask("lazy-celery-context-test")
    calls = []

    def _get_app():
        calls.append(True)
        return task_app

    monkeypatch.setattr("app.tasks.context._get_task_flask_app", _get_app)
    # Force the worker path even if pytest leaves another Flask context active.
    monkeypatch.setattr("flask.has_app_context", lambda: False)
    celery = make_celery()

    @celery.task(name="tests.lazy_flask_context")
    def context_probe():
        return current_app.name

    assert calls == []
    assert context_probe() == "lazy-celery-context-test"
    assert calls == [True]


def test_async_email_test_task_delivers_through_shared_email_handler(monkeypatch):
    from flask import Flask
    from app.notifications.channel_handlers.email import EmailHandler
    from app.notifications.tasks import send_email_test_task

    app = Flask("async-email-task-test")
    sent = {}

    monkeypatch.setattr("app.utils.security.validate_email", lambda value: True)

    def _deliver(self, notification, recipient):
        sent["notification"] = notification
        sent["recipient"] = recipient
        return {
            "success": True,
            "external_id": "test-provider-message",
            "response_code": 250,
            "response_body": "email_provider_accepted",
        }

    monkeypatch.setattr(EmailHandler, "deliver", _deliver)

    # The task is executed by Celery inside this same context in production.
    with app.app_context():
        result = send_email_test_task.run(
            recipient="owner-controlled@example.test",
            requested_by_user_id=73,
        )

    assert result == {"status": "accepted", "error_code": None}
    assert sent["recipient"] == {
        "email": "owner-controlled@example.test",
        "user_id": 73,
    }
    assert sent["notification"].subject == "AFCON360 email delivery test"
    assert "asynchronous worker" in sent["notification"].body


def test_aggregator_legacy_webhook_url_is_encrypted_at_rest(monkeypatch):
    from app.extensions import db
    from app.notifications.models import NotificationAggregator
    from app.notifications.settings import CommunicationSettingsService
    from app.utils.crypto import decrypt_json, is_encrypted_json

    _fernet(monkeypatch)
    legacy_url = (
        "https://api-user:basic-auth-secret@hooks.example.test/incoming"
        "?token=webhook-token-secret-77cc"
    )
    aggregator = type(
        "Aggregator",
        (),
        {
            "credentials": None,
            "webhook_url": legacy_url,
            "priority": 10,
        },
    )()

    class _Query:
        def filter_by(self, **kwargs):
            assert kwargs == {"name": "legacy-webhook", "is_deleted": False}
            return self

        def first(self):
            return aggregator

    monkeypatch.setattr(NotificationAggregator, "query", _Query())
    monkeypatch.setattr(db.session, "add", lambda value: None)
    monkeypatch.setattr(db.session, "commit", lambda: None)

    CommunicationSettingsService.upsert_aggregator(
        name="legacy-webhook",
        provider_type="generic",
        channels=["webhook"],
        credentials=None,
    )

    assert aggregator.webhook_url is None
    assert is_encrypted_json(aggregator.credentials)
    stored_text = repr(aggregator.credentials)
    assert "basic-auth-secret" not in stored_text
    assert "webhook-token-secret-77cc" not in stored_text
    assert decrypt_json(aggregator.credentials)["webhook_url"] == legacy_url


def test_aggregator_serializer_never_returns_webhook_url_or_credential_values(monkeypatch):
    from app.notifications.routes import _serialize_aggregator
    from app.utils.crypto import encrypt_json

    _fernet(monkeypatch)
    secret_url = "https://hooks.example.test/?token=api-token-secret-9911"
    aggregator = type(
        "Aggregator",
        (),
        {
            "id": 9,
            "name": "webhook",
            "provider_type": "generic",
            "channels": ["webhook"],
            "enabled": True,
            "webhook_url": None,
            "priority": 1,
            "credentials": encrypt_json({
                "webhook_url": secret_url,
                "api_key": "api-key-secret-7722",
                "nested": {"client_secret": "client-secret-1188"},
            }),
            "updated_at": None,
        },
    )()

    payload = _serialize_aggregator(aggregator)

    assert payload["webhook_url"] == "***REDACTED***"
    assert payload["webhook_url_configured"] is True
    assert payload["credentials"]["webhook_url"] == "***REDACTED***"
    assert payload["credentials"]["api_key"] == "***REDACTED***"
    assert payload["credentials"]["nested"]["client_secret"] == "***REDACTED***"
    assert secret_url not in repr(payload)


def test_auth_configuration_hydrates_provider_secrets_from_encrypted_settings(monkeypatch):
    from app.auth.config_model import AuthConfiguration
    from app.notifications.models import CommunicationSettings
    from app.notifications.settings import CommunicationSettingsService

    _fernet(monkeypatch)
    encrypted_config = CommunicationSettingsService._encrypt_config({
        "google_client_secret": "google-client-secret-12aa",
        "sendgrid_api_key": "sendgrid-api-key-34bb",
        "twilio_account_sid": "AC_PRIVATE_56cc",
        "twilio_auth_token": "twilio-auth-token-78dd",
        "africa_talking_username": "africa-talking-user-90ee",
        "africa_talking_api_key": "africa-talking-key-aabb",
    })

    class _Query:
        def filter_by(self, **kwargs):
            assert kwargs == {"key": "auth_providers", "is_deleted": False}
            return self

        def first(self):
            return type("Setting", (), {"config": encrypted_config})()

    monkeypatch.setattr(CommunicationSettings, "query", _Query())
    config = AuthConfiguration()

    AuthConfiguration._hydrate_provider_secrets(config)

    assert config.google_client_secret == "google-client-secret-12aa"
    assert config.sendgrid_api_key == "sendgrid-api-key-34bb"
    assert config.twilio_account_sid == "AC_PRIVATE_56cc"
    assert config.twilio_auth_token == "twilio-auth-token-78dd"
    assert config.africa_talking_username == "africa-talking-user-90ee"
    assert config.africa_talking_api_key == "africa-talking-key-aabb"


def test_auth_configuration_serializer_never_returns_secret_values():
    from app.auth.config_model import AuthConfiguration

    config = AuthConfiguration(
        google_client_secret="google-client-secret-12aa",
        sendgrid_api_key="sendgrid-api-key-34bb",
        twilio_account_sid="AC_PRIVATE_56cc",
        twilio_auth_token="twilio-auth-token-78dd",
        africa_talking_username="africa-talking-user-90ee",
        africa_talking_api_key="africa-talking-key-aabb",
    )

    payload = config.to_dict(include_secrets=True)

    for secret in (
        "google-client-secret-12aa",
        "sendgrid-api-key-34bb",
        "AC_PRIVATE_56cc",
        "twilio-auth-token-78dd",
        "africa-talking-user-90ee",
        "africa-talking-key-aabb",
    ):
        assert secret not in repr(payload)
    assert payload["google_client_secret_configured"] is True
    assert payload["sendgrid_api_key_configured"] is True


def test_legacy_owner_auth_settings_template_never_prefills_provider_secrets():
    from pathlib import Path

    source = Path("templates/admin/owner/auth_settings.html").read_text(
        encoding="utf-8"
    )
    secret_fields = (
        "google_client_secret",
        "sendgrid_api_key",
        "twilio_account_sid",
        "twilio_auth_token",
        "africa_talking_username",
        "africa_talking_api_key",
    )
    for field in secret_fields:
        assert f'value="{{{{ config.{field}' not in source
        assert f'name="{field}"' in source
        assert f'name="clear_{field}"' in source
