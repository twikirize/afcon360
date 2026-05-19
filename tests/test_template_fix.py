#!/usr/bin/env python
"""
Test template rendering for trust settings with correct path
"""

from app import create_app
from app.events.settings_model import EventSettings
from app.events.trust_service import EventTrustService

def test_template_rendering():
    """Test if trust settings template captures all dynamic values"""
    app = create_app()
    
    with app.app_context():
        # Get current settings
        settings = EventSettings.get()
        
        # Get sample user analyses
        from app.identity.models.user import User
        sample_users = User.query.limit(3).all()
        user_analyses = []
        
        for user in sample_users:
            analysis = EventTrustService.get_trust_analysis(user)
            user_analyses.append(analysis)
        
        # Test template rendering
        with app.test_request_context():
            template = app.jinja_env.get_or_select_template('admin/trust_settings.html')
            rendered = template.render(settings=settings, user_analyses=user_analyses)
            
            print('Template Rendering Test Results:')
            print('Settings captured in template:')
            print(f'   enable_trust_based_publishing: {settings.enable_trust_based_publishing}')
            print(f'   high_trust_threshold: {settings.high_trust_threshold}')
            print(f'   medium_trust_threshold: {settings.medium_trust_threshold}')
            print(f'   enable_role_bypass: {settings.enable_role_bypass}')
            print(f'   enable_kyc_boost: {settings.enable_kyc_boost}')
            print(f'   enable_account_age_boost: {settings.enable_account_age_boost}')
            print(f'   enable_event_history_boost: {settings.enable_event_history_boost}')
            
            print('\nUser analyses captured:')
            for analysis in user_analyses:
                username = analysis['username']
                trust_level = analysis['trust_level']
                should_auto = analysis['should_auto_publish']
                print(f'   {username}: {trust_level} (auto-publish: {should_auto})')
            
            # Check if template contains the expected values
            high_found = str(settings.high_trust_threshold) in rendered
            medium_found = str(settings.medium_trust_threshold) in rendered
            
            print(f'\n✅ High threshold value found: {high_found}')
            print(f'✅ Medium threshold value found: {medium_found}')
            
            # Check for toggle states
            role_bypass_found = 'name="enable_role_bypass"' in rendered
            print(f'✅ Role bypass toggle found: {role_bypass_found}')
            
            # Check for all dynamic elements
            dynamic_elements = [
                'enable_trust_based_publishing',
                'high_trust_threshold', 
                'medium_trust_threshold',
                'enable_role_bypass',
                'enable_kyc_boost',
                'enable_account_age_boost',
                'enable_event_history_boost'
            ]
            
            all_found = True
            for element in dynamic_elements:
                found = element in rendered
                status = '✅' if found else '❌'
                print(f'{status} {element} found: {found}')
                if not found:
                    all_found = False
                    
            print(f'\nTemplate rendered successfully ({len(rendered)} characters)')
            if all_found:
                print('✅ All dynamic values are properly captured!')
            else:
                print('❌ Some dynamic values are missing!')
            
            return all_found

if __name__ == "__main__":
    test_template_rendering()
