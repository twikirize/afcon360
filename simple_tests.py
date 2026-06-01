#KEEP PUTTING FILES HERE TO TEST THEN COMMENT THEM  FOR FUTURE USE
#THEN COMMENT THE USED SCRIPTS

##--- All community-related endpoints: ---
from app import create_app
from flask import url_for
app = create_app()
with app.app_context():
    try:
        url = url_for('events.community_host_register', slug='swearing-in')
        print(f"✅ Generated URL: {url}")
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"Error type: {type(e).__name__}")

    # List all endpoints in events blueprint
    print("\nAll community-related endpoints:")
    for rule in app.url_map.iter_rules():
        if 'community' in str(rule):
            print(f"  {rule.endpoint} -> {rule}")
"""
#--- Testing Context Builder ---
# Create a test script
from app import create_app
from app.events.models import Event
from app.events.services import EventService

app = create_app()
with app.app_context():
    # Check if event exists
    event = Event.query.filter_by(slug='swearing-in').first()
    if event:
        print(f'✅ Event found: {event.name}')
        print(f'   Status: {event.status}')
        print(f'   Ticket types: {len(event.ticket_types)}')
    else:
        print('❌ Event "swearing-in" NOT found')
        print('\nAvailable events:')
        for e in Event.query.all():
            print(f'  - {e.slug}: {e.name}')

    # Test context builder
    print('\n--- Testing Context Builder ---')
    context = EventService.build_event_context('swearing-in')
    print(f'Event found: {context.get("event_found")}')
    print(f'Event name: {context.get("event_name")}')
    print(f'Can register: {context.get("can_register")}')


"""