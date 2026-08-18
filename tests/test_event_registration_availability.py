from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from app.events.services import EventService


class FakeColumn:
    def __eq__(self, other):
        return self

    def in_(self, values):
        return self


class FakeQuery:
    def __init__(self, counts):
        self.counts = iter(counts)

    def filter(self, *criteria):
        return self

    def count(self):
        return next(self.counts)


class FakeRegistration:
    event_id = FakeColumn()
    ticket_type_id = FakeColumn()
    status = FakeColumn()


class FakeTicket:
    def __init__(self, ticket_id=1, capacity=100):
        self.id = ticket_id
        self.name = "General"
        self.description = ""
        self.price = 0
        self.capacity = capacity
        self.is_active = True
        self.available_from = None
        self.available_until = None


class FakeEvent:
    def __init__(self, **values):
        self.id = 1
        self.public_id = "event-public-id"
        self.slug = values.get("slug", "availability-event")
        self.status = values.get("status", "published")
        self.registration_required = values.get("registration_required", True)
        self.start_date = values["start_date"]
        self.end_date = values["end_date"]
        self.max_capacity = values.get("max_capacity", 100)
        self.registration_opens_at = values.get("registration_opens_at")
        self.registration_closes_at = values.get("registration_closes_at")
        self.currency = "USD"
        self.ticket_types = [FakeTicket(capacity=values.get("ticket_capacity", 100))]


class TestEventRegistrationAvailability(unittest.TestCase):
    """Regression coverage for the public registration state contract."""

    def setUp(self):
        self.registration_counts = [0, 0]

    def tearDown(self):
        pass

    def make_event(self, **overrides):
        now = datetime.now(timezone.utc)
        values = {
            "slug": "availability-event",
            "status": "published",
            "registration_required": True,
            "start_date": (now + timedelta(days=1)).date(),
            "end_date": (now + timedelta(days=2)).date(),
            "max_capacity": 100,
            "registration_opens_at": now - timedelta(days=1),
            "registration_closes_at": now + timedelta(days=1),
        }
        values.update(overrides)
        return FakeEvent(**values), FakeTicket()

    def availability(self, event, now):
        with patch.object(
            EventService,
            "_get_registration_class",
            return_value=type("Registration", (), {
                "event_id": FakeColumn(),
                "ticket_type_id": FakeColumn(),
                "status": FakeColumn(),
                "query": FakeQuery(self.registration_counts),
            }),
        ):
            return EventService.get_registration_availability(
                event, now=now, use_cache=False
            )

    def test_registration_is_not_open_before_opening_time(self):
        now = datetime.now(timezone.utc)
        event, _ = self.make_event(registration_opens_at=now + timedelta(hours=2))

        snapshot = self.availability(event, now)

        self.assertEqual(snapshot["state"], "not_open")
        self.assertFalse(snapshot["is_sold_out"])

    def test_registration_is_open_for_a_live_event(self):
        now = datetime.now(timezone.utc)
        event, _ = self.make_event(
            start_date=now.date(),
            end_date=(now + timedelta(days=1)).date(),
        )

        snapshot = self.availability(event, now)

        self.assertEqual(snapshot["state"], "open")
        self.assertEqual(snapshot["event_phase"], "live")

    def test_registration_closes_at_explicit_deadline(self):
        now = datetime.now(timezone.utc)
        event, _ = self.make_event(registration_closes_at=now - timedelta(minutes=1))

        snapshot = self.availability(event, now)

        self.assertEqual(snapshot["state"], "closed")
        self.assertEqual(snapshot["reason"], "registration_deadline")

    def test_expired_event_has_precedence_over_open_window(self):
        now = datetime.now(timezone.utc)
        event, _ = self.make_event(
            start_date=(now - timedelta(days=3)).date(),
            end_date=(now - timedelta(days=1)).date(),
            registration_closes_at=now + timedelta(days=1),
        )

        snapshot = self.availability(event, now)

        self.assertEqual(snapshot["state"], "expired")
        self.assertEqual(snapshot["event_phase"], "expired")

    def test_event_capacity_returns_sold_out(self):
        now = datetime.now(timezone.utc)
        event, _ = self.make_event(max_capacity=1, slug="sold-out-event")
        self.registration_counts = [1, 0]

        snapshot = self.availability(event, now)

        self.assertEqual(snapshot["state"], "sold_out")
        self.assertEqual(snapshot["remaining_capacity"], 0)

    def test_registration_deadline_defaults_to_event_start(self):
        now = datetime.now(timezone.utc)
        event, _ = self.make_event(
            registration_closes_at=None,
            start_date=now.date(),
        )

        snapshot = self.availability(event, now)

        self.assertEqual(snapshot["state"], "closed")
        self.assertIsNotNone(snapshot["closes_at"])


if __name__ == "__main__":
    unittest.main()