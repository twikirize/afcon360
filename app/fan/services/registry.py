"""Compatibility service for fan profile and KYC lookup workflows.

The registry is an in-process read-through cache only; PostgreSQL remains the
source of truth and all writes use the mapped models and SQLAlchemy session.
"""

from app.extensions import db
from app.fan.models import FanProfile
from app.identity.individuals.individual_verification import IndividualVerification


fan_registry = {}


def clear_fan_registry():
    fan_registry.clear()


def get_or_create_fan(user_id: int):
    if user_id in fan_registry:
        return fan_registry[user_id]

    fan = FanProfile.query.filter_by(user_id=user_id).first()
    created = fan is None
    if created:
        try:
            fan = FanProfile(
                user_id=user_id,
                display_name='Unknown',
                nationality='UG',
                favorite_team='None',
            )
        except TypeError:
            fan = FanProfile(user_id=user_id)
        db.session.add(fan)

    verification = (
        IndividualVerification.query
        .filter_by(user_id=user_id)
        .order_by(IndividualVerification.created_at.desc())
        .first()
    )
    if verification and getattr(fan, 'verification_id', None) is None:
        fan.verification_id = verification.id
        db.session.commit()
    elif created:
        db.session.commit()

    fan_registry[user_id] = fan
    return fan


def get_fan_kyc_status(user_id: int) -> dict:
    fan = get_or_create_fan(user_id)
    return {
        'status': fan.kyc_status,
        'is_verified': fan.is_kyc_verified,
        'verification_id': fan.verification_id,
    }


def link_fan_to_verification(user_id: int, verification_id: int) -> bool:
    verification = IndividualVerification.query.get(verification_id)
    if not verification or verification.user_id != user_id:
        return False

    fan = get_or_create_fan(user_id)
    fan.verification_id = verification_id
    db.session.commit()
    fan_registry[user_id] = fan
    return True


def update_fan_profile(
    user_id: int,
    name=None,
    nationality=None,
    favorite_team=None,
    avatar_url=None,
):
    fan = get_or_create_fan(user_id)
    if name is not None:
        fan.display_name = name
    if nationality is not None:
        fan.nationality = nationality
    if favorite_team is not None:
        fan.favorite_team = favorite_team
    if avatar_url is not None:
        fan.avatar_url = avatar_url
    db.session.commit()
    fan_registry[user_id] = fan
    return fan