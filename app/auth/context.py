"""Canonical operating-context resolution for the authenticated user.

This module deliberately normalizes existing domain assignments instead of
creating a second identity or permission store.  Domain models are imported
lazily so the auth package remains independent from feature-module import
order, and every selected context is revalidated against live assignments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Iterable, Mapping, Optional

from flask import abort, jsonify, request, session, url_for


class ContextType(str, Enum):
    PERSONAL = "personal"
    ORGANISATION = "organisation"
    EVENT = "event"
    DRIVER = "driver"
    ACCOMMODATION_HOST = "accommodation_host"
    PLATFORM = "platform"


@dataclass(frozen=True)
class ContextRequest:
    """Normalized input accepted by the resolver."""

    type: ContextType
    public_id: Optional[str] = None
    role: Optional[str] = None
    next: Optional[str] = None

    @classmethod
    def from_value(cls, value: Any) -> "ContextRequest":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("context request must be a mapping")

        raw_type = value.get("type", value.get("context_type"))
        aliases = {"individual": "personal", "organization": "organisation"}
        raw_type = aliases.get(str(raw_type).strip().lower(), raw_type)
        try:
            context_type = ContextType(str(raw_type).strip().lower())
        except (TypeError, ValueError) as exc:
            raise ValueError("unsupported context type") from exc

        raw_id = value.get("public_id", value.get("id"))
        public_id = None if raw_id in (None, "") else str(raw_id)
        role = value.get("role")
        role = str(role).strip() if role not in (None, "") else None
        return cls(
            type=context_type,
            public_id=public_id,
            role=role,
            next=value.get("next"),
        )


@dataclass(frozen=True)
class ContextDescriptor:
    """Safe, template/API-facing representation of an eligible context."""

    type: ContextType
    public_id: Optional[str]
    label: str
    role: Optional[str]
    workspace_url: Optional[str] = None
    permission_lookup_metadata: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def id(self) -> Optional[str]:
        """Compatibility alias; this is always a public identifier."""
        return self.public_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "public_id": self.public_id,
            "id": self.public_id,
            "label": self.label,
            "role": self.role,
            "workspace_url": self.workspace_url,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


class ContextSwitchError(ValueError):
    """Raised when a requested context cannot be established."""


_SESSION_KEYS = ("active_context_type", "active_context_id", "active_role")
_BLOCKED_EVENT_STATES = {"suspended", "deactivated", "deleted", "archived"}
_APPROVED_DRIVER_TIERS = {"platform_verified", "event_certified"}
_BLOCKED_DRIVER_STATES = {"suspended", "revoked", "blacklisted"}


def _is_live_user(user: Any) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", True)
        and getattr(user, "is_active", True)
        and not getattr(user, "is_deleted", False)
    )


def _public_id(value: Any) -> Optional[str]:
    raw = getattr(value, "public_id", None)
    return None if raw is None else str(raw)


def _safe_url(endpoint: str, **values: Any) -> Optional[str]:
    try:
        return url_for(endpoint, **values)
    except Exception:
        return None


def _workspace_url(
    context_type: ContextType,
    public_id: Optional[str],
    role: Optional[str] = None,
) -> Optional[str]:
    """Resolve the canonical landing page for an operating context.

    ``role`` is used only to choose a platform workspace. The destination's
    existing authorization and context guards still enforce access.
    """
    platform_endpoints = {
        "owner": ("admin.owner.dashboard",),
        "super_admin": ("admin.super_dashboard",),
        "admin": ("admin.super_dashboard",),
        "auditor": ("admin.auditor.dashboard",),
        "compliance_officer": ("admin.compliance.dashboard",),
        "moderator": ("admin.moderator.dashboard",),
        "support": ("admin.support.dashboard",),
        "event_manager": ("admin.event_manager_dashboard",),
        "transport_admin": ("admin.transport_admin_dashboard",),
        "wallet_admin": ("admin.wallet_admin_dashboard",),
        "accommodation_admin": ("admin.accommodation_admin_dashboard",),
        "tourism_admin": ("admin.tourism_admin_dashboard",),
        "org_admin": ("admin.org_admin_dashboard",),
        "org_member": ("admin.org_member_dashboard",),
    }
    if context_type is ContextType.PLATFORM:
        candidates = platform_endpoints.get(role or "", ("admin.super_dashboard",))
    else:
        candidates = {
            ContextType.PERSONAL: ("user.dashboard",),
            ContextType.ORGANISATION: ("org.org_dashboard",),
            ContextType.EVENT: ("events.organizer_dashboard", "admin.event_manager_dashboard"),
            ContextType.DRIVER: ("transport.driver_dashboard", "transport.dashboard_overview"),
            ContextType.ACCOMMODATION_HOST: ("accommodation.host_dashboard",),
        }[context_type]
    for endpoint in candidates:
        values = {}
        if context_type == ContextType.ORGANISATION and public_id and endpoint == "org.org_dashboard":
            values["org_id"] = public_id
        elif context_type == ContextType.EVENT and endpoint == "events.organizer_dashboard" and public_id:
            values["identifier"] = public_id
        url = _safe_url(endpoint, **values)
        if url:
            return url
    return None


def _personal_context(user: Any) -> ContextDescriptor:
    return ContextDescriptor(
        type=ContextType.PERSONAL,
        public_id=None,
        label="Personal",
        role="user",
        workspace_url=_workspace_url(ContextType.PERSONAL, None),
        permission_lookup_metadata={"user_public_id": _public_id(user)},
    )


def _query_rows(model: Any, **filters: Any) -> Optional[list[Any]]:
    """Query a model and return None when its query interface is unavailable."""
    try:
        return model.query.filter_by(**filters).all()
    except (AttributeError, ImportError, RuntimeError):
        return None


def _loaded_memberships(user: Any) -> Iterable[Any]:
    try:
        from app.identity.models.organisation_member import OrganisationMember

        rows = _query_rows(
            OrganisationMember,
            user_id=getattr(user, "id", None),
            is_active=True,
            is_deleted=False,
        )
        if rows is not None:
            return rows
    except (ImportError, AttributeError, RuntimeError):
        pass
    return getattr(user, "organisations", ()) or ()


def _loaded_event_roles(user: Any) -> Iterable[Any]:
    try:
        from app.events.models import EventRole

        rows = _query_rows(
            EventRole,
            user_id=getattr(user, "id", None),
            is_active=True,
            is_deleted=False,
        )
        if rows is not None:
            return rows
    except (ImportError, AttributeError, RuntimeError):
        pass
    return getattr(user, "event_roles", ()) or ()


def _loaded_global_roles(user: Any) -> Iterable[Any]:
    try:
        from app.identity.models.user import UserRole

        rows = _query_rows(
            UserRole,
            user_id=getattr(user, "id", None),
            is_deleted=False,
        )
        if rows is not None:
            return rows
    except (ImportError, AttributeError, RuntimeError):
        pass
    return getattr(user, "roles", ()) or ()


def _loaded_driver(user: Any) -> Any:
    try:
        from app.transport.models import DriverProfile

        return DriverProfile.query.filter_by(
            user_id=getattr(user, "id", None), is_deleted=False
        ).first()
    except (ImportError, AttributeError, RuntimeError):
        return getattr(user, "driver_profile", None)


def _role_is_live(assignment: Any) -> bool:
    return not getattr(assignment, "is_deleted", False) and getattr(
        assignment, "is_active", True
    )


def _organisation_is_live(organisation: Any) -> bool:
    if not organisation:
        return False
    if getattr(organisation, "is_deleted", False) or not getattr(organisation, "is_active", True):
        return False
    if getattr(organisation, "lifecycle_state", None) in {"suspended", "closed"}:
        return False
    return True


def _event_is_live(event: Any) -> bool:
    if not event or getattr(event, "is_deleted", False):
        return False
    state = getattr(event, "status", None)
    state = getattr(state, "value", state)
    return str(state).lower() not in _BLOCKED_EVENT_STATES


def _global_contexts(user: Any) -> list[ContextDescriptor]:
    descriptors: list[ContextDescriptor] = []
    for assignment in _loaded_global_roles(user):
        if not _role_is_live(assignment):
            continue
        role = getattr(assignment, "role", None)
        if not role or getattr(role, "scope", "global") != "global":
            continue
        role_name = getattr(role, "name", None)
        if not role_name:
            continue
        descriptors.append(
            ContextDescriptor(
                type=ContextType.PLATFORM,
                public_id=_public_id(user),
                label=f"Platform Administration — {role_name.replace('_', ' ').title()}",
                role=role_name,
                workspace_url=_workspace_url(ContextType.PLATFORM, _public_id(user), role_name),
                permission_lookup_metadata={"role_id": getattr(role, "id", None)},
            )
        )
    return descriptors


def _organisation_contexts(user: Any) -> list[ContextDescriptor]:
    descriptors: list[ContextDescriptor] = []
    for membership in _loaded_memberships(user):
        if not getattr(membership, "is_active", True) or getattr(membership, "is_deleted", False):
            continue
        organisation = getattr(membership, "organisation", None)
        if not _organisation_is_live(organisation):
            continue
        public_id = getattr(organisation, "org_id", None)
        if not public_id:
            continue
        for assignment in getattr(membership, "roles", ()) or ():
            if not _role_is_live(assignment):
                continue
            role = getattr(assignment, "role", None)
            role_name = getattr(role, "name", None)
            if not role_name:
                continue
            descriptors.append(
                ContextDescriptor(
                    type=ContextType.ORGANISATION,
                    public_id=str(public_id),
                    label=f"{getattr(organisation, 'legal_name', None) or getattr(organisation, 'name', 'Organisation')} — {role_name.replace('_', ' ').title()}",
                    role=role_name,
                    workspace_url=_workspace_url(ContextType.ORGANISATION, str(public_id)),
                    permission_lookup_metadata={
                        "organisation_id": getattr(organisation, "id", None),
                        "membership_id": getattr(membership, "id", None),
                    },
                )
            )
    return descriptors


def _event_contexts(user: Any) -> list[ContextDescriptor]:
    descriptors: list[ContextDescriptor] = []
    for assignment in _loaded_event_roles(user):
        if not _role_is_live(assignment):
            continue
        event = getattr(assignment, "event", None)
        if not _event_is_live(event) or not getattr(event, "public_id", None):
            continue
        role_name = getattr(assignment, "role", None)
        if not role_name:
            continue
        public_id = str(event.public_id)
        descriptors.append(
            ContextDescriptor(
                type=ContextType.EVENT,
                public_id=public_id,
                label=f"{getattr(event, 'name', 'Event')} — {str(role_name).replace('_', ' ').title()}",
                role=str(role_name),
                workspace_url=_workspace_url(ContextType.EVENT, public_id),
                permission_lookup_metadata={
                    "event_id": getattr(event, "id", None),
                    "event_role_id": getattr(assignment, "id", None),
                },
            )
        )
    return descriptors


def _driver_contexts(user: Any) -> list[ContextDescriptor]:
    driver = _loaded_driver(user)
    if not driver:
        return []
    tier = getattr(getattr(driver, "verification_tier", None), "value", getattr(driver, "verification_tier", None))
    compliance = getattr(getattr(driver, "compliance_status", None), "value", getattr(driver, "compliance_status", None))
    if str(tier).lower() not in _APPROVED_DRIVER_TIERS:
        return []
    if str(compliance).lower() in _BLOCKED_DRIVER_STATES:
        return []
    public_id = getattr(driver, "public_id", None) or getattr(driver, "driver_code", None)
    if not public_id:
        return []
    return [
        ContextDescriptor(
            type=ContextType.DRIVER,
            public_id=str(public_id),
            label="Transport — Driver",
            role="driver",
            workspace_url=_workspace_url(ContextType.DRIVER, str(public_id)),
            permission_lookup_metadata={"driver_id": getattr(driver, "id", None)},
        )
    ]


def _host_contexts(user: Any) -> list[ContextDescriptor]:
    descriptors: list[ContextDescriptor] = []
    try:
        from app.accommodation.services.identity_service import AccommodationIdentityService

        can_host, _ = AccommodationIdentityService.can_host(user)
    except (ImportError, AttributeError, RuntimeError):
        can_host = False
    profile = getattr(user, "host_profile", None)
    if can_host and (profile is None or (
        getattr(profile, "is_active_host", True) and not getattr(profile, "is_suspended", False)
    )):
        descriptors.append(
            ContextDescriptor(
                type=ContextType.ACCOMMODATION_HOST,
                public_id=_public_id(user),
                label="Accommodation — Host",
                role="accommodation_host",
                workspace_url=_workspace_url(ContextType.ACCOMMODATION_HOST, _public_id(user)),
                permission_lookup_metadata={"host_user_id": getattr(user, "id", None)},
            )
        )

    for membership in _loaded_memberships(user):
        organisation = getattr(membership, "organisation", None)
        if not getattr(membership, "is_active", True) or not _organisation_is_live(organisation):
            continue
        org_id = getattr(organisation, "id", None)
        public_id = getattr(organisation, "org_id", None)
        if not org_id or not public_id:
            continue
        try:
            can_org_host, _ = AccommodationIdentityService.can_org_host(org_id)
        except (AttributeError, RuntimeError):
            can_org_host = False
        if can_org_host:
            descriptors.append(
                ContextDescriptor(
                    type=ContextType.ACCOMMODATION_HOST,
                    public_id=str(public_id),
                    label=f"{getattr(organisation, 'legal_name', 'Organisation')} — Accommodation Host",
                    role="accommodation_host",
                    workspace_url=_workspace_url(ContextType.ACCOMMODATION_HOST, str(public_id)),
                    permission_lookup_metadata={
                        "organisation_id": org_id,
                        "host_organisation_id": org_id,
                    },
                )
            )
    return descriptors


def get_available_contexts(user: Any) -> list[ContextDescriptor]:
    """Return all currently eligible contexts for *user* in stable order."""
    if not _is_live_user(user):
        return []
    contexts = [_personal_context(user)]
    contexts.extend(_global_contexts(user))
    contexts.extend(_organisation_contexts(user))
    contexts.extend(_event_contexts(user))
    contexts.extend(_driver_contexts(user))
    contexts.extend(_host_contexts(user))
    # ``user`` is the baseline personal role, not a second platform persona.
    # ``fan`` is a profile/mode concept, not an operating context. Filtering
    # both also keeps legacy role rows from rendering duplicate switcher items.
    filtered: list[ContextDescriptor] = []
    seen: set[tuple[ContextType, Optional[str], Optional[str]]] = set()
    for context in contexts:
        if context.type is ContextType.PLATFORM and context.role in {"user", "fan"}:
            continue
        key = (context.type, context.public_id, context.role)
        if key in seen:
            continue
        seen.add(key)
        filtered.append(context)
    return filtered


def validate_context(user: Any, requested: Any) -> Optional[ContextDescriptor]:
    """Resolve a request against current assignments, or return ``None``."""
    if not _is_live_user(user):
        return None
    try:
        request = ContextRequest.from_value(requested)
    except ValueError:
        return None
    if request.type == ContextType.PERSONAL:
        if request.public_id is not None or request.role not in (None, "user"):
            return None
        return _personal_context(user)

    for descriptor in get_available_contexts(user):
        if descriptor.type != request.type or descriptor.public_id != request.public_id:
            continue
        if request.role is not None and descriptor.role != request.role:
            continue
        return descriptor
    return None


def clear_active_context() -> ContextDescriptor:
    """Clear only canonical context-selection keys and return Personal."""
    for key in _SESSION_KEYS:
        session.pop(key, None)
    return ContextDescriptor(
        type=ContextType.PERSONAL,
        public_id=None,
        label="Personal",
        role="user",
        workspace_url=_workspace_url(ContextType.PERSONAL, None),
    )


def switch_context(user: Any, requested: Any) -> ContextDescriptor:
    """Validate and store an eligible context without changing assignments."""
    descriptor = validate_context(user, requested)
    if descriptor is None:
        raise ContextSwitchError("requested context is invalid or not assigned")
    session["active_context_type"] = descriptor.type.value
    session["active_context_id"] = descriptor.public_id
    session["active_role"] = descriptor.role
    return descriptor


def get_active_context(user: Any = None) -> ContextDescriptor:
    """Return the selected context after fresh database-backed validation."""
    if user is None:
        from flask_login import current_user

        user = current_user
    if not _is_live_user(user):
        return _personal_context(user)
    context_type = session.get("active_context_type")
    if not context_type:
        # Read-only rollout compatibility for sessions created before the
        # canonical keys existed.  The legacy values are never written here.
        legacy_type = session.get("current_context")
        legacy_id = session.get("current_org_id")
        if legacy_type in {"organization", "organisation"} and legacy_id:
            legacy_descriptor = validate_context(
                user,
                {"type": "organisation", "id": legacy_id},
            )
            if legacy_descriptor is not None:
                return legacy_descriptor
        return _personal_context(user)
    request = {
        "type": context_type,
        "id": session.get("active_context_id"),
        "role": session.get("active_role"),
    }
    descriptor = validate_context(user, request)
    if descriptor is None:
        return clear_active_context()
    return descriptor


def resolve_effective_permissions(
    user: Any,
    context: Optional[ContextDescriptor] = None,
) -> set[str]:
    """Resolve capabilities for a context at request time; never cache in session."""
    context = context or get_active_context(user)
    if context.type == ContextType.PERSONAL:
        from app.auth.helpers import has_global_permission, get_user_global_roles
        from app.identity.models.roles_permission import Permission, Role, RolePermission
        from app.extensions import db

        if "owner" in get_user_global_roles(user):
            return {"*"}
        role_names = get_user_global_roles(user)
        rows = db.session.query(Permission.name).join(RolePermission, RolePermission.permission_id == Permission.id).join(Role, RolePermission.role_id == Role.id).filter(Role.name.in_(role_names)).all()
        return {name for (name,) in rows} if rows else set()

    if context.type == ContextType.PLATFORM:
        for descriptor in get_available_contexts(user):
            if descriptor.type == context.type and descriptor.role == context.role:
                role_id = descriptor.permission_lookup_metadata.get("role_id")
                if context.role == "owner":
                    return {"*"}
                from app.identity.models.roles_permission import Permission, RolePermission
                from app.extensions import db

                rows = db.session.query(Permission.name).join(RolePermission, RolePermission.permission_id == Permission.id).filter(RolePermission.role_id == role_id).all()
                return {name for (name,) in rows} if rows else set()
        return set()

    if context.type == ContextType.ORGANISATION:
        from app.auth.helpers import has_org_permission
        org_id = context.permission_lookup_metadata.get("organisation_id")
        if not org_id:
            return set()
        from app.identity.models.organisation_member import OrganisationMember
        member = OrganisationMember.query.filter_by(user_id=user.id, organisation_id=org_id, is_active=True, is_deleted=False).first()
        if not member:
            return set()
        permissions = set(getattr(member, "effective_permissions", set()) or set())
        return permissions

    if context.type == ContextType.EVENT:
        event_role_id = context.permission_lookup_metadata.get("event_role_id")
        from app.events.models import EventRole

        role = EventRole.query.filter_by(id=event_role_id, user_id=user.id, is_active=True, is_deleted=False).first()
        if not role:
            return set()
        permissions = getattr(role, "permissions", None) or []
        return {str(item) for item in permissions if item}

    if context.type == ContextType.DRIVER:
        return {"transport.driver"}
    if context.type == ContextType.ACCOMMODATION_HOST:
        return {"accommodation.host"}
    return set()


def can_in_context(
    user: Any,
    permission: str,
    context: Optional[ContextDescriptor] = None,
) -> bool:
    """Fail-closed context-aware permission predicate."""
    if not user or not permission:
        return False
    context = context or get_active_context(user)
    permissions = resolve_effective_permissions(user, context)
    return "*" in permissions or permission in permissions


def active_context_required(context_type: ContextType):
    """Require a freshly resolved operating context for a workspace route."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            from flask_login import current_user

            active = get_active_context(current_user)
            if active.type is not context_type:
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({"error": "The requested operating context is not active."}), 403
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def active_context_or_platform_required(context_type: ContextType):
    """Require the workspace context, while allowing platform administration."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            from flask_login import current_user

            active = get_active_context(current_user)
            if active.type not in {context_type, ContextType.PLATFORM}:
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({"error": "The requested operating context is not active."}), 403
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
