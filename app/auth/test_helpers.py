from app.identity.models.user import User
from app.extensions import db

def create_user_with_role(role_name):
    """Create a test user with a specific role"""
    from app.auth.roles import get_role
    
    user = User(
        username=f"test_{role_name}",
        email=f"{role_name}@test.com",
        is_active=True
    )
    user.set_password("testpass123")
    
    role = get_role(role_name)
    if role:
        user.roles.append(role)
    
    db.session.add(user)
    db.session.commit()
    
    return user
