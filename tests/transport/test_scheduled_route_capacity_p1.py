"""PICKUP-TIME-AUTHORITY-P1 — scheduled-route capacity runtime regression.

``ScheduledRoute.can_accommodate`` used ``func.sum`` while the only
``func`` import was local to the adjacent ``update_availability`` method,
so the admin route-assign path raised ``NameError: name 'func' is not
defined``. This proves the capacity query builds and executes.
"""
import uuid

from app.extensions import db
from app.transport.models import ScheduledRoute


def _create_route(app, capacity=4):
    with app.app_context():
        route = ScheduledRoute(
            provider_type="individual_driver",
            provider_id=1,
            name="P1 capacity route",
            route_type="shuttle",
            route_code=f"P1CAP-{uuid.uuid4().hex[:8].upper()}",
            schedule_pattern={"frequency": "daily"},
            stops=[{"name": "A"}, {"name": "B"}],
            vehicle_capacity=capacity,
        )
        db.session.add(route)
        db.session.commit()
        return route.id


class TestScheduledRouteCapacity:

    def test_can_accommodate_executes_capacity_query(self, app):
        route_id = _create_route(app, capacity=4)
        with app.app_context():
            route = db.session.get(ScheduledRoute, route_id)
            assert route.can_accommodate(2) is True
            assert route.can_accommodate(5) is False
