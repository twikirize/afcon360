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
    
    html = response.get_data(as_text=True)
    if 'Invalid username or password' in html:
        print('LOGIN FAILED - Invalid credentials')
    elif 'Welcome' in html or 'Dashboard' in html or 'logout' in html.lower():
        print('LOGIN SUCCESS')
    else:
        print('Login status:', response.status_code)
        if 'Invalid' in html or 'invalid' in html:
            print('Login failed - invalid credentials')
    
    # Now test settings page
    response = client.get('/admin/owner/settings')
    print('Settings status:', response.status_code)
    html = response.get_data(as_text=True)
    
    for term, label in [
        ('OTP Delivery Methods', 'Unified section title'),
        ('Email (OCI)', 'Email section'),
        ('SMS (Twilio)', 'SMS section'),
        ('WhatsApp (Twilio)', 'WhatsApp section'),
        ('testOtpChannel', 'Test function'),
        ('save_otp_delivery_config', 'Save route'),
        ('test_twilio_sms', 'SMS test route'),
        ('test_twilio_whatsapp', 'WhatsApp test route'),
        ('save_otp_delivery_config', 'Save route'),
    ]:
        if term in response.get_data(as_text=True):
            print(f'{label}: FOUND')
        else:
            print(f'{label}: NOT FOUND')