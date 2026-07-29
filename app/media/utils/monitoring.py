import logging
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)


def report_processing_metrics(media_id: int, status: str, duration: float, 
                             attempts: int, error: str = None):
    """
    Report processing metrics to monitoring system.
    Integrates with Datadog, Prometheus, or custom metrics.
    """
    # Example: Log structured data
    logger.info(
        f"Media processing metric: {media_id}",
        extra={
            'media_id': media_id,
            'status': status,
            'duration': duration,
            'attempts': attempts,
            'error': error,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    )
    
    # Integrate with monitoring systems
    # if current_app.config.get('DATADOG_ENABLED'):
    #     from datadog import statsd
    #     statsd.histogram('media.processing.duration', duration)
    #     statsd.increment('media.processing.status', tags=[f'status:{status}'])


def alert_on_failure(media_id: str, error: str, attempts: int):
    """
    Send alert when media processing fails permanently.
    """
    # Example: Send to Slack, Email, or PagerDuty
    logger.error(
        f"🚨 MEDIA PROCESSING FAILED: {media_id}",
        extra={
            'media_id': media_id,
            'error': error,
            'attempts': attempts,
            'severity': 'high'
        }
    )
    
    # Slack notification example
    # slack_webhook = current_app.config.get('SLACK_WEBHOOK_URL')
    # if slack_webhook:
    #     import requests
    #     requests.post(slack_webhook, json={
    #         'text': f"🚨 Media {media_id} processing failed after {attempts} attempts: {error}"
    #     })
