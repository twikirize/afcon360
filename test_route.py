import os
os.environ['FLASK_APP'] = 'app.py'
from app import create_app
app = create_app()
with app.test_client() as client:
    # Try to access /accommodation/
    response = client.get('/accommodation/')
    print(f"Status: {response.status_code}")
    if response.status_code >= 400:
        print(f"Response: {response.data[:2000]}")