"""
app/admin/owner/backup_routes.py

Owner-only Database Backup & Restore management UI/API.

All routes require the owner role. Restore is destructive and requires an
explicit typed confirmation. Backups are referenced by `public_id` (UUID), never
by the internal `id`.
"""

import logging
import os
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, send_file, current_app,
)
from flask_login import login_required, current_user

from app.admin.owner.decorators import owner_required
from app.extensions import db
from app.models.system_config import SystemConfig
from app.backup.backup_service import (
    BackupService,
    BackupRecord,
    BackupType,
    BackupSchedule,
    BackupStatus,
)
from app.admin.owner.audit import audit_owner_action

logger = logging.getLogger(__name__)

owner_backup_bp = Blueprint("owner_backup", __name__)


def owner_login_required(f):
    return login_required(owner_required(f))


@owner_backup_bp.route("/backups")
@owner_login_required
@audit_owner_action("viewed_backups", "backup")
def backups():
    """List backups, show create form, scheduler config, and health status."""
    try:
        svc = BackupService()
        records = BackupService.list_backups(limit=100)
        status = svc.get_backup_status()

        config = {
            "BACKUP_ENABLED": SystemConfig.get("BACKUP_ENABLED", True),
            "BACKUP_FREQUENCY": SystemConfig.get("BACKUP_FREQUENCY", "daily"),
            "BACKUP_INCLUDE_FILES": SystemConfig.get("BACKUP_INCLUDE_FILES", False),
            "BACKUP_INCLUDE_CONFIG": SystemConfig.get("BACKUP_INCLUDE_CONFIG", True),
        }
        pg_dump_ok = BackupService._which("pg_dump") is not None
        psql_ok = BackupService._which("psql") is not None

        return render_template(
            "owner/backups.html",
            backups=records,
            status=status,
            config=config,
            tools_available=pg_dump_ok and psql_ok,
            backup_types=[BackupType.DATABASE, BackupType.FILES, BackupType.CONFIG, BackupType.FULL],
            frequencies=list(BackupSchedule.ALL),
        )
    except Exception as exc:
        logger.error(f"Failed to load backups page: {exc}", exc_info=True)
        flash("Error loading backups page.", "danger")
        return redirect(url_for("admin.owner.dashboard"))


@owner_backup_bp.route("/backups/create", methods=["POST"])
@owner_login_required
@audit_owner_action("created_backup", "backup")
def create_backup():
    """Trigger a manual backup of the selected type."""
    try:
        backup_type = request.form.get("backup_type", BackupType.DATABASE)
        if backup_type not in BackupType.ALL:
            flash("Invalid backup type.", "danger")
            return redirect(url_for("admin.owner.backups"))

        svc = BackupService()
        svc.compression_enabled = True

        if backup_type == BackupType.FULL:
            results = svc.create_full_backup(BackupSchedule.MANUAL, current_user.id)
            ok = all(r.status == BackupStatus.COMPLETED for r in results.values())
        elif backup_type == BackupType.FILES:
            rec = svc.create_files_backup(BackupSchedule.MANUAL, current_user.id)
            ok = rec.status == BackupStatus.COMPLETED
        elif backup_type == BackupType.CONFIG:
            rec = svc.create_config_backup(BackupSchedule.MANUAL, current_user.id)
            ok = rec.status == BackupStatus.COMPLETED
        else:
            rec = svc.create_database_backup(BackupSchedule.MANUAL, current_user.id)
            ok = rec.status == BackupStatus.COMPLETED

        if ok:
            flash("Backup completed successfully.", "success")
        else:
            flash("Backup failed. Check the backup status/logs for details.", "danger")
    except Exception as exc:
        logger.error(f"Manual backup failed: {exc}", exc_info=True)
        flash(f"Backup failed: {exc}", "danger")
    return redirect(url_for("admin.owner.backups"))


@owner_backup_bp.route("/backups/<public_id>/download")
@owner_login_required
@audit_owner_action("downloaded_backup", "backup")
def download_backup(public_id):
    """Download a backup artifact."""
    record = BackupService.get_backup(public_id)
    if not record or not record.file_path or not _file_exists(record.file_path):
        flash("Backup file not found.", "danger")
        return redirect(url_for("admin.owner.backups"))
    try:
        return send_file(
            record.file_path,
            as_attachment=True,
            download_name=record.file_name or f"{record.public_id}.bin",
        )
    except Exception as exc:
        logger.error(f"Backup download failed: {exc}", exc_info=True)
        flash("Failed to download backup file.", "danger")
        return redirect(url_for("admin.owner.backups"))


@owner_backup_bp.route("/backups/<public_id>/restore", methods=["POST"])
@owner_login_required
@audit_owner_action("restored_backup", "backup")
def restore_backup(public_id):
    """
    Restore the database from a backup.

    DESTRUCTIVE: requires the owner to type the confirmation phrase and confirm
    awareness. Runs pg_dump-style --clean replay inside a single transaction.
    """
    record = BackupService.get_backup(public_id)
    if not record or record.backup_type != BackupType.DATABASE:
        flash("Database backup not found.", "danger")
        return redirect(url_for("admin.owner.backups"))

    confirmation = (request.form.get("confirm_text") or "").strip().upper()
    if confirmation != "RESTORE DATABASE":
        flash("Restore cancelled: confirmation phrase did not match.", "warning")
        return redirect(url_for("admin.owner.backups"))

    try:
        svc = BackupService()
        success = svc.restore_database(public_id, verify_checksum=True)
        if success:
            flash(
                "Database restored successfully from backup. Verify system health.",
                "success",
            )
        else:
            flash("Restore reported failure. Check logs.", "danger")
    except Exception as exc:
        logger.error(f"Restore failed: {exc}", exc_info=True)
        flash(f"Restore failed: {exc}", "danger")
    return redirect(url_for("admin.owner.backups"))


@owner_backup_bp.route("/backups/<public_id>/delete", methods=["POST"])
@owner_login_required
@audit_owner_action("deleted_backup", "backup")
def delete_backup(public_id):
    """Delete a backup record and its artifact."""
    try:
        svc = BackupService()
        if svc.delete_backup(public_id):
            flash("Backup deleted.", "success")
        else:
            flash("Backup not found.", "warning")
    except Exception as exc:
        logger.error(f"Delete backup failed: {exc}", exc_info=True)
        flash("Failed to delete backup.", "danger")
    return redirect(url_for("admin.owner.backups"))


@owner_backup_bp.route("/backups/settings", methods=["POST"])
@owner_login_required
@audit_owner_action("updated_backup_settings", "backup")
def backup_settings():
    """Update scheduled-backup configuration (runtime, no restart required)."""
    try:
        enabled = request.form.get("backup_enabled") == "on"
        frequency = request.form.get("backup_frequency", "daily")
        if frequency not in BackupSchedule.ALL:
            frequency = "daily"
        include_files = request.form.get("backup_include_files") == "on"
        include_config = request.form.get("backup_include_config") == "on"

        SystemConfig.set("BACKUP_ENABLED", enabled, value_type="bool", category="backup")
        SystemConfig.set("BACKUP_FREQUENCY", frequency, value_type="str", category="backup")
        SystemConfig.set("BACKUP_INCLUDE_FILES", include_files, value_type="bool", category="backup")
        SystemConfig.set("BACKUP_INCLUDE_CONFIG", include_config, value_type="bool", category="backup")
        db.session.commit()

        flash("Backup schedule settings updated.", "success")
    except Exception as exc:
        logger.error(f"Update backup settings failed: {exc}", exc_info=True)
        db.session.rollback()
        flash("Failed to update backup settings.", "danger")
    return redirect(url_for("admin.owner.backups"))


def _file_exists(path: str) -> bool:
    try:
        return bool(path) and os.path.exists(path)
    except Exception:
        return False
