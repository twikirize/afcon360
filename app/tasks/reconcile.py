"""Simple reconciliation job that scans ledger entries and finds imbalances.

Run with:
    python -m app.tasks.reconcile

It records a ReconciliationRun and any issues in ReconciliationIssue table.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from celery import shared_task
from app.extensions import db
from app.wallet.models.reconciliation import ReconciliationRun, ReconciliationIssue
from app.wallet.models.ledger import LedgerEntryModel
from app.wallet.services.reconciliation_service import ReconciliationService
from flask import current_app


@shared_task(bind=True)
def daily_wallet_reconciliation(self):
    """Celery task for daily wallet reconciliation."""
    from app import create_app
    app = create_app()
    with app.app_context():
        service = ReconciliationService()
        return service.run_daily_reconciliation()


def run_reconciliation(days=1):
    """
    Legacy reconciliation function - now calls ReconciliationService
    for a more thorough check.
    """
    session = db.session
    service = ReconciliationService(session=session)
    return service.run_daily_reconciliation()


if __name__ == '__main__':
    print('Starting reconciliation...')
    run_reconciliation(days=1)

