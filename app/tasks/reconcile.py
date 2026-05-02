"""Simple reconciliation job that scans ledger entries and finds imbalances.

Run with:
    python -m app.tasks.reconcile

It records a ReconciliationRun and any issues in ReconciliationIssue table.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from app.extensions import db
from app.wallet.models.reconciliation import ReconciliationRun, ReconciliationIssue
from app.wallet.models.ledger import LedgerEntryModel
from flask import current_app


def run_reconciliation(days=1):
    session = db.session
    run = ReconciliationRun()
    session.add(run)
    session.commit()

    since = datetime.utcnow() - timedelta(days=days)

    # Aggregate debits and credits per currency
    # Simple approach: use SQLAlchemy queries to sum
    try:
        results = session.query(
            LedgerEntryModel.currency,
            LedgerEntryModel.entry_type,
        ).filter(LedgerEntryModel.created_at >= since).all()

        # Fallback conservative approach: compute totals in python for safety
        totals = {}
        entries = session.query(LedgerEntryModel).filter(LedgerEntryModel.created_at >= since).all()
        for e in entries:
            c = e.currency or 'UNKNOWN'
            totals.setdefault(c, Decimal('0'))
            if e.entry_type.name == 'CREDIT':
                totals[c] += Decimal(e.amount)
            else:
                totals[c] -= Decimal(e.amount)

        issues = []
        for cur, net in totals.items():
            if net != Decimal('0'):
                # record an issue
                issue = ReconciliationIssue(
                    run_id=run.id,
                    issue_type='net_mismatch',
                    details={'currency': cur, 'net': str(net)}
                )
                session.add(issue)
                issues.append({'currency': cur, 'net': str(net)})

        summary = {
            'checked_since': since.isoformat(),
            'currencies_checked': list(totals.keys()),
            'issues_found': len(issues)
        }

        run.mark_completed(summary=summary, session=session)
        session.commit()
        current_app.logger.info(f"Reconciliation run {run.id} completed: {summary}")
        return run.id, summary

    except Exception as e:
        session.rollback()
        run.status = 'failed'
        run.notes = str(e)
        session.add(run)
        session.commit()
        current_app.logger.error(f"Reconciliation run failed: {e}")
        raise


if __name__ == '__main__':
    print('Starting reconciliation...')
    run_reconciliation(days=1)

