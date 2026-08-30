from app import create_app
from flask import render_template
app = create_app()
with app.test_request_context('/kyc/'):
    html = render_template(
        'kyc/index.html',
        kyc_info={'tier_name': 'Enhanced', 'verification_status': 'approved'},
        fulfillment_percentage=75, next_tier_name='Premium',
        next_tier_requirements=['phone_verified'],
        missing_requirements=['income_source', 'bank_reference', 'proof_of_address', 'tin', 'national_id', 'passport', 'driver_license', 'selfie'],
        kyc_stage=3, overall_status='verified',
        verification_message='ok', show_individual=True, show_organization=False,
    )
    a = html.find('resume exactly where')
    b = html.find('Your verification decision')
    print('BETWEEN:', repr(html[a:b]) if a>=0 and b>=0 else 'NOT FOUND a=%s b=%s' % (a,b))
    print('count kyc-requirement-card-list:', html.count('kyc-requirement-card-list'))
    print('count <ul:', html.count('<ul'))
