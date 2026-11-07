"""Unit tests for optional OCI off-site backup replication.

These tests use a fake S3-compatible client and never contact OCI.
"""

import hashlib
import io

import pytest

pytestmark = pytest.mark.no_database


class _FakeS3Client:
    def __init__(self, uploaded_bytes=None):
        self.uploaded_bytes = uploaded_bytes
        self.upload_args = None
        self.put_args = None
        self.object_metadata = None

    def put_object(self, Bucket, Key, Body, ContentLength, Metadata=None):
        self.uploaded_bytes = Body.read()
        self.put_args = (Bucket, Key, ContentLength)
        self.object_metadata = dict(Metadata or {})

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        with open(filename, "rb") as source:
            self.uploaded_bytes = source.read()
        self.upload_args = (filename, bucket, key)
        self.object_metadata = (ExtraArgs or {}).get("Metadata", {})

    def head_object(self, Bucket, Key):
        return {
            "ContentLength": len(self.uploaded_bytes),
            "Metadata": dict(self.object_metadata),
            "VersionId": "test-version-1",
        }

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.uploaded_bytes)}


def _configure_offsite(app):
    app.config.update(
        BACKUP_OFFSITE_ENABLED=True,
        BACKUP_OFFSITE_BUCKET="afcon360-backups-test",
        BACKUP_OFFSITE_ACCESS_KEY="test-access-key",
        BACKUP_OFFSITE_SECRET_KEY="test-secret-key",
        BACKUP_OFFSITE_PREFIX="afcon360/backups",
        BACKUP_OFFSITE_ENVIRONMENT="test",
        OCI_ENDPOINT_URL="https://objectstorage.example.invalid",
        OCI_REGION="eu-frankfurt-1",
    )


def test_offsite_backup_upload_verifies_remote_content_checksum(
    app, monkeypatch, tmp_path
):
    import boto3

    from app.backup.backup_service import BackupService

    payload = b"AFCON360 backup artifact for off-site checksum test"
    backup_path = tmp_path / "database_manual_test.sql.gz"
    backup_path.write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()

    fake_client = _FakeS3Client()
    client_calls = []

    def _client_factory(service_name, **kwargs):
        client_calls.append((service_name, kwargs))
        return fake_client

    monkeypatch.setattr(boto3, "client", _client_factory)
    _configure_offsite(app)

    with app.app_context():
        result = BackupService.__new__(BackupService)._upload_offsite_artifact(
            str(backup_path), "database", checksum, backup_public_id="backup-test-123"
        )

    assert result["provider"] == "oci"
    assert result["bucket"] == "afcon360-backups-test"
    assert result["object_key"].startswith(
        "afcon360/backups/test/database/"
    )
    assert "/backup-test-123/" in result["object_key"]
    assert result["sha256"] == checksum
    assert result["size"] == len(payload)
    assert result["verified"] is True
    assert result["version_id"] == "test-version-1"
    assert fake_client.uploaded_bytes == payload
    assert fake_client.put_args == (
        "afcon360-backups-test", result["object_key"], len(payload)
    )

    assert len(client_calls) == 1
    service_name, kwargs = client_calls[0]
    assert service_name == "s3"
    assert kwargs["aws_access_key_id"] == "test-access-key"
    assert kwargs["aws_secret_access_key"] == "test-secret-key"
    # OCI's S3 compatibility API requires Signature Version 4 and path-style URLs.
    assert kwargs["config"].signature_version == "s3v4"
    assert kwargs["config"].s3 == {"addressing_style": "path"}


def test_offsite_backup_upload_rejects_remote_content_mismatch(
    app, monkeypatch, tmp_path
):
    import boto3

    from app.backup.backup_service import BackupService

    payload = b"original local backup bytes"
    backup_path = tmp_path / "files_manual_test.tar.gz"
    backup_path.write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()

    fake_client = _FakeS3Client()

    def _tampered_get_object(Bucket, Key):
        return {"Body": io.BytesIO(b"tampered remote bytes")}

    fake_client.get_object = _tampered_get_object
    monkeypatch.setattr(boto3, "client", lambda service_name, **kwargs: fake_client)
    _configure_offsite(app)

    with app.app_context():
        with pytest.raises(RuntimeError, match="content checksum mismatch"):
            BackupService.__new__(BackupService)._upload_offsite_artifact(
                str(backup_path), "files", checksum
            )


def test_enabled_offsite_backup_requires_complete_private_target_config(
    app, monkeypatch, tmp_path
):
    import boto3

    from app.backup.backup_service import BackupService

    backup_path = tmp_path / "database_manual_test.sql.gz"
    backup_path.write_bytes(b"backup")
    checksum = hashlib.sha256(b"backup").hexdigest()

    app.config.update(
        BACKUP_OFFSITE_ENABLED=True,
        BACKUP_OFFSITE_BUCKET="",
        BACKUP_OFFSITE_ACCESS_KEY="",
        BACKUP_OFFSITE_SECRET_KEY="",
        OCI_ENDPOINT_URL="",
        OCI_REGION="",
    )

    def _unexpected_client(*args, **kwargs):
        pytest.fail("OCI client must not be created with incomplete configuration")

    monkeypatch.setattr(boto3, "client", _unexpected_client)

    with app.app_context():
        with pytest.raises(
            RuntimeError,
            match="required settings are missing",
        ):
            BackupService.__new__(BackupService)._upload_offsite_artifact(
                str(backup_path), "database", checksum
            )

def test_offsite_backup_download_verifies_and_writes_new_file(
    app, monkeypatch, tmp_path
):
    import boto3

    from app.backup.backup_service import BackupService

    payload = b"AFCON360 verified remote backup download"
    checksum = hashlib.sha256(payload).hexdigest()
    destination = tmp_path / "recovery" / "database.sql.gz"
    partial_modes = []

    class _InspectingBody(io.BytesIO):
        def read(self, size=-1):
            partial_files = list(destination.parent.glob(".database.sql.gz.partial-*"))
            if partial_files:
                partial_modes.append(partial_files[0].stat().st_mode & 0o777)
            return super().read(size)

    fake_client = _FakeS3Client(payload)
    fake_client.object_metadata = {"sha256": checksum}
    fake_client.get_object = lambda **_: {"Body": _InspectingBody(payload)}
    client_calls = []

    def _client_factory(service_name, **kwargs):
        client_calls.append((service_name, kwargs))
        return fake_client

    monkeypatch.setattr(boto3, "client", _client_factory)
    _configure_offsite(app)
    with app.app_context():
        result = BackupService.__new__(BackupService)._download_offsite_artifact(
            bucket="afcon360-backups-test",
            object_key="afcon360/backups/test/database/database.sql.gz",
            destination_path=str(destination),
            expected_sha256=checksum,
            expected_size=len(payload),
        )

    assert result["verified"] is True
    assert result["sha256"] == checksum
    assert result["size"] == len(payload)
    assert destination.read_bytes() == payload
    assert destination.stat().st_mode & 0o777 == 0o600
    assert partial_modes and set(partial_modes) == {0o600}
    assert len(client_calls) == 1
    assert client_calls[0][1]["config"].signature_version == "s3v4"
    assert client_calls[0][1]["config"].s3 == {"addressing_style": "path"}

    # A recovery file is never silently overwritten.
    with app.app_context():
        with pytest.raises(FileExistsError):
            BackupService.__new__(BackupService)._download_offsite_artifact(
                bucket="afcon360-backups-test",
                object_key="afcon360/backups/test/database/database.sql.gz",
                destination_path=str(destination),
                expected_sha256=checksum,
                expected_size=len(payload),
            )
    assert destination.read_bytes() == payload


def test_offsite_backup_download_rejects_corrupted_content_without_leaving_partial_file(
    app, monkeypatch, tmp_path
):
    import boto3

    from app.backup.backup_service import BackupService

    payload = b"AFCON360 expected bytes"
    checksum = hashlib.sha256(payload).hexdigest()
    fake_client = _FakeS3Client(payload)
    fake_client.object_metadata = {"sha256": checksum}
    # Keep the byte length identical so this exercises SHA-256 mismatch,
    # not only the earlier content-length guard.
    fake_client.get_object = lambda **_: {
        "Body": io.BytesIO(b"AFCON360 tampered bytes")
    }
    monkeypatch.setattr(boto3, "client", lambda service_name, **kwargs: fake_client)
    _configure_offsite(app)

    destination = tmp_path / "recovery" / "tampered.sql.gz"
    with app.app_context():
        with pytest.raises(RuntimeError, match="content checksum mismatch"):
            BackupService.__new__(BackupService)._download_offsite_artifact(
                bucket="afcon360-backups-test",
                object_key="afcon360/backups/test/database/tampered.sql.gz",
                destination_path=str(destination),
                expected_sha256=checksum,
                expected_size=len(payload),
            )

    assert not destination.exists()
    if destination.parent.exists():
        assert list(destination.parent.glob("*.partial-*")) == []
