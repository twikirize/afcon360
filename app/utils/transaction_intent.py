"""
Transaction Intent Service - Pre-authentication transaction continuity.

This module provides a secure mechanism for anonymous visitors to preserve
their transaction intent (event ticket selection, accommodation booking,
transport booking) across the authentication boundary.

SECURITY PROPERTIES:
- Short-lived (configurable TTL, default 30 minutes)
- Integrity protected (signed with app SECRET_KEY)
- Session-bound (tied to Flask session ID)
- Cleared after successful conversion/commit/cancellation
- Cannot bypass authorization (intent is only a convenience layer)
- Cannot alter authoritative pricing/inventory/ownership/KYC/payment decisions
- Idempotent (repeated restore/consumption is safe)
- At commit time, authoritative state is re-resolved from database

INTENT DATA STRUCTURE:
{
    "intent_type": "event_ticket" | "accommodation_booking" | "transport_booking",
    "domain_refs": {
        "event_public_id": "...",
        "ticket_type_public_id": "...",
        "property_public_id": "...",
        "room_type_public_id": "...",
        "transport_route_public_id": "...",
    },
    "dates": {"check_in": "...", "check_out": "...", "pickup_time": "..."},
    "quantity": 1,
    "participant_info": {"full_name": "...", "email": "...", "phone": "..."},
    "return_route": "/events/...",  # Where to redirect after auth
    "created_at": "ISO timestamp",
    "expires_at": "ISO timestamp",
    "idempotency_key": "uuid",
}
"""

import json
import uuid
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from flask import session, current_app, has_request_context


# Default TTL for transaction intent (30 minutes)
DEFAULT_INTENT_TTL_MINUTES = 30
MAX_INTENT_TTL_MINUTES = 120  # 2 hours max


class TransactionIntentError(Exception):
    """Raised when intent operations fail."""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _get_signing_key() -> bytes:
    """Get the HMAC signing key from app config."""
    if has_request_context():
        return current_app.config.get("SECRET_KEY", "dev-secret-change-in-production").encode()
    return b"dev-secret-change-in-production"


def _sign_payload(payload: Dict[str, Any]) -> str:
    """Create HMAC signature for payload integrity."""
    serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    signature = hmac.new(
        _get_signing_key(),
        serialized.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature


def _verify_signature(payload: Dict[str, Any], signature: str) -> bool:
    """Verify HMAC signature."""
    expected = _sign_payload(payload)
    return hmac.compare_digest(expected, signature)


def _get_session_id() -> Optional[str]:
    """Get current Flask session ID."""
    if has_request_context() and session:
        # Flask session doesn't have sid by default; use a stable session marker
        if '_session_id' not in session:
            session['_session_id'] = str(uuid.uuid4())
        return session['_session_id']
    return None


def create_transaction_intent(
    intent_type: str,
    domain_refs: Optional[Dict[str, str]] = None,
    dates: Optional[Dict[str, str]] = None,
    quantity: int = 1,
    participant_info: Optional[Dict[str, str]] = None,
    return_route: Optional[str] = None,
    ttl_minutes: int = DEFAULT_INTENT_TTL_MINUTES,
) -> Tuple[str, Dict[str, Any]]:
    """
    Create a new transaction intent and store in session.
    
    Returns:
        Tuple of (idempotency_key, intent_dict)
    
    Raises:
        TransactionIntentError: If intent_type is invalid or session unavailable.
    """
    if not has_request_context():
        raise TransactionIntentError("NO_REQUEST_CONTEXT", "Cannot create intent outside request context")
    
    if not session:
        raise TransactionIntentError("NO_SESSION", "Flask session not available")
    
    # Validate intent type
    valid_types = ("event_ticket", "accommodation_booking", "transport_booking")
    if intent_type not in valid_types:
        raise TransactionIntentError("INVALID_INTENT_TYPE", f"intent_type must be one of {valid_types}")
    
    # Validate TTL
    ttl_minutes = max(1, min(ttl_minutes, MAX_INTENT_TTL_MINUTES))
    
    # Generate unique idempotency key
    idempotency_key = str(uuid.uuid4())
    
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ttl_minutes)
    
    intent = {
        "intent_type": intent_type,
        "domain_refs": domain_refs or {},
        "dates": dates or {},
        "quantity": max(1, int(quantity)),
        "participant_info": participant_info or {},
        "return_route": return_route,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "idempotency_key": idempotency_key,
        "session_id": _get_session_id(),
    }
    
    # Sign the intent for integrity
    intent["_signature"] = _sign_payload({k: v for k, v in intent.items() if k != "_signature"})
    
    # Store in session under a namespaced key
    session.setdefault("_transaction_intents", {})
    session["_transaction_intents"][idempotency_key] = intent
    session.modified = True
    
    return idempotency_key, intent


def get_transaction_intent(idempotency_key: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve and validate a transaction intent.
    
    Returns the intent dict if valid and not expired, None otherwise.
    Does NOT consume the intent - use consume_transaction_intent() for that.
    """
    if not has_request_context() or not session:
        return None
    
    intents = session.get("_transaction_intents", {})
    intent = intents.get(idempotency_key)
    
    if not intent:
        return None
    
    # Verify signature
    stored_sig = intent.pop("_signature", None)
    if not stored_sig or not _verify_signature(intent, stored_sig):
        # Tampered intent - remove it
        session["_transaction_intents"].pop(idempotency_key, None)
        session.modified = True
        return None
    
    # Restore signature for future checks
    intent["_signature"] = stored_sig
    
    # Check expiry
    try:
        expires_at = datetime.fromisoformat(intent["expires_at"].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_at:
            session["_transaction_intents"].pop(idempotency_key, None)
            session.modified = True
            return None
    except (ValueError, KeyError):
        session["_transaction_intents"].pop(idempotency_key, None)
        session.modified = True
        return None
    
    # Verify session binding
    if intent.get("session_id") and intent["session_id"] != _get_session_id():
        # Session mismatch - potential hijacking attempt
        session["_transaction_intents"].pop(idempotency_key, None)
        session.modified = True
        return None
    
    return intent


def consume_transaction_intent(idempotency_key: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve and consume (remove) a transaction intent.
    
    Use this when committing the transaction - the intent is consumed
    and cannot be reused.
    
    Returns the intent dict if valid, None otherwise.
    """
    intent = get_transaction_intent(idempotency_key)
    if intent:
        if has_request_context() and session:
            session["_transaction_intents"].pop(idempotency_key, None)
            session.modified = True
    return intent


def clear_transaction_intent(idempotency_key: str) -> bool:
    """Explicitly clear a transaction intent (e.g., on cancellation)."""
    if not has_request_context() or not session:
        return False
    removed = session["_transaction_intents"].pop(idempotency_key, None) is not None
    if removed:
        session.modified = True
    return removed


def clear_all_transaction_intents() -> int:
    """Clear all transaction intents for the current session."""
    if not has_request_context() or not session:
        return 0
    count = len(session.get("_transaction_intents", {}))
    session["_transaction_intents"] = {}
    session.modified = True
    return count


def get_active_intent_count() -> int:
    """Get count of valid (non-expired) intents in current session."""
    if not has_request_context() or not session:
        return 0
    count = 0
    now = datetime.now(timezone.utc)
    for intent in session.get("_transaction_intents", {}).values():
        try:
            expires_at = datetime.fromisoformat(intent["expires_at"].replace('Z', '+00:00'))
            if now <= expires_at:
                count += 1
        except (ValueError, KeyError):
            pass
    return count


# Convenience functions for specific domains

def create_event_ticket_intent(
    event_public_id: str,
    ticket_type_public_id: str,
    quantity: int = 1,
    participant_info: Optional[Dict[str, str]] = None,
    return_route: Optional[str] = None,
    ttl_minutes: int = DEFAULT_INTENT_TTL_MINUTES,
) -> Tuple[str, Dict[str, Any]]:
    """Create intent for event ticket purchase."""
    return create_transaction_intent(
        intent_type="event_ticket",
        domain_refs={
            "event_public_id": event_public_id,
            "ticket_type_public_id": ticket_type_public_id,
        },
        quantity=quantity,
        participant_info=participant_info,
        return_route=return_route,
        ttl_minutes=ttl_minutes,
    )


def create_accommodation_booking_intent(
    property_public_id: str,
    room_type_public_id: str,
    check_in: str,
    check_out: str,
    rooms_requested: int = 1,
    participant_info: Optional[Dict[str, str]] = None,
    return_route: Optional[str] = None,
    ttl_minutes: int = DEFAULT_INTENT_TTL_MINUTES,
) -> Tuple[str, Dict[str, Any]]:
    """Create intent for accommodation booking."""
    return create_transaction_intent(
        intent_type="accommodation_booking",
        domain_refs={
            "property_public_id": property_public_id,
            "room_type_public_id": room_type_public_id,
        },
        dates={"check_in": check_in, "check_out": check_out},
        quantity=rooms_requested,
        participant_info=participant_info,
        return_route=return_route,
        ttl_minutes=ttl_minutes,
    )


def create_transport_booking_intent(
    route_public_id: Optional[str] = None,
    pickup_time: Optional[str] = None,
    dropoff_time: Optional[str] = None,
    passenger_count: int = 1,
    participant_info: Optional[Dict[str, str]] = None,
    return_route: Optional[str] = None,
    ttl_minutes: int = DEFAULT_INTENT_TTL_MINUTES,
) -> Tuple[str, Dict[str, Any]]:
    """Create intent for transport booking."""
    domain_refs = {}
    dates = {}
    if route_public_id:
        domain_refs["transport_route_public_id"] = route_public_id
    if pickup_time:
        dates["pickup_time"] = pickup_time
    if dropoff_time:
        dates["dropoff_time"] = dropoff_time
    
    return create_transaction_intent(
        intent_type="transport_booking",
        domain_refs=domain_refs,
        dates=dates,
        quantity=passenger_count,
        participant_info=participant_info,
        return_route=return_route,
        ttl_minutes=ttl_minutes,
    )


def validate_intent_against_authoritative_state(intent: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validate intent against current authoritative database state.
    
    This MUST be called at commit time before finalizing any transaction.
    The intent is ONLY a convenience layer - authoritative state always wins.
    
    Returns:
        Tuple of (is_valid, error_message, resolved_authoritative_data)
    """
    # This is a stub - actual implementation would query each domain's
    # authoritative services to re-validate pricing, inventory, etc.
    # For now, we return the intent data as-is with a note that
    # the caller must re-resolve from the database.
    
    intent_type = intent.get("intent_type")
    
    if intent_type == "event_ticket":
        # Caller must re-fetch Event, TicketType from DB using public_ids
        # and verify: event status, ticket availability, current price
        return True, "OK - re-resolve event/ticket from DB", {
            "event_public_id": intent["domain_refs"].get("event_public_id"),
            "ticket_type_public_id": intent["domain_refs"].get("ticket_type_public_id"),
        }
    
    elif intent_type == "accommodation_booking":
        # Caller must re-fetch Property, RoomType from DB
        # and verify: property status, room availability, current rates
        return True, "OK - re-resolve property/room from DB", {
            "property_public_id": intent["domain_refs"].get("property_public_id"),
            "room_type_public_id": intent["domain_refs"].get("room_type_public_id"),
            "check_in": intent["dates"].get("check_in"),
            "check_out": intent["dates"].get("check_out"),
        }
    
    elif intent_type == "transport_booking":
        # Caller must re-fetch Route/Vehicle from DB
        return True, "OK - re-resolve transport from DB", {
            "route_public_id": intent["domain_refs"].get("transport_route_public_id"),
            "pickup_time": intent["dates"].get("pickup_time"),
        }
    
    return False, f"Unknown intent_type: {intent_type}", {}


# Template context processor for accessing intent in templates
def inject_transaction_intents():
    """Jinja2 context processor to expose active intent count."""
    if not has_request_context():
        return {}
    return {
        "active_intent_count": get_active_intent_count(),
    }