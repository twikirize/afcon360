from app import create_app
from app.events.services import EventService

app = create_app()
with app.app_context():
    event = EventService.get_event('NOTHING')
    if event:
        print('API response fields:')
        print('  id (public_id):', event.get('id'))
        print('  slug:', event.get('slug'))
        print('  internal_id:', event.get('internal_id'))
        print('  name:', event.get('name'))
    else:
        print('Event not found')
