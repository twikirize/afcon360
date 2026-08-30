from app import create_app
from flask import render_template
app = create_app()
with app.test_request_context('/kyc/?_pane=1'):
    html = render_template(
        'kyc/index.html',
        kyc_info={'tier_name': 'Enhanced', 'verification_status': 'approved'},
        fulfillment_percentage=75, next_tier_name='Premium',
        next_tier_requirements=['phone_verified'],
        missing_requirements=['income_source', 'bank_reference', 'proof_of_address', 'tin', 'national_id', 'passport', 'driver_license', 'selfie'],
        kyc_stage=3, overall_status='verified',
        verification_message='ok', show_individual=True, show_organization=False,
        requirement_icons={'income_source':'bi-cash-stack','bank_reference':'bi-bank','proof_of_address':'bi-house','tin':'bi-hash','national_id':'bi-card-text','passport':'bi-passport','driver_license':'bi-license','selfie':'bi-camera'},
        requirement_helps={'income_source':'Upload proof of income source','bank_reference':'Provide a bank reference letter','proof_of_address':'Upload proof of address','tin':'Submit Tax Identification Number','national_id':'Upload your national ID','passport':'Upload your passport','driver_license':'Upload your driver license','selfie':'Submit a selfie verification'},
    )
print(html)