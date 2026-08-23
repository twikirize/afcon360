from pathlib import Path

import pytest


def test_event_favorite_api_is_registered_at_public_api_prefix():
    from flask import Flask
    from app.events import event_favorites_api_bp

    app = Flask(__name__)
    app.register_blueprint(event_favorites_api_bp)
    assert any(
        rule.rule == "/api/events/<public_id>/toggle-favorite"
        and "POST" in rule.methods
        for rule in app.url_map.iter_rules()
    )


def test_event_create_defaults_to_registration_for_the_visible_ticketing_flow():
    routes = Path("app/events/routes.py").read_text(encoding="utf-8-sig")

    assert "data['registration_required'] = 'registration_required' in request.form" not in routes
    assert "data.setdefault('registration_required', True)" in routes


def test_ticket_modal_and_registration_form_submit_normalized_ticket_data():
    edit_template = Path("templates/events/organizer/edit.html").read_text(encoding="utf-8-sig")
    register_template = Path("templates/events/attendee/register.html").read_text(encoding="utf-8-sig")
    list_template = Path("templates/events/public/list.html").read_text(encoding="utf-8-sig")
    service = Path("app/events/services.py").read_text(encoding="utf-8-sig")

    assert "capacity = 0 if capacity_value in (None, \"\") else int(capacity_value)" in service
    form_start = register_template.index('<form id="reg-form"')
    ticket_input = register_template.index('name="ticket_type_id"')
    assert form_start < ticket_input
    assert "name=\"capacity\"" in edit_template
    assert "let originalHTML = button.innerHTML;" in list_template
    assert "result.error || result.message" in list_template


def test_event_context_includes_confirmed_registration_count_for_ticket_types(monkeypatch):
    from types import SimpleNamespace

    from app.events.constants import EventStatus
    from app.events.services import EventService

    ticket_type = SimpleNamespace(
        id=7,
        name="General admission",
        description="",
        price=0,
        capacity=10,
        is_active=True,
        available_from=None,
        available_until=None,
        registrations=[
            SimpleNamespace(status="confirmed"),
            SimpleNamespace(status="pending_payment"),
            SimpleNamespace(status="cancelled"),
        ],
    )
    event = SimpleNamespace(
        id=3,
        slug="test-event-3rd",
        name="Test event",
        description="",
        category="sports",
        city="Kampala",
        country="Uganda",
        venue="Main stadium",
        start_date=None,
        end_date=None,
        currency="UGX",
        status=EventStatus.PUBLISHED.value,
        featured=False,
        event_metadata={},
        contact_email=None,
        contact_phone=None,
        website=None,
        max_capacity=100,
        registration_required=True,
        ticket_types=[ticket_type],
    )

    class RegistrationQuery:
        def filter(self, *criteria):
            return self

        def filter_by(self, **filters):
            return self

        def count(self):
            return 1

        def first(self):
            return None

    class QueryField:
        def __eq__(self, other):
            return self

        def in_(self, values):
            return self

    registration_model = SimpleNamespace(
        query=RegistrationQuery(),
        event_id=QueryField(),
        status=QueryField(),
        ticket_type_id=QueryField(),
    )

    monkeypatch.setattr(EventService, "get_event_model", lambda event_slug: event)
    monkeypatch.setattr(
        EventService,
        "_get_registration_class",
        lambda: registration_model,
    )

    context = EventService.build_event_context_json(event.slug)

    assert context["ticket_types"][0]["registration_count"] == 1
    assert context["ticket_types"][0]["remaining"] == 9


def test_public_event_listing_orders_newest_events_first(monkeypatch):
    from app.events.constants import EventStatus
    from app.events.services import EventService

    class SortColumn:
        def __init__(self, name):
            self.name = name

        def desc(self):
            return f"{self.name} DESC"

    class ListingQuery:
        def __init__(self):
            self.filters = None
            self.ordering = None

        def filter_by(self, **filters):
            self.filters = filters
            return self

        def order_by(self, *ordering):
            self.ordering = ordering
            return self

        def all(self):
            return [{"slug": "newest"}, {"slug": "older"}]

    query = ListingQuery()

    class FakeEvent:
        created_at = SortColumn("created_at")
        id = SortColumn("id")

    FakeEvent.query = query

    monkeypatch.setattr(EventService, "_get_event_model_class", lambda: FakeEvent)
    monkeypatch.setattr(EventService, "_event_to_dict", lambda event: event)

    events = EventService.get_all_events(status=EventStatus.PUBLISHED)

    assert query.filters == {"status": EventStatus.PUBLISHED.value}
    assert query.ordering == ("created_at DESC", "id DESC")
    assert events == [{"slug": "newest"}, {"slug": "older"}]


def test_event_expiry_is_inclusive_through_the_end_date():
    from datetime import date
    from types import SimpleNamespace

    from app.events.services import EventService

    event = SimpleNamespace(end_date=date(2026, 8, 15))

    assert EventService.is_event_expired(event, today=date(2026, 8, 15)) is False
    assert EventService.is_event_expired(event, today=date(2026, 8, 16)) is True


def test_expired_event_context_cannot_be_registered(monkeypatch):
    from datetime import date
    from types import SimpleNamespace

    from app.events.constants import EventStatus
    from app.events.services import EventService

    event = SimpleNamespace(
        id=3,
        slug="expired-event",
        name="Expired event",
        description="",
        category="sports",
        city="Kampala",
        country="Uganda",
        venue="Main stadium",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 14),
        currency="UGX",
        status=EventStatus.PUBLISHED.value,
        featured=False,
        event_metadata={},
        contact_email=None,
        contact_phone=None,
        website=None,
        max_capacity=100,
        ticket_types=[],
    )

    class RegistrationQuery:
        def filter(self, *criteria):
            return self

        def filter_by(self, **filters):
            return self

        def count(self):
            return 0

        def first(self):
            return None

    class QueryField:
        def __eq__(self, other):
            return self

        def in_(self, values):
            return self

    registration_model = SimpleNamespace(
        query=RegistrationQuery(),
        event_id=QueryField(),
        status=QueryField(),
        ticket_type_id=QueryField(),
    )

    monkeypatch.setattr(EventService, "get_event_model", lambda event_slug: event)
    monkeypatch.setattr(
        EventService,
        "_get_registration_class",
        lambda: registration_model,
    )

    context = EventService.build_event_context_json(
        event.slug,
        today=date(2026, 8, 15),
    )

    assert context["event_is_expired"] is True
    assert context["can_register"] is False


def test_registration_route_rejects_expired_events_and_template_blocks_duplicate_self_submission():
    from pathlib import Path

    routes = Path("app/events/routes.py").read_text(encoding="utf-8-sig")
    template = Path("templates/events/attendee/register.html").read_text(encoding="utf-8-sig")
    landing = Path("templates/events/public/landing.html").read_text(encoding="utf-8-sig")

    assert "event_is_expired" in routes
    assert "}), 410" in routes
    assert "user_registered=json_context.get('user_registered', False)" in routes
    assert "if booking_type == BookingType.SELF.value" in routes
    assert "user_registered" in template
    assert "type === 'self'" in template
    assert "Registration closed" in template
    assert "is_past_event" in landing
    assert "Event Ended" in landing


@pytest.mark.no_database
def test_past_event_landing_uses_a_recap_without_live_booking_actions():
    routes = Path("app/events/routes.py").read_text(encoding="utf-8-sig")
    landing = Path("templates/events/public/landing.html").read_text(encoding="utf-8-sig")

    assert "is_past_event = context.get('event_is_expired', False)" in routes
    assert "properties = [] if is_past_event else search_properties" in routes
    assert "{% if event.start_date and not is_past_event %}" in landing
    assert "{% if not is_past_event and current_user.is_authenticated %}" in landing
    assert "{% elif not can_register %}" in landing
    assert "Event Ended" in landing
    assert "event-recap" in landing
    assert "Accommodation near" not in landing.split("{% if is_past_event %}", 1)[-1].split("{% endif %}", 1)[0]


def test_free_ticket_purchase_does_not_require_wallet_activity(monkeypatch):
    from decimal import Decimal
    from types import SimpleNamespace
    import sys
    import types

    import importlib

    payments_package = types.ModuleType("app.wallet.payments")
    payments_package.__path__ = []
    mobile_money_module = types.ModuleType("app.wallet.payments.mobile_money")
    mobile_money_module.MobileMoneyService = object
    monkeypatch.setitem(sys.modules, "app.wallet.payments", payments_package)
    monkeypatch.setitem(sys.modules, "app.wallet.payments.mobile_money", mobile_money_module)

    payment_service_module = importlib.import_module("app.events.payment_service")
    from app.events.models import Event, TicketType
    from app.events.payment_service import EventPaymentService
    monkeypatch.setattr(
        "app.events.services.EventService._registration_gate_error",
        lambda event, ticket_type_id=None: None,
    )

    event = SimpleNamespace(id=41, currency="UGX", end_date=None)
    ticket_type = SimpleNamespace(
        id=42,
        event_id=event.id,
        price=Decimal("0.00"),
        capacity=0,
        available_seats=0,
    )

    class FakeSession:
        def get(self, model, identifier):
            if model is Event and identifier == event.id:
                return event
            if model is TicketType and identifier == ticket_type.id:
                return ticket_type
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

    class FakeWalletService:
        def __init__(self):
            raise AssertionError("Free registration must not initialize wallet services")

    wallet_calls = []
    monkeypatch.setattr(payment_service_module.db, "session", FakeSession())
    monkeypatch.setattr(payment_service_module, "WalletService", FakeWalletService)

    service = EventPaymentService()
    monkeypatch.setattr(
        service,
        "_process_wallet_payment",
        lambda *args: wallet_calls.append(("wallet", args)) or {"success": False},
    )
    monkeypatch.setattr(
        service,
        "_process_mobile_money_payment",
        lambda *args: wallet_calls.append(("mobile_money", args)) or {"success": False},
    )
    monkeypatch.setattr(
        service,
        "_create_registrations",
        lambda **kwargs: [{"registration_ref": "ER-FREE-0001"}],
    )

    for payment_method, payment_kwargs in (
        ("wallet", {}),
        ("mobile_money", {"mobile_money_operator": "mtn", "mobile_money_phone": "0700000000"}),
    ):
        result = service.process_ticket_purchase(
            user_id=7,
            event_id=event.id,
            ticket_type_id=ticket_type.id,
            quantity=0,
            payment_method=payment_method,
            create_primary_for_payer=False,
            **payment_kwargs,
        )

        assert result["success"] is True, result
        assert result["total_paid"] == 0.0

    refund_calls = []

    def fail_registration(**kwargs):
        raise RuntimeError("registration unavailable")

    monkeypatch.setattr(service, "_create_registrations", fail_registration)
    monkeypatch.setattr(
        service,
        "_refund_payment",
        lambda **kwargs: refund_calls.append(kwargs) or {"success": True},
    )
    failed_result = service.process_ticket_purchase(
        user_id=7,
        event_id=event.id,
        ticket_type_id=ticket_type.id,
        quantity=0,
        payment_method="wallet",
        create_primary_for_payer=False,
    )

    assert failed_result["success"] is False
    assert "registration unavailable" in failed_result["error"]
    assert wallet_calls == []
    assert refund_calls == []


def test_free_registration_has_no_wallet_transaction_reference(monkeypatch):
    from decimal import Decimal
    from types import SimpleNamespace

    import importlib

    payment_service_module = importlib.import_module("app.events.payment_service")
    from app.events.models import Event, TicketType
    from app.events.payment_service import EventPaymentService

    event = SimpleNamespace(id=51, slug="free-event")
    ticket_type = SimpleNamespace(id=52, event_id=event.id, price=Decimal("0.00"))
    registrations = []

    class FakeRegistration:
        id = 53

        def __init__(self, **kwargs):
            registrations.append(kwargs)
            self.id = self.__class__.id
            self.registration_ref = None
            self.ticket_number = None
            self.qr_token = None

        def generate_refs(self, event_slug, sequence):
            self.registration_ref = f"ER-{event_slug.upper()}-{sequence:08d}"
            self.ticket_number = f"TKT-{event_slug.upper()}-{sequence:08d}"
            self.qr_token = "free-qr-token"

    class FakeQuery:
        def filter_by(self, **filters):
            return self

        def scalar(self):
            return 0

    class FakeSession:
        def get(self, model, identifier):
            if model is TicketType and identifier == ticket_type.id:
                return ticket_type
            if model is Event and identifier == event.id:
                return event
            return None

        def query(self, *args):
            return FakeQuery()

        def add(self, registration):
            return None

        def flush(self):
            return None

    monkeypatch.setattr(payment_service_module.db, "session", FakeSession())
    monkeypatch.setattr(payment_service_module, "EventRegistration", FakeRegistration)

    service = object.__new__(EventPaymentService)
    result = service._create_single_registration(
        user_id=8,
        event_id=event.id,
        ticket_type_id=ticket_type.id,
        payment_reference=None,
        attendee_data={"name": "Free Attendee", "email": "free@example.com"},
    )

    assert result["registration_ref"] == "ER-FREE-EVENT-00000001"
    assert registrations[0]["payment_status"] == "free"
    assert registrations[0]["wallet_txn_id"] is None
    assert registrations[0]["registration_fee"] == 0.0