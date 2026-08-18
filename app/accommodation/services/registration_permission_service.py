"""Authorization for booking roster management."""

from app.auth.delegation import DelegationScope, DelegationService


class RegistrationPermissionService:
    """Keep roster management authorization in one place."""

    SCOPE = getattr(DelegationScope, "ACCOMMODATION_REGISTRATION_MANAGEMENT", None)

    @staticmethod
    def can_manage_registrations(user, booking) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if user.id in {
            booking.booked_by_user_id,
            booking.booking_owner_id,
            booking.host_user_id,
        }:
            return True
        if hasattr(user, "has_global_role") and user.has_global_role(
            "owner", "super_admin", "admin", "accommodation_admin"
        ):
            return True
        if RegistrationPermissionService.SCOPE is None:
            return False
        return DelegationService().check_delegation_permission(
            user.id, RegistrationPermissionService.SCOPE
        )