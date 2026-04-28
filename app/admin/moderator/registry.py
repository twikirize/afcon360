_REGISTRY = {}

def register_module(entity_type: str, display_name: str, review_url_fn=None):
    _REGISTRY[entity_type] = {
        "display_name": display_name,
        "review_url_fn": review_url_fn,
    }

def get_registry():
    return dict(_REGISTRY)

def get_review_url(entity_type: str, entity_id: int) -> str | None:
    entry = _REGISTRY.get(entity_type)
    if entry and entry.get("review_url_fn"):
        return entry["review_url_fn"](entity_id)
    return None