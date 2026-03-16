#app/auth/services/org.py

from app.extensions import db
from app.identity.models.user import OrgUserRole, OrgRole
from app.auth.sessions import revoke_all_sessions_for_user
#---------------------------------------------------
#Transfer ownership
#----------------------------------------

def transfer_org_ownership(org_id: int, from_user_id: int, to_user_id: int):
    org_owner_role = OrgRole.query.filter_by(name="org_owner").first()
    org_admin_role = OrgRole.query.filter_by(name="org_admin").first()

    if not org_owner_role or not org_admin_role:
        raise RuntimeError("Org roles not seeded")

    # downgrade old owner to admin
    OrgUserRole.query.filter_by(
        org_id=org_id,
        user_id=from_user_id,
        org_role_id=org_owner_role.id
    ).update({"org_role_id": org_admin_role.id})

    # promote new owner
    OrgUserRole.query.filter_by(
        org_id=org_id,
        user_id=to_user_id
    ).update({"org_role_id": org_owner_role.id})

    db.session.commit()

    # optional: revoke sessions for both users
    revoke_all_sessions_for_user(from_user_id)
    revoke_all_sessions_for_user(to_user_id)
