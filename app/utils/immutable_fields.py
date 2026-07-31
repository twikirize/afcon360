from typing import Set, Dict, Any, Optional, Tuple
from app.profile.models import IMMUTABLE_AFTER_VERIFICATION


def get_immutable_fields() -> Set[str]:
    return IMMUTABLE_AFTER_VERIFICATION.copy()


def is_field_immutable(field_name: str) -> bool:
    return field_name in IMMUTABLE_AFTER_VERIFICATION


def filter_immutable_changes(
    profile: Any,
    data: Dict[str, Any],
    is_verified: bool,
) -> Tuple[Dict[str, Any], Set[str]]:
    if not is_verified:
        return data, set()

    allowed = {}
    blocked = set()

    for field, value in data.items():
        if field in IMMUTABLE_AFTER_VERIFICATION:
            current_value = getattr(profile, field, None)
            if current_value != value:
                blocked.add(field)
        else:
            allowed[field] = value

    return allowed, blocked


def enforce_immutability(
    profile: Any,
    data: Dict[str, Any],
    is_verified: bool,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    if not is_verified:
        return {}

    blocked = {}
    for field in IMMUTABLE_AFTER_VERIFICATION:
        if field in data:
            current_value = getattr(profile, field, None)
            new_value = data[field]
            if current_value != new_value:
                blocked[field] = {
                    "old_value": str(current_value) if current_value is not None else None,
                    "attempted_value": str(new_value) if new_value is not None else None,
                }

    return blocked