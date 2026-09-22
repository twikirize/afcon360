# app/geo/realtime.py
"""
AFCON360 GEO - realtime location delivery boundary (GEO-14).

What this owns (domain-neutral delivery mechanism, no business meaning):
- the location event envelope (coordinates + timestamp + freshness facts)
- best-effort publication onto scoped Redis channels
- safe parsing of inbound channel payloads (malformed -> None, never raise)
- the SSE byte format + the snapshot-then-stream iteration contract

What this does NOT own:
- who may publish (the producing domain authorizes before calling)
- who may subscribe (the HTTP/SSE view authorizes before streaming)
- what a location MEANS (online/available/dispatchable stay in Transport)
- history/replay (GEO-15). Latest-state semantics only: snapshot first,
  then live updates. No event log is kept here.

Mechanism (GEO-14 decision, CASE C): Redis pub/sub + SSE. No usable push
path existed (Socket.IO serves console/host/monitor channels only; no
location channel; no SSE anywhere). Pub/sub carries no durability, so
every stream opens with the current canonical snapshot (reconnect
recovery) and clients must treat `resolved` freshness facts, not the
channel, as truth.

Public references only: channels and envelopes carry the domain's public
reference (e.g. driver `driver_code`), never internal integer IDs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, Optional

from app.geo.services import LOCATION_TTL_SECONDS
from app.geo.validation import is_fresh, normalize_location_payload

logger = logging.getLogger(__name__)

EVENT_VERSION = 1
EVENT_LOCATION_UPDATED = "location.updated"
ENTITY_TYPES = frozenset({"driver", "vehicle"})
CHANNEL_PREFIX = "geo:location"
SSE_RETRY_MS = 5000
SSE_HEARTBEAT_S = 15


def location_channel(entity_type: str, public_ref: str) -> str:
    """Scoped channel for one entity's location events.

    One channel per entity (never a global "all drivers" feed) so a
    subscriber only receives the entity it was authorized for.
    """
    return f"{CHANNEL_PREFIX}:{entity_type}:{public_ref}"


def build_location_event(entity_type: str, public_ref: str,
                         location: Dict[str, Any],
                         *,
                         source: str = "transport-tracking",
                         now: Optional[datetime] = None) -> Dict[str, Any]:
    """Build the canonical location event envelope from a stored location.

    `location` is the canonical dict form (latitude/longitude[/accuracy]
    [/timestamp]) as persisted by the producing domain. Coordinates are
    re-validated here (latitude-first, ranges enforced): invalid input
    raises ValidationError so the producer rejects it instead of
    publishing a lie. No internal IDs are accepted or emitted.
    """
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unsupported entity_type: {entity_type!r}")
    if not isinstance(public_ref, str) or not public_ref.strip():
        raise ValueError("public_ref must be a non-empty string")

    if not isinstance(location, dict):
        raise ValueError("location must be the canonical location dict")
    # Re-validates coordinates (latitude-first, ranges) and the timestamp:
    # invalid input raises ValidationError so the producer rejects it
    # instead of publishing a lie.
    point = normalize_location_payload(location)

    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    # A payload without a timestamp describes state as of publish time;
    # the envelope always carries an explicit observed_at, never a
    # refreshed copy of a stale reading.
    observed_at = point.timestamp or ref
    age_s = (ref - observed_at).total_seconds()

    return {
        "version": EVENT_VERSION,
        "event": EVENT_LOCATION_UPDATED,
        "entity_type": entity_type,
        "public_ref": public_ref.strip(),
        "latitude": point.latitude,
        "longitude": point.longitude,
        "accuracy": point.accuracy,
        "observed_at": observed_at.isoformat(),
        "age_s": age_s,
        "fresh": bool(is_fresh(point, LOCATION_TTL_SECONDS, now=ref))
        if point.timestamp is not None else True,
        "source": source,
    }


def parse_location_event(raw: Any) -> Optional[Dict[str, Any]]:
    """Parse one channel payload into a normalized envelope, or None.

    Never raises: malformed JSON, wrong shapes, unknown versions, and
    out-of-range coordinates are all safely rejected so a poisoned
    channel message can never crash a stream or fabricate movement.
    Pub/sub subscribe-confirmations (dicts without the envelope keys)
    are rejected the same way.
    """
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw).decode("utf-8")
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(payload, dict):
            return None
        if (payload.get("version") != EVENT_VERSION
                or payload.get("event") != EVENT_LOCATION_UPDATED):
            return None
        entity_type = payload.get("entity_type")
        public_ref = payload.get("public_ref")
        if entity_type not in ENTITY_TYPES:
            return None
        if not isinstance(public_ref, str) or not public_ref.strip():
            return None
        point = normalize_location_payload({
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
        })
        observed_at = payload.get("observed_at")
        if not isinstance(observed_at, str) or not observed_at.strip():
            return None
        try:
            age_s = float(payload.get("age_s", 0.0))
        except (TypeError, ValueError):
            return None
        fresh = payload.get("fresh")
        if not isinstance(fresh, bool):
            return None
        return {
            "version": EVENT_VERSION,
            "event": EVENT_LOCATION_UPDATED,
            "entity_type": entity_type,
            "public_ref": public_ref,
            "latitude": point.latitude,
            "longitude": point.longitude,
            "accuracy": payload.get("accuracy", 0.0),
            "observed_at": observed_at,
            "age_s": age_s,
            "fresh": fresh,
            "source": payload.get("source", ""),
        }
    except Exception:  # never let a bad message break the consumer
        logger.debug("Rejected malformed location event payload",
                     exc_info=True)
        return None


def publish_location_event(redis, entity_type: str, public_ref: str,
                           event: Dict[str, Any]) -> bool:
    """Publish one envelope onto its scoped channel. Best-effort: returns
    False (never raises) when Redis is unavailable so publication can
    never break the underlying location write path."""
    try:
        channel = location_channel(entity_type, public_ref.strip())
        redis.publish(channel, json.dumps(event))
        return True
    except Exception as exc:  # Redis down must not break location writes
        logger.debug("Location event publication skipped: %s", exc)
        return False


def format_sse(event_name: str, data: Dict[str, Any]) -> str:
    """One SSE frame. Payloads are JSON objects without newlines."""
    return f"event: {event_name}\ndata: {json.dumps(data)}\n\n"


def iter_location_events(next_message: Callable[[float], Any],
                         snapshot_event: Optional[Dict[str, Any]] = None,
                         *,
                         retry_ms: int = SSE_RETRY_MS,
                         heartbeat_s: float = SSE_HEARTBEAT_S,
                         ) -> Iterator[str]:
    """Snapshot-then-stream SSE body for one entity channel.

    `next_message(timeout)` returns the next raw channel payload or None
    on timeout (the view wires this to `pubsub.get_message`). Every
    stream opens with the current canonical snapshot (or a `missing`
    state frame when there is none), so connect AND reconnect always
    recover latest state without replay. Malformed payloads are skipped.
    Heartbeat comments keep intermediaries from closing idle streams.
    """
    yield f"retry: {retry_ms}\n\n"
    if snapshot_event is not None:
        yield format_sse("snapshot", snapshot_event)
    while True:
        raw = next_message(heartbeat_s)
        if raw is None:
            yield ": heartbeat\n\n"
            continue
        event = parse_location_event(raw)
        if event is None:
            continue
        yield format_sse("location", event)


__all__ = [
    "EVENT_VERSION",
    "EVENT_LOCATION_UPDATED",
    "ENTITY_TYPES",
    "CHANNEL_PREFIX",
    "SSE_RETRY_MS",
    "SSE_HEARTBEAT_S",
    "location_channel",
    "build_location_event",
    "parse_location_event",
    "publish_location_event",
    "format_sse",
    "iter_location_events",
]
