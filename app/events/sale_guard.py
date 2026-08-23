# app/events/sale_guard.py
"""
Admin kill-switch + per-event sale mode for high-demand onsales.

A single feature flag (global or per-event) can take an onsale offline at
any time without a deploy.  Modes:

    open          - normal sales
    waitlist_only - redirect demand to the waitlist (Phase 2 UX)
    paused        - temporary hold (maintenance / incident)
    closed        - sales disabled

State is stored in Redis (with a DB-config fallback) so it is instant and
does not require a migration.  The @sale_guard decorator enforces it on the
reserve/confirm endpoints and returns a standard "high demand" response.
"""

from functools import wraps

from flask import current_app, jsonify, request

from app.extensions import redis_client

VALID_MODES = frozenset({"open", "waitlist_only", "paused", "closed"})

_GLOBAL_KEY = "events:global_sale_mode"
_EVENT_KEY = "event:sale_mode:{event_id}"


def _read_key(key: str):
    if redis_client is None:
        return None
    try:
        value = redis_client.get(key)
    except Exception:
        return None
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return value


def _write_key(key: str, mode: str) -> None:
    if redis_client is None:
        return
    try:
        if mode == "open":
            redis_client.delete(key)
        else:
            redis_client.setex(key, 86400, mode)
    except Exception:
        pass


def global_sale_mode() -> str:
    value = _read_key(_GLOBAL_KEY)
    if value in VALID_MODES:
        return value
    return current_app.config.get("EVENTS_SALE_MODE", "open")


def event_sale_mode(event_id: int) -> str:
    value = _read_key(_EVENT_KEY.format(event_id=event_id))
    if value in VALID_MODES:
        return value
    return "open"


def set_global_sale_mode(mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError("invalid sale mode")
    _write_key(_GLOBAL_KEY, mode)


def set_event_sale_mode(event_id: int, mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError("invalid sale mode")
    _write_key(_EVENT_KEY.format(event_id=event_id), mode)


def sale_guard(view):
    """Block reserve/confirm when the global or per-event sale mode is not open."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        identifier = kwargs.get("identifier") or (args[0] if args else None)
        mode = global_sale_mode()
        event = None
        if identifier is not None:
            from app.events.models import Event

            event = (
                Event.query.filter_by(slug=identifier).first()
                or Event.query.filter_by(public_id=str(identifier)).first()
            )
        if event is not None and mode == "open":
            mode = event_sale_mode(event.id)

        if mode == "open":
            return view(*args, **kwargs)

        if mode == "waitlist_only":
            return (
                jsonify(
                    {
                        "error": "high_demand",
                        "message": (
                            "High demand - join the waitlist to be notified when "
                            "more tickets are released."
                        ),
                        "sale_mode": mode,
                    }
                ),
                409,
            )

        return (
            jsonify(
                {
                    "error": "sale_unavailable",
                    "message": (
                        "Ticket sales are temporarily unavailable. Please try "
                        "again shortly."
                    ),
                    "sale_mode": mode,
                }
            ),
            503,
        )

    return wrapper
