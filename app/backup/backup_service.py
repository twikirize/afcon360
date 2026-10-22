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
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable

from flask import current_app
from app.extensions import db
from app.models.base import BaseModel
from app.config import Config


class BackupCancelledError(Exception):
    """Raised when an operator cancels a running backup.

    The backup is terminated cooperatively: the child process is stopped and
    the partial artifact is discarded. The durable record is finalized as
    FAILED (there is no CANCELLED status in the existing contract) with this
    error message so the operator can distinguish it from a real failure.
    """


class BackupProgress:
    """Thread-safe progress tracker for backup operations."""

    # Cap the retained activity log so a long-running dump cannot grow the
    # tracker state (and therefore every progress response) without bound.
    MAX_DETAILS = 60

    def __init__(self, backup_id: str, socketio=None, namespace: str = '/admin'):
        self.backup_id = backup_id
        self.socketio = socketio
        self.namespace = namespace
        self._lock = threading.Lock()
        self._current_step = ""
        self._current_substep = ""
        self._progress = 0
        self._total_steps = 0
        self._completed_steps = 0
        self._details = []
        self._started_at = time.time()
        self._finished = False
        self._finished_at = None
        self._record_public_id = None
        self._error = None
        self._cancelled = False

    def start(self, total_steps: int, description: str = "Starting backup..."):
        with self._lock:
            self._total_steps = total_steps
            self._current_step = description
            self._progress = 0
            self._completed_steps = 0
            self._details = [description]
        self._publish()

    def step(self, description: str, progress: Optional[int] = None):
        with self._lock:
            self._completed_steps += 1
            if progress is not None:
                self._progress = min(100, max(0, progress))
            else:
                self._progress = min(100, int((self._completed_steps / max(1, self._total_steps)) * 100))
            self._current_step = description
            self._append_detail(description)
        self._publish()

    def substep(self, description: str):
        with self._lock:
            self._current_substep = description
            self._append_detail(f"→ {description}")
        self._publish()

    def complete(self, success: bool = True, message: str = "Completed"):
        with self._lock:
            self._progress = 100 if success else 0
            self._current_step = message
            self._finished = True
            self._finished_at = time.time()
        self._publish()

    def fail(self, error: str):
        with self._lock:
            self._progress = 0
            self._current_step = f"Failed: {error}"
            self._error = str(error)
            self._finished = True
            self._finished_at = time.time()
        self._publish()

    def set_record(self, public_id: Optional[str]):
        """Link the tracker to the durable BackupRecord public_id."""
        with self._lock:
            self._record_public_id = public_id

    @property
    def record_public_id(self) -> Optional[str]:
        with self._lock:
            return self._record_public_id

    @property
    def finished(self) -> bool:
        with self._lock:
            return self._finished

    def request_cancel(self) -> bool:
        """Flag the running backup for cooperative cancellation."""
        with self._lock:
            if self._finished:
                return False
            self._cancelled = True
            self._current_step = "Cancellation requested..."
            self._append_detail("Cancellation requested by operator")
        self._publish()
        return True

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def _append_detail(self, entry: str):
        self._details.append(entry)
        if len(self._details) > self.MAX_DETAILS:
            del self._details[: len(self._details) - self.MAX_DETAILS]

    def _publish(self):
        """Emit the current state to Socket.IO.

        MUST be called with self._lock NOT held. get_state() acquires the
        lock, and threading.Lock is not reentrant, so emitting while the
        lock is held would deadlock the backup worker.
        """
        if self.socketio:
            try:
                self.socketio.emit('backup_progress', self.get_state(), namespace=self.namespace)
            except Exception:
                pass  # Don't let socket errors break backup

    def _state_locked(self) -> Dict[str, Any]:
        """Build the state snapshot. Caller MUST hold self._lock."""
        return {
            'backup_id': self.backup_id,
            'record_public_id': self._record_public_id,
            'progress': self._progress,
            'step': self._current_step,
            'substep': self._current_substep,
            'details': list(self._details),
            'elapsed': int(time.time() - self._started_at),
            'finished': self._finished,
            'error': self._error,
            'cancelled': self._cancelled,
        }

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return self._state_locked()


# Global progress tracker registry
_progress_registry: Dict[str, BackupProgress] = {}
_registry_lock = threading.Lock()


def get_progress_tracker(backup_id: str) -> Optional[BackupProgress]:
    with _registry_lock:
        return _progress_registry.get(backup_id)


def create_progress_tracker(backup_id: str, socketio=None, total_steps: int = 5) -> BackupProgress:
    tracker = BackupProgress(backup_id, socketio)
    with _registry_lock:
        _progress_registry[backup_id] = tracker
    return tracker


def remove_progress_tracker(backup_id: str):
    with _registry_lock:
        _progress_registry.pop(backup_id, None)


def find_progress_tracker_by_record(record_public_id: str) -> Optional[BackupProgress]:
    """Resolve a live tracker from the durable BackupRecord public_id.

    The async route keys the tracker by a tracking id. Once the backup thread
    has created (or attached to) the real BackupRecord, callers that only know
    the record public_id can still reach the live tracker.
    """
    with _registry_lock:
        for tracker in _progress_registry.values():
            if tracker.record_public_id == record_public_id:
                return tracker
    return None


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
        """Locate a PostgreSQL client tool.

        Search order:
          1. Explicit env var override: PG_DUMP_PATH / PG_RESTORE_PATH / PSQL_PATH
          2. Standard PATH lookup
          3. Common Windows PostgreSQL install directories
        """
        # 1. Explicit env override
        env_name = f"{tool.upper()}_PATH"  # pg_dump -> PG_DUMP_PATH
        env_path = os.environ.get(env_name)
        if env_path and os.path.isfile(env_path):
            return env_path

        # 2. Standard PATH
        found = shutil.which(tool)
        if found:
            return found

        # 3. Common Windows install locations
        for version in ("18", "17", "16", "15", "14"):
            candidate = f"C:\\Program Files\\PostgreSQL\\{version}\\bin\\{tool}.exe"
            if os.path.isfile(candidate):
                return candidate

        return None

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
            "last_completed_at": last.isoformat() if last is not None else None,
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

    @staticmethod
    def _terminate_process(proc) -> None:
        """Stop a running child process, escalating to kill if needed."""
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()
        except Exception:
            pass

    @staticmethod
    def _remove_partial_artifact(backup_path: str) -> None:
        """Delete an incomplete backup artifact left behind by a failure."""
        try:
            if backup_path and os.path.exists(backup_path):
                os.remove(backup_path)
        except Exception:
            pass

    @staticmethod
    def _start_stream_reader(stream, on_line=None, max_lines: int = 200):
        """Drain a child-process stream on a background thread.

        Reading stderr only after the process has exited deadlocks the dump.
        `pg_dump --verbose` writes one line per database object; once the
        stderr pipe buffer fills, pg_dump blocks on the write, stdout never
        reaches EOF, and the parent blocks forever on stdout.

        The reader thread consumes the pipe continuously and reports each
        line through `on_line`. It returns the list that collects the lines
        (bounded by `max_lines`) and the reader thread.
        """
        collected: List[str] = []

        def _reader():
            try:
                for raw in iter(stream.readline, b""):
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    if len(collected) < max_lines:
                        collected.append(line)
                    if on_line and line:
                        try:
                            on_line(line)
                        except Exception:
                            pass
            except Exception:
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        reader = threading.Thread(target=_reader, daemon=True, name="backup-stream-reader")
        reader.start()
        return collected, reader

    def create_database_backup(self, schedule: str = BackupSchedule.MANUAL,
                               triggered_by: Optional[int] = None,
                               progress: Optional[BackupProgress] = None,
                               record: Optional[BackupRecord] = None) -> BackupRecord:
        """Dump the PostgreSQL database to a compressed .sql.gz archive.

        When ``record`` is supplied the caller owns the durable BackupRecord
        (this is how the async route keeps exactly one record per operation);
        otherwise a new record is created here.
        """
        pg_dump = self._require_tool("pg_dump")
        if record is None:
            record = BackupRecord(
                backup_type=BackupType.DATABASE,
                backup_schedule=schedule,
                status=BackupStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
                created_by=triggered_by,
            )
            db.session.add(record)
            db.session.commit()

        # Initialize progress tracking
        if progress:
            progress.set_record(record.public_id)
            progress.start(6, "Initializing database backup...")
        
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"database_{schedule}_{ts}.sql"
            if self.compression_enabled:
                filename += ".gz"
            backup_path = os.path.join(self.backup_dir, filename)

            cfg = self._get_database_config()
            
            if progress:
                progress.step("Building pg_dump command...", 10)
            
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

            if progress:
                progress.step("Connecting to database...", 20)
                progress.substep("Establishing connection to PostgreSQL...")
            
            if self.compression_enabled:
                with open(backup_path, "wb") as out:
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        env=self._db_env(),
                    )
                    # pg_dump --verbose reports each object on stderr. The pipe
                    # must be drained while the dump runs, otherwise pg_dump
                    # blocks on a full stderr buffer and the backup never
                    # finishes. The drained lines double as live progress.
                    last_reported = [0.0]

                    def _report_dump_line(line: str) -> None:
                        if not progress or not line.startswith("dumping "):
                            return
                        now = time.monotonic()
                        if now - last_reported[0] < 0.5:
                            return
                        last_reported[0] = now
                        progress.substep(line)

                    stderr_lines, _reader = self._start_stream_reader(
                        proc.stderr, _report_dump_line
                    )
                    try:
                        if progress:
                            progress.step("Dumping database schema and data...", 30)
                            progress.substep("Running pg_dump with --clean --if-exists...")
                            
                        bytes_written = 0
                        last_progress_update = 0
                        last_substep_update = 0
                        last_cancel_check = 0
                        with gzip.open(out, "wb") as gz:
                            for chunk in iter(lambda: proc.stdout.read(65536), b""):
                                gz.write(chunk)
                                bytes_written += len(chunk)
                                if progress and bytes_written - last_cancel_check >= 1024 * 1024:
                                    last_cancel_check = bytes_written
                                    if progress.cancelled:
                                        raise BackupCancelledError(
                                            "Backup cancelled by operator"
                                        )
                                if progress:
                                    # Progress is reported on a byte threshold, not
                                    # per chunk. The dump stream arrives in 64 KiB
                                    # slices; emitting on every slice floods the
                                    # activity log and pins the reported percentage
                                    # to the pre-dump value.
                                    if bytes_written - last_progress_update >= 10 * 1024 * 1024:
                                        last_progress_update = bytes_written
                                        # Estimate progress: 30% + up to 50% for dump phase
                                        # Cap at 80% (leaving 20% for checksum/finalize)
                                        estimated_progress = min(80, 30 + int((bytes_written / (1024 * 1024)) * 2))
                                        progress.step(f"Dumping database... {bytes_written // (1024*1024)} MB written", estimated_progress)
                                    elif bytes_written - last_substep_update >= 1024 * 1024:
                                        last_substep_update = bytes_written
                                        progress.substep(f"Compressing data stream... {bytes_written // (1024*1024)} MB written")
                        try:
                            proc.wait(timeout=self.dump_timeout)
                        except subprocess.TimeoutExpired:
                            self._terminate_process(proc)
                            raise RuntimeError(
                                f"pg_dump timed out after {self.dump_timeout}s"
                            )
                        if proc.returncode != 0:
                            # stderr was already drained by the reader thread,
                            # so the collected lines are the only error detail
                            # available here.
                            err = "\n".join(stderr_lines[-20:])
                            raise RuntimeError(f"pg_dump failed: {err}")
                    except BackupCancelledError:
                        # Stop the child dump process before unwinding, then
                        # discard the partial artifact.
                        self._terminate_process(proc)
                        self._remove_partial_artifact(backup_path)
                        raise
            else:
                if progress:
                    progress.step("Dumping database (uncompressed)...", 30)
                with open(backup_path, "w") as out:
                    proc = subprocess.run(
                        cmd, stdout=out, stderr=subprocess.PIPE,
                        env=self._db_env(), timeout=self.dump_timeout,
                    )
                    if proc.returncode != 0:
                        err = proc.stderr.decode(errors="replace")
                        raise RuntimeError(f"pg_dump failed: {err}")

            if progress:
                progress.step("Calculating checksum...", 90)
            
            self._finalize_success(
                record, backup_path,
                metadata={"compression": self.compression_enabled, "tool": "pg_dump"},
            )
            self._cleanup_old_backups(BackupType.DATABASE, schedule)
            
            if progress:
                progress.complete(True, "Database backup completed successfully")
            current_app.logger.info(f"Database backup completed: {backup_path}")
            return record
        except Exception as exc:
            current_app.logger.error(f"Database backup failed: {exc}")
            if progress:
                progress.fail(str(exc))
            return self._finalize_failure(record, str(exc))

    def create_files_backup(self, schedule: str = BackupSchedule.WEEKLY,
                            triggered_by: Optional[int] = None,
                            progress: Optional[BackupProgress] = None,
                            record: Optional[BackupRecord] = None) -> BackupRecord:
        """Archive application directories (templates/static/uploads/logs) as tar.gz."""
        if record is None:
            record = BackupRecord(
                backup_type=BackupType.FILES,
                backup_schedule=schedule,
                status=BackupStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
                created_by=triggered_by,
            )
            db.session.add(record)
            db.session.commit()

        if progress:
            progress.set_record(record.public_id)
            progress.start(5, "Initializing files backup...")
        
        try:
            if progress:
                progress.step("Preparing file archive...", 10)
            
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"files_{schedule}_{ts}.tar.gz"
            backup_path = os.path.join(self.backup_dir, filename)

            app_root = current_app.root_path
            
            if progress:
                progress.step("Scanning directories...", 20)
            
            dirs = [d for d in FILE_BACKUP_DIRS if os.path.isdir(os.path.join(app_root, d))]
            if not dirs:
                raise RuntimeError("No backup directories found to archive.")
            
            if progress:
                progress.step(f"Archiving {len(dirs)} directories...", 40)
            
            raw_tar = backup_path.replace(".gz", "")
            cmd = ["tar", "-czf", backup_path, "-C", app_root] + dirs
            
            if progress:
                progress.substep("Running tar compression...")
            
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.dump_timeout)
            if proc.returncode != 0:
                raise RuntimeError(f"tar failed: {proc.stderr}")
            if os.path.exists(raw_tar):
                os.remove(raw_tar)

            if progress:
                progress.step("Finalizing archive...", 90)
            
            self._finalize_success(
                record, backup_path,
                metadata={"directories": dirs, "compression": True, "tool": "tar"},
            )
            self._cleanup_old_backups(BackupType.FILES, schedule)
            
            if progress:
                progress.complete(True, "Files backup completed successfully")
            current_app.logger.info(f"Files backup completed: {backup_path}")
            return record
        except Exception as exc:
            current_app.logger.error(f"Files backup failed: {exc}")
            if progress:
                progress.fail(str(exc))
            return self._finalize_failure(record, str(exc))

    def create_config_backup(self, schedule: str = BackupSchedule.MONTHLY,
                             triggered_by: Optional[int] = None,
                             progress: Optional[BackupProgress] = None,
                             record: Optional[BackupRecord] = None) -> BackupRecord:
        """Snapshot dynamic SystemConfig values to a JSON archive."""
        if record is None:
            record = BackupRecord(
                backup_type=BackupType.CONFIG,
                backup_schedule=schedule,
                status=BackupStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
                created_by=triggered_by,
            )
            db.session.add(record)
            db.session.commit()

        if progress:
            progress.set_record(record.public_id)
            progress.start(4, "Initializing config backup...")
        
        try:
            from app.models.system_config import SystemConfig
            
            if progress:
                progress.step("Fetching system configuration...", 20)
            
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"config_{schedule}_{ts}.json"
            if self.compression_enabled:
                filename += ".gz"
            backup_path = os.path.join(self.backup_dir, filename)
            
            if progress:
                progress.step("Querying system configuration...", 30)
            
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
            
            if progress:
                progress.step("Writing configuration file...", 60)
            
            if self.compression_enabled:
                with gzip.open(backup_path, "wt", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, default=str)
            else:
                with open(backup_path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, default=str)
            
            if progress:
                progress.step("Finalizing config backup...", 90)
            
            self._finalize_success(
                record, backup_path,
                metadata={"count": len(config_data), "compression": self.compression_enabled},
            )
            self._cleanup_old_backups(BackupType.CONFIG, schedule)
            
            if progress:
                progress.complete(True, "Config backup completed successfully")
            current_app.logger.info(f"Config backup completed: {backup_path}")
            return record
        except Exception as exc:
            current_app.logger.error(f"Config backup failed: {exc}")
            if progress:
                progress.fail(str(exc))
            return self._finalize_failure(record, str(exc))

    def create_full_backup(self, schedule: str = BackupSchedule.DAILY,
                           triggered_by: Optional[int] = None,
                           progress: Optional[BackupProgress] = None,
                           records: Optional[Dict[str, BackupRecord]] = None) -> Dict[str, BackupRecord]:
        """Convenience: run database + files + config backups together.

        ``records`` lets the caller pre-create the durable BackupRecord rows so
        an async run produces exactly one record per backup type.
        """
        # For full backup, we create a parent progress tracker
        if progress:
            progress.start(15, "Starting full backup (database + files + config)...")

        records = records or {}
        results = {}
        try:
            if progress:
                progress.step("Starting database backup...", 5)
            results[BackupType.DATABASE] = self.create_database_backup(
                schedule, triggered_by, progress, records.get(BackupType.DATABASE)
            )

            if progress:
                progress.step("Starting files backup...", 50)
            results[BackupType.FILES] = self.create_files_backup(
                schedule, triggered_by, progress, records.get(BackupType.FILES)
            )

            if progress:
                progress.step("Starting config backup...", 80)
            results[BackupType.CONFIG] = self.create_config_backup(
                schedule, triggered_by, progress, records.get(BackupType.CONFIG)
            )
            
            if progress:
                progress.complete(True, "Full backup completed successfully")
            return results
        except Exception as exc:
            current_app.logger.error(f"Full backup failed: {exc}")
            if progress:
                progress.fail(str(exc))
            # Try to finalize any completed backups
            for key, record in results.items():
                if record.status == BackupStatus.RUNNING:
                    self._finalize_failure(record, str(exc))
            raise

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
