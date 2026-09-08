from app import create_app
app = create_app()
with app.test_client() as c:
    with app.app_context():
        resp = c.get('/me/capabilities/dashboard')
        print(f'Status: {resp.status_code}')
        print(f'Content type: {resp.content_type[:50]}')
        print(f'Preview length: {len(resp.data)}')
        print(f'First 300 chars: {resp.data[:300].decode()[:300]}')