def test_kyc_templates_render():
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
            requirement_icons={'income_source':'bi-cash-stack','bank_reference':'bi-bank','proof_of_address':'bi-house','tin':'bi-hash','national_id':'bi-card-text','passport':'bi-passport','driver_license':'bi-license','selfie':'bi-camera'},
            requirement_helps={'income_source':'Upload proof of income source','bank_reference':'Provide a bank reference letter','proof_of_address':'Upload proof of address','tin':'Submit Tax Identification Number','national_id':'Upload your national ID','passport':'Upload your passport','driver_license':'Upload your driver license','selfie':'Submit a selfie verification'},
        )
        assert 'kyc-requirement-card-list' in html
        assert 'kyc-requirement-card-link' in html
        assert 'kyc-req-icon' in html
        assert 'kyc-req-name' in html
        assert 'kyc-req-help' in html
        assert 'kyc-req-arrow' in html
        assert 'bi-cash-stack' in html
        assert 'bi-bank' in html
        assert 'bi-passport' in html
        assert 'bi-camera' in html
        assert 'Draft saved' in html
        assert 'Upload proof of income source' in html
        assert 'kyc-requirements' in html
        assert 'What you need to complete' in html
        assert 'Your verification decision' in html

        upload_html = render_template(
            'kyc/verify_upload.html',
            show_individual=True, show_organization=False, verified_id_types=set(),
            accepted_id_types=['national_id'], reupload_requests=[],
            organisation_reupload_requests=[], requested_reupload=None,
            preselect_id_type='income_source', user_orgs=[], in_org_context=False, active_org_id=None,
        )
        assert 'kycSaveDraftBtn' in upload_html
        assert 'afcon_kyc_draft_' in upload_html
        assert 'URLSearchParams' in upload_html
