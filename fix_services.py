filepath = 'app/events/services.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '''        if event.organizer_id != user_id:
            return None, "Unauthorized"''',
    '''        user = db.session.get(User, user_id)
        if not user or not _is_event_owner(user, event):
            return None, "Unauthorized"'''
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
