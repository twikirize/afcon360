"""
Events Module Signals - Loose Coupling Bridge
Allows other modules to react without direct imports
"""
from blinker import Namespace

signals = Namespace()

# Broadcast when registration is complete
event_registered = signals.signal('event-registered')
event_cancelled = signals.signal('event-cancelled')
event_capacity_released = signals.signal('event-capacity-released')

# Signal for requesting service provider data
service_provider_data_requested = signals.signal('service-provider-data-requested')

# Signal for offering services after event registration
offer_services_after_registration = signals.signal('offer-services-after-registration')
