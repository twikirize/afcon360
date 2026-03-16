from app.fan.models import FanProfile

fan_registry = {}

def get_or_create_fan(user_id):
    if user_id in fan_registry:
        return fan_registry[user_id]
    profile = FanProfile(user_id, "Unknown", "UG", "None")
    fan_registry[user_id] = profile
    return profile

def update_fan_profile(user_id, name, nationality, favorite_team, avatar_url=None):
    profile = get_or_create_fan(user_id)
    profile.name = name
    profile.nationality = nationality
    profile.favorite_team = favorite_team
    profile.avatar_url = avatar_url
    return profile