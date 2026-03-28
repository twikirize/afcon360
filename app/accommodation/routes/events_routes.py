# app/accommodation/routes/event_routes.py
"""
Event landing pages - For AFCON, Crusades, etc.
"""

from flask import render_template, request, jsonify
from app.accommodation.routes import event
from app.accommodation.services.search_service import search_properties
from app.accommodation.models.booking import BookingContextType


@event.route("/", endpoint="list")
def event_list():
    """List all events"""
    events = {
        'afcon-2026': {
            'name': 'AFCON 2026',
            'slug': 'afcon-2026',
            'city': 'Kampala',
            'description': 'Africa Cup of Nations 2026 - The biggest football event in Africa!',
            'start_date': '2026-06-01',
            'end_date': '2026-07-31',
            'dates': 'June - July 2026',
            'venue': 'Namboole Stadium',
            'image': '/static/images/afcon-2026.jpg',
            'metadata': {
                'image': '/static/images/afcon-2026.jpg'
            }
        },
        'crusade-2026': {
            'name': 'Great Crusade 2026',
            'slug': 'crusade-2026',
            'city': 'Kampala',
            'description': 'Annual spiritual gathering with thousands of believers',
            'start_date': '2026-04-10',
            'end_date': '2026-04-13',
            'dates': 'April 10-13, 2026',
            'venue': 'Kololo Independence Grounds',
            'image': '/static/images/crusade-2026.jpg',
            'metadata': {
                'image': '/static/images/crusade-2026.jpg'
            }
        },
        'world-cup-2026': {
            'name': 'World Cup 2026',
            'slug': 'world-cup-2026',
            'city': 'Nairobi',
            'description': 'Watch the World Cup in style!',
            'start_date': '2026-06-01',
            'end_date': '2026-07-31',
            'dates': 'June - July 2026',
            'venue': 'Kasarani Stadium',
            'image': '/static/images/worldcup-2026.jpg',
            'metadata': {
                'image': '/static/images/worldcup-2026.jpg'
            }
        }
    }

    events_list = list(events.values())

    return render_template(
        'accommodation/events/list.html',
        events=events_list
    )


@event.route("/<event_slug>", endpoint="landing")
def event_landing(event_slug):
    """Landing page for an event"""
    events = {
        'afcon-2026': {
            'name': 'AFCON 2026',
            'slug': 'afcon-2026',
            'city': 'Kampala',
            'description': 'Africa Cup of Nations 2026 - The biggest football event in Africa!',
            'start_date': '2026-06-01',
            'end_date': '2026-07-31',
            'dates': 'June - July 2026',
            'venue': 'Namboole Stadium',
            'image': '/static/images/afcon-2026.jpg'
        },
        'crusade-2026': {
            'name': 'Great Crusade 2026',
            'slug': 'crusade-2026',
            'city': 'Kampala',
            'description': 'Annual spiritual gathering with thousands of believers',
            'start_date': '2026-04-10',
            'end_date': '2026-04-13',
            'dates': 'April 10-13, 2026',
            'venue': 'Kololo Independence Grounds',
            'image': '/static/images/crusade-2026.jpg'
        },
        'world-cup-2026': {
            'name': 'World Cup 2026',
            'slug': 'world-cup-2026',
            'city': 'Nairobi',
            'description': 'Watch the World Cup in style!',
            'start_date': '2026-06-01',
            'end_date': '2026-07-31',
            'dates': 'June - July 2026',
            'venue': 'Kasarani Stadium',
            'image': '/static/images/worldcup-2026.jpg'
        }
    }

    event_data = events.get(event_slug)
    if not event_data:
        return render_template('accommodation/events/not_found.html', event_slug=event_slug), 404

    properties = search_properties(city=event_data['city'])

    return render_template(
        'accommodation/events/landing.html',
        event=event_data,
        properties=properties,
        context_type=BookingContextType.EVENT.value,
        context_id=event_slug,
        context_metadata={
            'event_name': event_data['name'],
            'event_dates': event_data['dates'],
            'venue': event_data['venue']
        }
    )


@event.route("/create", endpoint="create_event")
def create_event():
    """Create event page"""
    return render_template('accommodation/events/create.html')


@event.route("/my-events", endpoint="my_events")
def my_events():
    """User's events page"""
    return render_template('accommodation/events/my_events.html')


@event.route("/<event_slug>/edit", endpoint="edit_event")
def edit_event(event_slug):
    """Edit event page"""
    return render_template('accommodation/events/edit.html', event_slug=event_slug)


@event.route("/api/<event_slug>/properties", endpoint="api_properties")
def api_event_properties(event_slug):
    """JSON API for event properties"""
    events = {
        'afcon-2026': {'city': 'Kampala'},
        'crusade-2026': {'city': 'Kampala'},
        'world-cup-2026': {'city': 'Nairobi'}
    }

    event_data = events.get(event_slug)
    if not event_data:
        return jsonify({'error': 'Event not found'}), 404

    properties = search_properties(city=event_data['city'])
    return jsonify({
        'success': True,
        'properties': properties,
        'count': len(properties)
    })