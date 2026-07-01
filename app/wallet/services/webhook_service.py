"""
Webhook Service for managing webhook events
"""

from typing import List, Optional, Dict, Any
from app.wallet.repositories.webhook_repository import WebhookRepository


class WebhookService:
    """Service layer for webhook management"""

    def __init__(self):
        self.repository = WebhookRepository()

    def get_paginated_webhooks(
        self,
        page: int = 1,
        per_page: int = 20,
        status: Optional[str] = None,
        provider: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        return self.repository.get_paginated(page, per_page, status, provider, search)

    def get_stats(self) -> Dict[str, Any]:
        return self.repository.get_stats()

    def get_webhook_detail(self, event_id: int) -> Optional[Dict[str, Any]]:
        event = self.repository.get_by_id(event_id)
        if not event:
            return None

        return {
            'id': event.id,
            'provider': event.provider,
            'event_type': event.event_type,
            'payload': event.payload,
            'raw_body': event.raw_body,
            'signature': event.signature,
            'status': event.status,
            'retry_count': event.retry_count,
            'last_error': event.last_error,
            'next_retry_at': event.next_retry_at,
            'processed_at': event.processed_at,
            'created_at': event.created_at,
            'updated_at': event.updated_at
        }

    def retry_webhook(self, event_id: int) -> Dict[str, Any]:
        event = self.repository.get_by_id(event_id)
        if not event:
            return {'success': False, 'error': 'Webhook not found'}
        if event.status != 'failed':
            return {'success': False, 'error': f'Cannot retry webhook with status: {event.status}'}
        if self.repository.retry_webhook(event_id):
            return {'success': True, 'message': f'Webhook {event_id} requeued for processing'}
        return {'success': False, 'error': 'Failed to retry webhook'}

    def delete_webhook(self, event_id: int) -> Dict[str, Any]:
        event = self.repository.get_by_id(event_id)
        if not event:
            return {'success': False, 'error': 'Webhook not found'}
        if self.repository.delete_webhook(event_id):
            return {'success': True, 'message': f'Webhook {event_id} deleted'}
        return {'success': False, 'error': 'Failed to delete webhook'}

    def bulk_delete_webhooks(self, ids: List[int]) -> Dict[str, Any]:
        if not ids:
            return {'success': False, 'error': 'No webhooks selected'}
        deleted = self.repository.bulk_delete(ids)
        return {'success': True, 'message': f'{deleted} webhooks deleted'}
