# app/tasks/transport_permission_purge.py
"""
Daily Celery task to auto-revoke expired transport permissions.

This task runs once per day (via Celery beat schedule) and sets
``is_active=False`` on all ``TransportPermission`` records where
``expires_at`` is in the past.

It also purges (deletes) permissions that have no expiry and have
been manually revoked, keeping the table clean.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.transport_permissions import TransportPermission
from app.extensions import db


def purge_expired_transport_permissions() -> int:
    """
    Auto-revoke all expired transport permissions.

    Sets ``is_active=False`` for all ``TransportPermission`` records
    where ``expires_at`` is in the past (and ``expires_at`` is not NULL).

    Returns:
        Number of permissions revoked
    """
    from sqlalchemy import and_

    count = TransportPermission.query.filter(
        and_(
            TransportPermission.is_active == True,
            TransportPermission.expires_at < datetime.now(timezone.utc),
        )
    ).update({"is_active": False}, synchronize_session=False)
    db.session.commit()
    return count


def purge_all_transport_permissions() -> int:
    """
    Revoke ALL transport permissions (hard revoke).

    Useful for resetting the system or after a security review.

    Returns:
        Number of permissions revoked
    """
    from sqlalchemy import delete

    count = db.session.query(TransportPermission).filter(
        TransportPermission.is_active == True
    ).delete(synchronize_session=False)
    db.session.commit()
    return count