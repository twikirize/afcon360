from app import create_app
from flask import render_template
app = create_app()
with app.test_request_context('/kyc/'):
    html = render_template(
        'kyc/index.html',
        kyc_info={'tier_name':'Enhanced','verification_status':'approved'},
        fulfillment_percentage=75, next_tier_name='Premium',
        next_tier_requirements=['phone_verified'],
        missing_requirements=['income_source','bank_reference','proof_of_address','tin','national_id','passport','driver_license','selfie'],
        kyc_stage=3, overall_status='verified',
        verification_message='ok', show_individual=True, show_organization=False,
    )
f = open('scripts_tmp_out.txt','w',encoding='utf-8')
f.write('len: '+str(len(html))+'\n')
f.write('count ul: '+str(html.count('<ul'))+'\n')
f.write('count kyc-requirement-card-list: '+str(html.count('kyc-requirement-card-list'))+'\n')
f.write('count kyc-req-icon: '+str(html.count('kyc-req-icon'))+'\n')
f.write('count kyc-requirement-card-link: '+str(html.count('kyc-requirement-card-link'))+'\n')
# find all ul tags
import re
for m in re.finditer(r'<ul[^>]*>', html):
    f.write('ul: '+repr(m.group())+'\n')
f.write('--- first 200 chars after resume ---')
i = html.find('resume')
f.write(repr(html[i:i+200]) if i>=0 else 'NOT FOUND')
f.write('\n--- around your verification ---')
i = html.find('Your verification')
f.write(repr(html[i:i+200]) if i>=0 else 'NOT FOUND')
f.write('\n--- draft saved context ---')
i = html.find('Draft saved')
f.write(repr(html[max(0,i-200):i+50]) if i>=0 else 'NOT FOUND')
f.close()
