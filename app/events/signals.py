"""
Backwards-compatible re-export of signals from signal_handlers.
Import signals from here OR signal_handlers — both are the same object.
"""
from app.events.signal_handlers import (
    event_registered,
    event_cancelled,
    event_capacity_released,
    offer_services_after_registration,
    service_provider_data_requested,
)
