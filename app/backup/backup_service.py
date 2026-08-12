"""
Automated Backup and Disaster Recovery Service for AFCON360

Implements PostgreSQL database dumps (pg_dump), file backups (tar+gzip),
configuration snapshots, SHA-256 checksum verification, and disaster-recovery
restores via psql.

Design notes (production hardening):
- All models inherit from app.models.base.BaseModel (BigInteger PK, soft delete).
- Backups are never exposed by internal `id`; routes use `public_id` (UUID).
- All pg_dump/psql calls go through subprocess with PGPASSWORD injected via the
  environment (never on the command line) and a hard timeout to avoid hangs.
- Scheduling is delegated to Celery beat (see app/tasks/backup_tasks.py); this
  module intentionally has NO hard dependency on the `schedule` library.
"""

import os
import gzip
import json
import shutil
import hashlib
import subprocess
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from flask import current_app
from app.extensions import db
from app.models.base import BaseModel
from app.config import Config


logger = logging.getLogger(__name__)


class BackupType:
    """Backup type constants."""
    DATABASE = "database"
    FILES = "files"
    CONFIG = "config"
    FULL = "full"
    ALL = (DATABASE, FILES, CONFIG, FULL)


class BackupSchedule:
    """Backup schedule constants."""
    MANUAL = "manual"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ALL = (MANUAL, HOURLY, DAILY, WEEKLY, MONTHLY)


class BackupStatus:
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ALL = (RUNNING, COMPLETED, FAILED)


# Retention policy (how many completed backups to keep per schedule).
DEFAULT_RETENTION = {
    BackupSchedule.HOURLY: 24,
    BackupSchedule.DAILY: 30,
    BackupSchedule.WEEKLY: 12,
    BackupSchedule.MONTHLY: 24,
}

# Default backup directory (overridable via BACKUP_DIR config / env).
DEFAULT_BACKUP_DIR = "/var/backups/afcon360"

# Directories mirrored by a "files" backup (relative to app root).
FILE_BACKUP_DIRS = ("templates", "static", "uploads", "logs")


class BackupRecord(BaseModel):
    """Tracks a single backup operation and its resulting artifact."""

    __tablename__ = "backup_records"

    public_id = db.Column(
        db.String(64), unique=True, nullable=False, index=True,
        default=lambda: uuid.uuid4().hex,
    )
    backup_type = db.Column(db.String(20), nullable=False, index=True)
    backup_schedule = db.Column(db.String(20), nullable=False, default=BackupSchedule.MANUAL)
    file_path = db.Column(db.String(500), nullable=True)
    file_name = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    checksum = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(20), nullable=False, default=BackupStatus.RUNNING, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_by = db.Column(db.BigInteger, nullable=True)

    def __repr__(self):
        return f"<BackupRecord {self.public_id} {self.backup_type} {self.status}>"

    @property
    def is_completed_flag(self) -> bool:
        return self.status == BackupStatus.COMPLETED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "public_id": self.public_id,
            "backup_type": self.backup_type,
            "backup_schedule": self.backup_schedule,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "checksum": self.checksum,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "error_message": self.error_message,
            "created_by": self.created_by,
        }


class BackupService:
    """Core backup / restore engine backed by pg_dump and psql."""

    def __init__(self):
        self.backup_dir = current_app.config.get("BACKUP_DIR") or DEFAULT_BACKUP_DIR
        self.compression_enabled = True
        self.max_backups = dict(DEFAULT_RETENTION)
        self.dump_timeout = int(current_app.config.get("BACKUP_DUMP_TIMEOUT", 1800))
        os.makedirs(self.backup_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Tooling helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _which(tool: str) -> Optional[str]:
        return shutil.which(tool)

    def _require_tool(self, tool: str) -> str:
        path = self._which(tool)
        if not path:
            raise RuntimeError(
                f"'{tool}' executable not found on PATH. Install PostgreSQL client "
                f"tools (pg_dump/psql) and ensure they are on PATH for backup/restore."
            )
        return path

    def _get_database_config(self) -> Dict[str, str]:
        return {
            "host": Config.DB_HOST,
            "port": str(Config.DB_PORT),
            "user": Config.DB_USER,
            "password": Config.DB_PASS,
            "dbname": Config.DB_NAME,
        }

    def _db_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        pwd = self._get_database_config().get("password")
        if pwd:
            env["PGPASSWORD"] = pwd
        return env

    @staticmethod
    def _calculate_checksum(file_path: str) -> str:
        hash_sha = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                hash_sha.update(chunk)
        return hash_sha.hexdigest()

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def get_backup(public_id: str) -> Optional[BackupRecord]:
        return BackupRecord.query.filter_by(
            public_id=public_id, is_deleted=False
        ).first()

    @staticmethod
    def list_backups(backup_type: Optional[str] = None, limit: int = 100) -> List[BackupRecord]:
        q = BackupRecord.query.filter_by(is_deleted=False)
        if backup_type:
            q = q.filter_by(backup_type=backup_type)
        return q.order_by(BackupRecord.created_at.desc()).limit(limit).all()

    def get_backup_status(self) -> Dict[str, Any]:
        records = BackupRecord.query.filter_by(is_deleted=False).all()
        completed = [r for r in records if r.status == BackupStatus.COMPLETED]
        failed = [r for r in records if r.status == BackupStatus.FAILED]
        running = [r for r in records if r.status == BackupStatus.RUNNING]
        last = max((r.completed_at for r in completed if r.completed_at), default=None)
        return {
            "total": len(records),
            "completed": len(completed),
            "failed": len(failed),
            "running": len(running),
            "last_completed_at": last.isoformat() if last else None,
            "backup_directory": self.backup_dir,
        }

    # ------------------------------------------------------------------ #
    # Create backups
    # ------------------------------------------------------------------ #
    def _finalize_success(self, record: BackupRecord, backup_path: str,
                          metadata: Optional[Dict[str, Any]] = None) -> BackupRecord:
        record.file_path = backup_path
        record.file_name = os.path.basename(backup_path)
        record.file_size = os.path.getsize(backup_path)
        record.checksum = self._calculate_checksum(backup_path)
        record.status = BackupStatus.COMPLETED
        record.completed_at = datetime.now(timezone.utc)
        if metadata:
            record.metadata_json = metadata
        db.session.commit()
        return record

    def _finalize_failure(self, record: BackupRecord, error: str) -> BackupRecord:
        record.status = BackupStatus.FAILED
        record.error_message = str(error)[:4000]
        record.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        return record

    def create_database_backup(self, schedule: str = BackupSchedule.MANUAL,
                               triggered_by: Optional[int] = None) -> BackupRecord:
        """Dump the PostgreSQL database to a compressed .sql.gz archive."""
        pg_dump = self._require_tool("pg_dump")
        record = BackupRecord(
            backup_type=BackupType.DATABASE,
            backup_schedule=schedule,
            status=BackupStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            created_by=triggered_by,
        )
        db.session.add(record)
        db.session.commit()
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"database_{schedule}_{ts}.sql"
            if self.compression_enabled:
                filename += ".gz"
            backup_path = os.path.join(self.backup_dir, filename)

            cfg = self._get_database_config()
            cmd = [
                pg_dump,
                "--host", cfg["host"],
                "--port", cfg["port"],
                "--username", cfg["user"],
                "--dbname", cfg["dbname"],
                "--verbose",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--format=plain",
            ]

            if self.compression_enabled:
                with open(backup_path, "wb") as out:
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        env=self._db_env(),
                    )
                    with gzip.open(out, "wb") as gz:
                        for chunk in iter(lambda: proc.stdout.read(65536), b""):
                            gz.write(chunk)
                    proc.wait(timeout=self.dump_timeout)
                    if proc.returncode != 0:
                        err = proc.stderr.read().decode(errors="replace")
                        raise RuntimeError(f"pg_dump failed: {err}")
            else:
                with open(backup_path, "w") as out:
                    proc = subprocess.run(
                        cmd, stdout=out, stderr=subprocess.PIPE,
                        env=self._db_env(), timeout=self.dump_timeout,
                    )
                    if proc.returncode != 0:
                        err = proc.stderr.decode(errors="replace")
                        raise RuntimeError(f"pg_dump failed: {err}")

            self._finalize_success(
                record, backup_path,
                metadata={"compression": self.compression_enabled, "tool": "pg_dump"},
            )
            self._cleanup_old_backups(BackupType.DATABASE, schedule)
            current_app.logger.info(f"Database backup completed: {backup_path}")
            return record
        except Exception as exc:
            current_app.logger.error(f"Database backup failed: {exc}")
            return self._finalize_failure(record, exc)

    def create_files_backup(self, schedule: str = BackupSchedule.WEEKLY,
                            triggered_by: Optional[int] = None) -> BackupRecord:
        """Archive application directories (templates/static/uploads/logs) as tar.gz."""
        record = BackupRecord(
            backup_type=BackupType.FILES,
            backup_schedule=schedule,
            status=BackupStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            created_by=triggered_by,
        )
        db.session.add(record)
        db.session.commit()
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"files_{schedule}_{ts}.tar.gz"
            backup_path = os.path.join(self.backup_dir, filename)

            app_root = current_app.root_path
            dirs = [d for d in FILE_BACKUP_DIRS if os.path.isdir(os.path.join(app_root, d))]
            if not dirs:
                raise RuntimeError("No backup directories found to archive.")

            raw_tar = backup_path.replace(".gz", "")
            cmd = ["tar", "-czf", backup_path, "-C", app_root] + dirs
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.dump_timeout)
            if proc.returncode != 0:
                raise RuntimeError(f"tar failed: {proc.stderr}")
            if os.path.exists(raw_tar):
                os.remove(raw_tar)

            self._finalize_success(
                record, backup_path,
                metadata={"directories": dirs, "compression": True, "tool": "tar"},
            )
            self._cleanup_old_backups(BackupType.FILES, schedule)
            current_app.logger.info(f"Files backup completed: {backup_path}")
            return record
        except Exception as exc:
            current_app.logger.error(f"Files backup failed: {exc}")
            return self._finalize_failure(record, exc)

    def create_config_backup(self, schedule: str = BackupSchedule.MONTHLY,
                             triggered_by: Optional[int] = None) -> BackupRecord:
        """Snapshot dynamic SystemConfig values to a JSON archive."""
        record = BackupRecord(
            backup_type=BackupType.CONFIG,
            backup_schedule=schedule,
            status=BackupStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            created_by=triggered_by,
        )
        db.session.add(record)
        db.session.commit()
        try:
            from app.models.system_config import SystemConfig

            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"config_{schedule}_{ts}.json"
            if self.compression_enabled:
                filename += ".gz"
            backup_path = os.path.join(self.backup_dir, filename)

            rows = SystemConfig.query.filter_by(is_deleted=False).all()
            config_data = [
                {
                    "key": r.key,
                    "value": r.value,
                    "value_type": r.value_type,
                    "category": r.category,
                    "description": r.description,
                }
                for r in rows
            ]
            payload = {
                "generated_at": ts,
                "count": len(config_data),
                "settings": config_data,
            }

            if self.compression_enabled:
                with gzip.open(backup_path, "wt", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, default=str)
            else:
                with open(backup_path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, default=str)

            self._finalize_success(
                record, backup_path,
                metadata={"count": len(config_data), "compression": self.compression_enabled},
            )
            self._cleanup_old_backups(BackupType.CONFIG, schedule)
            current_app.logger.info(f"Config backup completed: {backup_path}")
            return record
        except Exception as exc:
            current_app.logger.error(f"Config backup failed: {exc}")
            return self._finalize_failure(record, exc)

    def create_full_backup(self, schedule: str = BackupSchedule.DAILY,
                           triggered_by: Optional[int] = None) -> Dict[str, BackupRecord]:
        """Convenience: run database + files + config backups together."""
        return {
            BackupType.DATABASE: self.create_database_backup(schedule, triggered_by),
            BackupType.FILES: self.create_files_backup(schedule, triggered_by),
            BackupType.CONFIG: self.create_config_backup(schedule, triggered_by),
        }

    # ------------------------------------------------------------------ #
    # Restore & delete
    # ------------------------------------------------------------------ #
    def restore_database(self, public_id: str, verify_checksum: bool = True) -> bool:
        """
        Restore the database from a completed backup artifact using psql.

        WARNING: this is destructive. The dump was created with --clean and is
        replayed with --single-transaction so it either fully applies or rolls
        back. Callers MUST have confirmed owner intent before invoking.
        """
        psql = self._require_tool("psql")
        record = self.get_backup(public_id)
        if not record or record.backup_type != BackupType.DATABASE:
            raise ValueError("Database backup not found or invalid type.")
        if record.status != BackupStatus.COMPLETED:
            raise ValueError("Cannot restore an incomplete/failed backup.")

        backup_path = record.file_path
        if not backup_path or not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup file missing: {backup_path}")

        if verify_checksum:
            if self._calculate_checksum(backup_path) != record.checksum:
                raise ValueError("Checksum mismatch - backup may be corrupted.")

        cfg = self._get_database_config()
        cmd = [
            psql,
            "--host", cfg["host"],
            "--port", cfg["port"],
            "--username", cfg["user"],
            "--dbname", cfg["dbname"],
            "--single-transaction",
            "--echo-errors",
            "--quiet",
        ]

        try:
            if backup_path.endswith(".gz"):
                with gzip.open(backup_path, "rt", encoding="utf-8") as fh:
                    proc = subprocess.run(
                        cmd, stdin=fh, capture_output=True, text=True,
                        env=self._db_env(), timeout=self.dump_timeout,
                    )
            else:
                with open(backup_path, "r", encoding="utf-8") as fh:
                    proc = subprocess.run(
                        cmd, stdin=fh, capture_output=True, text=True,
                        env=self._db_env(), timeout=self.dump_timeout,
                    )
            if proc.returncode != 0:
                raise RuntimeError(f"psql restore failed: {proc.stderr}")
        except Exception as exc:
            current_app.logger.error(f"Database restore failed: {exc}")
            raise

        current_app.logger.info(f"Database restored from: {backup_path}")
        return True

    def delete_backup(self, public_id: str) -> bool:
        """Soft-delete a backup record and remove its artifact from disk."""
        record = self.get_backup(public_id)
        if not record:
            return False
        try:
            if record.file_path and os.path.exists(record.file_path):
                os.remove(record.file_path)
        except OSError as exc:
            current_app.logger.warning(f"Could not remove backup file {record.file_path}: {exc}")
        record.soft_delete()
        return True

    # ------------------------------------------------------------------ #
    # Retention
    # ------------------------------------------------------------------ #
    def _cleanup_old_backups(self, backup_type: str, schedule: str) -> None:
        """Keep only the most recent N completed backups for a given schedule."""
        max_keep = self.max_backups.get(schedule, 10)
        if max_keep <= 0:
            return
        old = (
            BackupRecord.query.filter_by(
                is_deleted=False,
                backup_type=backup_type,
                backup_schedule=schedule,
                status=BackupStatus.COMPLETED,
            )
            .order_by(BackupRecord.created_at.desc())
            .offset(max_keep)
            .all()
        )
        for backup in old:
            try:
                if backup.file_path and os.path.exists(backup.file_path):
                    os.remove(backup.file_path)
                backup.soft_delete()
            except OSError as exc:
                current_app.logger.warning(
                    f"Failed to purge old backup {backup.public_id}: {exc}"
                )
        db.session.commit()
