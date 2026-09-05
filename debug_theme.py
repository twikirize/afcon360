import sys
sys.path.insert(0, r'C:\Users\OBED\Desktop\afcon360_app')
from app import create_app
app = create_app()
with app.app_context():
    from app.models.theme import UserThemePreference, GlobalTheme
    from app.identity.models.user import User
    users = User.query.all()
    for u in users:
        pref = UserThemePreference.query.get(u.id)
        print(f'User {u.id}: has_preference={pref is not None}')