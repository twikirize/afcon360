from app import create_app
app = create_app()
with app.app_context():
    from app.identity.services.provider_participation_service import get_individual_intention, is_capability_operational, ProviderCapabilityCode, ProviderCapabilityStatus
    from app.identity.models.provider_participation import ProviderParticipation
    from sqlalchemy import inspect, create_engine
    
    engine = create_engine(app.extensions['sqlalchemy'].engine.url)
    conn = engine.connect()
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print('Tables:', tables)
    
    # Check provider_participation table
    if 'provider_participation' in tables:
        result = conn.execute('SELECT * FROM provider_participation').fetchall()
        print('\nProvider participations:')
        for row in result:
            print(f'  user_id={row.user_id}, capability_code={row.capability_code}, status={row.status}')
    
    # Check user
    from app.identity.models.user import User
    users = User.query.limit(5).all()
    for user in users:
        print(f'\nUser {user.id}: is_fully_verified={user.is_fully_verified()}, profile_completed={getattr(user.profile, "profile_completed", "N/A") if user.profile else None}')
        # Check capability
        cap = is_capability_operational('individual', user.id, ProviderCapabilityCode.ACCOMMODATION.value)
        print(f'  Accommodation capability operational: {cap}')