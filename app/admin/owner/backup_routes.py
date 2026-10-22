"""
app/admin/owner/backup_routes.py

Owner-only Database Backup & Restore management UI/API.

All routes require the owner role. Restore is destructive and requires an
explicit typed confirmation. Backups are referenced by `public_id` (UUID), never
by the internal `id`.
"""

import logging
import os
import threading
from datetime import datetime, timezone
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, send_file, current_app, jsonify,
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
    create_progress_tracker,
    get_progress_tracker,
    find_progress_tracker_by_record,
    remove_progress_tracker,
)
from app.admin.owner.audit import audit_owner_action

logger = logging.getLogger(__name__)

owner_backup_bp = Blueprint("owner_backup", __name__)

# How long a finished progress tracker stays resident so the operator's next
# poll observes the terminal state before the registry entry is reclaimed.
PROGRESS_TRACKER_GRACE_SECONDS = 120


def _elapsed_seconds(record) -> int:
    """Elapsed seconds for a backup record.

    ``started_at``/``completed_at`` are plain ``DateTime`` columns, so
    PostgreSQL round-trips them as naive datetimes. Mixing a naive value with
    an aware ``datetime.now(timezone.utc)`` raises TypeError, so both ends are
    normalized to naive UTC before subtracting.
    """
    start = record.started_at or record.created_at
    if start is None:
        return 0
    end = record.completed_at or datetime.now(timezone.utc)
    if start.tzinfo is not None:
        start = start.astimezone(timezone.utc).replace(tzinfo=None)
    if end.tzinfo is not None:
        end = end.astimezone(timezone.utc).replace(tzinfo=None)
    return int(max(0, (end - start).total_seconds()))


def _expire_progress_tracker(backup_id: str, delay: int = PROGRESS_TRACKER_GRACE_SECONDS):
    """Remove a tracker after a grace period instead of immediately."""
    timer = threading.Timer(delay, remove_progress_tracker, args=(backup_id,))
    timer.daemon = True
    timer.start()


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
            return redirect(url_for("admin.owner.owner_backup.backups"))

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
    return redirect(url_for("admin.owner.owner_backup.backups"))


@owner_backup_bp.route("/backups/create-async", methods=["POST"])
@owner_login_required
@audit_owner_action("created_backup_async", "backup")
def create_backup_async():
    """Start a backup asynchronously and return a backup ID for progress tracking."""
    try:
        backup_type = request.form.get("backup_type", BackupType.DATABASE)
        if backup_type not in BackupType.ALL:
            return jsonify({"error": "Invalid backup type"}), 400

        # Resolve the acting user in the request context. The background thread
        # runs without a request context, so `current_user` is not usable there.
        user_id = current_user.id

        # Pre-create the durable BackupRecord(s) so an async run produces
        # exactly one record per backup type. The service methods attach to
        # these instead of creating a second, orphaned record.
        record_types = (
            [BackupType.DATABASE, BackupType.FILES, BackupType.CONFIG]
            if backup_type == BackupType.FULL
            else [backup_type]
        )
        records = {}
        for rtype in record_types:
            rec = BackupRecord(
                backup_type=rtype,
                backup_schedule=BackupSchedule.MANUAL,
                status=BackupStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
                created_by=user_id,
            )
            db.session.add(rec)
            records[rtype] = rec
        db.session.commit()

        # The tracker is keyed by the primary record's public_id so the
        # progress endpoint can resolve it directly.
        tracking_id = records[record_types[0]].public_id

        from app.extensions import socketio
        progress = create_progress_tracker(tracking_id, socketio)

        # `current_app` is a context-bound proxy. A worker thread has no
        # application context of its own, so resolving the proxy there raises
        # "Working outside of application context". Bind the real app object
        # while the request context is still alive.
        app_obj = current_app._get_current_object()  # type: ignore[attr-defined]

        def run_backup():
            try:
                with app_obj.app_context():
                    try:
                        svc = BackupService()
                        svc.compression_enabled = True
                        if backup_type == BackupType.FULL:
                            svc.create_full_backup(
                                BackupSchedule.MANUAL, user_id, progress, records
                            )
                        elif backup_type == BackupType.FILES:
                            svc.create_files_backup(
                                BackupSchedule.MANUAL, user_id, progress,
                                records.get(BackupType.FILES),
                            )
                        elif backup_type == BackupType.CONFIG:
                            svc.create_config_backup(
                                BackupSchedule.MANUAL, user_id, progress,
                                records.get(BackupType.CONFIG),
                            )
                        else:
                            svc.create_database_backup(
                                BackupSchedule.MANUAL, user_id, progress,
                                records.get(BackupType.DATABASE),
                            )
                    except Exception as exc:
                        logger.error(f"Async backup failed: {exc}", exc_info=True)
                        progress.fail(str(exc))
                        try:
                            for rec in records.values():
                                if rec.status == BackupStatus.RUNNING:
                                    rec.status = BackupStatus.FAILED
                                    rec.error_message = str(exc)[:4000]
                                    rec.completed_at = datetime.now(timezone.utc)
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
            except Exception as exc:
                # Covers failures that happen before/around the app context
                # push (for example a context that cannot be established).
                # Without this the thread would die silently and the operator
                # would watch a frozen progress bar until the tracker expired.
                logger.error(f"Async backup worker crashed: {exc}", exc_info=True)
                progress.fail(str(exc))
            finally:
                # Keep the finished tracker available for a short grace
                # period so the operator's next poll observes the terminal
                # state instead of falling back to the database.
                _expire_progress_tracker(tracking_id)

        thread = threading.Thread(target=run_backup, daemon=True, name="backup-async")
        thread.start()

        return jsonify({
            "backup_id": tracking_id,
            "status": "started",
            "message": "Backup started. Use the progress endpoint to track.",
        }), 202

    except Exception as exc:
        logger.error(f"Async backup failed to start: {exc}", exc_info=True)
        return jsonify({"error": str(exc)}), 500


@owner_backup_bp.route("/backups/progress/<backup_id>")
@owner_login_required
def backup_progress(backup_id):
    """Get current progress of a backup operation."""
    tracker = get_progress_tracker(backup_id)
    if not tracker:
        tracker = find_progress_tracker_by_record(backup_id)

    if not tracker:
        # No live tracker — fall back to the durable record state.
        record = BackupRecord.query.filter_by(public_id=backup_id, is_deleted=False).first()
        if not record:
            return jsonify({"error": "Backup not found"}), 404
        finished = record.status != BackupStatus.RUNNING
        return jsonify({
            "backup_id": backup_id,
            "record_public_id": record.public_id,
            "progress": 100 if record.status == BackupStatus.COMPLETED else (0 if finished else 0),
            "step": record.status,
            "substep": record.error_message or "",
            "details": [],
            "elapsed": _elapsed_seconds(record),
            "finished": finished,
            "error": record.error_message,
            "cancelled": False,
            "status": record.status,
        })

    return jsonify(tracker.get_state())


@owner_backup_bp.route("/backups/progress/<backup_id>/cancel", methods=["POST"])
@owner_login_required
@audit_owner_action("cancelled_backup", "backup")
def cancel_backup(backup_id):
    """Request cooperative cancellation of a running backup."""
    tracker = get_progress_tracker(backup_id) or find_progress_tracker_by_record(backup_id)
    if not tracker:
        return jsonify({"error": "No running backup for that id"}), 404
    if tracker.finished:
        return jsonify({"error": "Backup already finished", "finished": True}), 409
    tracker.request_cancel()
    return jsonify({"backup_id": backup_id, "cancelling": True}), 202



@owner_backup_bp.route("/backups/<public_id>/download")
@owner_login_required
@audit_owner_action("downloaded_backup", "backup")
def download_backup(public_id):
    """Download a backup artifact."""
    record = BackupService.get_backup(public_id)
    if not record or not record.file_path or not _file_exists(record.file_path):
        flash("Backup file not found.", "danger")
        return redirect(url_for("admin.owner.owner_backup.backups"))
    try:
        return send_file(
            record.file_path,
            as_attachment=True,
            download_name=record.file_name or f"{record.public_id}.bin",
        )
    except Exception as exc:
        logger.error(f"Backup download failed: {exc}", exc_info=True)
        flash("Failed to download backup file.", "danger")
        return redirect(url_for("admin.owner.owner_backup.backups"))


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
        return redirect(url_for("admin.owner.owner_backup.backups"))

    confirmation = (request.form.get("confirm_text") or "").strip().upper()
    if confirmation != "RESTORE DATABASE":
        flash("Restore cancelled: confirmation phrase did not match.", "warning")
        return redirect(url_for("admin.owner.owner_backup.backups"))

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
    return redirect(url_for("admin.owner.owner_backup.backups"))


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
    return redirect(url_for("admin.owner.owner_backup.backups"))


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
    return redirect(url_for("admin.owner.owner_backup.backups"))


def _file_exists(path: str) -> bool:
    try:
        return bool(path) and os.path.exists(path)
    except Exception:
        return False
