"""
app/tasks/backup_tasks.py

Celery tasks for scheduled database/file/config backups.

These run under the Celery beat scheduler (see celery_app.beat_schedule). The
actual pg_dump / psql work lives in app.backup.backup_service.BackupService.

Behavior is driven by SystemConfig so the owner can toggle backups at runtime:
- BACKUP_ENABLED        (bool, default True)
- BACKUP_FREQUENCY      ('hourly'|'daily'|'weekly'|'monthly', default 'daily')
- BACKUP_INCLUDE_FILES  (bool, default False)
- BACKUP_INCLUDE_CONFIG (bool, default True)
"""

import logging
from datetime import datetime, timezone, timedelta

from app.celery_app import celery_app
from app.backup.backup_service import (
    BackupService,
    BackupRecord,
    BackupType,
    BackupStatus,
)

logger = logging.getLogger(__name__)

_FREQUENCY_INTERVALS = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


@celery_app.task(name="backup.scheduled_run")
def scheduled_backup_run() -> dict:
    """
    Beat task: create backups only when due, per the configured frequency.
    Returns a small status dict (never raises) so beat stays healthy.
    """
    from app import create_app

    app = create_app()
    with app.app_context():
        return _run_scheduled_backup()


def _run_scheduled_backup() -> dict:
    from app.models.system_config import SystemConfig

    try:
        enabled = SystemConfig.get("BACKUP_ENABLED", True)
        if not enabled:
            return {"skipped": "disabled"}

        frequency = SystemConfig.get("BACKUP_FREQUENCY", "daily")
        include_files = SystemConfig.get("BACKUP_INCLUDE_FILES", False)
        include_config = SystemConfig.get("BACKUP_INCLUDE_CONFIG", True)

        interval = _FREQUENCY_INTERVALS.get(frequency, timedelta(days=1))
        now = datetime.now(timezone.utc)

        last = (
            BackupRecord.query.filter_by(
                backup_type=BackupType.DATABASE,
                status=BackupStatus.COMPLETED,
                is_deleted=False,
            )
            .order_by(BackupRecord.completed_at.desc())
            .first()
        )
        if last and last.completed_at and (now - last.completed_at) < interval:
            return {
                "skipped": "not_due",
                "frequency": frequency,
                "last_completed_at": last.completed_at.isoformat(),
            }

        svc = BackupService()
        svc.create_database_backup(schedule=frequency)
        if include_files:
            svc.create_files_backup(schedule=frequency)
        if include_config:
            svc.create_config_backup(schedule=frequency)

        logger.info(f"Scheduled backup run completed (frequency={frequency})")
        return {"ok": True, "frequency": frequency}
    except Exception as exc:
        logger.error(f"Scheduled backup run failed: {exc}", exc_info=True)
        return {"ok": False, "error": str(exc)}


@celery_app.task(name="backup.create_now")
def create_backup_task(backup_type: str = BackupType.DATABASE,
                       schedule: str = "manual",
                       triggered_by: int = None) -> dict:
    """On-demand backup task (usable from routes or CLI)."""
    from app import create_app

    app = create_app()
    with app.app_context():
        try:
            svc = BackupService()
            if backup_type == BackupType.FILES:
                rec = svc.create_files_backup(schedule, triggered_by)
            elif backup_type == BackupType.CONFIG:
                rec = svc.create_config_backup(schedule, triggered_by)
            else:
                rec = svc.create_database_backup(schedule, triggered_by)
            return {"ok": rec.status == BackupStatus.COMPLETED, "public_id": rec.public_id,
                    "status": rec.status}
        except Exception as exc:
            logger.error(f"On-demand backup failed: {exc}", exc_info=True)
            return {"ok": False, "error": str(exc)}
