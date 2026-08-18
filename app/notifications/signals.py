"""
AFCON360 Notification Signals

Decoupled event bus (blinker) for lifecycle events. Domain services emit these
signals; the notification listeners (app/notifications/listeners.py) subscribe
and dispatch notifications. This keeps modules decoupled from the notification
system while guaranteeing full lifecycle coverage:

    account.created -> signup notification
    kyc.submitted / kyc.approved / kyc.rejected
    wallet.created / wallet.transaction
    property.submitted / property.approved / property.rejected / property.suspended
    booking.confirmed / booking.cancelled / booking.checked_in / booking.checked_out
    event.registered / event.reminder
    transport.booking.created / transport.driver_assigned
    message.sent (internal)
"""

try:
    from blinker import signal

    user_signed_up = signal('user-signed-up')
    kyc_submitted = signal('kyc-submitted')
    kyc_approved = signal('kyc-approved')
    kyc_rejected = signal('kyc-rejected')
    wallet_created = signal('wallet-created')
    wallet_transaction = signal('wallet-transaction')
    property_submitted = signal('property-submitted')
    property_approved = signal('property-approved')
    property_rejected = signal('property-rejected')
    property_suspended = signal('property-suspended')
    booking_created = signal('booking-created')
    booking_confirmed = signal('booking-confirmed')
    booking_cancelled = signal('booking-cancelled')
    booking_checked_in = signal('booking-checked-in')
    booking_checked_out = signal('booking-checked-out')
    booking_dates_modified = signal('booking-dates-modified')
    event_registered = signal('event-registered')
    event_reminder = signal('event-reminder')
    transport_booking_created = signal('transport-booking-created')
    transport_driver_assigned = signal('transport-driver-assigned')
    message_sent = signal('message-sent')
except ImportError:
    # Fallback no-op signals if blinker is unavailable
    class _NoOp:
        def connect(self, *a, **k):
            return None
        def send(self, *a, **k):
            return []
    _s = _NoOp()
    user_signed_up = kyc_submitted = kyc_approved = kyc_rejected = _s
    wallet_created = wallet_transaction = _s
    property_submitted = property_approved = property_rejected = property_suspended = _s
    booking_created =     booking_confirmed = booking_cancelled = _s
    booking_checked_in = booking_checked_out = _s
    booking_dates_modified = _s
    event_registered = event_reminder = _s
    transport_booking_created = transport_driver_assigned = message_sent = _s
