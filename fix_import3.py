filepath = 'app/events/services.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '''        from app.identity.models.user import User
        Event = cls._get_event_model_class()''',
    '''        from app.identity.models.user import User
        from app.events.permissions import _is_event_owner
        Event = cls._get_event_model_class()'''
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
