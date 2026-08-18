"""Regression coverage for the accommodation payment-options contract."""

from decimal import Decimal
from types import SimpleNamespace

from app.accommodation.models.booking_policy import PropertyBookingPolicy
from app.accommodation.models.property_payment_method import PropertyPaymentMethod
from app.accommodation.services.payment_policy_service import PaymentPolicyService
from app.wallet.models.payment_method import PaymentMethodConfig


class _Query:
    def __init__(self, *, first=None, all_items=None):
        self._first = first
        self._all_items = all_items or []

    def filter_by(self, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._all_items


def test_property_payment_options_keep_method_specific_timings(monkeypatch):
    policy = SimpleNamespace(
        allow_pay_now=True,
        allow_pay_on_arrival=True,
        allow_deposit_payment=True,
        deposit_percentage=Decimal("0"),
        cancellation_policy="flexible",
        free_cancel_hours=24,
        require_guest_identity=False,
        require_guest_phone=True,
        require_guest_email=True,
        minimum_age=None,
    )
    wallet = SimpleNamespace(
        id=1,
        method_id="wallet",
        display_name="AFCON360 Wallet",
        method_type="wallet",
        supported_currencies=["USD"],
        allowed_timings=["pay_now", "deposit"],
        transaction_fee=Decimal("0"),
        min_amount=Decimal("0"),
        max_amount=Decimal("1000000"),
    )
    cash = SimpleNamespace(
        id=2,
        method_id="cash",
        display_name="Cash",
        method_type="cash",
        supported_currencies=["USD"],
        allowed_timings=["pay_on_arrival"],
        transaction_fee=Decimal("0"),
        min_amount=Decimal("0"),
        max_amount=Decimal("1000000"),
    )
    links = [
        SimpleNamespace(wallet_method_id=1, preferred_currency=None),
        SimpleNamespace(wallet_method_id=2, preferred_currency=None),
    ]

    monkeypatch.setattr(PropertyBookingPolicy, "query", _Query(first=policy))
    monkeypatch.setattr(PropertyPaymentMethod, "query", _Query(all_items=links))
    monkeypatch.setattr(PaymentMethodConfig, "query", _Query(all_items=[wallet, cash]))
    monkeypatch.setattr(
        "app.accommodation.services.payment_policy_service.db.session.get",
        lambda model, property_id: SimpleNamespace(currency="USD"),
    )
    monkeypatch.setattr(
        "app.accommodation.services.payment_policy_service.PlatformBookingPolicyOverride.query",
        _Query(first=None),
    )

    options = PaymentPolicyService.get_allowed_options(2, Decimal("100"))

    assert [(item["method_id"], item["allowed_timings"]) for item in options["payment_methods"]] == [
        ("wallet", ["pay_now", "deposit"]),
        ("cash", ["pay_on_arrival"]),
    ]