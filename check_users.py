from app import create_app
app = create_app()
with app.app_context():
    from app.identity.models.user import User
    from app.auth.context import get_active_context, ContextType
    from app.accommodation.services.identity_service import AccommodationIdentityService
    
    # Get all users
    users = User.query.all()
    for user in users:
        print(f'\nUser {user.id}: {user.email}')
        print(f'  is_active: {user.is_active}, is_deleted: {user.is_deleted}')
        print(f'  is_fully_verified: {user.is_fully_verified()}')
        pcompl = getattr(user.profile, 'profile_completed', 'N/A') if user.profile else None
        print(f'  profile_completed: {pcompl}')
        
        # Check can_host
        can_host, reason = AccommodationIdentityService.can_host(user)
        print(f'  can_host: {can_host}, reason: {reason}')
        
        # Check active context
        active = get_active_context(user)
        print(f'  active_context.type: {active.type if active else None}')
        print(f'  active_context.public_id: {active.public_id if active else None}')
        
        # Check host identity
        host_info = AccommodationIdentityService.get_host_identity(user)
        print(f'  host_info.type: {host_info["type"] if host_info else None}')