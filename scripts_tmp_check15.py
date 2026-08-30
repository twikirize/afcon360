from app import create_app
from flask import render_template
from jinja2 import Environment, DictLoader

# Test with a minimal template directly using Jinja2
env = Environment(loader=DictLoader({
    'test.html': '''
<div class="kyc-dashboard">
    <h1>Identity verification</h1>
    <p>Test paragraph</p>
    
    <div class="panel mb-4" id="kyc-requirements">
        <div class="panel-header">
            <div class="panel-title">What you need to complete</div>
            <span>{{ fulfillment_percentage }}% complete</span>
        </div>
        <div class="panel-body">
            <ul class="kyc-requirement-card-list" id="kyc-requirement-list">
                {% for requirement in missing_requirements %}
                    <li>{{ requirement }}</li>
                {% endfor %}
            </ul>
        </div>
    </div>
    
    <div class="panel mb-4">
        <div class="panel-header">
            <div class="panel-title">Your verification decision</div>
        </div>
        <div class="panel-body">
            <p>{{ verification_message }}</p>
        </div>
    </div>
    
    <div class="panel mb-4">
        <div class="panel-header">
            <div class="panel-title">Verification Progress</div>
        </div>
    </div>
</div>
'''
}))

template = env.get_template('test.html')
html = template.render(
    fulfillment_percentage=75,
    missing_requirements=['income_source', 'bank_reference'],
    verification_message='ok',
)
print("Minimal Jinja2 test:")
print(html)
print()

# Now test with Flask's render_template but with a simpler template
from flask import Flask
app = Flask(__name__)
app.jinja_env.loader = DictLoader({
    'simple.html': '''
<div class="kyc-dashboard">
    <h1>Identity verification</h1>
    
    <div class="panel mb-4" id="kyc-requirements">
        Panel 1: Requirements
        <ul id="kyc-requirement-list">
            {% for req in missing_requirements %}
                <li>{{ req }}</li>
            {% endfor %}
        </ul>
    </div>
    
    <div class="panel mb-4" id="verification-decision">
        Panel 2: Verification Decision
    </div>
    
    <div class="panel mb-4" id="progress">
        Panel 3: Progress
    </div>
</div>
'''
})

with app.test_request_context('/'):
    html = render_template('simple.html', missing_requirements=['a', 'b'])
    print("Flask simple test:")
    print(html)