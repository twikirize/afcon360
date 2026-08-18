# app/identity/services/user_roles.py
"""
User roles service for loading RBAC roles
"""

from sqlalchemy import select
from app.extensions import db
from app.utils.transactions import transactional
from app.identity.models import Organisation, Role, User, UserRole


@transactional("Load RBAC roles for user")
def load_user_roles(user_id: int):
    """
    Fetch all roles assigned to a user along with organisation and role details.
    Any DB error is caught, logged, and rolled back automatically via @transactional.
    """
    statement = (
        select(
            UserRole.id.label('user_roles_id'),
            UserRole.user_id,
            UserRole.role_id,
            UserRole.assigned_by,
            UserRole.assigned_at,
            User.id.label('assigned_by_user_id'),
            User.username.label('assigned_by_username'),
            Organisation.id.label('org_id'),
            Organisation.legal_name.label('org_name'),
            Role.name.label('role_name'),
            Role.scope.label('role_scope'),
        )
        .select_from(UserRole)
        .outerjoin(User, User.id == UserRole.assigned_by)
        .outerjoin(Organisation, Organisation.id == User.default_org_id)
        .outerjoin(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id)
    )
    result = db.session.execute(statement)
    
    # Convert to list of dictionaries for easier consumption
    roles = []
    for row in result:
        roles.append({
            'user_roles_id': row.user_roles_id,
            'user_id': row.user_id,
            'role_id': row.role_id,
            'assigned_by': row.assigned_by,
            'assigned_at': row.assigned_at,
            'assigned_by_user_id': row.assigned_by_user_id,
            'assigned_by_username': row.assigned_by_username,
            'org_id': row.org_id,
            'org_name': row.org_name,
            'role_name': row.role_name,
            'role_scope': row.role_scope
        })
    
    return roles
