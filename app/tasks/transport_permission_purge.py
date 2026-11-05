# app/tasks/transport_permission_purge.py
"""
Celery task to auto-revoke expired transport permissions.

The scheduled task processes a bounded page and requeues a continuation so
large permission tables do not monopolise the single constrained worker.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.core.transport_permissions import TransportPermission
from app.extensions import db

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.transport_permission_purge.purge_expired_transport_permissions",
    bind=True,
)
def purge_expired_transport_permissions(
    self,
    batch_size: int = 100,
    after_permission_id: int = 0,
) -> dict:
    """Revoke one ordered page of expired transport permissions."""
    from app import create_app

    batch_size = max(1, min(int(batch_size), 250))
    after_permission_id = max(0, int(after_permission_id))
    app = create_app()

    with app.app_context():
        now = datetime.now(timezone.utc)
        permission_ids = [
            row[0]
            for row in (
                db.session.query(TransportPermission.id)
                .filter(
                    TransportPermission.is_active.is_(True),
                    TransportPermission.expires_at.is_not(None),
                    TransportPermission.expires_at < now,
                    TransportPermission.id > after_permission_id,
                )
                .order_by(TransportPermission.id.asc())
                .limit(batch_size)
                .all()
            )
        ]

        revoked = 0
        if permission_ids:
            revoked = (
                TransportPermission.query.filter(
                    TransportPermission.id.in_(permission_ids),
                    TransportPermission.is_active.is_(True),
                    TransportPermission.expires_at < now,
                )
                .update({"is_active": False}, synchronize_session=False)
                or 0
            )
            db.session.commit()

        continuation_queued = False
        if len(permission_ids) >= batch_size:
            try:
                self.apply_async(
                    kwargs={
                        "batch_size": batch_size,
                        "after_permission_id": permission_ids[-1],
                    },
                    countdown=5,
                )
                continuation_queued = True
            except Exception:
                logger.exception(
                    "Could not schedule the next expired-permission page"
                )

        return {
            "revoked": revoked,
            "examined": len(permission_ids),
            "batch_size": batch_size,
            "continuation_queued": continuation_queued,
        }


def purge_all_transport_permissions() -> int:
    """
    Revoke ALL active transport permissions (hard revoke).

    This is a manual security operation, not part of the scheduled purge.
    """
    count = db.session.query(TransportPermission).filter(
        TransportPermission.is_active.is_(True)
    ).delete(synchronize_session=False)
    db.session.commit()
    return count
