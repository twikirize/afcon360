from jinja2 import Environment
env = Environment()
tmpl = '''
<ul class="kyc-requirement-card-list">
{% for requirement in reqs %}
    {% set req_lower = requirement|lower|replace(' ', '_') %}
    {% if req_lower in ['income_source','passport'] %}
        {% set icons = {'income_source':'bi-cash-stack','passport':'bi-passport'} %}
        {% set helps = {'income_source':'Upload proof','passport':'Upload passport'} %}
        <li><a class="kyc-requirement-card-link" data-req="{{ req_lower }}">
            <span class="kyc-req-icon"><i class="bi {{ icons[req_lower] }}"></i></span>
            <span class="kyc-req-name">{{ requirement }}</span>
            <span class="kyc-req-help">{{ helps[req_lower] }}</span>
        </a></li>
    {% else %}
        <li><span>{{ requirement }}</span></li>
    {% endif %}
{% endfor %}
</ul>
'''
t = env.from_string(tmpl)
out = t.render(reqs=['income_source', 'passport', 'other'])
print(out)
print('---')
print('kyc-requirement-card-list' in out)
print('kyc-req-icon' in out)
