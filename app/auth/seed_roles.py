# app/auth/seed_roles.py
"""
Database seed script for roles, permissions, and role-permission links.

All operations are idempotent — safe to run multiple times without
duplicating data.

CLI commands (register via register_commands(app) in create_app):
    flask seed-all            Roles + permissions + links
    flask seed-roles          Roles only
    flask seed-permissions    Permissions only
    flask seed-links          Role-permission links only

Role names defined here are the SINGLE SOURCE OF TRUTH.
Keep in sync with:
    app/auth/helpers.py     (has_global_role checks)
    app/auth/decorators.py  (@require_role guards)
    app/identity/models/user.py  (is_owner, is_super_admin helpers)
"""

from __future__ import annotations

import logging
from typing import Dict, List, NamedTuple

from app.extensions import db
from app.identity.models.roles_permission import (
    Permission,
    Role,
    assign_permission_to_role,
    get_or_create_org_role,
    get_or_create_permission,
    get_or_create_role,
)

log = logging.getLogger(__name__)


# ============================================================================
# ROLE DEFINITIONS - SINGLE SOURCE OF TRUTH
# ============================================================================

class RoleDef(NamedTuple):
    name: str
    level: int
    description: str
    scope: str = "global"


GLOBAL_ROLE_DEFS: List[RoleDef] = [
    RoleDef("owner", 1, "Platform owner — ultimate authority, no restrictions"),
    RoleDef("super_admin", 2, "Full system admin; manages admins, roles, users"),
    RoleDef("admin", 3, "Manages regular users; cannot touch system config"),
    RoleDef("auditor", 4, "Read-only audit log access"),
    RoleDef("compliance_officer", 5, "AML review and compliance management"),
    RoleDef("moderator", 6, "Content moderation and user support"),
    RoleDef("support", 7, "Assists users with issues; read-heavy access"),
    RoleDef("event_manager", 8, "Event management and approval"),
    RoleDef("transport_admin", 9, "Transport system administration"),
    RoleDef("wallet_admin", 10, "Wallet and transaction management"),
    RoleDef("accommodation_admin", 11, "Accommodation property management"),
    RoleDef("tourism_admin", 12, "Tourism content and destination management"),
    RoleDef("fan", 13, "Default end-user; no admin access"),
]

ORG_ROLE_DEFS: List[RoleDef] = [
    RoleDef("org_owner", 1, "Organisation owner — full control", "org"),
    RoleDef("org_admin", 2, "Organisation administrator", "org"),
    RoleDef("finance_manager", 3, "Manages finances and payouts", "org"),
    RoleDef("transport_manager", 3, "Manages drivers, vehicles, and routes", "org"),
    RoleDef("hr_manager", 3, "Manages staff and member records", "org"),
    RoleDef("dispatcher", 4, "Assigns and dispatches drivers to trips", "org"),
    RoleDef("project_manager", 3, "Manages projects within the organisation", "org"),
    RoleDef("org_member", 5, "Standard organisation member", "org"),
    RoleDef("org_guest", 6, "Limited read-only guest access", "org"),
]


# ============================================================================
# PERMISSION DEFINITIONS - SINGLE SOURCE OF TRUTH
# ============================================================================

class PermDef(NamedTuple):
    name: str
    description: str
    roles: List[str]  # Role names that receive this permission


GLOBAL_PERMISSION_DEFS: List[PermDef] = [
    # Users
    PermDef("users.view", "View user list and profiles",
            ["owner", "super_admin", "admin", "support"]),
    PermDef("users.manage", "Create, edit, suspend users",
            ["owner", "super_admin", "admin"]),
    PermDef("users.delete", "Hard-delete user accounts",
            ["owner", "super_admin"]),
    PermDef("users.assign_roles", "Assign and revoke roles",
            ["owner", "super_admin"]),

    # KYC
    PermDef("kyc.view", "View KYC records and queue",
            ["owner", "super_admin", "admin"]),
    PermDef("kyc.approve", "Approve or reject KYC submissions",
            ["owner", "super_admin", "admin"]),

    # Organisations
    PermDef("orgs.view", "View organisation list and details",
            ["owner", "super_admin", "admin", "support"]),
    PermDef("orgs.manage", "Create, edit, suspend organisations",
            ["owner", "super_admin"]),

    # Content
    PermDef("content.view", "View content items and categories",
            ["owner", "super_admin", "admin", "moderator"]),
    PermDef("content.manage", "Create, edit, delete content",
            ["owner", "super_admin", "admin", "moderator"]),
    PermDef("content.moderate", "Review and action flagged content",
            ["owner", "super_admin", "admin", "moderator"]),

    # Submissions
    PermDef("submissions.view", "View submission queue",
            ["owner", "super_admin", "admin", "moderator", "support"]),
    PermDef("submissions.review", "Approve or reject submissions",
            ["owner", "super_admin", "admin", "moderator"]),

    # Wallet
    PermDef("wallet.view", "View wallet balances and transactions",
            ["owner", "super_admin", "admin"]),
    PermDef("wallet.manage", "Adjust limits, enable/disable features",
            ["owner", "super_admin"]),
    PermDef("wallet.approve_withdrawals", "Approve withdrawal requests",
            ["owner", "super_admin"]),

    # Transport
    PermDef("transport.view", "View bookings, drivers, routes",
            ["owner", "super_admin", "admin"]),
    PermDef("transport.manage", "Manage drivers, vehicles, routes",
            ["owner", "super_admin", "admin"]),
    PermDef("transport.settings", "Configure transport module settings",
            ["owner", "super_admin"]),

    # System
    PermDef("system.modules", "Enable or disable platform modules",
            ["owner"]),
    PermDef("system.config", "Edit system-level configuration",
            ["owner"]),
    PermDef("system.health", "View system health and service status",
            ["owner", "super_admin"]),

    # Audit & AML
    PermDef("audit.view", "View audit logs",
            ["owner", "super_admin", "admin", "auditor", "compliance_officer"]),
    PermDef("audit.export", "Export audit log data",
            ["owner", "super_admin", "admin", "auditor"]),
    PermDef("audit.read", "Read-only audit access",
            ["owner", "super_admin", "admin", "auditor", "compliance_officer"]),
    PermDef("aml.view", "View AML flagged transactions",
            ["owner", "super_admin", "compliance_officer"]),
    PermDef("aml.review", "Review AML flagged transactions",
            ["owner", "super_admin", "compliance_officer"]),
    PermDef("aml.resolve", "Resolve AML flagged transactions",
            ["owner", "super_admin"]),

    # Roles / Permissions (meta)
    PermDef("roles.view", "View role definitions",
            ["owner", "super_admin"]),
    PermDef("roles.assign", "Assign or revoke roles",
            ["owner", "super_admin"]),
    PermDef("permissions.manage", "Create permissions and link to roles",
            ["owner"]),
    PermDef("permissions.view", "View permissions",
            ["owner", "super_admin"]),

    # Accommodation
    PermDef("accommodation.search", "Search and view listings",
            ["owner", "super_admin", "admin", "fan"]),
    PermDef("accommodation.view", "View property details",
            ["owner", "super_admin", "admin", "fan"]),
    PermDef("accommodation.book", "Create bookings",
            ["owner", "super_admin", "admin", "fan"]),
    PermDef("accommodation.host", "Create and manage own listings",
            ["owner", "super_admin", "admin"]),
    PermDef("accommodation.manage", "Platform-wide listing management",
            ["owner", "super_admin", "admin"]),
    PermDef("accommodation.verify_host", "Approve host registrations",
            ["owner", "super_admin", "admin"]),
    PermDef("accommodation.payouts", "Manage host payouts",
            ["owner", "super_admin"]),
    PermDef("accommodation.moderate", "Moderate reviews and listings",
            ["owner", "super_admin", "moderator"]),
]

ORG_PERMISSION_DEFS: List[PermDef] = [
    # Finance
    PermDef("org.finance.view", "View org finances",
            ["org_owner", "org_admin", "finance_manager"]),
    PermDef("org.finance.manage", "Manage org finances and payouts",
            ["org_owner", "finance_manager"]),

    # Transport
    PermDef("org.transport.view", "View org transport operations",
            ["org_owner", "org_admin", "transport_manager", "dispatcher"]),
    PermDef("org.transport.manage", "Manage drivers, vehicles, routes",
            ["org_owner", "transport_manager"]),
    PermDef("org.transport.dispatch", "Assign drivers to trips",
            ["org_owner", "transport_manager", "dispatcher"]),

    # Members / HR
    PermDef("org.members.view", "View org member list",
            ["org_owner", "org_admin", "hr_manager"]),
    PermDef("org.members.manage", "Add and remove org members",
            ["org_owner", "org_admin", "hr_manager"]),
    PermDef("org.members.manage_roles", "Assign org-scoped roles",
            ["org_owner", "org_admin"]),

    # Settings
    PermDef("org.settings.view", "View org settings",
            ["org_owner", "org_admin"]),
    PermDef("org.settings.manage", "Edit org settings",
            ["org_owner"]),

    # Projects
    PermDef("org.projects.view", "View org projects",
            ["org_owner", "org_admin", "project_manager"]),
    PermDef("org.projects.manage", "Manage org projects",
            ["org_owner", "project_manager"]),

    # Accommodation
    PermDef("org.accommodation.view", "View org's accommodation listings",
            ["org_owner", "org_admin", "transport_manager"]),
    PermDef("org.accommodation.manage", "Manage org's accommodation listings",
            ["org_owner", "transport_manager"]),
    PermDef("org.accommodation.pricing", "Manage pricing for org listings",
            ["org_owner", "transport_manager", "finance_manager"]),
]


# ============================================================================
# ORGANISATION ROLE TEMPLATES
# ============================================================================

class OrgRoleTemplate(NamedTuple):
    name: str
    description: str
    permissions: List[str]


ORG_ROLE_TEMPLATES: Dict[str, OrgRoleTemplate] = {
    "org_owner": OrgRoleTemplate(
        "org_owner", "Organisation owner",
        [p.name for p in ORG_PERMISSION_DEFS],
    ),
    "org_admin": OrgRoleTemplate(
        "org_admin", "Organisation administrator",
        ["org.finance.view", "org.transport.view",
         "org.members.view", "org.members.manage",
         "org.settings.view"],
    ),
    "finance_manager": OrgRoleTemplate(
        "finance_manager", "Finance manager",
        ["org.finance.view", "org.finance.manage"],
    ),
    "transport_manager": OrgRoleTemplate(
        "transport_manager", "Transport manager",
        ["org.transport.view", "org.transport.manage", "org.transport.dispatch"],
    ),
    "hr_manager": OrgRoleTemplate(
        "hr_manager", "HR manager",
        ["org.members.view", "org.members.manage"],
    ),
    "dispatcher": OrgRoleTemplate(
        "dispatcher", "Trip dispatcher",
        ["org.transport.view", "org.transport.dispatch"],
    ),
    "project_manager": OrgRoleTemplate(
        "project_manager", "Project manager",
        ["org.projects.view", "org.projects.manage"],
    ),
    "org_member": OrgRoleTemplate(
        "org_member", "Standard member",
        ["org.members.view"],
    ),
    "org_guest": OrgRoleTemplate(
        "org_guest", "Guest access",
        [],
    ),
}


# ============================================================================
# SEED FUNCTIONS
# ============================================================================

def seed_roles(*, verbose: bool = True) -> Dict[str, Role]:
    """Seed all global and org-scoped roles. Idempotent."""
    seeded: Dict[str, Role] = {}
    created: List[str] = []

    for r in GLOBAL_ROLE_DEFS:
        role = get_or_create_role(
            r.name,
            scope="global",
            description=r.description,
            level=r.level,
            commit=False,
        )
        seeded[r.name] = role
        if not role.id:
            created.append(r.name)

    for r in ORG_ROLE_DEFS:
        role = get_or_create_org_role(
            r.name,
            description=r.description,
            level=r.level,
            commit=False,
        )
        seeded[r.name] = role
        if not role.id:
            created.append(r.name)

    db.session.commit()

    if verbose:
        if created:
            print(f"✅  Roles created: {', '.join(created)}")
        else:
            print("ℹ️   Roles: all already exist")

    return seeded


def seed_permissions(*, verbose: bool = True) -> Dict[str, Permission]:
    """Seed all global and org-scoped permissions. Idempotent."""
    seeded: Dict[str, Permission] = {}
    created: List[str] = []

    for p in GLOBAL_PERMISSION_DEFS + ORG_PERMISSION_DEFS:
        perm = get_or_create_permission(
            p.name,
            description=p.description,
            commit=False,
        )
        seeded[p.name] = perm
        if not perm.id:
            created.append(p.name)

    db.session.commit()

    if verbose:
        if created:
            print(f"✅  Permissions created: {len(created)}")
        else:
            print("ℹ️   Permissions: all already exist")

    return seeded


def seed_role_permissions(
        roles: Dict[str, Role],
        permissions: Dict[str, Permission],
        *,
        verbose: bool = True,
) -> int:
    """Link each permission to its designated roles. Idempotent."""
    created = 0

    for p_def in GLOBAL_PERMISSION_DEFS + ORG_PERMISSION_DEFS:
        perm = permissions.get(p_def.name)
        if not perm:
            log.warning("Permission %r not found — skipping", p_def.name)
            continue

        for role_name in p_def.roles:
            role = roles.get(role_name)
            if not role:
                log.warning(
                    "Role %r not found when linking permission %r — skipping",
                    role_name, p_def.name,
                )
                continue

            link = assign_permission_to_role(role, perm, commit=False)
            if not link.id:
                created += 1

    db.session.commit()

    if verbose:
        print(f"✅  Role-permission links: {created} new")

    return created


def seed_all(*, verbose: bool = True) -> None:
    """Full idempotent seed: roles → permissions → role-permission links."""
    print("\n── Seeding roles ───────────────────────────────────────")
    roles = seed_roles(verbose=verbose)

    print("\n── Seeding permissions ─────────────────────────────────")
    permissions = seed_permissions(verbose=verbose)

    print("\n── Linking permissions to roles ────────────────────────")
    seed_role_permissions(roles, permissions, verbose=verbose)

    print("\n✅  Seed complete.\n")


# ============================================================================
# CLI REGISTRATION
# ============================================================================

def register_commands(app) -> None:
    """
    Register Flask CLI commands.

    Call this from ``create_app()``::

        from app.auth.seed_roles import register_commands
        register_commands(app)

    Available commands:
        flask seed-all
        flask seed-roles
        flask seed-permissions
        flask seed-links
    """

    @app.cli.command("seed-all")
    def _seed_all():
        """Seed roles, permissions, and role-permission links."""
        with app.app_context():
            seed_all()

    @app.cli.command("seed-roles")
    def _seed_roles():
        """Seed roles only."""
        with app.app_context():
            seed_roles()

    @app.cli.command("seed-permissions")
    def _seed_permissions():
        """Seed permissions only."""
        with app.app_context():
            seed_permissions()

    @app.cli.command("seed-links")
    def _seed_links():
        """Link permissions to roles (requires roles and permissions seeded first)."""
        with app.app_context():
            roles = {r.name: r for r in Role.query.all()}
            permissions = {p.name: p for p in Permission.query.all()}
            seed_role_permissions(roles, permissions)


if __name__ == "__main__":
    seed_all()
