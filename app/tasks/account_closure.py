# app/tasks/account_closure.py
"""
Celery task to finalize account closures whose grace period has expired.
"""

from __future__ import annotations

import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="account.finalize_due_closures",
    bind=True,
)
def finalize_due_account_closures_task(
    self,
    limit: int = 50,
) -> dict:
    """Finalize a bounded page of expired closure requests."""
    from app import create_app

    limit = max(1, min(int(limit), 250))
    app = create_app()

    with app.app_context():
        from app.auth.account_deletion_service import finalize_due_account_closures

        return finalize_due_account_closures(limit=limit)