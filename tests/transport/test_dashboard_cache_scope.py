"""S-16 behavioral proof: admin dashboard cache is scope-isolated.

The global key let org-scoped admins receive the platform-wide
dashboard from cache. The scope parameter partitions the cache; the
default ("global") preserves the existing single caller.
"""
from unittest.mock import patch

from app.transport.services.dashboard_service import DashboardService


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, timeout=None):
        self.store[key] = value


def _service_with_fake_cache():
    fake = FakeCache()
    svc = DashboardService()
    return svc, fake


def test_default_scope_returns_dict_and_caches():
    svc, fake = _service_with_fake_cache()
    calls = []

    def fresh_context():
        context = {"marker": len(calls)}
        calls.append(context)
        return context

    with patch(
        "app.transport.services.dashboard_service.cache", fake
    ), patch.object(
        DashboardService, "get_admin_dashboard_context", side_effect=fresh_context
    ):
        first = svc.get_cached_admin_dashboard()
        assert isinstance(first, dict)
        second = svc.get_cached_admin_dashboard()
        assert second is first, "same scope must hit the cache"
        assert len(calls) == 1, "context built more than once for one scope"


def test_distinct_scopes_do_not_share_entries():
    svc, fake = _service_with_fake_cache()

    def fresh_context():
        return {"marker": len(fake.store)}

    with patch(
        "app.transport.services.dashboard_service.cache", fake
    ), patch.object(
        DashboardService, "get_admin_dashboard_context", side_effect=fresh_context
    ):
        glob = svc.get_cached_admin_dashboard()
        org = svc.get_cached_admin_dashboard(scope="org:123")
        assert org is not glob, "org scope must not receive the global entry"
        assert set(fake.store.keys()) == {
            f"{svc.CACHE_KEY}:global",
            f"{svc.CACHE_KEY}:org:123",
        }
