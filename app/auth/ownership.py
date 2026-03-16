# app/auth/ownership.py
"""
Organisation ownership transfer utilities.

Ownership is represented by the ``org_owner`` OrgRole assignment within
an organisation.  Only one member should hold ``org_owner`` at any time —
this module enforces that invariant during transfers.
"""

from __future__ import annotations

import logging

from app.extensions import db
from app.identity.models.organisation_member import OrgRole, OrgUserRole

log = logging.getLogger(__name__)


def get_org_owner(org_id: int) -> OrgUserRole | None:
    """
    Return the ``OrgUserRole`` record for the current owner of *org_id*,
    or ``None`` if no owner is assigned.
    """
    return (
        OrgUserRole.query
        .join(OrgRole, OrgUserRole.role_id == OrgRole.id)
        .filter(
            OrgRole.name == "org_owner",
            OrgUserRole.organisation_member.has(organisation_id=org_id),
        )
        .first()
    )


def transfer_ownership(
    org_id: int,
    from_member,
    to_member,
    performed_by,
) -> None:
    """
    Transfer ``org_owner`` from *from_member* to *to_member*.

    Args:
        org_id:       The organisation's primary key.
        from_member:  ``OrganisationMember`` of the current owner.
        to_member:    ``OrganisationMember`` of the incoming owner.
        performed_by: ``User`` performing the action (recorded for audit).

    Raises:
        ValueError:   If *from_member* is not the current owner.
        RuntimeError: If the ``org_owner`` role has not been seeded.
    """
    current_owner = get_org_owner(org_id)

    if not current_owner or current_owner.organisation_member_id != from_member.id:
        raise ValueError(
            f"User (member_id={from_member.id}) is not the current owner "
            f"of organisation {org_id}."
        )

    owner_role = OrgRole.query.filter_by(
        name="org_owner",
        organisation_id=org_id,
    ).first()

    if not owner_role:
        raise RuntimeError(
            "org_owner role not found for this organisation. "
            "Run flask seed-all and ensure org roles are provisioned."
        )

    # Revoke from current owner
    db.session.delete(current_owner)

    # Assign to new owner
    new_owner_record = OrgUserRole(
        organisation_member_id=to_member.id,
        role_id=owner_role.id,
        assigned_by=performed_by.id,
    )
    db.session.add(new_owner_record)
    db.session.commit()

    log.info(
        "org_ownership_transferred",
        extra={
            "org_id":       org_id,
            "from_member":  from_member.id,
            "to_member":    to_member.id,
            "performed_by": performed_by.id,
        },
    )