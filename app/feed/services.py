"""
AFCON360 FeedService

Aggregates content from across the platform into a unified feed:
  - Posts (user/org/system published content)
  - Events (published, upcoming)
  - Advertisements (active, approved, placement=home_feed)
  - System notifications (platform announcements, "how to use" guides)
  - Accommodation highlights (recently approved properties)
  - Transport routes (scheduled routes)

Produces a list of unified feed-item dicts with a consistent schema so the
template can render any type with a single card renderer.

Scoring: "orderly but randomly" — items are scored by priority + recency +
a seeded random factor so the feed looks fresh on each page load but
pagination stays stable within a session (the seed is passed to the client).
"""

import hashlib
import logging
import random
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

from app.extensions import db

logger = logging.getLogger(__name__)


def _seeded_random(seed: str, key: str) -> float:
    """Deterministic 0-1 float from a seed + key, so pagination is stable."""
    h = hashlib.md5(f"{seed}:{key}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _recency_bonus(created_at: datetime) -> float:
    """Higher score for newer items. Decays over ~7 days."""
    if not created_at:
        return 0
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_hours = (now - created_at).total_seconds() / 3600
    # 100 points at age=0, decaying to 0 after ~7 days (168 hours)
    return max(0, 100 * (1 - age_hours / 168))


class FeedService:
    """Unified feed aggregation service."""

    # ── Public API ────────────────────────────────────────────────

    @classmethod
    def get_feed(
        cls,
        page: int = 1,
        per_page: int = 10,
        layout: Optional[str] = None,
        seed: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Return a paginated slice of the unified feed.

        Returns:
            {
                'items': [...],    # list of feed-item dicts
                'page': int,
                'per_page': int,
                'has_more': bool,
                'layout': str,
                'seed': str,
            }
        """
        if seed is None:
            seed = str(random.randint(100000, 999999))

        try:
            all_items = cls._collect_all(user_id=user_id)
        except Exception as e:
            logger.warning(f"FeedService.get_feed failed: {e}")
            all_items = []
            try:
                db.session.rollback()
            except Exception:
                pass

        # Score and sort
        for item in all_items:
            item["_score"] = (
                item.get("priority", 0) * 100
                + _recency_bonus(item.get("created_at"))
                + _seeded_random(seed, item["feed_id"]) * 30
            )
            if item.get("is_pinned"):
                item["_score"] += 10000

        all_items.sort(key=lambda x: x["_score"], reverse=True)

        # Paginate
        total = len(all_items)
        start = (page - 1) * per_page
        end = start + per_page
        page_items = all_items[start:end]

        # Strip internal keys
        for item in page_items:
            item.pop("_score", None)

        return {
            "items": page_items,
            "page": page,
            "per_page": per_page,
            "has_more": end < total,
            "layout": layout or "mixed",
            "seed": seed,
        }

    @classmethod
    def get_sidebar_ads(cls, placement: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Active advertisements for a sidebar placement.

        Returns an empty list if none exist (template falls back to placeholders).
        """
        try:
            from app.feed.models import Advertisement

            now = datetime.now(timezone.utc)
            query = Advertisement.query.filter(
                Advertisement.is_deleted.is_(False),
                Advertisement.status == "active",
                Advertisement.placement == placement,
                db.or_(
                    Advertisement.start_date.is_(None),
                    Advertisement.start_date <= now,
                ),
                db.or_(
                    Advertisement.end_date.is_(None),
                    Advertisement.end_date >= now,
                ),
            ).order_by(
                Advertisement.priority.desc(),
            ).limit(limit)

            ads = query.all()
            return [cls._ad_to_item(a) for a in ads]
        except Exception as e:
            logger.warning(f"FeedService.get_sidebar_ads failed: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass
            return []

    # ── Collection (private) ──────────────────────────────────────

    @classmethod
    def _collect_all(cls, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Query every content source and merge into one list."""
        items: List[Dict[str, Any]] = []

        # Each collector is isolated — one failing source must not break the feed.
        # In PostgreSQL, a failed query aborts the transaction, so we rollback
        # after each failure to restore a clean session for the next collector.
        for collector in (
            cls._collect_posts,
            cls._collect_events,
            cls._collect_feed_ads,
            cls._collect_system_updates,
            cls._collect_accommodation,
            cls._collect_transport,
        ):
            try:
                items.extend(collector(user_id=user_id))
            except Exception as e:
                logger.warning(f"Feed collector {collector.__name__} failed: {e}")
                try:
                    db.session.rollback()
                except Exception:
                    pass

        return items

    @classmethod
    def _collect_posts(cls, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        from app.feed.models import Post

        query = Post.query.filter(
            Post.is_deleted.is_(False),
            Post.status == "published",
            Post.visibility == "public",
        ).order_by(Post.created_at.desc()).limit(15)

        posts = query.all()
        return [cls._post_to_item(p) for p in posts]

    @classmethod
    def _collect_events(cls, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        from app.events.models import Event
        from app.events.constants import EventStatus

        query = Event.query.filter(
            Event.is_deleted.is_(False),
            Event.status == EventStatus.PUBLISHED.value,
        ).order_by(Event.start_date.asc()).limit(8)

        events = query.all()
        return [cls._event_to_item(e) for e in events]

    @classmethod
    def _collect_feed_ads(cls, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        from app.feed.models import Advertisement

        now = datetime.now(timezone.utc)
        query = Advertisement.query.filter(
            Advertisement.is_deleted.is_(False),
            Advertisement.status == "active",
            Advertisement.placement == "home_feed",
            db.or_(
                Advertisement.start_date.is_(None),
                Advertisement.start_date <= now,
            ),
            db.or_(
                Advertisement.end_date.is_(None),
                Advertisement.end_date >= now,
            ),
        ).order_by(Advertisement.priority.desc()).limit(5)

        ads = query.all()
        return [cls._ad_to_item(a) for a in ads]

    @classmethod
    def _collect_system_updates(cls, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Platform announcements / 'how to use the system' notifications.

        Queries system-wide notifications (user_id is NULL) that are either
        module=system or type=platform_announcement. The is_read flag is
        per-user, so on the public feed we show all system-wide announcements
        regardless of read state.
        """
        from app.notifications.models import Notification

        query = Notification.query.filter(
            Notification.is_deleted.is_(False),
            Notification.user_id.is_(None),  # system-wide, not per-user
            db.or_(
                Notification.module == "system",
                Notification.type == "platform_announcement",
            ),
        ).order_by(Notification.created_at.desc()).limit(5)

        notifs = query.all()
        return [cls._notification_to_item(n) for n in notifs]

    @classmethod
    def _collect_accommodation(cls, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        from app.accommodation.models.property import Property

        query = Property.query.filter(
            Property.is_deleted.is_(False),
            Property.status.in_(["approved", "active", "published"]),
            Property.visibility == "public",
        ).order_by(Property.created_at.desc()).limit(5)

        properties = query.all()
        return [cls._property_to_item(p) for p in properties]

    @classmethod
    def _collect_transport(cls, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        from app.transport.models import ScheduledRoute

        query = ScheduledRoute.query.filter(
            ScheduledRoute.is_deleted.is_(False),
            ScheduledRoute.is_active.is_(True),
        ).order_by(ScheduledRoute.created_at.desc()).limit(5)

        routes = query.all()
        return [cls._route_to_item(r) for r in routes]

    # ── Converters (model → unified feed-item dict) ───────────────

    @classmethod
    def _post_to_item(cls, post) -> Dict[str, Any]:
        return {
            "feed_id": f"post_{post.id}",
            "type": "post",
            "title": (post.link_title or "") if post.link_title else "",
            "body": post.body or "",
            "image_url": post.media_url or "",
            "link_url": post.link_url or "",
            "author_name": cls._author_name(post),
            "author_avatar": "",
            "source_module": post.source_module or "system",
            "metadata": {
                "likes": post.likes_count or 0,
                "comments": post.comments_count or 0,
            },
            "created_at": post.created_at,
            "priority": 8 if post.is_pinned else 3,
            "is_pinned": post.is_pinned,
        }

    @classmethod
    def _event_to_item(cls, event) -> Dict[str, Any]:
        return {
            "feed_id": f"event_{event.id}",
            "type": "event",
            "title": event.name or "",
            "body": (event.description or "")[:300],
            "image_url": "",
            "link_url": f"/events/{event.slug}" if event.slug else "",
            "author_name": "AFCON360 Events",
            "author_avatar": "",
            "source_module": "events",
            "metadata": {
                "start_date": event.start_date.isoformat() if event.start_date else None,
                "end_date": event.end_date.isoformat() if event.end_date else None,
                "city": event.city or "",
                "country": event.country or "",
                "venue": event.venue or "",
                "category": event.category or "general",
                "featured": bool(event.featured),
                "registration_fee": str(event.registration_fee) if event.registration_fee else None,
                "currency": event.currency or "USD",
            },
            "created_at": event.created_at,
            "priority": 7 if event.featured else 5,
            "is_pinned": False,
        }

    @classmethod
    def _ad_to_item(cls, ad) -> Dict[str, Any]:
        return {
            "feed_id": f"ad_{ad.id}",
            "type": "ad",
            "title": ad.title or "",
            "body": ad.description or "",
            "image_url": ad.image_url or "",
            "link_url": ad.link_url or "",
            "author_name": ad.advertiser_name or "Sponsored",
            "author_avatar": "",
            "source_module": ad.source_module or "system",
            "metadata": {
                "ad_type": ad.ad_type,
                "placement": ad.placement,
                "priority": ad.priority,
            },
            "created_at": ad.created_at,
            "priority": (ad.priority or 5) + 2,
            "is_pinned": False,
        }

    @classmethod
    def _notification_to_item(cls, notif) -> Dict[str, Any]:
        from app.notifications.models import MODULE_LABELS, MODULE_ICONS

        return {
            "feed_id": f"sys_{notif.id}",
            "type": "system_update",
            "title": notif.subject or (notif.type.replace("_", " ").title() if notif.type else ""),
            "body": (notif.body or "")[:400],
            "image_url": "",
            "link_url": notif.link or "",
            "author_name": "AFCON360",
            "author_avatar": "",
            "source_module": notif.module or "system",
            "metadata": {
                "module_label": MODULE_LABELS.get(notif.module, "System"),
                "module_icon": MODULE_ICONS.get(notif.module, "bi-bell"),
            },
            "created_at": notif.created_at,
            "priority": 6,
            "is_pinned": getattr(notif, "is_important", False),
        }

    @classmethod
    def _property_to_item(cls, prop) -> Dict[str, Any]:
        return {
            "feed_id": f"prop_{prop.id}",
            "type": "property",
            "title": prop.title or "",
            "body": (prop.summary or prop.description or "")[:300],
            "image_url": "",
            "link_url": f"/accommodation/{prop.slug}" if prop.slug else "",
            "author_name": "Accommodation",
            "author_avatar": "",
            "source_module": "accommodation",
            "metadata": {
                "property_type": prop.property_type or "",
                "city": prop.city or "",
                "country": prop.country or "",
                "price_per_night": str(prop.base_price_per_night) if prop.base_price_per_night else None,
            },
            "created_at": prop.created_at,
            "priority": 4,
            "is_pinned": False,
        }

    @classmethod
    def _route_to_item(cls, route) -> Dict[str, Any]:
        return {
            "feed_id": f"route_{route.id}",
            "type": "transport",
            "title": route.name or "",
            "body": (route.description or "")[:300],
            "image_url": "",
            "link_url": "/transport/",
            "author_name": "Transport",
            "author_avatar": "",
            "source_module": "transport",
            "metadata": {
                "route_type": route.route_type or "",
                "primary_zone": route.primary_zone or "",
                "price_per_seat": str(route.price_per_seat) if route.price_per_seat else None,
                "available_seats": route.available_seats or 0,
            },
            "created_at": route.created_at,
            "priority": 4,
            "is_pinned": False,
        }

    # ── Helpers ────────────────────────────────────────────────────

    @classmethod
    def _author_name(cls, post) -> str:
        if post.author_type == "system":
            return "AFCON360"
        if post.author_id:
            try:
                from app.identity.models.user import User

                user = User.query.filter_by(id=post.author_id).first()
                if user:
                    return user.username or user.email or "User"
            except Exception:
                pass
        return "User"
