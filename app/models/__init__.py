"""
app/models/ — Shared, domain-agnostic models.

This package holds models that don't belong to any single business domain:
aggregated analytics, platform configuration, and theming.

----------------------------------------------------------------------------
REGISTRATION CONTRACT — READ BEFORE ADDING A MODEL
----------------------------------------------------------------------------
Unlike app.<domain>.models (whose modules are imported explicitly by
app.core.model_registry.register_all_models()), this package is imported
as a whole:  `from app import models`.  That means the classes imported
in THIS FILE are the classes Alembic sees.

If a model lives in app/models/ but is not imported below, `flask db
migrate` will not detect it, and a fresh database will not have its
table.  The failure is silent: the model works at runtime against an
already-existing table but breaks on a clean install.  Keep this file
in sync with the folder — that is the only maintenance obligation
Option A imposes, and it's the right one because the file sits in the
directory you're already editing.

Adding a new shared model:
    1. Create app/models/<name>.py with your SQLAlchemy model class.
    2. Add `from app.models.<name> import <ClassName>` below.
    3. Run `flask db migrate` — the CREATE TABLE should appear in the diff.

----------------------------------------------------------------------------
FILES IN THIS PACKAGE
----------------------------------------------------------------------------
analytics.py       PageViewAggregate    hourly/daily page-view rollups
system_config.py   SystemConfig         key/value platform configuration
theme.py           GlobalTheme, UserThemePreference, EventTheme
base.py            BaseModel, TimestampMixin, ProtectedModel (abstract)

DELIBERATELY NOT HERE
---------------------
audit.py — retired. The canonical audit model is app.audit.models.AuditLog
(table `audit_logs`); app/models/audit.ActivityLog was merged into it on
2026-10-24 (log_instance() + read-only aliases) and the file deleted.
Do not reintroduce a parallel audit model in this package.

notification.py — backward-compatibility re-exports of
app.notifications.models.  The canonical models live there and are
registered via that package's own boot import; re-exporting here would
be redundant.  The shim file is kept only so existing imports keep
working.
"""

# --- Aggregated analytics ---------------------------------------------------
# Written only by AnalyticsService.flush_hourly_to_db(); never per-request.
# This is the model that motivated creating this file — it was invisible to
# Alembic autogenerate until the package was imported from the registry.
from app.models.analytics import PageViewAggregate  # noqa: F401

# --- Platform configuration -------------------------------------------------
# Also loaded elsewhere in the boot path (the `system_configs` table has
# 98 rows in Phase 1), but importing here makes this file authoritative as
# the package index and guarantees registration from a cold start.  The
# duplicate import is a no-op — the class is the same object.
from app.models.system_config import SystemConfig  # noqa: F401

# --- Theming ----------------------------------------------------------------
# FK to events.id is resolved lazily at mapper-config time, so ordering
# relative to app.events.models does not matter here.
from app.models.theme import (  # noqa: F401
    EventTheme,
    GlobalTheme,
    UserThemePreference,
)

__all__ = [
    "PageViewAggregate",
    "SystemConfig",
    "EventTheme",
    "GlobalTheme",
    "UserThemePreference",
]
