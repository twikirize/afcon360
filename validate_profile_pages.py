import os
from app import create_app
from app.extensions import db
from app.identity.models.user import User
from werkzeug.security import generate_password_hash

os.environ['FLASK_ENV'] = 'testing'
app = create_app()
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
with app.app_context():
    owner = User.query.filter_by(email='owner@test.com').first()
    if not owner:
        owner = User(username='test_owner', email='owner@test.com')
        owner.password_hash = generate_password_hash('test_password')
        owner.is_app_owner = True
        db.session.add(owner)
        db.session.commit()
    else:
        owner.password_hash = generate_password_hash('test_password')
        db.session.commit()

    client = app.test_client()
    login = client.post('/login', data={'email': 'owner@test.com', 'password': 'test_password'}, follow_redirects=True)
    print('LOGIN', login.status_code, login.request.path)
    print('LOGIN snippet:', login.data.decode('utf-8', 'replace')[:250].replace('\n', ' '))
    for path in ['/account', '/profile/edit', '/profile/me']:
        resp = client.get(path, follow_redirects=True)
        print('\nPATH', path, 'status', resp.status_code, 'final', resp.request.path)
        print('BODY snippet:', resp.data.decode('utf-8', 'replace')[:350].replace('\n', ' '))
