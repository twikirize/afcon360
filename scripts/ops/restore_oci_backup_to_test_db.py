#!/usr/bin/env python3
"""Download an OCI backup and restore it only into a disposable test database.

This utility deliberately does not create/drop databases. The target database
must already exist and its name must start with afcon360_restore_test_. The dump
contains cleanup statements, so the target must be disposable.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional


CONFIRMATION = "RESTORE_ONLY_TO_DISPOSABLE_TEST_DATABASE"


def _required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def _configuration() -> dict:
    environment = (os.getenv("BACKUP_OFFSITE_ENVIRONMENT") or "").strip().lower()
    if environment not in {"test", "testing", "staging"}:
        raise RuntimeError(
            "Restore utility only accepts BACKUP_OFFSITE_ENVIRONMENT=test or staging"
        )
    if os.getenv("BACKUP_RESTORE_CONFIRMATION") != CONFIRMATION:
        raise RuntimeError(
            "Set BACKUP_RESTORE_CONFIRMATION to the documented staging-only confirmation"
        )

    database = _required_env("BACKUP_RESTORE_TEST_DATABASE")
    if not re.fullmatch(r"afcon360_restore_test_[a-z0-9_]{1,48}", database):
        raise RuntimeError(
            "BACKUP_RESTORE_TEST_DATABASE must start with afcon360_restore_test_"
        )

    return {
        "bucket": _required_env("BACKUP_OFFSITE_BUCKET"),
        "access_key": _required_env("BACKUP_OFFSITE_ACCESS_KEY"),
        "secret_key": _required_env("BACKUP_OFFSITE_SECRET_KEY"),
        "endpoint": _required_env("OCI_ENDPOINT_URL"),
        "region": _required_env("OCI_REGION"),
        "database": database,
        "pg_host": _required_env("BACKUP_RESTORE_TEST_PGHOST"),
        "pg_port": _required_env("BACKUP_RESTORE_TEST_PGPORT"),
        "pg_user": _required_env("BACKUP_RESTORE_TEST_PGUSER"),
        "pg_password": _required_env("BACKUP_RESTORE_TEST_PGPASSWORD"),
    }


def _download_and_verify(
    config: dict,
    object_key: str,
    expected_sha256: str,
    expected_size: Optional[int],
    destination: Path,
) -> dict:
    import boto3
    from botocore.client import Config as BotoConfig

    if not object_key or object_key.startswith("/") or ".." in object_key.split("/"):
        raise ValueError("A valid relative OCI object key is required")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256 or ""):
        raise ValueError("--sha256 must be a 64-character hexadecimal SHA-256 digest")

    client = boto3.client(
        "s3",
        region_name=config["region"],
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )
    head = client.head_object(Bucket=config["bucket"], Key=object_key)
    remote_size = int(head.get("ContentLength", -1))
    metadata = {
        str(key).lower(): str(value)
        for key, value in (head.get("Metadata") or {}).items()
    }
    if remote_size < 0:
        raise RuntimeError("OCI object did not report a valid content length")
    if expected_size is not None and remote_size != expected_size:
        raise RuntimeError("OCI object size does not match --expected-size")
    if metadata.get("sha256") != expected_sha256.lower():
        raise RuntimeError("OCI object checksum metadata does not match --sha256")

    response = client.get_object(Bucket=config["bucket"], Key=object_key)
    body = response["Body"]
    digest = hashlib.sha256()
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as output:
            os.chmod(destination, 0o600)
            for chunk in iter(lambda: body.read(1024 * 1024), b""):
                output.write(chunk)
                digest.update(chunk)
                total += len(chunk)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        body.close()

    actual = digest.hexdigest()
    if total != remote_size or actual != expected_sha256.lower():
        destination.unlink(missing_ok=True)
        raise RuntimeError("Downloaded OCI backup failed size or SHA-256 verification")

    return {
        "bucket": config["bucket"],
        "object_key": object_key,
        "path": str(destination),
        "size": total,
        "sha256": actual,
        "verified": True,
    }


def _restore_to_test_database(
    config: dict,
    backup_path: Path,
    timeout: int,
    expected_revision: Optional[str] = None,
    expected_table_count: Optional[int] = None,
    expected_users_count: Optional[int] = None,
    expected_marker: Optional[str] = None,
) -> dict[str, Any]:
    psql = shutil.which(os.getenv("PSQL_PATH") or "psql")
    if not psql:
        raise RuntimeError("psql was not found on PATH")

    command = [
        psql,
        "--no-psqlrc",
        "--host", config["pg_host"],
        "--port", config["pg_port"],
        "--username", config["pg_user"],
        "--dbname", config["database"],
        "--single-transaction",
        "--set", "ON_ERROR_STOP=on",
        "--echo-errors",
        "--quiet",
    ]
    env = os.environ.copy()
    env["PGPASSWORD"] = config["pg_password"]

    try:
        if backup_path.suffix.lower() == ".gz":
            with gzip.open(backup_path, "rt", encoding="utf-8") as source:
                result = subprocess.run(
                    command,
                    stdin=source,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=timeout,
                    check=False,
                )
        else:
            with backup_path.open("r", encoding="utf-8") as source:
                result = subprocess.run(
                    command,
                    stdin=source,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=timeout,
                    check=False,
                )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"psql restore exceeded the {timeout}-second timeout") from exc

    if result.returncode:
        detail = (result.stderr or "").strip()[-2000:]
        raise RuntimeError(f"psql restore failed (exit {result.returncode}): {detail}")

    verify_command = [
        psql,
        "--no-psqlrc",
        "--host", config["pg_host"],
        "--port", config["pg_port"],
        "--username", config["pg_user"],
        "--dbname", config["database"],
        "--no-align",
        "--tuples-only",
        "--command",
        (
            "SELECT current_database() || '|' || "
            "COALESCE((SELECT string_agg(version_num, ',') FROM alembic_version), '') || '|' || "
            "(SELECT count(*)::text FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')) || '|' || "
            "(SELECT count(*)::text FROM users)"
            + (
                " || '|' || (SELECT count(*)::text "
                "FROM public.oci_backup_drill_marker WHERE marker = "
                + "'" + expected_marker + "'"
            ) if expected_marker else ""
        ),
    ]
    check = subprocess.run(
        verify_command,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    if check.returncode:
        raise RuntimeError("Post-restore schema verification query failed")
    value = (check.stdout or "").strip()
    try:
        parts = value.split("|")
        if len(parts) != (5 if expected_marker else 4):
            raise ValueError("Unexpected verification field count")
        database, revision, count_text, users_text = parts[:4]
        table_count = int(count_text)
        users_count = int(users_text)
        marker_count = int(parts[4]) if expected_marker else None
    except (ValueError, TypeError):
        raise RuntimeError("Post-restore verification returned an invalid result") from None
    if database != config["database"] or not revision or table_count <= 0 or users_count < 1:
        raise RuntimeError(
            "Post-restore verification did not find the expected test database, "
            "Alembic revision, tables, and at least one user"
        )
    if expected_revision is not None and revision != expected_revision:
        raise RuntimeError("Restored Alembic revision does not match the source backup")
    if expected_table_count is not None and table_count != expected_table_count:
        raise RuntimeError("Restored table count does not match the source database")
    if expected_users_count is not None and users_count != expected_users_count:
        raise RuntimeError("Restored user count does not match the source database")
    if expected_marker is not None and marker_count != 1:
        raise RuntimeError("The expected synthetic recovery marker is missing after restore")
    return {
        "table_count": table_count,
        "alembic_revision": revision,
        "users_count": users_count,
        "marker_count": marker_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download a recorded OCI backup and restore into a disposable test PostgreSQL database."
    )
    parser.add_argument("--object-key", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--expected-size", type=int)
    parser.add_argument("--expected-alembic-revision")
    parser.add_argument("--expected-table-count", type=int)
    parser.add_argument("--expected-users-count", type=int)
    parser.add_argument(
        "--expected-marker",
        help="Require this synthetic marker row to exist exactly once after restore",
    )
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument(
        "--keep-download",
        action="store_true",
        help="Retain the downloaded backup in the temporary recovery directory",
    )
    args = parser.parse_args()

    config = _configuration()
    workspace = Path(tempfile.mkdtemp(prefix="afcon360-oci-restore-"))
    backup_path = workspace / Path(args.object_key).name

    try:
        downloaded = _download_and_verify(
            config,
            args.object_key,
            args.sha256,
            args.expected_size,
            backup_path,
        )
        if args.expected_marker and not re.fullmatch(r"[A-Z0-9_]{1,100}", args.expected_marker):
            raise ValueError("--expected-marker must contain only uppercase letters, digits and underscores")
        verification = _restore_to_test_database(
            config,
            backup_path,
            args.timeout,
            expected_revision=args.expected_alembic_revision,
            expected_table_count=args.expected_table_count,
            expected_users_count=args.expected_users_count,
            expected_marker=args.expected_marker,
        )
        print("OFFSITE_DOWNLOAD_VERIFIED=true")
        print(f"OBJECT_KEY={downloaded['object_key']}")
        print(f"DOWNLOADED_BYTES={downloaded['size']}")
        print(f"SHA256={downloaded['sha256']}")
        print(f"RESTORED_DATABASE={config['database']}")
        print(f"ALEMBIC_REVISION={verification['alembic_revision']}")
        print(f"RESTORED_TABLES={verification['table_count']}")
        print(f"RESTORED_USERS={verification['users_count']}")
        if verification["marker_count"] is not None:
            print(f"RESTORED_MARKER_ROWS={verification['marker_count']}")
        print("RESTORE_VERIFIED=true")
        return 0
    finally:
        if not args.keep_download:
            shutil.rmtree(workspace, ignore_errors=True)
        else:
            print(f"RECOVERY_WORKSPACE={workspace}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"RECOVERY_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
