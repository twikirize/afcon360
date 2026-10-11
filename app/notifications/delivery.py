"""
AFCON360 Notification Delivery Functions

Plain, context-free delivery functions for notification fan-outs that must not
run on the request thread. Each function re-fetches its domain record by the
internal id — an ORM instance bound to the originating request's session must
never be handed to another thread — and then delegates to NotificationService.

Consumed by:
  * app/notifications/dispatch.py  (background-thread fallback)
  * app/notifications/tasks.py     (Celery tasks)
"""

import logging

logger = logging.getLogger(__name__)


def deliver_kyc_submitted(user_id, kyc_record_id):
    """Notify the submitter and the review team that a KYC submission arrived."""
    from app.extensions import db
    from app.kyc.models import KycRecord
    from app.notifications.services import NotificationService

    record = db.session.get(KycRecord, kyc_record_id) if kyc_record_id else None
    NotificationService.notify_kyc_submitted(user_id=user_id, kyc_record=record)


def deliver_kyc_approved(user_id, kyc_record_id):
    """Notify the submitter and the review team that a KYC submission passed."""
    from app.extensions import db
    from app.kyc.models import KycRecord
    from app.notifications.services import NotificationService

    record = db.session.get(KycRecord, kyc_record_id) if kyc_record_id else None
    NotificationService.notify_kyc_approved(user_id=user_id, kyc_record=record)
