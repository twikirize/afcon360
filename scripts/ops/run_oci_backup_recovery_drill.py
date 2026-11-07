#!/usr/bin/env python3
"""Run a real OCI upload/download/restore drill against disposable databases.

This script is intended for the protected GitHub Actions staging workflow.
It creates only synthetic source data, calls the application's BackupService,
and emits non-secret verification facts through GITHUB_OUTPUT.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

# Running a file under scripts/ops puts that directory, not the repository
# root, at sys.path[0]. Add the project root so `import app` works both in
# GitHub Actions and when this utility is launched from another directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text


def _write_outputs(values: dict[str, Any]) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as output:
        for key, value in values.items():
            rendered = str(value)
            if "\n" in rendered or "\r" in rendered:
                raise RuntimeError(f"Unsafe newline in workflow output: {key}")
            output.write(f"{key}={rendered}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a synthetic AFCON360 database backup and replicate it to OCI."
    )
    parser.add_argument("--marker", required=True)
    parser.add_argument("--run-token", required=True)
    args = parser.parse_args()

    if not re.fullmatch(r"AFCON360_OCI_DRILL_[A-Z0-9_]{1,80}", args.marker):
        raise ValueError("--marker must be a safe AFCON360_OCI_DRILL_ token")
    if not re.fullmatch(r"[a-z0-9_]{1,48}", args.run_token):
        raise ValueError("--run-token must contain only lowercase letters, digits and underscores")

    from app import create_app
    from app.backup.backup_service import (
        BackupSchedule,
        BackupService,
        BackupStatus,
    )
    from app.extensions import db
    from app.identity.models.user import User

    app = create_app()
    backup_dir = os.getenv("BACKUP_DIR")
    if not backup_dir or not backup_dir.startswith("/tmp/afcon360-oci-drill-"):
        raise RuntimeError(
            "The OCI drill requires BACKUP_DIR to point to its dedicated /tmp workspace"
        )
    # BackupService reads Flask's app config, not os.environ directly. Apply
    # this drill-only temporary path explicitly instead of the production
    # default /var/backups/afcon360.
    app.config["BACKUP_DIR"] = backup_dir
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)

    with app.app_context():
        # A dedicated marker table makes the restored contents independently
        # verifiable. It contains no production or personal information.
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS public.oci_backup_drill_marker (
                marker text PRIMARY KEY,
                created_at timestamptz NOT NULL DEFAULT now()
            )
        """))
        db.session.execute(
            text("""
                INSERT INTO public.oci_backup_drill_marker (marker)
                VALUES (:marker)
                ON CONFLICT (marker) DO NOTHING
            """),
            {"marker": args.marker},
        )

        email = f"oci-drill-{args.run_token}@example.test"
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(
                username=f"oci_drill_{args.run_token}",
                email=email,
                is_verified=True,
                is_active=True,
            )
            user.set_password("OCI-DRILL-NOT-A-REAL-ACCOUNT")
            db.session.add(user)
        db.session.commit()

        # Capture the source state before the dump. The restore utility must
        # observe the same revision, table count, user count and marker.
        revision = db.session.execute(
            text("SELECT string_agg(version_num, ',') FROM alembic_version")
        ).scalar_one()
        table_count = db.session.execute(text("""
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        """)).scalar_one()
        users_count = User.query.count()
        marker_count = db.session.execute(
            text("""
                SELECT count(*)
                FROM public.oci_backup_drill_marker
                WHERE marker = :marker
            """),
            {"marker": args.marker},
        ).scalar_one()

        if not revision or int(table_count) <= 0 or int(users_count) < 1 or int(marker_count) != 1:
            raise RuntimeError("Synthetic source database did not meet pre-backup verification")

        service = BackupService()
        record = service.create_database_backup(schedule=BackupSchedule.MANUAL)
        if record.status != BackupStatus.COMPLETED:
            raise RuntimeError(
                "Application database backup did not complete: "
                + str(record.error_message or "no error detail")
            )

        offsite = (record.metadata_json or {}).get("offsite") or {}
        if offsite.get("provider") != "oci" or offsite.get("verified") is not True:
            raise RuntimeError("Application backup did not confirm a verified OCI object")

        required = {
            "object_key": offsite.get("object_key"),
            "sha256": record.checksum,
            "size": record.file_size,
        }
        if not all(value is not None and value != "" for value in required.values()):
            raise RuntimeError("Completed backup record is missing OCI recovery metadata")

        outputs = {
            "object_key": required["object_key"],
            "sha256": required["sha256"],
            "size": required["size"],
            "expected_revision": revision,
            "expected_table_count": int(table_count),
            "expected_users_count": int(users_count),
            "expected_marker": args.marker,
        }
        _write_outputs(outputs)

        print("LOCAL_DATABASE_BACKUP_COMPLETED=true")
        print("OCI_UPLOAD_AND_REMOTE_READBACK_VERIFIED=true")
        print(f"OCI_OBJECT_KEY={required['object_key']}")
        print(f"BACKUP_BYTES={required['size']}")
        print(f"BACKUP_SHA256={required['sha256']}")
        print(f"SOURCE_ALEMBIC_REVISION={revision}")
        print(f"SOURCE_TABLES={table_count}")
        print(f"SOURCE_USERS={users_count}")
        print("SYNTHETIC_MARKER_PRESENT=true")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"OCI_BACKUP_DRILL_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
