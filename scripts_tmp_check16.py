from app import create_app
from flask import render_template
app = create_app()

# Test 1: With requirement_icons/helps as simple dicts
with app.test_request_context('/kyc/?_pane=1'):
    html = render_template(
        'kyc/index.html',
        kyc_info={'tier_name': 'Enhanced', 'verification_status': 'approved'},
        fulfillment_percentage=75, next_tier_name='Premium',
        next_tier_requirements=['phone_verified'],
        missing_requirements=['income_source', 'bank_reference'],
        kyc_stage=3, overall_status='verified',
        verification_message='ok', show_individual=True, show_organization=False,
        requirement_icons={'income_source':'bi-cash-stack','bank_reference':'bi-bank'},
        requirement_helps={'income_source':'Upload proof','bank_reference':'Bank ref'},
    )
    print("Test 1 - simple dicts:")
    for term in ['kyc-requirements', 'Your verification decision', 'Verification Progress', 'What happens next']:
        found = term in html
        print(f'  {term}: {found}')

# Test 2: Without requirement_icons/helps (should cause Undefined)
with app.test_request_context('/kyc/?_pane=1'):
    html = render_template(
        'kyc/index.html',
        kyc_info={'tier_name': 'Enhanced', 'verification_status': 'approved'},
        fulfillment_percentage=75, next_tier_name='Premium',
        next_tier_requirements=['phone_verified'],
        missing_requirements=['income_source', 'bank_reference'],
        kyc_stage=3, overall_status='verified',
        verification_message='ok', show_individual=True, show_organization=False,
    )
    print("\nTest 2 - no icons/helps:")
    for term in ['kyc-requirements', 'Your verification decision', 'Verification Progress', 'What happens next']:
        found = term in html
        print(f'  {term}: {found}')