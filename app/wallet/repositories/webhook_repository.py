"""
Webhook Repository for managing webhook events
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import desc, and_, or_
from app.extensions import db
from app.wallet.models.webhook_event import WebhookEvent


class WebhookRepository:
    """Repository for WebhookEvent data access"""

    @staticmethod
    def get_by_id(event_id: int) -> Optional[WebhookEvent]:
        return db.session.get(WebhookEvent, event_id)

    @staticmethod
    def get_paginated(
        page: int = 1,
        per_page: int = 20,
        status: Optional[str] = None,
        provider: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        query = WebhookEvent.query

        if status:
            query = query.filter_by(status=status)
        if provider:
            query = query.filter_by(provider=provider)
        if search:
            query = query.filter(
                or_(
                    WebhookEvent.event_type.ilike(f'%{search}%'),
                    WebhookEvent.provider.ilike(f'%{search}%'),
                    WebhookEvent.last_error.ilike(f'%{search}%')
                )
            )

        paginated = query.order_by(
            desc(WebhookEvent.created_at)
        ).paginate(page=page, per_page=per_page, error_out=False)

        return {
            'items': paginated.items,
            'total': paginated.total,
            'page': paginated.page,
            'per_page': paginated.per_page,
            'pages': paginated.pages,
            'has_prev': paginated.has_prev,
            'has_next': paginated.has_next
        }

    @staticmethod
    def get_stats() -> Dict[str, Any]:
        from sqlalchemy import func

        total = WebhookEvent.query.count()
        queued = WebhookEvent.query.filter_by(status='queued').count()
        processed = WebhookEvent.query.filter_by(status='processed').count()
        failed = WebhookEvent.query.filter_by(status='failed').count()

        provider_stats = db.session.query(
            WebhookEvent.provider,
            func.count(WebhookEvent.id).label('count'),
            func.count(WebhookEvent.id).filter(WebhookEvent.status == 'failed').label('failed_count')
        ).group_by(WebhookEvent.provider).all()

        last_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_count = WebhookEvent.query.filter(
            WebhookEvent.created_at >= last_24h
        ).count()

        return {
            'total': total,
            'queued': queued,
            'processed': processed,
            'failed': failed,
            'success_rate': round((processed / total * 100) if total > 0 else 0, 1),
            'recent_24h': recent_count,
            'providers': [
                {
                    'name': p[0],
                    'total': p[1],
                    'failed': p[2],
                    'success_rate': round(((p[1] - p[2]) / p[1] * 100) if p[1] > 0 else 0, 1)
                }
                for p in provider_stats
            ]
        }

    @staticmethod
    def retry_webhook(event_id: int) -> bool:
        event = db.session.get(WebhookEvent, event_id)
        if event and event.status == 'failed':
            event.status = 'queued'
            event.next_retry_at = datetime.now(timezone.utc)
            db.session.commit()
            return True
        return False

    @staticmethod
    def delete_webhook(event_id: int) -> bool:
        event = db.session.get(WebhookEvent, event_id)
        if event:
            db.session.delete(event)
            db.session.commit()
            return True
        return False

    @staticmethod
    def bulk_delete(ids: List[int]) -> int:
        deleted = WebhookEvent.query.filter(WebhookEvent.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        return deleted

