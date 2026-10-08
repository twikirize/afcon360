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
- /geo/api/geocode: anonymous-allowed forward-geocode search for the rider
  location picker (UI-01 + destination discovery). Deliberately NOT ``geo.view`` (that permission
  is owner-only and would lock riders out) and NOT a GEO module hard-gate:
  a disabled, unconfigured or unreachable provider degrades truthfully to
  ``results: []`` instead of blocking.

Full location/routing/geocoding endpoints arrive with their service nodes.
"""

from flask import abort, jsonify, render_template
from flask_login import login_required
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.auth.decorators import admin_required, require_permission
from app.geo import geo_bp
from app.utils.exceptions import RateLimitError
from app.utils.module_guard import require_module_enabled
from app.utils.rate_limiting import rate_limit


@geo_bp.errorhandler(RateLimitError)
def _geo_rate_limited(error):
    """429 JSON for GEO rate-limit breaches (blueprint-scoped).

    The house ``rate_limit`` decorator raises ``RateLimitError``, which
    has no application-wide handler (it would become a 500 via the
    generic Exception handler). GEO answers 429 with the endpoint's
    error shape instead. Scope is this blueprint only: no other
    module's behavior changes.
    """
    return jsonify({
        "success": False,
        "error": getattr(error, "message", None) or "Rate limit exceeded",
        "code": "RATE_LIMITED",
    }), 429


def _health_payload():
    """GEO health payload shared by the JSON (tooling) and UX endpoints."""
    from app.geo.config import load_geo_config

    config = load_geo_config()
    geoapify = getattr(config, "geoapify", None)
    return {
        "module": "geo",
        "status": "ok",
        "adapters": {
            "valhalla": {"enabled": config.valhalla.enabled,
                         "configured": bool(config.valhalla.base_url)},
            "photon": {"enabled": config.photon.enabled,
                       "configured": bool(config.photon.base_url)},
            # The API key itself is never exposed: configured is a boolean.
            "geoapify": {
                "enabled": bool(getattr(geoapify, "enabled", False)),
                "configured": bool(getattr(geoapify, "api_key", "")),
            },
            "tiles": {"kind": config.tiles.kind,
                      "configured": bool(config.tiles.base_url)},
        },
    }


def _provider_attribution(provider: str):
    """Display credit for the answering geocoding provider.

    Geoapify's free plan mandates "Powered by Geoapify"; OSM-derived data
    mandates the OSM credit. None when no provider answered (no provider
    data is displayed then). Plain text: rendering (link/placement) is the
    consuming UI's decision.
    """
    if provider == "geoapify":
        from app.geo.providers.geoapify import ATTRIBUTION_GEOAPIFY
        return ATTRIBUTION_GEOAPIFY
    if provider == "photon":
        from app.geo.providers.geoapify import ATTRIBUTION_OSM
        return ATTRIBUTION_OSM
    return None


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


@geo_bp.get("/api/geocode")
@rate_limit("geo_geocode", limit=60, period=60)
def geocode_search():
    """JSON forward-geocode search for the rider location picker (UI-01).

    Anonymous-allowed so riders can discover places before signing in
    (pickup AND destination search share this endpoint; the booking
    action still goes through transport.book_transport with auth + KYC
    + rate limit unchanged). No login, no ``require_permission("geo.view")``
    (owner-only, would lock riders out), no GEO module hard-gate: a
    disabled/unconfigured/unreachable provider degrades truthfully to
    ``results: []`` instead of blocking the form. Abuse is bounded by
    the per-IP ``rate_limit`` (60/minute) below.

    Quota protection: 60 requests/minute shared endpoint budget (existing
    ``rate_limit`` helper, in-memory; see note below), client-side
    debounce retained, provider timeouts bounded per adapter.
    Single-character queries are answered as honest no-results without
    touching any provider.

    Contract:
        GET /geo/api/geocode?q=<query>&limit=<n>
        - q: non-empty after strip, else 400 INVALID_QUERY.
        - limit: optional positive int, default 5, clamped to max 5,
          else 400 INVALID_LIMIT.
        - 200: {success, query, provider, results[], attribution}. ``provider``
          names the provider that ANSWERED ("geoapify" when the primary
          produced candidates, "photon" when the fallback did,
          "unresolved" when nothing did); each result is
          {label, latitude, longitude, provider} plus ``osm_type`` /
          ``osm_id`` ONLY when the provider actually supplied that datum
          (the canonical provenance reference pair - never a wholesale
          ``raw`` dump). ``attribution`` carries the required display
          credit for the answering provider (Geoapify free plan mandates
          "Powered by Geoapify"; OSM data mandates the OSM credit); it is
          None when no provider answered.
        - Every provider miss (disabled, unconfigured, timeout, HTTP
          error, malformed response, empty collection, no matches)
          returns ``results: []`` with ``success: true`` - never
          fabricated coordinates.
    """
    from flask import request

    from app.geo.config import load_geo_config
    from app.geo.services import build_geocoding_service

    query = request.args.get("q")
    if not isinstance(query, str) or not query.strip():
        return jsonify({
            "success": False,
            "error": "q must be a non-empty string",
            "code": "INVALID_QUERY",
        }), 400
    query = query.strip()

    if len(query) < 2:
        # Minimum query length (quota protection): a single character
        # cannot usefully resolve. Honest no-result, no provider call.
        return jsonify({
            "success": True,
            "query": query,
            "provider": "unresolved",
            "results": [],
            "attribution": None,
        }), 200

    limit_raw = request.args.get("limit")
    if limit_raw is None:
        limit = 5
    else:
        try:
            limit = int(str(limit_raw).strip())
        except (TypeError, ValueError):
            limit = None
        if limit is None or limit <= 0:
            return jsonify({
                "success": False,
                "error": "limit must be a positive integer (max 5)",
                "code": "INVALID_LIMIT",
            }), 400
    limit = min(limit, 5)

    # Per-request service from the existing env/config surface: no global
    # wiring change, and the existing get_geocoding_service() singleton
    # (provider-less default) stays untouched for its current callers.
    service = build_geocoding_service(load_geo_config())
    results = service.geocode(query, limit=limit)

    items = []
    for result in results:
        if result is None or not getattr(result, "resolved", False):
            continue  # truthful miss: unresolved entries are never emitted
        latitude = getattr(result, "latitude", None)
        longitude = getattr(result, "longitude", None)
        provider = getattr(result, "provider", None)
        if latitude is None or longitude is None:
            continue
        if (not isinstance(provider, str) or not provider.strip()
                or provider == "unresolved"):
            # Every emitted result must be echoable as booking-time
            # evidence; an identity-less result would be refused later
            # (H2), so it is not presented now.
            continue
        item = {
            "label": getattr(result, "display_name", "") or "",
            "latitude": latitude,
            "longitude": longitude,
            "provider": provider,
        }
        raw = getattr(result, "raw", None)
        if isinstance(raw, dict):
            # OSM provenance datum pair only - never the raw payload.
            if raw.get("osm_type") is not None:
                item["osm_type"] = raw["osm_type"]
            if raw.get("osm_id") is not None:
                item["osm_id"] = raw["osm_id"]
        items.append(item)

    return jsonify({
        "success": True,
        "query": query,
        # Answer-based provider identity: who actually resolved the
        # candidates (geoapify > photon > unresolved). Never the wiring.
        "provider": items[0]["provider"] if items else "unresolved",
        "results": items,
        "attribution": _provider_attribution(
            items[0]["provider"] if items else "unresolved"),
    }), 200


@geo_bp.get("/api/reverse")
@rate_limit("geo_reverse", limit=60, period=60)
def reverse_lookup():
    """JSON reverse-geocode for accepted GPS/map coordinates (UI bridge).

    DISCOVERY boundary (anonymous-or-authenticated): turns already-known
    coordinates into a human-readable identity for display. Enrichment
    ONLY — it never establishes, moves, or re-sources a location:
    callers keep their coordinates, source, and method untouched.

    Contract:
        GET /geo/api/reverse?lat=<lat>&lon=<lon>
        - lat/lon: required finite numbers in range (bool/str rejected,
          never coerced), else 400 INVALID_COORDINATES.
        - 200: {success, provider, latitude, longitude, display_name,
          presentable, attribution}. ``provider`` names who ANSWERED;
          ``display_name`` is the provider label ONLY when
          ``presentable`` is true, else None (unknown stays unknown —
          callers fall back to their generic method label). ``attribution``
          mirrors the geocode endpoint; None when nothing answered.
        - Provider outage degrades to presentable=false with success=true
          (coordinates stay valid; never fabricated identity).
    Quota protection mirrors the geocode endpoint (shared 60/min budget
    under a separate key, bounded provider timeouts, no credential
    exposure anywhere in the path).
    """
    from flask import request

    from app.core.validators import validate_coordinates
    from app.geo.config import load_geo_config
    from app.geo.interfaces import GeoPoint
    from app.geo.services import (build_geocoding_service,
                                  reverse_identity_presentable)

    def _number(value):
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str) and value.strip():
            try:
                number = float(value.strip())
            except (TypeError, ValueError):
                return None
        else:
            return None
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number

    latitude = _number(request.args.get("lat"))
    longitude = _number(request.args.get("lon"))
    if latitude is None or longitude is None:
        return jsonify({
            "success": False,
            "error": "lat and lon must be finite numbers",
            "code": "INVALID_COORDINATES",
        }), 400
    try:
        validate_coordinates(latitude, longitude)
    except Exception:
        return jsonify({
            "success": False,
            "error": "lat must be within [-90, 90] and lon within "
                     "[-180, 180]",
            "code": "INVALID_COORDINATES",
        }), 400

    service = build_geocoding_service(load_geo_config())
    result = service.reverse(GeoPoint(latitude, longitude))

    resolved = result is not None and bool(
        getattr(result, "resolved", False))
    if resolved and reverse_identity_presentable(result):
        provider = getattr(result, "provider", None) or "unresolved"
        display_name = getattr(result, "display_name", "") or ""
        presentable = True
    else:
        provider = "unresolved"
        display_name = None
        presentable = False

    return jsonify({
        "success": True,
        "provider": provider,
        "latitude": latitude,
        "longitude": longitude,
        "display_name": display_name,
        "presentable": presentable,
        "attribution": _provider_attribution(provider),
    }), 200


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


class _ChannelDead(Exception):
    """Raised when the underlying Redis pubsub connection is broken."""


def _next_channel_payload(get_message, timeout):
    """Extract one channel payload for the SSE iterator.

    Subscribe-confirmations and timeouts surface as None (heartbeat /
    skip); only `message` frames carry data.

    R-02 remediation: a ConnectionError / TimeoutError from the pubsub
    socket means the connection is dead. redis-py will attempt a
    blocking reconnect if we ask it for another message — on the sole
    gevent loop that stalls the whole process for up to 2x
    socket_connect_timeout. We therefore raise _ChannelDead here, so
    iter_location_events can yield a degraded frame and close instead
    of retrying on the hub.

    Both error families are caught: redis-py raises its OWN
    ConnectionError / TimeoutError classes (subclasses of RedisError,
    NOT of the builtins) on every socket failure, and the builtins
    cover any raw OSError path that escapes unwrapped.
    """
    try:
        msg = get_message(timeout=timeout)
    except (RedisConnectionError, RedisTimeoutError,
            ConnectionError, TimeoutError, OSError) as exc:
        raise _ChannelDead(str(exc)) from exc
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
