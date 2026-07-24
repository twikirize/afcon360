from app import db
from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.services.availability_service import AvailabilityService
from datetime import datetime

booking = AccommodationBooking.query.filter_by(booking_reference='ACC-202607180907-95E58A7A').first()
if not booking:
    print('Booking not found')
    exit()

print(f'Found booking ID={booking.id} status={booking.status}')

# Unblock dates
AvailabilityService.unblock_dates(booking.property_id, booking.check_in, booking.check_out)
print('Unblocked dates')

# Cancel booking
booking.status = 'cancelled'
booking.cancelled_at = datetime.now()
booking.cancelled_by_user_id = booking.guest_user_id
booking.cancellation_reason = 'System error during confirmation'
db.session.commit()
print('Booking cancelled successfully')
