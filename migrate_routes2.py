import re

filepath = 'app/events/routes.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. _can_check_in
target1 = '''        # Event organizers can always check in
        if event_data.get('organizer_id') == user.id:
            return True'''
replacement1 = '''        # Event owners/operators can always check in
        event_model = EventService.get_event_model(event_data.get('slug'))
        if event_model and _is_event_owner(user, event_model):
            return True'''
content = content.replace(target1, replacement1)

# 2. api_contact_organizer
target2 = '''        organizer = db.session.get(User, event.organizer_id) if event.organizer_id else None'''
replacement2 = '''        # Determine the primary contact
        contact_user_id = event.current_owner_id if event.current_owner_type == 'individual' else (event.original_creator_id or event.organizer_id)
        organizer = db.session.get(User, contact_user_id) if contact_user_id else None'''
content = content.replace(target2, replacement2)

# 3. organizer_messages
target3 = '''    messages = OrganizerMessage.query.join(Event)\\
        .filter(Event.organizer_id == current_user.id)\\
        .order_by(OrganizerMessage.created_at.desc())\\
        .all()'''
replacement3 = '''    from sqlalchemy import or_, and_
    from app.events.models import EventRole
    messages = OrganizerMessage.query.join(Event)\\
        .outerjoin(EventRole, Event.id == EventRole.event_id)\\
        .filter(or_(
            and_(Event.current_owner_type == 'individual', Event.current_owner_id == current_user.id),
            EventRole.user_id == current_user.id
        ))\\
        .order_by(OrganizerMessage.created_at.desc())\\
        .all()'''
content = content.replace(target3, replacement3)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated routes.py")
