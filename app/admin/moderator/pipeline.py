from app.admin.services import create_flag

def _score_priority(entity_type: str, submitted_by_user) -> str:
    """
    Simple risk scoring. Returns priority string.
    Extend this later with ML hooks.
    """
    # New/unverified accounts are higher risk
    if not getattr(submitted_by_user, 'is_verified', True):
        return "high"
    return "normal"

def submit_for_moderation(entity_type: str, object_id: int, reason: str, submitted_by_user, priority: str = None):
    """
    Universal moderation entry point for ALL modules.
    Wraps create_flag(). Does NOT change entity state.
    """
    if priority is None:
        priority = _score_priority(entity_type, submitted_by_user)
    return create_flag(
        submitted_by_user,
        entity_type,
        object_id,
        reason,
        priority=priority,
    )
