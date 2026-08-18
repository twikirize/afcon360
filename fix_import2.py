filepath = 'app/events/services.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '''    def update_event(cls, event_id: str, data: Dict, user_id: int) -> Tuple[bool, Optional[str]]:
        Event = cls._get_event_model_class()''',
    '''    def update_event(cls, event_id: str, data: Dict, user_id: int) -> Tuple[bool, Optional[str]]:
        from app.identity.models.user import User
        Event = cls._get_event_model_class()'''
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
