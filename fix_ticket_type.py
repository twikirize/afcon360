filepath = 'app/events/models.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

target = '''    def __init__(self, **kwargs):
        if 'organizer_id' in kwargs:
            import logging
            import warnings
            warnings.warn('Event constructor organizer_id parameter is DEPRECATED (Phase 4 Step 5)', DeprecationWarning, stacklevel=2)
            logging.getLogger(__name__).warning('LEGACY CONSTRUCTOR FALLBACK: Event initialized with organizer_id. Phase 4 Deprecation.')
        super().__init__(**kwargs)
        if self.available_seats is None:'''
replacement = '''    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.available_seats is None:'''
content = content.replace(target, replacement)
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
