import os
os.environ['FLASK_ENV'] = 'development'
os.environ['APP_ENV'] = 'local'
os.environ['FLASK_SSL'] = 'none'

from app import create_app
from app.config import Config
import re

app = create_app(config_object=Config)
with app.test_client() as client:
    # Login
    response = client.get('/login')
    html = response.get_data(as_text=True)
    import re
    csrf_meta = re.search(r'meta name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))
    if not csrf_meta:
        csrf_input = re.search(r'name="csrf_token" value="([^"]+)"', html)
        csrf_token = csrf_input.group(1) if csrf_input else None
    else:
        csrf_token = csrf_meta.group(1)
    
    print('CSRF token found')
    
    # Login
    response = client.post('/login', data={
        'email': 'twikirizeobed@gmail.com',
        'password': 'password123',
        'csrf_token': csrf_token
    }, follow_redirects=True)
    print('Login status:', response.status_code)
    
    # Now test settings page
    response = client.get('/admin/owner/settings')
    print('Settings status:', response.status_code)
    html = response.get_data(as_text=True)
    
    # Check for form actions
    import re
    save_actions = re.findall(r'action="([^"]*)"', response.get_data(as_text=True))
    for action in save_actions:
        if 'otp-delivery-config' in action or 'twilio-sms' in action or 'twilio-whatsapp' in action:
            print('Form action:', action)
    
    # Check for test functions in JS
    if 'testOtpChannel' in response.get_data(as_text=True):
        print('testOtpChannel: FOUND')
    if 'testTwilioSms' in response.get_data(as_text=True):
        print('testTwilioSms: FOUND')
    if 'testTwilioWhatsApp' in response.get_data(as_text=True):
        print('testTwilioWhatsApp: FOUND')
        
    # Check form actions
    save_actions = re.findall(r'action="([^"]*)"', html)
    for action in save_actions:
        if 'otp-delivery-config' in action or 'twilio-sms' in action or 'twilio-whatsapp' in action:
            print('Form action:', action)