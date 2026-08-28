# app/accommodation/state_machine/__init__.py
"""
Accommodation state machines.
- BookingStateMachine: booking lifecycle (independent of payment)
- PaymentStateMachine: payment lifecycle (independent of booking)
- BookingPolicyEvaluator: policy bridge between the two
- PaymentPolicyEvaluator: payment-specific policy evaluation
"""

from app.accommodation.state_machine.booking_states import (
    BookingStateMachine,
    InvalidStateTransition,
)
from app.accommodation.state_machine.payment_states import (
    PaymentStateMachine,
    PaymentState,
    InvalidPaymentTransition,
)
from app.accommodation.state_machine.policy_evaluator import (
    BookingPolicyEvaluator,
    PaymentPolicyEvaluator,
    PolicyDecision,
    PaymentRequirement,
)

__all__ = [
    "BookingStateMachine",
    "InvalidStateTransition",
    "PaymentStateMachine",
    "PaymentState",
    "InvalidPaymentTransition",
    "BookingPolicyEvaluator",
    "PaymentPolicyEvaluator",
    "PolicyDecision",
    "PaymentRequirement",
]