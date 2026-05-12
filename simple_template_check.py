#!/usr/bin/env python
"""
Simple template verification
"""

def check_template():
    with open('templates/admin/trust_settings.html', 'r') as f:
        content = f.read()
    
    print('Template Content Analysis:')
    print('Template exists and is readable')
    print('Template size:', len(content), 'characters')
    
    # Check for key dynamic elements
    elements = [
        'settings.high_trust_threshold',
        'settings.medium_trust_threshold', 
        'settings.enable_role_bypass',
        'settings.enable_kyc_boost',
        'settings.enable_account_age_boost',
        'settings.enable_event_history_boost',
        'settings.enable_trust_based_publishing',
        'user_analyses',
        'trust-settings',
        'threshold-slider',
        'toggle-switch'
    ]
    
    print('Dynamic Elements Found:')
    for element in elements:
        found = element in content
        status = 'OK' if found else 'MISSING'
        print(f'{status}: {element} = {found}')
    
    # Check for JavaScript functions
    js_functions = ['updateThresholdDisplay', 'testThresholds', 'analyzeUser', 'resetSettings']
    print('JavaScript Functions:')
    for func in js_functions:
        found = func in content
        status = 'OK' if found else 'MISSING'
        print(f'{status}: {func} = {found}')
    
    # Check for template sections
    sections = [
        'trust-level-indicator',
        'user-analysis-card', 
        'settings-section',
        'modal',
        'btn',
        'fas fa-'
    ]
    
    print('Template Sections:')
    for section in sections:
        found = section in content
        status = 'OK' if found else 'MISSING'
        print(f'{status}: {section} = {found}')
    
    print('Template verification complete!')
    return True

if __name__ == "__main__":
    check_template()
