# app/events/view_models.py
"""ViewModels for Event module - separates presentation from business logic"""

from typing import Dict, Optional, List
from app.events.models import Event, TicketType

class EventRegistrationViewModel:
    """View model for event landing page - contains exactly what the template needs"""
    
    def __init__(self, event: Event, current_user=None):
        self.event = event
        self.user = current_user
        
        # Direct attributes for template access
        self.name = event.name
        self.description = event.description or ''
        self.start_date = event.start_date.isoformat() if event.start_date else None
        self.end_date = event.end_date.isoformat() if event.end_date else None
        self.city = event.city
        self.venue = event.venue or ''
        self.currency = event.currency
        self.status = event.status.value if event.status else None
        self.max_capacity = event.max_capacity or 0
        self.contact_email = event.contact_email
        self.contact_phone = event.contact_phone
        self.website = event.website
        self.category = event.category
        self.metadata = event.event_metadata or {}
        self.slug = event.slug
        self.featured = event.featured
        
        # Process ticket types
        self.ticket_types = []
        self.is_paid_event = False
        for tt in event.ticket_types:
            if tt.is_active:
                self.ticket_types.append({
                    'id': tt.id,
                    'name': tt.name,
                    'price': float(tt.price),
                    'capacity': tt.capacity,
                    'description': tt.description or '',
                    'is_active': tt.is_active
                })
                if tt.price > 0:
                    self.is_paid_event = True
        
        # Sort ticket types by price (cheapest first)
        self.ticket_types.sort(key=lambda x: x['price'])
    
    def to_dict(self) -> Dict:
        """Convert to dict for JSON responses"""
        from app.events.services import EventService
        return EventService._event_to_dict(self.event)
