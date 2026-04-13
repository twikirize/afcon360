from app.fan.models import FanProfile
from app.identity.individuals.individual_verification import IndividualVerification
from app.extensions import db

fan_registry = {}

def get_or_create_fan(user_id):
    if user_id in fan_registry:
        return fan_registry[user_id]

    # Try to get existing fan profile from database
    profile = FanProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        # Create a new fan profile
        profile = FanProfile(
            user_id=user_id,
            display_name="Unknown",
            nationality="UG",
            favorite_team="None"
        )
        db.session.add(profile)
        db.session.commit()

    # Check for existing KYC verification
    verification = IndividualVerification.query.filter_by(user_id=user_id).order_by(
        IndividualVerification.requested_at.desc()
    ).first()

    if verification:
        profile.verification_id = verification.id
        db.session.commit()

    fan_registry[user_id] = profile
    return profile

def update_fan_profile(user_id, name, nationality, favorite_team, avatar_url=None):
    profile = get_or_create_fan(user_id)
    profile.display_name = name
    profile.nationality = nationality
    profile.favorite_team = favorite_team
    profile.avatar_url = avatar_url
    db.session.commit()
    return profile

def get_fan_kyc_status(user_id):
    """Get KYC status for a fan"""
    profile = get_or_create_fan(user_id)
    return {
        'status': profile.kyc_status,
        'is_verified': profile.is_kyc_verified,
        'verification_id': profile.verification_id
    }

def link_fan_to_verification(user_id, verification_id):
    """Link a fan profile to a specific verification"""
    profile = get_or_create_fan(user_id)
    verification = IndividualVerification.query.get(verification_id)
    if verification and verification.user_id == user_id:
        profile.verification_id = verification_id
        db.session.commit()
        return True
    return False

def clear_fan_registry():
    """Clear the fan registry cache (useful for testing)"""
    global fan_registry
    fan_registry.clear()
