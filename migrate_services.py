filepath = 'app/events/services.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

import re

# Add import if missing
if 'from app.events.permissions import _is_event_owner' not in content:
    content = content.replace('from app.events.models import Event, EventRegistration, TicketType, Waitlist', 
                              'from app.events.models import Event, EventRegistration, TicketType, Waitlist, EventRole\nfrom app.events.permissions import _is_event_owner\nfrom app.identity.models.user import User')


content = content.replace(
    '''        if event.organizer_id != user_id:
            return False, "Unauthorized"''',
    '''        user = db.session.get(User, user_id)
        if not user or not _is_event_owner(user, event):
            return False, "Unauthorized"'''
)

# Fix get_events_by_organizer
content = content.replace(
    '''    def get_events_by_organizer(cls, organizer_id: int) -> List[Dict]:
        Event = cls._get_event_model_class()
        events = Event.query.filter_by(organizer_id=organizer_id).order_by(Event.created_at.desc()).all()''',
    '''    def get_events_by_organizer(cls, organizer_id: int) -> List[Dict]:
        Event = cls._get_event_model_class()
        from sqlalchemy import or_, and_
        events = Event.query.outerjoin(
            EventRole, Event.id == EventRole.event_id
        ).filter(
            or_(
                and_(Event.current_owner_type == 'individual', Event.current_owner_id == organizer_id),
                EventRole.user_id == organizer_id
            )
        ).order_by(Event.created_at.desc()).all()'''
)

# Fix get_events_managed_by_user
content = content.replace(
    '''        events = []
        user_events = Event.query.filter_by(organizer_id=user_id).all()
        events.extend(user_events)''',
    '''        events = []
        from sqlalchemy import or_, and_
        user_events = Event.query.outerjoin(
            EventRole, Event.id == EventRole.event_id
        ).filter(
            or_(
                and_(Event.current_owner_type == 'individual', Event.current_owner_id == user_id),
                EventRole.user_id == user_id
            )
        ).all()
        events.extend(user_events)'''
)

# Fix get_organizer_dashboard_data
content = content.replace(
    '''    def get_organizer_dashboard_data(cls, user_id: int) -> Dict:
        managed_events = cls.get_events_managed_by_user(user_id)
        Event = cls._get_event_model_class()
        Registration = cls._get_registration_class()
        event_models = Event.query.filter_by(organizer_id=user_id).all()''',
    '''    def get_organizer_dashboard_data(cls, user_id: int) -> Dict:
        managed_events = cls.get_events_managed_by_user(user_id)
        Event = cls._get_event_model_class()
        Registration = cls._get_registration_class()
        from sqlalchemy import or_, and_
        event_models = Event.query.outerjoin(
            EventRole, Event.id == EventRole.event_id
        ).filter(
            or_(
                and_(Event.current_owner_type == 'individual', Event.current_owner_id == user_id),
                EventRole.user_id == user_id
            )
        ).all()'''
)

# Fix update_event_status
content = content.replace(
    '''        elif new_status == EventStatus.PUBLISHED:
            is_organizer = (event.organizer_id == user_id)
            if not (has_global_permission(user, "events.approve") or is_organizer):
                return False, "You do not have permission to publish this event"''',
    '''        elif new_status == EventStatus.PUBLISHED:
            is_owner = _is_event_owner(user, event)
            if not (has_global_permission(user, "events.approve") or is_owner):
                return False, "You do not have permission to publish this event"'''
)


with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated services.py")
