# app/accommodation/state_machine/__init__.py
"""
Accommodation booking state machine.
Re-exports from booking_states so both import paths work:
  - from app.accommodation.state_machine import BookingStateMachine
  - from app.accommodation.state_machine.booking_states import BookingStateMachine
"""

from app.accommodation.state_machine.booking_states import (
    BookingStateMachine,
    InvalidStateTransition,
)

__all__ = [
    "BookingStateMachine",
    "InvalidStateTransition",
]