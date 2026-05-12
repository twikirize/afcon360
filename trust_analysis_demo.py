from app import create_app
from app.identity.models.user import User
from app.events.trust_service import EventTrustService

app = create_app()
with app.app_context():
    users = User.query.limit(5).all()
    
    print('SECURITY/TRUST ANALYSIS BY USER:')
    print('=' * 80)
    
    for user in users:
        analysis = EventTrustService.get_trust_analysis(user)
        factors = analysis['factors']
        
        print(f'\nUser: {user.username}')
        print(f'Trust Level: {analysis["trust_level"].upper()}')
        print(f'Auto-Publish: {analysis["should_auto_publish"]}')
        
        # Calculate estimated score
        score = 0
        if 'admin' in str(factors['roles']):
            score += 40
        elif 'event_manager' in str(factors['roles']) or 'moderator' in str(factors['roles']):
            score += 25
        
        if factors['kyc_level'] >= 2:
            score += 30
        elif factors['kyc_level'] >= 1:
            score += 15
            
        if factors['is_verified']:
            score += 15
            
        if factors['account_age_days'] >= 30:
            score += 15
        elif factors['account_age_days'] >= 7:
            score += 8
            
        if factors['successful_events'] >= 5:
            score += 20
        elif factors['successful_events'] >= 2:
            score += 10
        
        print(f'Estimated Score: ~{score} points')
        print(f'Score Breakdown:')
        print(f'  - Roles: {factors["roles"]}')
        print(f'  - KYC Level: {factors["kyc_level"]}')
        print(f'  - Email Verified: {factors["is_verified"]}')
        print(f'  - Account Age: {factors["account_age_days"]} days')
        print(f'  - Successful Events: {factors["successful_events"]}')
        
        if analysis['trust_level'] == 'high':
            print('  [HIGH] Security Level: HIGH - Full access, auto-publish immediately')
        elif analysis['trust_level'] == 'medium':
            print('  [MEDIUM] Security Level: MEDIUM - Limited access, auto-publish after approval')
        else:
            print('  [LOW] Security Level: LOW - Restricted access, manual publishing required')
        print('-' * 80)
