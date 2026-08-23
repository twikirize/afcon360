# app/monitor/broadcaster.py
"""
Decoupled real-time broadcaster for the owner mission-control dashboard.

Emits structured reservation / confirmation events over SocketIO. Every emit is
best-effort: a failure here must NEVER break the underlying reservation or
confirmation flow, so the emit is wrapped and swallowed.
"""
import logging
from datetime import datetime, timezone

from app.extensions import socketio

logger = logging.getLogger(__name__)


def broadcast_reservation_event(
    event_type,
    status,
    ticket_type_id=None,
    quantity=None,
    available=None,
    message=None,
):
    """Broadcast a structured system event to all connected monitor clients.

    event_type: "ticket" | "accommodation" | "transport" (domain)
    status:     "reserved" | "sold" | "sold_out" | "payment_failed" | "error"
    """
    payload = {
        "type": event_type,
        "status": status,
        "ticket_type_id": ticket_type_id,
        "quantity": quantity,
        "available": available,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        socketio.emit("reservation_event", payload)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to broadcast reservation event: %s", exc)
