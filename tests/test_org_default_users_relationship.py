"""Regression proof for Phase 1A: Organisation.default_users inverse.

``User.default_org`` declares ``back_populates="default_users"``; the
``Organisation.default_users`` inverse was removed and is restored here.
The check reads the unconfigured mapper properties (no mapper
configuration is triggered, no database I/O occurs), so it is independent
of any other pre-existing missing inverses outside this node's scope.
"""

from sqlalchemy import inspect as sa_inspect

from app.identity.models.organisation import Organisation
from app.identity.models.user import User


def _relationship(model_cls, name):
    # sqlalchemy.inspect() is the public, typed entry point to a mapped
    # class's Mapper; _configure_mappers=False keeps this independent of
    # any other mapper in the registry. getattr() reads Relationship-only
    # attributes that the MapperProperty base type does not declare.
    return sa_inspect(model_cls).get_property(name, _configure_mappers=False)


def test_default_org_inverse_pair_is_declared():
    forward = _relationship(User, "default_org")
    assert getattr(forward, "back_populates") == "default_users"
    inverse = _relationship(Organisation, "default_users")
    assert getattr(inverse, "back_populates") == "default_org"


def test_default_users_targets_user_via_default_org_id():
    inverse = _relationship(Organisation, "default_users")
    assert getattr(inverse, "argument") == "User"
    # SQLAlchemy stringifies the declared "User.default_org_id" key against
    # the users table once the class is known.
    assert {
        str(key) for key in getattr(inverse, "_user_defined_foreign_keys")
    } == {"users.default_org_id"}
