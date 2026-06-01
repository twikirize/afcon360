"""
app/models/analytics.py

SQLAlchemy model for aggregated page-view analytics.

This table is written ONLY by AnalyticsService.flush_hourly_to_db().
It is never written per-request — that's the whole point.

Storage math (worst case, all 10 modules × 24 h/day × 365 days):
  10 × 24 × 365 = 87 600 rows/year
  At ~200 bytes/row ≈ 17 MB/year
  After 5 years: ~85 MB total.  Trivially small.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, Integer, String, UniqueConstraint
)
from app.extensions import db


class PageViewAggregate(db.Model):
    """
    Hourly (and daily, monthly) aggregated page-view counts per module.

    Retention policy:
      - Hourly rows: keep 90 days, then DELETE (handled by a nightly cron)
      - Daily rollup rows: keep 2 years
      - Monthly rollup rows: keep indefinitely (a few KB/year)

    The nightly cleanup query:
        DELETE FROM analytics_page_views
        WHERE period_type = 'hour'
          AND period_start < NOW() - INTERVAL '90 days';
    """

    __tablename__ = "analytics_page_views"

    id = Column(BigInteger, primary_key=True)

    # Which module was visited: 'wallet', 'tourism', 'transport', …
    module = Column(String(50), nullable=False, index=True)

    # Start of the aggregation window (UTC, truncated to the hour/day/month)
    period_start = Column(DateTime(timezone=True), nullable=False)

    # Granularity: 'hour' | 'day' | 'month'
    period_type = Column(String(10), nullable=False)

    # Raw view counter (sum of all requests in the window)
    view_count = Column(Integer, nullable=False, default=0)

    # Approximate unique users (from HyperLogLog pfcount)
    unique_users = Column(Integer, nullable=False, default=0)

    # Written at flush time
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Fast range queries: "wallet views last 30 days"
        Index("ix_apv_module_period", "module", "period_start", "period_type"),
        # Fast time-range scans for cleanup job
        Index("ix_apv_period_start", "period_start"),
        # Prevent duplicate flushes if cron runs twice in a window
        UniqueConstraint("module", "period_start", "period_type", name="uq_apv_module_period"),
    )

    def __repr__(self):
        return (
            f"<PageViewAggregate {self.module} "
            f"{self.period_type}:{self.period_start:%Y-%m-%d %H:00} "
            f"views={self.view_count}>"
        )
