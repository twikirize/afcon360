# app/admin/hooks.py
from app.auth.services import register_hook
from app.extensions import redis_client  # optional: your redis client or message queue

def ws_broadcast(event_name, payload):
    """
    Example handler that publishes to a Redis channel or other pub/sub.
    Replace with your WebSocket broadcaster or job queue.
    """
    channel = f"events:{event_name}"
    # Keep payload small; do not include secrets
    redis_client.publish(channel, payload)  # ensure redis_client exists and is configured

def register_admin_hooks():
    # register handlers for events we care about in admin UI
    register_hook("user.created", lambda p: ws_broadcast("user.created", p))
    register_hook("user.authenticated", lambda p: ws_broadcast("user.authenticated", p))
    register_hook("user.failed_auth", lambda p: ws_broadcast("user.failed_auth", p))
    register_hook("user.verified", lambda p: ws_broadcast("user.verified", p))
    register_hook("user.activated", lambda p: ws_broadcast("user.activated", p))
    register_hook("user.soft_deleted", lambda p: ws_broadcast("user.soft_deleted", p))
    register_hook("user.restored", lambda p: ws_broadcast("user.restored", p))
    register_hook("role.assigned", lambda p: ws_broadcast("role.assigned", p))
    register_hook("role.removed", lambda p: ws_broadcast("role.removed", p))