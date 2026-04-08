from sqlalchemy import text
from app.extensions import db
from app.utils.transactions import transactional

@transactional("Load RBAC roles for user")
def load_user_roles(user_id: int):
    """
    Fetch all roles assigned to a user along with organisation and role details.
    Any DB error is caught, logged, and rolled back automatically via @transactional.
    """
    result = db.session.execute(
        text("""
            SELECT ur.id AS user_roles_id,
                   ur.user_id,
                   ur.role_id,
                   ur.assigned_by,
                   ur.assigned_at,
                   u.id AS assigned_by_user_id,
                   u.username AS assigned_by_username,
                   o.id AS org_id,
                   o.legal_name AS org_name,
                   r.name AS role_name,
                   r.scope AS role_scope
            FROM user_roles ur
            LEFT JOIN users u ON u.id = ur.assigned_by
            LEFT JOIN organisations o ON o.id = u.default_org_id
            LEFT JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = :uid
        """),
        {"uid": user_id}
    ).fetchall()

    return result
