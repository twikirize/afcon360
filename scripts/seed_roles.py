"""# scripts/seed_roles.py

from app import create_app
from app.extensions import db
from app.identity.models import Role, Permission, Organization
app = create_app()
with app.app_context():
    roles = ["super_admin","platform_admin","user","guest","org_owner","org_admin","manager","staff","viewer"]
    for r in roles:
        if not Role.query.filter_by(name=r).first():
            db.session.add(Role(name=r, scope="global" if r in ["super_admin","platform_admin","user","guest"] else "org"))
    db.session.commit()
    print("Seeded roles")

"""
