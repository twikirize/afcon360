def test_debug():
    from app import create_app
    from flask import render_template
    app = create_app()
    with app.test_request_context('/kyc/'):
        html = render_template(
            'kyc/verify_upload.html',
            show_individual=True, show_organization=False,
            verified_id_types=set(),
            accepted_id_types=['national_id', 'passport', 'driver_license'],
            reupload_requests=[], organisation_reupload_requests=[],
            requested_reupload=None, preselect_id_type='income_source',
            user_orgs=[], in_org_context=False, active_org_id=None,
        )
    for token in ['individualForm', 'handlePresignedUpload', 'kyc-submit-btn',
                  'kycSaveDraftBtn', 'afcon_kyc_draft_', 'script']:
        print(token, '->', token in html)
    # show last 400 chars
    print('TAIL:', repr(html[-400:]))
