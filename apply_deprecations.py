def add_deprecation_to_permissions():
    filepath = 'app/events/permissions.py'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    target = "def _resolve_organiser_id(event) -> int | None:\n    \"\"\"Return the organiser user id from either a model instance or a dict.\"\"\""
    replacement = "def _resolve_organiser_id(event) -> int | None:\n    \"\"\"Return the organiser user id from either a model instance or a dict.\"\"\"\n    import logging\n    import warnings\n    warnings.warn('organizer_id fallback usage is DEPRECATED (Phase 4 Step 5)', DeprecationWarning, stacklevel=2)\n    logging.getLogger(__name__).warning('LEGACY PERMISSION FALLBACK: _resolve_organiser_id called. Phase 4 Deprecation.')"
    
    if "LEGACY PERMISSION FALLBACK" not in content:
        content = content.replace(target, replacement)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Updated permissions.py")

def add_deprecation_to_models():
    filepath = 'app/events/models.py'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    target = "def __init__(self, **kwargs):\n        super().__init__(**kwargs)"
    replacement = "def __init__(self, **kwargs):\n        if 'organizer_id' in kwargs:\n            import logging\n            import warnings\n            warnings.warn('Event constructor organizer_id parameter is DEPRECATED (Phase 4 Step 5)', DeprecationWarning, stacklevel=2)\n            logging.getLogger(__name__).warning('LEGACY CONSTRUCTOR FALLBACK: Event initialized with organizer_id. Phase 4 Deprecation.')\n        super().__init__(**kwargs)"
    
    if "LEGACY CONSTRUCTOR FALLBACK" not in content:
        content = content.replace(target, replacement)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Updated models.py")

add_deprecation_to_permissions()
add_deprecation_to_models()
