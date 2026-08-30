from app import create_app
app = create_app()
env = app.jinja_env
source, name, up_to_date = env.get_source('kyc/index.html')
out = open('scripts_tmp_out.txt', 'w', encoding='utf-8')
out.write('source length: ' + str(len(source)) + '\n')
i = source.find('<ul class="kyc-requirement-card-list"')
out.write('UL block: ' + repr(source[i-20:i+220]) + '\n')
out.write('---\n')
out.write('lstrip_blocks: ' + str(getattr(env, 'lstrip_blocks', 'N/A')) + '\n')
out.write('trim_blocks: ' + str(getattr(env, 'trim_blocks', 'N/A')) + '\n')
out.write('undefined: ' + str(getattr(env, 'undefined', 'N/A')) + '\n')
from jinja2 import StrictUndefined
try:
    t = env.from_string(source, undefined=StrictUndefined)
    rendered = t.render(kyc_info={'tier_name':'Enhanced','verification_status':'approved'},
                   fulfillment_percentage=75, next_tier_name='Premium',
                   next_tier_requirements=['phone_verified'],
                   missing_requirements=['income_source','bank_reference'],
                   kyc_stage=3, overall_status='verified',
                   verification_message='ok', show_individual=True, show_organization=False,
                   records=[], kyc_info2=None)
    out.write('UL in strict render: ' + str('<ul class="kyc-requirement-card-list"' in rendered) + '\n')
    # Check for 'income_source' in rendered
    out.write('income_source in rendered: ' + str('income_source' in rendered) + '\n')
    out.write('kyc-requirement-card-link count: ' + str(rendered.count('kyc-requirement-card-link')) + '\n')
except Exception as e:
    out.write('strict render error: ' + type(e).__name__ + ': ' + str(e) + '\n')
out.close()
