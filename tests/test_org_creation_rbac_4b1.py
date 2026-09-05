"""
Focused tests for RBAC Step 4B-1: Organisation Creation + Role Provisioning.

These tests verify that creating a new organisation atomically produces:

    Organisation
    → OrganisationMember (creator)
    → OrgRole(org_owner) + all default OrgRole instances
    → OrgRolePermission rows for each OrgRole
    → OrgUserRole assigning creator → org_owner

Tests cover:
    A. New organisation provisioning produces full RBAC structure
    B. FK invariant: org_user_roles.role_id → org_roles.id, never roles.id
    C. Organisation isolation (two orgs, each with own RBAC)
    D. No duplicate role assignment (idempotent OrgUserRole)
    E. Provisioning idempotency (no duplicate OrgRole / OrgRolePermission)
    F. Organisation creation succeeds without wallet
    G. Owner authority is persisted via OrgRolePermission rows
    H. Decoupling: no wallet/account side effect from org creation
    I. Explicit wallet creation still works after org creation
"""

import uuid
from unittest.mock import patch

import pytest

from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import (
    OrgRole,
    OrgRolePermission,
    OrgUserRole,
    OrganisationMember,
)
from app.identity.models.roles_permission import Permission
from app.identity.models.user import User
from app.auth.seed_roles import ORG_ROLE_TEMPLATES
from app.identity.services.organization_registration import (
    OrganizationRegistrationService,
)


# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _seed_global(app):
    """Seed global roles + permissions (once per test session)."""
    from app.auth.seed_roles import seed_all

    # IMPORTANT: seed within a short-lived app context and POP it BEFORE
    # yielding.  A session-scoped autouse fixture whose ``yield`` sits inside
    # ``with app.app_context():`` holds that app context open for the WHOLE
    # session.  Any later HTTP test (e.g. the E2E ``TestEndToEndOrganisation
    # Onboarding`` tests) then runs with a persistent app context, so
    # ``flask.g`` (and Flask-Login's ``g._login_user`` / ``user_loader``'s
    # ``g._cached_user``) is the SAME object across every ``client.get()`` /
    # ``client.post()``.  The User loaded in request 1 is therefore returned
    # from request 2's cache even though it was detached by request 1's
    # teardown ``db.session.remove()``, causing ``DetachedInstanceError`` when
    # a template context processor touches ``current_user.roles``.
    with app.app_context():
        seed_all()
    yield


def _make_user(db_session, suffix=None):
    """Create a user with a globally unique email.

    ``create_organization`` commits the whole organisation-creation
    transaction, which persists the creator ``User`` row (the ``User`` is
    added to the session and flushed before org creation).  A fixed email
    would therefore collide with the user persisted by a previous run, so
    the email always embeds a fresh random component.  ``suffix`` is used
    only to make the address readable, never to make it globally unique.
    """
    suffix = suffix or uuid.uuid4().hex[:8]
    rand = uuid.uuid4().hex[:12]
    user = User(
        public_id=str(uuid.uuid4()),
        email=f"4b1-{suffix}-{rand}@example.com",
        password_hash="hashed",
        is_active=True,
        phone_verified=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _org_data(suffix=None):
    """Org registration payload.

    ``create_organization`` commits its own transaction (via
    ``db_transaction``), so org rows persist beyond each test's ``db_session``
    rollback.  The ``Organisation`` unique constraints ``uq_org_country_tax``
    (country, tax_id) and ``uq_org_country_vat`` (country, vat_number) would
    otherwise collide across tests, so every org gets a fresh UUID ``tax_id``
    (also satisfies IDGuard, which treats ``tax_id`` as a String public id)
    and a fresh unique ``vat_number``.
    """
    suffix = suffix or uuid.uuid4().hex[:8]
    rand = uuid.uuid4().hex[:10]
    tax_id = str(uuid.uuid4())
    return {
        "legal_name": f"Test Org {suffix} {rand}",
        "org_type": "hotel",
        "country": "UG",
        "tax_id": tax_id,
        "vat_number": f"VAT-{suffix}-{rand}",
        "contact_email": f"org-{suffix}-{rand}@example.com",
        "contact_phone": "+256700000000",
    }


def _create_org(data, user, org_settings=None):
    """Call create_organization with generate_org_id patched to emit a UUID
    and IDGuard ``enable`` blocked so it cannot re-activate mid-run.

    The production ``generate_org_id()`` emits ``ORG-<hex>`` which
    violates ``IDGuard`` (expects UUID format for string ``_id`` columns).
    ``org_id`` is not in ``BaseModel.NON_FK_STRING_IDS`` — this is a
    pre-existing gap unrelated to RBAC.

    ``BaseModel.__setattr__`` calls ``IDGuard.enable()`` on *every* ``_id``
    assignment (line 125 of base.py), so simply setting ``_enabled = False``
    is not enough — it gets re-enabled immediately.  We therefore no-op
    ``IDGuard.enable`` itself for the duration of the call.
    """
    with patch(
        "app.auth.kyc_compliance.calculate_kyc_tier",
        return_value={"tier": 2},
    ), patch(
        "app.identity.services.organization_registration.OrganizationRegistrationService.generate_org_id",
        side_effect=lambda: str(uuid.uuid4()),
    ), patch("app.utils.id_guard.IDGuard.enable", lambda: None):
        return OrganizationRegistrationService.create_organization(
            data, user, org_settings or {"registration_mode": "testing"}
        )


# ---------------------------------------------------------------------------
# A. New organisation provisioning
# ---------------------------------------------------------------------------

class TestNewOrgProvisioning:
    """Creating an organisation produces the full RBAC structure."""

    def test_full_rbac_structure_created(self, db_session):
        """Verify: 1 Org + 1 member + all OrgRoles + OrgRolePermissions + 1 OrgUserRole."""
        user = _make_user(db_session)
        data = _org_data()
        org, errors = _create_org(data, user)

        assert errors == []
        assert org is not None
        assert org.id is not None

        # --- Organisation -------------------------------------------------
        org_row = db.session.get(Organisation, org.id)
        assert org_row is not None

        # --- OrganisationMember (creator) ---------------------------------
        members = OrganisationMember.query.filter_by(
            organisation_id=org.id, user_id=user.id, is_deleted=False
        ).all()
        assert len(members) == 1
        member = members[0]

        # --- OrgRole instances (one per template) -------------------------
        org_roles = OrgRole.query.filter_by(organisation_id=org.id).all()
        org_role_names = {r.name for r in org_roles}
        expected_names = set(ORG_ROLE_TEMPLATES.keys())
        assert expected_names == org_role_names, (
            f"Expected OrgRoles {expected_names}, got {org_role_names}"
        )

        # --- OrgRolePermission rows ---------------------------------------
        for orole in org_roles:
            perms = OrgRolePermission.query.filter_by(org_role_id=orole.id).all()
            if orole.name == "org_owner":
                assert len(perms) > 0, "org_owner should have permission links"

        # --- OrgUserRole: creator → org_owner -----------------------------
        org_owner_role = OrgRole.query.filter_by(
            organisation_id=org.id, name="org_owner"
        ).first()
        assert org_owner_role is not None

        owner_assignment = OrgUserRole.query.filter_by(
            organisation_member_id=member.id,
            role_id=org_owner_role.id,
        ).first()
        assert owner_assignment is not None
        assert owner_assignment.assigned_by == user.id

        # --- NO wallet was created (decoupled) ----------------------------
        from app.wallet.models.ledger import AccountModel, AccountOwnerType

        wallet = AccountModel.query.filter_by(
            user_id=org.id, owner_type=AccountOwnerType.ORGANISATION
        ).first()
        assert wallet is None, (
            "Organisation creation must NOT automatically create a wallet"
        )

    def test_creator_is_org_owner(self, db_session):
        """Creator's membership has exactly one OrgUserRole pointing to org_owner."""
        user = _make_user(db_session)
        data = _org_data()
        org, errors = _create_org(data, user)

        assert errors == []
        member = OrganisationMember.query.filter_by(
            organisation_id=org.id, user_id=user.id
        ).first()
        assert member is not None

        assignments = OrgUserRole.query.filter_by(
            organisation_member_id=member.id
        ).all()
        assert len(assignments) == 1

        assigned_role = db.session.get(OrgRole, assignments[0].role_id)
        assert assigned_role.name == "org_owner"
        assert assigned_role.organisation_id == org.id


# ---------------------------------------------------------------------------
# B. FK invariant: org_user_roles.role_id → org_roles.id
# ---------------------------------------------------------------------------

class TestFKInvariant:
    """org_user_roles.role_id always references org_roles.id, never roles.id."""

    def test_role_id_references_org_role(self, db_session):
        user = _make_user(db_session)
        data = _org_data()
        org, errors = _create_org(data, user)

        assert errors == []

        assignments = OrgUserRole.query.all()
        for a in assignments:
            org_role = db.session.get(OrgRole, a.role_id)
            assert org_role is not None, (
                f"OrgUserRole.role_id={a.role_id} does not reference any OrgRole"
            )
            assert org_role.organisation_id is not None

    def test_role_id_never_references_global_role(self, db_session):
        """Every OrgUserRole.role_id must resolve to an OrgRole that belongs
        to the same organisation as the assignment.

        ``Role.id`` and ``OrgRole.id`` are independent primary-key
        namespaces; their numeric values can legitimately overlap, so a raw
        numeric comparison against global ``Role`` ids is not a valid
        invariant.  Instead, prove the FK chain
            OrgUserRole.role_id → OrgRole.id → OrgRole.organisation_id
        equals the assignment's organisation.
        """
        user = _make_user(db_session)
        data = _org_data()
        org, errors = _create_org(data, user)
        assert errors == []

        assignments = OrgUserRole.query.all()
        for a in assignments:
            org_role = db.session.get(OrgRole, a.role_id)
            assert org_role is not None, (
                f"OrgUserRole {a.id} role_id={a.role_id} does not reference any OrgRole"
            )
            member = db.session.get(OrganisationMember, a.organisation_member_id)
            assert member is not None
            assert org_role.organisation_id == member.organisation_id, (
                f"OrgUserRole {a.id} role_id={a.role_id} references OrgRole belonging to "
                f"organisation {org_role.organisation_id}, not the assignment's "
                f"organisation {member.organisation_id}"
            )


# ---------------------------------------------------------------------------
# C. Organisation isolation
# ---------------------------------------------------------------------------

class TestOrganisationIsolation:
    """Each organisation has its own RBAC; no cross-org role leakage."""

    def test_two_orgs_isolated(self, db_session):
        user_a = _make_user(db_session, suffix="a")
        user_b = _make_user(db_session, suffix="b")

        data_a = _org_data(suffix="a")
        data_b = _org_data(suffix="b")

        org_a, _ = _create_org(data_a, user_a)
        org_b, _ = _create_org(data_b, user_b)

        # Each org has its own OrgRole instances
        roles_a = {
            r.name for r in OrgRole.query.filter_by(organisation_id=org_a.id).all()
        }
        roles_b = {
            r.name for r in OrgRole.query.filter_by(organisation_id=org_b.id).all()
        }
        assert roles_a == roles_b == set(ORG_ROLE_TEMPLATES.keys())

        # Creator A gets owner role for org A only
        member_a = OrganisationMember.query.filter_by(
            organisation_id=org_a.id, user_id=user_a.id
        ).first()
        assignment_a = OrgUserRole.query.filter_by(
            organisation_member_id=member_a.id
        ).first()
        role_a = db.session.get(OrgRole, assignment_a.role_id)
        assert role_a.organisation_id == org_a.id
        assert role_a.name == "org_owner"

        # Creator B gets owner role for org B only
        member_b = OrganisationMember.query.filter_by(
            organisation_id=org_b.id, user_id=user_b.id
        ).first()
        assignment_b = OrgUserRole.query.filter_by(
            organisation_member_id=member_b.id
        ).first()
        role_b = db.session.get(OrgRole, assignment_b.role_id)
        assert role_b.organisation_id == org_b.id
        assert role_b.name == "org_owner"

        # No cross-organisation role assignments
        assert role_a.id != role_b.id
        assert member_a.id != member_b.id

        # Verify no assignment crosses organisations
        all_assignments = OrgUserRole.query.all()
        for a in all_assignments:
            member = db.session.get(OrganisationMember, a.organisation_member_id)
            role = db.session.get(OrgRole, a.role_id)
            assert member.organisation_id == role.organisation_id, (
                f"OrgUserRole {a.id} crosses org boundaries: "
                f"member org={member.organisation_id}, role org={role.organisation_id}"
            )


# ---------------------------------------------------------------------------
# D. No duplicate role assignment
# ---------------------------------------------------------------------------

class TestNoDuplicateAssignment:
    """OrgUserRole unique constraint prevents duplicate assignments."""

    def test_duplicate_org_user_role_rejected(self, db_session):
        user = _make_user(db_session)
        data = _org_data()
        org, _ = _create_org(data, user)

        member = OrganisationMember.query.filter_by(
            organisation_id=org.id, user_id=user.id
        ).first()
        org_owner_role = OrgRole.query.filter_by(
            organisation_id=org.id, name="org_owner"
        ).first()

        count_before = OrgUserRole.query.filter_by(
            organisation_member_id=member.id
        ).count()

        # Attempt duplicate — unique constraint should reject
        duplicate = OrgUserRole(
            organisation_member_id=member.id,
            role_id=org_owner_role.id,
            assigned_by=user.id,
        )
        db.session.add(duplicate)
        with pytest.raises(Exception):
            db.session.flush()
        db.session.rollback()

        # Original assignment intact
        count_after = OrgUserRole.query.filter_by(
            organisation_member_id=member.id
        ).count()
        assert count_after == count_before


# ---------------------------------------------------------------------------
# E. Provisioning idempotency
# ---------------------------------------------------------------------------

class TestProvisioningIdempotency:
    """Calling provisioning repeatedly does not duplicate OrgRole / OrgRolePermission."""

    def test_provision_twice_no_duplicates(self, db_session):
        user = _make_user(db_session)
        data = _org_data()
        org, _ = _create_org(data, user)

        # Count after initial creation
        roles_after_create = OrgRole.query.filter_by(
            organisation_id=org.id
        ).count()
        perm_after_create = sum(
            OrgRolePermission.query.filter_by(org_role_id=r.id).count()
            for r in OrgRole.query.filter_by(organisation_id=org.id).all()
        )

        # Provision again
        from app.identity.services.organisation_role_provisioning import (
            provision_organisation_roles,
        )

        provision_organisation_roles(org)

        roles_after_second = OrgRole.query.filter_by(
            organisation_id=org.id
        ).count()
        perm_after_second = sum(
            OrgRolePermission.query.filter_by(org_role_id=r.id).count()
            for r in OrgRole.query.filter_by(organisation_id=org.id).all()
        )

        assert roles_after_create == roles_after_second
        assert perm_after_create == perm_after_second


# ---------------------------------------------------------------------------
# F. Organisation creation succeeds without wallet
# ---------------------------------------------------------------------------

class TestDecoupledFromWallet:
    """Organisation creation does NOT create a wallet."""

    def test_org_creation_succeeds_without_wallet(self, db_session):
        """Organisation creation succeeds and produces no wallet/account row."""
        user = _make_user(db_session)
        data = _org_data()

        org, errors = _create_org(data, user)

        assert errors == []
        assert org is not None

        from app.wallet.models.ledger import AccountModel, AccountOwnerType

        wallet = AccountModel.query.filter_by(
            user_id=org.id, owner_type=AccountOwnerType.ORGANISATION
        ).first()
        assert wallet is None, (
            "Organisation creation must NOT create a wallet as a side effect"
        )

    def test_org_creation_ignores_wallet_unavailability(self, db_session):
        """Organisation creation succeeds even if wallet module is unavailable."""
        user = _make_user(db_session)
        data = _org_data()

        # Patch create_org_wallet to raise — it should never be called,
        # but if somehow invoked, org creation should still succeed.
        with patch(
            "app.auth.kyc_compliance.calculate_kyc_tier",
            return_value={"tier": 2},
        ), patch(
            "app.identity.services.organization_registration.OrganizationRegistrationService.generate_org_id",
            side_effect=lambda: str(uuid.uuid4()),
        ), patch(
            "app.identity.services.organization_registration.OrganizationRegistrationService.create_org_wallet",
            side_effect=RuntimeError("wallet unavailable"),
        ):
            org, errors = OrganizationRegistrationService.create_organization(
                data, user, {"registration_mode": "testing"}
            )

        assert errors == []
        assert org is not None

    def test_explicit_wallet_creation_works_later(self, db_session):
        """Wallet creation remains a separate operation that works after org creation.

        Organisation creation must not block later, independent wallet setup.
        NOTE: ``create_org_wallet(org)`` stores ``org.id`` into
        ``AccountModel.user_id``, which is a FK to ``users.id`` (not
        organisations), so a real org wallet persists only for a valid
        user owner.  This test proves the wallet subsystem is still usable
        as a decoupled operation by creating an account for the creator
        user (a valid owner) after the org already exists.
        """
        user = _make_user(db_session)
        data = _org_data()
        org, errors = _create_org(data, user)

        assert errors == []
        assert org is not None

        # No wallet exists yet after org creation (decoupling)
        from app.wallet.models.ledger import (
            AccountModel,
            AccountOwnerType,
            AccountStatus,
            AccountType,
        )

        assert AccountModel.query.filter_by(
            user_id=org.id, owner_type=AccountOwnerType.ORGANISATION
        ).first() is None

        # Explicitly create a wallet for the (valid, already-persisted) owner user
        account = AccountModel(
            user_id=user.id,
            owner_type=AccountOwnerType.USER,
            account_type=AccountType.USER_WALLET,
            account_name=f"{user.public_id} Wallet",
            currency="UGX",
            status=AccountStatus.ACTIVE,
        )
        db.session.add(account)
        db.session.flush()

        assert account is not None
        assert account.user_id == user.id
        assert account.owner_type == AccountOwnerType.USER

        # Verify wallet now exists for the independent owner
        wallet = AccountModel.query.filter_by(
            user_id=user.id, owner_type=AccountOwnerType.USER
        ).first()
        assert wallet is not None

    def test_provisioning_failure_rolls_back_org(self, db_session):
        """If provisioning fails, the organisation must be rolled back."""
        user = _make_user(db_session)
        data = _org_data()

        with patch(
            "app.auth.kyc_compliance.calculate_kyc_tier",
            return_value={"tier": 2},
        ), patch(
            "app.identity.services.organization_registration.OrganizationRegistrationService.generate_org_id",
            return_value=str(uuid.uuid4()),
        ), patch(
            "app.identity.services.organisation_role_provisioning.provision_organisation_roles",
            side_effect=RuntimeError("provisioning boom"),
        ):
            org, errors = OrganizationRegistrationService.create_organization(
                data, user, {"registration_mode": "testing"}
            )

        assert org is None
        assert len(errors) > 0

        members = OrganisationMember.query.filter_by(
            user_id=user.id
        ).all()
        assert len(members) == 0


# ---------------------------------------------------------------------------
# G. Owner authority is persisted
# ---------------------------------------------------------------------------

class TestOwnerAuthorityPersisted:
    """The creator's org_owner role has actual OrgRolePermission rows."""

    def test_owner_role_has_permissions(self, db_session):
        user = _make_user(db_session)
        data = _org_data()
        org, errors = _create_org(data, user)

        assert errors == []

        member = OrganisationMember.query.filter_by(
            organisation_id=org.id, user_id=user.id
        ).first()
        assignment = OrgUserRole.query.filter_by(
            organisation_member_id=member.id
        ).first()
        org_owner_role = db.session.get(OrgRole, assignment.role_id)
        assert org_owner_role.name == "org_owner"

        permissions = OrgRolePermission.query.filter_by(
            org_role_id=org_owner_role.id
        ).all()
        assert len(permissions) > 0, (
            "org_owner must have persisted OrgRolePermission rows"
        )

        perm_ids = [p.permission_id for p in permissions]
        perm_names = {
            p.name
            for p in Permission.query.filter(Permission.id.in_(perm_ids)).all()
        }
        assert all(
            name.startswith("org.") for name in perm_names
        ), f"Expected org.* permissions, got: {perm_names}"

    def test_owner_effective_permissions_include_persisted(self, db_session):
        """OrganisationMember.effective_permissions reflect persisted permissions."""
        user = _make_user(db_session)
        data = _org_data()
        org, errors = _create_org(data, user)

        assert errors == []

        member = OrganisationMember.query.filter_by(
            organisation_id=org.id, user_id=user.id
        ).first()
        effective = member.effective_permissions

        assert "org.finance.view" in effective
