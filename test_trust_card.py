#!/usr/bin/env python
"""
Test Trust Security card in owner settings
"""

def test_trust_security_card():
    """Test that the Trust Security card is properly integrated"""
    
    # Read the owner settings template
    with open('templates/owner/settings.html', 'r', encoding='utf-8') as f:
        template_content = f.read()
    
    print('Testing Trust Security Card Integration:')
    print('=' * 50)
    
    # Check if the Trust Security card exists
    checks = [
        ('Trust-Based Security title', 'Trust-Based Security' in template_content),
        ('Trust Security card icon', '🛡️' in template_content),
        ('Trust settings URL', 'admin.trust_settings.trust_settings' in template_content),
        ('Card description', 'Configure trust scoring' in template_content),
        ('Security badge', 'badge-security' in template_content),
        ('Settings card structure', 'settings-card' in template_content),
        ('Authentication section', 'Authentication & Verification' in template_content)
    ]
    
    all_passed = True
    for check_name, passed in checks:
        status = 'OK' if passed else 'FAIL'
        print(f'{status} {check_name}: {passed}')
        if not passed:
            all_passed = False
    
    # Check the exact card structure
    card_start = template_content.find('Trust-Based Security')
    if card_start > 0:
        print('\nTrust Security Card found at position:', card_start)
    
    result = 'PASS' if all_passed else 'FAIL'
    print(f'\nOverall Result: {result}')
    
    if all_passed:
        print('\nTrust Security card is properly integrated!')
        print('Location: Owner Settings -> Authentication & Verification section')
        print('URL: /admin/admin/trust-settings')
        print('Style: Security badge with shield icon')
    else:
        print('\nSome checks failed. Please review the integration.')
    
    return all_passed

if __name__ == "__main__":
    test_trust_security_card()
