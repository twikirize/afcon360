# app/geo/routes.py
"""
AFCON360 GEO - HTTP surface (control-plane integration slice).

- /geo/api/health : JSON liveness for tooling/monitoring, unguarded
  (precedent: health endpoints stay unguarded for infra monitors).
- /geo/health     : human-readable status page. Restricted by the
  ``geo.view`` permission, which is seeded to the OWNER only. Super admins
  and admins are granted access solely when the owner enables it on the
  owner-dashboard "GEO Access Control" toggle. The raw JSON remains
  available for tooling at /geo/api/health.
- /geo/           : guarded module overview rendering truthful foundation
  status. Requires login + enabled GEO module + ``geo.view`` permission
  (owner-granted for super_admin/admin). When GEO is disabled, the module
  guard returns the standard module-disabled page (runtime effect proof).

Full location/routing/geocoding endpoints arrive with their service nodes.
"""

from flask import abort, jsonify, render_template
from flask_login import login_required

from app.auth.decorators import admin_required, require_permission
from app.geo import geo_bp
from app.utils.module_guard import require_module_enabled


def _health_payload():
    """GEO health payload shared by the JSON (tooling) and UX endpoints."""
    from app.geo.config import load_geo_config

    config = load_geo_config()
    return {
        "module": "geo",
        "status": "ok",
        "adapters": {
            "valhalla": {"enabled": config.valhalla.enabled,
                         "configured": bool(config.valhalla.base_url)},
            "photon": {"enabled": config.photon.enabled,
                       "configured": bool(config.photon.base_url)},
            "tiles": {"kind": config.tiles.kind,
                      "configured": bool(config.tiles.base_url)},
        },
    }


@geo_bp.get("/api/health")
def health_json():
    """GEO liveness for tooling/monitoring: JSON, unguarded (health precedent).

    Intentionally without module/login guards so infra monitors and CI keep
    polling it regardless of GEO module flag or session state.
    """
    return jsonify(_health_payload()), 200


@geo_bp.get("/health")
@login_required
@require_permission("geo.view")
def health():
    """GEO health UX page: human-readable status for users with ``geo.view``.

    The permission is seeded to the owner only; super admins and admins get
    access only when the owner grants it via the owner-dashboard GEO access
    toggle. Not gated on the GEO module flag so operators can still see
    truthful status when the module is disabled. The raw JSON stays open at
    /geo/api/health for tooling.
    """
    from flask import current_app

    from app.geo.config import load_geo_config
    from app.utils.module_toggle_service import ModuleToggleService

    config = load_geo_config(current_app)
    payload = _health_payload()
    return render_template(
        "geo/health.html",
        status=payload["status"],
        geo_enabled=ModuleToggleService.is_enabled("geo"),
        adapters=payload["adapters"],
        location_ttl_seconds=config.location_ttl_seconds,
    )


def _resolve_location_subject(entity_type: str, public_ref: str):
    """Resolve a stream public reference to its internal record id.

    Drivers resolve by `driver_code`, vehicles by `license_plate` — the
    established external references. Returns the internal id (server-side
    only, never emitted) or None. Soft-deleted records never resolve.
    """
    from app.extensions import db

    if entity_type == "driver":
        from app.transport.models import DriverProfile
        record = DriverProfile.query.filter_by(
            driver_code=public_ref, is_deleted=False).first()
    elif entity_type == "vehicle":
        from app.transport.models import Vehicle
        record = Vehicle.query.filter_by(
            license_plate=public_ref, is_deleted=False).first()
    else:
        return None
    if record is None:
        return None
    return record.id


def _next_channel_payload(get_message, timeout):
    """Extract one channel payload for the SSE iterator.

    Subscribe-confirmations and timeouts surface as None (heartbeat /
    skip); only `message` frames carry data. Never raises.
    """
    try:
        msg = get_message(timeout=timeout)
    except Exception:
        return None
    if not isinstance(msg, dict) or msg.get("type") != "message":
        return None
    return msg.get("data")


@geo_bp.get("/stream/location/<entity_type>/<public_ref>")
@login_required
@admin_required
@require_module_enabled("transport")
def location_stream(entity_type, public_ref):
    """SSE: authorized live location for one entity (GEO-14).

    Authorization mirrors the existing driver/vehicle location read
    surfaces exactly: logged-in admin, transport module enabled. One
    channel per entity (never a global feed); the URL carries the
    public reference only. Every stream opens with the current
    canonical snapshot (or a truthful `missing` state), then live
    updates; reconnect therefore recovers latest state with no replay.
    Redis/channel failure degrades to snapshot-only with an explicit
    `degraded` state — never a fake "live" status.
    """
    from flask import Response, current_app

    from app.geo.realtime import (ENTITY_TYPES, format_sse,
                                  iter_location_events,
                                  location_channel)
    from app.utils.exceptions import NotFoundError

    if (entity_type not in ENTITY_TYPES or not isinstance(public_ref, str)
            or not public_ref.strip() or len(public_ref) > 64):
        abort(404)
    public_ref = public_ref.strip()

    internal_id = _resolve_location_subject(entity_type, public_ref)
    if internal_id is None:
        abort(404)

    from typing import Any, Dict

    from app.transport.services.tracking_service import TrackingService
    snapshot = None
    current: Dict[str, Any]
    try:
        current = TrackingService.get_location(entity_type, internal_id)
    except NotFoundError:
        current = {"success": False}
    except Exception as exc:
        current_app.logger.warning(
            "Location snapshot failed for %s %s: %s",
            entity_type, public_ref, exc)
        current = {"success": False}
    if current.get("success"):
        try:
            from app.geo.realtime import build_location_event
            snapshot = build_location_event(
                entity_type, public_ref, current["data"]["location"])
        except Exception as exc:
            current_app.logger.warning(
                "Location snapshot rejected for %s %s: %s",
                entity_type, public_ref, exc)
            snapshot = None

    try:
        from app.extensions import redis_client
        pubsub = redis_client.pubsub()
        pubsub.subscribe(location_channel(entity_type, public_ref))
        get_message = pubsub.get_message
        channel_ok = True
    except Exception as exc:
        current_app.logger.warning(
            "Realtime channel unavailable for %s %s: %s",
            entity_type, public_ref, exc)
        channel_ok = False

    def generate():
        if snapshot is not None:
            yield format_sse("snapshot", snapshot)
        else:
            yield format_sse("state", {
                "status": "missing",
                "entity_type": entity_type,
                "public_ref": public_ref,
            })
        if not channel_ok:
            yield format_sse("state", {
                "status": "degraded",
                "reason": ("realtime channel unavailable; "
                           "snapshot only, no live updates"),
                "entity_type": entity_type,
                "public_ref": public_ref,
            })
            return
        yield from iter_location_events(
            lambda timeout: _next_channel_payload(get_message, timeout),
            snapshot_event=None)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@geo_bp.get("/history/location/<entity_type>/<public_ref>")
@login_required
@admin_required
@require_module_enabled("transport")
def location_history(entity_type, public_ref):
    """JSON: authorized observation history for one entity (GEO-15).

    Authorization mirrors the live location surfaces exactly: logged-in
    admin, transport module enabled, one entity per request (never a
    global feed); the URL carries the public reference only. Unknown
    references 404; known entities with no observations return an
    honest empty list. Chronological (oldest first); internal IDs are
    never emitted.
    """
    from flask import request

    from app.geo.history import get_observations
    from app.geo.realtime import ENTITY_TYPES

    if (entity_type not in ENTITY_TYPES or not isinstance(public_ref, str)
            or not public_ref.strip() or len(public_ref) > 64):
        abort(404)
    public_ref = public_ref.strip()

    if _resolve_location_subject(entity_type, public_ref) is None:
        abort(404)

    try:
        observations = get_observations(
            entity_type, public_ref,
            since=request.args.get("since"),
            until=request.args.get("until"),
            limit=request.args.get("limit", 100),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, "data": observations,
                    "count": len(observations)}), 200


@geo_bp.get("/activity/cells")
@login_required
@admin_required
@require_module_enabled("transport")
def activity_cells():
    """JSON: observation concentration per grid cell (GEO-17).

    Derived read-only from GEO-15 history: counts + distinct observed
    entities per cell. Raw movements, internal IDs, and availability
    semantics are never exposed (availability stays in Transport).
    since/until required; window echoed back; historical aggregates
    are never labelled live.
    """
    from flask import request

    from app.geo.activity import get_activity

    try:
        payload = get_activity(
            request.args.get("entity_type"),
            since=request.args.get("since"),
            until=request.args.get("until"),
            bbox={
                "min_latitude": request.args.get("min_latitude"),
                "max_latitude": request.args.get("max_latitude"),
                "min_longitude": request.args.get("min_longitude"),
                "max_longitude": request.args.get("max_longitude"),
            } if request.args.get("min_latitude") is not None else None,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, **payload}), 200


@geo_bp.get("/demand/cells")
@login_required
@admin_required
@require_module_enabled("transport")
def demand_cells():
    """JSON: booking-request concentration per grid cell (GEO-17).

    Demand signal is Transport-owned
    (`booking_request_points`: submitted requests except drafts and
    cancellations); GEO only bins the points. Counts per cell, no
    identifiers, no pricing/dispatch meaning.
    """
    from datetime import datetime, timezone
    from flask import request

    from app.geo.activity import aggregate_cells, parse_window

    try:
        start, end = parse_window(request.args.get("since"),
                                  request.args.get("until"))
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    try:
        from app.transport.services.booking_service import (
            booking_request_points)
        points, skipped = booking_request_points(start, end)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    agg = aggregate_cells(points)
    cells = [{
        "cell_key": cell["cell_key"],
        "center": cell["center"],
        "request_count": cell["count"],
    } for cell in agg["cells"]]
    return jsonify({
        "success": True,
        "cells": cells,
        "window": {"since": start.isoformat(), "until": end.isoformat()},
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "skipped_invalid": skipped + agg["skipped_invalid"],
        "truncated": agg["truncated"],
    }), 200


@geo_bp.get("/stream/booking/<booking_reference>")
@login_required
@require_module_enabled("transport")
def booking_location_stream(booking_reference):
    """SSE: rider booking-scoped live driver location (GEO rider node).

    Authorization is booking ownership, NOT admin role and NOT driver
    reference knowledge: the viewer must own the booking (or hold a
    global admin role — union of existing powers, no broadening), the
    booking must be in a trackable active state, and an assignment
    must currently exist. The Transport-owned
    `get_rider_tracking_subject` decides; GEO only delivers.

    Every stream opens with the current snapshot (or truthful
    `missing`), then live driver-channel updates. Booking state and
    assignment are RE-VALIDATED on every stream tick (message or
    heartbeat): terminal states, released assignment, or a changed
    driver close the stream with an explicit `closed` frame — access
    is never resumed on reconnect without re-authorization, and the
    driver channel itself never leaks across bookings (per-tick
    public-ref match).
    """
    from flask import Response, current_app
    from flask_login import current_user

    from app.auth.helpers import has_global_role
    from app.geo.realtime import (format_sse, iter_location_events,
                                   location_channel)
    from app.transport.services.tracking_service import TrackingService
    from app.utils.exceptions import NotFoundError

    if (not isinstance(booking_reference, str)
            or not booking_reference.strip()
            or len(booking_reference) > 64):
        abort(404)
    ref = booking_reference.strip()
    viewer_is_admin = bool(has_global_role(
        current_user, "admin", "super_admin", "owner"))
    # Capture plain values at view entry: streaming generators iterate
    # after the request context may be gone (test clients, servers),
    # so per-tick revalidation must not touch request-bound proxies.
    viewer_uid = int(current_user.id)
    from flask import current_app as _current_app
    app_obj = _current_app._get_current_object()

    def _subject():
        with app_obj.app_context():
            return TrackingService.get_rider_tracking_subject(
                ref, viewer_uid, viewer_is_admin)

    subject = _subject()
    if subject["reason"] == "unknown_booking":
        abort(404)
    if subject["reason"] == "not_authorized":
        abort(403)
    if not subject["allowed"]:
        abort(404)

    driver_public_ref = subject["driver_public_ref"]
    internal_id = _resolve_location_subject("driver", driver_public_ref)
    if internal_id is None:
        abort(404)

    from typing import Any, Dict

    snapshot = None
    current: Dict[str, Any]
    try:
        current = TrackingService.get_location("driver", internal_id)
    except NotFoundError:
        current = {"success": False}
    except Exception as exc:
        current_app.logger.warning(
            "Rider snapshot failed for booking %s: %s", ref, exc)
        current = {"success": False}
    if current.get("success"):
        try:
            from app.geo.realtime import build_location_event
            snapshot = build_location_event(
                "driver", driver_public_ref, current["data"]["location"])
        except Exception as exc:
            current_app.logger.warning(
                "Rider snapshot rejected for booking %s: %s", ref, exc)
            snapshot = None

    try:
        from app.extensions import redis_client
        pubsub = redis_client.pubsub()
        pubsub.subscribe(location_channel("driver", driver_public_ref))
        get_message = pubsub.get_message
        channel_ok = True
    except Exception as exc:
        current_app.logger.warning(
            "Rider channel unavailable for booking %s: %s", ref, exc)
        channel_ok = False

    def generate():
        if snapshot is not None:
            yield format_sse("snapshot", snapshot)
        else:
            yield format_sse("state", {
                "status": "missing",
                "booking_reference": ref,
            })
        if not channel_ok:
            yield format_sse("state", {
                "status": "degraded",
                "reason": ("realtime channel unavailable; "
                           "snapshot only, no live updates"),
                "booking_reference": ref,
            })
            return
        for frame in iter_location_events(
                lambda timeout: _next_channel_payload(get_message, timeout),
                snapshot_event=None):
            yield frame

    # NOTE: per-tick booking revalidation wraps the generator below:
    # the opening frames (snapshot/missing, or degraded + return) pass
    # through; every subsequent live/heartbeat tick re-checks the
    # tracking subject first.
    def guarded():
        iterator = generate()
        # Passthrough for retry + opening frames (already authorized).
        try:
            yield next(iterator)
            yield next(iterator)
        except StopIteration:
            return
        for frame in iterator:
            live = _subject()
            if (not live["allowed"]
                    or live["driver_public_ref"] != driver_public_ref):
                yield format_sse("state", {
                    "status": "closed",
                    "reason": live["reason"],
                    "booking_reference": ref,
                })
                return
            event_ref = _frame_public_ref(frame)
            if event_ref is not None and event_ref != driver_public_ref:
                continue
            yield frame

    return Response(guarded(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


def _frame_public_ref(frame):
    """Public ref carried by an SSE data frame, or None for
    heartbeats/retry lines (no payload to check)."""
    try:
        text = frame.decode("utf-8") if isinstance(frame, bytes) else frame
        for line in text.splitlines():
            if line.startswith("data:"):
                import json as _json
                payload = _json.loads(line[5:].strip())
                if isinstance(payload, dict):
                    return payload.get("public_ref")
                return None
        return None
    except Exception:
        return None


@geo_bp.get("/", endpoint="overview")
@login_required
@require_module_enabled("geo")
@require_permission("geo.view")
def overview():
    """GEO module overview: truthful foundation status only.

    Shows enabled state + adapter availability from the real GEO config.
    Provider stubs report not-configured until their implementation nodes
    land. No maps, no fabricated locations/routes/demand. The ``geo.view``
    permission is seeded to the owner only; super_admin/admin get access
    only when the owner grants it via the owner-dashboard GEO toggle.
    """
    from flask import current_app

    from app.geo.config import load_geo_config
    from app.geo.map_renderer import build_public_map_config
    from app.utils.module_toggle_service import ModuleToggleService

    config = load_geo_config(current_app)
    enabled = ModuleToggleService.is_enabled("geo")
    return render_template(
        "geo/overview.html",
        geo_enabled=enabled,
        map_config=build_public_map_config(config),
        tiles_kind=config.tiles.kind,
        tiles_configured=bool(config.tiles.base_url),
        valhalla_enabled=config.valhalla.enabled,
        valhalla_configured=bool(config.valhalla.base_url),
        photon_enabled=config.photon.enabled,
        photon_configured=bool(config.photon.base_url),
        location_ttl_seconds=config.location_ttl_seconds,
    )
