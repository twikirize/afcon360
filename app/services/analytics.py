"""
app/services/analytics.py

AFCON360 Analytics Service
===========================
Lightweight page-view and conversion tracking built on Redis.

Architecture (as agreed):
  Browser/Route  →  Redis counters (real-time, 48 h TTL on hourly buckets)
                 →  PostgreSQL aggregates (hourly flush via Celery / cron)
                 →  Monthly rollups kept indefinitely

What this is NOT:
  - Not a security/forensic audit log  (use ForensicAuditService for that)
  - Not a per-request event store       (that was the original mistake)
  - Not a session replay tool

What this IS:
  - Cheap, fast aggregate counters      (Redis INCR ≈ 0.1 ms)
  - HyperLogLog unique-user estimates   (12 KB of memory regardless of scale)
  - Conversion funnel hooks             (view → book → pay)
  - An AFCON match-day spike absorber   (Redis handles millions/sec; Postgres sees ~24 rows/module/day)
"""

from __future__ import annotations

import json
import random
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Optional

from flask import current_app, request, has_request_context
from flask_login import current_user

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Redis client (lazy, thread-safe via flask g or module-level singleton)
# ──────────────────────────────────────────────────────────────────────────────

_redis_client = None  # module-level singleton; reset in tests


def _get_redis():
    """
    Return a Redis connection.

    Uses the app's existing Redis config so we don't introduce a second
    connection pool.  Falls back gracefully if Redis is unavailable —
    analytics failures must NEVER affect the user request.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis  # noqa: PLC0415
        _redis_client = redis.Redis(
            host=current_app.config.get("REDIS_HOST", "localhost"),
            port=int(current_app.config.get("REDIS_PORT", 6379)),
            db=int(current_app.config.get("REDIS_ANALYTICS_DB", 1)),  # separate DB from session/cache
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=0.5,
        )
        _redis_client.ping()  # fail fast at startup, not mid-request
        return _redis_client
    except Exception as exc:
        logger.warning("AnalyticsService: Redis unavailable (%s). Tracking disabled.", exc)
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Valid modules (guards against typos leaking into Redis keys)
# ──────────────────────────────────────────────────────────────────────────────

KNOWN_MODULES = frozenset({
    "dashboard",
    "wallet",
    "transport",
    "accommodation",
    "tourism",
    "tournament",
    "events",
    "profile",
    "kyc",
})

# ──────────────────────────────────────────────────────────────────────────────
# TTLs
# ──────────────────────────────────────────────────────────────────────────────

TTL_HOURLY = 172_800      # 48 h  — hourly buckets flushed to Postgres before expiry
TTL_DAILY = 2_592_000     # 30 d  — daily totals kept in Redis for dashboards
TTL_SAMPLE = 604_800      # 7 d   — 1 % metadata samples for debug

SAMPLE_RATE = 0.01        # 1 % metadata sampling


# ──────────────────────────────────────────────────────────────────────────────
# Core service
# ──────────────────────────────────────────────────────────────────────────────

class AnalyticsService:
    """
    Stateless analytics helper.  All methods are class-methods so callers
    don't need to instantiate anything:

        AnalyticsService.track_page_view("wallet")
        AnalyticsService.track_conversion("wallet", "deposit_completed")
    """

    # ── Public API ────────────────────────────────────────────────────────────

    @classmethod
    def track_page_view(
        cls,
        module: str,
        user_id: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Record one page view for *module*.

        Safe to call from any Flask route.  If Redis is down the error is
        swallowed so the page still loads.

        Args:
            module:   One of KNOWN_MODULES (e.g. "wallet", "tourism").
            user_id:  Internal BIGINT user id.  Auto-resolved from
                      current_user if omitted.
            metadata: Optional dict stored in a sampled debug list (1 % of
                      requests, 7-day TTL, capped at 1 000 entries).
        """
        if not cls._is_enabled():
            return

        module = cls._validate_module(module)
        if module is None:
            return

        # Resolve user id without crashing when called outside request context
        uid = cls._resolve_user_id(user_id)

        r = _get_redis()
        if r is None:
            return

        try:
            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y%m%d")
            hour_str = now.strftime("%Y%m%d%H")

            pipe = r.pipeline(transaction=False)  # fire-and-forget pipeline

            # 1. Hourly counter  →  flushed to Postgres and deleted each hour
            h_key = f"pv:h:{module}:{hour_str}"
            pipe.incr(h_key)
            pipe.expire(h_key, TTL_HOURLY)

            # 2. Daily counter  →  30-day rolling window for live dashboards
            d_key = f"pv:d:{module}:{date_str}"
            pipe.incr(d_key)
            pipe.expire(d_key, TTL_DAILY)

            # 3. Unique users via HyperLogLog  (~12 KB regardless of cardinality)
            if uid:
                uu_key = f"uu:{module}:{date_str}"
                pipe.pfadd(uu_key, uid)
                pipe.expire(uu_key, TTL_DAILY)

            pipe.execute()

            # 4. 1 % metadata sample (separate, not in pipeline to avoid noise)
            if metadata and random.random() < SAMPLE_RATE:
                cls._store_sample(r, module, date_str, uid, metadata)

        except Exception as exc:
            logger.debug("AnalyticsService.track_page_view error: %s", exc)

    @classmethod
    def track_conversion(
        cls,
        module: str,
        event: str,
        user_id: Optional[int] = None,
    ) -> None:
        """
        Record a conversion event (e.g. ticket purchased, transport booked).

        Call this AFTER the transaction is committed so you don't count
        abandoned checkouts.

        Args:
            module: Module name (e.g. "wallet").
            event:  Conversion type.  Use snake_case constants:
                    "deposit_completed", "ticket_purchased",
                    "transport_booked", "accommodation_booked".
            user_id: Internal BIGINT user id.
        """
        if not cls._is_enabled():
            return

        module = cls._validate_module(module)
        if module is None:
            return

        uid = cls._resolve_user_id(user_id)
        r = _get_redis()
        if r is None:
            return

        try:
            today = datetime.now(timezone.utc).strftime("%Y%m%d")

            pipe = r.pipeline(transaction=False)

            # Conversion count
            cv_key = f"cv:{module}:{event}:{today}"
            pipe.incr(cv_key)
            pipe.expire(cv_key, TTL_DAILY)

            # Unique converting users
            if uid:
                uv_key = f"ucv:{module}:{event}:{today}"
                pipe.pfadd(uv_key, uid)
                pipe.expire(uv_key, TTL_DAILY)

            pipe.execute()

        except Exception as exc:
            logger.debug("AnalyticsService.track_conversion error: %s", exc)

    @classmethod
    def get_realtime_stats(cls, module: str, date: Optional[str] = None) -> dict:
        """
        Return live Redis stats for *module* on *date* (YYYYMMDD, default today).

        Used by the admin dashboard to show live activity.
        Returns zeroed dict if Redis unavailable — never raises.
        """
        empty = {"views_today": 0, "unique_users_today": 0, "views_this_hour": 0}

        module = cls._validate_module(module)
        if module is None:
            return empty

        r = _get_redis()
        if r is None:
            return empty

        try:
            now = datetime.now(timezone.utc)
            date = date or now.strftime("%Y%m%d")
            hour_str = now.strftime("%Y%m%d%H")

            return {
                "views_today": int(r.get(f"pv:d:{module}:{date}") or 0),
                "views_this_hour": int(r.get(f"pv:h:{module}:{hour_str}") or 0),
                "unique_users_today": r.pfcount(f"uu:{module}:{date}"),
            }
        except Exception as exc:
            logger.debug("AnalyticsService.get_realtime_stats error: %s", exc)
            return empty

    @classmethod
    def get_realtime_overview(cls) -> dict:
        """
        Aggregate stats across all known modules for the admin overview panel.
        """
        r = _get_redis()
        if r is None:
            return {}

        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        result = {}
        for mod in KNOWN_MODULES:
            try:
                result[mod] = {
                    "views": int(r.get(f"pv:d:{mod}:{today}") or 0),
                    "unique_users": r.pfcount(f"uu:{mod}:{today}"),
                }
            except Exception:
                result[mod] = {"views": 0, "unique_users": 0}
        return result

    # ── Aggregation (called by Celery beat or cron every hour) ───────────────

    @classmethod
    def flush_hourly_to_db(cls) -> dict:
        """
        Flush the PREVIOUS hour's Redis counters into the ``analytics_page_views``
        Postgres table, then DELETE the Redis keys.

        Schedule this every hour, e.g. in Celery:
            @celery.on_after_finalize.connect
            def setup_periodic(sender, **kwargs):
                sender.add_periodic_task(3600.0, flush_analytics_task.s())

        Or via cron:
            0 * * * *  cd /srv/afcon360 && flask analytics flush-hourly

        Returns a summary dict for logging.
        """
        from app.extensions import db  # local import — avoids circular deps
        from app.models.analytics import PageViewAggregate  # see migration below

        r = _get_redis()
        if r is None:
            return {"error": "redis_unavailable"}

        from datetime import timedelta
        now = datetime.now(timezone.utc)
        prev_hour = now - timedelta(hours=1)
        hour_str = prev_hour.strftime("%Y%m%d%H")
        date_str = prev_hour.strftime("%Y%m%d")
        period_start = prev_hour.replace(minute=0, second=0, microsecond=0)

        flushed = 0
        errors = 0

        for module in KNOWN_MODULES:
            h_key = f"pv:h:{module}:{hour_str}"
            uu_key = f"uu:{module}:{date_str}"

            try:
                view_count = int(r.get(h_key) or 0)
                if view_count == 0:
                    continue  # Don't write zero rows

                unique_users = r.pfcount(uu_key)  # approximate, but good enough

                row = PageViewAggregate(
                    module=module,
                    period_start=period_start,
                    period_type="hour",
                    view_count=view_count,
                    unique_users=unique_users,
                )
                db.session.add(row)
                r.delete(h_key)  # only delete AFTER successful DB add
                flushed += 1

            except Exception as exc:
                logger.error("AnalyticsService flush error for %s: %s", module, exc)
                errors += 1

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.error("AnalyticsService flush commit failed: %s", exc)
            return {"flushed": 0, "errors": errors + 1}

        return {"flushed": flushed, "errors": errors, "hour": hour_str}

    # ── Private helpers ───────────────────────────────────────────────────────

    @classmethod
    def _is_enabled(cls) -> bool:
        try:
            return current_app.config.get("ANALYTICS_ENABLED", True)
        except RuntimeError:
            return False  # Outside app context

    @classmethod
    def _validate_module(cls, module: str) -> Optional[str]:
        m = module.lower().strip()
        if m not in KNOWN_MODULES:
            logger.warning("AnalyticsService: unknown module '%s' ignored.", module)
            return None
        return m

    @classmethod
    def _resolve_user_id(cls, explicit_id: Optional[int]) -> Optional[int]:
        if explicit_id is not None:
            return explicit_id
        try:
            if has_request_context() and current_user.is_authenticated:
                return current_user.id  # BIGINT — correct
        except Exception:
            pass
        return None

    @classmethod
    def _store_sample(cls, r, module: str, date_str: str, uid, metadata: dict):
        """Store a 1 % metadata sample for debugging — fire and forget."""
        try:
            sample = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "uid": uid,
                "ua": request.user_agent.string[:200] if has_request_context() else None,
                "ip": request.remote_addr if has_request_context() else None,
                **{k: str(v)[:100] for k, v in (metadata or {}).items()},
            }
            key = f"sample:{module}:{date_str}"
            r.lpush(key, json.dumps(sample))
            r.ltrim(key, 0, 999)   # keep last 1 000 samples max
            r.expire(key, TTL_SAMPLE)
        except Exception:
            pass  # samples are never critical


# ──────────────────────────────────────────────────────────────────────────────
# Decorator — drop-in for routes
# ──────────────────────────────────────────────────────────────────────────────

def track_view(module: str):
    """
    Route decorator that calls AnalyticsService.track_page_view automatically.

    Usage::

        @wallet_bp.route('/dashboard')
        @login_required
        @track_view('wallet')
        def wallet_dashboard():
            ...

    The decorator is a no-op if analytics is disabled or Redis is down.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            AnalyticsService.track_page_view(module)
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ──────────────────────────────────────────────────────────────────────────────
# Flask CLI commands  (flask analytics flush-hourly, flask analytics stats)
# ──────────────────────────────────────────────────────────────────────────────

def register_analytics_commands(app):
    """
    Call this in create_app() after registering blueprints::

        from app.services.analytics import register_analytics_commands
        register_analytics_commands(app)
    """
    import click  # noqa: PLC0415

    @app.cli.group("analytics")
    def analytics_cli():
        """AFCON360 analytics commands."""

    @analytics_cli.command("flush-hourly")
    def flush_hourly():
        """Flush last hour's Redis page-view counters to Postgres."""
        result = AnalyticsService.flush_hourly_to_db()
        click.echo(f"Flush result: {result}")

    @analytics_cli.command("stats")
    @click.argument("module", default="all")
    def show_stats(module):
        """Show today's live stats for MODULE (or 'all')."""
        if module == "all":
            overview = AnalyticsService.get_realtime_overview()
            click.echo("\nAFCON360 — Today's Analytics\n" + "=" * 40)
            for mod, data in sorted(overview.items()):
                click.echo(f"  {mod:20s}  views={data['views']:>6}  unique={data['unique_users']:>6}")
        else:
            stats = AnalyticsService.get_realtime_stats(module)
            click.echo(f"\n{module} stats: {stats}")