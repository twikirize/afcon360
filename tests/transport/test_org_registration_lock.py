"""SUPPLY-LOCK-SITE-1048: organisation-registration lock regression.

Covers three defects fixed together in
``ProviderService.register_organisation_transport``
(app/transport/services/provider_service.py):

  A. ``sanitize_input`` was called on the whole mapping instead of per
     string value (it operates on strings only).
  B. ``validate_organisation_transport`` returns ``Tuple[bool, List[str]]``
     but the caller used dict-style access (``['valid']`` / ``['errors']``).
  C. ``with_cache_lock`` (a decorator factory) was used as a context
     manager; the fix reuses the module-local ``_redis_lock`` context
     manager (same precedent as the driver-registration site).

Pre-flight notes (recorded, not worked around):

  * There is no ``app/organisation`` package in this tree — only
    ``app/identity/models/organisation.py``. ``get_organisation_identity``
    therefore fail-closes with ``ServiceUnavailableError``. This file
    injects a fake ``app.organisation.services.registry_service`` module
    (returning an active/verified/business-registered identity) into
    ``sys.modules`` so the REAL ``register_organisation_transport`` body
    is exercised. No production code is stubbed; ``sanitize_input``,
    ``validate_organisation_transport`` and ``_redis_lock`` all run for
    real.
  * Email uses ``@gmail.com``: ``email_validator`` performs a
    deliverability check and rejects non-existent domains (probe-verified
    during SUPPLY-00).
  * ``@rate_limit`` here is the in-memory decorator in
    ``app/utils/rate_limiting.py`` (not Redis-backed), so the Redis-failure
    test scopes its mock to ``redis_client.set`` only and clears the
    in-memory rate-limit store before each call.
"""
import sys
import types
import uuid

import pytest

from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organization_types import OrganizationType
from app.identity.models.user import User
from app.transport.models import OrganisationTransportProfile
from app.transport.services.provider_service import get_provider_service
from app.utils.exceptions import ConflictError


# ---------------------------------------------------------------------------
# Fixtures / helpers (minimal, local: no Organisation helper exists in
# tests/conftest.py or tests/test_transport_concurrent_claim.py to reuse)
# ---------------------------------------------------------------------------

@pytest.fixture()
def _org_transport_env(app, monkeypatch):
    """Enable all feature flags and fake the missing organisation registry.

    Patches ``SettingsService.is_feature_enabled`` to True (same approach
    as tests/transport/test_supply00_override.py T7/T8) so
    ``@feature_enabled('provider_onboarding_enabled')`` passes and
    eligibility checks see a verified organisation.
    """
    from app.transport.services.settings_service import SettingsService
    monkeypatch.setattr(
        SettingsService,
        "is_feature_enabled",
        staticmethod(lambda key, default=False: True),
    )

    registry_mod = types.ModuleType(
        "app.organisation.services.registry_service"
    )

    class OrganisationRegistry:
        @staticmethod
        def get_organisation(organisation_id):
            return {
                "status": "active",
                "verified": True,
                "business_registered": True,
                "name": "Test Transport Co",
                "type": "transport_company",
                "registration_number": "REG-12345",
            }

    registry_mod.OrganisationRegistry = OrganisationRegistry
    services_pkg = types.ModuleType("app.organisation.services")
    services_pkg.registry_service = registry_mod
    org_pkg = types.ModuleType("app.organisation")
    org_pkg.services = services_pkg
    monkeypatch.setitem(
        sys.modules, "app.organisation", org_pkg
    )
    monkeypatch.setitem(
        sys.modules, "app.organisation.services", services_pkg
    )
    monkeypatch.setitem(
        sys.modules,
        "app.organisation.services.registry_service",
        registry_mod,
    )
    yield


def _create_org_owner(app):
    """Create a user holding the owner role (satisfies @require_permission
    via the owner bypass in app/utils/security.py). Returns the user id."""
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import UserRole

    uid = uuid.uuid4().hex[:8]
    with app.app_context():
        user = User(
            username=f'org_owner_{uid}',
            email=f'org_owner_{uid}@test.example.com',
            is_verified=True,
            is_active=True,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.flush()
        owner_role = get_or_create_role('owner', level=1)
        db.session.add(UserRole(user_id=user.id, role_id=owner_role.id))
        db.session.commit()
        return user.id


def _create_organisation(app):
    """Create a transport-capable Organisation row. Returns the org id.

    Uses the legacy ``business_category`` enum fallback (no FK row needed
    in ``organisation_types``) so ``can_manage_transport()`` is True via
    ``OrganizationType.TRANSPORT_COMPANY``.
    """
    uid = uuid.uuid4().hex[:8]
    with app.app_context():
        org = Organisation(
            org_id=f'ORG-1048-{uid}',
            slug=f'test-transport-1048-{uid}',
            country='KE',
            legal_name=f'Test Transport Co {uid}',
            business_category=OrganizationType.TRANSPORT_COMPANY,
            is_active=True,
        )
        db.session.add(org)
        db.session.commit()
        return org.id


def _valid_org_payload(uid):
    """Minimum payload accepted by validate_organisation_transport and the
    OrganisationTransportProfile constructor."""
    return {
        # Required by validator:
        'organisation_name': 'Test Transport Co',
        'registration_number': 'REG-12345',
        # NOTE: email_validator checks deliverability; only real domains
        # (e.g. gmail.com) pass. afcon360.com / example domains do not.
        'contact_email': f'ops_{uid}@gmail.com',
        'phone_number': '+256700111222',
        'country': 'KE',
        # Required by constructor (not validated — latent Defect D, out of
        # scope for this node):
        'registration_type': 'transport_company',
    }


def _register(app, org_id, payload, user_id, request_id):
    """Call the REAL registration path with auth + isolation housekeeping.

    Follows the T7/T8 pattern: Flask-Login login inside a request context
    (satisfies @require_permission), in-memory rate-limit and idempotency
    stores cleared so each call reaches the function body.
    """
    from flask_login import login_user
    from app.utils.idempotency import clear_idempotency_keys
    from app.utils.rate_limiting import clear_rate_limits

    clear_idempotency_keys()
    clear_rate_limits()
    with app.test_request_context():
        with app.app_context():
            login_user(db.session.get(User, user_id))
            return get_provider_service().register_organisation_transport(
                organisation_id=org_id,
                data=payload,
                user_id=user_id,
                request_id=request_id,
            )


def _cleanup(app, org_id, user_id):
    """Best-effort removal of rows created by a test (profile, org, user)."""
    with app.app_context():
        OrganisationTransportProfile.query.filter_by(
            organisation_id=org_id
        ).delete(synchronize_session=False)
        db.session.commit()
        org = db.session.get(Organisation, org_id)
        if org is not None:
            db.session.delete(org)
            db.session.commit()
        user = db.session.get(User, user_id)
        if user is not None:
            db.session.delete(user)
            db.session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_org_registration_path_completes(app, _org_transport_env):
    """Full path reaches DB layer and returns a profile — proves A, B, C
    are all gone."""
    user_id = _create_org_owner(app)
    org_id = _create_organisation(app)
    try:
        uid = uuid.uuid4().hex[:8]
        result = _register(
            app, org_id, _valid_org_payload(uid), user_id,
            request_id=f't-lock-1048-a-{uid}',
        )
        assert result['success'] is True
        assert 'profile_id' in result['data']
    finally:
        _cleanup(app, org_id, user_id)


def test_org_registration_duplicate_prevented(app, _org_transport_env):
    """Second registration for the same org is refused by the DB/contract."""
    user_id = _create_org_owner(app)
    org_id = _create_organisation(app)
    try:
        uid = uuid.uuid4().hex[:8]
        _register(
            app, org_id, _valid_org_payload(uid), user_id,
            request_id=f't-lock-1048-b1-{uid}',
        )

        # Different request_id -> different idempotency key -> real path
        # executes a second time (the first attempt's result is not returned
        # from the idempotency cache).
        from app.utils.idempotency import clear_idempotency_keys
        from app.utils.rate_limiting import clear_rate_limits
        from flask_login import login_user

        clear_idempotency_keys()
        clear_rate_limits()
        with app.test_request_context():
            with app.app_context():
                login_user(db.session.get(User, user_id))
                with pytest.raises(ConflictError):
                    get_provider_service().register_organisation_transport(
                        organisation_id=org_id,
                        data=_valid_org_payload(uid),
                        user_id=user_id,
                        request_id=f't-lock-1048-b2-{uid}',
                    )
    finally:
        _cleanup(app, org_id, user_id)


def test_org_registration_survives_redis_failure(app, _org_transport_env,
                                                 monkeypatch):
    """_redis_lock is best-effort: Redis failure must not block registration,
    and the DB invariant must still hold."""
    user_id = _create_org_owner(app)
    org_id = _create_organisation(app)
    try:
        # Simulate Redis unavailability (scoped to the redis client only —
        # the in-memory @rate_limit decorator and idempotency store are
        # unaffected). NOTE: the client is patched at
        # ``app.extensions.redis_client`` (module attribute) because
        # ``LazyRedis.__getattr__`` raises RuntimeError (not
        # AttributeError) when unconfigured, so setattr directly on the
        # LazyRedis instance cannot be used.
        class _DownRedis:
            def set(self, *a, **kw):
                raise RuntimeError('redis down')

            def delete(self, *a, **kw):
                return 0

        monkeypatch.setattr(
            'app.extensions.redis_client', _DownRedis(), raising=False
        )

        uid = uuid.uuid4().hex[:8]
        result = _register(
            app, org_id, _valid_org_payload(uid), user_id,
            request_id=f't-lock-1048-c1-{uid}',
        )
        assert result['success'] is True

        # Duplicate still refused even without the lock.
        from app.utils.idempotency import clear_idempotency_keys
        from app.utils.rate_limiting import clear_rate_limits
        from flask_login import login_user

        clear_idempotency_keys()
        clear_rate_limits()
        with app.test_request_context():
            with app.app_context():
                login_user(db.session.get(User, user_id))
                with pytest.raises(ConflictError):
                    get_provider_service().register_organisation_transport(
                        organisation_id=org_id,
                        data=_valid_org_payload(uid),
                        user_id=user_id,
                        request_id=f't-lock-1048-c2-{uid}',
                    )
    finally:
        _cleanup(app, org_id, user_id)
