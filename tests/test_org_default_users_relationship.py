"""Regression proof for Phase 1A: Organisation.default_users inverse.

``User.default_org`` declares ``back_populates="default_users"``; the
``Organisation.default_users`` inverse was removed and is restored here.
The check reads the unconfigured mapper properties (no mapper
configuration is triggered, no database I/O occurs), so it is independent
of any other pre-existing missing inverses outside this node's scope.
"""

from app.identity.models.organisation import Organisation
from app.identity.models.user import User


def test_default_org_inverse_pair_is_declared():
    forward = User.__mapper__.get_property(
        "default_org", _configure_mappers=False
    )
    assert forward.back_populates == "default_users"
    inverse = Organisation.__mapper__.get_property(
        "default_users", _configure_mappers=False
    )
    assert inverse.back_populates == "default_org"


def test_default_users_targets_user_via_default_org_id():
    inverse = Organisation.__mapper__.get_property(
        "default_users", _configure_mappers=False
    )
    assert inverse.argument == "User"
    # SQLAlchemy stringifies the declared "User.default_org_id" key against
    # the users table once the class is known.
    assert {
        str(key) for key in inverse._user_defined_foreign_keys
    } == {"users.default_org_id"}
