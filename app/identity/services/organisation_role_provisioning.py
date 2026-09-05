# app/identity/services/organisation_role_provisioning.py
"""
Organisation role provisioning.

Given an existing :class:`Organisation`, this service creates the
organisation's per-organisation role instances (``OrgRole`` rows) derived
from the approved global organisation-role templates, and copies the
permissions belonging to each source global role definition into
``org_role_permissions``.

Architecture (canonical):
    global Role definition (roles, scope="org")
            |
            v
    OrgRole instance (org_roles)  -- template_name -> source global role
            |
            v
    OrgRolePermission (org_role_permissions)  -- copies of global role permissions

The provisioning mechanism is deliberately narrow:
    * It is **provisioning only**.
    * It is idempotent - running it repeatedly never creates duplicate
      ``org_roles`` rows or duplicate ``org_role_permissions`` links.
    * It never mutates or deletes the source global ``Role`` /
      ``Permission`` / ``RolePermission`` definitions.
    * It never creates, deletes, or modifies ``OrgUserRole`` assignments or
      ``OrgMemberPermission`` records.
    * It never touches organisation registration, membership assignment,
      or context authorization.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Set

from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrgRole, OrgRolePermission
from app.identity.models.roles_permission import Permission, Role
from app.auth.seed_roles import ORG_ROLE_TEMPLATES

log = logging.getLogger(__name__)


def _resolve_global_role(template_name: str) -> Optional[Role]:
    """Return the global organisation-scoped ``Role`` for *template_name*.

    The source of truth for an org role's permission set is the global
    ``Role`` row (``scope="org"``) created by ``seed_roles``. If the
    global role definition does not exist, the template cannot be
    provisioned and ``None`` is returned (the caller skips it).
    """
    return Role.query.filter_by(name=template_name, scope="org").first()


def _find_or_create_org_role(
    organisation: Organisation,
    template_name: str,
    description: Optional[str],
):
    """Return the ``OrgRole`` for *organisation* + *template_name* and whether
    it was newly created.

    Idempotent: reuses an existing row when present, otherwise creates and
    flushes a new one.

    Returns:
        A tuple ``(role, was_created)``.
    """
    role = (
        OrgRole.query.filter_by(
            organisation_id=organisation.id,
            name=template_name,
        ).first()
    )

    if role is not None:
        return role, False

    role = OrgRole(
        organisation_id=organisation.id,
        name=template_name,
        template_name=template_name,
        description=description,
    )
    db.session.add(role)
    db.session.flush()
    return role, True


def _link_org_role_permission(
    org_role: OrgRole,
    permission: Permission,
) -> bool:
    """Idempotently link a global ``Permission`` to an ``OrgRole``.

    Returns ``True`` if a new ``OrgRolePermission`` link was created,
    ``False`` if the link already existed.
    """
    existing = (
        OrgRolePermission.query.filter_by(
            org_role_id=org_role.id,
            permission_id=permission.id,
        ).first()
    )
    if existing is not None:
        return False

    db.session.add(
        OrgRolePermission(
            org_role_id=org_role.id,
            permission_id=permission.id,
        )
    )
    return True


def provision_organisation_roles(
    organisation: Organisation,
    *,
    roles: Optional[Set[str]] = None,
    commit: bool = True,
) -> Dict[str, Dict[str, object]]:
    """Provision the organisation's org-role instances from the global
    organisation-role templates.

    Args:
        organisation: The ``Organisation`` to provision roles for.
        roles:        Optional set of template/role names to provision.
                      Defaults to every entry in ``ORG_ROLE_TEMPLATES``.
        commit:       Whether this function should manage its own commit.
                      ``True`` (default) starts its own transaction and
                      commits at the end - used when calling standalone.
                      ``False`` runs as a nested operation (savepoint)
                      inside the caller's transaction and does NOT commit;
                      the outer transaction finalises the work. Use
                      ``commit=False`` when invocation happens inside another
                      ``db_transaction`` to avoid a premature/duplicate commit.

    Returns:
        A summary dict keyed by template name::

            {
                "org_owner": {
                    "status": "created" | "existing",
                    "org_role_id": <id>,
                    "permissions_created": <int>,
                    "permissions_existing": <int>,
                    "skipped": False,
                },
                ...
            }

    Raises:
        ValueError: If *organisation* is ``None``.

    The operation is atomic - it runs inside a single transaction (or
    savepoint when ``commit=False``) and rolls back on failure, so it can
    never leave a partially-created role/permission structure behind.
    """
    if organisation is None or not getattr(organisation, "id", None):
        raise ValueError("A persisted Organisation is required to provision roles.")

    template_names = list(ORG_ROLE_TEMPLATES.keys())
    if roles is not None:
        template_names = [name for name in template_names if name in roles]

    from app.utils.transactions import db_transaction

    results: Dict[str, Dict[str, object]] = {}

    # Only start an independent committing transaction when the caller
    # expects this function to manage its own commit. When commit=False we
    # open a savepoint instead so the work can roll back with the caller's
    # outer transaction and commits only when that outer transaction does.
    if commit:
        context = db_transaction(
            f"Provision organisation roles for org {organisation.id}"
        )
    else:
        context = db.session.begin_nested()

    with context:
        for template_name in template_names:
            template = ORG_ROLE_TEMPLATES[template_name]

            global_role = _resolve_global_role(template_name)
            if global_role is None:
                log.warning(
                    "Organisation role template %r has no global org-scoped Role "
                    "definition (scope='org'); skipping provisioning.",
                    template_name,
                )
                results[template_name] = {
                    "status": "skipped_missing_global_role",
                    "org_role_id": None,
                    "permissions_created": 0,
                    "permissions_existing": 0,
                    "skipped": True,
                }
                continue

            org_role, was_created = _find_or_create_org_role(
                organisation,
                template_name,
                template.description,
            )

            # Collect the source global role's permission names, resolving each
            # to a global Permission row, and link into org_role_permissions.
            permission_names = global_role.permission_names
            created = 0
            existing = 0

            for perm_name in permission_names:
                permission = Permission.query.filter_by(name=perm_name).first()
                if permission is None:
                    log.warning(
                        "Permission %r referenced by global org role %r not found; "
                        "skipping link.",
                        perm_name,
                        template_name,
                    )
                    continue
                if _link_org_role_permission(org_role, permission):
                    created += 1
                else:
                    existing += 1

            results[template_name] = {
                "status": "created" if was_created else "existing",
                "org_role_id": org_role.id,
                "permissions_created": created,
                "permissions_existing": existing,
                "skipped": False,
            }

    return results
