"""
app/wallet/api/admin_webhook_routes.py

Admin endpoints for WebhookEvent dead-letter queue management.
Add this to your existing admin_api_bp or register as a separate blueprint.

Endpoints:
    GET  /api/admin/wallet/webhooks/failed     - List dead_letter events
    POST /api/admin/wallet/webhooks/{id}/retry - Requeue a dead_letter event
    GET  /api/admin/wallet/webhooks/stats      - Queue health stats
"""

from flask import jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.wallet.models.webhook_event import WebhookEvent
from app.wallet.models.transaction import TransactionModel, TransactionStatus

# Import the existing blueprint from admin_api.py
from app.wallet.api.admin_api import admin_api_bp, require_any_role


@admin_api_bp.route("/webhooks/failed", methods=["GET"])
@login_required
@require_any_role("admin", "super_admin", "owner")
def list_failed_webhooks():
    """
    List dead_letter and failed webhook events for manual review.
    """
    status = request.args.get("status", "dead_letter")
    provider = request.args.get("provider")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = WebhookEvent.query.filter(WebhookEvent.status == status)
    if provider:
        query = query.filter(WebhookEvent.provider == provider)

    pagination = query.order_by(
        WebhookEvent.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "events": [
            {
                "id": str(e.id),
                "provider": e.provider,
                "event_type": e.event_type,
                "status": e.status,
                "retry_count": e.retry_count,
                "last_error": e.last_error,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "next_retry_at": e.next_retry_at.isoformat() if e.next_retry_at else None,
                "processed_at": e.processed_at.isoformat() if e.processed_at else None,
                # Show safe subset of payload - never log full card data
                "payload_preview": {
                    k: v for k, v in (e.payload or {}).items()
                    if k in ("event", "event_type", "status", "txRef",
                             "tx_ref", "reference", "amount", "currency")
                }
            }
            for e in pagination.items
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages
        }
    })


@admin_api_bp.route("/webhooks/<int:event_id>/retry", methods=["POST"])
@login_required
@require_any_role("admin", "super_admin", "owner")
def retry_webhook(event_id):
    """
    Manually requeue a dead_letter or failed webhook event.
    Resets status to 'queued' and clears retry counter.

    Only works on dead_letter or failed events.
    Will NOT requeue already processed events (safety guard).
    """
    event = WebhookEvent.query.get(event_id)
    if not event:
        return jsonify({"error": "Webhook event not found"}), 404

    # Safety: never re-process completed events
    if event.status in ("processed", "processing"):
        return jsonify({
            "error": f"Cannot retry event with status '{event.status}'. "
                     f"Only dead_letter and failed events can be retried."
        }), 400

    # Additional safety: ensure we won't double-credit by reprocessing an
    # event whose provider reference already maps to a COMPLETED transaction.
    # Extract provider reference from common payload shapes.
    payload = event.payload or {}
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    provider_ref = (
        data.get("txRef") or data.get("tx_ref") or data.get("reference")
        or payload.get("reference") or payload.get("txRef")
    )

    if provider_ref:
        existing_tx = TransactionModel.query.filter_by(
            client_request_id=provider_ref
        ).first()
        if existing_tx and existing_tx.status == TransactionStatus.COMPLETED:
            return jsonify({
                "error": (
                    f"A completed transaction already exists for this webhook reference: {existing_tx.id}. "
                    "Reprocessing would double-credit the user."
                )
            }), 400

    event.status = "queued"
    event.retry_count = 0
    event.next_retry_at = None
    event.last_error = f"Manual retry by admin {current_user.id} at {datetime.now(timezone.utc).isoformat()}"

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "success": True,
        "message": f"Event {event_id} requeued. Will be processed within 60 seconds.",
        "event_id": event_id
    })


@admin_api_bp.route("/webhooks/stats", methods=["GET"])
@login_required
@require_any_role("admin", "super_admin", "owner")
def webhook_stats():
    """
    Webhook queue health dashboard data.
    Shows counts by status and provider.
    """
    from sqlalchemy import func

    # Count by status
    status_counts = db.session.query(
        WebhookEvent.status,
        func.count(WebhookEvent.id).label("count")
    ).group_by(WebhookEvent.status).all()

    # Count dead_letter by provider
    dead_by_provider = db.session.query(
        WebhookEvent.provider,
        func.count(WebhookEvent.id).label("count")
    ).filter(
        WebhookEvent.status == "dead_letter"
    ).group_by(WebhookEvent.provider).all()

    # Recent processing rate (last 24h)
    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)
    processed_24h = WebhookEvent.query.filter(
        WebhookEvent.status == "processed",
        WebhookEvent.processed_at >= yesterday
    ).count()

    failed_24h = WebhookEvent.query.filter(
        WebhookEvent.status.in_(["failed", "dead_letter"]),
        WebhookEvent.created_at >= yesterday
    ).count()

    return jsonify({
        "queue_health": {
            "by_status": {row.status: row.count for row in status_counts},
            "dead_letter_by_provider": {row.provider: row.count for row in dead_by_provider},
            "last_24h": {
                "processed": processed_24h,
                "failed": failed_24h,
                "success_rate": round(
                    processed_24h / max(processed_24h + failed_24h, 1) * 100, 1
                )
            }
        },
        "checked_at": datetime.now(timezone.utc).isoformat()
    })


@admin_api_bp.route("/webhooks/<int:event_id>", methods=["GET"])
@login_required
@require_any_role("admin", "super_admin", "owner")
def get_webhook_detail(event_id):
    """Get full detail of a single webhook event including full payload."""
    event = WebhookEvent.query.get(event_id)
    if not event:
        return jsonify({"error": "Not found"}), 404

    return jsonify({
        "id": str(event.id),
        "provider": event.provider,
        "event_type": event.event_type,
        "status": event.status,
        "retry_count": event.retry_count,
        "last_error": event.last_error,
        "payload": event.payload,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "processed_at": event.processed_at.isoformat() if event.processed_at else None,
        "next_retry_at": event.next_retry_at.isoformat() if event.next_retry_at else None,
    })